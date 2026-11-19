#!/usr/bin/env python3
"""Đo ``P_det(R)`` — xác suất phát hiện theo **cự ly tới cảm biến** — trên RoadSpray `*_static`.

Vì sao (toàn bộ lý do task tồn tại)
-----------------------------------
Paper Linnhoff 2022 (arXiv 2212.08558) định nghĩa (Eq. 7):

    P_det = n / n_max(r_cl, p_cl)

với `n` = số detection trong một cụm, `n_max` = **số tia lidar cắt qua quả cầu biểu
diễn cụm** — phụ thuộc bán kính cụm `r` và vị trí cụm so với cảm biến (`R`).
Paper chỉ đo `P_det` ở **một** khoảng cách (25 m, Fig. 7: µ = −2,3; σ = 1,09), nên
`P_det` được dùng như **hằng số**. Hệ quả trong repo: số detection mỗi cụm
∝ `n_max` ∝ `(r/R)²` ⇒ cụm càng gần cảm biến càng bùng nổ số điểm.

Phép đo này lấy `P_det` **theo từng cụm** trên dữ liệu thật rồi hỏi: `P_det(R)` có
tăng theo `R` không, và tăng theo luật nào (hệ số mũ `b`)?

Cách làm (tái dùng, không viết lại)
----------------------------------
* `scripts/roadspray_static_clusters.py` — trừ nền range-image `(ring, az_bin)`,
  RANSAC mặt đường, DBSCAN góc (`eps = 0,7°`, `minPts = 3`) bằng cKDTree.
* `scripts/roadspray_static_plume_box.py` — chọn track xe theo tốc độ metadata,
  chỉ đo bag xe **đang rời xa** ego (ego thấy đuôi xe ⇒ plume hướng về ego).
* `scripts/roadspray_static_depth_profile.py` — nền theo **mode** (median bị xe
  chiếm > 50 % frame), RANSAC mặt đường xa 120 m, lọc `intensity <= 2`, loại hộp
  3D thân xe, nội suy vị trí xe tại đúng stamp lidar.
* `spray/beam_model.py` — bộ tia production (`load_beam_table()`: 30 ring × 1825
  az = 54.750 tia) để đối chứng `n_max`.

Ba định nghĩa `n_max` được tính cho **cùng một cụm** (mọi số đều xuất ra):

1. ``n_max_obs`` — **chuẩn chính**: số tia của **lưới tia ĐO ĐƯỢC từ chính bag**
   (elevation trung vị của từng ring thật + 1825 cột azimuth bước 0,197307°).
   Đây là chùm tia thật đã tạo ra `n` detection, nên đây mới là mẫu số đúng
   nghĩa paper ("position with respect to the beam pattern of the sensor").
   Lý do **không** dùng bảng production làm chuẩn: bảng production là lưới đều
   30 ring trong FOV −4,06…+5,88°, còn VLP-32C của RoadSpray có 29 ring **không
   đều** trải −25…+15° (đo trong bag: ring 0 ở −24,98°, ring 8 ở −4,00°, …).
   Dùng bảng production sẽ cho `n_max = 0` với mọi cụm nằm dưới −4,06° (tức phần
   lớn plume ở cự ly gần) ⇒ `P_det` vô nghĩa.
2. ``n_max_prod`` — số tia của `load_beam_table()` cắt quả cầu (đúng thứ generator
   đang dùng); xuất ra để **định lượng sai khác hình học** đó.
3. ``n_max_sil`` — số ô tia nằm trong **hull góc (az, el)** của cụm (silhouette
   thay vì quả cầu). Quả cầu thay cụm dẹt bằng một khối cầu ⇒ phồng thể tích;
   silhouette là ước lượng "số tia có thể trúng vật thể" bảo thủ hơn. Dùng để
   kiểm tra chuẩn hoá 0,10 ở 25 m (câu hỏi 3) chứ không thay chuẩn chính.

Vùng đo (theo reference implementation của paper, `define_spray_volumes()`):
ngay sau mặt đuôi xe, ngang ±5 m (rộng hơn hộp 3,4 m để không cắt plume), cao
0,15–**1,5 m** tính từ mặt phẳng mặt đường, sâu 0–25 m. Cắt lát theo **độ sâu 1,0 m**
rồi DBSCAN góc trong từng lát: DBSCAN của paper chạy trên (az, el) **không có
chiều cự ly**, nên hai điểm cùng tia cách nhau 5 m và 20 m vẫn là hàng xóm ⇒ cả
ống plume dính thành một cụm (đã trả giá ở `roadspray_static_plume_box.py`).
Trần cao 1,5 m **không** phải để tiện: đo được rằng phần "residual" cao 1,6–2,1 m
ngay sau đuôi xe là **mặt sau thân xe** (mặt phẳng có độ dày theo chiều sâu
sd ≈ 0,04 m, n = 1159 điểm ở 5 m) — nếu để lên 3,0 m thì > 90 % "detection" ở
50 km/h là thân xe, `P_det → 0,8` giả tạo.

Frame phải nằm **trong** khoảng thời gian của track (không ngoại suy): ngoại suy
±0,3 s như `roadspray_static_depth_profile.py` làm lệch vị trí xe tới ~4 m ở
50 km/h, đủ để thân xe lọt vào vùng "sau đuôi".

Hai chế độ:

    # 1) đo, ghi JSONL từng cụm
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
        /opt/anaconda3/bin/python scripts/measure_pdet_vs_range.py
    # 2) tổng hợp: bảng theo bin cự ly + fit log-log + bootstrap theo bag
    ... scripts/measure_pdet_vs_range.py --mode aggregate

Trung thực: RoadSpray static là ego **đỗ**, xe chạy ngang qua rồi ra xa — không
phải kịch bản following của generator. Mọi số đọc kèm caveat này.
"""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, QhullError

try:  # chạy như script (scripts/ trong sys.path) hoặc import từ repo root
    from roadspray_static_clusters import (
        AZ_BIN_DEG,
        MIN_BG_OBS,
        MIN_PTS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        angular_dbscan,
        measurement_meta,
    )
    from roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )
    from roadspray_static_depth_profile import (
        BODY_DIMS_M,
        BODY_MARGIN_M,
        INTENSITY_MAX_SPRAY,
        MAX_RANGE_EXT_M,
        NEAR_FIELD_M,
        background_lookup_mode,
        fit_ground_plane_ext,
        height_above,
    )
