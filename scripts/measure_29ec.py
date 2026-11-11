#!/usr/bin/env python3
"""Ticket 29e-c: measure real vs generated spray **by range bucket**.

Step 1 of the ticket: print the table that decides what to fix, *before* any
generator change. The recipe matches ``spray.semantic_stats`` (DBSCAN in the
discretized azimuth/elevation plane, ``eps = 0.7 deg``, ``minPts = 3``) so the
numbers are comparable with the ``cal`` measurements in
``docs/measurements/semantic-spray-clusters-by-speed.md``.

For every cell (vehicle class x speed) three scenes are picked evenly from the
release and 30 frames evenly from each scene. Real points are label 2; generated
points are the ray-cast detections returned by the wired pipeline
(``inject_plume_stateful`` -> ``raycast_frame``), which is what
``PlumeTransform`` runs.

    # Step 1: the bucket table only (no code change yet)
    /opt/anaconda3/bin/python scripts/measure_29ec.py

    # Step 3: acceptance measurements A1-A7
    /opt/anaconda3/bin/python scripts/measure_29ec.py --acceptance

Only numpy + stdlib; no GPU and no training.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import time
from pathlib import Path

import numpy as np
import yaml

from spray.beam_model import load_beam_table
from spray.plume import (
    PlumeConfig,
    inject_plume_stateful,
    visible_cluster_count_for_speed,
)
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.semantic_stats import cluster_angular

DATASET = Path("data/SemanticSprayDataset")
DOC = Path("docs/measurements/29ec-range-buckets.md")
SPLIT = Path("spray/config/semantic_spray_split.yaml")
ROAD_Z_M = -0.411
WFH_MM = 1.0
DT_S = 0.1
SPEEDS_KMH = (100.0, 130.0)
LADDER_KMH = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)
GROUPS = {
    "Crafter_dynamic": ("crafter", (6.8268, 2.4183, 2.6206)),
    "Golf_dynamic": ("golf", (4.2468, 2.0167, 1.4981)),
}
BUCKETS = ((0.0, 15.0), (15.0, 25.0), (25.0, 40.0), (40.0, np.inf))
CAL_CLUSTERS_PER_FRAME = {
    "crafter": (4.18, 11.31, 17.42, 22.02, 20.69, 29.24, 28.49, 17.58, 17.69),
    "golf": (3.62, 8.84, 11.36, 12.87, 10.51, 18.07, 16.69, 15.27, 16.64),
}

# Snapshot captured before any generator change (ticket step 1). Kept literal so
# the document keeps the diagnosis even after the code is fixed.
BEFORE_TABLE = """| lớp | km/h | dải (m) | real_pts | gen_pts | real_cl | gen_cl | real_p50 | gen_p50 | gen_raw_det | gen_dropped |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 100 | [0,15) | 78304 | 18822 | 1839 | 1013 | 6 | 5 | 18822 | 3090 |
| Crafter_dynamic | 100 | [15,25) | 9380 | 7986 | 116 | 231 | 7 | 5 | 7986 | 601 |
| Crafter_dynamic | 100 | [25,40) | 445 | 569 | 6 | 14 | 6 | 4 | 569 | 124 |
| Crafter_dynamic | 100 | [40+ | 4 | 12 | 0 | 1 | nan | 3 | 12 | 6 |
| Crafter_dynamic | 130 | [0,15) | 59996 | 13866 | 1271 | 801 | 7 | 6 | 13866 | 1839 |
| Crafter_dynamic | 130 | [15,25) | 6493 | 4945 | 74 | 233 | 6 | 10 | 4945 | 391 |
| Crafter_dynamic | 130 | [25,40) | 417 | 737 | 6 | 41 | 6 | 6 | 737 | 100 |
| Crafter_dynamic | 130 | [40+ | 3 | 113 | 0 | 8 | nan | 4 | 113 | 16 |
| Golf_dynamic | 100 | [0,15) | 35883 | 36378 | 1251 | 2227 | 5 | 5 | 36378 | 6694 |
| Golf_dynamic | 100 | [15,25) | 3781 | 7369 | 62 | 131 | 6 | 6 | 7369 | 345 |
| Golf_dynamic | 100 | [25,40) | 106 | 618 | 0 | 6 | nan | 4 | 618 | 45 |
| Golf_dynamic | 100 | [40+ | 3 | 1 | 0 | 0 | nan | nan | 1 | 1 |
| Golf_dynamic | 130 | [0,15) | 43607 | 48770 | 1271 | 2251 | 6 | 6 | 48770 | 5097 |
| Golf_dynamic | 130 | [15,25) | 6643 | 7081 | 71 | 187 | 5 | 6 | 7081 | 291 |
| Golf_dynamic | 130 | [25,40) | 534 | 848 | 8 | 40 | 12 | 6 | 848 | 86 |
| Golf_dynamic | 130 | [40+ | 4 | 88 | 0 | 1 | nan | 4 | 88 | 16 |"""


def cal_scenes() -> set[str]:
    """Scene rel paths in the frozen ``cal`` role (ticket 29d)."""
    document = yaml.safe_load(SPLIT.read_text(encoding="utf-8"))
    return {
        str(rel_path)
        for cell in document.get("cells") or []
        for rel_path in ((cell.get("scenes") or {}).get("cal") or [])
    }


def scenes_for(group: str, speed_kmh: float) -> list[Path]:
    measured_on = cal_scenes()
    found: list[Path] = []
    for metadata in sorted((DATASET / group).glob("*/metadata.txt")):
        with metadata.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows or abs(float(rows[0]["object_velocity"]) - speed_kmh) > 1e-6:
            continue
        rel = metadata.parent.relative_to(DATASET).as_posix()
        if rel not in measured_on:
            continue
        found.append(metadata.parent)
    return found


def evenly(items: list, count: int) -> list:
    if count <= 0 or count >= len(items):
        return list(items)
    picks = np.linspace(0, len(items) - 1, count).round().astype(int)
    return [items[index] for index in sorted(set(picks.tolist()))]


def _box_from_labels(scene: Path, frame_stem: str, speed_mps: float):
    path = scene / "object_labels" / "lidar" / f"{frame_stem}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    instances = payload[0]["instances"]
    if not instances:
        return None
    contour = instances[0]["contour"]
    center = contour["center3D"]
    size = contour["size3D"]
    return np.array(
        [
            [
                float(center["x"]),
                float(center["y"]),
                float(center["z"]),
                float(size["y"]),
                float(size["x"]),
                float(size["z"]),
                float(contour["rotation3D"]["z"]),
                speed_mps,
                0.0,
            ]
        ],
        dtype=np.float32,
    )


def scene_distance_m(scene: Path) -> float:
    with (scene / "metadata.txt").open() as handle:
        rows = list(csv.DictReader(handle))
    return float(rows[0]["distance_to_object"])


def fallback_box(
    dims: tuple[float, float, float], speed_mps: float, distance_m: float
) -> np.ndarray:
    width, length, height = dims[1], dims[0], dims[2]
    return np.array(
        [
            [
                distance_m,
                0.0,
                ROAD_Z_M + height / 2.0,
                width,
                length,
                height,
                0.0,
                speed_mps,
                0.0,
            ]
        ],
        dtype=np.float32,
    )


def _cluster_centers(
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    labels = cluster_angular(points)
    centers: list[float] = []
    sizes: list[int] = []
    for cluster_id in np.unique(labels):
        if cluster_id < 0:
            continue
        members = points[labels == cluster_id]
        centers.append(float(np.linalg.norm(members[:, :3].mean(axis=0))))
        sizes.append(int(members.shape[0]))
    return np.asarray(centers), np.asarray(sizes, dtype=np.int64)


def _bucket_index(values: np.ndarray) -> np.ndarray:
    index = np.full(values.shape, len(BUCKETS) - 1, dtype=np.int64)
    for slot, (lo, hi) in enumerate(BUCKETS):
        inside = (values >= lo) & (values < hi)
        index[inside] = slot
    return index


def _p50(values: np.ndarray) -> float:
    return float(np.median(values)) if values.size else float("nan")


def measure_cell(
    group: str,
    speed_kmh: float,
    *,
    scene_count: int = 3,
    frames_per_scene: int = 30,
) -> dict:
    vehicle_class, dims = GROUPS[group]
    speed_mps = speed_kmh / 3.6
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)

    real_ranges: list[np.ndarray] = []
    real_centers: list[np.ndarray] = []
    real_sizes: list[np.ndarray] = []
    gen_ranges: list[np.ndarray] = []
    gen_centers: list[np.ndarray] = []
    gen_sizes: list[np.ndarray] = []
    gen_noise: list[np.ndarray] = []
    det_z: list[np.ndarray] = []
    det_y: list[np.ndarray] = []
    det_per_frame: list[int] = []
    alive_per_frame: list[int] = []
    capped: list[int] = []
    latency_ms: list[float] = []

    state = PlumeState()
    table = load_beam_table()
    config = PlumeConfig()
    for scene in scenes:
        frames = evenly(
            sorted((scene / "velodyne").glob("*.bin")), frames_per_scene
        )
        for frame_index, path in enumerate(frames):
            points = np.fromfile(path, dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(
                scene / "labels" / f"{path.stem}.label", dtype=np.uint32
            )
            spray = points[labels == 2]
            if spray.shape[0]:
                real_ranges.append(np.linalg.norm(spray[:, :3], axis=1))
                centers, sizes = _cluster_centers(spray)
                real_centers.append(centers)
                real_sizes.append(sizes)
            else:
                real_ranges.append(np.zeros(0))
                real_centers.append(np.zeros(0))
                real_sizes.append(np.zeros(0, dtype=np.int64))

            box = _box_from_labels(scene, path.stem, speed_mps)
            if box is None:
                box = fallback_box(dims, speed_mps, scene_distance_m(scene))

            context = PlumeContext(
                scene_token=f"{group}/{speed_kmh:g}/{scene.name}",
                frame_index=frame_index,
                epoch=0,
                sensor_origin=np.zeros(3, dtype=np.float64),
                ego_speed_mps=speed_mps,
                object_speed_mps=speed_mps,
                wfh_mm=WFH_MM,
                road_z_m=ROAD_Z_M,
                object_velocity_ego_mps=np.zeros(3, dtype=np.float64),
            )
            seed = seed_for(context.scene_token, frame_index, 0, 0)
            with contextlib.redirect_stdout(io.StringIO()):
                result = inject_plume_stateful(
                    points,
                    box,
                    context,
                    state,
                    seed=seed,
                    token=context.scene_token,
                    config=config,
                    dt=DT_S,
                    vehicle_class=vehicle_class,
                )
                started = time.perf_counter()
                ray = raycast_frame(
                    result.points_clean,
                    state.all_alive(),
                    table=table,
                    road_z_m=ROAD_Z_M,
                    rng=np.random.default_rng(seed),
                    capped=result.stats.capped,
                    vehicle_class=vehicle_class,
                )
            latency_ms.append((time.perf_counter() - started) * 1000.0)
            capped.append(int(result.stats.capped))
            alive_per_frame.append(int(state.counters.alive))
            detections = np.asarray(ray.detections, dtype=np.float32)
            det_per_frame.append(int(detections.shape[0]))
            if detections.shape[0] == 0:
                gen_ranges.append(np.zeros(0))
                gen_centers.append(np.zeros(0))
                gen_sizes.append(np.zeros(0, dtype=np.int64))
                gen_noise.append(np.zeros((0, 3)))
                continue
            gen_ranges.append(np.linalg.norm(detections[:, :3], axis=1))
            det_z.append(detections[:, 2].astype(np.float64))
            det_y.append(np.abs(detections[:, 1].astype(np.float64)))
            centers, sizes = _cluster_centers(detections)
            gen_centers.append(centers)
            gen_sizes.append(sizes)
            gen_noise.append(
                detections[cluster_angular(detections) < 0, :3].astype(np.float64)
            )

    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "real_ranges": real_ranges,
        "real_centers": real_centers,
        "real_sizes": real_sizes,
        "gen_ranges": gen_ranges,
        "gen_centers": gen_centers,
        "gen_sizes": gen_sizes,
        "gen_noise": gen_noise,
        "det_z": np.concatenate(det_z) if det_z else np.zeros(0),
        "det_y": np.concatenate(det_y) if det_y else np.zeros(0),
        "det_per_frame": np.asarray(det_per_frame, dtype=np.float64),
        "alive_per_frame": np.asarray(alive_per_frame, dtype=np.float64),
        "capped": int(np.max(capped)) if capped else 0,
        "latency_ms": np.asarray(latency_ms, dtype=np.float64),
        "frames": len(real_ranges),
    }


def _bucket_rows(cell: dict) -> list[dict]:
    real_r = np.concatenate(cell["real_ranges"]) if cell["real_ranges"] else np.zeros(0)
    real_c = np.concatenate(cell["real_centers"]) if cell["real_centers"] else np.zeros(0)
    real_s = np.concatenate(cell["real_sizes"]) if cell["real_sizes"] else np.zeros(0, np.int64)
    gen_r = np.concatenate(cell["gen_ranges"]) if cell["gen_ranges"] else np.zeros(0)
    gen_c = np.concatenate(cell["gen_centers"]) if cell["gen_centers"] else np.zeros(0)
    gen_s = np.concatenate(cell["gen_sizes"]) if cell["gen_sizes"] else np.zeros(0, np.int64)
    noise = np.concatenate(cell["gen_noise"]) if cell["gen_noise"] else np.zeros((0, 3))

    real_idx = _bucket_index(real_r)
    real_c_idx = _bucket_index(real_c)
    gen_idx = _bucket_index(gen_r)
    gen_c_idx = _bucket_index(gen_c)
    noise_idx = (
        _bucket_index(np.linalg.norm(noise, axis=1)) if noise.size else np.zeros(0, np.int64)
    )

    rows = []
    for slot, (lo, hi) in enumerate(BUCKETS):
        real_mask = real_idx == slot
        gen_mask = gen_idx == slot
        real_cl_mask = real_c_idx == slot
        gen_cl_mask = gen_c_idx == slot
        rows.append(
            {
                "bucket": f"[{lo:g},{hi:g})" if np.isfinite(hi) else f"[{lo:g}+",
                "real_pts": int(real_mask.sum()),
                "gen_pts": int(gen_mask.sum()),
                "real_cl": int(real_cl_mask.sum()),
                "gen_cl": int(gen_cl_mask.sum()),
                "real_p50": _p50(real_s[real_cl_mask]),
                "gen_p50": _p50(gen_s[gen_cl_mask]),
                "gen_raw_det": int(gen_mask.sum()),
                "gen_dropped": int((noise_idx == slot).sum()),
            }
        )
    return rows


def render_bucket_table(cells: list[dict]) -> str:
    lines = [
        "| lớp | km/h | dải (m) | real_pts | gen_pts | real_cl | gen_cl | real_p50 | gen_p50 | gen_raw_det | gen_dropped |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        for row in _bucket_rows(cell):
            lines.append(
                f"| {cell['group']} | {cell['speed']:g} | {row['bucket']} | "
                f"{row['real_pts']} | {row['gen_pts']} | {row['real_cl']} | "
                f"{row['gen_cl']} | {row['real_p50']:.0f} | {row['gen_p50']:.0f} | "
                f"{row['gen_raw_det']} | {row['gen_dropped']} |"
            )
    return "\n".join(lines)


def render_acceptance(cells: list[dict], ladder: list[dict]) -> str:
    lines = [
        "### A1 — cụm/frame của mô hình (`visible = round(rate·K)` tại wfh_ref), 9 mốc × 2 lớp",
        "",
        "Đại lượng đích của bảng `cal` (PM 29c: 'đo qua `visible_cluster_count_for_speed`').",
        "Số cụm **sống tức thời** là đại lượng khác (cửa sổ 4T), in ở hàng dưới để đối chiếu.",
        "",
    ]
    lines.append(
        "| lớp | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for vehicle_class in ("crafter", "golf"):
        values = [
            str(visible_cluster_count_for_speed(speed, vehicle_class=vehicle_class))
            for speed in LADDER_KMH
        ]
        table = " | ".join(f"{value:.2f}" for value in CAL_CLUSTERS_PER_FRAME[vehicle_class])
        lines.append(f"| {vehicle_class} mô hình | " + " | ".join(values) + " |")
        lines.append(f"| {vehicle_class} bảng | {table} |")
        alive = []
        for speed in LADDER_KMH:
            cell = next(
                item
                for item in ladder
                if item["speed"] == speed
                and item["group"].lower().startswith(vehicle_class)
            )
            tail = cell["alive_per_frame"][-20:]
            alive.append(f"{np.median(tail):.0f}" if tail.size else "-")
        lines.append(f"| {vehicle_class} sống đo | " + " | ".join(alive) + " |")
    lines += ["", "### A2-A7 — điểm/frame, p50, chiều cao, |y|, latency, capped", ""]
    lines.append(
        "| lớp | km/h | điểm/frame | p50/cụm | h p5/med/p95 (m) | p95\\|y\\| (m) | latency med (ms) | capped |"
    )
    lines.append("|---|---:|---:|---:|---|---:|---:|---:|")
    for cell in ladder:
        rows = _bucket_rows(cell)
        gen_r = np.concatenate(cell["gen_ranges"]) if cell["gen_ranges"] else np.zeros(0)
        gen_s = np.concatenate(cell["gen_sizes"]) if cell["gen_sizes"] else np.zeros(0, np.int64)
        heights = cell["det_z"] - ROAD_Z_M if cell["det_z"].size else np.zeros(0)
        p5, med, p95 = (
            np.percentile(heights, [5, 50, 95]) if heights.size else (np.nan,) * 3
        )
        p95_y = float(np.percentile(cell["det_y"], 95)) if cell["det_y"].size else float("nan")
        tail = cell["det_per_frame"][-20:]
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | "
            f"{np.median(tail) if tail.size else float('nan'):.0f} | {_p50(gen_s):.0f} | "
            f"{p5:.3f} / {med:.3f} / {p95:.3f} | {p95_y:.3f} | "
            f"{np.median(cell['latency_ms']):.1f} | {cell['capped']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acceptance",
        action="store_true",
        help="also run the 9-speed ladder and print A1-A7",
    )
    args = parser.parse_args()

    cells = [
        measure_cell(group, speed)
        for group in GROUPS
        for speed in SPEEDS_KMH
    ]
    table = render_bucket_table(cells)
    body = [
        "# 29e-c — plume sinh vs thật theo dải cự ly",
        "",
        "Sinh bằng `scripts/measure_29ec.py`, đúng thứ tự bắt buộc của ticket: **bảng trước khi",
        "sửa code sinh**, rồi mới sửa và đo lại.",
        f"3 scene × 30 frame mỗi ô, `wfh_ref = {WFH_MM:g} mm`, DBSCAN 0,7°/minPts=3,",
        "real = điểm label 2; gen = detection ray-cast của đường stateful đã nối (`PlumeTransform`).",
        "",
        "## Bước 1 — trước khi sửa code sinh",
        "",
        BEFORE_TABLE,
        "",
        "## Bước 3 — sau một vòng sửa",
        "",
        table,
        "",
    ]
    if args.acceptance:
        ladder = [
            measure_cell(group, speed, scene_count=1, frames_per_scene=60)
            for group in GROUPS
            for speed in LADDER_KMH
        ]
        body += ["## Bước 3 — nghiệm thu", "", render_acceptance(cells, ladder), ""]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(body), encoding="utf-8")
    print(table)
    if args.acceptance:
        print()
        print(render_acceptance(cells, ladder))
        print()
        print(f"Đã ghi {DOC}")


if __name__ == "__main__":
    main()
