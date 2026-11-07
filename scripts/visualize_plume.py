#!/usr/bin/env python3
"""Render BEV stills of the spray plume generator and of real SemanticSpray.

Outputs (``docs/figs/plume``):

* ``bev-plume.png``       one synthetic frame, box fixed at (22 m, 0), 72 km/h;
* ``real-vs-synth.png``   real SemanticSpray frame (selected by criterion) vs
                          the synthetic frame above, identical axes/colors;
* ``grid-12-22-38.png``   3 box ranges x 2 seeds, plume points only.

The script only imports numpy/matplotlib/pillow (no mmcv). Run it with the
isolated viz env::

    ~/.venvs/viz/bin/python scripts/visualize_plume.py

Nothing here changes plume parameters; the generator is used as-is.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import spray.plume as plume  # noqa: E402
from spray.plume import PlumeConfig, cluster_count_for_speed, inject_plume  # noqa: E402
from spray.spray_stats import NOISE_LABEL, load_scan  # noqa: E402
from scripts.semantic_spray_stats import (  # noqa: E402
    scan_cluster_records,
    scene_dirs,
)

FIG_DIR = os.path.join(REPO, "docs", "figs", "plume")

# Same colours/markers everywhere so the real-vs-synth panels are comparable.
CLEAN_COLOR = "#c3c7cc"
PLUME_COLOR = "#b3001b"
BOX_COLOR = "#1f5fbf"
EGO_COLOR = "#202124"
CLEAN_SIZE = 1.0
PLUME_SIZE = 18.0

BOX_LENGTH_M = 4.5
BOX_WIDTH_M = 1.9
BOX_HEIGHT_M = 1.5
BOX_Z_M = 0.9


def make_box(x: float, y: float, speed_kmh: float) -> np.ndarray:
    """mmdet3d-style box (x, y, z, dx, dy, dz, yaw, vx, vy)."""
    vx = speed_kmh / 3.6
    return np.array(
        [[x, y, BOX_Z_M, BOX_LENGTH_M, BOX_WIDTH_M, BOX_HEIGHT_M, 0.0, vx, 0.0]],
        dtype=np.float32,
    )


def synthetic_clean(n: int = 4000, seed: int = 12345) -> np.ndarray:
    """Deterministic sparse ground cloud used only as visual reference."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-10.0, 45.0, n)
    y = rng.uniform(-15.0, 15.0, n)
    return np.column_stack(
        [x, y, np.zeros(n), np.zeros(n), np.zeros(n)]
    ).astype(np.float32)


def spawn_counts(points, boxes, seed: int, token: str = "") -> tuple:
    """Run the generator while recording the point count drawn per cluster.

    This wraps the module's own ``_count_for_distance`` so the per-cluster size
    reflects exactly what the generator drew; the file is not modified and the
    RNG stream is untouched.
    """
    counts: list[int] = []
    original = plume._count_for_distance

    def wrapped(rng, distance, config):
        count = original(rng, distance, config)
        counts.append(int(count))
        return count

    plume._count_for_distance = wrapped
    try:
        result = inject_plume(points, boxes, seed=seed, token=token)
    finally:
        plume._count_for_distance = original
    return result, counts


def plume_ratio_median(injected: np.ndarray) -> float:
    """Median ``r_range / r_extent`` using the ticket-16 single-linkage parser."""
    if len(injected) == 0:
        return float("nan")
    labels = np.full(len(injected), NOISE_LABEL, dtype=np.int32)
    records = scan_cluster_records(injected, labels, radius=0.5)
    ratios = [
        record.r_range_m / record.r_extent_m
        for record in records
        if record.r_extent_m > 0.0
    ]
    return float(np.median(ratios)) if ratios else float("nan")


def draw_ego(ax) -> None:
    ax.add_patch(
        Polygon(
            [(2.4, 0.0), (-2.4, 1.0), (-2.4, -1.0)],
            closed=True,
            facecolor=EGO_COLOR,
            edgecolor=EGO_COLOR,
            zorder=5,
        )
    )
    ax.text(0.0, -2.2, "ego", ha="center", va="top", fontsize=9, color=EGO_COLOR)