except ImportError:  # pragma: no cover - import từ repo root
    from scripts.roadspray_static_clusters import (
        AZ_BIN_DEG,
        MIN_BG_OBS,
        MIN_PTS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        angular_dbscan,
        measurement_meta,
    )
    from scripts.roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )
    from scripts.roadspray_static_depth_profile import (
        BODY_DIMS_M,
        BODY_MARGIN_M,
        INTENSITY_MAX_SPRAY,
        MAX_RANGE_EXT_M,
        NEAR_FIELD_M,
        background_lookup_mode,
        fit_ground_plane_ext,
        height_above,
    )

from spray.beam_model import ELEVATION_STEP_DEG, build_beams, load_beam_table, ray_directions

# --- vùng đo ---------------------------------------------------------------
DEPTH_MIN_M = 0.0
DEPTH_MAX_M = 25.0
SLICE_M = 1.0             # bề dày lát cắt theo độ sâu [m]
HEIGHT_MIN_M = 0.15       # trên mặt phẳng mặt đường
HEIGHT_MAX_M = 1.5        # trần vùng spray của reference implementation
LATERAL_HALF_M = 5.0
BODY_BACK_EXTRA_M = 0.2
# --- chùm tia đo được ------------------------------------------------------
AZ_COLUMNS = 1825         # 360° / 0,197307° (đo trên release)
AZ_STEP_DEG = 360.0 / AZ_COLUMNS
# --- bin cự ly -------------------------------------------------------------
R_EDGES = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 55.0)
R_LABELS = tuple(f"{int(lo)}–{int(hi)}" for lo, hi in zip(R_EDGES[:-1], R_EDGES[1:]))
N_BOOT = 2000
# Bán kính cố định để đo ``P_det`` theo cách **generator dùng**: generator lấy
# r ~ lognormal(median 0,31 m) **độc lập với R** (spray/plume_state.py:
# RADIUS_MEDIAN_M = 0,31). Đo thêm ``n_max`` tại đúng bán kính này cho mỗi cụm
# ⇒ ``P_eff = n / n_max(0,31 m, R)`` là P_det mà generator CẦN, đo trực tiếp
# chứ không suy ra từ đại số.
FIXED_RADIUS_M = 0.31


