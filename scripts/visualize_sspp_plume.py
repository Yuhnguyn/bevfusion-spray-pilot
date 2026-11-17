#!/usr/bin/env python3
"""Render real spray and the generated plume side by side on the same frame.

This is a **qualitative** complement to the quantitative checks already in
``scripts/probe_sspp_plume.py`` and ``scripts/smoke_sspp_paperpath.py``: a human
looks at the two rows and judges density, height, continuity and position
relative to the vehicle tail. Nothing in ``spray/`` is changed; the chain is the
one from the smoke run, only the plotting is added.

Row upper = **real** (``labels == 2``), row lower = **generated**
(``raycast_frame`` detections). Columns: BEV ``x-y``, side view ``x-z``, and
range + ``z`` histograms. Both rows share the same axis limits, colour map and
point sizes, otherwise the eye comparison means nothing.

State must be warmed up
-----------------------
For every frame ``k`` that is drawn, the generator is run **sequentially from
frame 0 to ``k``** on the same :class:`~spray.plume_state.PlumeState` (one state
per scene, reset when the scene changes). Clusters accumulate across frames: if
only frame ``k`` were run the trail would be empty and the picture meaningless.
When several frames are requested, one pass runs up to ``max(frames)`` and
snapshots the requested indices along the way.

CLI::

    python scripts/visualize_sspp_plume.py --scene <token> --frames 0,5,10 --out <dir>
    python scripts/visualize_sspp_plume.py --grid --out <dir>

Markers on stdout per rendered frame::

    SSPP_VIS_OK scene=<s> frame=<k> n_real=<n> n_gen=<n> png=<path>
    SSPP_VIS_NO_REAL scene=<s> frame=<k>      # real side has no spray, still drawn

and at the end::

    SSPP_VIS_DONE files=<n> dir=<path>
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from spray.beam_model import (  # noqa: E402
    ELEVATION_MAX_DEG,
    ELEVATION_MIN_DEG,
    BeamTable,
)
from spray.plume import inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, seed_for  # noqa: E402
from spray.plume_state import PlumeState  # noqa: E402
from spray.raycast import raycast_frame  # noqa: E402
from spray.sspp_adapter import load_points  # noqa: E402
from spray.wet_ground import WetGroundConfig  # noqa: E402

NOISE_LABEL = 2
WFH_MM = 1.0
EPOCH = 0
SEED = 0
VEHICLE_CLASS = {
    "Crafter_dynamic": "crafter",
    "Golf_dynamic": "golf",
}
VLP32C_RINGS = 32
VLP32C_AZIMUTH_STEP_DEG = 0.2

DEFAULT_FRAMES = "0,5,10"
DEFAULT_OUT = Path.home() / ".hermes" / "drafts" / "spray-viz"
DEFAULT_DATASET_ROOT = REPO / "data" / "SemanticSprayDataset"
DEFAULT_INFOS = REPO / "data" / "sspp_infos_train.pkl"
DEFAULT_SPLIT_JSON = REPO / "data" / "sspp_split.json"
SPLIT = "train"

# Shared view limits: both rows must use these exact numbers.
X_LIM = (-10.0, 45.0)
Y_LIM = (-12.0, 12.0)
Z_LIM = (-1.0, 3.0)

# Shared styling: identical for the real and generated rows.
BG_COLOR = "#9aa0a6"
BG_ALPHA = 0.15
BG_SIZE = 1.0
FG_COLOR = "#d9480f"
FG_ALPHA = 0.8
FG_SIZE = 3.0

RANGE_BINS = np.linspace(0.0, 40.0, 21)
Z_BINS = np.linspace(-0.5, 3.0, 21)


def vlp32c_beam_table() -> BeamTable:
    """The 32-ring VLP-32C grid used by the ray-casting step (same as smoke)."""

    elevation = np.linspace(
        ELEVATION_MIN_DEG, ELEVATION_MAX_DEG, VLP32C_RINGS, dtype=np.float64
    )
    return BeamTable(
        elevation_deg=tuple(float(value) for value in elevation),
        azimuth_step_deg=VLP32C_AZIMUTH_STEP_DEG,
    )


def frames_of_scene(infos: list[dict], rel_scene: str) -> list[dict]:
    """All frames of one scene, in ascending timestamp order."""

    prefix = rel_scene + "/"
    frames = [info for info in infos if str(info["token"]).startswith(prefix)]
    frames.sort(key=lambda info: info["timestamp"])
    return frames


def read_labels(dataset_root: Path, rel_scene: str, scan_id: str) -> np.ndarray:
    path = dataset_root / rel_scene / "labels" / f"{scan_id}.label"
    return np.fromfile(path, dtype=np.int32)


def object_speed_mps(boxes: np.ndarray) -> float:
    if boxes.shape[0] == 0:
        return 0.0
    return float(np.max(np.abs(boxes[:, 7].astype(np.float64))))


def road_z_m(boxes: np.ndarray) -> float:
    return float(np.median(boxes[:, 2].astype(np.float64)))


def build_context(
    info: dict, rel_scene: str, frame_index: int, boxes: np.ndarray
) -> PlumeContext:
    return PlumeContext(
        scene_token=rel_scene,
        frame_index=frame_index,
        epoch=EPOCH,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=float(info["ego_speed_kmh"]) / 3.6,
        object_speed_mps=object_speed_mps(boxes),
        wfh_mm=WFH_MM,
        road_z_m=road_z_m(boxes),
    )


def run_scene(
    dataset_root: Path,
    rel_scene: str,
    frames: list[dict],
    wanted: list[int],
    table: BeamTable,
) -> dict[int, dict]:
    """Run the chain from frame 0 to ``max(wanted)`` and snapshot ``wanted``.

    One :class:`PlumeState` for the whole pass; this is what warms the plume up
    so frame ``k`` carries the trail of every earlier frame.
    """

    wanted_set = sorted(set(int(index) for index in wanted))
    last = wanted_set[-1]
    if last >= len(frames):
        raise SystemExit(
            f"SSPP_VIS_ERROR scene={rel_scene} frame={last} "
            f"but scene has only {len(frames)} frames"
        )

    vehicle_class = VEHICLE_CLASS[rel_scene.split("/")[0]]
    state = PlumeState()
    snapshots: dict[int, dict] = {}

    for frame_index in range(last + 1):
        info = frames[frame_index]
        points = load_points(info, dataset_root)
        labels = read_labels(dataset_root, rel_scene, info["scan_id"])
        if labels.shape[0] != points.shape[0]:
            raise ValueError(
                f"{info['token']}: {labels.shape[0]} labels vs "
                f"{points.shape[0]} points"
            )
        noise = labels == NOISE_LABEL
        clean = points[~noise]

        boxes = np.asarray(info["gt_boxes"], dtype=np.float64)
        context = build_context(info, rel_scene, frame_index, boxes)

        result = inject_plume_stateful(
            clean,
            boxes,
            context,
            state,
            seed=SEED,
            token=info["token"],
            wet_ground=WetGroundConfig(enabled=True),
            vehicle_class=vehicle_class,
        )
        raycast = raycast_frame(
            result.points,
            state.all_alive(),
            table=table,
            road_z_m=context.road_z_m,
            rng=np.random.default_rng(
                seed_for(info["token"], frame_index, EPOCH)
            ),
        )

        if frame_index in wanted_set:
            detections = raycast.detections
            snapshots[frame_index] = {
                "scene": rel_scene,
                "frame": frame_index,
                "boxes": boxes,
                "road_z": context.road_z_m,
                "bg": clean[:, :3].astype(np.float64),
                "real": points[noise][:, :3].astype(np.float64),
                "gen": (
                    detections[:, :3].astype(np.float64)
                    if detections.size
                    else np.empty((0, 3), dtype=np.float64)
                ),
                "n_real": int(noise.sum()),
                "n_gen": int(detections.shape[0]),
                "clusters_alive": len(state.all_alive()),
            }

    return snapshots


def footprint_corners(box: np.ndarray) -> np.ndarray:
    """Closed ``(5, 2)`` footprint of a 9-column box.

    Columns are ``x, y, z_bottom, size_x, size_y, size_z, yaw, vx, vy`` (see
    ``spray/sspp_adapter.py``). ``size_x`` is the longitudinal extent along yaw
    and ``size_y`` the lateral one; measured on 120 frames, 33,743 points fall
    in the box with ``size_x`` along yaw versus 296 for the swap.
    """

    cx, cy = float(box[0]), float(box[1])
    half_length = float(box[3]) / 2.0
    half_width = float(box[4]) / 2.0
    yaw = float(box[6])
    local = np.array(
        [
            [half_length, half_width],
            [half_length, -half_width],
            [-half_length, -half_width],
            [-half_length, half_width],
            [half_length, half_width],
        ],
        dtype=np.float64,
    )
    cos_yaw = np.cos(yaw)
    sin_yaw = np.sin(yaw)
    rotation = np.array(
        [[cos_yaw, -sin_yaw], [sin_yaw, cos_yaw]], dtype=np.float64
    )
    return local @ rotation.T + np.array([cx, cy])


def _clip(points: np.ndarray, x_lim, y_lim) -> np.ndarray:
    if points.shape[0] == 0:
        return points
    mask = (
        (points[:, 0] >= x_lim[0])
        & (points[:, 0] <= x_lim[1])
        & (points[:, 1] >= y_lim[0])
        & (points[:, 1] <= y_lim[1])
    )
    return points[mask]


def draw_bev(ax, snapshot: dict, fg: np.ndarray) -> None:
    bg = snapshot["bg"]
    if bg.shape[0]:
        ax.scatter(
            bg[:, 0],
            bg[:, 1],
            s=BG_SIZE,
            c=BG_COLOR,
            alpha=BG_ALPHA,
            linewidths=0,
            rasterized=True,
        )
    if fg.shape[0]:
        ax.scatter(
            fg[:, 0],
            fg[:, 1],
            s=FG_SIZE,
            c=FG_COLOR,
            alpha=FG_ALPHA,
            linewidths=0,
            rasterized=True,
        )
    for box in snapshot["boxes"]:
        if not np.isfinite(box[:7]).all():
            continue
        ax.add_patch(
            Polygon(
                footprint_corners(box),
                closed=True,
                fill=False,
                edgecolor="#1f2933",
                linewidth=1.0,
            )
        )
    ax.set_xlim(*X_LIM)
    ax.set_ylim(*Y_LIM)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x — forward (m)")
    ax.set_ylabel("y — lateral (m)")
    ax.grid(True, linewidth=0.3, alpha=0.4)


def draw_side(ax, snapshot: dict, fg: np.ndarray) -> None:
    bg = snapshot["bg"]
    bg_mask = (bg[:, 0] >= X_LIM[0]) & (bg[:, 0] <= X_LIM[1])
    if bg.shape[0]:
        ax.scatter(
            bg[bg_mask, 0],
            bg[bg_mask, 2],
            s=BG_SIZE,
            c=BG_COLOR,
            alpha=BG_ALPHA,
            linewidths=0,
            rasterized=True,
        )
    fg_mask = (fg[:, 0] >= X_LIM[0]) & (fg[:, 0] <= X_LIM[1])
    if fg.shape[0]:
        ax.scatter(
            fg[fg_mask, 0],
            fg[fg_mask, 2],
            s=FG_SIZE,
            c=FG_COLOR,
            alpha=FG_ALPHA,
            linewidths=0,
            rasterized=True,
        )
    ground = snapshot["road_z"]
    ax.axhline(
        ground,
        color="#1f2933",
        linewidth=1.0,
        linestyle="--",
        label=f"road z={ground:.3f} m",
    )
    for box in snapshot["boxes"]:
        if not np.isfinite(box[:7]).all():
            continue
        corners = footprint_corners(box)
        x_lo = float(corners[:, 0].min())
        x_hi = float(corners[:, 0].max())
        z_lo = float(box[2])
        height = float(box[5])
        ax.add_patch(
            Polygon(
                [
                    [x_lo, z_lo],
                    [x_hi, z_lo],
                    [x_hi, z_lo + height],
                    [x_lo, z_lo + height],
                ],
                closed=True,
                fill=False,
                edgecolor="#1f2933",
                linewidth=0.8,
                alpha=0.7,
            )
        )
    ax.set_xlim(*X_LIM)
    ax.set_ylim(*Z_LIM)
    ax.set_xlabel("x — forward (m)")
    ax.set_ylabel("z (m)")
    ax.grid(True, linewidth=0.3, alpha=0.4)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.5)


def draw_histograms(ax_range, ax_z, fg: np.ndarray) -> None:
    if fg.shape[0]:
        distances = np.linalg.norm(fg[:, :3], axis=1)
        z = fg[:, 2]
        median_range = float(np.median(distances))
        z_p5, z_p50, z_p95 = (float(v) for v in np.percentile(z, [5, 50, 95]))
    else:
        distances = np.empty(0)
        z = np.empty(0)
        median_range = float("nan")
        z_p5 = z_p50 = z_p95 = float("nan")

    ax_range.hist(distances, bins=RANGE_BINS, color=FG_COLOR, alpha=0.8)
    ax_z.hist(z, bins=Z_BINS, color=FG_COLOR, alpha=0.8)

    ax_range.set_xlim(RANGE_BINS[0], RANGE_BINS[-1])
    ax_z.set_xlim(Z_BINS[0], Z_BINS[-1])
    ax_z.set_xlabel("z (m)")
    ax_range.set_ylabel("count")
    ax_z.set_ylabel("count")
    for ax in (ax_range, ax_z):
        ax.grid(True, linewidth=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)

    ax_range.text(
        0.98,
        0.95,
        f"n={fg.shape[0]}\n"
        f"range p50={median_range:.1f} m\n"
        f"z p5/p50/p95={z_p5:.2f}/{z_p50:.2f}/{z_p95:.2f} m",
        transform=ax_range.transAxes,
        ha="right",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.7),
    )


def render_frame(snapshot: dict, png: Path) -> None:
    """Two rows (real, generated) × three columns, shared scales."""

    fig = plt.figure(figsize=(16.0, 9.0))
    grid = fig.add_gridspec(
        2,
        3,
        width_ratios=[1.15, 1.15, 0.95],
        hspace=0.38,
        wspace=0.24,
    )

    rows = [
        (
            f"THẬT — label==2, n={snapshot['n_real']}",
            snapshot["real"],
        ),
        (
            "SINH — raycast detections, "
            f"n={snapshot['n_gen']}, "
            f"clusters_alive={snapshot['clusters_alive']}",
            snapshot["gen"],
        ),
    ]

    hist_axes = []
    for row, (title, fg) in enumerate(rows):
        ax_bev = fig.add_subplot(grid[row, 0])
        ax_side = fig.add_subplot(grid[row, 1])
        nested = grid[row, 2].subgridspec(2, 1, hspace=0.75)
        ax_range = fig.add_subplot(nested[0])
        ax_z = fig.add_subplot(nested[1])

        draw_bev(ax_bev, snapshot, fg)
        draw_side(ax_side, snapshot, fg)
        draw_histograms(ax_range, ax_z, fg)

        ax_bev.set_title(f"BEV (x–y)\n{title}", fontsize=10)
        ax_side.set_title("Side view (x–z)", fontsize=10)
        ax_range.set_title("range + z histograms", fontsize=9, loc="left")
        hist_axes.extend([ax_range, ax_z])

    top = max(ax.get_ylim()[1] for ax in hist_axes)
    for ax in hist_axes:
        ax.set_ylim(0.0, top * 1.05 if top > 0 else 1.0)

    fig.suptitle(
        f"{snapshot['scene']} — frame {snapshot['frame']} — "
        "real vs generated spray",
        fontsize=12,
    )
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)


def render_grid(rows: list[dict], png: Path) -> None:
    """Contact sheet: 3 scenes (rows) × 2 sides (real | generated) of BEV plots."""

    fig = plt.figure(figsize=(14.0, 4.2 * len(rows)))
    grid = fig.add_gridspec(len(rows), 2, hspace=0.32, wspace=0.12)

    for row, entry in enumerate(rows):
        snapshot = entry["snapshot"]
        speed = entry["speed"]
        sides = [
            ("THẬT", snapshot["real"], snapshot["n_real"]),
            ("SINH", snapshot["gen"], snapshot["n_gen"]),
        ]
        for col, (label, fg, count) in enumerate(sides):
            ax = fig.add_subplot(grid[row, col])
            draw_bev(ax, snapshot, fg)
            colour = "#1f2933" if col == 0 else FG_COLOR
            ax.set_title(
                f"{snapshot['scene']}  (ego {speed:.0f} km/h) — "
                f"frame {snapshot['frame']}\n"
                f"{label}  n={count}"
                + (
                    f", clusters_alive={snapshot['clusters_alive']}"
                    if col == 1
                    else ""
                ),
                fontsize=9,
                color=colour,
            )

    fig.suptitle(
        "SemanticSpray++ — real spray vs generated plume "
        "(BEV, lowest / middle / highest train speed)",
        fontsize=12,
    )
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _emit_marker(snapshot: dict, png: Path) -> None:
    if snapshot["n_real"] == 0:
        print(
            f"SSPP_VIS_NO_REAL scene={snapshot['scene']} "
            f"frame={snapshot['frame']}"
        )
    print(
        "SSPP_VIS_OK "
        f"scene={snapshot['scene']} "
        f"frame={snapshot['frame']} "
        f"n_real={snapshot['n_real']} "
        f"n_gen={snapshot['n_gen']} "
        f"png={png}"
    )


def choose_default_scene(
    infos: list[dict], split_doc: dict
) -> tuple[str, list[dict]]:
    """First train scene whose boxes move faster than 40 km/h."""

    for rel_scene in split_doc["split"][SPLIT]:
        frames = frames_of_scene(infos, rel_scene)
        if not frames:
            continue
        for frame in frames:
            boxes = np.asarray(frame["gt_boxes"], dtype=np.float64)
            if boxes.shape[0] and object_speed_mps(boxes) * 3.6 > 40.0:
                return rel_scene, frames
    raise SystemExit("SSPP_VIS_ERROR no train scene with box speed > 40 km/h")


def pick_grid_scenes(infos: list[dict], split_doc: dict) -> list[tuple]:
    """Three train scenes at the lowest, middle and highest ego speed."""

    entries: list[tuple[str, list[dict], float]] = []
    for rel_scene in split_doc["split"][SPLIT]:
        frames = frames_of_scene(infos, rel_scene)
        if not frames:
            continue
        speed = float(np.median([float(f["ego_speed_kmh"]) for f in frames]))
        entries.append((rel_scene, frames, speed))
    if not entries:
        raise SystemExit("SSPP_VIS_ERROR no train frames in the split")

    speeds = sorted({round(entry[2], 1) for entry in entries})
    targets = (
        [speeds[0], speeds[len(speeds) // 2], speeds[-1]]
        if len(speeds) >= 3
        else speeds
    )
    picks: list[tuple] = []
    used: set[str] = set()
    for speed in targets:
        for rel_scene, frames, scene_speed in entries:
            if rel_scene in used:
                continue
            if abs(scene_speed - speed) < 0.5:
                picks.append((rel_scene, frames, scene_speed))
                used.add(rel_scene)
                break
    return picks[:3]


def parse_frames(text: str) -> list[int]:
    indices: list[int] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        value = int(chunk)
        if value < 0:
            raise SystemExit(f"SSPP_VIS_ERROR negative frame index {value}")
        indices.append(value)
    if not indices:
        raise SystemExit("SSPP_VIS_ERROR --frames is empty")
    return indices


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scene",
        default=None,
        help="scene token, e.g. Crafter_dynamic/0012_2021-09-08-14-50-58_0",
    )
    parser.add_argument(
        "--frames",
        default=DEFAULT_FRAMES,
        help="comma-separated frame indices (default 0,5,10)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--grid",
        action="store_true",
        help="contact sheet: 3 train scenes (low/mid/high speed) × real|gen",
    )
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--infos", type=Path, default=DEFAULT_INFOS)
    parser.add_argument("--split-json", type=Path, default=DEFAULT_SPLIT_JSON)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_root = args.dataset_root.resolve()
    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with args.infos.open("rb") as handle:
        infos = pickle.load(handle)
    split_doc = json.loads(args.split_json.read_text(encoding="utf-8"))
    table = vlp32c_beam_table()

    if args.grid:
        picks = pick_grid_scenes(infos, split_doc)
        if not picks:
            raise SystemExit("SSPP_VIS_ERROR no scene picked for --grid")
        entries: list[dict] = []
        for rel_scene, frames, speed in picks:
            mid = len(frames) // 2
            snapshots = run_scene(
                dataset_root, rel_scene, frames, [mid], table
            )
            entries.append({"snapshot": snapshots[mid], "speed": speed})

        png = out_dir / "sspp_plume_grid.png"
        render_grid(entries, png)
        for entry in entries:
            _emit_marker(entry["snapshot"], png)
        print(f"SSPP_VIS_DONE files=1 dir={out_dir}")
        return 0

    if args.scene:
        rel_scene = args.scene.strip().strip("/")
        frames = frames_of_scene(infos, rel_scene)
        if not frames:
            raise SystemExit(
                f"SSPP_VIS_ERROR scene={rel_scene} not found in {args.infos}"
            )
    else:
        rel_scene, frames = choose_default_scene(infos, split_doc)

    wanted = parse_frames(args.frames)
    snapshots = run_scene(dataset_root, rel_scene, frames, wanted, table)

    written = 0
    for index in sorted(set(wanted)):
        snapshot = snapshots[index]
        png = out_dir / (
            f"{rel_scene.replace('/', '_')}_f{index:03d}.png"
        )
        render_frame(snapshot, png)
        _emit_marker(snapshot, png)
        written += 1

    print(f"SSPP_VIS_DONE files={written} dir={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
