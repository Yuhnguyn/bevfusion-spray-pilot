from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlumeConfig:
    """Tham số sinh plume.

    Ba nhóm giá trị, phân biệt rõ nguồn (xem docs/semantic-spray-stats.md,
    docs/adr/0003):

    - Hiệu chỉnh theo Linnhoff et al. 2022 (arXiv 2212.08558): ngưỡng tốc độ
      50 km/h, phân bố lognormal của bán kính cụm và số điểm/cụm.
    - Đo trên SemanticSpray (bản release local): số cụm dense mỗi frame.
    - Lựa chọn của repo, không có nguồn ngoài: bù hình học, biên an toàn.
    """

    point_cloud_range: tuple[float, float, float, float, float, float] = (
        -54.0,
        -54.0,
        -5.0,
        54.0,
        54.0,
        3.0,
    )
    # Linnhoff §III-A: spray bắt đầu ở 50 km/h.
    min_speed_kmh: float = 50.0
    # Dung sai để 50,0 km/h không bị loại vì làm tròn float32
    # (float32(50/3.6)*3.6 = 50.0000015, nhưng float32(30/3.6)*3.6 = 29.999999).
    speed_epsilon_kmh: float = 1e-3
    # Số cụm tăng tuyến tính theo tốc độ; hai đầu là lựa chọn của repo, được
    # chọn để khớp dense clusters/frame median = 5 của SemanticSpray ở dải giữa.
    clusters_speed_bounds_kmh: tuple[float, float] = (50.0, 130.0)
    clusters_at_speed_bounds: tuple[int, int] = (2, 8)
    # Số điểm mỗi cụm: lognormal, median 17 (đo được), sigma chọn để p90 ~ 40.
    points_per_cluster_median: float = 17.0
    points_per_cluster_sigma: float = 0.67
    points_per_cluster_bounds: tuple[int, int] = (3, 200)
    # Bán kính cụm: lognormal median 0,30 m (Linnhoff Fig. 5, μ=-1,2 sigma=0,8).
    cluster_radius_median_m: float = 0.30
    cluster_radius_sigma: float = 0.8
    cluster_radius_bounds_m: tuple[float, float] = (0.10, 1.50)
    distance_range_m: tuple[float, float] = (1.0, 10.0)
    height_range_m: tuple[float, float] = (0.2, 2.0)
    lateral_sigma_m: float = 0.5
    box_margin_m: float = 0.2
    max_injected_points: int = 2000
    intensity: float = 0.0
    time_lag: float = 0.0


@dataclass
class PlumeStats:
    eligible_boxes: int = 0
    skipped_no_velocity: int = 0
    skipped_low_speed: int = 0
    clusters: int = 0
    injected: int = 0
    rejected_range: int = 0
    rejected_box: int = 0
    capped: int = 0


@dataclass
class PlumeResult:
    points: np.ndarray
    points_clean: np.ndarray
    injected: np.ndarray
    stats: PlumeStats


def cluster_count_for_speed(speed_kmh: float, config: PlumeConfig | None = None) -> int:
    """Số cụm cho một box ở tốc độ cho trước (0 nếu dưới ngưỡng)."""
    cfg = config or PlumeConfig()
    if speed_kmh < cfg.min_speed_kmh - cfg.speed_epsilon_kmh:
        return 0
    lo_speed, hi_speed = cfg.clusters_speed_bounds_kmh
    lo_count, hi_count = cfg.clusters_at_speed_bounds
    if hi_speed <= lo_speed:
        return lo_count
    t = (speed_kmh - lo_speed) / (hi_speed - lo_speed)
    t = min(max(t, 0.0), 1.0)
    return int(round(lo_count + t * (hi_count - lo_count)))


