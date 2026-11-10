#!/usr/bin/env python3
"""Measure the LiDAR beam table (ring -> elevation) from SemanticSpray.

Ticket 29a. The release's ring ids are real beam ids, but the manufacturer's
VLP-32C table does not apply: the data was clipped vertically and the ring ids
were renumbered ``0..N-1``. This script measures the angles from the data and
writes ``spray/config/beam_elevation.yaml``; it never edits the manufacturer's
table to fit (see ``docs/history/plume-beam-table.md``).

Robustness rules measured in that document:

- the elevation of a ring is the **median of the points inside its IQR**, not
  the mean: ring 0 carries spray/noise outliers up to +52 deg;
- a ring counts only in frames where it has at least ``MIN_POINTS_PER_FRAME``
  points (sparse rings are stray points, not beams);
- the sensor azimuth step is the median positive gap between consecutive
  azimuths of one ring, dropping gaps above ``MAX_GAP_DEG`` (the wrap seam).

Sampling is deterministic: sorted file list, evenly spaced indices, no random
state, so two runs write byte-identical YAML.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "data" / "SemanticSprayDataset"
OUTPUT = REPO / "spray" / "config" / "beam_elevation.yaml"

N_FRAMES = 120
MIN_POINTS_PER_FRAME = 100
MAX_GAP_DEG = 5.0
# A real beam scans (almost) every frame; a ring seen in a minority of frames
# is stray points assigned to an id that is not a beam.
MIN_FRAME_FRACTION = 0.9


def sample_frames(n_frames: int = N_FRAMES) -> list[Path]:
    """Evenly spaced frames over the whole dataset, in sorted file order."""
    files = sorted(DATASET.glob("*/*/velodyne/*.bin"))
    if len(files) < n_frames:
        raise SystemExit(
            f"need at least {n_frames} velodyne frames under {DATASET}, "
            f"found {len(files)}"
        )
    indices = np.unique(
        np.linspace(0, len(files) - 1, n_frames).round().astype(int)
    )
    return [files[int(index)] for index in indices]


def load_frame(path: Path) -> np.ndarray:
    """Read one ``velodyne/*.bin`` frame as an (N, 5) float64 array."""
    raw = np.fromfile(path, dtype=np.float32)
    if raw.size == 0 or raw.size % 5:
        raise SystemExit(f"{path}: expected x,y,z,intensity,ring rows, got {raw.size}")
    return raw.reshape(-1, 5).astype(np.float64)


def azimuth_step_deg(azimuth: np.ndarray) -> float:
    """Median positive gap between consecutive azimuths, dropping the seam."""
    ordered = np.sort(azimuth)
    gaps = np.diff(ordered)
    gaps = gaps[(gaps > 0.0) & (gaps <= MAX_GAP_DEG)]
    if gaps.size == 0:
        return float("nan")
    return float(np.median(gaps))


def measure(frames: list[Path]) -> dict:
    """Per-ring elevation medians, counts and azimuth steps over all frames."""
    per_frame_median: dict[int, list[float]] = defaultdict(list)
    per_frame_step: dict[int, list[float]] = defaultdict(list)
    points: dict[int, int] = defaultdict(int)
    n_frames: dict[int, int] = defaultdict(int)

    for path in frames:
        cloud = load_frame(path)
        x, y, z = cloud[:, 0], cloud[:, 1], cloud[:, 2]
        ring = cloud[:, 4].astype(np.int64)
        elevation = np.degrees(np.arctan2(z, np.hypot(x, y)))
        azimuth = np.degrees(np.arctan2(y, x))

        for beam in np.unique(ring):
            mask = ring == beam
            count = int(mask.sum())
            if count < MIN_POINTS_PER_FRAME:
                continue
            values = elevation[mask]
            q25, q75 = np.percentile(values, [25.0, 75.0])
            inner = values[(values >= q25) & (values <= q75)]
            if inner.size == 0:
                continue
            per_frame_median[int(beam)].append(float(np.median(inner)))
            step = azimuth_step_deg(azimuth[mask])
            if np.isfinite(step):
                per_frame_step[int(beam)].append(step)
            points[int(beam)] += count
            n_frames[int(beam)] += 1

    return {
        "per_frame_median": per_frame_median,
        "per_frame_step": per_frame_step,
        "points": points,
        "n_frames": n_frames,
    }


def beam_rows(stats: dict, frames: int) -> tuple[list[dict], list[int]]:
    """Aggregate rings into beam rows and the list of excluded sparse rings."""
    rows: list[dict] = []
    excluded: list[int] = []
    threshold = MIN_FRAME_FRACTION * frames
    for beam in sorted(stats["per_frame_median"]):
        if stats["n_frames"][beam] < threshold:
            excluded.append(beam)
            continue
        medians = np.asarray(stats["per_frame_median"][beam], dtype=np.float64)
        steps = np.asarray(stats["per_frame_step"][beam], dtype=np.float64)
        rows.append(
            {
                "ring": beam,
                "n_frame": stats["n_frames"][beam],
                "n_points": stats["points"][beam],
                "elevation_deg": float(np.median(medians)),
                "std_deg": float(np.std(medians)),
                "azimuth_step_deg": float(np.median(steps)),
            }
        )
    rings = [row["ring"] for row in rows]
    if rings != list(range(len(rings))):
        raise SystemExit(
            "measured beams are not a contiguous 0..N-1 band: " f"{rings}"
        )
    if not rows:
        raise SystemExit("no ring passed the measurement thresholds")
    return rows, excluded


def render_markdown(rows: list[dict], excluded: list[int], frames: int) -> str:
    lines = [
        f"Đo trên **{frames} frame** rải đều toàn dataset "
        f"({len(rows)} beam, ring id `0…{len(rows) - 1}`).",
        "",
        "| ring | n_frame | n_điểm | elevation_median | std_giữa_frame "
        "| azimuth_step |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['ring']} | {row['n_frame']} | {row['n_points']:,} | "
            f"{row['elevation_deg']:.4f} | {row['std_deg']:.4f} | "
            f"{row['azimuth_step_deg']:.4f} |"
        )
    if excluded:
        lines += [
            "",
            f"Bỏ (không phải beam, < {MIN_FRAME_FRACTION:.0%} số frame có "
            f"≥ {MIN_POINTS_PER_FRAME} điểm): "
            + ", ".join(str(beam) for beam in excluded),
        ]
    return "\n".join(lines)


def render_yaml(rows: list[dict], frames: int) -> str:
    azimuth_step = float(np.median([row["azimuth_step_deg"] for row in rows]))
    elevations = ", ".join(f"{row['elevation_deg']:.6f}" for row in rows)
    return "\n".join(
        [
            "# Sinh bởi scripts/measure_beam_table.py — [ĐO] trên "
            "SemanticSpray (207 scene)",
            f'source: "SemanticSpray VLP-32C, {frames} frame, ring id '
            f'0..{len(rows) - 1} (release đánh lại)"',
            f"azimuth_step_deg: {azimuth_step:.6f}",
            f"elevation_deg: [{elevations}]",
            "",
        ]
    )


def main() -> int:
    started = time.perf_counter()
    frames = sample_frames()
    stats = measure(frames)
    rows, excluded = beam_rows(stats, len(frames))
    body = render_markdown(rows, excluded, len(frames))
    text = render_yaml(rows, len(frames))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")

    elapsed = time.perf_counter() - started
    azimuth_step = float(np.median([row["azimuth_step_deg"] for row in rows]))
    print(body)
    print()
    print(f"Đã ghi {OUTPUT.relative_to(REPO)}")
    print(f"Beam: {len(rows)} (M = {len(rows)})")
    print(f"azimuth_step_deg = {azimuth_step:.6f}")
    print(f"Elapsed: {elapsed:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
