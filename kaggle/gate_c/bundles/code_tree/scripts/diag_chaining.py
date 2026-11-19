"""Thí nghiệm quyết định: bảng "29 cụm/frame" là 29 quả cầu RỜI hay 29 MẢNG dính?

Sinh N quả cầu r=0.3 trong khối đuôi, chạy đúng DBSCAN của bảng (0.7°/minPts 3),
xem ra bao nhiêu cụm và phân bố kích thước.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_stats import cluster_angular

RNG = np.random.default_rng(0)
R = 0.30
BLOCK = np.array([3.33, 3.40, 2.41])  # dài, rộng, cao (khối đuôi Crafter)
CENTER = np.array([18.0, 0.0, 0.6])   # sau đuôi box x=22, l=6.83


def spawn(n_clusters, points_per_cluster=14):
    pts = []
    for _ in range(n_clusters):
        c = CENTER + RNG.uniform(-0.5, 0.5, 3) * BLOCK
        # điểm trong quả cầu r
        v = RNG.normal(size=(points_per_cluster, 3))
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        v *= R * RNG.random((points_per_cluster, 1)) ** (1 / 3)
        pts.append(c + v)
    return np.concatenate(pts)


print("=" * 76)
print("Sinh N quả cầu r=0.30, 14 điểm/cụm trong khối 3.33×3.40×2.41 m")
print("→ chạy DBSCAN 0.7°/minPts 3 (đúng như bảng cal) → đếm cụm")
print()
print(" N gốc | điểm | cụm DBSCAN | lớn nhất | %tổng | p95 | max/median")
for n in (10, 29, 50, 100, 240, 500):
    cloud = spawn(n)
    lbl = cluster_angular(cloud, eps_deg=0.7, min_pts=3)
    ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
    if len(counts) == 0:
        print(f" {n:5d} | {len(cloud):5d} | 0 cụm")
        continue
    top = counts.max()
    med = np.median(counts)
    print(f" {n:5d} | {len(cloud):5d} | {len(counts):10d} | {top:8d} | "
          f"{top/len(cloud):4.0%} | {np.percentile(counts,95):3.0f} | {top/med:.0f}×")

print()
print("=" * 76)
print("SO SÁNH với THẬT @100 km/h (scene 0060):")
print("  n=1766–2791 điểm | 34–85 cụm | lớn nhất 641–1238 (21–56%) | max/median 100–250×")
print()
print("KẾT LUẬN cần đọc:")
print("  Nếu N=29 cho ra 29 cụm rời, max/median ~1× → generator sinh 29 QUẢ CẦU,")
print("  còn THẬT là 29 MẢNG (max/median 100–250×). Cùng 'số cụm' nhưng khác bản chất.")
print("  Muốn ra mảng: N phải lớn tới mức các quả cầu CHẠM nhau để DBSCAN nối.")
print()
# tìm N tối thiểu để bắt đầu dính
print("Tìm ngưỡng dính:")
for n in (240, 400, 600, 900, 1200):
    cloud = spawn(n)
    lbl = cluster_angular(cloud, eps_deg=0.7, min_pts=3)
    ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
    if len(counts) == 0:
        continue
    print(f"  N={n:4d} ({len(cloud):5d} điểm): {len(counts):3d} cụm, "
          f"lớn nhất {counts.max():4d} ({counts.max()/len(cloud):4.0%}), "
          f"max/median={counts.max()/np.median(counts):.0f}×")
