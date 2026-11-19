"""Đo không gian solution: muốn khớp thật thì phải đổi cái gì, bao nhiêu?"""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_stats import cluster_angular

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)
    by_scene = defaultdict(list)
    for info in infos:
        by_scene[info["token"].rsplit("/", 1)[0]].append(info)

    print("=" * 74)
    print("A. Mảng nước thật: 1 cụm DBSCAN lớn nhất chiếm bao nhiêu?")
    print("   (nếu 1 cụm = 982 điểm / 1766 thì đó là MẢNG LIỀN, không phải cụm cầu)")
    for scene in ["Crafter_dynamic/0060_2021-09-08-16-27-14_0",
                  "Crafter_dynamic/0084_2021-09-08-17-31-03_0"]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        for k in (16, 24, 32):
            if k >= len(frames):
                continue
            info = frames[k]
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            real = pts[lab == 2][:, :3]
            if len(real) < 10:
                continue
            lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
            ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
            if len(counts) == 0:
                continue
            top = counts.max()
            sub = real[lbl == ids[np.argmax(counts)]]
            ext = sub.max(axis=0) - sub.min(axis=0)
            print(f" {scene.split('/')[1][:4]} f={k}: n={len(real)} cụm={len(counts)} | "
                  f"cụm lớn nhất {top} điểm = {top/len(real):.0%} tổng | "
                  f"extent={ext[0]:.1f}×{ext[1]:.1f}×{ext[2]:.1f} m")

    print("\n" + "=" * 74)
    print("B. Det/frame cần bao nhiêu để khớp thật? Và cần gì để đạt?")
    print("   det/cụm = (tia cắt cụm) × P_det(mean 0.172) × survival(mean 0.256)")
    print("   tia cắt ≈ (2·atan(r/d) / 0.333°) × (2·atan(r/d) / 0.197°)")
    print()
    print("   r (m) | d=15m: tia | det/cụm | 29 cụm → det/frame | 34 cụm → det/frame")
    for r in (0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0):
        d = 15.0
        ang = np.degrees(2 * np.arctan(r / d))
        n_beams = (ang / 0.333) * (ang / 0.197)
        per_cluster = n_beams * 0.172 * 0.256
        print(f"   {r:4.1f} | {n_beams:12.0f} | {per_cluster:7.1f} | "
              f"{per_cluster*29:19.0f} | {per_cluster*34:18.0f}")
    print("\n   THẬT @100 km/h: 1766–2791 det/frame, 34–85 cụm")
    print("   ⇒ cần det/cụm ≈ 1766/34 = 52 (nếu 34 cụm) hoặc 1766/85 = 21 (nếu 85 cụm)")

    print("\n" + "=" * 74)
    print("C. Nếu giữ r=0.3 (paper) thì cần bao nhiêu cụm?")
    d = 15.0
    r = 0.3
    ang = np.degrees(2 * np.arctan(r / d))
    n_beams = (ang / 0.333) * (ang / 0.197)
    per_cluster = n_beams * 0.172 * 0.256
    need = 1766 / per_cluster
    print(f"   det/cụm = {per_cluster:.1f} ⇒ cần {need:.0f} cụm sống để ra 1766 det")
    print(f"   bảng visible @100 = 29.2 ⇒ cần gấp {need/29.2:.0f}× số cụm")
    print(f"   Nhưng nếu tăng số cụm thì 'cụm/frame' không còn khớp bảng đo nữa.")

    print("\n" + "=" * 74)
    print("D. Mật độ: 29 cụm r=0.3 trong khối 3.3×3.4×2.4 m có chồng nhau không?")
    vol_block = 3.33 * 3.4 * 2.4
    vol_cluster = 4 / 3 * np.pi * 0.3**3
    print(f"   thể tích khối = {vol_block:.1f} m³, 1 cụm = {vol_cluster:.3f} m³")
    print(f"   29 cụm = {29*vol_cluster:.2f} m³ = {29*vol_cluster/vol_block:.1%} thể tích khối")
    print(f"   ⇒ các cụm RỜI NHAU, không nối thành mảng")
    print(f"   Muốn phủ kín khối cần {vol_block/vol_cluster:.0f} cụm r=0.3")


if __name__ == "__main__":
    main()
