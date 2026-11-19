#!/usr/bin/env python3
"""Vì sao corr(Δrecall, lượng spray) DƯƠNG — phân tích đối chứng với spray THẬT.

Nghịch lý cần giải:
    scene 0000 :  55 điểm/frame -> Δrecall −0,526
    Golf 0102  : 342 điểm/frame -> Δrecall −0,091
    corr(Δrecall, spray/frame) = +0,192

Ba phép kiểm ở đây:
  1. Spray thật có cùng quy luật không? Nếu `Δrecall(real)` cũng tương quan dương
     với lượng spray thì nghịch lý **không phải** của generator — nó là tính chất
     của bộ dữ liệu/độ khó scene.
  2. `spray/frame` có bị confound bởi số điểm nền (scene nhiều điểm -> nhiều cụm,
     đồng thời recall vốn cao) không?
  3. Tỉ số `Δplume/Δreal` — nếu ổn định quanh một hằng số thì "gấp N lần" là cách
     mô tả đúng hơn "tương quan với liều".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SUMMARY = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections_summary.json"
ROOT = REPO / "data/SemanticSprayDataset"
IOU_THRESH = 0.5
RANGE_M = 54.0
SCORE_THRESH = 0.2


def _real_recall_per_scene() -> dict[str, float]:
    """Recall nhánh ``real`` theo scene, tính bằng đúng công thức của harness.

    ``recall_per_scene`` trong summary chỉ có ``clean`` và ``plume``. Nhánh
    ``real`` phải tự tính, dùng cùng quy tắc: label-agnostic, mỗi detection dùng
    một lần, lọc ``‖xy‖ <= 54`` và ``score >= 0,20``. Bộ đếm này đã được kiểm
    chứng khớp số của harness (ra đúng −0,2188 cho nhánh plume).
    """
    from proxy_eval.matcher import bev_iou
    from spray.sspp_adapter import (
        _boxes_to_arrays, read_frame_boxes, read_metadata,
    )

    cache: dict = {}
    per_scene: dict[str, list[float]] = {}

    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] != "real":
                continue
            scene, frame_idx = row["scene_token"], row["frame_idx"]
            key = (scene, frame_idx)
            if key not in cache:
                path = ROOT / scene
                scan = sorted(p.stem for p in
                              (path / "velodyne").glob("*.bin"))[frame_idx]
                boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
                if not boxes_json.is_file():
                    cache[key] = None
                else:
                    meta = read_metadata(path / "metadata.txt")
                    boxes, _, _ = _boxes_to_arrays(
                        read_frame_boxes(boxes_json),
                        float(meta["object_velocity"]) / 3.6)
                    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 9)[:, :7]
                    keep = np.linalg.norm(boxes[:, :2], axis=1) <= RANGE_M
                    cache[key] = boxes[keep]
            gt = cache[key]
            if gt is None or len(gt) == 0:
                continue

            detections = row["boxes"]
            if len(detections) == 0:
                per_scene.setdefault(scene, []).append(0.0)
                continue
            det = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"],
                             b["yaw"]] for b in detections], dtype=float)
            scores = np.array([float(b["score"]) for b in detections])
            mask = ((np.linalg.norm(det[:, :2], axis=1) <= RANGE_M)
                    & (scores >= SCORE_THRESH))
            det, scores = det[mask], scores[mask]

            used = np.zeros(len(det), dtype=bool)
            matched = 0
            for gt_index in range(len(gt)):
                for det_index in np.argsort(-scores, kind="stable"):
                    if used[det_index]:
                        continue
                    if bev_iou(det[det_index], gt[gt_index]) >= IOU_THRESH:
                        used[det_index] = True
                        matched += 1
                        break
            per_scene.setdefault(scene, []).append(matched / len(gt))

    return {scene: float(np.mean(values)) for scene, values in per_scene.items()}


def main() -> None:
    summary = json.load(open(SUMMARY))
    paired = summary["summary"]["paired"]["plume_minus_clean"]
    rec = paired["recall_per_scene"]

    agg: dict[str, dict[str, list]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            entry = agg.setdefault(row["scene_token"],
                                   {"inj": [], "base": [], "real_det": [], "n_frame": 0})
            if row["arm"] == "plume":
                entry["inj"].append(int(row["n_injected"]))
            elif row["arm"] == "clean":
                entry["base"].append(int(row["n_real_points_before"]))
                entry["n_frame"] += 1
            elif row["arm"] == "real":
                entry["real_det"].append(len(row["boxes"]))

    scenes = [s for s in sorted(agg) if s in rec["clean"]]
    spray = np.array([np.mean(agg[s]["inj"]) for s in scenes])
    base = np.array([np.mean(agg[s]["base"]) for s in scenes])
    clean = np.array([rec["clean"][s] for s in scenes])
    d_plume = np.array([rec["plume"][s] - rec["clean"][s] for s in scenes])
    # Δrecall của spray THẬT: recall(real) − recall(clean). Summary chỉ có
    # recall_per_scene cho clean/plume, nên lấy `real` từ per_speed rồi tính lại
    # theo scene bằng chính công thức recall = TP/(TP+FN) của harness.
    real_rec = _real_recall_per_scene()
    d_real = np.array([real_rec[s] - rec["clean"][s] for s in scenes])

    def corr(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    print(f"{'scene':<26} {'clean':>6} {'plume':>6} {'real':>6} "
          f"{'d_plume':>8} {'d_real':>7} {'spray/f':>8} {'base_pts':>9}")
    for i, scene in enumerate(scenes):
        print(f"{scene.split('/')[1][:24]:<26} {clean[i]:6.3f} "
              f"{rec['plume'][scene]:6.3f} {real_rec[scene]:6.3f} "
              f"{d_plume[i]:+8.3f} {d_real[i]:+7.3f} {spray[i]:8.1f} {base[i]:9.0f}")

    print()
    print("1) SPRAY THẬT có cùng quy luật?")
    print(f"   corr(d_plume, spray/f) = {corr(d_plume, spray):+.3f}")
    print(f"   corr(d_real,  spray/f) = {corr(d_real,  spray):+.3f}")
    print(f"   corr(d_real,  d_plume) = {corr(d_real, d_plume):+.3f}")
    print(f"   d_real  p50 = {np.median(d_real):+.3f}  "
          f"(min {d_real.min():+.3f}, max {d_real.max():+.3f})")

    print()
    print("2) CONFOUND: spray/frame vs số điểm nền")
    print(f"   corr(spray/f, base_pts/f) = {corr(spray, base):+.3f}")
    print(f"   corr(clean_rec, base_pts/f) = {corr(clean, base):+.3f}")
    print(f"   corr(clean_rec, spray/f)    = {corr(clean, spray):+.3f}")
    print()
    print("   Bảng theo mức điểm nền:")
    order = np.argsort(base)
    for lo, hi in ((0, 28000), (28000, 30000), (30000, 999999)):
        mask = (base >= lo) & (base < hi)
        if mask.sum() == 0:
            continue
        print(f"     base {lo:>6}–{hi:<6}: n={int(mask.sum()):2d}  "
              f"clean p50 {np.median(clean[mask]):.3f}  "
              f"d_plume p50 {np.median(d_plume[mask]):+.3f}  "
              f"spray/f p50 {np.median(spray[mask]):6.1f}")

    print()
    print("3) TỈ SỐ Δplume/Δreal (mô tả 'gấp N lần' thay cho 'tương quan liều')")
    ratios = []
    for i in range(len(scenes)):
        if abs(d_real[i]) > 1e-6:
            ratios.append(d_plume[i] / d_real[i])
    ratios = np.array(ratios)
    print(f"   n = {len(ratios)}")
    print(f"   p25/p50/p75 = {np.percentile(ratios,25):.2f} / "
          f"{np.median(ratios):.2f} / {np.percentile(ratios,75):.2f}")
    print(f"   min/max = {ratios.min():.2f} / {ratios.max():.2f}")
    print(f"   corr(tỉ số, spray/f) = {corr(ratios, spray[:len(ratios)]):+.3f}"
          if len(ratios) == len(spray) else "")

    print()
    print("4) Nhóm theo độ khó scene (clean_recall):")
    for lo, hi in ((0.0, 0.85), (0.85, 1.01)):
        mask = (clean >= lo) & (clean < hi)
        if mask.sum() == 0:
            continue
        print(f"   clean {lo:.2f}–{hi:.2f}: n={int(mask.sum())}  "
              f"d_plume p50 {np.median(d_plume[mask]):+.3f}  "
              f"d_real p50 {np.median(d_real[mask]):+.3f}  "
              f"spray/f p50 {np.median(spray[mask]):6.1f}")


if __name__ == "__main__":
    main()
