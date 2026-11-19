#!/usr/bin/env python3
"""ROOT CAUSE bước 6 (vế cuối): CƠ CHẾ trong bán kính 6 m là gì?

Bước 5 đã chốt hiệu ứng là CỤC BỘ (~6 m), không toàn cục:
    hộp 0 điểm trong footprint, plume cách 2–4 m  -> mất 22,9 %
    plume cách 6–10 m                              -> mất  5,8 %
    plume cách 20+ m                               -> mất  0,9 %

Hai cơ chế còn lại trong bán kính đó:

  H-A "CHẮN TẦM NHÌN" (angular occlusion): plume nằm trên chùm tia cảm biến->hộp,
      gần cảm biến hơn ⇒ trong không gian BEV nó lấp vùng trước vật thể, làm
      feature của vật thể bị "chìm".
  H-B "VẬT THỂ GIẢ TRANH CHỖ" (decoy): plume tự sinh ra hộp dự đoán, và hộp giả đó
      chiếm mất đỉnh heatmap / bị NMS giữ thay hộp thật.

Phép đo phân biệt:
  * `wedge` : tỉ lệ điểm plume nằm trong góc phương vị của hộp VÀ gần cảm biến hơn
              tâm hộp. Cao ở nhóm MẤT ⇒ H-A.
  * `decoy` : có hộp dự đoán khác (không khớp GT) nằm trong 4 m quanh hộp GT không,
              và score của nó. Nếu hộp giả đó CAO hơn hộp thật ở nhóm MẤT ⇒ H-B.

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_occlusion_vs_decoy.py
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
DECOY_RADIUS = 4.0


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
                                   token=f"od/{frame_idx}", config=PlumeConfig(),
                                   vehicle_class=cls)
    plume = np.asarray(result.points[clean.shape[0]:], dtype=np.float64)
    cache[key] = plume
    return plume


def main() -> None:
    by = _load()
    cache: dict = {}
    rows = []

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

        bear_p = np.arctan2(plume_xyz[:, 1], plume_xyz[:, 0])
        r_p = np.linalg.norm(plume_xyz[:, :2], axis=1)

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

            # H-A: plume trong góc phương vị của hộp và gần cảm biến hơn tâm hộp
            bear_b = float(np.arctan2(gt[1], gt[0]))
            r_b = float(np.hypot(gt[0], gt[1]))
            half = float(np.arctan2(gt[4] / 2, max(r_b, 1.0)))
            delta = np.abs(np.angle(np.exp(1j * (bear_p - bear_b))))
            in_wedge = (delta <= half) & (r_p < r_b)
            wedge = float(in_wedge.sum())

            # H-B: hộp dự đoán KHÔNG khớp GT nào, nằm trong DECOY_RADIUS quanh hộp GT
            decoy_score = 0.0
            for k in range(len(pb)):
                if bev_iou(pb[k], gt) >= IOU_THRESH:
                    continue
                if np.hypot(pb[k][0] - gt[0], pb[k][1] - gt[1]) <= DECOY_RADIUS:
                    decoy_score = max(decoy_score, float(ps[k]))

            rows.append((wedge, decoy_score, p_score - float(cs[ci]),
                         1.0 if lost else 0.0))

    arr = np.array(rows, dtype=float)
    kept = arr[arr[:, 3] == 0]
    lost = arr[arr[:, 3] == 1]
    print(f"tổng hộp khớp GT: {len(arr)}   GIỮ {len(kept)}   MẤT {len(lost)}")
    print()

    print("H-A  ĐIỂM PLUME TRONG GÓC PHƯƠNG VỊ CỦA HỘP (gần cảm biến hơn):")
    for name, group in (("GIỮ", kept), ("MẤT", lost)):
        print(f"  {name}: p50 = {np.median(group[:,0]):6.1f}   "
              f"mean = {group[:,0].mean():6.1f}   "
              f">0 điểm: {100*np.mean(group[:,0] > 0):5.1f} %")
    print()
    print("  Tỉ lệ MẤT theo số điểm plume chắn tầm nhìn:")
    for lo, hi in ((0, 0), (1, 5), (6, 20), (21, 1e9)):
        mask = ((arr[:, 0] >= lo) & (arr[:, 0] <= hi)) if hi < 1e9 else (arr[:, 0] >= lo)
        if mask.sum() < 5:
            continue
        label = f"{int(lo)}" if lo == hi else (f"{int(lo)}+" if hi >= 1e9
                                               else f"{int(lo)}–{int(hi)}")
        print(f"    {label:>7} điểm : n={int(mask.sum()):4d}  "
              f"mất {100*np.mean(arr[mask,3]):5.1f} %")
    print()
    print(f"  corr(số điểm chắn, mất hộp) = "
          f"{float(np.corrcoef(arr[:,0], arr[:,3])[0,1]):+.3f}")

    print()
    print("H-B  HỘP GIẢ TRANH CHỖ (trong 4 m quanh hộp GT):")
    for name, group in (("GIỮ", kept), ("MẤT", lost)):
        print(f"  {name}: có hộp giả = {100*np.mean(group[:,1] > 0):5.1f} %   "
              f"score giả p50 = {np.median(group[:,1]):.3f}")
    both = arr[(arr[:, 1] > 0)]
    print(f"  trong nhóm CÓ hộp giả (n={len(both)}): mất {100*np.mean(both[:,3]):.1f} %")
    print(f"  corr(score hộp giả, mất hộp) = "
          f"{float(np.corrcoef(arr[:,1], arr[:,3])[0,1]):+.3f}")


if __name__ == "__main__":
    main()