# --------------------------------------------------------------------------
# chùm tia
# --------------------------------------------------------------------------
def measured_beam_dirs(
    clouds: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """Lưới tia **đo được** từ chính bag.

    Trả ``(dirs, elev_deg, az_deg, elev_grid, az_grid, az_offset_deg)`` với `dirs`
    là (K, 3) đơn vị, ``elev_grid``/``az_grid`` là (K,) đã duỗi phẳng. Elevation
    mỗi ring = trung vị elevation **thô** (không snap 0,333°).
    """
    per_ring: dict[int, list[float]] = defaultdict(list)
    az_parts: list[np.ndarray] = []
    stride = max(1, len(clouds) // 8)
    for index, cloud in enumerate(clouds):
        if index % stride and index != len(clouds) - 1:
            continue
        az, _ = angular_coords(cloud)
        el_raw = np.degrees(np.arctan2(
            cloud[:, 2], np.hypot(cloud[:, 0], cloud[:, 1])))
        az_parts.append(az)
        for ring in np.unique(cloud[:, 3]).astype(int):
            mask = cloud[:, 3] == ring
            per_ring[ring].append(float(np.median(el_raw[mask])))
    elevation = np.array([float(np.median(v)) for _k, v in sorted(per_ring.items())])
    az_flat = np.concatenate(az_parts)
    # pha của lưới azimuth so với lưới đều 1825 cột
    frac = az_flat / AZ_STEP_DEG
    phase = np.exp(2j * np.pi * (frac - np.round(frac)))
    offset = float(np.angle(phase.mean()) / (2.0 * np.pi) * AZ_STEP_DEG)
    columns = (offset + np.arange(AZ_COLUMNS) * AZ_STEP_DEG) % 360.0
    elev_grid, az_grid = np.meshgrid(elevation, columns)
    elev_flat, az_flat_grid = elev_grid.ravel(), az_grid.ravel()
    dirs = ray_directions(elev_flat, az_flat_grid)
    return dirs, elevation, columns, elev_flat, az_flat_grid, offset


def production_dirs() -> np.ndarray:
    """Tia của bộ tia production (`load_beam_table()`: 30 ring × 1825 az)."""
    table = load_beam_table()
    elevation, azimuth = build_beams(table)
    return ray_directions(elevation, azimuth)


def count_beams_in_sphere(dirs: np.ndarray, centre: np.ndarray, radius: float) -> int:
    """Số tia cắt quả cầu ``(centre, radius)`` — đúng Eq. 7 của paper.

    Điều kiện "khoảng cách từ **đường thẳng** chứa tia tới tâm cầu <= r" cộng
    "tâm cầu ở phía trước cảm biến" (``proj > 0``). Khi cảm biến nằm trong cầu
    (``|c| <= r``) thì mọi tia đều cắt.
    """
    if radius <= 0.0:
        return 0
    norm2 = float(centre @ centre)
    if norm2 <= radius * radius:
        return int(dirs.shape[0])
    projected = dirs @ centre
    perpendicular2 = norm2 - projected * projected
    hit = (perpendicular2 <= radius * radius) & (projected > 0.0)
    return int(hit.sum())


def circular_mean_deg(values: np.ndarray) -> float:
    radians = np.radians(values)
    return float(np.degrees(np.angle(np.exp(1j * radians).mean())))


def count_beams_in_silhouette(az_grid: np.ndarray, elev_grid: np.ndarray,
                              az_points: np.ndarray,
                              elev_points: np.ndarray) -> int:
    """Số ô tia nằm trong hull góc (az, el) của cụm; −1 nếu hull suy biến."""
    if az_points.size < 4:
        return -1
    centre_az = circular_mean_deg(az_points)
    local_az = (az_points - centre_az + 180.0) % 360.0 - 180.0
    points = np.column_stack([local_az, elev_points])
    if np.ptp(points[:, 0]) < 1e-9 or np.ptp(points[:, 1]) < 1e-9:
        return -1
    try:
        hull = ConvexHull(points)
    except (QhullError, ValueError):
        return -1
    local_grid = (az_grid - centre_az + 180.0) % 360.0 - 180.0
    window = ((local_grid >= points[:, 0].min() - 0.5)
              & (local_grid <= points[:, 0].max() + 0.5)
              & (elev_grid >= points[:, 1].min() - 0.5)
              & (elev_grid <= points[:, 1].max() + 0.5))
    if not window.any():
        return -1
    cells = np.column_stack([local_grid[window], elev_grid[window]])
    equations = hull.equations
    inside = (cells @ equations[:, :2].T + equations[:, 2] <= 1e-9).all(axis=1)
    return int(inside.sum())


# --------------------------------------------------------------------------
# đo một bag
# --------------------------------------------------------------------------
def process_bag(
    bag_name: str,
    bag_path: str,
    info: dict,
    to_velodyne: np.ndarray,
    rng: np.random.Generator,
    cfg: argparse.Namespace,
) -> tuple[list[dict], dict, str]:
    """Đo 1 bag; trả (bản ghi cụm, chẩn đoán, lý do bỏ nếu có)."""
    clouds, stamps = read_lidar(bag_path)
    if not clouds:
        return [], {}, "no_clouds"
    track = car_track(bag_path, to_velodyne, info.get("speed_kmh"))
    if track.shape[0] < 5:
        return [], {}, "no_track"
    delta_t = np.diff(track[:, 0])
    valid_t = delta_t > 1e-3
    if not valid_t.any():
        return [], {}, "no_track_dt"
    track_r = np.hypot(track[:, 1], track[:, 2])
    range_rate = float(np.median(np.diff(track_r)[valid_t] / delta_t[valid_t]))
    if range_rate <= 0.0:
        return [], {}, "approaching"

    motion = track[-1, 1:3] - track[0, 1:3]
    norm = float(np.linalg.norm(motion))
    if norm < 1e-6:
        return [], {}, "no_motion"
    motion = motion / norm
    lateral_dir = np.array([-motion[1], motion[0]])
    # tham số vùng đo lấy từ CLI (KHÔNG dùng hằng số module — nếu không thì
    # --slice/--height-max bị bỏ qua âm thầm và bảng độ bền thành giả)
    slice_m = float(getattr(cfg, "slice_m", SLICE_M))
    height_max = float(getattr(cfg, "height_max", HEIGHT_MAX_M))
    lateral_half = float(getattr(cfg, "lateral_half", LATERAL_HALF_M))
    depth_max = float(getattr(cfg, "depth_max", DEPTH_MAX_M))
    half_length = OBJECT_HALF_LENGTH_M.get(
        str(info.get("object_name")), DEFAULT_HALF_LENGTH_M)
    body_dims = BODY_DIMS_M.get(str(info.get("object_name")), (5.0, 2.0, 2.0))

    lut_bg, lut_obs = background_lookup_mode(clouds)
    coef = fit_ground_plane_ext(clouds[len(clouds) // 2], rng)
    if coef is None:
        return [], {}, "no_ground"
    (dirs_obs, elevation_obs, columns_obs,
     elev_flat, az_flat, az_offset) = measured_beam_dirs(clouds)
    dirs_prod = PRODUCTION_DIRS

    records: list[dict] = []
    diag = {
        "frames": 0, "clusters": 0, "n_max_obs_zero": 0, "p_gt_one": 0,
        "n_above_height": 0, "n_region": 0, "n_raw_region": 0,
        "rings": int(elevation_obs.size), "az_offset_deg": round(az_offset, 4),
        "elev_min": round(float(elevation_obs.min()), 3),
        "elev_max": round(float(elevation_obs.max()), 3),
        "car_range_min": 1e9, "car_range_max": 0.0,
    }
    t_min, t_max = float(track[0, 0]), float(track[-1, 0])
    for index, cloud in enumerate(clouds):
        stamp = float(stamps[index])
        # KHÔNG ngoại suy quỹ đạo: frame ngoài khoảng track bị bỏ.
        if stamp < t_min or stamp > t_max:
            continue
        centre = np.array([
            float(np.interp(stamp, track[:, 0], track[:, 1 + axis]))
            for axis in range(3)
        ])
        centre_s = float(centre[:2] @ motion)
        centre_t = float(centre[:2] @ lateral_dir)
        rear = centre_s - half_length

        height = height_above(coef, cloud)
        ranges = np.linalg.norm(cloud[:, :3], axis=1)
        az, el = angular_coords(cloud)
        az_bin = np.floor((az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        key = cloud[:, 3].astype(np.int64) * 1024 + az_bin
        tolerance = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
        residual = (ranges <= MAX_RANGE_EXT_M) & (
            (lut_obs[key] < MIN_BG_OBS)
            | (np.abs(ranges - lut_bg[key]) > tolerance))
        residual &= ranges > NEAR_FIELD_M

        along = cloud[:, :2] @ motion
        lateral = cloud[:, :2] @ lateral_dir
        depth = rear - along
        lateral_rel = np.abs(lateral - centre_t)
        spray_like = cloud[:, 4] <= INTENSITY_MAX_SPRAY
        if getattr(cfg, "body_box", True):
            length, width, body_height = body_dims
            margin = BODY_MARGIN_M
            back_extra = float(getattr(cfg, "body_back_extra", BODY_BACK_EXTRA_M))
            s_rel = along - centre_s
            t_rel = lateral - centre_t
            body = (
                (np.abs(t_rel) <= width / 2.0 + margin)
                & (s_rel >= -length / 2.0 - margin - back_extra)
                & (s_rel <= length / 2.0 + margin)
                & (height >= -margin)
                & (height <= body_height + margin)
            )
            spray_like = spray_like & ~body

        in_depth = (depth >= DEPTH_MIN_M) & (depth < depth_max)
        in_lateral = lateral_rel <= lateral_half
        in_height = (height >= HEIGHT_MIN_M) & (height <= height_max)
        region = in_depth & in_lateral & in_height & (ranges <= MAX_RANGE_EXT_M)
        selected = np.nonzero(residual & spray_like & region)[0]
        car_range = float(np.hypot(centre[0], centre[1]))
        diag["frames"] += 1
        diag["n_region"] += int(selected.size)
        diag["n_raw_region"] += int((region & (ranges > NEAR_FIELD_M)).sum())
        diag["n_above_height"] += int(
            (residual & spray_like & in_depth & in_lateral
             & (height > height_max) & (height <= max(height_max + 1.5, 3.0))
             & (ranges <= MAX_RANGE_EXT_M)).sum())
        diag["car_range_min"] = min(diag["car_range_min"], car_range)
        diag["car_range_max"] = max(diag["car_range_max"], car_range)

        if selected.size < MIN_PTS:
            continue
        capsule = np.floor((depth[selected] - DEPTH_MIN_M) / slice_m).astype(np.int64)
        for slice_id in np.unique(capsule):
            members_slice = selected[capsule == slice_id]
            if members_slice.size < MIN_PTS:
                continue
            labels = angular_dbscan(az[members_slice], el[members_slice])
            n_labels = int(labels.max()) + 1 if labels.size else 0
            for label in range(n_labels):
                members = members_slice[labels == label]
                if members.size < MIN_PTS:
                    continue
                xyz = cloud[members, :3]
                cluster_centre = xyz.mean(axis=0)
                distance = float(np.linalg.norm(cluster_centre))
                radius = float(np.linalg.norm(xyz - cluster_centre, axis=1).max())
                if radius <= 0.0 or distance <= 0.0:
                    continue
                n_max_obs = count_beams_in_sphere(dirs_obs, cluster_centre, radius)
                n_max_fixed = count_beams_in_sphere(
                    dirs_obs, cluster_centre, FIXED_RADIUS_M)
                n_max_prod = count_beams_in_sphere(dirs_prod, cluster_centre, radius)
                n_rings = int(np.unique(cloud[members, 3]).size)
                # Hull góc chỉ có nghĩa khi cụm trải >= 2 ring và đủ điểm; cụm
                # 3–5 điểm nằm trên một hàng ô thì hull là đoạn thẳng ⇒ vô nghĩa.
                n_max_sil = (count_beams_in_silhouette(
                    az_flat, elev_flat, az[members], el[members])
                    if members.size >= 8 and n_rings >= 2 else -1)
                record = {
                    "bag": bag_name,
                    "frame": int(index),
                    "object_name": info.get("object_name"),
                    "speed_kmh": info.get("speed_kmh"),
                    "itr_after_water": info.get("itr_after_water"),
                    "car_range": round(car_range, 2),
                    "n": int(members.size),
                    "range": round(distance, 3),
                    "radius": round(radius, 3),
                    "n_max_obs": int(n_max_obs),
                    "n_max_prod": int(n_max_prod),
                    "n_max_sil": int(n_max_sil),
                    "n_max_fix": int(n_max_fixed),
                    "depth": round(float(depth[members].mean()), 2),
                    "elev": round(float(np.degrees(np.arctan2(
                        cluster_centre[2],
                        float(np.hypot(cluster_centre[0], cluster_centre[1]))))), 2),
                    "height_mean": round(float(height[members].mean()), 2),
                    "lateral_mean": round(float(lateral_rel[members].mean()), 2),
                    "intensity_mean": round(float(cloud[members, 4].mean()), 2),
                    "n_rings": n_rings,
                }
                if n_max_obs <= 0:
                    diag["n_max_obs_zero"] += 1
                elif record["n"] > n_max_obs:
                    diag["p_gt_one"] += 1
                records.append(record)
                diag["clusters"] += 1
    diag["car_range_min"] = round(float(diag["car_range_min"]), 2)
    diag["car_range_max"] = round(float(diag["car_range_max"]), 2)
    return records, diag, ""


# --------------------------------------------------------------------------
# chọn bag
# --------------------------------------------------------------------------
def candidate_bags(archive_names: list[str], meta: dict, speed: int) -> list[str]:
    """Bag ứng viên cho 1 tốc độ, xoay vòng theo `itr_after_water`."""
    rows = [n for n in archive_names
            if meta.get(Path(n).name, {}).get("speed_kmh") == speed]
    by_water: dict[int, list[str]] = defaultdict(list)
    for name in rows:
        itr = meta[Path(name).name].get("itr_after_water") or 0
        by_water[int(itr)].append(name)
    order: list[str] = []
    keys = sorted(by_water)
    while any(by_water.values()):
        for k in keys:
            if by_water[k]:
                order.append(by_water[k].pop(0))
    return order


def parse_plan(text: str) -> list[tuple[int, int]]:
    plan = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        speed, count = chunk.split(":")
        plan.append((int(speed), int(count)))
    return plan


def run(args: argparse.Namespace) -> None:
    meta = measurement_meta(Path(args.xlsx))
    to_velodyne = sensor_to_velodyne(Path(args.meta))
    tmp_dir = Path(args.tmp)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261119)
    plan = parse_plan(args.plan)
    rows_out: list[dict] = []
    diags: list[dict] = []
    used: list[dict] = []
    started = time.time()
    for zip_path in [p for p in args.zip.split(",") if p.strip()]:
        archive = zipfile.ZipFile(zip_path)
        names = sorted(n for n in archive.namelist() if n.endswith(".bag"))
        for speed, want in plan:
            got = 0
            for name in candidate_bags(names, meta, speed):
                if got >= want:
                    break
                bag_name = Path(name).name
                info = meta.get(bag_name)
                if info is None:
                    continue
                archive.extract(name, tmp_dir)
                bag_path = tmp_dir / bag_name
                Path(tmp_dir / name).replace(bag_path)
                records, diag, why = process_bag(
                    bag_name, str(bag_path), info, to_velodyne, rng, args)
                bag_path.unlink()
                if not records:
                    print(f"  [{speed} km/h] bỏ {bag_name}: {why}", flush=True)
                    continue
                got += 1
                rows_out.extend(records)
                diag.update({"bag": bag_name, "why": why})
                diags.append(diag)
                used.append({"bag": bag_name, "speed_kmh": speed,
                             "object_name": info.get("object_name"),
                             "itr_after_water": info.get("itr_after_water"),
                             "frames": diag["frames"], "clusters": diag["clusters"],
                             "car_range": [diag["car_range_min"],
                                           diag["car_range_max"]]})
                print(f"[{speed:3d} km/h] {str(info.get('object_name')):7s} "
                      f"{bag_name} frames={diag['frames']:3d} "
                      f"clusters={diag['clusters']:4d} rings={diag['rings']} "
                      f"car={diag['car_range_min']:.0f}-{diag['car_range_max']:.0f}m "
                      f"{time.time() - started:.0f}s", flush=True)
            if got == 0:
                print(f"  !! KHÔNG ĐO ĐƯỢC {speed} km/h", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        handle.write(json.dumps({
            "_kind": "params", "slice_m": args.slice_m,
            "height_max_m": args.height_max, "height_min_m": HEIGHT_MIN_M,
            "lateral_half_m": args.lateral_half, "depth_max_m": args.depth_max,
            "body_box": bool(args.body_box),
            "body_back_extra": args.body_back_extra,
            "plan": args.plan, "zip": args.zip,
            "r_edges": list(R_EDGES), "bags": used, "diagnostics": diags,
            "accumulate_dir": "roadspray_static_depth_profile.py",
            "clustering": "DBSCAN góc (az, el) eps=0.7°, minPts=3, lát sâu "
                          f"{args.slice_m} m",
        }) + "\n")
        for record in rows_out:
            handle.write(json.dumps(record) + "\n")
    print(f"xong: {len(rows_out)} cụm / {len(used)} bag -> {out}", flush=True)


# --------------------------------------------------------------------------
# tổng hợp
# --------------------------------------------------------------------------
def load_jsonl(path: Path) -> tuple[dict, list[dict]]:
    params, rows = {}, []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if "_kind" in item:
                params = item
            else:
                rows.append(item)
    return params, rows


def arrays(rows: list[dict], y_of) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Trả (log R, log y, mã bag) — bỏ dòng có y <= 0 hoặc không hữu hạn."""
    x, y, bags = [], [], []
    for row in rows:
        value = y_of(row)
        if value is None or not np.isfinite(value) or value <= 0.0:
            continue
        x.append(np.log(row["range"]))
        y.append(np.log(value))
        bags.append(row["bag"])
    codes, uniques = np.unique(np.asarray(bags), return_inverse=True)
    return np.asarray(x), np.asarray(y), uniques.reshape(-1)


def slope_pooled(x: np.ndarray, y: np.ndarray) -> float:
    xm, ym = float(x.mean()), float(y.mean())
    denominator = float(((x - xm) ** 2).sum())
    if denominator <= 0.0:
        return float("nan")
    return float(((x - xm) * (y - ym)).sum() / denominator)


def slope_fe(x: np.ndarray, y: np.ndarray, group: np.ndarray) -> float:
    counts = np.bincount(group).astype(float)
    mean_x = np.bincount(group, weights=x) / counts
    mean_y = np.bincount(group, weights=y) / counts
    xd = x - mean_x[group]
    yd = y - mean_y[group]
    denominator = float((xd * xd).sum())
    if denominator <= 0.0:
        return float("nan")
    return float((xd * yd).sum() / denominator)


def fit_block(rows: list[dict], y_of, rng: np.random.Generator,
              label: str = "") -> dict:
    """Fit ``log y = a + b log R`` + bootstrap theo bag (pooled và bag-FE)."""
    x, y, codes = arrays(rows, y_of)
    if x.size < 10:
        return {"label": label, "n": int(x.size), "bags": 0,
                "b": float("nan"), "a": float("nan"),
                "r2": float("nan"), "b_ci": [float("nan")] * 2,
                "b_fe": float("nan"), "b_fe_ci": [float("nan")] * 2}
    b = slope_pooled(x, y)
    a = float(y.mean() - b * x.mean())
    predicted = a + b * x
    total = float(((y - y.mean()) ** 2).sum())
    r2 = (1.0 - float(((y - predicted) ** 2).sum()) / total) if total > 0 else float("nan")
    b_fe = slope_fe(x, y, codes)
    n_bags = int(codes.max()) + 1
    if n_bags < 2:  # chỉ 1 bag: không bootstrap được, vẫn báo slope
        return {"label": label, "n": int(x.size), "bags": n_bags,
                "a": a, "b": b, "b_ci": [float("nan")] * 2, "r2": r2,
                "b_fe": float("nan"), "b_fe_ci": [float("nan")] * 2,
                "b_boot_sd": float("nan")}
    members = [np.nonzero(codes == code)[0] for code in range(n_bags)]
    pooled_draws = np.empty(N_BOOT)
    fe_draws = np.empty(N_BOOT)
    for index in range(N_BOOT):
        picks = rng.integers(0, n_bags, n_bags)
        idx = np.concatenate([members[p] for p in picks])
        group = np.concatenate([np.full(members[p].size, j, dtype=np.int64)
                                for j, p in enumerate(picks)])
        pooled_draws[index] = slope_pooled(x[idx], y[idx])
        fe_draws[index] = slope_fe(x[idx], y[idx], group)
    lo, hi = np.percentile(pooled_draws, [2.5, 97.5])
    fe_lo, fe_hi = np.percentile(fe_draws, [2.5, 97.5])
    return {"label": label, "n": int(x.size), "bags": int(n_bags),
            "a": a, "b": b, "b_ci": [float(lo), float(hi)], "r2": r2,
            "b_fe": float(b_fe), "b_fe_ci": [float(fe_lo), float(fe_hi)],
            "b_boot_sd": float(pooled_draws.std())}


def summarise_bins(rows: list[dict]) -> list[dict]:
    out = []
    for position, (lo, hi) in enumerate(zip(R_EDGES[:-1], R_EDGES[1:])):
        subset = [r for r in rows if lo <= r["range"] < hi]
        if not subset:
            out.append({"label": R_LABELS[position], "lo": lo, "hi": hi,
                        "clusters": 0, "bags": 0, "p_obs_n": 0, "p_prod_n": 0,
                        "p_sil_n": 0})
            continue
        p_obs = np.array([r["n"] / r["n_max_obs"] for r in subset
                          if r["n_max_obs"] > 0])
        p_sil = np.array([r["n"] / r["n_max_sil"] for r in subset
                          if r["n_max_sil"] > 0])
        p_prod = np.array([r["n"] / r["n_max_prod"] for r in subset
                           if r["n_max_prod"] > 0])
        p_paper = np.array([r["n"] / paper_nmax(r["radius"], r["range"])
                            for r in subset])
        n_values = np.array([r["n"] for r in subset], dtype=float)
        out.append({
            "label": R_LABELS[position], "lo": lo, "hi": hi,
            "clusters": len(subset),
            "bags": len({r["bag"] for r in subset}),
            "p_obs_med": float(np.median(p_obs)) if p_obs.size else float("nan"),
            "p_obs_q1": float(np.percentile(p_obs, 25)) if p_obs.size else float("nan"),
            "p_obs_q3": float(np.percentile(p_obs, 75)) if p_obs.size else float("nan"),
            "p_obs_n": int(p_obs.size),
            "p_sil_med": float(np.median(p_sil)) if p_sil.size else float("nan"),
            "p_sil_n": int(p_sil.size),
            "p_prod_med": float(np.median(p_prod)) if p_prod.size else float("nan"),
            "p_prod_n": int(p_prod.size),
            "p_paper_med": float(np.median(p_paper)) if p_paper.size else float("nan"),
            "elev_med": float(np.median([r.get("elev", float("nan"))
                                          for r in subset]))
            if any("elev" in r for r in subset) else float("nan"),
            "n_max_paper_med": float(np.median([
                paper_nmax(r["radius"], r["range"]) for r in subset])),
            "p_eff_med": float(np.median([
                r["n"] / r["n_max_fix"] for r in subset
                if r["n_max_fix"] > 0])) if any(r["n_max_fix"] > 0 for r in subset)
                else float("nan"),
            "n_max_fix_med": float(np.median([r["n_max_fix"] for r in subset])),
            "n_med": float(np.median(n_values)),
            "n_q1": float(np.percentile(n_values, 25)),
            "n_q3": float(np.percentile(n_values, 75)),
            "n_max_med": float(np.median([r["n_max_obs"] for r in subset])),
            "n_max_prod_med": float(np.median([r["n_max_prod"] for r in subset])),
            "radius_med": float(np.median([r["radius"] for r in subset])),
            "range_med": float(np.median([r["range"] for r in subset])),
            "depth_med": float(np.median([r["depth"] for r in subset])),
            "car_range_med": float(np.median([r["car_range"] for r in subset])),
            "rings_med": float(np.median([r["n_rings"] for r in subset])),
        })
    return out


def paper_nmax(radius: float, distance: float) -> float:
    """Eq. 7: số tia cắt cầu theo **góc khối** / góc khối một ô tia (paper)."""
    table = load_beam_table()
    omega = float(np.radians(table.azimuth_step_deg)
                  * np.radians(ELEVATION_STEP_DEG))
    ratio = min(radius / distance, 1.0)
    solid = (4.0 * np.pi if ratio >= 1.0
             else 2.0 * np.pi * (1.0 - np.sqrt(1.0 - ratio * ratio)))
    return float(solid / omega)


def aggregate(args: argparse.Namespace) -> None:
    params, rows = load_jsonl(Path(args.out))
    rng = np.random.default_rng(20261120)
    summary: dict = {"params": {k: v for k, v in params.items() if k != "_kind"},
                     "bins": [], "fits": {}, "questions": {}}
    if not rows:
        print("KHÔNG CÓ DỮ LIỆU")
        return
    n_bags = len({r["bag"] for r in rows})
    print(f"# {len(rows)} cụm / {n_bags} bag / "
          f"{len({(r['bag'], r['frame']) for r in rows})} frame-có-cụm\n")

    bins = summarise_bins(rows)
    summary["bins"] = bins
    print("| bin cự ly (m) | cụm | bag | median n | IQR n | median n_max | "
          "median r (m) | median P_det | IQR P_det | median P_sil |")
    print("|---|---:|---:|---:|---|---:|---:|---|---|---:|")
    for item in bins:
        if item["clusters"] == 0:
            print(f"| {item['label']} | 0 | 0 | — | — | — | — | — | — | — |")
            continue
        print(f"| {item['label']} | {item['clusters']} | {item['bags']} | "
              f"{item['n_med']:.0f} | {item['n_q1']:.0f}–{item['n_q3']:.0f} | "
              f"{item['n_max_med']:.0f} | {item['radius_med']:.2f} | "
              f"{item['p_obs_med']:.3f} | {item['p_obs_q1']:.3f}–{item['p_obs_q3']:.3f} | "
              f"{item['p_sil_med']:.3f} |")

    usable = [r for r in rows if r["n_max_obs"] > 0]
    print(f"\nCụm dùng được (n_max_obs > 0): {len(usable)}/{len(rows)}; "
          f"n_max_obs = 0: {len(rows) - len(usable)}")

    # --- fit chính -----------------------------------------------------
    p_fit = fit_block(usable, lambda r: r["n"] / r["n_max_obs"], rng, "P_det")
    n_fit = fit_block(rows, lambda r: float(r["n"]), rng, "n")
    r_fit = fit_block(usable, lambda r: r["radius"], rng, "r")
    fixed = [r for r in usable if r["n_max_fix"] > 0]
    p_eff = fit_block(fixed, lambda r: r["n"] / r["n_max_fix"], rng, "P_eff")
    nmax_fix_fit = fit_block(fixed, lambda r: float(r["n_max_fix"]), rng, "n_max_fix")
    summary["fits"]["p_vs_r"] = p_fit
    summary["fits"]["n_vs_r"] = n_fit
    summary["fits"]["r_vs_r"] = r_fit
    summary["fits"]["p_eff_vs_r"] = p_eff
    summary["fits"]["nmax_fix_vs_r"] = nmax_fix_fit
    print(f"\nFit P_det  log P = {p_fit['a']:.3f} + {p_fit['b']:.3f}·log R   "
          f"(b CI95 [{p_fit['b_ci'][0]:.3f}; {p_fit['b_ci'][1]:.3f}], "
          f"R² = {p_fit['r2']:.3f}, n = {p_fit['n']}, bag = {p_fit['bags']})")
    print(f"           bag-FE b = {p_fit['b_fe']:.3f} "
          f"(CI95 [{p_fit['b_fe_ci'][0]:.3f}; {p_fit['b_fe_ci'][1]:.3f}])")
    print(f"Fit n      log n = {n_fit['a']:.3f} + {n_fit['b']:.3f}·log R   "
          f"(CI95 [{n_fit['b_ci'][0]:.3f}; {n_fit['b_ci'][1]:.3f}], "
          f"R² = {n_fit['r2']:.3f}); bag-FE b = {n_fit['b_fe']:.3f} "
          f"(CI95 [{n_fit['b_fe_ci'][0]:.3f}; {n_fit['b_fe_ci'][1]:.3f}])")
    print(f"Fit r      log r = {r_fit['a']:.3f} + {r_fit['b']:.3f}·log R   "
          f"(CI95 [{r_fit['b_ci'][0]:.3f}; {r_fit['b_ci'][1]:.3f}])")
    print(f"Fit P_eff  (n_max tại r = {FIXED_RADIUS_M:.2f} m CỐ ĐỊNH, như "
          f"generator) log P = {p_eff['a']:.3f} + {p_eff['b']:.3f}·log R   "
          f"(CI95 [{p_eff['b_ci'][0]:.3f}; {p_eff['b_ci'][1]:.3f}], "
          f"R² = {p_eff['r2']:.3f}, n = {p_eff['n']}); bag-FE b = "
          f"{p_eff['b_fe']:.3f} (CI95 [{p_eff['b_fe_ci'][0]:.3f}; "
          f"{p_eff['b_fe_ci'][1]:.3f}])")

    # fit trên MEDIAN TỪNG BIN (bền hơn với nhiễu cụm; mỗi bin 1 điểm)
    def bin_median_fit(y_key: str, weight: str = "usable") -> tuple[float, float, int]:
        xs, ys = [], []
        for item in bins:
            value = item.get(y_key)
            if item["clusters"] == 0 or value is None or not np.isfinite(value):
                continue
            if value <= 0.0:
                continue
            xs.append(np.log(item["range_med"]))
            ys.append(np.log(value))
        if len(xs) < 3:
            return float("nan"), float("nan"), len(xs)
        slope, intercept = np.polyfit(np.asarray(xs), np.asarray(ys), 1)
        return float(intercept), float(slope), len(xs)
    a_bin, b_bin, n_bin = bin_median_fit("p_obs_med")
    an_bin, bn_bin, _ = bin_median_fit("n_med")
    summary["fits"]["p_bin_medians"] = {"a": a_bin, "b": b_bin, "n_bins": n_bin}
    summary["fits"]["n_bin_medians"] = {"a": an_bin, "b": bn_bin}
    summary["fits"]["p_eff_bin_medians"] = {
        "b": bin_median_fit("p_eff_med")[1]}
    print(f"Fit bin-median  P_det: b = {b_bin:.3f} ({n_bin} bin) | "
          f"n: b = {bn_bin:.3f}")

    # --- theo lớp / tốc độ --------------------------------------------
    print("\n## Theo lớp và tốc độ\n")
    print("| ô | bag | cụm | median R | median n | median n_max | median P_det | b |")
    print("|---|---:|---:|---:|---:|---:|---|---:|")
    summary["fits"]["cells"] = {}
    cells = sorted({(str(r["object_name"]), int(r["speed_kmh"])) for r in usable})
    for key in cells:
        subset = [r for r in usable if (str(r["object_name"]), int(r["speed_kmh"])) == key]
        if len(subset) < 20:
            print(f"| {key[0]} {key[1]} | {len({r['bag'] for r in subset})} | "
                  f"{len(subset)} | — | — | — | — | — |")
            continue
        cell_fit = fit_block(subset, lambda r: r["n"] / r["n_max_obs"], rng)
        print(f"| {key[0]} {key[1]} | {len({r['bag'] for r in subset})} | "
              f"{len(subset)} | {np.median([r['range'] for r in subset]):.1f} | "
              f"{np.median([r['n'] for r in subset]):.0f} | "
              f"{np.median([r['n_max_obs'] for r in subset]):.0f} | "
              f"{np.median([r['n'] / r['n_max_obs'] for r in subset]):.3f} | "
              f"{cell_fit['b']:.3f} |")
        summary["fits"]["cells"][f"{key[0]}_{key[1]}"] = cell_fit

    # --- kiểm tra độ bền ----------------------------------------------
    print("\n## Kiểm tra độ bền của b (P_det)\n")
    print("| biến thể | cụm | b | CI95 |")
    print("|---|---:|---:|---|")
    variants = {
        "chuẩn: n_max đo được": (usable, lambda r: r["n"] / r["n_max_obs"]),
        "chỉ cụm n >= 10": ([r for r in usable if r["n"] >= 10],
                            lambda r: r["n"] / r["n_max_obs"]),
        "chỉ cụm n >= 20": ([r for r in usable if r["n"] >= 20],
                            lambda r: r["n"] / r["n_max_obs"]),
        "chỉ spray tươi depth <= 6 m": ([r for r in usable if r["depth"] <= 6.0],
                                        lambda r: r["n"] / r["n_max_obs"]),
        "chỉ depth > 6 m": ([r for r in usable if r["depth"] > 6.0],
                            lambda r: r["n"] / r["n_max_obs"]),
        "n_max = silhouette (hull góc)": ([r for r in usable if r["n_max_sil"] > 0],
                                          lambda r: r["n"] / r["n_max_sil"]),
        "n_max = bảng production": ([r for r in usable if r["n_max_prod"] > 0],
                                    lambda r: r["n"] / r["n_max_prod"]),
        "n_max = công thức paper (Ω/ω)": (
            usable, lambda r: r["n"] / paper_nmax(r["radius"], r["range"])),
    }
    summary["fits"]["variants"] = {}
    for label, (subset, y_of) in variants.items():
        if len(subset) < 30:
            print(f"| {label} | {len(subset)} | — | — |")
            continue
        variant = fit_block(subset, y_of, rng)
        print(f"| {label} | {len(subset)} | {variant['b']:.3f} | "
              f"[{variant['b_ci'][0]:.3f}; {variant['b_ci'][1]:.3f}] |")
        summary["fits"]["variants"][label] = variant

    # --- câu hỏi 3 & 4 ------------------------------------------------
    radius_med = float(np.median([r["radius"] for r in usable]))
    near_25 = [r for r in usable if 20.0 <= r["range"] < 30.0]
    radius_at_25 = float(np.median([r["radius"] for r in near_25])) if near_25 else radius_med
    p25_fit = float(np.exp(p_fit["a"] + p_fit["b"] * np.log(25.0)))
    p2_fit = float(np.exp(p_fit["a"] + p_fit["b"] * np.log(2.0)))
    nmax2 = paper_nmax(radius_at_25, 2.0)
    nmax25 = paper_nmax(radius_at_25, 25.0)
    ratio_model = nmax2 / nmax25
    ratio_measured = ratio_model * (2.0 / 25.0) ** p_fit["b"]
    # P_det mà generator CẦN nếu giữ r cố định ở giá trị đo tại 25 m:
    # n_gen(R) = n_max(r_25, R)·P_req(R) và n_max(r_25, R) ∝ R^-2
    # ⇒ P_req(R) ∝ n_obs(R)·R²  ⇒ b_req = b_n + 2.
    b_req = n_fit["b"] + 2.0
    b_req_ci = [n_fit["b_ci"][0] + 2.0, n_fit["b_ci"][1] + 2.0]
    ratio_required = ratio_model * (2.0 / 25.0) ** b_req
    # kiểm tra số: n_max(r_25, R) có đúng luật R^-2 trên dải đo không
    grid = np.array([5.0, 8.0, 12.0, 16.0, 20.0, 25.0, 30.0, 40.0])
    nmax_grid = np.array([paper_nmax(radius_at_25, d) for d in grid])
    nmax_slope = float(np.polyfit(np.log(grid), np.log(nmax_grid), 1)[0])
    summary["questions"] = {
        "radius_med_m": radius_med, "radius_at_25m_m": radius_at_25,
        "p_at_25_fit": p25_fit, "p_at_2_fit": p2_fit,
        "p_at_25_bin_med": next((b["p_obs_med"] for b in bins
                                 if b["lo"] == 20.0), float("nan")),
        "p_at_25_bin_med_sil": next((b["p_sil_med"] for b in bins
                                     if b["lo"] == 20.0), float("nan")),
        "nmax_paper_2m": nmax2, "nmax_paper_25m": nmax25,
        "nmax_ratio_2_over_25": ratio_model,
        "nmax_grid": grid.tolist(), "nmax_grid_values": nmax_grid.round(1).tolist(),
        "nmax_local_slope": nmax_slope,
        "points_ratio_measured_b": ratio_measured,
        "points_ratio_paper_b0": ratio_model,
        "b_required_fixed_r": b_req, "b_required_ci": b_req_ci,
        "points_ratio_required": ratio_required,
        "b_eff_measured": p_eff["b"], "b_eff_ci": p_eff["b_ci"],
        "points_ratio_eff_measured": ratio_model
        * (2.0 / 25.0) ** p_eff["b"] if np.isfinite(p_eff["b"]) else float("nan"),
        "n_max_fix_by_bin": {b["label"]: b.get("n_max_fix_med") for b in bins},
        "p_eff_by_bin": {b["label"]: b.get("p_eff_med") for b in bins},
        "n_med_all": float(np.median([r["n"] for r in usable])),
        "n_med_by_bin": {b["label"]: b.get("n_med") for b in bins},
        "p_med_by_bin": {b["label"]: b.get("p_obs_med") for b in bins},
        "radius_by_bin": {b["label"]: b.get("radius_med") for b in bins},
    }
    print("\n## Câu hỏi 3–4\n")
    print(f"P_det từ fit: 25 m = {p25_fit:.3f} | 2 m = {p2_fit:.4f}; "
          f"median bin 20–25 m = {summary['questions']['p_at_25_bin_med']:.3f} "
          f"(silhouette {summary['questions']['p_at_25_bin_med_sil']:.3f})")
    print(f"r trung vị = {radius_med:.3f} m; r trung vị trong 20–30 m = "
          f"{radius_at_25:.3f} m (paper: 0,31 m)")
    print(f"n_max paper với r = {radius_at_25:.3f} m: 2 m = {nmax2:.0f}, "
          f"25 m = {nmax25:.0f}, tỉ lệ {ratio_model:.1f}×; "
          f"slope log-log trên 5–40 m = {nmax_slope:.3f} (lý thuyết −2)")
    print(f"điểm/cụm 2 m : 25 m = {ratio_measured:.2f}× nếu dùng b đo được "
          f"({p_fit['b']:.2f}) — tức KHÔNG cải thiện so với {ratio_model:.1f}× "
          f"của mô hình hằng số")
    print(f"nếu giữ r cố định (như generator, r = {FIXED_RADIUS_M:.2f} m) thì "
          f"P_det ĐO ĐƯỢC là P(R) ∝ R^{p_eff['b']:.2f} "
          f"(CI95 [{p_eff['b_ci'][0]:.2f}; {p_eff['b_ci'][1]:.2f}]) "
          f"⇒ điểm/cụm 2 m : 25 m = "
          f"{ratio_model * (2.0 / 25.0) ** p_eff['b']:.2f}×")
    print(f"Nếu n_max ∝ R^-2 (bảng tia ĐỀU của generator) thì P_det cần là "
          f"b_n + 2 = {b_req:.2f} (CI95 [{b_req_ci[0]:.2f}; {b_req_ci[1]:.2f}]). "
          f"Nhưng n_max của lưới tia THẬT chỉ giảm như R^"
          f"{nmax_fix_fit['b']:.2f} (CI95 [{nmax_fix_fit['b_ci'][0]:.2f}; "
          f"{nmax_fix_fit['b_ci'][1]:.2f}]) ⇒ b_eff = b_n − slope(n_max) = "
          f"{n_fit['b'] - nmax_fix_fit['b']:.2f}, khớp b_eff đo được "
          f"{p_eff['b']:.2f}")

    out = Path(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nsummary -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("run", "aggregate"), default="run")
    parser.add_argument("--zip",
                        default="data/roadspray/Crafter_static.zip,"
                                "data/roadspray/Golf_static.zip")
    parser.add_argument("--xlsx",
                        default="data/roadspray/meta_data_measurement.xlsx")
    parser.add_argument("--meta", default="data/roadspray/meta_data_dataset.json")
    parser.add_argument("--tmp", default=".scratch/tmp/bags")
    parser.add_argument("--out", default=".scratch/tmp/pdet_vs_range.jsonl")
    parser.add_argument("--summary", default=".scratch/tmp/pdet_vs_range_summary.json")
    parser.add_argument("--plan", default="50:2,100:1,130:2",
                        help="số bag mỗi tốc độ, mỗi lớp xe: '50:2,100:1,130:2'")
    parser.add_argument("--slice", dest="slice_m", type=float, default=SLICE_M)
    parser.add_argument("--height-max", type=float, default=HEIGHT_MAX_M)
    parser.add_argument("--lateral-half", type=float, default=LATERAL_HALF_M)
    parser.add_argument("--depth-max", type=float, default=DEPTH_MAX_M)
    parser.add_argument("--no-body", dest="body_box", action="store_false")
    parser.add_argument("--body-back-extra", type=float, default=BODY_BACK_EXTRA_M)
    args = parser.parse_args()
    if args.mode == "run":
        run(args)
    else:
        aggregate(args)


PRODUCTION_DIRS = production_dirs()


if __name__ == "__main__":
    main()
