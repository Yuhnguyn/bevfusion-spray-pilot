#!/usr/bin/env python3
"""Chữ ký quyết định: `wfh` lấy mẫu THEO SCENE đã vào nhánh plume chưa?

Lý do chọn chữ ký này (không dùng cự ly hộp như lần trước, đã thử và vô dụng vì
hộp sinh ra khắp scene):
  * `wfh` lấy mẫu theo scene ⇒ mỗi scene một mức ướt khác nhau ⇒ tỉ lệ điểm bị
    attenuate **khác nhau giữa các scene**, và **tương quan** với `wfh` của scene.
  * production dùng `wfh = 1,0` cố định ⇒ mọi scene cùng một mức ướt ⇒ nếu
    attenuation vẫn phụ thuộc hình học road-band thì vẫn dao động, NHƯNG không
    tương quan với `sample_wfh_mm(scene)`.

Đây là phép kiểm không thể trùng hợp: `sample_wfh_mm` là hàm hash của riêng repo
này; production không bao giờ gọi nó.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from spray.plume_context import sample_wfh_mm  # noqa: E402

JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"


def main() -> None:
    agg: dict[str, dict[str, int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] != "plume":
                continue
            entry = agg.setdefault(row["scene_token"],
                                   {"att": 0, "before": 0, "n": 0})
            entry["att"] += int(row["n_real_points_attenuated"])
            entry["before"] += int(row["n_real_points_before"])
            entry["n"] += 1

    print(f"{'scene':<34} {'wfh scene':>10} {'atten%':>7} {'n':>4}")
    sampled, attenuation = [], []
    for scene in sorted(agg):
        wfh = sample_wfh_mm(scene, 0, 0)
        frac = 100.0 * agg[scene]["att"] / max(agg[scene]["before"], 1)
        sampled.append(wfh)
        attenuation.append(frac)
        print(f"{scene.split('/')[1][:32]:<34} {wfh:10.3f} {frac:7.3f} "
              f"{agg[scene]['n']:4d}")

    w = np.array(sampled)
    f = np.array(attenuation)
    corr = float(np.corrcoef(w, f)[0, 1])
    print()
    print(f"corr(wfh, atten%) = {corr:+.3f}")
    print(f"so scene wfh < 1,0: {int((w < 1.0).sum())}/{len(w)}   "
          f"(production luon 1,0)")
    print(f"wfh min/p50/max = {w.min():.3f} / {np.median(w):.3f} / {w.max():.3f}")
    print()
    print("Đọc: nếu wfh phân tán theo scene VÀ corr dương rõ ⇒ lấy mẫu theo scene "
          "đã chạy.")
    print("     Nếu mọi scene cùng một mức ẩm ⇒ nhánh plume là production "
          "(wfh = 1,0 cố định).")


if __name__ == "__main__":
    main()
