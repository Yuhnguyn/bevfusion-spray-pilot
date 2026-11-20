#!/usr/bin/env python3
"""ĐÍNH CHÍNH phép đo "điểm xe không mất" — đo lại ĐÚNG cách.

Phép đo trước (`rootcause_point_loss.py`) SAI: nó lấy
    plume_pts = concatenate([ray.real_points, ray.detections])
tức **cộng lại** các detection plume vào số điểm, nên phần điểm thật bị xoá được
bù lại bằng điểm plume rơi gần đó ⇒ ra "176 070 -> 176 190 (+0,1 %)".

Code thật (`spray/raycast.py:384-396`):
    point_dropped = np.repeat(wins[group_hit], group_counts)
    dropped[point_indices[point_dropped]] = True
    stats.real_dropped_plume_stronger = int(point_dropped.sum())
    return RaycastResult(real_points=real[~dropped], ...)
⇒ điểm thật **BỊ XOÁ** khi detection plume mạnh hơn trên cùng tia.

Đo lại đúng:
  1. `real_points` MỘT MÌNH (không cộng detections) — đếm trong hộp GT;
  2. `stats.real_dropped_plume_stronger` — tổng điểm bị xoá;
  3. bao nhiêu điểm bị xoá nằm TRONG hộp GT;
  4. tương quan với việc hộp bị mất.
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


def _load() -> dict:
    frames: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            frames.setdefault((row["scene_token"], row["frame_idx"]), {})[
                row["arm"]] = row
    return frames


def _in_box(xyz: np.ndarray, box: np.ndarray) -> np.ndarray:
    if len(xyz) == 0:
        return np.zeros(0, dtype=bool)
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    dz = xyz[:, 2] - box[2]
    return ((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)
            & (dz >= -0.1) & (dz <= box[5] + 0.1))


def _key(xyz: np.ndarray, decimals: int = 4) -> set:
    if len(xyz) == 0:
        return set()
    return set(map(tuple, np.round(xyz[:, :3], decimals).tolist()))


def main() -> None:
    frames = _load()
    table = load_beam_table()
    cache: dict = {}
    rows = []
    tot_dropped = 0
    tot_dropped_in_box = 0
    tot_real_clean = 0
    tot_real_plume = 0

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
                clean_xyz = points[labels != SPRAY][:, :3].astype(np.float64)

                state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                           min_range_m=2.5, max_range_m=50.0))
                context = PlumeContext(scene_token=scene, frame_index=frame_idx,
                                       epoch=0, sensor_origin=np.zeros(3),
                                       ego_speed_mps=ego_v, object_speed_mps=obj_v,
                                       wfh_mm=sample_wfh_mm(scene, 0, 0),
                                       road_z_m=road_z)
                result = inject_plume_stateful(
                    points[labels != SPRAY].astype(np.float32), boxes, context,
                    state, seed=SEED, token=f"fx/{frame_idx}",
                    config=PlumeConfig(), vehicle_class=cls)
                ray = raycast_frame(result.points, state.select_alive(),
                                    table=table, road_z_m=road_z,
                                    rng=np.random.default_rng(SEED),
                                    config=RaycastConfig(max_distance_m=50.0))
                # CHỈ real_points — KHÔNG cộng detections
                plume_real_xyz = ray.real_points[:, :3].astype(np.float64)
                dropped_n = int(ray.stats.real_dropped_plume_stronger)
                # điểm thật bị xoá = có ở clean, không có ở plume real_points
                clean_keys = _key(clean_xyz)
                plume_keys = _key(plume_real_xyz)
                gone_keys = clean_keys - plume_keys
                cache[key] = (boxes, clean_xyz, plume_real_xyz, dropped_n,
                              gone_keys, road_z)
        if cache[key] is None:
            continue
        boxes, clean_xyz, plume_xyz, dropped_n, gone_keys, _rz = cache[key]
        tot_dropped += dropped_n
        tot_real_clean += len(clean_xyz)
        tot_real_plume += len(plume_xyz)

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

            n_clean = int(_in_box(clean_xyz, gt).sum())
            n_plume = int(_in_box(plume_xyz, gt).sum())
            # điểm bị xoá nằm trong hộp: dựng mảng từ gone_keys
            gone_in_box = 0
            if gone_keys:
                gone_arr = np.array(sorted(gone_keys), dtype=np.float64)
                gone_in_box = int(_in_box(gone_arr, gt).sum())
                tot_dropped_in_box += gone_in_box
            if n_clean == 0:
                continue
            rows.append((n_clean, n_plume, n_plume / n_clean, gone_in_box,
                         p_score - float(cs[ci]), 1.0 if lost else 0.0))

    arr = np.array(rows, dtype=float)
    kept = arr[arr[:, 5] == 0]
    lost = arr[arr[:, 5] == 1]

    print(f"hộp có >=1 điểm xe: {len(arr)}   GIỮ {len(kept)}   MẤT {len(lost)}")
    print()
    print(f"{'':<20} {'GIỮ p50':>9} {'MẤT p50':>9} {'GIỮ mean':>9} {'MẤT mean':>9}")
    for col, name in ((0, "điểm xe clean"), (1, "điểm xe plume(real)"),
                      (2, "tỉ lệ giữ"), (3, "số điểm bị xoá")):
        print(f"{name:<20} {np.median(kept[:,col]):9.3f} {np.median(lost[:,col]):9.3f} "
              f"{kept[:,col].mean():9.3f} {lost[:,col].mean():9.3f}")

    print()
    print("Tổng điểm thật (chỉ real_points, KHÔNG cộng detections):")
    print(f"  clean {tot_real_clean} -> plume {tot_real_plume} "
          f"({100*(tot_real_plume/max(tot_real_clean,1)-1):+.2f} %)")
    print(f"  stats.real_dropped_plume_stronger (tổng): {tot_dropped}")
    print(f"  điểm bị xoá rơi TRONG hộp GT (tổng): {tot_dropped_in_box}")
    print()
    print("Tỉ lệ MẤT theo số điểm xe bị xoá:")
    for lo, hi in ((0, 0), (1, 5), (6, 20), (21, 1e9)):
        mask = ((arr[:, 3] >= lo) & (arr[:, 3] <= hi)) if hi < 1e9 else (arr[:, 3] >= lo)
        if mask.sum() < 5:
            continue
        label = f"{int(lo)}" if lo == hi else (f"{int(lo)}+" if hi >= 1e9
                                               else f"{int(lo)}-{int(hi)}")
        print(f"  {label:>7} điểm xoá : n={int(mask.sum()):4d}  "
              f"mất {100*np.mean(arr[mask,5]):5.1f} %  "
              f"Δscore p50 {np.median(arr[mask,4]):+.3f}")

    print()
    print(f"corr(tỉ lệ điểm giữ, mất hộp) = "
          f"{float(np.corrcoef(arr[:,2], arr[:,5])[0,1]):+.3f}")
    print(f"corr(số điểm xoá,    mất hộp) = "
          f"{float(np.corrcoef(arr[:,3], arr[:,5])[0,1]):+.3f}")


if __name__ == "__main__":
    main()
