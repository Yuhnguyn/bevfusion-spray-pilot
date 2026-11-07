from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

# Số điểm/cụm median theo cự ly 3D của tâm cụm trong LiDAR frame [ĐO, ticket 16].
# Ngoại xuy phẳng: mọi cự ly > 30 m dùng 10 (không bịa đường cong mới).
_POINTS_MEDIAN_BY_RANGE: tuple[tuple[float, float, int], ...] = (
    (0.0, 5.0, 30),
    (5.0, 10.0, 20),
    (10.0, 20.0, 14),
    (20.0, 30.0, 10),
    (30.0, float("inf"), 10),
)

# [CODE] dee.cpp:509–512 — mean = (0.2*wfh + 0.1) * (v_kmh - 50).
_CLUSTER_COUNT_WFH_COEFF = 0.2
_CLUSTER_COUNT_BASE = 0.1

# [CODE] profile VLP-32 `update_cycle_time` = 0.1 s — chu kỳ model tham chiếu sinh cụm.
# Dùng để cộng dồn số cụm còn sống qua các chu kỳ (hệ số K, ticket 22).
_UPDATE_CYCLE_TIME_S = 0.1


@dataclass(frozen=True)
class PlumeConfig:
    """Tham số sinh plume.

    Xem docs/plume-model-provenance.md

    Ba nhóm giá trị, phân biệt rõ nguồn (xem docs/semantic-spray-stats.md,
    docs/adr/0003):

    - Cơ chế port từ code tham chiếu đã publish của Linnhoff et al. 2022
      (openMSL/sl-1-2, MPL-2.0): kích hoạt trên 40 km/h, số cụm
      `(0,2*wfh + 0,1) * (v_kmh - 50)`, lifetime `T = wfh*0,02*(v_kmh - 50) + 0,2`.
      Chi tiết giá trị + số dòng: docs/plume-model-provenance.md.
    - Đo trên SemanticSpray (bản release local): số điểm/cụm median **theo cự ly**
      (`_POINTS_MEDIAN_BY_RANGE`, ticket 16) và bề dày theo tia
      `r_range/r_extent = 1,28` (ticket 16, hiệu chỉnh bằng `radial_squash`).
    - Lựa chọn của repo, không có nguồn ngoài: `water_film_height_m` mặc định
      1 mm (dataset không khai báo độ ướt), bù hình học, biên an toàn.

    `cluster_radius_median_m` giữ 0,30 dù ticket 16 đo median `r_extent` = 0,755 m:
    con số 0,755 là **cận trên** vì single-linkage trên `(x, y)` nối chuỗi các cụm
    gần nhau (`docs/plume-geometry-vs-real.md` §Caveats), còn profile tham chiếu
    cho lognormal μ=-1,2 σ=0,8 → median 0,30.
    """

    point_cloud_range: tuple[float, float, float, float, float, float] = (
        -54.0,
        -54.0,
        -5.0,
        54.0,
        54.0,
        3.0,
    )
    # [CODE] DetectionEnvironmentalEffects.cpp:502,:554 — spray chỉ kích hoạt khi
    # object_velocity > 40/3.6 m/s VÀ water_film_height > 0. Đây là ngưỡng KÍCH HOẠT,
    # không phải offset của công thức số cụm (offset là 50 km/h, xem dưới).
    min_speed_kmh: float = 40.0
    # [CHỌN] OSI không cho default, dataset không khai báo độ ướt. Giả định 1 mm
    # (mặt đường ướt đều) — phải ghi rõ ở mọi báo cáo dùng generator.
    water_film_height_m: float = 0.001
    # [CODE] profile num_clusters_velocity_offset_kmh = 50.0. Ở v ≤ 50 km/h
    # công thức cho 0 cụm; KHÔNG thêm sàn.
    cluster_count_velocity_offset_kmh: float = 50.0
    # [CODE] dee.cpp:530 — time_constant = wfh*0.02*(v_kmh - 50) + 0.2 (giây).
    lifetime_water_film_coeff: float = 0.02
    lifetime_base_s: float = 0.2
    # [CODE] dee.cpp:446 — cụm bị xoá khi age > 4 * time_constant.
    lifetime_max_age_factor: float = 4.0
    # Số điểm mỗi cụm: lognormal quanh median theo cự ly, sigma chọn để p90 ~ 40.
    # Trường `points_per_cluster_median` giữ lại cho tương thích constructor; generator
    # không đọc nữa vì median giờ phụ thuộc cự ly (ticket 16), xem
    # `_POINTS_MEDIAN_BY_RANGE`. 17 vẫn là median gộp của mọi cụm [ĐO].
    points_per_cluster_median: float = 17.0
    points_per_cluster_sigma: float = 0.67
    points_per_cluster_bounds: tuple[int, int] = (3, 200)
    # Bán kính cụm: lognormal median 0,30 m (Linnhoff Fig. 5, μ=-1,2 sigma=0,8).
    # Giữ 0,30 dù ticket 16 đo median r_extent = 0,755 m: single-linkage trên (x, y)
    # nối chuỗi các cụm gần nhau nên 0,755 là CẬN TRÊN; paper Fig. 5 cho đúng 0,30.
    cluster_radius_median_m: float = 0.30
    cluster_radius_sigma: float = 0.8
    # [CODE] dee.cpp:528 — code tham chiếu cắt `std::min(1.0f, ...)`; trần 1,0 m.
    cluster_radius_bounds_m: tuple[float, float] = (0.10, 1.00)
    # Hệ số bẹp cụm dọc theo tia (hướng từ gốc LiDAR tới tâm cụm).
    # Công thức liên tục cho khối cầu đặc vô hạn điểm: S = 1,28/2 = 0,64.
    # Nhưng cụm chỉ có vài chục điểm rời rạc, nên max |p| hụt so với biên ellipsoid:
    # S = 0,64 chỉ cho median per-cluster r_range/r_extent ~0,98 (quá mỏng).
    # Vì vậy S được hiệu chỉnh thực nghiệm: quét S trên ≥900 cụm, nhiều seed,
    # d = 8–30 m, chọn giá trị cho median per-cluster r_range/r_extent = 1,28
    # đúng như ticket 16 đo. S hiệu dụng = 0,885 (khác 0,64 vì lý do rời rạc trên).
    radial_squash: float = 0.885
    distance_range_m: tuple[float, float] = (1.0, 10.0)
    height_range_m: tuple[float, float] = (0.2, 2.0)
    lateral_sigma_m: float = 0.5
    box_margin_m: float = 0.2
    max_injected_points: int = 2000
    intensity: float = 0.0
    # Cột 5 là ring index; điểm tổng hợp gán ring 0; không dùng cho occlusion.
    ring: float = 0.0


