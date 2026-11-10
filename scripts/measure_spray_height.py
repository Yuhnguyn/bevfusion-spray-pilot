"""Measure the vertical placement of the real spray in a pitch-invariant frame.

The elevation angle of a spray point is measured from the sensor, so it carries
the ego vehicle's pitch and roll. Two frames are immune to that:

* **height above the local road plane** -- fit a plane to the ground points of
  the same frame and subtract it, so pitch/roll cancel out;
* **fraction of the leading vehicle's height** -- divide that height by the
  vehicle box height, which turns ``1,1-1,9 m`` into a number that transfers to
  any vehicle without hardcoding metres.

The second one is what a generator should use: the tail block then spans a
*measured fraction* of the box, and the absolute metres follow from the box
geometry of whatever vehicle is in front.

    /opt/anaconda3/bin/python scripts/measure_spray_height.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

DATASET = Path("data/SemanticSprayDataset")
BOX_HEIGHT_M = 2.6206  # [ĐO] docs/plume-v2-measurements.md, van of Crafter_dynamic
SPEEDS_KMH = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)


def _plane(points: np.ndarray) -> tuple[float, float, float]:
    """Robust ground plane ``z = a*x + b*y + c`` fitted inside 3-40 m."""
    mask = (points[:, 0] > 3.0) & (points[:, 0] < 40.0) & (np.abs(points[:, 2]) < 0.4)
    subset = points[mask]
    if subset.shape[0] < 50:
        return 0.0, 0.0, -0.411
    design = np.column_stack([subset[:, 0], subset[:, 1], np.ones(subset.shape[0])])
    coef, *_ = np.linalg.lstsq(design, subset[:, 2], rcond=None)
    for _ in range(3):
        residual = subset[:, 2] - design @ coef
        keep = np.abs(residual) < 0.05
        if keep.sum() < 50:
            break
        coef, *_ = np.linalg.lstsq(design[keep], subset[keep, 2], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def scene_speeds() -> dict[float, list[str]]:
    table: dict[float, list[str]] = {}
    for metadata in sorted(DATASET.glob("*/*/metadata.txt")):
        with metadata.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            continue
        table.setdefault(float(rows[0]["object_velocity"]), []).append(
            str(metadata.parent.relative_to(DATASET))
        )
    return table


def measure(scenes: list[str], max_frames: int) -> dict[str, np.ndarray]:
    heights: list[np.ndarray] = []
    ranges: list[np.ndarray] = []
    per_frame_points: list[int] = []
    pitch_deg: list[float] = []
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
            a, b, c = _plane(points)
            pitch_deg.append(float(np.degrees(np.arctan(a))))
            spray = points[labels == 2]
            per_frame_points.append(spray.shape[0])
            if not spray.size:
                continue
            above = spray[:, 2] - (a * spray[:, 0] + b * spray[:, 1] + c)
            heights.append(above)
            ranges.append(np.linalg.norm(spray[:, :3], axis=1))
    return {
        "height": np.concatenate(heights) if heights else np.empty(0),
        "range": np.concatenate(ranges) if ranges else np.empty(0),
        "points": np.asarray(per_frame_points, dtype=float),
        "pitch": np.asarray(pitch_deg, dtype=float),
    }


def main() -> None:
    table = scene_speeds()
    pooled_h: list[np.ndarray] = []
    print("Do cao bui nuoc tren mat duong da fit (hieu chinh pitch/roll), 2 scene/muc")
    print("- 100 % chieu cao box = 2,6206 m (van Crafter_dynamic)")
    print(
        "  km/h | pitch med | diem/frame med | do cao: p5 / med / p95 (m)"
        " | % chieu cao box: p5 / med / p95"
    )
    for speed in SPEEDS_KMH:
        scenes = table.get(speed, [])[:2]
        if not scenes:
            continue
        data = measure(scenes, 60)
        height = data["height"]
        if not height.size:
            print(f"  {speed:5.0f} | khong co diem spray")
            continue
        pooled_h.append(height)
        p5, med, p95 = np.percentile(height, [5, 50, 95])
        print(
            f"  {speed:5.0f} | {np.median(data['pitch']):+8.2f} do |"
            f" {np.median(data['points']):13.0f} | {p5:5.2f} / {med:5.2f} / {p95:5.2f}"
            f" | {100 * p5 / BOX_HEIGHT_M:5.1f} / {100 * med / BOX_HEIGHT_M:5.1f}"
            f" / {100 * p95 / BOX_HEIGHT_M:5.1f} %"
        )
    if pooled_h:
        pooled = np.concatenate(pooled_h)
        p5, med, p95 = np.percentile(pooled, [5, 50, 95])
        print(
            f"\nGOP TAT CA 50-130 km/h (n={pooled.size} diem spray):"
            f" p5={p5:.2f} m  med={med:.2f} m  p95={p95:.2f} m"
            f" | theo chieu cao box: {100 * p5 / BOX_HEIGHT_M:.1f} %"
            f" / {100 * med / BOX_HEIGHT_M:.1f} % / {100 * p95 / BOX_HEIGHT_M:.1f} %"
        )
        print(
            f"  khoi sau duoi hien tai phu 0-1,5 m tren mat duong"
            f" = 0,0-{100 * 1.5 / BOX_HEIGHT_M:.1f} % chieu cao box"
            f" | trung vi khoi = {100 * 0.75 / BOX_HEIGHT_M:.1f} %"
        )
        print(
            f"  trung vi nhan that = {100 * med / BOX_HEIGHT_M:.1f} % chieu cao box"
            f" ({med:.2f} m) -> khoi can phu quanh muc do, khong phai 0-1,5 m"
        )


if __name__ == "__main__":
    main()