def draw_box(ax, box: np.ndarray) -> None:
    x, y = float(box[0, 0]), float(box[0, 1])
    ax.add_patch(
        Rectangle(
            (x - BOX_LENGTH_M / 2.0, y - BOX_WIDTH_M / 2.0),
            BOX_LENGTH_M,
            BOX_WIDTH_M,
            facecolor="none",
            edgecolor=BOX_COLOR,
            linewidth=2.0,
            zorder=6,
        )
    )
    speed_kmh = float(np.hypot(box[0, 7], box[0, 8])) * 3.6
    ax.text(
        x,
        y + BOX_WIDTH_M / 2.0 + 0.8,
        f"box {speed_kmh:.0f} km/h",
        ha="center",
        va="bottom",
        fontsize=9,
        color=BOX_COLOR,
    )


def draw_direction_arrow(ax, box: np.ndarray, length: float = 6.0) -> None:
    vx, vy = float(box[0, 7]), float(box[0, 8])
    norm = float(np.hypot(vx, vy))
    ux, uy = -vx / norm, -vy / norm
    x, y = float(box[0, 0]), float(box[0, 1])
    ax.annotate(
        "",
        xy=(x + ux * length, y + uy * length),
        xytext=(x, y),
        arrowprops=dict(arrowstyle="-|>", color=BOX_COLOR, lw=2.2),
        zorder=7,
    )
    ax.text(
        x + ux * length,
        y + uy * length - 0.9,
        r"$-v/|v|$",
        ha="center",
        va="top",
        fontsize=9,
        color=BOX_COLOR,
    )


def _style_axes(ax) -> None:
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, color="#e6e8eb", linewidth=0.6)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_facecolor("#fbfbfc")


def render_image1(out_dir: str) -> dict:
    clean = synthetic_clean()
    box = make_box(22.0, 0.0, 72.0)
    result, counts = spawn_counts(clean, box, seed=0)
    ratio = plume_ratio_median(result.injected)

    fig, ax = plt.subplots(figsize=(11, 6.2))
    _style_axes(ax)
    ax.scatter(
        result.points_clean[:, 0],
        result.points_clean[:, 1],
        s=CLEAN_SIZE,
        c=CLEAN_COLOR,
        linewidths=0,
        label="points_clean",
        zorder=1,
    )
    ax.scatter(
        result.injected[:, 0],
        result.injected[:, 1],
        s=PLUME_SIZE,
        c=PLUME_COLOR,
        linewidths=0,
        label="plume points",
        zorder=4,
    )
    draw_box(ax, box)
    draw_ego(ax)
    draw_direction_arrow(ax, box)

    ax.set_xlim(-10.0, 45.0)
    ax.set_ylim(-15.0, 15.0)
    ax.set_title(
        "Synthetic spray plume, one frame (frame-independent generator)", fontsize=12
    )
    ax.text(
        0.01,
        0.99,
        "\n".join(
            [
                f"plume points: {result.stats.injected}",
                f"clusters: {result.stats.clusters}",
                f"median r_range/r_extent: {ratio:.3f}",
                f"seed: 0, box x=22 m, v=72 km/h",
            ]
        ),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#d0d4d9"),
    )
    handles = [
        Line2D([], [], marker="o", linestyle="", color=CLEAN_COLOR, markersize=4, label="points_clean"),
        Line2D([], [], marker="o", linestyle="", color=PLUME_COLOR, markersize=8, label="plume points"),
        Line2D([], [], color=BOX_COLOR, lw=2, label="vehicle box"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.9)
    path = os.path.join(out_dir, "bev-plume.png")
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)

    stats = {
        "points": int(result.stats.injected),
        "clusters": int(result.stats.clusters),
        "spawned_counts": [int(c) for c in counts],
        "ratio_median": ratio,
    }
    print(f"image1: {path}  {stats}")
    return stats


