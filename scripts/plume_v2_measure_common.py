#!/usr/bin/env python3
"""Shared helpers for the ticket-25 zero-GPU measurements.

Only numpy + stdlib. The four measurement scripts each own one marker section
in ``docs/plume-v2-measurements.md``; this module provides the file I/O and the
dataset readers so a re-run produces byte-identical sections.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "data" / "SemanticSprayDataset"
DOC = REPO / "docs" / "plume-v2-measurements.md"
GROUPS = ("Crafter_dynamic", "Golf_dynamic")

VLP32C_MANUAL_URL = (
    "https://data.ouster.io/downloads/velodyne/user-manual/"
    "vlp-32c-revd-user-manual.pdf"
)
VLP32C_SOURCE = "[PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2"
HDL32E_DATASHEET_URL = (
    "https://www.mapix.com/wp-content/uploads/2018/07/"
    "97-0038_Rev-M_-HDL-32E_Datasheet_Web.pdf"
)
HDL32E_SOURCE = (
    "[PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N "
    "(FOV +10,67…−30,67; bước 1,33°)"
)
DATASET_README_URL = (
    "https://github.com/uulm-mrm/semantic_spray_dataset"
)

VLP32C_ELEVATION_BY_LASER_ID = {
    0: -25.000,
    1: -1.000,
    2: -1.667,
    3: -15.639,
    4: -11.310,
    5: 0.000,
    6: -0.667,
    7: -8.843,
    8: -7.254,
    9: 0.333,
    10: -0.333,
    11: -6.148,
    12: -5.333,
    13: 1.333,
    14: 0.667,
    15: -4.000,
    16: -4.667,
    17: 1.667,
    18: 1.000,
    19: -3.667,
    20: -3.333,
    21: 3.333,
    22: 2.333,
    23: -2.667,
    24: -3.000,
    25: 7.000,
    26: 4.667,
    27: -2.333,
    28: -2.000,
    29: 15.000,
    30: 10.333,
    31: -1.333,
}

HDL32E_ELEVATION_BY_LASER_ID = {
    index: value
    for index, value in enumerate(
        (
            -30.67, -29.33, -28.00, -26.67, -25.33, -24.00, -22.67, -21.33,
            -20.00, -18.67, -17.33, -16.00, -14.67, -13.33, -12.00, -10.67,
            -9.33, -8.00, -6.67, -5.33, -4.00, -2.67, -1.33, 0.00,
            1.33, 2.67, 4.00, 5.33, 6.67, 8.00, 9.33, 10.67,
        )
    )
}

DOC_HEADER = """# Plume v2 — số đo 0 GPU (ticket 25)

File này do 4 script sinh ra; mỗi section nằm giữa cặp marker
`<!-- BEGIN <script> -->` … `<!-- END <script> -->` và được **thay**, không nối thêm.
Chạy lại bất kỳ script nào cũng cho đúng cùng nội dung (idempotent).

```bash
/opt/anaconda3/bin/python scripts/measure_speeds.py
/opt/anaconda3/bin/python scripts/measure_beam_angles.py
/opt/anaconda3/bin/python scripts/measure_ego_motion.py
/opt/anaconda3/bin/python scripts/verify_frame_geometry.py
```