@dataclass
class PlumeStats:
    eligible_boxes: int = 0
    skipped_no_velocity: int = 0
    skipped_low_speed: int = 0
    clusters_spawned: int = 0
    # Giữ field cho tương thích; luôn 0 từ ticket 22 (dropout đã bỏ, suy giảm nằm trong K).
    clusters_dropped_lifetime: int = 0
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
    """Số cụm **nhìn thấy trong một frame** cho một box ở tốc độ cho trước.

    [CODE] DetectionEnvironmentalEffects.cpp:502,:554 (kích hoạt trên 40 km/h và
    wfh > 0) và :509–512 (``mean = (0.2*wfh + 0.1) * (v_kmh - 50)``). ``mean`` là
    số cụm **sinh mỗi chu kỳ** ``Δt = 0,1 s``; số cụm trong frame ở trạng thái
    dừng là ``round(mean × K)`` với ``K = steady_state_cluster_factor`` (ticket 22).
    Ở ``v ≤ 50 km/h`` công thức cho 0 cụm — giữ đúng 0.
    """
    cfg = config or PlumeConfig()
    if speed_kmh <= cfg.min_speed_kmh or cfg.water_film_height_m <= 0.0:
        return 0
    mean = (
        _CLUSTER_COUNT_WFH_COEFF * cfg.water_film_height_m + _CLUSTER_COUNT_BASE
    ) * (speed_kmh - cfg.cluster_count_velocity_offset_kmh)
    if mean <= 0.0:
        return 0
    visible = mean * steady_state_cluster_factor(speed_kmh, cfg)
    return int(np.floor(visible + 0.5))