def read_object_velocity(scene_dir: str) -> float:
    lines = (
        open(os.path.join(scene_dir, "metadata.txt"), encoding="utf-8")
        .read()
        .strip()
        .splitlines()
    )
    header = lines[0].split(",")
    row = lines[1].split(",")
    return float(dict(zip(header, row))["object_velocity"])


def select_real_frame(root: str) -> dict:
    """First frame with object_velocity > 50 km/h and >= 50 spray points.

    Falls back to >= 30 spray points only if no frame reaches 50; the chosen
    threshold is returned so the report/HTML can state it.
    """
    for threshold in (50, 30):
        for scene in scene_dirs(root):
            velocity = read_object_velocity(scene)
            if velocity <= 50.0:
                continue
            label_dir = os.path.join(scene, "labels")
            for name in sorted(os.listdir(label_dir)):
                if not name.endswith(".label"):
                    continue
                scan_id = name[: -len(".label")]
                labels = np.fromfile(
                    os.path.join(label_dir, name), dtype=np.int32
                )
                spray = int(np.count_nonzero(labels == NOISE_LABEL))
                if spray >= threshold:
                    return {
                        "scene": scene,
                        "scan_id": scan_id,
                        "velocity_kmh": velocity,
                        "spray_points": spray,
                        "threshold": threshold,
                    }
    raise SystemExit("no real frame with >50 km/h and enough spray points found")


def render_image2(out_dir: str, synthetic: dict) -> dict:
    selection = select_real_frame(os.path.join(REPO, "data", "SemanticSprayDataset"))
    points, labels = load_scan(selection["scene"], selection["scan_id"])
    records = scan_cluster_records(points, labels, radius=0.5)
    dense = [r for r in records if r.point_count >= 5]
    spray_mask = labels == NOISE_LABEL

    clean = synthetic_clean()
    box = make_box(22.0, 0.0, 72.0)
    result, _ = spawn_counts(clean, box, seed=0)

    fig, axes = plt.subplots(2, 1, figsize=(11, 10.4))
    for ax in axes:
        _style_axes(ax)
        ax.set_xlim(-10.0, 45.0)
        ax.set_ylim(-15.0, 15.0)

    ax = axes[0]
    ax.scatter(
        points[~spray_mask, 0],
        points[~spray_mask, 1],
        s=CLEAN_SIZE,
        c=CLEAN_COLOR,
        linewidths=0,
        zorder=1,
    )
    ax.scatter(
        points[spray_mask, 0],
        points[spray_mask, 1],
        s=PLUME_SIZE,
        c=PLUME_COLOR,
        linewidths=0,
        zorder=4,
    )
    scene_name = os.path.basename(selection["scene"])
    ax.set_title(
        "real SemanticSpray — "
        f"{os.path.basename(os.path.dirname(selection['scene']))}/{scene_name} "
        f"frame {selection['scan_id']}",
        fontsize=11,
    )
    ax.text(
        0.01,
        0.99,
        "\n".join(
            [
                f"object velocity: {selection['velocity_kmh']:.0f} km/h",
                f"spray points: {selection['spray_points']}",
                f"single-linkage clusters: {len(records)} (dense >= 5: {len(dense)})",
                f"selection threshold: >= {selection['threshold']} spray points",
            ]
        ),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#d0d4d9"),
    )

    ax = axes[1]
    ax.scatter(
        result.points_clean[:, 0],
        result.points_clean[:, 1],
        s=CLEAN_SIZE,
        c=CLEAN_COLOR,
        linewidths=0,
        zorder=1,
    )
    ax.scatter(
        result.injected[:, 0],
        result.injected[:, 1],
        s=PLUME_SIZE,
        c=PLUME_COLOR,
        linewidths=0,
        zorder=4,
    )
    draw_box(ax, box)
    draw_ego(ax)
    draw_direction_arrow(ax, box)
    ax.set_title("synthetic — box x=22 m, 72 km/h, seed=0", fontsize=11)
    ax.text(
        0.01,
        0.99,
        "\n".join(
            [
                f"plume points: {synthetic['points']}",
                f"clusters: {synthetic['clusters']}",
                f"median r_range/r_extent: {synthetic['ratio_median']:.3f}",
            ]
        ),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#d0d4d9"),
    )

    fig.suptitle(
        "Real spray vs synthetic plume (same axes, colours, marker size)",
        fontsize=12,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    path = os.path.join(out_dir, "real-vs-synth.png")
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)

    info = {
        "scene": os.path.relpath(selection["scene"], REPO),
        "scan_id": selection["scan_id"],
        "velocity_kmh": selection["velocity_kmh"],
        "spray_points": selection["spray_points"],
        "single_linkage_clusters": len(records),
        "dense_clusters": len(dense),
        "threshold": selection["threshold"],
    }
    print(f"image2: {path}  {info}")
    return info


