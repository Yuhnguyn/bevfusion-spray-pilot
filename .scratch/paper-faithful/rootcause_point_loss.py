#!/usr/bin/env python3
"""ROOT CAUSE (vế cuối): plume có THỰC SỰ lấy mất điểm của xe không?

Bước trước đã loại H-B (hộp giả) và ủng hộ H-A (chắn tầm nhìn):
    hộp bị plume chắn trong góc phương vị: 27,5 % mất
    hộp không bị chắn                    :  3,7 % mất   (gấp 7,4 lần)

Nhưng "chắn" mới là tương quan. Vế vật lý phải là: **số điểm LiDAR của chính vật
thể giảm**. Cơ chế khả dĩ trong code: ``raycast`` trả ``real_points`` đã bị
**attenuate** (``att_real_points``), tức tia đi qua plume bị hấp thụ ⇒ điểm của xe
phía sau bị mất/thay. Đây là occlusion viết bằng attenuation.

Phép đo quyết định: đếm điểm nằm TRONG hộp GT, ở hai nhánh.
  clean  : points[label != 2]           (điểm gốc)
  plume  : ray.real_points + detections (điểm sau raycast)

Nếu nhóm MẤT có số điểm xe giảm mạnh còn nhóm GIỮ thì không ⇒ occlusion là cơ chế.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from proxy_eval.matcher import bev_iou  # noqa: E402
from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import RaycastConfig, raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

ROOT = REPO / "data/SemanticSprayDataset"
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SPRAY = 2
SEED = 0
IOU_THRESH = 0.5
SCORE_THRESH = 0.2
RANGE_M = 54.0


def _load() -> dict:
    frames: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            frames.setdefault((row["scene_token"], row["frame_idx"]), {})[
                row["arm"]] = row
    return frames


def _count_in_box(xyz: np.ndarray, box: np.ndarray) -> int:
    if len(xyz) == 0:
        return 0
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    dz = xyz[:, 2] - box[2]
    inside = ((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)
              & (dz >= -0.1) & (dz <= box[5] + 0.1))
    return int(inside.sum())


def main() -> None:
    frames = _load()
    table = load_beam_table()
    cache: dict = {}
    rows = []

    for (scene, frame_idx), arms in sorted(frames.items()):
        clean_rec, plume_rec = arms.get("clean"), arms.get("plume")
        if clean_rec is None or plume_rec is None:
            continue
        key = (scene, frame_idx)
        if key not in cache:
            path = ROOT / scene
            scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
            boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
            if not boxes_json.is_file():
                cache[key] = None
            else:
                meta = read_metadata(path / "metadata.txt")
                obj_v = float(meta["object_velocity"]) / 3.6
                ego_v = float(meta.get("ego_velocity")
                              or meta["object_velocity"]) / 3.6
                cls = "crafter" if "Crafter" in scene else "golf"
                points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                                     dtype=np.float32).reshape(-1, 5)
                labels = np.fromfile(path / "labels" / f"{scan}.label",
                                     dtype=np.uint32)
                boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
                road_z = float(np.median(boxes[:, 2])) if len(boxes) else -0.4
                clean_pts = points[labels != SPRAY].astype(np.float32)

                state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                           min_range_m=2.5, max_range_m=50.0))
                context = PlumeContext(scene_token=scene, frame_index=frame_idx,
                                       epoch=0, sensor_origin=np.zeros(3),
                                       ego_speed_mps=ego_v, object_speed_mps=obj_v,
                                       wfh_mm=sample_wfh_mm(scene, 0, 0),
                                       road_z_m=road_z)
                result = inject_plume_stateful(
                    clean_pts, boxes, context, state, seed=SEED,
                    token=f"occ/{frame_idx}", config=PlumeConfig(),
                    vehicle_class=cls)
                ray = raycast_frame(result.points, state.select_alive(),
                                    table=table, road_z_m=road_z,
                                    rng=np.random.default_rng(SEED),
                                    config=RaycastConfig(max_distance_m=50.0))
                plume_pts = np.concatenate([ray.real_points, ray.detections],
                                           axis=0)
                cache[key] = (boxes, clean_pts[:, :3].astype(np.float64),
                              plume_pts[:, :3].astype(np.float64), road_z)
        if cache[key] is None:
            continue
        boxes, clean_xyz, plume_xyz, _road_z = cache[key]

        cb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
                       for b in clean_rec["boxes"]], dtype=float)
        cs = np.array([float(b["score"]) for b in clean_rec["boxes"]])
        pb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
                       for b in plume_rec["boxes"]], dtype=float)
        ps = np.array([float(b["score"]) for b in plume_rec["boxes"]])
        if len(cb) == 0:
            continue

        for gt in cb:
            ious = [bev_iou(b, gt) for b in cb]
            if max(ious) < IOU_THRESH:
                continue
            ci = int(np.argmax(ious))
            if cs[ci] < SCORE_THRESH:
                continue
            pi = int(np.argmax([bev_iou(b, gt) for b in pb])) if len(pb) else -1
            p_score = float(ps[pi]) if pi >= 0 else 0.0
            p_iou = bev_iou(pb[pi], gt) if pi >= 0 else 0.0
            lost = not (p_iou >= IOU_THRESH and p_score >= SCORE_THRESH)

            n_clean = _count_in_box(clean_xyz, gt)
            n_plume = _count_in_box(plume_xyz, gt)
            if n_clean == 0:
                continue
            rows.append((n_clean, n_plume, n_plume / n_clean,
                         p_score - float(cs[ci]), 1.0 if lost else 0.0))

    arr = np.array(rows, dtype=float)
    kept = arr[arr[:, 4] == 0]
    lost = arr[arr[:, 4] == 1]

    print(f"hộp có >=1 điểm xe trong hộp: {len(arr)}   GIỮ {len(kept)}   MẤT {len(lost)}")
    print()
    print(f"{'':<16} {'GIỮ p50':>9} {'MẤT p50':>9} {'GIỮ mean':>9} {'MẤT mean':>9}")
    for col, name in ((0, "điểm xe clean"), (1, "điểm xe plume"), (2, "tỉ lệ giữ"), (3, "Δscore")):
        print(f"{name:<16} {np.median(kept[:,col]):9.3f} {np.median(lost[:,col]):9.3f} "
              f"{kept[:,col].mean():9.3f} {lost[:,col].mean():9.3f}")

    print()
    print(f"Tổng điểm xe trong hộp: clean {arr[:,0].sum():.0f} -> "
          f"plume {arr[:,1].sum():.0f} "
          f"({100*(arr[:,1].sum()/arr[:,0].sum()-1):+.1f} %)")
    print()
    print("Tỉ lệ MẤT theo mức mất điểm xe:")
    for lo, hi in ((0.0, 0.9), (0.9, 0.99), (0.99, 1.01), (1.01, 99)):
        mask = (arr[:, 2] >= lo) & (arr[:, 2] < hi)
        if mask.sum() < 5:
            continue
        label = (f"<90 %" if hi <= 0.9 else
                 f"90-99 %" if hi <= 0.99 else
                 f"99-101 %" if hi <= 1.01 else f">101 %")
        print(f"  giữ {label:>9} điểm xe : n={int(mask.sum()):4d}  "
              f"mất {100*np.mean(arr[mask,4]):5.1f} %  "
              f"Δscore p50 {np.median(arr[mask,3]):+.3f}")

    def corr(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    print()
    print(f"corr(tỉ lệ điểm xe giữ, mất hộp) = {corr(arr[:,2], arr[:,4]):+.3f}")
    print(f"corr(Δđiểm xe,            Δscore) = {corr(arr[:,1]-arr[:,0], arr[:,3]):+.3f}")


if __name__ == "__main__":
    main()