def lifetime_time_constant(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """[CODE] dee.cpp:530 — hằng số thời gian ``T`` (giây) của cụm."""
    cfg = config or PlumeConfig()
    return (
        cfg.lifetime_water_film_coeff
        * cfg.water_film_height_m
        * (speed_kmh - cfg.cluster_count_velocity_offset_kmh)
        + cfg.lifetime_base_s
    )


def steady_state_cluster_factor(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """Hệ số tích luỹ ``K`` của số cụm ở trạng thái dừng (ticket 22).

    Cụm sinh mỗi chu kỳ ``Δt`` sống với xác suất ``exp(-age/T)`` và bị xoá khi
    ``age > 4T``, nên số cụm còn lại trong một frame là tổng cấp số nhân:

        K = Σ_{k=0}^{4T/Δt} exp(-k·Δt/T)

    ``T = lifetime_time_constant(v)`` (dee.cpp:530), ``Δt = 0,1 s`` từ profile
    ``update_cycle_time``. Với ``T = 0,2 s`` → ``K ≈ 2,51``; không hard-code vì
    ``T`` tăng nhẹ theo tốc độ.
    """
    cfg = config or PlumeConfig()
    time_constant = lifetime_time_constant(speed_kmh, cfg)
    steps = int(
        np.floor(cfg.lifetime_max_age_factor * time_constant / _UPDATE_CYCLE_TIME_S)
    )
    k = np.arange(steps + 1, dtype=np.float64)
    return float(np.exp(-k * _UPDATE_CYCLE_TIME_S / time_constant).sum())


def inject_plume(
    points: np.ndarray,
    boxes: np.ndarray,
    *,
    seed: int,
    token: str = "",
    config: PlumeConfig | None = None,
) -> PlumeResult:
    """Thêm cụm plume vào sau các box đang chạy.

    Số cụm mỗi box là số cụm **nhìn thấy trong một frame** ở trạng thái dừng:
    ``cluster_count_for_speed`` = ``round(mean × K)``, với ``K`` là tổng cấp số
    nhân của xác suất sống ``exp(-age/T)`` trên ``[0, 4T]``. Generator chạy
    per-frame, không có state qua frame; **không** còn dropout ``age ~ U(0,4T)``
    vì suy giảm lifetime đã nằm trong ``K`` (ticket 22). Deterministic theo
    ``seed``/``token``.
    """
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
            stats.clusters_spawned += 1
            distance = rng.uniform(*cfg.distance_range_m)
            lateral = rng.normal(0.0, cfg.lateral_sigma_m)
            z = rng.uniform(*cfg.height_range_m)
            center = (
                np.asarray(box[:2], dtype=np.float64)
                + direction * distance
                + perp * lateral
            )
            center3 = np.array([center[0], center[1], z], dtype=np.float64)
            d = float(np.linalg.norm(center3))
            radius = _lognormal_clipped(
                rng,
                cfg.cluster_radius_median_m,
                cfg.cluster_radius_sigma,
                cfg.cluster_radius_bounds_m,
            )
            count = _count_for_distance(rng, d, cfg)
            offsets = _ball(rng, count, radius)
            if d > 0.0:
                offsets = _thin_radial(offsets, center3 / d, cfg.radial_squash)
            cloud = np.empty((count, 5), dtype=np.float32)
            cloud[:, 0] = offsets[:, 0] + center[0]
            cloud[:, 1] = offsets[:, 1] + center[1]
            cloud[:, 2] = offsets[:, 2] + z
            cloud[:, 3] = cfg.intensity
            cloud[:, 4] = cfg.ring
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


def _points_median_for_distance(distance: float) -> int:
    for lo, hi, median in _POINTS_MEDIAN_BY_RANGE:
        if lo <= distance < hi:
            return median
    return _POINTS_MEDIAN_BY_RANGE[-1][2]


def _count_for_distance(
    rng: np.random.Generator, distance: float, cfg: PlumeConfig
) -> int:
    median = _points_median_for_distance(distance)
    value = round(median * float(np.exp(cfg.points_per_cluster_sigma * rng.normal())))
    lo, hi = cfg.points_per_cluster_bounds
    return int(min(max(value, lo), hi))


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


def _thin_radial(offsets: np.ndarray, u: np.ndarray, squash: float) -> np.ndarray:
    """Ép offset dọc theo tia ``u`` với hệ số ``squash`` (bỏ thành phần dọc tia)."""
    along = offsets @ u
    return offsets - (1.0 - squash) * along[:, None] * u[None, :]


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