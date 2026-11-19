#!/usr/bin/env python3
"""Verify the frame spacing (Δt) of SemanticSpray++ before trusting 0.1 s.

``spray.plume_state.DEFAULT_DT_S`` is the VLP-32C ``update_cycle_time`` from the
reference profile, not something measured on this release. Before the stateful
plume advects clusters with that constant, the background displacement between
two consecutive scans is measured here:

1. split every cloud into azimuth bins of ``0.5 deg``;
2. take the median range (``|xyz|``) of each bin for frame ``k`` and ``k + 1``;
3. drop bins empty in either frame;
4. report ``median_shift_m`` = median of ``|r_{k+1} - r_k|`` over the surviving
   bins and ``implied_dt_s = median_shift_m / ego_speed_mps``.

The statistic is a magnitude on purpose. The signed median of the same deltas
is also printed (``SSPP_DT_PROBE_SIGNED``) but it is not the verdict: the
ground plane dominates the point count and is translation-invariant, so the
signed per-bin median collapses toward zero and says nothing about motion.
``|Δr|`` is what the prescribed check uses, and at 60–120 km/h a 0.1 s step
puts about 1.7–3.3 m between the two scans.

This is a measurement. Nothing in ``spray/`` is changed, and a mismatch is
reported, not fixed.

Run with::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
        scripts/verify_sspp_dt.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from spray.sspp_adapter import (  # noqa: E402
    build_info,
    ego_speed_kmh,
    load_points,
    object_speed_kmh,
    read_metadata,
)

AZIMUTH_BIN_DEG = 0.5
EXPECTED_DT_S = 0.1
TOLERANCE = 0.5
DEFAULT_SCAN_A = "000000"
DEFAULT_SCAN_B = "000001"
DEFAULT_DATASET_ROOT = REPO / "data" / "SemanticSprayDataset"
DEFAULT_SPLIT_JSON = REPO / "data" / "sspp_split.json"


def select_scenes(scenes: list[str]) -> list[str]:
    """Three train scenes: the first and last Crafter plus the first Golf.

    The train list is ordered by scene id, which the split builder grouped by
    speed, so the first and last Crafter bracket the speed range (60 and
    120 km/h here). Probing two speeds keeps the speed dependence of the
    statistic visible instead of hiding it behind one bucket.
    """

    chosen: list[str] = []
    crafter = [scene for scene in scenes if scene.startswith("Crafter_dynamic/")]
    golf = [scene for scene in scenes if scene.startswith("Golf_dynamic/")]
    if crafter:
        chosen.append(crafter[0])
        if len(crafter) > 1:
            chosen.append(crafter[-1])
    if golf:
        chosen.append(golf[0])
    if len(chosen) < 3:
        for scene in scenes:
            if scene not in chosen:
                chosen.append(scene)
            if len(chosen) >= 3:
                break
    return chosen[:3]


def bin_median_ranges(points: np.ndarray, step_deg: float) -> np.ndarray:
    """Median range per azimuth bin; ``nan`` where a bin is empty."""

    count = int(round(360.0 / step_deg))
    azimuth = np.degrees(np.arctan2(points[:, 1], points[:, 0])) % 360.0
    index = (np.rint(azimuth / step_deg).astype(np.int64)) % count
    ranges = np.linalg.norm(points[:, :3].astype(np.float64), axis=1)

    order = np.argsort(index, kind="stable")
    sorted_index = index[order]
    sorted_range = ranges[order]
    starts = np.searchsorted(sorted_index, np.arange(count))
    ends = np.searchsorted(sorted_index, np.arange(count), side="right")

    medians = np.full(count, np.nan)
    for bin_index in range(count):
        if ends[bin_index] > starts[bin_index]:
            medians[bin_index] = np.median(
                sorted_range[starts[bin_index] : ends[bin_index]]
            )
    return medians


def measure_shift(
    dataset_root: Path,
    rel_scene: str,
    metadata_row: dict[str, str],
    scan_a: str,
    scan_b: str,
) -> dict:
    """Background shift between two consecutive scans of one scene."""

    info_a = build_info(dataset_root, rel_scene, scan_a, metadata_row)
    info_b = build_info(dataset_root, rel_scene, scan_b, metadata_row)
    medians_a = bin_median_ranges(load_points(info_a, dataset_root), AZIMUTH_BIN_DEG)
    medians_b = bin_median_ranges(load_points(info_b, dataset_root), AZIMUTH_BIN_DEG)

    filled = np.isfinite(medians_a) & np.isfinite(medians_b)
    delta = medians_b[filled] - medians_a[filled]
    shift = float(np.median(np.abs(delta)))
    signed = float(np.median(delta))

    object_kmh = object_speed_kmh(metadata_row)
    ego_kmh = ego_speed_kmh(metadata_row, object_kmh)
    ego_mps = ego_kmh / 3.6
    return {
        "scene": rel_scene,
        "speed_kmh": ego_kmh,
        "bins": int(filled.sum()),
        "median_shift_m": shift,
        "signed_median_shift_m": signed,
        "implied_dt_s": shift / ego_mps if ego_mps > 0.0 else float("nan"),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--split-json", type=Path, default=DEFAULT_SPLIT_JSON)
    parser.add_argument("--split", default="train")
    parser.add_argument("--scan-a", default=DEFAULT_SCAN_A)
    parser.add_argument("--scan-b", default=DEFAULT_SCAN_B)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_root = args.dataset_root.resolve()
    split_doc = json.loads(args.split_json.read_text(encoding="utf-8"))
    scenes = select_scenes(list(split_doc["split"][args.split]))

    mismatches = 0
    for rel_scene in scenes:
        scene_dir = dataset_root / rel_scene
        metadata_row = read_metadata(scene_dir / "metadata.txt")
        measured = measure_shift(
            dataset_root, rel_scene, metadata_row, args.scan_a, args.scan_b
        )
        print(
            "SSPP_DT_PROBE "
            f"scene={measured['scene']} "
            f"speed_kmh={measured['speed_kmh']:.0f} "
            f"median_shift_m={measured['median_shift_m']:.3f} "
            f"implied_dt_s={measured['implied_dt_s']:.4f}"
        )
        print(
            "SSPP_DT_PROBE_SIGNED "
            f"scene={measured['scene']} "
            f"bins={measured['bins']} "
            f"signed_median_shift_m={measured['signed_median_shift_m']:.3f}"
        )
        if abs(measured["implied_dt_s"] - EXPECTED_DT_S) > TOLERANCE * EXPECTED_DT_S:
            mismatches += 1
            print(
                "SSPP_DT_MISMATCH "
                f"scene={measured['scene']} "
                f"implied_dt_s={measured['implied_dt_s']:.4f} "
                f"expected_dt_s={EXPECTED_DT_S}"
            )
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
