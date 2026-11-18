#!/usr/bin/env python3
"""Đuôi phân bố **điểm/cụm** của spray thật trên SSPP — đo theo fold, không leak.

Vì sao cần (plan §2 A3): sau A1, generator khớp **cụm/frame** (29,1 vs thật 28,5)
nhưng chỉ sinh **~140 điểm/frame** trong khi `label == 2` có **1 050–2 220**
⇒ thiếu 8–16× về khối lượng điểm. Muốn chốt đích (T1 dùng số paper / T2 theo
`label == 2` / T3 chỉ khớp cụm) thì phải biết **phân bố** điểm/cụm của dữ liệu
thật, không chỉ trung bình: nếu đuôi nặng (vài cụm khổng lồ giữ phần lớn điểm)
thì "tăng đều mọi cụm" là sai cách sửa.

Recipe đo giữ y nguyên bảng cụm/frame: chỉ `label == 2`, DBSCAN trên
`(azimuth, elevation)` `eps = 0,7°`, `minPts = 3`, elevation snap `0,333°`,
azimuth wrap — gọi thẳng :func:`spray.semantic_stats.cluster_angular`.

Không leak: mỗi scene được đo **một lần**, nhưng khi gộp cho fold `k` thì **loại
12 scene test của fold k** (dùng ``fold_test_scenes`` của
`scripts/sspp_cluster_table_folds.py`). Nhờ vậy mỗi đích rút ra từ fold nào cũng
không chứa scene mà fold đó sẽ chấm.

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/sspp_cluster_size_dist.py --md-out /tmp/sizes.md --json-out /tmp/sizes.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from spray.semantic_stats import ANGULAR_EPS_DEG, MIN_PTS, cluster_angular
from sspp_cluster_table_folds import (
    CLASS_BY_GROUP,
    SPEEDS_KMH,
    SceneInfo,
    fold_test_scenes,
    read_scene_inventory,
    sample_frame_indices,
)

NOISE_LABEL = 2
FRAMES_PER_SCENE = 15
BIG_CLUSTER_POINTS = 50  # ngưỡng "chuỗi lớn" đã dùng trong plume-root-cause.md
BOOTSTRAP_ROUNDS = 2000
SEED = 20261118


def measure_scene_sizes(scene: SceneInfo, root: Path) -> dict:
    """Trả về kích thước cụm (số điểm) của từng frame được sample."""
    scene_dir = root / scene.rel_path
    scan_ids = sorted(path.stem for path in (scene_dir / "velodyne").glob("*.bin"))
    indices = sample_frame_indices(len(scan_ids), FRAMES_PER_SCENE)
    frames = []
    dropped = 0
    for index in indices:
        scan_id = scan_ids[index]
        points = np.fromfile(scene_dir / "velodyne" / f"{scan_id}.bin",
                             dtype=np.float32).reshape(-1, 5)
        labels = np.fromfile(scene_dir / "labels" / f"{scan_id}.label",
                             dtype=np.uint32)
        if labels.size != points.shape[0]:
            dropped += 1
            continue
        noise = points[labels == NOISE_LABEL][:, :3].astype(np.float64)
        if noise.shape[0] < MIN_PTS:
            sizes: list[int] = []
        else:
            cluster_ids = cluster_angular(noise, eps_deg=ANGULAR_EPS_DEG,
                                          min_pts=MIN_PTS)
            valid = cluster_ids[cluster_ids >= 0]
            sizes = [int(value) for value in np.bincount(valid)] if valid.size else []
        frames.append({"scan_id": scan_id, "sizes": sizes})
    return {"frames": frames, "n_frame_dropped": dropped}


def summarise(size_lists: list[list[int]]) -> dict:
    """Gộp danh sách kích thước cụm của nhiều frame thành thống kê."""
    flat = [size for sizes in size_lists for size in sizes]
    totals = [sum(sizes) for sizes in size_lists]
    if not flat:
        return {"n_frame": len(size_lists), "n_cluster": 0, "points_per_frame": 0.0}
    array = np.asarray(flat, dtype=np.int64)
    big = array[array >= BIG_CLUSTER_POINTS]
    return {
        "n_frame": len(size_lists),
        "n_cluster": int(array.size),
        "clusters_per_frame": float(array.size) / max(len(size_lists), 1),
        "points_per_frame": float(np.mean(totals)) if totals else 0.0,
        "points_per_cluster_median": float(np.median(array)),
        "points_per_cluster_mean": float(array.mean()),
        "points_per_cluster_p95": float(np.percentile(array, 95)),
        "points_per_cluster_max": int(array.max()),
        "clusters_ge_big": int(big.size),
        "share_clusters_ge_big": float(big.size) / array.size,
        "share_points_in_big": float(big.sum()) / array.sum(),
    }


def bootstrap_mean_ci(per_scene: dict[str, np.ndarray], rng: np.random.Generator,
                      rounds: int = BOOTSTRAP_ROUNDS) -> tuple[float, float]:
    """CI95 percentile của mean điểm/cụm, resample ở mức **scene**."""
    keys = sorted(per_scene)
    if len(keys) < 2:
        return (float("nan"), float("nan"))
    stacks = [per_scene[key] for key in keys]
    means = np.empty(rounds)
    for index in range(rounds):
        pick = rng.integers(0, len(keys), size=len(keys))
        values = np.concatenate([stacks[choice] for choice in pick])
        means[index] = values.mean() if values.size else np.nan
    return (float(np.nanpercentile(means, 2.5)), float(np.nanpercentile(means, 97.5)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/SemanticSprayDataset")
    parser.add_argument("--md-out", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--limit-scenes", type=int, default=0)
    args = parser.parse_args()

    root = Path(args.root)
    scenes = read_scene_inventory(root)
    if args.limit_scenes:
        scenes = scenes[: args.limit_scenes]
    print(f"scene: {len(scenes)}", flush=True)

    measured: dict[str, dict] = {}
    for position, scene in enumerate(scenes, start=1):
        measured[scene.rel_path] = measure_scene_sizes(scene, root)
        if position % 25 == 0 or position == len(scenes):
            print(f"  [{position}/{len(scenes)}] {scene.rel_path}", flush=True)

    by_path = {scene.rel_path: scene for scene in scenes}
    rows: dict[str, dict] = {}
    for fold in (1, 2, 3):
        excluded = {scene.rel_path for scene in fold_test_scenes(scenes, fold)}
        cells: dict[tuple[str, float], dict[str, list[np.ndarray]]] = defaultdict(dict)
        for path, payload in measured.items():
            scene = by_path[path]
            vehicle = CLASS_BY_GROUP.get(scene.group)
            if vehicle is None:
                continue
            for frame in payload["frames"]:
                sizes = np.asarray(frame["sizes"], dtype=np.int64)
                key = (vehicle, float(scene.speed_kmh))
                if path in excluded:
                    continue
                cells[key].setdefault(path, []).append(sizes)
        rng = np.random.default_rng(SEED + fold)
        for key, per_scene_lists in sorted(cells.items()):
            vehicle, speed = key
            frame_lists = [sizes for lists in per_scene_lists.values() for sizes in lists]
            per_scene_arrays = {
                path: np.concatenate([sizes for sizes in lists if sizes.size])
                for path, lists in per_scene_lists.items()
                if any(sizes.size for sizes in lists)
            }
            stats = summarise(frame_lists)
            low, high = bootstrap_mean_ci(per_scene_arrays, rng)
            rows[f"fold{fold}|{vehicle}|{speed:.0f}"] = {
                "fold": fold,
                "vehicle": vehicle,
                "speed_kmh": speed,
                "n_scene": len(per_scene_lists),
                **stats,
                "points_per_cluster_mean_ci95": [low, high],
            }

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"rows": rows, "recipe": {
                "noise_label": NOISE_LABEL,
                "eps_deg": ANGULAR_EPS_DEG,
                "min_pts": MIN_PTS,
                "frames_per_scene": FRAMES_PER_SCENE,
                "big_cluster_points": BIG_CLUSTER_POINTS,
            }}, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        "# Đuôi phân bố điểm/cụm trên SSPP (đo theo fold, không leak)",
        "",
        "| fold | xe | km/h | scene | frame | cụm/frame | điểm/frame | điểm/cụm p50 | mean [CI95] | p95 | max | cụm ≥50 đ | % điểm trong cụm ≥50 đ |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for key, row in sorted(rows.items(), key=lambda item: (
            item[1]["fold"], item[1]["vehicle"], item[1]["speed_kmh"])):
        low, high = row["points_per_cluster_mean_ci95"]
        lines.append(
            f"| {row['fold']} | {row['vehicle']} | {row['speed_kmh']:.0f} | "
            f"{row['n_scene']} | {row['n_frame']} | {row['clusters_per_frame']:.2f} | "
            f"{row['points_per_frame']:.0f} | {row['points_per_cluster_median']:.0f} | "
            f"{row['points_per_cluster_mean']:.1f} [{low:.1f}; {high:.1f}] | "
            f"{row['points_per_cluster_p95']:.0f} | {row['points_per_cluster_max']} | "
            f"{row['clusters_ge_big']} | {100 * row['share_points_in_big']:.1f} % |"
        )
    text = "\n".join(lines) + "\n"
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
