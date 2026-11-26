#!/usr/bin/env python3
"""2 panel: CODE CU vs CODE MOI, cung scene cung frame, tren nen spray THAT.

Panel giua ban truoc (Cach A cu) bi bo: da chung minh bit-identical voi code moi
(2212 == 2212 diem), nen ve 2 lan la lap.
"""
from __future__ import annotations

import argparse

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PANELS = [
    ("old", "CODE CU  (truoc A9)", "#e8453c",
     "tan xa alpha=0,06  ·  mien vo han  ·  wfh=1,0 co dinh"),
    ("new", "CODE MOI  (sau A9 = mac dinh)", "#1e8e3e",
     "khong tan xa  ·  2,5-50 m  ·  wfh mau theo scene"),
]


def draw_bev(ax, d, title, colour, sub, xlim=(0, 60), ylim=(-14, 14)):
    bg, veh, real, gen = d["clean_bg"], d["veh"], d["real"], d["gen"]
    ax.scatter(bg[:, 0], bg[:, 1], s=0.25, c="#b6bcc2", alpha=0.28, linewidths=0)
    if len(real):
        ax.scatter(real[:, 0], real[:, 1], s=5.0, c="#202124", alpha=0.62,
                   linewidths=0, marker="o")
    if len(veh):
        ax.scatter(veh[:, 0], veh[:, 1], s=1.8, c="#1a73e8", alpha=0.95, linewidths=0)
    if len(gen):
        ax.scatter(gen[:, 0], gen[:, 1], s=5.5, c=colour, alpha=0.95,
                   linewidths=0, marker="o")

    for box in d["boxes"][:1]:
        x, y, _, L, W, _, yaw = (float(v) for v in box[:7])
        pts = [(x + sx * L / 2 * np.cos(yaw) - sy * W / 2 * np.sin(yaw),
                y + sx * L / 2 * np.sin(yaw) + sy * W / 2 * np.cos(yaw))
               for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        pts.append(pts[0])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#f9ab00", lw=1.5)

    ax.axvline(0.0, color="#d93025", lw=0.7, ls=":", alpha=0.9)
    for r in (10, 20, 30, 40, 50):
        ax.plot([r, r], [-0.4, 0.4], color="#9aa0a6", lw=0.8)
        ax.text(r, 1.2, f"{r}m", color="#9aa0a6", fontsize=6.5, ha="center")
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    ax.set_facecolor("#fbfcfd")
    ax.tick_params(colors="#3c4043", labelsize=7)
    for s in ax.spines.values():
        s.set_color("#dadce0")
    ax.set_title(title, color="#202124", fontsize=11, pad=8, loc="left")
    ax.text(0.985, 0.03, sub, transform=ax.transAxes, color="#3c4043",
            fontsize=7.5, va="bottom", ha="right",
            bbox=dict(boxstyle="round,pad=0.32", fc="#f1f3f4", ec="#dadce0", lw=0.7))


def draw_side(ax, d, colour, road_z, xlim=(0, 60), ylim=(-1.0, 3.2)):
    bg = d["clean_bg"]
    m = (bg[:, 2] > road_z - 1.5) & (bg[:, 2] < road_z + 4.5)
    ax.scatter(bg[m, 0], bg[m, 2] - road_z, s=0.25, c="#b6bcc2", alpha=0.20, linewidths=0)
    for key, c, s, a in (("real", "#202124", 3.4, 0.55), ("gen", colour, 3.8, 0.95)):
        p = d[key]
        if len(p):
            ax.scatter(p[:, 0], p[:, 2] - road_z, s=s, c=c, alpha=a, linewidths=0)
    ax.axhline(0.0, color="#80868b", lw=0.8)
    ax.text(1.0, 0.10, "mat duong", color="#80868b", fontsize=6.5)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    ax.set_facecolor("#fbfcfd")
    ax.tick_params(colors="#3c4043", labelsize=7)
    for s in ax.spines.values():
        s.set_color("#dadce0")


def load(path: str, idx: int) -> dict:
    z = np.load(path, allow_pickle=True)
    d = {k: z[k][idx] for k in ("real", "gen", "clean_bg", "veh", "boxes", "radius", "range")}
    d.update(obj_kmh=float(z["obj_kmh"]), wfh=float(z["wfh_mm"]), road_z=float(z["road_z"]))
    d["n_alive"] = len(d["radius"])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--frame", type=int, default=-1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    z = np.load(args.new, allow_pickle=True)
    counts = np.array([len(x) for x in z["gen"]])
    frame = args.frame if args.frame >= 0 else int(np.argmin(np.abs(counts - np.median(counts))))

    data = {"old": load(args.old, frame), "new": load(args.new, frame)}
    d0 = data["new"]

    fig = plt.figure(figsize=(15.0, 7.4), facecolor="#ffffff")
    gs = fig.add_gridspec(2, 2, height_ratios=[2.9, 1.05], hspace=0.13, wspace=0.06)

    for col, (key, title, colour, sub) in enumerate(PANELS):
        d = data[key]
        ax = fig.add_subplot(gs[0, col])
        draw_bev(ax, d, f"{title}      gen {len(d['gen'])} / real {len(d['real'])}", colour, sub)
        if col == 0:
            ax.set_ylabel("y (m)", color="#3c4043", fontsize=8)
        ax = fig.add_subplot(gs[1, col])
        draw_side(ax, d, colour, d["road_z"])
        ax.set_xlabel("x (m) — nhin ngang", color="#3c4043", fontsize=8)

    fig.suptitle(
        f"SemanticSpray / RoadSpray — Crafter {d0['obj_kmh']:.0f} km/h · frame {frame} "
        f"(gan trung vi) · cung seed · cung scene",
        fontsize=12.5, color="#202124", y=0.985)
    fig.text(0.5, 0.018,
             "cham den = spray THAT (nhan tay)   ·   cham mau = spray do generator sinh   ·   "
             "xanh duong = xe   ·   chi so dau panel = so diem trong frame nay",
             ha="center", fontsize=8.8, color="#5f6368")
    fig.savefig(args.out, dpi=115, bbox_inches="tight", facecolor="#ffffff")
    print(f"wrote {args.out}  (frame {frame})")

    print("\npanel                  gen/frame  real/frame  alive  r_p50  r_p99  %det<=20m")
    for key, _, _, _ in PANELS:
        d = data[key]
        r = d["radius"] if d["n_alive"] else np.array([np.nan])
        allg = np.vstack([x for x in z["gen"] if len(x)]) if counts.max() else np.zeros((0, 3))
        print(f"{key:<18} {len(d['gen']):9d} {len(d['real']):11d} {d['n_alive']:6d} "
              f"{np.percentile(r, 50):6.2f} {np.percentile(r, 99):6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