Tag: `[ĐO]` đo trên máy này · `[PAPER]` spec nhà sản xuất · `[CHỌN]` giả định
của dự án, không suy ra từ nguồn · `[tính toán]` số suy ra từ công thức đã dẫn.
"""


def scene_dirs() -> list[Path]:
    return [
        scene
        for group in GROUPS
        for scene in sorted((DATASET / group).iterdir())
        if (scene / "velodyne").is_dir()
    ]


def frame_ids(scene: Path) -> list[str]:
    return sorted(path.stem for path in (scene / "velodyne").glob("*.bin"))


def read_metadata(scene: Path) -> dict[str, str]:
    rows = [
        row
        for row in csv.reader((scene / "metadata.txt").read_text().splitlines())
        if row
    ]
    if len(rows) != 2:
        raise ValueError(f"{scene}/metadata.txt: expected 2 rows, got {len(rows)}")
    return dict(zip(rows[0], rows[1]))


def load_points(scene: Path, scan_id: str) -> np.ndarray:
    return np.fromfile(
        scene / "velodyne" / f"{scan_id}.bin", dtype=np.float32
    ).reshape(-1, 5)


def load_labels(scene: Path, scan_id: str) -> np.ndarray:
    return np.fromfile(scene / "labels" / f"{scan_id}.label", dtype=np.int32)


def evenly(items: list, count: int) -> list:
    if count <= 0 or count >= len(items):
        return list(items)
    picks = np.linspace(0, len(items) - 1, count).round().astype(int)
    return [items[index] for index in sorted(set(picks.tolist()))]


def _section_markers(name: str) -> tuple[str, str]:
    return f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"


def replace_section(name: str, body: str, doc: Path = DOC) -> None:
    doc.parent.mkdir(parents=True, exist_ok=True)
    if not doc.exists():
        doc.write_text(DOC_HEADER + "\n", encoding="utf-8")
    text = doc.read_text(encoding="utf-8")
    begin, end = _section_markers(name)
    section = f"{begin}\n{body.strip()}\n{end}\n"

    if begin in text and end in text:
        start = text.index(begin)
        stop = text.index(end, start) + len(end)
        if text[stop : stop + 1] == "\n":
            stop += 1
        text = text[:start] + section + text[stop:]
    else:
        conclusion = "<!-- BEGIN conclusion -->"
        if conclusion in text:
            index = text.index(conclusion)
            text = text[:index] + section + "\n" + text[index:]
        else:
            text = text.rstrip("\n") + "\n\n" + section
    doc.write_text(text, encoding="utf-8")


def speed_stats() -> dict:
    records = []
    for group in GROUPS:
        for scene in sorted((DATASET / group).iterdir()):
            if not (scene / "velodyne").is_dir():
                continue
            meta = read_metadata(scene)
            records.append(
                {
                    "group": group,
                    "scene": scene.name,
                    "object_name": meta["object_name"],
                    "object_velocity": int(float(meta["object_velocity"])),
                    "ego_velocity": int(float(meta["ego_velocity"])),
                    "distance": float(meta["distance_to_object"]),
                    "itr": int(float(meta["itr_after_water"])),
                    "frames": len(frame_ids(scene)),
                }
            )

    total_frames = sum(record["frames"] for record in records)

    def bucket(field: str) -> dict:
        result: dict = {}
        for record in records:
            key = record[field]
            slot = result.setdefault(key, {"scenes": 0, "frames": 0})
            slot["scenes"] += 1
            slot["frames"] += record["frames"]
        return result

    def at_least(threshold: int) -> tuple[int, int]:
        selected = [
            record
            for record in records
            if record["object_velocity"] >= threshold
        ]
        return len(selected), sum(record["frames"] for record in selected)

    by_velocity = bucket("object_velocity")
    by_ego = bucket("ego_velocity")
    by_distance = bucket("distance")
    by_itr = bucket("itr")
    by_name = bucket("object_name")

    ge40_scenes, ge40_frames = at_least(40)
    ge50_scenes, ge50_frames = at_least(50)
    lt50_frames = sum(
        record["frames"] for record in records if record["object_velocity"] < 50
    )
    eq50_frames = sum(
        record["frames"] for record in records if record["object_velocity"] == 50
    )
    gt50_frames = sum(
        record["frames"] for record in records if record["object_velocity"] > 50
    )

    return {
        "records": records,
        "n_scenes": len(records),
        "n_frames": total_frames,
        "by_velocity": by_velocity,
        "by_ego": by_ego,
        "by_distance": by_distance,
        "by_itr": by_itr,
        "by_name": by_name,
        "ge40_scenes": ge40_scenes,
        "ge40_frames": ge40_frames,
        "ge50_scenes": ge50_scenes,
        "ge50_frames": ge50_frames,
        "lt50_frames": lt50_frames,
        "eq50_frames": eq50_frames,
        "gt50_frames": gt50_frames,
        "object_ne_ego": sum(
            1
            for record in records
            if record["object_velocity"] != record["ego_velocity"]
        ),
        "group_frames": {
            group: sum(
                record["frames"] for record in records if record["group"] == group
            )
            for group in GROUPS
        },
        "group_scenes": {
            group: sum(
                1 for record in records if record["group"] == group
            )
            for group in GROUPS
        },
    }


def beam_sample_scenes() -> list[Path]:
    selected: list[Path] = []
    for group in GROUPS:
        scenes = [
            scene
            for scene in sorted((DATASET / group).iterdir())
            if (scene / "velodyne").is_dir()
        ]
        selected.extend([scenes[0], scenes[len(scenes) // 2], scenes[-1]])
    return selected


def beam_stats(frames_per_scene: int = 10) -> dict:
    scenes = beam_sample_scenes()
    elevation_by_ring: dict[int, list[float]] = {ring: [] for ring in range(32)}
    azimuth_bins_by_ring: dict[int, list[int]] = {ring: [] for ring in range(32)}
    points_by_ring = np.zeros(32, dtype=np.int64)
    ring_union: set[int] = set()
    distinct_rings: list[int] = []
    distinct_intensities: list[int] = []
    intensity_min = float("inf")
    intensity_max = float("-inf")
    intensity_samples: list[float] = []
    non_integer_ring = 0
    non_integer_intensity = 0
    frames = 0

    for scene in scenes:
        for scan_id in evenly(frame_ids(scene), frames_per_scene):
            points = load_points(scene, scan_id).astype(np.float64)
            radial = np.hypot(points[:, 0], points[:, 1])
            elevation = np.degrees(
                np.arctan2(points[:, 2], radial)
            )
            ring = np.rint(points[:, 4]).astype(np.int64)
            valid = radial > 1e-6

            rings = np.unique(ring[valid])
            ring_union.update(int(value) for value in rings)
            distinct_rings.append(int(len(np.unique(points[:, 4]))))
            distinct_intensities.append(int(len(np.unique(points[:, 3]))))
            intensity_min = min(intensity_min, float(points[:, 3].min()))
            intensity_max = max(intensity_max, float(points[:, 3].max()))
            intensity_samples.append(points[:, 3])
            non_integer_ring += int(np.count_nonzero(points[:, 4] != ring))
            non_integer_intensity += int(
                np.count_nonzero(points[:, 3] != np.rint(points[:, 3]))
            )
            points_by_ring += np.bincount(
                ring[valid], minlength=32
            ).astype(np.int64)

            for value in rings:
                mask = valid & (ring == value)
                elevation_by_ring[int(value)].append(
                    float(np.median(elevation[mask]))
                )
                azimuth = np.degrees(
                    np.arctan2(points[mask, 1], points[mask, 0])
                )
                bins = np.floor((azimuth + 180.0) / 10.0).astype(np.int64)
                azimuth_bins_by_ring[int(value)].append(
                    int(len(np.unique(np.clip(bins, 0, 35))))
                )
            frames += 1

    intensity_all = np.concatenate(intensity_samples) if intensity_samples else np.zeros(0)
    per_ring = {}
    nominal_values = list(VLP32C_ELEVATION_BY_LASER_ID.values())
    hdl_values = list(HDL32E_ELEVATION_BY_LASER_ID.values())
    for ring in range(32):
        samples = elevation_by_ring[ring]
        if not samples:
            per_ring[ring] = {"n_frames": 0, "n_points": int(points_by_ring[ring])}
            continue
        observed = float(np.median(samples))
        nominal = VLP32C_ELEVATION_BY_LASER_ID[ring]
        nearest = min(nominal_values, key=lambda value: abs(observed - value))
        hdl_nominal = HDL32E_ELEVATION_BY_LASER_ID[ring]
        per_ring[ring] = {
            "n_frames": len(samples),
            "n_points": int(points_by_ring[ring]),
            "observed": observed,
            "p25": float(np.percentile(samples, 25)),
            "p75": float(np.percentile(samples, 75)),
            "az_bins_median": float(
                np.median(azimuth_bins_by_ring[ring])
            ),
            "nominal_same_id": nominal,
            "delta_same_id": observed - nominal,
            "nearest_nominal": nearest,
            "delta_nearest": observed - nearest,
            "nominal_hdl32e": hdl_nominal,
            "delta_hdl32e": observed - hdl_nominal,
        }

    present = [ring for ring in per_ring if per_ring[ring]["n_frames"] > 0]
    stable = [
        ring for ring in present if per_ring[ring]["n_frames"] >= max(30, frames // 2)
    ]

    def deviation(rings: list[int], key: str) -> tuple[float, float, int]:
        values = np.abs([per_ring[ring][key] for ring in rings])
        return (
            float(np.median(values)),
            float(values.max()),
            int(np.count_nonzero(values >= 0.5)),
        )

    same_all = deviation(present, "delta_same_id")
    same_stable = deviation(stable, "delta_same_id")
    nearest_all = deviation(present, "delta_nearest")
    hdl_all = deviation(present, "delta_hdl32e")

    return {
        "scenes": scenes,
        "frames": frames,
        "ring_union": sorted(ring_union),
        "distinct_rings": distinct_rings,
        "distinct_intensities": distinct_intensities,
        "intensity_min": intensity_min,
        "intensity_max": intensity_max,
        "intensity_p1": float(np.percentile(intensity_all, 1)),
        "intensity_p50": float(np.percentile(intensity_all, 50)),
        "intensity_p99": float(np.percentile(intensity_all, 99)),
        "non_integer_ring": non_integer_ring,
        "non_integer_intensity": non_integer_intensity,
        "points_by_ring": points_by_ring,
        "per_ring": per_ring,
        "present": present,
        "stable": stable,
        "same_all": same_all,
        "same_stable": same_stable,
        "nearest_all": nearest_all,
        "hdl_all": hdl_all,
    }
