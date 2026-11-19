#!/usr/bin/env python3
"""Vì sao recall sụp: theo dõi CHÍNH hộp khớp GT qua hai nhánh.

Bối cảnh: spray chỉ thêm 55–400 điểm/frame (0,04–1,47 % điểm nền), vậy mà recall
sụp. Nếu là che khuất thì phải có quan hệ liều–đáp ứng; đo được corr ≈ +0,19
(dương!) nên KHÔNG phải che khuất. Nghi phạm còn lại: score của hộp đúng bị đẩy
xuống dưới ngưỡng 0,20.

Script này, cho từng frame: tìm hộp clean khớp GT (IoU ≥ 0,5). Nếu plume vẫn còn
hộp đó, in score của nó ở hai nhánh. Nếu mất, in score của hộp gần nhất ở plume.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from proxy_eval.matcher import bev_iou  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
ROOT = REPO / "data/SemanticSprayDataset"
IOU_THRESH = 0.5
RANGE_M = 54.0
SCORE_THRESH = 0.2


def _load() -> dict:
    by: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            r = json.loads(line)
            by.setdefault((r["scene_token"], r["frame_idx"]), {})[r["arm"]] = r
    return by


def _gt(scene: str, frame_idx: int, cache: dict):
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
    boxes, _, _ = _boxes_to_arrays(
        read_frame_boxes(boxes_json), float(meta["object_velocity"]) / 3.6
    )
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 9)[:, :7]
    keep = np.linalg.norm(boxes[:, :2], axis=1) <= RANGE_M
    cache[key] = boxes[keep]
    return cache[key]


def _arrays(detections: list[dict]):
    if not detections:
        return np.zeros((0, 7)), np.zeros(0)
    boxes = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
                      for b in detections], dtype=float)
    scores = np.array([float(b["score"]) for b in detections], dtype=float)
    return boxes, scores


def main() -> None:
    by = _load()
    cache: dict = {}
    rows = []
    n_kept_above = 0
    n_kept_below = 0
    n_disappeared = 0

    for (scene, frame_idx), arms in sorted(by.items()):
        gt = _gt(scene, frame_idx, cache)
        if gt is None or len(gt) == 0:
            continue
        clean, plume = arms.get("clean"), arms.get("plume")
        if clean is None or plume is None:
            continue
        cb, cs = _arrays(clean["boxes"])
        pb, ps = _arrays(plume["boxes"])

        for gt_box in gt:
            # hộp clean khớp GT này
            ious = [bev_iou(b, gt_box) for b in cb] if len(cb) else []
            if not ious or max(ious) < IOU_THRESH:
                continue
            ci = int(np.argmax(ious))
            if cs[ci] < SCORE_THRESH:
                continue  # clean cũng trượt -> không phải ca ta quan tâm

            pi = int(np.argmax([bev_iou(b, gt_box) for b in pb])) if len(pb) else -1
            p_iou = bev_iou(pb[pi], gt_box) if pi >= 0 else 0.0
            p_score = float(ps[pi]) if pi >= 0 else float("nan")
            hit = p_iou >= IOU_THRESH and p_score >= SCORE_THRESH

            if hit:
                n_kept_above += 1
            else:
                if p_iou >= IOU_THRESH:
                    n_kept_below += 1          # hộp vẫn đúng chỗ, score rớt
                else:
                    n_disappeared += 1         # hộp biến mất / lệch
            rows.append((scene, frame_idx, float(cs[ci]), p_score, p_iou, hit))

    total = len(rows)
    print(f"frame co GT khop o nhanh clean: {total}")
    print(f"  plume GIU  (IoU>=0,5 va score>=0,2): {n_kept_above} ({100*n_kept_above/total:.1f} %)")
    print(f"  plume ROI score (IoU>=0,5, score<0,2): {n_kept_below} ({100*n_kept_below/total:.1f} %)")
    print(f"  plume MAT HOP  (IoU<0,5): {n_disappeared} ({100*n_disappeared/total:.1f} %)")
    print()

    arr = np.array([[r[2], r[3], r[4]] for r in rows], dtype=float)
    print(f"score clean  min/median/max = "
          f"{arr[:,0].min():.3f} / {np.median(arr[:,0]):.3f} / {arr[:,0].max():.3f}")
    valid = ~np.isnan(arr[:,1])
    print(f"score plume  min/median/max = "
          f"{np.nanmin(arr[:,1]):.3f} / {np.nanmedian(arr[:,1]):.3f} / {np.nanmax(arr[:,1]):.3f}")
    print(f"IoU plume    min/median/max = "
          f"{arr[:,2].min():.3f} / {np.median(arr[:,2]):.3f} / {arr[:,2].max():.3f}")
    print()

    lost = [r for r in rows if not r[5]]
    if lost:
        print("20 ca MAT, xep theo delta score:")
        lost.sort(key=lambda r: (r[3] if not np.isnan(r[3]) else 0))
        for scene, frame_idx, sc_, ps_, piou, _ in lost[:20]:
            print(f"  {scene.split('/')[1][:26]:<28} f{frame_idx:<4d} "
                  f"score {sc_:.3f} -> {ps_:.3f}  IoU {piou:.3f}")


if __name__ == "__main__":
    main()
