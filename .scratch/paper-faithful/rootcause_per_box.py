#!/usr/bin/env python3
"""ROOT CAUSE bước 4: điểm plume có nằm trong footprint hộp GT không, và nó có
DỰ BÁO được mức rớt score của CHÍNH hộp đó không?

Đây là phép đo ở tầng HỘP (không phải scene), nên mạnh hơn tương quan scene:
678 hộp khớp GT trong cổng C, mỗi hộp có Δscore đo được. Nếu bệnh là "điểm plume
pha loãng feature của voxel chứa xe", thì hộp nào có NHIỀU điểm plume trong
footprint phải rớt score NHIỀU — quan hệ liều–đáp ứng ở mức từng hộp.

Ba biến đếm cho mỗi hộp:
  n_in_box3d   : điểm plume nằm trong hộp 3D
  n_in_footprint: điểm plume trong footprint xy, BẤT KỂ z
  n_within_2m  : điểm plume trong 2 m quanh tâm hộp (xy)

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_per_box.py
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
SPRAY, VEH = 2, 1
SEED = 0
IOU_THRESH = 0.5
SCORE_THRESH = 0.2


def load_cfg() -> dict:
    by: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            by.setdefault((row["scene_token"], row["frame_idx"]), {})[row["arm"]] = row
    return by


def plume_points(scene: str, frame_idx: int, cache: dict) -> np.ndarray | None:
    """Điểm plume (thô, trước raycast) cho một frame, sinh lại y hệt cổng C."""
    key = (scene, frame_idx)
    if key in cache:
        return cache[key]
    path = ROOT / scene
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
    cls = "crafter" if "Crafter" in scene else "golf"
    cfg = replace(PlumeStateConfig(), diffusion_alpha=0.0,
                  min_range_m=2.5, max_range_m=50.0)
    state = PlumeState(cfg)
    wfh = sample_wfh_mm(scene, 0, 0)

    scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
    points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                         dtype=np.float32).reshape(-1, 5)
    labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
    if labels.size != points.shape[0]:
        cache[key] = None
        return None
    boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
    if not boxes_json.is_file():
        cache[key] = None
        return None
    boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
    road_z = float(np.median(boxes[:, 2])) if len(boxes) else float(
        np.percentile(points[:, 2], 5.0))

    clean = points[labels != SPRAY].astype(np.float32)
    context = PlumeContext(scene_token=scene, frame_index=frame_idx, epoch=0,
                           sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                           object_speed_mps=obj_v, wfh_mm=wfh, road_z_m=road_z)
    result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                   token=f"pb/{frame_idx}", config=PlumeConfig(),
                                   vehicle_class=cls)
    # điểm plume = phần thêm vào so với clean (điểm thô, chưa raycast)
    total = result.points.shape[0]
    n_clean = clean.shape[0]
    plume = (result.points[n_clean:] if total > n_clean else
             np.zeros((0, 5), dtype=np.float32))
    cache[key] = np.asarray(plume, dtype=np.float64)
    return cache[key]


def count_in_box(xyz: np.ndarray, box: np.ndarray) -> tuple[int, int, int]:
    if len(xyz) == 0:
        return 0, 0, 0
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    in_fp = (np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)
    dz = xyz[:, 2] - box[2]
    in_3d = in_fp & (dz >= 0) & (dz <= box[5])
    near = np.hypot(dx, dy) <= 2.0
    return int(in_3d.sum()), int(in_fp.sum()), int(near.sum())


def main() -> None:
    by = load_cfg()
    table = load_beam_table()
    rows: list[tuple[int, int, int, float, float, float]] = []
    cache: dict = {}

    for (scene, frame_idx), arms in sorted(by.items()):
        clean, plume = arms.get("clean"), arms.get("plume")
        if clean is None or plume is None:
            continue
        gt_boxes = np.array(
            [[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
             for b in clean["boxes"]], dtype=float)
        if len(gt_boxes) == 0:
            continue
        cb = gt_boxes
        cs = np.array([float(b["score"]) for b in clean["boxes"]])
        pb = gt_boxes if len(plume["boxes"]) == 0 else gt_boxes
        pboxes = np.array(
            [[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
             for b in plume["boxes"]], dtype=float)
        ps = np.array([float(b["score"]) for b in plume["boxes"]])

        plume_xyz = plume_points(scene, frame_idx, cache)
        if plume_xyz is None:
            continue
        if len(plume_xyz) == 0:
            continue

        for gt in cb:
            ious = [bev_iou(b, gt) for b in cb]
            if not ious or max(ious) < IOU_THRESH:
                continue
            ci = int(np.argmax(ious))
            if cs[ci] < SCORE_THRESH:
                continue
            pi = int(np.argmax([bev_iou(b, gt) for b in pboxes])) if len(pboxes) else -1
            p_score = float(ps[pi]) if pi >= 0 else 0.0
            p_iou = bev_iou(pboxes[pi], gt) if pi >= 0 else 0.0
            matched_plume = p_iou >= IOU_THRESH and p_score >= SCORE_THRESH
            n3d, nfp, n2 = count_in_box(plume_xyz[:, :3], gt)
            rows.append((n3d, nfp, n2, float(cs[ci]), p_score,
                         1.0 if matched_plume else 0.0))

    arr = np.array(rows, dtype=float)
    n = len(arr)
    print(f"hộp khớp GT (clean score >= {SCORE_THRESH}): {n}")
    lost = arr[arr[:, 5] == 0]
    kept = arr[arr[:, 5] == 1]
    print(f"  plume GIU : {len(kept)}")
    print(f"  plume MAT : {len(lost)}")
    print()

    print(f"{'':<18} {'GIU (p50)':>10} {'MAT (p50)':>10} {'GIU (mean)':>11} {'MAT (mean)':>11}")
    for col, name in ((0, "n_in_box3d"), (1, "n_in_footprint"), (2, "n_within_2m")):
        print(f"{name:<18} {np.median(kept[:,col]):10.2f} {np.median(lost[:,col]):10.2f} "
              f"{kept[:,col].mean():11.2f} {lost[:,col].mean():11.2f}")

    print()
    print("Tương quan với Δscore (score_plume − score_clean):")
    ds = arr[:, 4] - arr[:, 3]
    for col, name in ((0, "n_in_box3d"), (1, "n_in_footprint"), (2, "n_within_2m")):
        if arr[:, col].std() < 1e-9:
            print(f"  {name:<18} (không đổi, không tính được)")
            continue
        print(f"  {name:<18} r = {float(np.corrcoef(arr[:,col], ds)[0,1]):+.3f}")

    print()
    print("Nhóm theo số điểm plume trong footprint:")
    for lo, hi in ((0, 0), (1, 5), (6, 20), (21, 1e9)):
        mask = ((arr[:, 1] >= lo) & (arr[:, 1] <= hi)) if hi < 1e9 else (arr[:, 1] >= lo)
        if mask.sum() == 0:
            continue
        label = f"{int(lo)}" if lo == hi else (f"{int(lo)}+" if hi >= 1e9
                                              else f"{int(lo)}–{int(hi)}")
        print(f"  {label:>8} điểm : n={int(mask.sum()):4d}  "
              f"mất hộp {100*np.mean(arr[mask,5]==0):5.1f} %  "
              f"Δscore p50 {np.median(ds[mask]):+.3f}")


if __name__ == "__main__":
    main()