def inject_plume(
    points: np.ndarray,
    boxes: np.ndarray,
    *,
    seed: int,
    token: str = "",
    config: PlumeConfig | None = None,
) -> PlumeResult:
    cfg = config or PlumeConfig()
    clean = _as_five_columns(points)
    box_arr = _as_boxes(boxes)
    rng = _rng(seed, token)
    stats = PlumeStats()
    chunks: list[np.ndarray] = []
    has_velocity = box_arr.shape[1] >= 9

    for box in box_arr:
        if not np.isfinite(box[:7]).all():
            continue
        if not _in_range(box[:3], cfg.point_cloud_range):
            continue
        if not has_velocity:
            stats.skipped_no_velocity += 1
            continue
        vx, vy = float(box[7]), float(box[8])
        if not np.isfinite(vx) or not np.isfinite(vy):
            stats.skipped_no_velocity += 1
            continue
        speed = float(np.hypot(vx, vy))
        if speed <= 1e-6:
            stats.skipped_no_velocity += 1
            continue
        speed_kmh = speed * 3.6
        n_clusters = cluster_count_for_speed(speed_kmh, cfg)
        if n_clusters == 0:
            stats.skipped_low_speed += 1
            continue

        stats.eligible_boxes += 1
        direction = -np.array([vx, vy], dtype=np.float64) / speed
        perp = np.array([-direction[1], direction[0]])

        for _ in range(n_clusters):
            distance = rng.uniform(*cfg.distance_range_m)
            lateral = rng.normal(0.0, cfg.lateral_sigma_m)
            z = rng.uniform(*cfg.height_range_m)
            center = (
                np.asarray(box[:2], dtype=np.float64)
                + direction * distance
                + perp * lateral
            )
            radius = _lognormal_clipped(
                rng,
                cfg.cluster_radius_median_m,
                cfg.cluster_radius_sigma,
                cfg.cluster_radius_bounds_m,
            )
            count = int(
                round(
                    _lognormal_clipped(
                        rng,
                        cfg.points_per_cluster_median,
                        cfg.points_per_cluster_sigma,
                        (
                            float(cfg.points_per_cluster_bounds[0]),
                            float(cfg.points_per_cluster_bounds[1]),
                        ),
                    )
                )
            )
            offsets = _ball(rng, count, radius)
            cloud = np.empty((count, 5), dtype=np.float32)
            cloud[:, 0] = offsets[:, 0] + center[0]
            cloud[:, 1] = offsets[:, 1] + center[1]
            cloud[:, 2] = offsets[:, 2] + z
            cloud[:, 3] = cfg.intensity
            cloud[:, 4] = cfg.time_lag
            chunks.append(cloud)
            stats.clusters += 1

    injected = (
        np.concatenate(chunks, axis=0)
        if chunks
        else np.empty((0, 5), dtype=np.float32)
    )

    x_min, y_min, z_min, x_max, y_max, z_max = cfg.point_cloud_range
    in_range = (
        (injected[:, 0] >= x_min)
        & (injected[:, 0] <= x_max)
        & (injected[:, 1] >= y_min)
        & (injected[:, 1] <= y_max)
        & (injected[:, 2] >= z_min)
        & (injected[:, 2] <= z_max)
    )
    stats.rejected_range = int((~in_range).sum())
    injected = injected[in_range]

    if len(injected) and len(box_arr):
        inside = np.zeros(len(injected), dtype=bool)
        for box in box_arr:
            if not np.isfinite(box[:7]).all():
                continue
            inside |= _inside_box(injected, box, cfg.box_margin_m)
        stats.rejected_box = int(inside.sum())
        injected = injected[~inside]

    if len(injected) > cfg.max_injected_points:
        keep = rng.choice(len(injected), cfg.max_injected_points, replace=False)
        keep.sort()
        stats.capped = len(injected) - cfg.max_injected_points
        injected = injected[keep]

    stats.injected = int(len(injected))
    augmented = (
        np.concatenate([clean, injected], axis=0) if len(injected) else clean.copy()
    )
    return PlumeResult(
        points=augmented,
        points_clean=clean.copy(),
        injected=injected,
        stats=stats,
    )


def _as_five_columns(points: np.ndarray) -> np.ndarray:
    arr = np.asarray(points)
    if arr.ndim != 2 or arr.shape[1] not in (4, 5):
        raise ValueError("points must have shape (N, 4) or (N, 5)")
    if arr.shape[1] == 4:
        arr = np.concatenate(
            [arr, np.zeros((arr.shape[0], 1), dtype=arr.dtype)], axis=1
        )
    return arr.astype(np.float32, copy=True)


def _as_boxes(boxes: np.ndarray) -> np.ndarray:
    arr = np.asarray(boxes, dtype=np.float32)
    if arr.size == 0:
        return arr.reshape(0, 9)
    if arr.ndim != 2 or arr.shape[1] < 7:
        raise ValueError("boxes must have shape (M, >=7)")
    return arr


def _rng(seed: int, token: str) -> np.random.Generator:
    digest = hashlib.blake2b(
        f"{token}:{seed}".encode("utf-8"), digest_size=8
    ).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))


def _in_range(
    point: np.ndarray,
    bounds: tuple[float, float, float, float, float, float],
) -> bool:
    x_min, y_min, z_min, x_max, y_max, z_max = bounds
    return (
        x_min <= point[0] <= x_max
        and y_min <= point[1] <= y_max
        and z_min <= point[2] <= z_max
    )


def _lognormal_clipped(
    rng: np.random.Generator,
    median: float,
    sigma: float,
    bounds: tuple[float, float],
) -> float:
    """Lognormal với median cho trước, kẹp vào bounds."""
    lo, hi = bounds
    value = median * float(np.exp(sigma * rng.normal()))
    return float(min(max(value, lo), hi))


def _ball(
    rng: np.random.Generator, count: int, radius: float
) -> np.ndarray:
    vec = rng.normal(size=(count, 3))
    norms = np.linalg.norm(vec, axis=1, keepdims=True)
    vec = np.divide(vec, norms, out=np.zeros_like(vec), where=norms > 0)
    scale = radius * rng.random((count, 1)) ** (1.0 / 3.0)
    return (vec * scale).astype(np.float32)


def _inside_box(points: np.ndarray, box: np.ndarray, margin: float) -> np.ndarray:
    cx, cy, cz, width, length, height, yaw = (float(v) for v in box[:7])
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    cos_yaw = np.cos(-yaw)
    sin_yaw = np.sin(-yaw)
    local_x = dx * cos_yaw - dy * sin_yaw
    local_y = dx * sin_yaw + dy * cos_yaw
    return (
        (np.abs(local_x) <= width / 2.0 + margin)
        & (np.abs(local_y) <= length / 2.0 + margin)
        & (points[:, 2] >= cz - height / 2.0 - margin)
        & (points[:, 2] <= cz + height / 2.0 + margin)
    )