"""Chẩn đoán 3: kích thước cụm thật vs sinh, và giả thuyết spray của chính ego.

Đo: (a) extent không gian của cụm thật lớn nhất, (b) nếu sinh khối sau ego thì
phân bố cự ly có khớp không.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_stats import cluster_angular

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)
    by_scene = {}
    for info in infos:
        by_scene.setdefault(info["token"].rsplit("/", 1)[0], []).append(info)

    print("=== Kích thước cụm THẬT (label==2) ===")
    for scene in [
        "Crafter_dynamic/0012_2021-09-08-14-50-58_0",
        "Crafter_dynamic/0060_2021-09-08-16-27-14_0",
        "Crafter_dynamic/0084_2021-09-08-17-31-03_0",
    ]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        for k in (16, 24, 32):
            if k >= len(frames):
                continue
            info = frames[k]
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(
                ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
            )
            real = pts[lab == 2][:, :3]
            if len(real) < 10:
                continue
            lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
            ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
            if len(counts) == 0:
                continue
            order = np.argsort(counts)[::-1]
            print(f"\n {scene.split('/')[0]}/{scene.split('/')[1][:4]} f={k} "
                  f"n={len(real)} clusters={len(counts)}")
            for rank in range(min(3, len(order))):
                cid = ids[order[rank]]
                sub = real[lbl == cid]
                ext = sub.max(axis=0) - sub.min(axis=0)
                d = np.linalg.norm(sub, axis=1)
                print(
                    f"   cluster#{rank+1} n={counts[order[rank]]} "
                    f"extent(x,y,z)=({ext[0]:.1f},{ext[1]:.1f},{ext[2]:.1f}) "
                    f"d_p50={np.median(d):.1f} "
                    f"x_p50={np.median(sub[:,0]):.1f} y_p50={np.median(sub[:,1]):.1f}"
                )

    print("\n=== Nếu sinh khối SAU EGO (giả thuyết ego spray) ===")
    print("Khối dài |v|*dt = 33.3*0.1 = 3.33 m mỗi frame, cộng dồn qua 4T/Δt frame.")
    v = 120 / 3.6
    dt = 0.1
    T = 1.8  # 120 km/h, wfh 1 mm
    n_alive = int(4 * T / dt)
    print(f"  v=120 km/h: T={T}s, cụm sống tối đa {n_alive} frame")
    print(f"  khối mỗi frame dài {v*dt:.2f} m → vệt tối đa {v*dt*n_alive:.1f} m")
    print(f"  THẬT: spray ego trải x từ {np.median([-6.6,-5.4,-3.1]):.1f} m (p50) "
          f"tới ~ -12 m (đuôi vệt)")


if __name__ == "__main__":
    main()
