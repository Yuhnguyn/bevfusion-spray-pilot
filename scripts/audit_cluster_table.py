#!/usr/bin/env python3
"""Audit bảng `_CLUSTER_VISIBLE_BY_SPEED` trên split `train` của SSPP.

Đo lại cụm/frame bằng đúng toán tử của bảng gốc — DBSCAN trên mặt phẳng
`(azimuth, elevation)`, `eps = 0,7°`, `minPts = 3`
(`spray.semantic_stats.cluster_angular`) — nhưng KHÔNG gộp frame thành một số:

* bảng A: từng (lớp, tốc độ, scene) một dòng, để thấy scene nào kéo đường cong;
* bảng B: median per-scene rồi median của các scene (median-of-medians), thay cho
  median gộp frame, kèm CV giữa các scene và độ lệch so với bảng đang dùng;
* bảng C: tách theo bin cự ly 3D của box (10…50 m) để biết có đủ dữ liệu so với
  Fig. 11b của paper hay không.

Phạm vi: `data/sspp_infos_train.pkl` (16 scene, 1.124 frame, tốc độ 60/80/100/120).
Chỉ frame có box với vận tốc > 45 km/h. Không sửa generator, không sửa bảng.

Chạy::

    CONDA_NO_PLUGINS=true python scripts/audit_cluster_table.py

Marker: `AUDIT_TABLE_A`, `AUDIT_TABLE_B`, `AUDIT_TABLE_C`, `AUDIT_CLUSTER_OK`.
"""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from spray.plume import _CLUSTER_VISIBLE_BY_SPEED  # noqa: E402
from spray.semantic_stats import cluster_angular  # noqa: E402

ROOT = REPO / "data" / "SemanticSprayDataset"
INFOS = REPO / "data" / "sspp_infos_train.pkl"

MIN_SPEED_KMH = 45.0
POSE_BINS_M = (10, 20, 30, 40, 50)
MIN_FRAMES_FOR_CLAIM = 30


@dataclass(frozen=True)
class Frame:
    group: str
    speed_kmh: int
    scene: str
    scan_id: str
    n_clusters: int
    n_points: int
    speed_actual_kmh: float
    distance_m: float


def speed_bin(speed_kmh: float) -> int:
    return int(np.floor(speed_kmh / 10.0 + 0.5) * 10)


def range_bin(distance_m: float) -> int:
    return int(np.floor(distance_m / 10.0 + 0.5) * 10)


def short_scene(scene: str) -> str:
    group, name = scene.split("/")
    prefix = "C" if group.startswith("Crafter") else "G"
    return f"{prefix}{name[:4]}"


def measure(info: dict) -> tuple[Frame | None, str]:
    boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
    if len(boxes) == 0:
        return None, "no_box"
    vx, vy = float(boxes[0, 7]), float(boxes[0, 8])
    if not np.isfinite(vx) or not np.isfinite(vy):
        return None, "no_velocity"
    speed_kmh = float(np.hypot(vx, vy)) * 3.6
    if speed_kmh <= MIN_SPEED_KMH:
        return None, "low_speed"

    scene = info["token"].rsplit("/", 1)[0]
    points = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
    labels = np.fromfile(
        ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
    )
    noise = points[labels == 2][:, :3]
    if len(noise) >= 3:
        cluster_labels = cluster_angular(noise, eps_deg=0.7, min_pts=3)
        n_clusters = int(len(np.unique(cluster_labels[cluster_labels >= 0])))
    else:
        n_clusters = 0

    return (
        Frame(
            group=info["group"].replace("_dynamic", "").lower(),
            speed_kmh=speed_bin(speed_kmh),
            scene=short_scene(scene),
            scan_id=info["scan_id"],
            n_clusters=n_clusters,
            n_points=int(len(noise)),
            speed_actual_kmh=speed_kmh,
            distance_m=float(np.linalg.norm(boxes[0, :3])),
        ),
        "",
    )


