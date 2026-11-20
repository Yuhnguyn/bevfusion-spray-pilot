#!/usr/bin/env python3
"""ROOT CAUSE (chốt): nhiễm độc FEATURE trong vành 2-6 m giải thích phần còn lại.

Bức tranh sau các phép đo trước:
  - điểm xe bị xoá: 2903 điểm/954 frame = 0,01 % tổng; 1818 trong hộp GT.
    Hộp có >=1 điểm bị xoá mất 27-33 %; hộp 0 điểm bị xoá vẫn mất **13,3 %**.
  - voxel eviction: 0 điểm bị cắt.
  - hộp giả (decoy): loại.
  - hộp 0 điểm plume trong footprint: cách plume 2-4 m mất 22,9 %, >20 m mất 0,9 %.

⇒ Còn **13,3 % mất mát cơ sở** không do mất điểm và không do điểm trong hộp. Ứng viên:
plume nằm trong VÀNH 2-6 m quanh vật thể làm nhiễu đặc trưng cục bộ mà detector dùng
để tự tin vào hộp đó (receptive field của BEV feature map).

Phép đo quyết định: **quan hệ liều-đáp ứng theo số điểm plume trong vành**, chỉ trên
những hộp có **0 điểm plume trong footprint** (để loại hẳn cơ chế điểm-trong-hộp).
Nếu tỉ lệ mất tăng đơn điệu theo số điểm vành ⇒ nhiễm độc feature cục bộ là thật.

Vành định nghĩa theo BEV (xy), bỏ qua z:
  vòng trong  : cách tâm hộp 2,0-4,0 m
  vòng ngoài  : cách tâm hộp 4,0-6,0 m
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
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
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


def _plume(scene: str, frame_idx: int, cache: dict) -> np.ndarray | None:
    key = (scene, frame_idx)
    if key in cache:
        return cache[key]
    path = ROOT / scene
    scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
    boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
    if not boxes_json.is_file():
        cache[key] = None
        return None
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
    cls = "crafter" if "Crafter" in scene else "golf"
    points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                         dtype=np.float32).reshape(-1, 5)
    labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
    boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
    road_z = float(np.median(boxes[:, 2])) if len(boxes) else -0.4
    clean = points[labels != SPRAY].astype(np.float32)
    state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                               min_range_m=2.5, max_range_m=50.0))
    context = PlumeContext(scene_token=scene, frame_index=frame_idx, epoch=0,
                           sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                           object_speed_mps=obj_v,
                           wfh_mm=sample_wfh_mm(scene, 0, 0), road_z_m=road_z)
    result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                   token=f"an/{frame_idx}", config=PlumeConfig(),
                                   vehicle_class=cls)
    plume = np.asarray(result.points[clean.shape[0]:], dtype=np.float64)
    cache[key] = plume
    return plume


def _counts(xyz: np.ndarray, box: np.ndarray) -> tuple[int, int, int]:
    """(trong footprint, vành 2-4 m, vành 4-6 m)."""
    if len(xyz) == 0:
        return 0, 0, 0
    dist = np.linalg.norm(xyz[:, :2] - box[:2], axis=1)
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    fp = ((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)).sum()
    inner = int(((dist >= 2.0) & (dist < 4.0)).sum())
    outer = int(((dist >= 4.0) & (dist < 6.0)).sum())
    return int(fp), inner, outer


def main() -> None:
    frames = _load()
    cache: dict = {}
    rows = []

    for (scene, frame_idx), arms in sorted(frames.items()):
        clean_rec, plume_rec = arms.get("clean"), arms.get("plume")
        if clean_rec is None or plume_rec is None:
            continue
        plume_xyz = _plume(scene, frame_idx, cache)
        if plume_xyz is None or len(plume_xyz) == 0:
            continue
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
            fp, inner, outer = _counts(plume_xyz[:, :3], gt)
            rows.append((fp, inner, outer, inner + outer,
                         p_score - float(cs[ci]), 1.0 if lost else 0.0))

    arr = np.array(rows, dtype=float)
    print(f"tổng hộp: {len(arr)}")
    print(f"hộp có 0 điểm plume trong footprint: {int((arr[:,0]==0).sum())}")
    print()

    clean_zero = arr[arr[:, 0] == 0]
    print("CHỈ hộp có 0 điểm trong footprint — quan hệ liều đáp ứng theo VÀNH 2-6 m:")
    print(f"{'điểm vành':>12} {'n':>6} {'mất hộp':>9} {'Δscore p50':>12}")
    bands = ((0, 0), (1, 50), (51, 200), (201, 600), (601, 1e9))
    doses, losses = [], []
    for lo, hi in bands:
        mask = ((clean_zero[:, 3] >= lo)
                & (clean_zero[:, 3] <= hi if hi < 1e9 else clean_zero[:, 3] >= lo))
        if mask.sum() < 5:
            continue
        label = f"{int(lo)}" if lo == hi else (
            f"{int(lo)}+" if hi >= 1e9 else f"{int(lo)}-{int(hi)}")
        rate = float(np.mean(clean_zero[mask, 5]))
        print(f"{label:>12} {int(mask.sum()):6d} {100*rate:8.1f} % "
              f"{np.median(clean_zero[mask,4]):+12.3f}")
        doses.append(float(np.mean(clean_zero[mask, 3])))
        losses.append(rate)

    if len(doses) >= 3:
        print()
        print(f"  corr(liều vành, mất hộp) = "
              f"{float(np.corrcoef(clean_zero[:,3], clean_zero[:,5])[0,1]):+.3f}")
        print(f"  tương quan mức nhóm     = {float(np.corrcoef(doses, losses)[0,1]):+.3f}")

    print()
    print("Đối chứng: vành trong (2-4 m) vs vành ngoài (4-6 m), hộp 0 điểm footprint")
    for name, col in (("vành trong 2-4 m", 1), ("vành ngoài 4-6 m", 2)):
        have = clean_zero[clean_zero[:, col] > 0]
        none = clean_zero[clean_zero[:, col] == 0]
        if len(have) < 5 or len(none) < 5:
            continue
        print(f"  {name}: có plume n={len(have):4d} mất {100*np.mean(have[:,5]):5.1f} %"
              f"  |  không n={len(none):4d} mất {100*np.mean(none[:,5]):5.1f} %")


if __name__ == "__main__":
    main()
