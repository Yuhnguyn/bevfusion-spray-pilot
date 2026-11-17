"""Chẩn đoán 2: spray thật có nằm sau đuôi xe không, hay là nhiễu khắp scene?

Nếu phần lớn label==2 nằm gần ego (d < 10 m) chứ không phải sau box (x≈22 m),
thì phép so "thật vs sinh" hiện tại đang so hai thứ khác nhau.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

ROOT = Path("data/SemanticSprayDataset")


def load(split="train"):
    with open(f"data/sspp_infos_{split}.pkl", "rb") as fh:
        return pickle.load(fh)


def main():
    infos = load("train")
    by_scene = {}
    for info in infos:
        by_scene.setdefault(info["token"].rsplit("/", 1)[0], []).append(info)

    for scene in [
        "Crafter_dynamic/0012_2021-09-08-14-50-58_0",
        "Crafter_dynamic/0060_2021-09-08-16-27-14_0",
        "Crafter_dynamic/0084_2021-09-08-17-31-03_0",
    ]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        print(f"\n=== {scene} ===")
        for k in (8, 16, 24, 32):
            if k >= len(frames):
                continue
            info = frames[k]
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(
                ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
            )
            real = pts[lab == 2]
            boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(real) == 0 or len(boxes) == 0:
                continue
            bx = boxes[0]
            v = float(np.hypot(bx[7], bx[8])) * 3.6
            d = np.linalg.norm(real[:, :3], axis=1)
            # vùng sau đuôi xe: x trong [box_x - l - 12, box_x - l/2 + 2]
            x = real[:, 0]
            l = bx[4]
            tail_lo = bx[0] - l / 2 - 12.0
            tail_hi = bx[0] + l / 2 + 2.0
            in_tail = (x >= tail_lo) & (x <= tail_hi)
            near_ego = d < 10.0
            print(
                f" frame={k} v={v:.0f} n_real={len(real)} | "
                f"d_p50={np.median(d):.1f} | "
                f"in_tail(x∈[{tail_lo:.0f},{tail_hi:.0f}])={in_tail.sum()} "
                f"({in_tail.mean():.1%}) | "
                f"near_ego(d<10m)={near_ego.sum()} ({near_ego.mean():.1%})"
            )
            # của phần trong tail: z thế nào
            if in_tail.any():
                zt = real[in_tail, 2]
                road_z = float(np.median(boxes[:, 2] - boxes[:, 5] / 2.0))
                print(
                    f"   TAIL-ONLY: n={in_tail.sum()} "
                    f"z_abs_p50={np.median(zt):.2f} "
                    f"z_above_road_p50={np.median(zt)-road_z:.2f} "
                    f"z_above_road_p95={np.percentile(zt,95)-road_z:.2f} "
                    f"d_p50={np.median(d[in_tail]):.1f}"
                )
            if near_ego.any():
                zn = real[near_ego, 2]
                road_z = float(np.median(boxes[:, 2] - boxes[:, 5] / 2.0))
                print(
                    f"   NEAR-EGO : n={near_ego.sum()} "
                    f"z_abs_p50={np.median(zn):.2f} "
                    f"z_above_road_p50={np.median(zn)-road_z:.2f} "
                    f"x_p50={np.median(real[near_ego,0]):.1f} "
                    f"y_p50={np.median(real[near_ego,1]):.1f}"
                )


if __name__ == "__main__":
    main()
