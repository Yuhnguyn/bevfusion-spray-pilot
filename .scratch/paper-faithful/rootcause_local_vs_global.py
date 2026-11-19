#!/usr/bin/env python3
"""ROOT CAUSE bước 5: TÁCH hai cơ chế — cục bộ (điểm trong hộp) vs toàn cục.

Bước 4 cho thấy quan hệ liều–đáp ứng ở tầng hộp:
      0 điểm trong footprint  -> 12,9 % mất hộp
      1–5 điểm               -> 30,9 %
      6–20 điểm              -> 44,2 %
      21+ điểm               -> 47,8 %
Nhưng 1592/1761 hộp có 0 điểm vẫn mất 12,9 % ⇒ còn một cơ chế **toàn cục**.

Phép đo tách hai cơ chế: với những hộp CÓ 0 điểm plume trong footprint, đo
khoảng cách từ tâm hộp tới điểm plume gần nhất, rồi so nhóm GIỮ vs nhóm MẤT.
  * nếu MẤT gần plume hơn GIỮ rõ rệt  ⇒ vẫn là hiệu ứng CỤC BỘ (bán kính lớn hơn
    footprint), và ta đo được bán kính đó;
  * nếu hai nhóm như nhau               ⇒ hiệu ứng TOÀN CỤC (feature map bị pha
    loãng), không phụ thuộc vị trí.

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_local_vs_global.py
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
    by: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            by.setdefault((row["scene_token"], row["frame_idx"]), {})[row["arm"]] = row
    return by


def _plume(scene: str, frame_idx: int, cache: dict) -> np.ndarray | None:
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
    boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
    if labels.size != points.shape[0] or not boxes_json.is_file():
        cache[key] = None
        return None
    boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
    road_z = float(np.median(boxes[:, 2])) if len(boxes) else -0.4
    clean = points[labels != SPRAY].astype(np.float32)
    context = PlumeContext(scene_token=scene, frame_index=frame_idx, epoch=0,
                           sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                           object_speed_mps=obj_v, wfh_mm=wfh, road_z_m=road_z)
    result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                   token=f"lg/{frame_idx}", config=PlumeConfig(),
                                   vehicle_class=cls)
    plume = result.points[clean.shape[0]:]
    cache[key] = np.asarray(plume, dtype=np.float64)
    return cache[key]


def _footprint_count(xyz: np.ndarray, box: np.ndarray) -> int:
    if len(xyz) == 0:
        return 0
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    return int(((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)).sum())


def main() -> None:
    by = _load()
    cache: dict = {}
    rows = []  # (dist_to_plume, in_fp, delta_score, lost)

    for (scene, frame_idx), arms in sorted(by.items()):
        clean, plume = arms.get("clean"), arms.get("plume")
        if clean is None or plume is None:
            continue
        plume_xyz = _plume(scene, frame_idx, cache)
        if plume_xyz is None or len(plume_xyz) == 0:
            continue
        cb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
                       for b in clean["boxes"]], dtype=float)
        cs = np.array([float(b["score"]) for b in clean["boxes"]])
        pb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
                       for b in plume["boxes"]], dtype=float)
        ps = np.array([float(b["score"]) for b in plume["boxes"]])
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
            dist = float(np.min(np.linalg.norm(plume_xyz[:, :2] - gt[:2], axis=1)))
            in_fp = _footprint_count(plume_xyz[:, :3], gt)
            rows.append((dist, in_fp, p_score - float(cs[ci]), 1.0 if lost else 0.0))

    arr = np.array(rows, dtype=float)
    print(f"tổng hộp khớp GT: {len(arr)}")

    # Chỉ hộp có 0 điểm trong footprint -> tách cục bộ vs toàn cục
    zero = arr[arr[:, 1] == 0]
    kept = zero[zero[:, 3] == 0]
    lost = zero[zero[:, 3] == 1]
    print(f"\nHộp có 0 điểm plume trong footprint: {len(zero)}")
    print(f"  GIỮ : {len(kept)}")
    print(f"  MẤT : {len(lost)}  ({100*len(lost)/max(len(zero),1):.1f} %)")
    print()
    print("Khoảng cách tâm hộp -> điểm plume gần nhất (m):")
    print(f"  GIỮ  p25/p50/p75 = {np.percentile(kept[:,0],25):6.2f} / "
          f"{np.percentile(kept[:,0],50):6.2f} / {np.percentile(kept[:,0],75):6.2f}")
    print(f"  MẤT  p25/p50/p75 = {np.percentile(lost[:,0],25):6.2f} / "
          f"{np.percentile(lost[:,0],50):6.2f} / {np.percentile(lost[:,0],75):6.2f}")
    print()
    print("Tỉ lệ MẤT theo khoảng cách tới plume (hộp 0 điểm trong footprint):")
    for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 10), (10, 20), (20, 1e9)):
        mask = (zero[:, 0] >= lo) & (zero[:, 0] < hi)
        if mask.sum() < 8:
            continue
        label = f"{lo:g}–{hi:g}" if hi < 1e9 else f"{lo:g}+"
        print(f"  {label:>8} m : n={int(mask.sum()):4d}  "
              f"mất {100*np.mean(zero[mask,3]):5.1f} %  "
              f"Δscore p50 {np.median(zero[mask,2]):+.3f}")
    print()
    print(f"corr(khoảng cách, mất hộp) trên nhóm 0-điểm = "
          f"{float(np.corrcoef(zero[:,0], zero[:,3])[0,1]):+.3f}")


if __name__ == "__main__":
    main()
