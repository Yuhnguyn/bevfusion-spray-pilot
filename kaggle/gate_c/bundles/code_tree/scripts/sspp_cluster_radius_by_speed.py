#!/usr/bin/env python3
"""Đo phân bố **bán kính cụm** trên SSPP theo từng tốc độ (kiểm định bước 2 của A3).

**Câu hỏi kiểm định.** Mô hình hiện tại coi bán kính cụm là lognormal với
``σ = 0,8`` cho **mọi** tốc độ (số trung bình của Linnhoff Fig. 5). Nếu số điểm
mỗi cụm tỉ lệ tiết diện (``∝ r²``) thì ``σ_count = 2σ_r``, nên từ phân bố kích
thước cụm thật ta suy được ``σ_r`` cần có. Dự đoán đưa ra trước khi đo:
``σ_r ≈ 0,42`` ở 50 km/h và ``0,72–0,96`` ở 70–130 km/h. **Nếu đo ra σ_r(50) ≈ 0,8
thì dự đoán SAI.**

**Định nghĩa bán kính** đúng như Paper A §III-B: *"the radii r_cl are set to the
maximum distance of detections to the respective cluster center"* — tức với mỗi
cụm DBSCAN, lấy tâm là trung bình điểm, bán kính = max ‖p − tâm‖.

Recipe gom cụm giữ y nguyên bảng cụm/frame: chỉ ``label == 2``, DBSCAN trên
``(azimuth, elevation)``, ``eps = 0,7°``, ``minPts = 3``.

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/sspp_cluster_radius_by_speed.py
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from spray.semantic_stats import ANGULAR_EPS_DEG, MIN_PTS, cluster_angular
from sspp_cluster_table_folds import (
    CLASS_BY_GROUP,
    SceneInfo,
    fold_test_scenes,
    read_scene_inventory,
    sample_frame_indices,
)

NOISE_LABEL = 2
FRAMES_PER_SCENE = 15

# Dự đoán đưa ra TRƯỚC khi đo (từ sigma_meas = sqrt(2 ln(mean/p50)) và sigma_count
# = 2*sigma_r, hệ số truyền pipeline ~1,05). Ghi ở đây để không "diễn giải lại"
# sau khi thấy số.
PREDICTED_SIGMA_R = {50: 0.42, 70: 0.72, 100: 0.93, 130: 0.96}
PAPER_SIGMA_R = 0.8
PAPER_MEDIAN_R = 0.30


def scene_radii(scene: SceneInfo, root: Path) -> list[dict]:
    scene_dir = root / scene.rel_path
    scan_ids = sorted(path.stem for path in (scene_dir / "velodyne").glob("*.bin"))
    indices = sample_frame_indices(len(scan_ids), FRAMES_PER_SCENE)
    frames = []
    for index in indices:
        scan_id = scan_ids[index]
        points = np.fromfile(scene_dir / "velodyne" / f"{scan_id}.bin",
                             dtype=np.float32).reshape(-1, 5)
        labels = np.fromfile(scene_dir / "labels" / f"{scan_id}.label",
                             dtype=np.uint32)
        if labels.size != points.shape[0]:
            continue
        noise = points[labels == NOISE_LABEL][:, :3].astype(np.float64)
        if noise.shape[0] < MIN_PTS:
            continue
        cluster_ids = cluster_angular(noise, eps_deg=ANGULAR_EPS_DEG,
                                      min_pts=MIN_PTS)
        radii = []
        for label in range(int(cluster_ids.max()) + 1 if cluster_ids.size else 0):
            members = noise[cluster_ids == label]
            if members.shape[0] == 0:
                continue
            centre = members.mean(axis=0)
            radii.append(float(np.linalg.norm(members - centre, axis=1).max()))
        frames.append(radii)
    return frames


def summarise(values: list[float]) -> dict:
    if not values:
        return {}
    array = np.asarray(values, dtype=np.float64)
    positive = array[array > 0.0]
    log = np.log(positive) if positive.size else np.array([0.0])
    return {
        "n_cluster": int(array.size),
        "median_m": float(np.median(array)),
        "mu_ln": float(log.mean()),
        "sigma_ln": float(log.std(ddof=1)) if log.size > 1 else 0.0,
        "p90_m": float(np.percentile(array, 90)),
        "max_m": float(array.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/SemanticSprayDataset")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    root = Path(args.root)
    scenes = read_scene_inventory(root)
    print(f"scene: {len(scenes)}", flush=True)

    measured: dict[str, list[list[float]]] = {}
    for position, scene in enumerate(scenes, start=1):
        measured[scene.rel_path] = scene_radii(scene, root)
        if position % 40 == 0 or position == len(scenes):
            print(f"  [{position}/{len(scenes)}]", flush=True)

    by_path = {scene.rel_path: scene for scene in scenes}
    output: dict[str, dict] = {}
    print(f"\n{'v':>4} {'xe':>8} {'fold':>5} {'scene':>6} {'cụm':>6} "
          f"{'median r':>9} {'mu_ln':>6} {'sigma_ln':>9} {'p90':>6} {'max':>7}")
    for fold in (1, 2, 3):
        excluded = {scene.rel_path for scene in fold_test_scenes(scenes, fold)}
        cells: dict[tuple[str, float], list[float]] = defaultdict(list)
        scene_count: dict[tuple[str, float], int] = defaultdict(int)
        for path, frames in measured.items():
            if path in excluded:
                continue
            scene = by_path[path]
            vehicle = CLASS_BY_GROUP.get(scene.group)
            if vehicle is None:
                continue
            key = (vehicle, float(scene.speed_kmh))
            scene_count[key] += 1
            for radii in frames:
                cells[key].extend(radii)
        for (vehicle, speed), values in sorted(cells.items()):
            stats = summarise(values)
            if not stats:
                continue
            output[f"fold{fold}|{vehicle}|{speed:.0f}"] = {
                "fold": fold, "vehicle": vehicle, "speed_kmh": speed,
                "n_scene": scene_count[(vehicle, speed)], **stats,
            }
            print(f"{speed:>4.0f} {vehicle:>8} {fold:>5} {scene_count[(vehicle, speed)]:>6} "
                  f"{stats['n_cluster']:>6} {stats['median_m']:>9.2f} "
                  f"{stats['mu_ln']:>6.2f} {stats['sigma_ln']:>9.2f} "
                  f"{stats['p90_m']:>6.2f} {stats['max_m']:>7.2f}")

    print("\n=== KIỂM ĐỊNH: sigma_r đo được vs dự đoán (Crafter, gộp 3 fold) ===")
    print(f"{'v':>4} {'sigma_r do':>10} {'du doan':>8} {'paper':>6} "
          f"{'median r':>9} {'paper median':>13}")
    summary = {}
    for speed in (50, 70, 100, 130):
        rows = [row for key, row in output.items()
                if row["vehicle"] == "crafter" and row["speed_kmh"] == speed]
        if not rows:
            continue
        sigma = float(np.mean([row["sigma_ln"] for row in rows]))
        median = float(np.mean([row["median_m"] for row in rows]))
        summary[speed] = {"sigma_ln": sigma, "median_m": median}
        predicted = PREDICTED_SIGMA_R.get(speed)
        print(f"{speed:>4.0f} {sigma:>10.2f} {predicted if predicted else float('nan'):>8.2f} "
              f"{PAPER_SIGMA_R:>6.1f} {median:>9.2f} {PAPER_MEDIAN_R:>13.2f}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"rows": output, "summary": summary,
                        "predicted_sigma_r": PREDICTED_SIGMA_R,
                        "paper_sigma_r": PAPER_SIGMA_R,
                        "paper_median_r": PAPER_MEDIAN_R},
                       ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
