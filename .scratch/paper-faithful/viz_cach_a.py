#!/usr/bin/env python3
"""A6 — clip 3 panel REAL | PRODUCTION | CÁCH A (miền bật), có hàng nhìn ngang.

Đọc thẳng `spray/`, không cần file phụ. Config "Cách A" = ADR-0006 §5.7:
diffusion_alpha=0, 2.5 <= |pos| <= 50 m, wfh lấy mẫu theo scene.

Panel:
  hàng trên  : BEV x–y, ±60 m dọc / ±20 m ngang
  hàng dưới  : nhìn ngang x–z — chỗ DUY NHẤT thấy được cụm ở sau cảm biến
               và cụm dưới mặt đường

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. MPLCONFIGDIR=/tmp/mplc \
    /opt/anaconda3/bin/python .scratch/paper-faithful/viz_cach_a.py \
      --scene Crafter_dynamic/0060_2021-09-08-16-27-14_0 --frames 50 \
      --out .scratch/diag/viz_cachA_100kmh.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import RaycastConfig, raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

SPRAY, VEH = 2, 1
SEED = 20261119
CLASS_DIMS = {"crafter": (6.829, 2.419, 2.621), "golf": (4.250, 2.020, 1.501)}


def cach_a_config(base: PlumeStateConfig) -> PlumeStateConfig:
    return replace(base, diffusion_alpha=0.0, min_range_m=2.5, max_range_m=50.0)


def draw_bev(ax, bg, veh, spray, boxes, title, colour, xlim=(-10, 60)):
    ax.scatter(bg[:, 0], bg[:, 1], s=0.22, c="#9aa0a6", alpha=0.25, linewidths=0)
    if len(veh):
        ax.scatter(veh[:, 0], veh[:, 1], s=0.9, c="#1a73e8", alpha=0.85, linewidths=0)
    if len(spray):
        ax.scatter(spray[:, 0], spray[:, 1], s=1.8, c=colour, alpha=0.9, linewidths=0)
    for box in boxes[:2]:
        x, y, _, L, W, _, yaw = (float(v) for v in box[:7])
        pts = [(x + sx * L / 2 * np.cos(yaw) - sy * W / 2 * np.sin(yaw),
                y + sx * L / 2 * np.sin(yaw) + sy * W / 2 * np.cos(yaw))
               for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        pts.append(pts[0])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#f9ab00", lw=1.0)
    ax.axvline(0.0, color="#d93025", lw=0.6, ls=":", alpha=0.85)
    ax.set_xlim(*xlim); ax.set_ylim(-20, 20)
    ax.set_aspect("equal"); ax.set_facecolor("#111315")
    ax.tick_params(colors="#cccccc", labelsize=6)
    for s in ax.spines.values():
        s.set_color("#444")
    ax.set_title(title, color="#eeeeee", fontsize=8)


def draw_side(ax, bg, spray, title, colour, road_z):
    m = (bg[:, 2] > road_z - 2.5) & (bg[:, 2] < road_z + 6.0)
    ax.scatter(bg[m, 0], bg[m, 2] - road_z, s=0.22, c="#9aa0a6", alpha=0.22, linewidths=0)
    if len(spray):
        ax.scatter(spray[:, 0], spray[:, 2] - road_z, s=1.5, c=colour, alpha=0.9, linewidths=0)
    ax.axhline(0.0, color="#666", lw=0.6)
    ax.axvline(0.0, color="#d93025", lw=0.6, ls=":")
    ax.set_xlim(-10, 60); ax.set_ylim(-2.5, 6.0)
    ax.set_aspect("equal"); ax.set_facecolor("#111315")
    ax.tick_params(colors="#cccccc", labelsize=6)
    for s in ax.spines.values():
        s.set_color("#444")
    ax.set_title(title, color="#eeeeee", fontsize=8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO / "data" / "SemanticSprayDataset"))
    ap.add_argument("--scene", required=True)
    ap.add_argument("--frames", type=int, default=50)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--subsample", type=int, default=3)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--out", default=str(REPO / ".scratch/diag/viz_cachA.mp4"))
    ap.add_argument("--no-wfh-sampling", action="store_true")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root = Path(args.root)
    sc = root / args.scene
    meta = read_metadata(sc / "metadata.txt")
    obj_kmh = float(meta["object_velocity"])
    ego_kmh = float(meta.get("ego_velocity") or obj_kmh)
    obj_v, ego_v = obj_kmh / 3.6, ego_kmh / 3.6
    cls = "crafter" if "Crafter" in args.scene else "golf"

    scans = sorted(p.stem for p in (sc / "velodyne").glob("*.bin"))
    selected = scans[args.start:args.start + args.frames]
    wfh_a = 1.0 if args.no_wfh_sampling else sample_wfh_mm(args.scene, 0, 0)
    print(f"{args.scene}: {len(selected)} frame @ {obj_kmh:.0f} km/h, "
          f"Cách A wfh={wfh_a:.3f} mm", flush=True)

    table = load_beam_table()
    cfg = PlumeConfig()
    prod_state = PlumeState(PlumeStateConfig())
    a_state = PlumeState(cach_a_config(PlumeStateConfig()))
    tmp = Path(tempfile.mkdtemp(prefix="cachA-"))

    for pos, sid in enumerate(selected):
        pts = np.fromfile(sc / "velodyne" / f"{sid}.bin", dtype=np.float32).reshape(-1, 5)
        lab = np.fromfile(sc / "labels" / f"{sid}.label", dtype=np.uint32)
        if lab.size != pts.shape[0]:
            lab = np.zeros(pts.shape[0], dtype=np.uint32)
        bp = sc / "object_labels" / "lidar" / f"{sid}.json"
        if bp.is_file():
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(bp), obj_v)
            road_z = float(np.median(boxes[:, 2]))
        else:
            xyz = pts[lab == VEH][:, :3]
            if xyz.shape[0] < 10:
                continue
            L, W, H = CLASS_DIMS[cls]
            rear = float(np.percentile(xyz[:, 0], 2.0))
            boxes = np.array([[rear + L / 2, float(np.median(xyz[:, 1])),
                               float(np.percentile(xyz[:, 2], 2.0)), L, W, H, 0, 0, 0]],
                             dtype=np.float32)
            road_z = float(np.percentile(pts[:, 2], 5.0))

        clean = pts[lab != SPRAY].astype(np.float32)
        base = dict(scene_token=args.scene, frame_index=pos, epoch=0,
                    sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                    object_speed_mps=obj_v, road_z_m=road_z)
        ctx_prod = PlumeContext(wfh_mm=1.0, **base)
        ctx_a = PlumeContext(wfh_mm=wfh_a, **base)

        pr = inject_plume_stateful(clean, boxes, ctx_prod, prod_state, seed=SEED,
                                   token=f"ca/prod/{pos}", config=cfg, vehicle_class=cls)
        rp = raycast_frame(pr.points, prod_state.select_alive(), table=table,
                           road_z_m=road_z, rng=np.random.default_rng(SEED))
        ar = inject_plume_stateful(clean, boxes, ctx_a, a_state, seed=SEED,
                                   token=f"ca/a/{pos}", config=cfg, vehicle_class=cls)
        ra = raycast_frame(ar.points, a_state.select_alive(), table=table,
                           road_z_m=road_z, rng=np.random.default_rng(SEED),
                           config=RaycastConfig(max_distance_m=50.0))

        bg = clean[:, :3][::args.subsample]
        veh = clean[:, :3][lab[lab != SPRAY] == VEH]
        real = pts[lab == SPRAY][:, :3]
        dp = rp.detections[:, :3] if len(rp.detections) else np.zeros((0, 3))
        da = ra.detections[:, :3] if len(ra.detections) else np.zeros((0, 3))

        def rmed(d):
            return float(np.median(np.linalg.norm(d, axis=1))) if len(d) else float("nan")

        fig, axes = plt.subplots(2, 3, figsize=(16.5, 8.4), facecolor="#ffffff")
        draw_bev(axes[0, 0], bg, veh, real, boxes,
                 f"REAL — spray thật ({len(real)}) · R p50 {rmed(real):.1f} m", "#d93025")
        draw_bev(axes[0, 1], bg, veh, dp, boxes,
                 f"PRODUCTION ({len(dp)}) · R p50 {rmed(dp):.1f} m", "#d93025")
        draw_bev(axes[0, 2], bg, veh, da, boxes,
                 f"CÁCH A ({len(da)}) · R p50 {rmed(da):.1f} m", "#0f9d58")
        draw_side(axes[1, 0], bg, real, "REAL — nhìn ngang x–z", "#d93025", road_z)
        draw_side(axes[1, 1], bg, dp, "PRODUCTION — nhìn ngang", "#d93025", road_z)
        draw_side(axes[1, 2], bg, da, "CÁCH A — nhìn ngang", "#0f9d58", road_z)
        fig.text(0.5, 0.012,
                 f"{args.scene} · frame {pos + 1}/{len(selected)} · {obj_kmh:.0f} km/h · "
                 f"Cách A: alpha=0, 2,5–50 m, wfh={wfh_a:.2f} mm · "
                 f"đường chấm đỏ dọc = mặt phẳng cảm biến x=0",
                 ha="center", fontsize=8, color="#333")
        fig.savefig(tmp / f"f_{pos:04d}.png", dpi=100)
        plt.close(fig)
        if pos % 10 == 0 or pos == len(selected) - 1:
            print(f"  [{pos+1}/{len(selected)}] real {len(real):5d} · "
                  f"prod {len(dp):5d} · cachA {len(da):5d}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = shutil.which("ffmpeg")
    if ff is None:
        print(f"no ffmpeg; PNG o {tmp}")
        return
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(args.fps),
                    "-i", str(tmp / "f_%04d.png"),
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"xong: {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
