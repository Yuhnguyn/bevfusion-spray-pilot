from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlumeConfig:
    point_cloud_range: tuple[float, float, float, float, float, float] = (
        -54.0,
        -54.0,
        -5.0,
        54.0,
        54.0,
        3.0,
    )
    min_speed_kmh: float = 30.0
    clusters_per_kmh: float = 0.08
    max_clusters_per_box: int = 6
    cluster_radius_m: float = 0.35
    points_per_cluster: int = 32
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
        if speed_kmh < cfg.min_speed_kmh:
            stats.skipped_low_speed += 1
            continue

        n_clusters = int(round(cfg.clusters_per_kmh * speed_kmh))
        n_clusters = min(max(n_clusters, 1), cfg.max_clusters_per_box)
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
            offsets = _ball(rng, cfg.points_per_cluster, cfg.cluster_radius_m)
            cloud = np.empty((cfg.points_per_cluster, 5), dtype=np.float32)
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
