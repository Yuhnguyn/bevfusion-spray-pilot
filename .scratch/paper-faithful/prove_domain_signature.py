#!/usr/bin/env python3
"""Chứng minh bằng CHỮ KÝ HÌNH HỌC: cổng C có bật miền Cách A hay không.

`n_injected` không cùng thang giữa hai đường (cổng C đếm qua raycast, local đếm
điểm plume thô) nên không so được. Dùng chữ ký trực tiếp, đọc từ chính hộp dự đoán:

  * miền BẬT  ⇒ `‖pos‖ − radius ≥ 2,5 m`, `‖pos‖ ≤ 50 m` ⇒ **không** hộp nào ở rất
    gần gốc và không hộp nào quá 50 m;
  * miền TẮT (production) ⇒ có hộp sát gốc (R < 2,5 m) và hộp trôi xa (> 50 m).

Đây là phép kiểm không thể trùng hợp: hai cấu hình cho hai hình bao khác nhau.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"


def main() -> None:
    arms: dict[str, list[float]] = {"clean": [], "plume": [], "real": []}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            arm = row["arm"]
            for box in row["boxes"]:
                arms[arm].append(float(np.hypot(box["x"], box["y"])))

    print(f"{'nhánh':>6} {'n hộp':>8} {'R min':>7} {'R p01':>7} {'R p50':>7} "
          f"{'R p95':>7} {'R max':>7} {'R<2,5':>6} {'R>50':>5}")
    for arm in ("clean", "plume", "real"):
        values = np.array(arms[arm])
        if values.size == 0:
            print(f"{arm:>6} (rỗng)")
            continue
        print(f"{arm:>6} {values.size:8d} {values.min():7.2f} "
              f"{np.percentile(values, 1):7.2f} {np.percentile(values, 50):7.2f} "
              f"{np.percentile(values, 95):7.2f} {values.max():7.2f} "
              f"{int((values < 2.5).sum()):6d} {int((values > 50).sum()):5d}")

    print()
    print("Đọc: nếu nhánh plume có R min ≥ 2,5 và R max ≤ 50 ⇒ miền Cách A ĐÃ bật.")
    print("     Nếu có hộp R < 2,5 hoặc R > 50 ⇒ miền KHÔNG bật (production).")


if __name__ == "__main__":
    main()
