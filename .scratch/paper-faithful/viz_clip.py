#!/usr/bin/env python3
"""Render clip MP4: generator hien tai, 1 scene, moi frame 1 hinh.

Nen = spray THAT (nhan tay). Cham mau = spray generator sinh.
Ca hai cung khung nhin nen nhin thay ngay generator dat o dau so voi that.

Chay:
  MPLCONFIGDIR=/tmp/mplc PYTHONPATH=. /opt/anaconda3/bin/python \
    .scratch/paper-faithful/viz_clip.py --npz /tmp/clip_new.npz \
    --out ~/.hermes/drafts/spray-pilot/viz/clip_new.mp4
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COLOUR = "#1e8e3e"
XMAX = 55.0
YMAX = 14.0


def draw_bev(ax, real, gen, bg, veh, boxes):
    ax.scatter(bg[:, 0], bg[:, 1], s=0.25, c="#c2c8ce", alpha=0.30, linewidths=0)
    if len(real):
        ax.scatter(real[:, 0], real[:, 1], s=6.0, c="#202124", alpha=0.55,
                   linewidths=0, marker="o")
    if len(veh):
        ax.scatter(veh[:, 0], veh[:, 1], s=2.0, c="#1a73e8", alpha=0.95, linewidths=0)
    if len(gen):
        ax.scatter(gen[:, 0], gen[:, 1], s=7.0, c=COLOUR, alpha=0.95,
                   linewidths=0, marker="o")
    for box in boxes[:1]:
        x, y, _, L, W, _, yaw = (float(v) for v in box[:7])
        pts = [(x + sx * L / 2 * np.cos(yaw) - sy * W / 2 * np.sin(yaw),
                y + sx * L / 2 * np.sin(yaw) + sy * W / 2 * np.cos(yaw))
               for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        pts.append(pts[0])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#f9ab00", lw=1.6)
    ax.axvline(0.0, color="#d93025", lw=0.7, ls=":", alpha=0.9)
    for r in (10, 20, 30, 40, 50):
        ax.plot([r, r], [-0.35, 0.35], color="#9aa0a6", lw=0.8)
        ax.text(r, 0.9, f"{r}", color="#8a9096", fontsize=6, ha="center")
    ax.set_xlim(0, XMAX)
    ax.set_ylim(-YMAX, YMAX)
    ax.set_aspect("equal")
    ax.set_facecolor("#fbfcfd")
    ax.tick_params(colors="#3c4043", labelsize=7)
    for s in ax.spines.values():
        s.set_color("#dadce0")


def draw_side(ax, real, gen, bg, road_z):
    m = (bg[:, 2] > road_z - 1.5) & (bg[:, 2] < road_z + 4.5)
    ax.scatter(bg[m, 0], bg[m, 2] - road_z, s=0.25, c="#c2c8ce", alpha=0.22, linewidths=0)
    for p, c, s, a in ((real, "#202124", 3.6, 0.5), (gen, COLOUR, 4.2, 0.95)):
        if len(p):
            ax.scatter(p[:, 0], p[:, 2] - road_z, s=s, c=c, alpha=a, linewidths=0)
    ax.axhline(0.0, color="#80868b", lw=0.8)
    ax.set_xlim(0, XMAX)
    ax.set_ylim(-1.0, 3.0)
    ax.set_aspect("equal")
    ax.set_facecolor("#fbfcfd")
    ax.tick_params(colors="#3c4043", labelsize=7)
    for s in ax.spines.values():
        s.set_color("#dadce0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--keep-png", action="store_true")
    args = ap.parse_args()

    z = np.load(args.npz, allow_pickle=True)
    real_all, gen_all = z["real"], z["gen"]
    bg_all, veh_all, boxes_all = z["clean_bg"], z["veh"], z["boxes"]
    fr_all, alive_all = z["frame"], z["n_alive"]
    obj_kmh, wfh, road_z = float(z["obj_kmh"]), float(z["wfh_mm"]), float(z["road_z"])
    scene = str(z["scene"])
    n = len(fr_all)

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / f".frames_{out.stem}"
    tmp.mkdir(exist_ok=True)
    for old in tmp.glob("*.png"):
        old.unlink()

    counts = np.array([len(g) for g in gen_all])
    for i in range(n):
        fig = plt.figure(figsize=(9.6, 7.4), facecolor="#ffffff")
        gs = fig.add_gridspec(2, 1, height_ratios=[2.85, 1.0], hspace=0.13)
        ax = fig.add_subplot(gs[0])
        draw_bev(ax, real_all[i], gen_all[i], bg_all[i], veh_all[i], boxes_all[i])
        ax.set_title(f"generator hien tai · {obj_kmh:.0f} km/h · wfh {wfh:.2f} mm",
                     fontsize=11, color="#202124", loc="left", pad=7)
        ax.set_ylabel("y (m)", color="#3c4043", fontsize=8)
        ax = fig.add_subplot(gs[1])
        draw_side(ax, real_all[i], gen_all[i], bg_all[i], road_z)
        ax.set_xlabel("x (m) — nhin ngang", color="#3c4043", fontsize=8)

        fig.text(0.5, 0.945,
                 f"frame {int(fr_all[i]) + 1}/{n}   ·   generator {len(gen_all[i]):3d} diem   "
                 f"·   spray that {len(real_all[i]):3d}   ·   cum song {int(alive_all[i]):2d}",
                 ha="center", fontsize=10.5, color="#202124")
        fig.text(0.5, 0.016,
                 "cham den = spray that (nhan tay)   ·   cham xanh = spray generator sinh",
                 ha="center", fontsize=8.5, color="#5f6368")
        fig.savefig(tmp / f"f_{i:04d}.png", dpi=100, facecolor="#ffffff", bbox_inches="tight")
        plt.close(fig)
        if i % 20 == 0 or i == n - 1:
            print(f"  [{i+1}/{n}] gen {len(gen_all[i]):4d} real {len(real_all[i]):4d}", flush=True)

    print(f"gen/frame: mean {counts.mean():.1f}  min {counts.min()}  max {counts.max()}")
    ff = shutil.which("ffmpeg")
    if ff is None:
        print(f"khong co ffmpeg; PNG o {tmp}")
        return 1
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(args.fps),
                    "-i", str(tmp / "f_%04d.png"),
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)],
                   check=True)
    if not args.keep_png:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"xong: {out} ({out.stat().st_size/1e6:.1f} MB, {n} frame @ {args.fps} fps = {n/args.fps:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