def render_image3(out_dir: str) -> list[dict]:
    ranges = (12.0, 22.0, 38.0)
    seeds = (0, 1)
    grid_speed_kmh = 130.0
    clean = synthetic_clean()

    panels: list[dict] = []
    fig, axes = plt.subplots(3, 2, figsize=(12, 13.5), sharex=True, sharey=True)
    for row, x in enumerate(ranges):
        for col, seed in enumerate(seeds):
            box = make_box(x, 0.0, grid_speed_kmh)
            result, counts = spawn_counts(clean, box, seed=seed)
            record = {
                "x_m": x,
                "seed": seed,
                "speed_kmh": grid_speed_kmh,
                "points": int(result.stats.injected),
                "clusters": int(result.stats.clusters),
                "median_points_per_cluster": float(np.median(counts)) if counts else float("nan"),
                "drawn_counts": [int(c) for c in counts],
            }
            panels.append(record)

            ax = axes[row, col]
            _style_axes(ax)
            ax.set_xlim(-8.0, 48.0)
            ax.set_ylim(-12.0, 12.0)
            ax.scatter(
                result.injected[:, 0],
                result.injected[:, 1],
                s=PLUME_SIZE,
                c=PLUME_COLOR,
                linewidths=0,
                zorder=2,
            )
            draw_box(ax, box)
            ax.set_title(
                f"x={x:.0f} m, seed={seed}", fontsize=11, color="#202124"
            )
            ax.text(
                0.01,
                0.99,
                "\n".join(
                    [
                        f"n_points: {record['points']}",
                        f"n_clusters: {record['clusters']}",
                        f"median points/cluster: "
                        f"{record['median_points_per_cluster']:.1f}",
                    ]
                ),
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#d0d4d9"),
            )
            if row == 2:
                ax.set_xlabel("x [m]")
            if col == 0:
                ax.set_ylabel("y [m]")

    fig.suptitle(
        "Plume only — density vs box range "
        f"({grid_speed_kmh:.0f} km/h, identical axes)",
        fontsize=13,
        y=0.995,
    )
    fig.text(
        0.5,
        0.973,
        "130 km/h gives ~20 clusters per panel, enough for a stable median; "
        "plume parameters are unchanged",
        ha="center",
        fontsize=9,
        color="#555a60",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    path = os.path.join(out_dir, "grid-12-22-38.png")
    fig.savefig(path, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"image3: {path}")
    for record in panels:
        print(
            f"  x={record['x_m']:.0f} seed={record['seed']} "
            f"n_points={record['points']} n_clusters={record['clusters']} "
            f"median_points/cluster={record['median_points_per_cluster']:.1f}"
        )
    return panels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=FIG_DIR)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    print("cluster_count_for_speed table:")
    for speed in (40, 50, 60, 80, 100, 130):
        print(f"  {speed:>3} km/h -> {cluster_count_for_speed(speed)} clusters")
    print(f"  72 km/h -> {cluster_count_for_speed(72.0)} clusters")

    synthetic = render_image1(args.out)
    render_image2(args.out, synthetic)
    render_image3(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
