#!/usr/bin/env python3
"""Vì sao corr(Δrecall, lượng spray) lại DƯƠNG — nghịch lý cần giải.

Quan sát gây lo:
    scene 0000 :  55 điểm/frame  ->  Δrecall −0,526   (sụp nặng)
    Golf 0102  : 342 điểm/frame  ->  Δrecall −0,091   (sụp nhẹ)
    ⇒ corr(Δrecall, lượng spray) = +0,192 (DƯƠNG)

Nếu spray gây hại thì nhiều spray phải hại hơn. Dấu dương nghĩa là biến `lượng
spray` đang bị **nhiễu bởi một biến thứ ba**. Script này tìm biến đó.

Ứng viên (đo được, không suy luận):
  A. `n_gt`      : số GT box/frame — scene nhiều vật thể thì mỗi vật thể dễ "cứu"
                   hơn khi tính recall trung bình? Không, recall là trung bình
                   trên GT nên không thiên vị. NHƯNG nếu lượng spray tỉ lệ với
                   số box thì hai biến này collinear.
  B. `n_det`     : số detection/frame — scene nhiều detection thì recall cao hơn
                   **ngay cả khi không có spray**; spray nhiều thường đi cùng
                   scene nhiều điểm ⇒ confound.
  C. `r_gt_p50`  : vật thể ở xa thì khó, plume ở xa thì nhiều điểm hơn (khối lớn
                   hơn) ⇒ spray nhiều = vật thể xa = recall vốn đã thấp.
  D. `base_recall`: recall của nhánh clean. Nếu clean đã cao (0,99) thì không thể
                   giảm nhiều (trần); nếu clean 0,5 thì giảm được nhiều ⇒
                   **hiệu ứng trần** tạo tương quan âm giả, và nếu lượng spray
                   tương quan dương với clean_recall thì tổng thành dương.

Phép kiểm quyết định: hồi quy Δrecall theo (lượng spray) có/không có `base_recall`.
Nếu hệ số của lượng spray **đổi dấu** khi thêm `base_recall` ⇒ nghịch lý chỉ là
confound, không phải cơ chế thật.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SUMMARY = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections_summary.json"


def main() -> None:
    summary = json.load(open(SUMMARY))
    paired = summary["summary"]["paired"]["plume_minus_clean"]
    rec_clean = paired["recall_per_scene"]["clean"]
    rec_plume = paired["recall_per_scene"]["plume"]
    rec_real = paired["recall_per_scene"].get("real")

    agg: dict[str, dict] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            scene = row["scene_token"]
            entry = agg.setdefault(scene, {
                "inj": [], "base": [], "n_det": [], "n_gt": [], "r_gt": [],
                "n_frame": 0,
            })
            if row["arm"] == "plume":
                entry["inj"].append(row["n_injected"])
                entry["n_det"].append(len(row["boxes"]))
                entry["n_frame"] += 1
            elif row["arm"] == "clean":
                entry["base"].append(row["n_real_points_before"])
                entry["n_gt"].append(len(row["boxes"]))

    scenes = [s for s in sorted(agg) if s in rec_clean and s in rec_plume]
    n = len(scenes)
    delta = np.array([rec_plume[s] - rec_clean[s] for s in scenes])
    spray = np.array([np.mean(agg[s]["inj"]) for s in scenes])
    base_rec = np.array([rec_clean[s] for s in scenes])
    n_det = np.array([np.mean(agg[s]["n_det"]) for s in scenes])
    base_pts = np.array([np.mean(agg[s]["base"]) for s in scenes])
    spray_pct = 100.0 * spray / base_pts

    def corr(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    print(f"n scene = {n}")
    print()
    print("Ma trận tương quan (Pearson):")
    labels = ["Δrecall", "spray/f", "spray%", "clean_rec", "n_det/f", "base_pts/f"]
    cols = [delta, spray, spray_pct, base_rec, n_det, base_pts]
    print("            " + " ".join(f"{lab:>11}" for lab in labels))
    for i, lab in enumerate(labels):
        print(f"{lab:>11} " + " ".join(f"{corr(cols[i], cols[j]):+11.3f}"
                                       for j in range(len(cols))))
    print()

    # Hồi quy bội tối giản bằng lstsq, chuẩn hoá để so hệ số
    def standardise(x):
        return (x - x.mean()) / (x.std() + 1e-12)

    def fit(features, target):
        matrix = np.column_stack([np.ones(len(target))] + features)
        coef, *_ = np.linalg.lstsq(matrix, target, rcond=None)
        pred = matrix @ coef
        ss_res = float(((target - pred) ** 2).sum())
        ss_tot = float(((target - target.mean()) ** 2).sum())
        return coef, 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    print("Hồi quy Δrecall (biến đã chuẩn hoá, hệ số so được trực tiếp):")
    coef1, r2_1 = fit([standardise(spray)], delta)
    print(f"  chỉ spray/f          : beta_spray = {coef1[1]:+.4f}   R² = {r2_1:.3f}")

    coef2, r2_2 = fit([standardise(spray), standardise(base_rec)], delta)
    print(f"  spray/f + clean_rec  : beta_spray = {coef2[1]:+.4f}   "
          f"beta_clean = {coef2[2]:+.4f}   R² = {r2_2:.3f}")

    coef3, r2_3 = fit([standardise(spray_pct)], delta)
    print(f"  chỉ spray%           : beta = {coef3[1]:+.4f}   R² = {r2_3:.3f}")

    coef4, r2_4 = fit([standardise(spray_pct), standardise(base_rec)], delta)
    print(f"  spray% + clean_rec   : beta_spray% = {coef4[1]:+.4f}   "
          f"beta_clean = {coef4[2]:+.4f}   R² = {r2_4:.3f}")
    print()

    print("Hiệu ứng TRẦN (ceiling):")
    print(f"  clean_recall  min/p50/max = {base_rec.min():.3f} / "
          f"{np.median(base_rec):.3f} / {base_rec.max():.3f}")
    print(f"  Δrecall       min/p50/max = {delta.min():+.3f} / "
          f"{np.median(delta):+.3f} / {delta.max():+.3f}")
    print(f"  corr(clean_rec, Δrecall)  = {corr(base_rec, delta):+.3f}")
    print()
    print("  Nhóm theo clean_recall:")
    for lo, hi in ((0.0, 0.85), (0.85, 0.95), (0.95, 1.01)):
        mask = (base_rec >= lo) & (base_rec < hi)
        if mask.sum() == 0:
            continue
        print(f"    clean {lo:.2f}–{hi:.2f}: n={int(mask.sum())}  "
              f"Δ p50 {np.median(delta[mask]):+.3f}  "
              f"spray/f p50 {np.median(spray[mask]):6.1f}")
    print()

    if rec_real is not None:
        delta_real = np.array([rec_real[s] - rec_clean[s] for s in scenes])
        print(f"Đối chứng với spray THẬT: corr(Δrecall_real, clean_rec) = "
              f"{corr(base_rec, delta_real):+.3f}")
        print(f"  Δreal p50 = {np.median(delta_real):+.3f}  "
              f"(nếu cũng phụ thuộc clean_rec thì hiệu ứng trần là chung, "
              f"không riêng của plume)")


if __name__ == "__main__":
    main()
