#!/usr/bin/env python3
"""Đo **depth profile 0–60 m** của plume spray thật trên RoadSpray `*_static`.

Mục đích (task-13 / T4): hộp calibration cũ chỉ dài 20 m; cần biết plume thật kéo
dài bao xa phía sau đuôi xe để biết hộp 20 m có cắt mất phần lớn plume không.

Tái dùng nguyên logic của `scripts/roadspray_static_plume_box.py`:
- chọn track xe đối tượng từ `/front_ibeo_lux/as_tx/objects` theo tốc độ metadata;
- chỉ đo bag xe **đang rời xa** ego (ego thấy đuôi xe, plume hướng về ego);
- mặt đuôi = tâm track − nửa chiều dài xe (Crafter 3,5 m / Golf 2,15 m);
- trừ nền bằng range-image theo `(ring, az_bin)`; RANSAC mặt phẳng mặt đường;
- `cluster_angular` (DBSCAN `eps=0,7°`, `minPts=3`, elevation snap `0,333°`).

Mở rộng vùng đo:
- sâu **0 → 60 m** sau mặt đuôi, bin **2 m**;
- xuất **HAI biến thể** trên cùng bin (theo yêu cầu R3 để so cùng thước với
  generator): `masked` = ngang ±5 m, cao 0,15–3,0 m từ mặt phẳng mặt đường;
  `unmasked` = mọi detection 0–60 m sau đuôi, **không** mask ngang/độ cao.

Detection = điểm residual sau trừ nền (range-image mode), `intensity <= 2`
(Paper A §III-B L724-726: >80 % detection spray có intensity 0, 16 % có 1) để
không đếm thân xe/reflector. Mỗi frame ghi: số điểm (detections) theo từng
depth-bin cho cả 2 biến thể; số cụm (masked); histogram độ cao/|y|; số điểm
trong hộp cũ 3,4×1,5×20 m; hệ số mặt phẳng mặt đường RANSAC; vùng đối chứng
phía trước xe (phải ~0). Trail 90 % xuất **biên phải bin** + biên trái + nội suy.

Hai chế độ:
    # 1) đo (mặc định) — ghi JSONL từng frame
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
        /opt/anaconda3/bin/python scripts/roadspray_static_depth_profile.py
    # 2) tổng hợp JSONL -> bảng markdown + summary JSON
    ... scripts/roadspray_static_depth_profile.py --mode aggregate

Lưu ý trung thực: RoadSpray static là ego ĐỖ, xe chạy qua; plume nhìn từ phía
sau/bên, không phải kịch bản following của generator. Mọi số đọc kèm caveat này.
"""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:  # chạy như script (scripts/ trong sys.path) hoặc import từ repo root
    from roadspray_static_clusters import (
        AZ_BIN_DEG,
        MAX_RANGE_M,
        MIN_BG_OBS,
        MIN_PTS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        angular_dbscan,
        background_lookup,
        measurement_meta,
    )
    from roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        TRACK_MAX_AGE_S,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )
except ImportError:  # pragma: no cover - import từ repo root
    from scripts.roadspray_static_clusters import (
        AZ_BIN_DEG,
        MAX_RANGE_M,
        MIN_BG_OBS,
        MIN_PTS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        angular_dbscan,
        background_lookup,
        measurement_meta,
    )
    from scripts.roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        TRACK_MAX_AGE_S,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )

# --- vùng đo mới (T4) ------------------------------------------------------
DEPTH_MAX_M = 60.0
BIN_WIDTH_M = 2.0
N_BINS = int(round(DEPTH_MAX_M / BIN_WIDTH_M))
LATERAL_HALF_M = 5.0
HEIGHT_MIN_M = 0.15
HEIGHT_MAX_M = 3.0
# LiDAR phải nhìn được tới rear + 60 m khi xe đã chạy xa; MAX_RANGE_M cũ (60)
# không đủ nên mở rộng. Đo thử 1 bag để kiểm tra data có trả về ở range này.
MAX_RANGE_EXT_M = 160.0
GROUND_MAX_RANGE_EXT_M = 120.0
NEAR_FIELD_M = 4.0  # bỏ điểm sát ego (thân xe/nhiễu gần)
# Paper A §III-B (L724-726): >80 % detection spray của VLP32 có intensity 0,
# 16 % có intensity 1. Thân xe / biển số / reflector cho intensity cao (p50 17-100
# trong thử nghiệm) nên lọc <= 2 để không đếm thân xe khi track bị trễ.
INTENSITY_MAX_SPRAY = 2.0
# Kích thước hộp thân xe để loại theo HÌNH HỌC (length, width, height) [m].
# Length = 2 × OBJECT_HALF_LENGTH_M của plume_box (Crafter 3,5 → 7,0 m;
# Golf 2,15 → 4,3 m); width/height theo xe thật. Track ibeo không cho dims
# (marker.scale chỉ là kích thước marker hiển thị 0,05–0,1 m) nên dùng hằng số.
BODY_DIMS_M = {"Crafter": (7.0, 2.4, 2.6), "Golf": (4.3, 1.8, 1.5)}
BODY_MARGIN_M = 0.2
# --- hộp cũ để nối số ------------------------------------------------------
BOX_WIDTH_M = 3.4
BOX_HEIGHT_M = 1.5
BOX_DEPTH_M = 20.0
CONTROL_DEPTH_M = 20.0
# --- histogram để tính percentile ------------------------------------------
H_EDGES = np.arange(HEIGHT_MIN_M, HEIGHT_MAX_M + 0.1, 0.1)      # 29 bins
Y_EDGES = np.arange(0.0, LATERAL_HALF_M + 0.1, 0.1)             # 50 bins


