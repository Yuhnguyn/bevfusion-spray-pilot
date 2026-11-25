"""Kiểm chứng 2 nghi vấn về phép đo CDF vừa commit (2026-11-25).

N1: vế THẬT có bao gồm điểm gần ego (along ~ 0) không? Nếu có thì CDF10 = 71 %
    là artifact của mask (depth = rear - along, nên điểm sát ego vẫn có
    depth ~ rear = 41 m, lọt cửa sổ [0,60)).
N2: "n_ahead_of_rear" của vế THẬT = 0 là TRIVIAL hay là đo được? Code real_static
    đã đặt `behind = (... & (depth >= 0.0))` TRƯỚC khi tính depth_hist, nên
    ahead luôn = 0 theo cấu trúc. Vế SINH thì tính trên TOÀN BỘ detection.

Chạy: base Python 3.11 + PYTHONPATH trỏ site-packages của venv.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.measure_cdf_over_range import (  # noqa: E402
    LATERAL_HALF_M, HEIGHT_MIN_M,
)
from scripts.roadspray_static_clusters import (  # noqa: E402
    AZ_BIN_DEG, MAX_RANGE_M, MIN_BG_OBS, RANGE_TOL_FRAC, RANGE_TOL_M,
    angular_coords, background_lookup, measurement_meta,
)
from scripts.roadspray_static_plume_box import (  # noqa: E402
    car_track, read_lidar, sensor_to_velodyne,
)

ZIP = "data/roadspray/Crafter_static.zip"
XLSX = "data/roadspray/meta_data_measurement.xlsx"
TMP = Path("C:/Users/ADMIN/AppData/Local/Temp/cdfprobe/rsbags")


def main() -> None:
    meta = measurement_meta(Path(XLSX))
    archive = zipfile.ZipFile(ZIP)
    members = sorted(n for n in archive.namelist() if n.endswith(".bag"))
    # bag 50 km/h đầu tiên
    pick = None
    for n in members:
        info = meta.get(Path(n).name)
        if info and info.get("speed_kmh") == 50:
            pick = n
            break
    assert pick, "không tìm được bag 50 km/h"
    info = meta[Path(pick).name]
    TMP.mkdir(parents=True, exist_ok=True)
    local = TMP / Path(pick).name
    if not local.is_file():
        with archive.open(pick) as src, open(local, "wb") as dst:
            import shutil
            shutil.copyfileobj(src, dst)
    print(f"bag {Path(pick).name} @ {info['speed_kmh']} km/h")

    clouds, stamps = read_lidar(local)
    to_velodyne = sensor_to_velodyne(local)
    track = car_track(local, to_velodyne, info.get("speed_kmh"))
    half_length = 3.4145  # Crafter 6,829 m
    height_max = 2.621
    lut = background_lookup(clouds)

    track_t = track[:, 0]
    track_xyz = track[:, 1:4]
    # hướng chuyển động: dùng hai điểm cuối của track
    motion = track_xyz[-1, :2] - track_xyz[0, :2]
    motion /= max(np.linalg.norm(motion), 1e-9)
    lateral_dir = np.array([-motion[1], motion[0]])

    n_near_ego = n_total = 0
    along_of_short = []
    for index, cloud in enumerate(clouds[:40]):
        stamp = stamps[index]
        centre = np.array([float(np.interp(stamp, track_t, track_xyz[:, a]))
                           for a in range(3)])
        centre_s = float(centre[:2] @ motion)
        centre_t = float(centre[:2] @ lateral_dir)
        rear = centre_s - half_length
        ranges = np.linalg.norm(cloud[:, :3], axis=1)
        az, _ = angular_coords(cloud)
        key = cloud[:, 3].astype(np.int64) * 1024 + np.floor(
            (az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        tol = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
        residual = ((ranges <= MAX_RANGE_M)
                    & ((lut[0][key] < MIN_BG_OBS)
                       | (np.abs(ranges - lut[1][key]) > tol)))
        residual &= ranges > 1.0
        along = cloud[:, :2] @ motion
        lateral = cloud[:, :2] @ lateral_dir
        depth = rear - along
        lateral_rel = np.abs(lateral - centre_t)
        spray_like = (cloud[:, 4] <= 0.07) & residual
        masked = (spray_like & (depth >= 0.0) & (depth < 60.0)
                  & (cloud[:, 2] >= -2.0) & (cloud[:, 2] <= height_max)
                  & (lateral_rel <= LATERAL_HALF_M))
        sel = np.nonzero(masked)[0]
        n_total += sel.size
        short = sel[ranges[sel] < 15.0]
        n_near_ego += short.size
        if short.size:
            along_of_short.append(along[short])
        if index == 0:
            print(f"  frame0: car_range={np.hypot(*centre[:2]):.1f} m, "
                  f"n_masked={sel.size}, n<15m={short.size}")

    print(f"\nN1 — trong {n_total} detection (40 frame): {n_near_ego} ở range<15 m "
          f"= {100.0 * n_near_ego / max(n_total, 1):.1f} %")
    if along_of_short:
        a = np.concatenate(along_of_short)
        print(f"   'along' (chiếu lên trục xe) của nhóm <15 m: "
              f"p5={np.percentile(a, 5):.1f} p50={np.percentile(a, 50):.1f} "
              f"p95={np.percentile(a, 95):.1f} m")
        print("   → nếu along ≈ 0..3 m thì đó là điểm quanh EGO, không phải plume xe đích.")
    print("\nN2 — vế THẬT: `behind` đã lọc (depth >= 0.0) TRƯỚC depth_hist,")
    print("   nên n_ahead_of_rear = 0 theo CẤU TRÚC, không phải số đo.")


if __name__ == "__main__":
    main()
