"""Chẩn đoán 6: label==2 có phải spray bắn lên CHÍNH ego (bẩn cảm biến) không?

Nếu điểm spray gần ego phân bố ĐỀU mọi góc phương vị (kể cả phía trước, hai bên)
thì đó là nước bắn lên cảm biến, KHÔNG phải vệt sau xe dẫn đường.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)
    by_scene = {}
    for info in infos:
        by_scene.setdefault(info["token"].rsplit("/", 1)[0], []).append(info)

    for scene in [
        "Crafter_dynamic/0060_2021-09-08-16-27-14_0",
        "Crafter_dynamic/0084_2021-09-08-17-31-03_0",
    ]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        print(f"\n=== {scene} ===")
        for k in (16, 24, 32):
            if k >= len(frames):
                continue
            info = frames[k]
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(
                ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
            )
            real = pts[lab == 2][:, :3]
            if len(real) == 0:
                continue
            az = np.degrees(np.arctan2(real[:, 1], real[:, 0]))  # -180..180
            d = np.linalg.norm(real[:, :3], axis=1)
            # chia 8 hướng
            bins = np.histogram(az, bins=8, range=(-180, 180))[0]
            front = ((az > -45) & (az < 45)).mean()
            side = (((az >= 45) & (az < 135)) | ((az <= -45) & (az > -135))).mean()
            back = ((az >= 135) | (az <= -135)).mean()
            print(
                f" f={k} n={len(real)} d_p50={np.median(d):.1f} | "
                f"azimuth 8-bin={bins.tolist()}"
            )
            print(
                f"   front(±45°)={front:.1%} side={side:.1%} back={back:.1%} "
                f"| d<5m:{(d<5).mean():.1%} d<10m:{(d<10).mean():.1%}"
            )
            # ring index của điểm spray — nếu ring 0 hoặc ring cao nhất → sát cảm biến
            ring = pts[lab == 2][:, 4]
            print(
                f"   ring: min={ring.min():.0f} p50={np.median(ring):.0f} "
                f"max={ring.max():.0f} | n_unique={len(np.unique(ring))}"
            )


if __name__ == "__main__":
    main()