def fit_ground_plane_ext(points: np.ndarray,
                         rng: np.random.Generator) -> tuple[float, float, float] | None:
    """RANSAC mặt đường trên phạm vi xa hơn `fit_ground_plane` (đến 120 m).

    Bản gốc giới hạn 45 m; depth profile cần 60 m sau xe (range tới ~150 m) nên
    fit trên nhiều điểm đường hơn để ngoại suy bớt lệch.
    """
    far = np.linalg.norm(points[:, :3], axis=1)
    candidate = np.nonzero((points[:, 2] < 0.0)
                           & (far <= GROUND_MAX_RANGE_EXT_M))[0]
    if candidate.size < 500:
        return None
    sample = candidate if candidate.size <= 6000 else rng.choice(
        candidate, size=6000, replace=False)
    xyz = points[sample, :3]
    best_count, best_coef = 0, None
    for _ in range(400):
        pick = rng.choice(sample.size, size=3, replace=False)
        design = np.column_stack([xyz[pick, 0], xyz[pick, 1], np.ones(3)])
        try:
            coef, *_ = np.linalg.lstsq(design, xyz[pick, 2], rcond=None)
        except np.linalg.LinAlgError:  # pragma: no cover
            continue
        if abs(coef[0]) > 0.35 or abs(coef[1]) > 0.35:
            continue
        residual = np.abs(xyz[:, 2] - (coef[0] * xyz[:, 0]
                                      + coef[1] * xyz[:, 1] + coef[2]))
        count = int((residual < 0.12).sum())
        if count > best_count:
            best_count, best_coef = count, coef
    if best_coef is None or best_count < 500:
        return None
    coef = best_coef
    for _ in range(2):
        residual = np.abs(xyz[:, 2] - (coef[0] * xyz[:, 0]
                                       + coef[1] * xyz[:, 1] + coef[2]))
        keep = residual < 0.12
        if keep.sum() < 500:
            break
        design = np.column_stack([xyz[keep, 0], xyz[keep, 1],
                                  np.ones(int(keep.sum()))])
        coef, *_ = np.linalg.lstsq(design, xyz[keep, 2], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def height_above(coef: tuple[float, float, float],
                 points: np.ndarray) -> np.ndarray:
    a, b, c = coef
    return points[:, 2] - (a * points[:, 0] + b * points[:, 1] + c)


def background_lookup_mode(clouds: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Nền theo **mode** range mỗi `(ring, az_bin)` thay vì median.

    Lý do: xe đối tượng đi qua một bin có thể chiếm >50 % số frame, làm median
    của bin = range của xe; khi xe đi khỏi, nền thật bị đánh dấu residual. Mode
    (đỉnh histogram 0,5 m) bám nền tĩnh vì nền trả về cùng range mỗi frame, còn
    xe quét qua tạo dải range rộng.
    """
    keys, ranges = [], []
    for cloud in clouds:
        az, _ = angular_coords(cloud)
        az_bin = np.floor((az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        keys.append(cloud[:, 3].astype(np.int64) * 1024 + az_bin)
        ranges.append(np.linalg.norm(cloud[:, :3], axis=1))
    flat_k = np.concatenate(keys)
    flat_r = np.concatenate(ranges)
    order = np.argsort(flat_k, kind="stable")
    sorted_k, sorted_r = flat_k[order], flat_r[order]
    uniq, starts = np.unique(sorted_k, return_index=True)
    obs = np.diff(np.append(starts, sorted_k.size))
    size = int(uniq.max()) + 1
    lut_mode = np.full(size, np.nan)
    lut_obs = np.zeros(size, dtype=np.int32)
    edges = np.arange(0.0, MAX_RANGE_EXT_M + 0.5, 0.5)
    for i in range(uniq.size):
        values = sorted_r[starts[i]:starts[i] + obs[i]]
        hist, _ = np.histogram(values, bins=edges)
        peak = int(hist.argmax())
        lut_mode[uniq[i]] = 0.5 * (edges[peak] + edges[peak + 1])
        lut_obs[uniq[i]] = obs[i]
    return lut_mode, lut_obs


def bin_index(values: np.ndarray, width: float, lo: float = 0.0) -> np.ndarray:
    return np.floor((values - lo) / width).astype(np.int64)


def climb(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Histogram thô (counts) theo edges; trả 1-D dài len(edges)-1."""
    if values.size == 0:
        return np.zeros(edges.size - 1, dtype=np.int64)
    counts, _ = np.histogram(values, bins=edges)
    return counts.astype(np.int64)


def percentile_from_hist(counts: np.ndarray, edges: np.ndarray,
                         q: float) -> float:
    total = int(counts.sum())
    if total == 0:
        return float("nan")
    target = q / 100.0 * total
    cum = np.cumsum(counts)
    index = int(np.searchsorted(cum, target, side="left"))
    index = min(index, len(counts) - 1)
    before = 0 if index == 0 else int(cum[index - 1])
    width = float(edges[index + 1] - edges[index])
    frac = (target - before) / max(int(counts[index]), 1)
    return float(edges[index] + frac * width)


def process_bag(
    bag_name: str,
    bag_path: str,
    info: dict,
    to_velodyne: np.ndarray,
    rng: np.random.Generator,
    cfg: argparse.Namespace,
) -> tuple[list[dict], str]:
    """Đo 1 bag; trả (records, lý do bỏ nếu có)."""
    clouds, stamps = read_lidar(bag_path)
    if not clouds:
        return [], "no_clouds"
    track = car_track(bag_path, to_velodyne, info.get("speed_kmh"))
    if track.shape[0] < 5:
        return [], "no_track"
    delta_t = np.diff(track[:, 0])
    valid_t = delta_t > 1e-3
    if not valid_t.any():
        return [], "no_track_dt"
    track_r = np.hypot(track[:, 1], track[:, 2])
    range_rate = float(np.median(np.diff(track_r)[valid_t] / delta_t[valid_t]))
    want_receding = getattr(cfg, "direction", "signal") == "signal"
    if want_receding and range_rate <= 0.0:
        return [], "approaching"
    if (not want_receding) and range_rate > 0.0:
        return [], "receding"

    motion = track[-1, 1:3] - track[0, 1:3]
    norm = float(np.linalg.norm(motion))
    if norm < 1e-6:
        return [], "no_motion"
    motion = motion / norm
    lateral_dir = np.array([-motion[1], motion[0]])
    half_length = OBJECT_HALF_LENGTH_M.get(
        str(info.get("object_name")), DEFAULT_HALF_LENGTH_M)

    lut_bg, lut_obs = background_lookup_mode(clouds)
    coef = fit_ground_plane_ext(clouds[len(clouds) // 2], rng)
    if coef is None:
        return [], "no_ground"

    records: list[dict] = []
    track_t = track[:, 0]
    track_xyz = track[:, 1:4]
    t_min, t_max = float(track_t[0]), float(track_t[-1])
    for index, cloud in enumerate(clouds):
        stamp = stamps[index]
        # Nội suy tuyến tính vị trí tâm xe tại đúng stamp của lidar (bag 50 km/h
        # có ibeo thưa: lấy mẫu gần nhất có thể trễ tới 0,3 s = 4,2 m, đủ để
        # thân xe lọt vào bin depth 0–4 m).
        if stamp < t_min - TRACK_MAX_AGE_S or stamp > t_max + TRACK_MAX_AGE_S:
            continue
        centre = np.array([
            float(np.interp(stamp, track_t, track_xyz[:, axis]))
            for axis in range(3)
        ])
        centre_s = float(centre[:2] @ motion)
        centre_t = float(centre[:2] @ lateral_dir)
        rear = centre_s - half_length
        front = centre_s + half_length

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
        height_max = float(getattr(cfg, "height_max", HEIGHT_MAX_M))
        spray_like = cloud[:, 4] <= INTENSITY_MAX_SPRAY
        body_removed = 0
        if getattr(cfg, "body_box", False):
            length, width, body_height = BODY_DIMS_M.get(
                str(info.get("object_name")), (5.0, 2.0, 2.0))
            margin = BODY_MARGIN_M
            back_extra = float(getattr(cfg, "body_back_extra", margin))
            s_rel = along - centre_s
            t_rel = lateral - centre_t
            body = (
                (np.abs(t_rel) <= width / 2.0 + margin)
                & (s_rel >= -length / 2.0 - margin - back_extra)
                & (s_rel <= length / 2.0 + margin)
                & (height >= -margin)
                & (height <= body_height + margin)
            )
            body_removed = int((residual & spray_like & body).sum())
            spray_like = spray_like & ~body
        behind = (residual & spray_like
                  & (depth >= 0.0) & (depth < DEPTH_MAX_M))       # biến thể UNMASKED
        mask_xy = ((height >= HEIGHT_MIN_M) & (height <= height_max)
                   & (lateral_rel <= LATERAL_HALF_M))
        masked = behind & mask_xy                                   # biến thể MASKED
        selected = np.nonzero(masked)[0]
        unmasked_idx = np.nonzero(behind)[0]
        ground_z_at_points = (coef[0] * cloud[:, 0] + coef[1] * cloud[:, 1]
                              + coef[2])

        record: dict = {
            "bag": bag_name,
            "frame": index,
            "speed_kmh": info.get("speed_kmh"),
            "object_name": info.get("object_name"),
            "itr_after_water": info.get("itr_after_water"),
            "measurement_itr": info.get("measurement_itr"),
            "car_range": round(float(np.hypot(centre[0], centre[1])), 2),
            "rear": round(float(rear), 2),
            "n_cloud": int(cloud.shape[0]),
            "n_residual": int(residual.sum()),
            "n_body_removed": body_removed,
            "n_masked": int(selected.size),
            "n_unmasked": int(unmasked_idx.size),
            "bins_masked": [0] * N_BINS,
            "bins_unmasked": [0] * N_BINS,
            "clusters_masked": [0] * N_BINS,
            "h_hist": [0] * (H_EDGES.size - 1),
            "y_hist": [0] * (Y_EDGES.size - 1),
            "h_max": 0.0,
            "y_max": 0.0,
            "n_in_box": 0,
            "n_box_height": 0,
            "n_box_width": 0,
            "n_unmasked_below_ground": 0,
            "n_unmasked_above_3m": 0,
            "height_max_m": round(height_max, 3),
            "n_unmasked_wide": 0,
            "ground_a": round(float(coef[0]), 4),
            "ground_b": round(float(coef[1]), 4),
            "ground_c": round(float(coef[2]), 4),
            "road_z_mean": None,
        }
        if unmasked_idx.size:
            bins_u = bin_index(depth[unmasked_idx], BIN_WIDTH_M)
            record["bins_unmasked"] = np.bincount(
                bins_u, minlength=N_BINS)[:N_BINS].astype(int).tolist()
            hu = height[unmasked_idx]
            lu = lateral_rel[unmasked_idx]
            record["n_unmasked_below_ground"] = int((hu < HEIGHT_MIN_M).sum())
            record["n_unmasked_above_3m"] = int((hu > HEIGHT_MAX_M).sum())
            record["n_unmasked_wide"] = int((lu > LATERAL_HALF_M).sum())
            record["road_z_mean"] = round(
                float(ground_z_at_points[unmasked_idx].mean()), 3)
        if selected.size:
            sel_depth = depth[selected]
            bins = bin_index(sel_depth, BIN_WIDTH_M)
            counts = np.bincount(bins, minlength=N_BINS)[:N_BINS]
            record["bins_masked"] = counts.astype(int).tolist()
            for bin_id in np.nonzero(counts >= MIN_PTS)[0]:
                members = selected[bins == bin_id]
                labels = angular_dbscan(az[members], el[members])
                clustered = labels[labels >= 0]
                record["clusters_masked"][int(bin_id)] = int(
                    clustered.max() + 1) if clustered.size else 0
            sel_height = height[selected]
            sel_lateral = lateral_rel[selected]
            record["h_hist"] = climb(sel_height, H_EDGES).astype(int).tolist()
            record["y_hist"] = climb(sel_lateral, Y_EDGES).astype(int).tolist()
            record["h_max"] = round(float(sel_height.max()), 3)
            record["y_max"] = round(float(sel_lateral.max()), 3)
            in_box = (sel_depth <= BOX_DEPTH_M) \
                & (sel_lateral <= BOX_WIDTH_M / 2.0) \
                & (sel_height <= BOX_HEIGHT_M)
            record["n_in_box"] = int(in_box.sum())
            record["n_box_height"] = int((sel_height <= BOX_HEIGHT_M).sum())
            record["n_box_width"] = int(
                (sel_lateral <= BOX_WIDTH_M / 2.0).sum())

        # đối chứng: vùng TRƯỚC xe cùng bề ngang/cao (không có spray)
        control = (residual & spray_like
                   & (height >= HEIGHT_MIN_M) & (height <= height_max)
                   & (lateral_rel <= LATERAL_HALF_M)
                   & (along >= front) & (along <= front + CONTROL_DEPTH_M))
        record["n_front"] = int(control.sum())
        record["direction"] = getattr(cfg, "direction", "signal")
        records.append(record)
    return records, ""


def candidate_bags(archive_names: list[str], meta: dict, speed: int,
                   max_candidates: int) -> list[str]:
    """Chọn bag ứng viên cho 1 tốc độ, xoay vòng theo `itr_after_water`."""
    rows = [n for n in archive_names
            if meta.get(Path(n).name, {}).get("speed_kmh") == speed]
    by_water: dict[int, list[str]] = defaultdict(list)
    for name in rows:
        itr = meta[Path(name).name].get("itr_after_water") or 0
        by_water[int(itr)].append(name)
    order: list[str] = []
    keys = sorted(by_water)
    while any(by_water.values()) and len(order) < len(rows):
        for k in keys:
            if by_water[k]:
                order.append(by_water[k].pop(0))
    return order[:max_candidates]


def run(args: argparse.Namespace) -> None:
    meta = measurement_meta(Path(args.xlsx))
    to_velodyne = sensor_to_velodyne(Path(args.meta))
    archive = zipfile.ZipFile(args.zip)
    names = sorted(n for n in archive.namelist() if n.endswith(".bag"))
    tmp_dir = Path(args.tmp)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261119)

    cells: dict[tuple[str, int], list[str]] = defaultdict(list)
    object_by_bag = {Path(n).name: meta.get(Path(n).name, {}).get("object_name")
                     for n in names}
    speeds = [int(v) for v in args.speeds.split(",") if v.strip()]
    rows_out: list[dict] = []
    started = time.time()
    for speed in speeds:
        candidates = candidate_bags(names, meta, speed, args.max_candidates)
        valid = 0
        for name in candidates:
            if valid >= args.target_valid_bags:
                break
            bag_name = Path(name).name
            object_name = object_by_bag.get(bag_name)
            if object_name is None:
                continue
            archive.extract(name, tmp_dir)
            bag_path = tmp_dir / bag_name
            Path(tmp_dir / name).replace(bag_path)
            info = meta[bag_name]
            records, why = process_bag(bag_name, str(bag_path), info,
                                       to_velodyne, rng, args)
            bag_path.unlink()
            if not records:
                print(f"  [{speed} km/h] bỏ {bag_name}: {why}", flush=True)
                continue
            valid += 1
            cells[(str(object_name), speed)].append(bag_name)
            rows_out.extend(records)
            elapsed = time.time() - started
            print(f"[{speed:3d} km/h] {object_name} {bag_name} "
                  f"frames={len(records)} valid={valid} "
                  f"{elapsed:.0f}s", flush=True)
        if valid == 0:
            print(f"  !! KHÔNG ĐO ĐƯỢC {speed} km/h", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        for record in rows_out:
            handle.write(json.dumps(record) + "\n")
    print(f"xong: {len(rows_out)} frame, {len(cells)} ô -> {out}", flush=True)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _trail_edges(rate: np.ndarray, q: float, n_bins: int, width: float,
                 depth_max: float) -> tuple[float, float, float]:
    """Trả (biên trái bin, biên phải bin, nội suy) tại vị trí q của khối lượng.

    Lead T4 yêu cầu `mass90`/`depth_at_mass` là **biên phải** của bin; biên trái
    và nội suy xuất kèm để đối chiếu.
    """
    mass = float(rate.sum())
    if mass <= 0.0:
        return float("nan"), float("nan"), float("nan")
    cum = np.cumsum(rate) / mass
    index = int(np.searchsorted(cum, q, side="left"))
    if index >= n_bins:
        return depth_max, depth_max, depth_max
    before = 0.0 if index == 0 else float(cum[index - 1])
    frac = (q - before) / max(float(cum[index] - before), 1e-12)
    left = index * width
    return float(left), float(left + width), float(left + frac * width)


def _sum_cell(records: list[dict]) -> dict:
    """Gộp các frame của một ô (lớp, tốc độ)."""
    frames = len(records)
    out = {
        "frames": frames,
        "bags": sorted({r["bag"] for r in records}),
        "n_bags": len({r["bag"] for r in records}),
        "bins_masked": np.zeros(N_BINS, dtype=np.int64),
        "bins_unmasked": np.zeros(N_BINS, dtype=np.int64),
        "clusters_masked": np.zeros(N_BINS, dtype=np.int64),
        "obs_frames": np.zeros(N_BINS, dtype=np.int64),
        "h_hist": np.zeros(H_EDGES.size - 1, dtype=np.int64),
        "y_hist": np.zeros(Y_EDGES.size - 1, dtype=np.int64),
        "n_masked": 0, "n_unmasked": 0, "n_in_box": 0, "n_body_removed": 0,
        "n_box_height": 0, "n_box_width": 0, "n_front": 0,
        "n_unmasked_below_ground": 0, "n_unmasked_above_3m": 0,
        "n_unmasked_wide": 0,
        "h_max": 0.0, "y_max": 0.0,
        "road_z": [], "ground": [],
    }
    for record in records:
        out["bins_masked"] += np.asarray(record["bins_masked"], dtype=np.int64)
        out["bins_unmasked"] += np.asarray(record["bins_unmasked"], dtype=np.int64)
        out["clusters_masked"] += np.asarray(record["clusters_masked"], dtype=np.int64)
        out["h_hist"] += np.asarray(record["h_hist"], dtype=np.int64)
        out["y_hist"] += np.asarray(record["y_hist"], dtype=np.int64)
        out["n_masked"] += int(record["n_masked"])
        out["n_body_removed"] += int(record.get("n_body_removed") or 0)
        out["n_unmasked"] += int(record["n_unmasked"])
        out["n_in_box"] += int(record["n_in_box"])
        out["n_box_height"] += int(record["n_box_height"])
        out["n_box_width"] += int(record["n_box_width"])
        out["n_front"] += int(record["n_front"])
        out["n_unmasked_below_ground"] += int(record["n_unmasked_below_ground"])
        out["n_unmasked_above_3m"] += int(record["n_unmasked_above_3m"])
        out["n_unmasked_wide"] += int(record["n_unmasked_wide"])
        out["h_max"] = max(out["h_max"], float(record["h_max"]))
        out["y_max"] = max(out["y_max"], float(record["y_max"]))
        if record.get("road_z_mean") is not None:
            out["road_z"].append(float(record["road_z_mean"]))
        out["ground"].append((float(record["ground_a"]),
                              float(record["ground_b"]),
                              float(record["ground_c"])))
        rear = float(record["rear"])
        for bin_id in range(N_BINS):
            if abs(rear) - (bin_id + 1) * BIN_WIDTH_M > NEAR_FIELD_M:
                out["obs_frames"][bin_id] += 1
    return out


def _cell_metrics(data: dict) -> dict:
    frames = max(data["frames"], 1)
    obs = data["obs_frames"]
    rate_masked = np.divide(data["bins_masked"], obs, out=np.zeros(N_BINS),
                            where=obs > 0)
    rate_unmasked = np.divide(data["bins_unmasked"], obs, out=np.zeros(N_BINS),
                              where=obs > 0)
    cluster_rate = data["clusters_masked"] / frames
    t90 = _trail_edges(rate_masked, 0.90, N_BINS, BIN_WIDTH_M, DEPTH_MAX_M)
    t95 = _trail_edges(rate_masked, 0.95, N_BINS, BIN_WIDTH_M, DEPTH_MAX_M)
    u90 = _trail_edges(rate_unmasked, 0.90, N_BINS, BIN_WIDTH_M, DEPTH_MAX_M)
    u95 = _trail_edges(rate_unmasked, 0.95, N_BINS, BIN_WIDTH_M, DEPTH_MAX_M)
    masked_mass = float(data["bins_masked"].sum())
    unmasked_mass = float(data["bins_unmasked"].sum())
    pct_depth20_masked = (100.0 * data["bins_masked"][: int(BOX_DEPTH_M / BIN_WIDTH_M)].sum()
                          / masked_mass) if masked_mass else float("nan")
    pct_depth20_unmasked = (100.0 * data["bins_unmasked"][: int(BOX_DEPTH_M / BIN_WIDTH_M)].sum()
                            / unmasked_mass) if unmasked_mass else float("nan")
    road_z = float(np.mean(data["road_z"])) if data["road_z"] else float("nan")
    ground = np.mean(np.asarray(data["ground"], dtype=float), axis=0)
    return {
        "n_bags": data["n_bags"], "bags": data["bags"], "frames": frames,
        "det_masked_per_frame": masked_mass / frames,
        "det_unmasked_per_frame": unmasked_mass / frames,
        "clusters_per_frame": float(cluster_rate.sum()),
        "trail90_m": t90[1], "trail90_left_m": t90[0], "trail90_interp_m": t90[2],
        "trail95_m": t95[1], "trail95_left_m": t95[0],
        "trail90_unmasked_m": u90[1], "trail95_unmasked_m": u95[1],
        "trail90_unmasked_left_m": u90[0],
        "pct_depth_le_20_masked": pct_depth20_masked,
        "pct_depth_le_20_unmasked": pct_depth20_unmasked,
        "pct_in_box_strict": 100.0 * data["n_in_box"] / masked_mass if masked_mass else float("nan"),
        "pct_box_height": 100.0 * data["n_box_height"] / masked_mass if masked_mass else float("nan"),
        "pct_box_width": 100.0 * data["n_box_width"] / masked_mass if masked_mass else float("nan"),
        "body_removed_per_frame": data["n_body_removed"] / frames,
        "pct_unmasked_outside_mask": (100.0 * (unmasked_mass - masked_mass)
                                      / unmasked_mass) if unmasked_mass else float("nan"),
        "pct_unmasked_below_ground": (100.0 * data["n_unmasked_below_ground"]
                                      / max(data["n_unmasked"], 1)),
        "pct_unmasked_above_3m": (100.0 * data["n_unmasked_above_3m"]
                                  / max(data["n_unmasked"], 1)),
        "pct_unmasked_wide": (100.0 * data["n_unmasked_wide"]
                              / max(data["n_unmasked"], 1)),
        "h_p50": percentile_from_hist(data["h_hist"], H_EDGES, 50),
        "h_p95": percentile_from_hist(data["h_hist"], H_EDGES, 95),
        "h_max": data["h_max"],
        "y_p50": percentile_from_hist(data["y_hist"], Y_EDGES, 50),
        "y_p95": percentile_from_hist(data["y_hist"], Y_EDGES, 95),
        "y_max": data["y_max"],
        "front_per_frame": data["n_front"] / frames,
        "road_z_mean": road_z,
        "ground_mean": [round(float(v), 4) for v in ground],
        "bins": {
            "lo_m": [i * BIN_WIDTH_M for i in range(N_BINS)],
            "hi_m": [(i + 1) * BIN_WIDTH_M for i in range(N_BINS)],
            "obs_frames": obs.astype(int).tolist(),
            "masked_det_cond_per_frame": rate_masked.round(3).tolist(),
            "unmasked_det_cond_per_frame": rate_unmasked.round(3).tolist(),
            "clusters_per_frame": cluster_rate.round(3).tolist(),
            "cum_masked_pct": (np.cumsum(rate_masked)
                               / max(float(rate_masked.sum()), 1e-12) * 100).round(2).tolist(),
            "cum_unmasked_pct": (np.cumsum(rate_unmasked)
                                 / max(float(rate_unmasked.sum()), 1e-12) * 100).round(2).tolist(),
        },
        "_rate_masked": rate_masked, "_rate_unmasked": rate_unmasked,
    }


def aggregate(args: argparse.Namespace) -> None:
    rows = load_jsonl(Path(args.out))
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for record in rows:
        groups[(str(record["object_name"]), int(record["speed_kmh"]))].append(record)
    summary: dict = {"cells": {}, "pooled": {}, "params": {
        "depth_max_m": DEPTH_MAX_M, "bin_width_m": BIN_WIDTH_M,
        "lateral_half_m": LATERAL_HALF_M, "height_min_m": HEIGHT_MIN_M,
        "height_max_m": rows[0].get("height_max_m", HEIGHT_MAX_M),
        "max_range_m": MAX_RANGE_EXT_M,
        "body_box": bool(rows[0].get("n_body_removed") is not None and
                         getattr(args, "body_box", False)),
        "body_back_extra": getattr(args, "body_back_extra", BODY_MARGIN_M),
        "intensity_max_spray": INTENSITY_MAX_SPRAY,
        "near_field_m": NEAR_FIELD_M,
        "box_strict": [BOX_WIDTH_M, BOX_HEIGHT_M, BOX_DEPTH_M],
        "trail_definition": "biên phải bin tại cumulative 90 % (interp và left xuất kèm)",
        "height_percentile": "histogram 0,1 m, nội suy trong bin",
    }}
    print("## Tổng hợp theo ô (lớp, tốc độ) — 2 biến thể\n")
    print("| lớp | km/h | bag | frame | det/frame masked | det/frame unmasked "
          "| trail90 masked (right) | trail90 unmasked (right) "
          "| %depth≤20 masked | %depth≤20 unmasked | %strict box | "
          "| h p95 | \\|y\\| p95 | road_z |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in sorted(groups, key=lambda k: (k[0], k[1])):
        data = _sum_cell(groups[key])
        cell = _cell_metrics(data)
        summary["cells"][f"{key[0]}_{key[1]}"] = cell
        print(f"| {key[0]} | {key[1]} | {cell['n_bags']} | {cell['frames']} | "
              f"{cell['det_masked_per_frame']:.1f} | {cell['det_unmasked_per_frame']:.1f} | "
              f"{cell['trail90_m']:.1f} m | {cell['trail90_unmasked_m']:.1f} m | "
              f"{cell['pct_depth_le_20_masked']:.1f} % | "
              f"{cell['pct_depth_le_20_unmasked']:.1f} % | "
              f"{cell['pct_in_box_strict']:.1f} % | {cell['h_p95']:.2f} m | "
              f"{cell['y_p95']:.2f} m | {cell['road_z_mean']:.2f} m |")

    print("\n## Depth profile gộp 2 lớp theo tốc độ (hai biến thể cùng bảng)\n")
    for speed in sorted({k[1] for k in groups}):
        records = [r for k in groups if k[1] == speed for r in groups[k]]
        data = _sum_cell(records)
        cell = _cell_metrics(data)
        summary["pooled"][str(speed)] = {k: cell[k] for k in cell if not k.startswith("_")}
        rate_m = cell["_rate_masked"]
        rate_u = cell["_rate_unmasked"]
        cum_m = np.cumsum(rate_m) / max(rate_m.sum(), 1e-12) * 100
        cum_u = np.cumsum(rate_u) / max(rate_u.sum(), 1e-12) * 100
        print(f"### {speed} km/h — {cell['n_bags']} bag, {cell['frames']} frame, "
              f"trail90 masked={cell['trail90_m']:.1f} m / unmasked="
              f"{cell['trail90_unmasked_m']:.1f} m\n")
        print("| bin (m) | masked det/frame | unmasked det/frame | % luỹ kế masked "
              "| % luỹ kế unmasked | frame quan sát |")
        print("|---|---:|---:|---:|---:|---:|")
        for i in range(N_BINS):
            print(f"| {i * BIN_WIDTH_M:.0f}–{(i + 1) * BIN_WIDTH_M:.0f} | "
                  f"{rate_m[i]:.3f} | {rate_u[i]:.3f} | {cum_m[i]:.2f} | "
                  f"{cum_u[i]:.2f} | {int(data['obs_frames'][i])} |")
        print()

    print("\n## Kiểm tra chéo & mask (mỗi tốc độ)\n")
    print("| km/h | %depth≤20 masked | %depth≤20 unmasked | %strict box "
          "| %unmasked ngoài mask | %unmasked dưới mặt đường | road_z mean |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for speed in sorted({k[1] for k in groups}):
        cell = summary["pooled"][str(speed)]
        print(f"| {speed} | {cell['pct_depth_le_20_masked']:.1f} | "
              f"{cell['pct_depth_le_20_unmasked']:.1f} | "
              f"{cell['pct_in_box_strict']:.1f} | "
              f"{cell['pct_unmasked_outside_mask']:.1f} | "
              f"{cell['pct_unmasked_below_ground']:.1f} | "
              f"{cell['road_z_mean']:.2f} |")

    out = Path(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary_pop = summary["pooled"]
    for k in summary_pop:
        summary_pop[k].pop("_rate_masked", None)
        summary_pop[k].pop("_rate_unmasked", None)
    for k in summary["cells"]:
        summary["cells"][k].pop("_rate_masked", None)
        summary["cells"][k].pop("_rate_unmasked", None)
    out.write_text(json.dumps(summary, indent=1))
    print(f"\nsummary -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("run", "aggregate"), default="run")
    parser.add_argument("--zip",
                        default="data/roadspray/Crafter_static.zip")
    parser.add_argument("--xlsx",
                        default="data/roadspray/meta_data_measurement.xlsx")
    parser.add_argument("--meta", default="data/roadspray/meta_data_dataset.json")
    parser.add_argument("--tmp", default=".scratch/roadspray-cal/tmp/bags")
    parser.add_argument("--out",
                        default=".scratch/roadspray-cal/tmp/depth_profile.jsonl")
    parser.add_argument("--summary",
                        default=".scratch/roadspray-cal/tmp/depth_profile_summary.json")
    parser.add_argument("--speeds", default="50,100,130")
    parser.add_argument("--height-max", type=float, default=HEIGHT_MAX_M)
    parser.add_argument("--body-box", action="store_true",
                        help="loại detection nằm trong hộp 3D thân xe (track pose + dims)")
    parser.add_argument("--body-back-extra", type=float, default=BODY_MARGIN_M,
                        help="nới thêm phía sau hộp thân xe [m]")
    parser.add_argument("--direction", choices=("signal", "control"),
                        default="signal", help="signal=receding, control=approaching")
    parser.add_argument("--target-valid-bags", type=int, default=6)
    parser.add_argument("--max-candidates", type=int, default=14)
    args = parser.parse_args()
    args.height_max = float(args.height_max)
    args.body_back_extra = float(args.body_back_extra)
    if args.mode == "run":
        run(args)
    else:
        aggregate(args)


if __name__ == "__main__":
    main()
