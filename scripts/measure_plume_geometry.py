"""Measure where real spray sits in the ego frame versus where the v2 generator
puts its clusters, speed by speed.

Motivation (measured, not assumed): in scene 0000 at 50 km/h the real spray
labels sit at **median range 3.84 m** while the leading vehicle is at 20 m, and
at 130 km/h (scene 0099) the median is **8.58 m**. The generator spawns its
clusters at the tail of the leading vehicle and lets drag pull them back, so the
question is whether they come back to the same place.

Two parts:

A. real labels -- spray points per frame, range and elevation distribution, one
   scene per speed for the whole 50-130 km/h ladder.
B. simulated state -- alive clusters frame by frame, range/elevation
   distribution, plus a cohort tracked from birth to expiry. ``--fov-prune``
   drops clusters that passed behind the sensor, which is the geometric bound
   the current ``age > 4T`` rule does not impose.

Deterministic; run with the anaconda interpreter (numpy 2.4.3):

    /opt/anaconda3/bin/python scripts/measure_plume_geometry.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState

DATASET = Path("data/SemanticSprayDataset")
ROAD_Z_M = -0.411
BOX_LENGTH_M = 6.8268
BOX_HEIGHT_M = 2.6206
BOX_Z_M = 0.899
TAIL_BLOCK_WIDTH_M = 3.4
TAIL_BLOCK_HEIGHT_M = 1.5
DT_S = 0.1
WFH_MM = 1.0
SPEEDS_KMH = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)


def _stats(values: np.ndarray) -> str:
    if values.size == 0:
        return "n=0"
    return (
        f"n={values.size:6d} p5={np.percentile(values, 5):6.2f} "
        f"med={np.median(values):6.2f} p95={np.percentile(values, 95):6.2f}"
    )


def _histogram(values: np.ndarray, edges: list[float]) -> str:
    if values.size == 0:
        return "(khong co)"
    counts, _ = np.histogram(values, bins=edges)
    total = counts.sum()
    return "  ".join(
        f"[{edges[i]:.0f},{edges[i + 1]:.0f}) {100.0 * c / total:5.1f}%"
        for i, c in enumerate(counts)
    )


def scene_speeds() -> dict[float, list[str]]:
    """Map each metadata speed to the scene directories that report it."""
    table: dict[float, list[str]] = {}
    for metadata in sorted(DATASET.glob("*/*/metadata.txt")):
        with metadata.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        speed = float(rows[0]["object_velocity"])
        table.setdefault(speed, []).append(str(metadata.parent.relative_to(DATASET)))
    return table


def real_spray(scenes: list[str], max_frames: int) -> tuple[int, np.ndarray, np.ndarray]:
    """Spray points per frame, plus the pooled range and elevation distributions."""
    counts: list[int] = []
    ranges: list[np.ndarray] = []
    elevations: list[np.ndarray] = []
    xs: list[np.ndarray] = []
    for scene in scenes:
        scene_dir = DATASET / scene
        for path in sorted((scene_dir / "velodyne").glob("*.bin"))[:max_frames]:
            label_path = scene_dir / "labels" / (path.stem + ".label")
            if not label_path.exists():
                continue
            points = np.fromfile(path, np.float32).reshape(-1, 5)
            labels = np.fromfile(label_path, np.uint32)
            if labels.size != points.shape[0]:
                continue
            spray = points[labels == 2]
            counts.append(spray.shape[0])
            if spray.size:
                ranges.append(np.linalg.norm(spray[:, :3], axis=1))
                xs.append(spray[:, 0])
                elevations.append(
                    np.degrees(
                        np.arctan2(spray[:, 2], np.hypot(spray[:, 0], spray[:, 1]))
                    )
                )
    med_points = int(np.median(counts)) if counts else 0
    flat_r = np.concatenate(ranges) if ranges else np.empty(0)
    flat_e = np.concatenate(elevations) if elevations else np.empty(0)
    flat_x = np.concatenate(xs) if xs else np.empty(0)
    return med_points, flat_r, flat_e, flat_x


def simulate(
    speed_kmh: float,
    frames: int,
    distance_m: float,
    *,
    fov_prune: bool,
    verbose: bool,
    behind_limit: float = -15.0,
    block_bottom_frac: float = 0.0,
    block_top_frac: float = 1.5 / 2.6206,
) -> dict[str, float]:
    speed_mps = speed_kmh / 3.6
    state = PlumeState()
    rng = np.random.default_rng(11)
    context = PlumeContext(
        scene_token=f"sim-{speed_kmh:g}",
        frame_index=0,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=speed_mps,
        object_speed_mps=speed_mps,
        wfh_mm=WFH_MM,
        road_z_m=ROAD_Z_M,
        object_velocity_ego_mps=np.zeros(3, dtype=np.float64),
    )
    block_length = speed_mps * DT_S
    road_z = BOX_Z_M - BOX_HEIGHT_M / 2.0
    block_low = road_z + block_bottom_frac * BOX_HEIGHT_M
    block_high = road_z + block_top_frac * BOX_HEIGHT_M
    centre = np.array(
        [distance_m - (BOX_LENGTH_M / 2.0 + block_length / 2.0), 0.0, (block_low + block_high) / 2.0]
    )
    extents = np.array(
        [block_length / 2.0, TAIL_BLOCK_WIDTH_M / 2.0, (block_high - block_low) / 2.0]
    )

    per_frame: list[np.ndarray] = []
    cohort: dict[int, list[tuple[float, float]]] = {}
    for frame in range(frames):
        # The ego velocity MUST be passed: positions are integrated in the ego
        # frame, so without it the plume flies forward at road speed.
        state.advance(DT_S, ego_velocity=np.array([speed_mps, 0.0, 0.0]))
        state.prune()
        created = state.spawn(
            context, object_id=0, rng=rng, dt=DT_S, center=centre, extents=extents
        )
        for cluster in created:
            if cluster.cluster_id < 4:
                cohort[cluster.cluster_id] = []
        if fov_prune:
            for cluster in state.all_alive():
                if cluster.pos[0] < behind_limit:
                    cluster.age = float("inf")
            state.prune()
        alive = state.all_alive()
        for cluster in alive:
            if cluster.cluster_id in cohort:
                cohort[cluster.cluster_id].append(
                    (frame * DT_S, float(np.linalg.norm(cluster.pos)))
                )
        if alive:
            per_frame.append(np.vstack([c.pos for c in alive]))
        else:
            per_frame.append(np.empty((0, 3)))

    steady = [p for p in per_frame[-30:] if p.size]
    if not steady:
        print(f"   {speed_kmh:>5.0f} km/h : khong sinh cum nao (mean = 0)")
        return {}
    positions = np.vstack(steady)
    ranges = np.linalg.norm(positions, axis=1)
    elevations = np.degrees(
        np.arctan2(positions[:, 2], np.hypot(positions[:, 0], positions[:, 1]))
    )
    lateral = positions[:, 1]
    alive_med = float(np.median([p.shape[0] for p in per_frame[-30:]]))
    if verbose:
        print(f"   mo phong: cum song med {alive_med:.0f} | range {_stats(ranges)}")
        print(f"             elevation {_stats(elevations)}")
        print(f"             phan bo range: {_histogram(ranges, [0, 2, 4, 6, 8, 12, 20, 60, 300])}")
        for cluster_id, series in sorted(cohort.items()):
            if not series:
                continue
            step = max(1, len(series) // 8)
            sampled = series[::step] + [series[-1]]
            print(
                f"             cum {cluster_id}: "
                + "  ".join(f"t={t:.1f}s r={r:.1f}m" for t, r in sampled)
            )
    return {
        "alive_med": alive_med,
        "range_med": float(np.median(ranges)),
        "range_p95": float(np.percentile(ranges, 95)),
        "elev_med": float(np.median(elevations)),
        "x_med": float(np.median(positions[:, 0])),
        "x_p5": float(np.percentile(positions[:, 0], 5)),
        "x_p95": float(np.percentile(positions[:, 0], 95)),
        "behind_share": float(100.0 * np.mean(positions[:, 0] < 0.0)),
        "y_p95": float(np.percentile(np.abs(lateral), 95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--distance", type=float, default=20.0)
    parser.add_argument("--scenes-per-speed", type=int, default=2)
    parser.add_argument("--max-real-frames", type=int, default=60)
    parser.add_argument(
        "--behind-limit",
        type=float,
        default=-15.0,
        help="drop clusters once they fall this far behind the sensor (m)",
    )
    parser.add_argument(
        "--block-frac",
        type=float,
        nargs=2,
        default=[0.0, 1.5 / 2.6206],
        metavar=("BOTTOM", "TOP"),
        help="tail block vertical span as a fraction of the leading box height",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    table = scene_speeds()
    print("A. NHAN THAT (spray = nhan 2) — mot bo scene moi muc toc do")
    print("  km/h | diem/frame | range: p5 / med / p95 | elevation med")
    real: dict[float, tuple[int, np.ndarray, np.ndarray]] = {}
    for speed in SPEEDS_KMH:
        scenes = table.get(speed, [])[: args.scenes_per_speed]
        if not scenes:
            continue
        points, ranges, elevations, xs = real_spray(scenes, args.max_real_frames)
        real[speed] = (points, ranges, elevations)
        if ranges.size:
            print(
                f"  {speed:5.0f} | {points:10d} | {np.percentile(ranges, 5):5.2f} /"
                f" {np.median(ranges):5.2f} / {np.percentile(ranges, 95):5.2f}"
                f" | elev {np.median(elevations):5.2f} do"
                f" | x {np.percentile(xs, 5):6.1f}/{np.median(xs):6.1f}/{np.percentile(xs, 95):6.1f}"
                f" | sau cam bien {100.0 * np.mean(xs < 0):5.1f}%"
            )

    for fov_prune in (False, True):
        label = "co cat cum di qua sau cam bien" if fov_prune else "chi cat theo age > 4T"
        print(f"\nB. MO PHONG ({label}) — xe dan o {args.distance:g} m, wfh={WFH_MM} mm")
        print("  km/h | song med | range med | p95 | elevation med | nhan that: diem/frame, range med")
        for speed in SPEEDS_KMH:
            result = simulate(
                speed,
                args.frames,
                args.distance,
                fov_prune=fov_prune,
                verbose=args.verbose,
                behind_limit=args.behind_limit,
                block_bottom_frac=args.block_frac[0],
                block_top_frac=args.block_frac[1],
            )
            if not result:
                continue
            points, ranges, _ = real[speed]
            print(
                f"  {speed:5.0f} | {result['alive_med']:8.0f} | {result['range_med']:9.2f} |"
                f" {result['range_p95']:5.1f} | x {result['x_p5']:6.1f}/{result['x_med']:6.1f}"
                f"/{result['x_p95']:6.1f} | sau cam bien {result['behind_share']:5.1f}%"
                f" | |y| p95 {result['y_p95']:4.1f} | that: {points:4d} diem,"
                f" range {np.median(ranges):5.2f} m"
            )


if __name__ == "__main__":
    main()