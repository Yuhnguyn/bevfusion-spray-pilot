#!/usr/bin/env python3
"""Compute SemanticSpray plume statistics for simulator comparison.

Reads the extracted SemanticSpray dataset, clusters label-2 (noise) points on
a sampled set of scans, and writes a markdown report next to the simulator
defaults from ``spray.plume.PlumeConfig``.
"""
import argparse
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from spray.spray_stats import (  # noqa: E402
    StatsAccumulator,
    compare_to_simulator,
    load_scan,
    render_markdown,
)


def scene_dirs(root: str) -> list[str]:
    scenes = []
    for group in sorted(os.listdir(root)):
        group_dir = os.path.join(root, group)
        if not os.path.isdir(group_dir):
            continue
        for scene in sorted(os.listdir(group_dir)):
            scene_dir = os.path.join(group_dir, scene)
            if os.path.isdir(os.path.join(scene_dir, "velodyne")):
                scenes.append(scene_dir)
    return scenes


def sample_scan_ids(scene: str, limit: int) -> list[str]:
    ids = sorted(
        name[:-4] for name in os.listdir(os.path.join(scene, "velodyne"))
        if name.endswith(".bin")
    )
    if limit <= 0 or limit >= len(ids):
        return ids
    picks = np.linspace(0, len(ids) - 1, limit).round().astype(int)
    return [ids[index] for index in sorted(set(picks.tolist()))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        default=os.path.join(REPO, "data", "SemanticSprayDataset"),
    )
    parser.add_argument("--frames-per-scene", type=int, default=10)
    parser.add_argument("--scenes", type=int, default=0, help="0 = all")
    parser.add_argument("--radius", type=float, default=0.5)
    parser.add_argument("--dense-min", type=int, default=5)
    parser.add_argument("--speed-kmh", type=float, default=50.0)
    parser.add_argument(
        "--out",
        default=os.path.join(REPO, "docs", "semantic-spray-stats.md"),
    )
    args = parser.parse_args()

    scenes = scene_dirs(args.data)
    if args.scenes:
        scenes = scenes[: args.scenes]
    if not scenes:
        raise SystemExit(f"no scenes found under {args.data}")

    accumulator = StatsAccumulator(radius=args.radius, dense_min=args.dense_min)
    sampled_frames = 0
    for number, scene in enumerate(scenes, start=1):
        for scan_id in sample_scan_ids(scene, args.frames_per_scene):
            points, labels = load_scan(scene, scan_id)
            accumulator.add(points, labels)
            sampled_frames += 1
        print(
            f"\rscene {number}/{len(scenes)}  frames {sampled_frames}",
            end="",
            flush=True,
        )
    print()

    summary = accumulator.summary()
    rows = compare_to_simulator(summary, speed_kmh=args.speed_kmh)
    report = render_markdown(
        summary,
        rows,
        scenes=len(scenes),
        sampled_frames=sampled_frames,
        speed_kmh=args.speed_kmh,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(report)
    print(f"wrote {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
