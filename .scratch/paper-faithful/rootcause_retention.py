#!/usr/bin/env python3
"""GIẢI NGHỊCH LÝ: retention rate — biến thật đứng sau "spray nhiều hại ít".

Đã biết mỗi frame chỉ có **đúng 1 GT box** (`n_gt/frame = 1,00` ở cả 12 scene),
nên recall mỗi frame là nhị phân: 0 hoặc 1. Vì thế:

    recall(scene)  = tỉ lệ frame bắt được
    Δrecall        = plume_recall − clean_recall

Định nghĩa `retention` = trong số frame mà **clean bắt được**, bao nhiêu % frame
**plume vẫn bắt được**:

    plume_recall = clean_recall × retention
    ⇒ Δrecall    = clean_recall × (retention − 1)

Đây là mấu chốt: nếu `retention` GẦN NHƯ KHÔNG ĐỔI giữa các scene, thì Δrecall
chỉ là `clean_recall` nhân một hằng số — và "nghịch lý spray nhiều hại ít" hoàn
toàn là **artefact của mẫu số**: scene mà detector vốn đã yếu (clean thấp) thì
Δrecall nhỏ theo, bất kể plume dày hay mỏng.

Phép đo:
  1. retention từng scene, kèm CI Wilson;
  2. retention có phụ thuộc lượng spray không;
  3. dự đoán Δrecall từ `clean_recall × (retention−1)` so với Δrecall thật.
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
SUMMARY = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections_summary.json"
ROOT = REPO / "data/SemanticSprayDataset"
IOU_THRESH = 0.5
SCORE_THRESH = 0.2
RANGE_M = 54.0

_GT: dict = {}


def gt_of(scene: str, frame_idx: int) -> np.ndarray | None:
    key = (scene, frame_idx)
    if key in _GT:
        return _GT[key]
    path = ROOT / scene
    scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
    boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
    if not boxes_json.is_file():
        _GT[key] = None
        return None
    meta = read_metadata(path / "metadata.txt")
    boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json),
                                   float(meta["object_velocity"]) / 3.6)
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 9)[:, :7]
    keep = np.linalg.norm(boxes[:, :2], axis=1) <= RANGE_M
    _GT[key] = boxes[keep]
    return _GT[key]


def hit(record, gt: np.ndarray) -> bool:
    if record is None or len(gt) == 0:
        return False
    det = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"],
                     b["yaw"]] for b in record["boxes"]], dtype=float)
    scores = np.array([float(b["score"]) for b in record["boxes"]])
    if len(det) == 0:
        return False
    mask = ((np.linalg.norm(det[:, :2], axis=1) <= RANGE_M)
            & (scores >= SCORE_THRESH))
    det = det[mask]
    return any(bev_iou(d, gt[0]) >= IOU_THRESH for d in det)


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z = 1.96
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return float(centre - half), float(centre + half)


def main() -> None:
    frames: dict[tuple[str, int], dict] = {}
    spray: dict[str, list[int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["scene_token"], row["frame_idx"])
            frames.setdefault(key, {})[row["arm"]] = row
            if row["arm"] == "plume":
                spray.setdefault(row["scene_token"], []).append(int(row["n_injected"]))
    spray_mean = {k: float(np.mean(v)) for k, v in spray.items()}

    stats: dict[str, dict[str, int]] = {}
    for (scene, frame_idx), arms in sorted(frames.items()):
        if "clean" not in arms or "plume" not in arms:
            continue
        gt = gt_of(scene, frame_idx)
        if gt is None or len(gt) == 0:
            continue
        entry = stats.setdefault(scene, {"clean_hit": 0, "plume_hit": 0,
                                         "n": 0, "retained": 0, "clean_hit_n": 0})
        c = hit(arms["clean"], gt)
        p = hit(arms["plume"], gt)
        entry["n"] += 1
        entry["clean_hit"] += int(c)
        entry["plume_hit"] += int(p)
        if c:
            entry["clean_hit_n"] += 1
            entry["retained"] += int(p)

    print(f"{'scene':<24} {'clean':>6} {'plume':>6} {'retention':>10} "
          f"{'CI95':>16} {'spray/f':>8} {'Δrecall':>8} {'dự đoán':>8}")
    rows = []
    for scene in sorted(stats):
        e = stats[scene]
        n = e["n"]
        clean_r = e["clean_hit"] / n
        plume_r = e["plume_hit"] / n
        ret = e["retained"] / max(e["clean_hit_n"], 1)
        lo, hi = wilson(e["retained"], e["clean_hit_n"])
        delta = plume_r - clean_r
        predicted = clean_r * (ret - 1.0)
        rows.append((scene, clean_r, plume_r, ret, lo, hi,
                     spray_mean.get(scene, float("nan")), delta, predicted))
        print(f"{scene.split('/')[1][:22]:<24} {clean_r:6.3f} {plume_r:6.3f} "
              f"{ret:10.3f} [{lo:5.3f};{hi:5.3f}] {spray_mean.get(scene, 0):8.1f} "
              f"{delta:+8.3f} {predicted:+8.3f}")

    ret = np.array([r[3] for r in rows])
    spray = np.array([r[6] for r in rows])
    delta = np.array([r[7] for r in rows])
    predicted = np.array([r[8] for r in rows])
    clean_r = np.array([r[1] for r in rows])

    def corr(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    print()
    print("RETENTION — biến thật:")
    print(f"  p25/p50/p75 = {np.percentile(ret,25):.3f} / "
          f"{np.median(ret):.3f} / {np.percentile(ret,75):.3f}")
    print(f"  min/max     = {ret.min():.3f} / {ret.max():.3f}")
    print(f"  corr(retention, spray/f)  = {corr(ret, spray):+.3f}")
    print(f"  corr(Δrecall,   spray/f)  = {corr(delta, spray):+.3f}   <- nghịch lý")
    print(f"  corr(Δrecall, clean_rec)  = {corr(delta, clean_r):+.3f}")
    print()
    print("KIỂM CHỨNG công thức Δrecall = clean_recall × (retention − 1):")
    print(f"  corr(thật, dự đoán) = {corr(delta, predicted):+.3f}")
    print(f"  sai số tuyệt đối p50 = {np.median(np.abs(delta - predicted)):.4f}")
    print(f"  sai số tuyệt đối max = {np.max(np.abs(delta - predicted)):.4f}")
    print()
    print("Nếu retention ~ KHÔNG ĐỔI và công thức khớp ⇒ nghịch lý đã được giải:")
    print("  Δrecall chỉ là clean_recall nhân hằng số; scene khó (clean thấp) thì")
    print("  Δ nhỏ theo, không liên quan plume dày/mỏng.")


if __name__ == "__main__":
    main()
