"""Kiểm 2 câu hỏi:
1. Bảng cal dùng 3 scene — variance giữa các scene lớn không? Có hợp lý không?
2. Fig 11 đo ở 50 m; bảng cal đo ở 20-30 m. Có phải đây là nguồn lệch?
3. 1766 det là 1 frame; so toàn bộ scene thì lệch bao nhiêu?
"""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_stats import cluster_angular

ROOT = Path("data/SemanticSprayDataset")


def load(split="train"):
    with open(f"data/sspp_infos_{split}.pkl", "rb") as fh:
        return pickle.load(fh)


def main():
    infos = load("train")
    by_scene = defaultdict(list)
    for info in infos:
        by_scene[info["token"].rsplit("/", 1)[0]].append(info)

    # ---------- 1. Variance giữa các scene ở cùng tốc độ ----------
    print("=" * 78)
    print("1. Cụm/frame THEO TỪNG SCENE (không gộp) — dao động lớn không?")
    print("   (bảng cal gộp 3 scene × 15 frame = 45 frame/ô)\n")

    by_speed = defaultdict(list)  # speed_bin -> list of (scene, n_clusters, n_points)
    for scene, frames in by_scene.items():
        for info in sorted(frames, key=lambda i: i["scan_id"]):
            boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(boxes) == 0:
                continue
            v = float(np.hypot(boxes[0, 7], boxes[0, 8])) * 3.6
            if v < 45:
                continue
            sb = int(round(v / 10.0) * 10)
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            real = pts[lab == 2][:, :3]
            if len(real) < 3:
                continue
            lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
            ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
            by_speed[sb].append((scene, len(counts), len(real)))

    print(" v  | n_scene | n_frame | cụm/frame: mean  p25  p50  p75 | CV   | min..max")
    for v in sorted(by_speed):
        rows = by_speed[v]
        scenes = sorted({r[0] for r in rows})
        c = np.array([r[1] for r in rows], dtype=float)
        cv = c.std() / c.mean() if c.mean() > 0 else 0
        print(f" {v:3d} | {len(scenes):7d} | {len(rows):7d} | "
              f"{c.mean():18.1f} {np.percentile(c,25):4.0f} {np.median(c):4.0f} "
              f"{np.percentile(c,75):4.0f} | {cv:4.2f} | {c.min():.0f}..{c.max():.0f}")

    # per-scene median
    print("\n  Theo từng scene (median cụm/frame của scene đó):")
    print("  v  | scene (rút gọn) | n_frame | cụm/frame median | điểm/frame median")
    for v in (60, 100, 120):
        if v not in by_speed:
            continue
        per = defaultdict(lambda: ([], []))
        for scene, nc, np_ in by_speed[v]:
            per[scene][0].append(nc)
            per[scene][1].append(np_)
        for scene in sorted(per):
            c, p = per[scene]
            print(f"  {v:3d} | {scene.split('/')[0][:7]}/{scene.split('/')[1][:4]} | "
                  f"{len(c):7d} | {np.median(c):16.1f} | {np.median(p):18.0f}")

    # ---------- 2. Cụm/frame theo cự ly box ----------
    print("\n" + "=" * 78)
    print("2. Cụm/frame theo CỰ LY box (Fig 11 đo @50 m, bảng cal @20-30 m)")
    print("   Nếu cự ly xa → cụm giảm thì bảng cal KHÔNG so được với Fig 11.\n")
    by_range = defaultdict(list)
    for scene, frames in by_scene.items():
        for info in sorted(frames, key=lambda i: i["scan_id"]):
            boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(boxes) == 0:
                continue
            v = float(np.hypot(boxes[0, 7], boxes[0, 8])) * 3.6
            if v < 45:
                continue
            dist = float(np.linalg.norm(boxes[0, :3]))
            rbin = int(round(dist / 10.0) * 10)
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            real = pts[lab == 2][:, :3]
            if len(real) < 3:
                continue
            lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
            ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
            by_range[rbin].append((v, len(counts), len(real)))

    print(" cự ly | n_frame | cụm/frame p50 | điểm/frame p50 | v p50")
    for r in sorted(by_range):
        rows = by_range[r]
        c = np.array([x[1] for x in rows], dtype=float)
        p = np.array([x[2] for x in rows], dtype=float)
        vv = np.array([x[0] for x in rows], dtype=float)
        print(f" {r:4d}m | {len(rows):7d} | {np.median(c):13.1f} | "
              f"{np.median(p):14.0f} | {np.median(vv):5.0f}")

    # ---------- 3. det/frame toàn scene vs 1 frame ----------
    print("\n" + "=" * 78)
    print("3. Điểm spray/frame: phân bố TOÀN BỘ frame của scene 0060 (100 km/h)")
    print("   (tôi đã so 1 frame = 1766; thực tế cả scene là bao nhiêu?)\n")
    for scene in ["Crafter_dynamic/0060_2021-09-08-16-27-14_0",
                  "Crafter_dynamic/0084_2021-09-08-17-31-03_0"]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        vals = []
        for info in frames:
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            vals.append(int((lab == 2).sum()))
        a = np.array(vals)
        print(f" {scene.split('/')[1][:4]} ({len(a)} frame): "
              f"p5={np.percentile(a,5):.0f} p25={np.percentile(a,25):.0f} "
              f"p50={np.median(a):.0f} p75={np.percentile(a,75):.0f} "
              f"p95={np.percentile(a,95):.0f} max={a.max()}")
        print(f"   frame 16 = {a[16]} | frame 24 = {a[24]} | frame 32 = {a[32]}")
        print(f"   → dùng p50={np.median(a):.0f} thay vì 1 frame thì mục tiêu "
              f"là {np.median(a):.0f}, không phải {a[16]}")


if __name__ == "__main__":
    main()