def _p(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def _median(values: list[float]) -> float:
    return float(np.median(np.asarray(values, dtype=np.float64)))


def print_table_a(frames: list[Frame]) -> None:
    by_scene: dict[tuple[str, int, str], list[Frame]] = defaultdict(list)
    for frame in frames:
        by_scene[(frame.group, frame.speed_kmh, frame.scene)].append(frame)

    print("AUDIT_TABLE_A")
    print(
        "group    kmh  scene  n_frame  c_p25  c_p50  c_p75  p_p50"
    )
    for key in sorted(by_scene):
        group, kmh, scene = key
        rows = by_scene[key]
        clusters = [float(r.n_clusters) for r in rows]
        points = [float(r.n_points) for r in rows]
        print(
            f"{group:<8} {kmh:4d}  {scene:<5}  {len(rows):7d}  "
            f"{_p(clusters, 25):5.1f}  {_median(clusters):5.1f}  "
            f"{_p(clusters, 75):5.1f}  {_median(points):5.0f}"
        )


def print_table_b(frames: list[Frame]) -> None:
    by_cell: dict[tuple[str, int], dict[str, list[Frame]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for frame in frames:
        by_cell[(frame.group, frame.speed_kmh)][frame.scene].append(frame)

    print()
    print("AUDIT_TABLE_B")
    print(
        "group    kmh  n_scene  med_of_med     min     max   scene_CV  "
        "frame_CV  table  delta_pct"
    )
    for key in sorted(by_cell):
        group, kmh = key
        per_scene = {
            scene: _median([float(r.n_clusters) for r in rows])
            for scene, rows in by_cell[key].items()
        }
        scene_medians = list(per_scene.values())
        med = _median(scene_medians)
        table = dict(_CLUSTER_VISIBLE_BY_SPEED[group]).get(float(kmh))
        delta = (
            (med - table) / table * 100.0
            if table is not None and table != 0.0
            else float("nan")
        )
        mean = float(np.mean(scene_medians))
        cv = float(np.std(scene_medians) / mean) if mean > 0.0 else float("nan")
        frame_values = np.asarray(
            [float(r.n_clusters) for rows in by_cell[key].values() for r in rows],
            dtype=np.float64,
        )
        frame_mean = float(frame_values.mean())
        frame_cv = (
            float(frame_values.std() / frame_mean) if frame_mean > 0.0 else float("nan")
        )
        print(
            f"{group:<8} {kmh:4d}  {len(scene_medians):7d}  {med:10.2f}  "
            f"{min(scene_medians):7.1f}  {max(scene_medians):7.1f}  "
            f"{cv:8.2f}  {frame_cv:8.2f}  "
            f"{(table if table is not None else float('nan')):5.2f}  "
            f"{delta:+9.1f}"
        )


def print_table_c(frames: list[Frame]) -> None:
    by_range: dict[tuple[str, int], list[Frame]] = defaultdict(list)
    for frame in frames:
        by_range[(frame.group, range_bin(frame.distance_m))].append(frame)

    print()
    print("AUDIT_TABLE_C")
    print("group    range_m  n_frame  c_p50  p_p50  v_p50  flag")
    for group in ("crafter", "golf"):
        for bin_m in POSE_BINS_M:
            rows = by_range.get((group, bin_m), [])
            if len(rows) < MIN_FRAMES_FOR_CLAIM:
                print(
                    f"{group:<8} {bin_m:7d}  {len(rows):7d}  "
                    "   n/a    n/a    n/a  khong-du-du-lieu"
                )
                continue
            print(
                f"{group:<8} {bin_m:7d}  {len(rows):7d}  "
                f"{_median([float(r.n_clusters) for r in rows]):5.1f}  "
                f"{_median([float(r.n_points) for r in rows]):5.0f}  "
                f"{_median([r.speed_actual_kmh for r in rows]):5.0f}  ok"
            )


def main() -> int:
    with INFOS.open("rb") as handle:
        infos: list[dict] = pickle.load(handle)

    frames: list[Frame] = []
    skipped: dict[str, int] = defaultdict(int)
    for number, info in enumerate(infos, start=1):
        frame, reason = measure(info)
        if frame is None:
            skipped[reason] += 1
            continue
        frames.append(frame)
        if number % 50 == 0:
            print(
                f"\rframes {number}/{len(infos)}  kept {len(frames)}",
                end="",
                file=sys.stderr,
                flush=True,
            )
    print("\r", end="", file=sys.stderr)

    scenes = sorted({frame.scene for frame in frames})
    print(
        f"AUDIT_SCOPE split=train infos={len(infos)} frames={len(frames)} "
        f"scenes={len(scenes)} min_speed_kmh={MIN_SPEED_KMH:g} "
        f"dbscan=eps0.7deg/minPts3 range_bins={','.join(map(str, POSE_BINS_M))}"
    )
    print(
        "AUDIT_NOTES "
        + (
            "skipped=none"
            if not skipped
            else " ".join(f"{reason}={count}" for reason, count in sorted(skipped.items()))
        )
        + f" sparse_noise_lt3={sum(1 for f in frames if f.n_points < 3)}"
    )
    print()

    print_table_a(frames)
    print_table_b(frames)
    print_table_c(frames)

    print()
    print(f"AUDIT_CLUSTER_OK scenes={len(scenes)} frames={len(frames)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
