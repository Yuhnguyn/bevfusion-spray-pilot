from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np

from spray.wet_ground import WetGroundConfig, apply_wet_ground

# Số điểm/cụm median theo cự ly 3D của tâm cụm trong LiDAR frame [ĐO, ticket 16].
# Ngoại xuy phẳng: mọi cự ly > 30 m dùng 10 (không bịa đường cong mới).
_POINTS_MEDIAN_BY_RANGE: tuple[tuple[float, float, int], ...] = (
    (0.0, 5.0, 30),
    (5.0, 10.0, 20),
    (10.0, 20.0, 14),
    (20.0, 30.0, 10),
    (30.0, float("inf"), 10),
)

# [ĐO] Cụm/frame trên `cal` (DBSCAN 0,7° / minPts 3), theo lớp xe và mốc 10 km/h.
# Ticket 29c mục 7: bảng tra, nội suy tuyến tính; đường cong KHÔNG đơn điệu nên
# không fit `a*(v-v0)`. Bảng gốc: docs/measurements/semantic-spray-clusters-by-speed.md.
_CLUSTER_VISIBLE_BY_SPEED: dict[str, tuple[tuple[float, float], ...]] = {
    "crafter": (
        (50.0, 4.18),
        (60.0, 11.31),
        (70.0, 17.42),
        (80.0, 22.02),
        (90.0, 20.69),
        (100.0, 29.24),
        (110.0, 28.49),
        (120.0, 17.58),
        (130.0, 17.69),
    ),
    "golf": (
        (50.0, 3.62),
        (60.0, 8.84),
        (70.0, 11.36),
        (80.0, 12.87),
        (90.0, 10.51),
        (100.0, 18.07),
        (110.0, 16.69),
        (120.0, 15.27),
        (130.0, 16.64),
    ),
}

# [CHỌN] Mức ẩm chuẩn của dataset: 1 mm — cùng giá trị `PlumeContext.wfh_mm`
# mặc định và mọi phép đo hình học đã công bố. `T_ref` lấy tại mức này.
# Ticket 29e-c đặt tên và đóng vòng: `rate(v) = visible_ref(v) / K(T_ref)` lấy
# `T_ref` tại `WFH_REF_MM`, nên `rate` không phụ thuộc `wfh` của frame.
WFH_REF_MM = 1.0
_REFERENCE_WATER_FILM_M = WFH_REF_MM / 1000.0

# [CODE] profile VLP-32 `update_cycle_time` = 0.1 s — chu kỳ model tham chiếu sinh cụm.
# Dùng để cộng dồn số cụm còn sống qua các chu kỳ (hệ số K, ticket 22).
_UPDATE_CYCLE_TIME_S = 0.1


@dataclass(frozen=True)
class PlumeConfig:
    """Tham số sinh plume.

    Xem docs/history/plume-model-provenance.md

    Ba nhóm giá trị, phân biệt rõ nguồn (xem docs/measurements/semantic-spray-stats.md,
    docs/adr/0003):

    - Cơ chế port từ code tham chiếu đã publish của Linnhoff et al. 2022
      (openMSL/sl-1-2, MPL-2.0): kích hoạt trên 40 km/h, lifetime
      `T = wfh*0,02*(v_kmh - 50) + 0,2`. Số cụm **không** còn lấy từ công thức
      `(0,2*wfh + 0,1) * (v_kmh - 50)` mà từ bảng đo `_CLUSTER_VISIBLE_BY_SPEED`
      (ticket 29c mục 7).
      Chi tiết giá trị + số dòng: docs/history/plume-model-provenance.md.
    - Đo trên SemanticSpray (bản release local): số điểm/cụm median **theo cự ly**
      (`_POINTS_MEDIAN_BY_RANGE`, ticket 16) và bề dày theo tia
      `r_range/r_extent = 1,28` (ticket 16, hiệu chỉnh bằng `radial_squash`).
    - Lựa chọn của repo, không có nguồn ngoài: `water_film_height_m` mặc định
      1 mm (dataset không khai báo độ ướt), bù hình học, biên an toàn.

    `cluster_radius_median_m` giữ 0,30 dù ticket 16 đo median `r_extent` = 0,755 m:
    con số 0,755 là **cận trên** vì single-linkage trên `(x, y)` nối chuỗi các cụm
    gần nhau (`docs/measurements/plume-geometry-vs-real.md` §Caveats), còn profile tham chiếu
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
    # [CODE] profile num_clusters_velocity_offset_kmh = 50.0. Bảng đo `cal` bắt đầu
    # ở mốc 50 km/h; dưới mốc đó không có số đo nên giữ 0 cụm, KHÔNG thêm sàn.
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
    # [ĐO] Nửa bề rộng phân bố ĐỀU của tâm cụm: p95(|y - y_tâm_box|) trên 1.022
    # frame `cal` = 2,22 m; đều trên ±a có p95 = 0,95a ⇒ a = 2,22/0,95 = 2,34 m.
    # Phân bố đều [PAPER] §III-B, không phải Gaussian.
    lateral_half_width_m: float = 2.34
    box_margin_m: float = 0.2
    intensity: float = 0.0
    # Cột 5 là ring index; điểm tổng hợp gán ring 0; không dùng cho occlusion.
    ring: float = 0.0
    # [ĐO] Khối phun sau đuôi: rộng 3,4 m, cao 5–92 % chiều cao box, đáy = đáy
    # box + 5 % chiều cao box. Số đo trên `cal`: đỉnh khối thực tế ~90 % chiều
    # cao box, thân khối bắt đầu ngay trên mặt đường. Chỉ đường stateful
    # (ticket 28b/29c) đọc. 29e-c trả về đúng dải 0,05–0,92 đã đo.
    #
    # ClassVar cố ý: `spray/config/plume_default.yaml` phải là bản sao khít của
    # mọi field dataclass (tests/test_plume_config_yaml.py). Vẫn đọc được qua
    # `config.tail_block_width_m` v.v.
    water_film_height_mm: ClassVar[float] = 1.0
    tail_block_width_m: ClassVar[float] = 3.4
    tail_block_height_frac: ClassVar[tuple[float, float]] = (0.05, 0.92)


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
    wet_points_in: int = 0
    wet_mean_ratio: float = 0.0
    # Ray-casting counters, filled by ``PlumeTransform`` from ``RaycastStats``.
    det: int = 0
    beams_hit: int = 0
    att_m_total: float = 0.0
    att_real_points: int = 0


@dataclass
class PlumeResult:
    points: np.ndarray
    points_clean: np.ndarray
    injected: np.ndarray
    stats: PlumeStats


def _visible_table(vehicle_class: str) -> tuple[np.ndarray, np.ndarray]:
    try:
        rows = _CLUSTER_VISIBLE_BY_SPEED[vehicle_class.lower()]
    except KeyError as exc:
        known = ", ".join(sorted(_CLUSTER_VISIBLE_BY_SPEED))
        raise ValueError(
            f"unknown vehicle class {vehicle_class!r}; expected one of {known}"
        ) from exc
    speeds = np.asarray([row[0] for row in rows], dtype=np.float64)
    visible = np.asarray([row[1] for row in rows], dtype=np.float64)
    return speeds, visible


def cluster_visible_target_for_speed(
    speed_kmh: float, vehicle_class: str = "crafter"
) -> float:
    """Cụm/frame **nhìn thấy** đo trên ``cal``, nội suy tuyến tính theo tốc độ.

    Bảng ``_CLUSTER_VISIBLE_BY_SPEED`` (ticket 29c mục 7). Đường cong không đơn
    điệu nên chỉ nội suy giữa các mốc 10 km/h, không fit hàm. Dưới mốc 50 km/h
    không có số đo ⇒ 0; trên 130 km/h giữ giá trị mốc cuối.
    """
    speeds, visible = _visible_table(vehicle_class)
    if speed_kmh < speeds[0]:
        return 0.0
    return float(np.interp(float(speed_kmh), speeds, visible))


def cluster_rate_for_speed(
    speed_kmh: float,
    config: PlumeConfig | None = None,
    vehicle_class: str = "crafter",
) -> float:
    """Số cụm **sinh mỗi chu kỳ** ``Δt = 0,1 s`` để khớp số cụm/frame đo được.

    ``rate(v) = visible_ref(v) / K(T_ref(v))`` — **không** chứa ``wfh``; độ ẩm
    chỉ tác động qua ``T`` khi caller tính số cụm hiển thị. ``T_ref`` lấy tại
    mức ẩm chuẩn của dataset (1 mm), để ``rate`` không đổi khi caller đổi ``wfh``.
    """
    cfg = config or PlumeConfig()
    visible_ref = cluster_visible_target_for_speed(speed_kmh, vehicle_class)
    if visible_ref <= 0.0:
        return 0.0
    reference = replace(cfg, water_film_height_m=_REFERENCE_WATER_FILM_M)
    k_ref = steady_state_cluster_factor(speed_kmh, reference)
    return visible_ref / k_ref


def visible_cluster_count_for_speed(
    speed_kmh: float,
    config: PlumeConfig | None = None,
    vehicle_class: str = "crafter",
) -> int:
    """Số cụm **nhìn thấy trong một frame** = ``round(rate × K(T(wfh, v)))``."""
    cfg = config or PlumeConfig()
    if speed_kmh <= cfg.min_speed_kmh or cfg.water_film_height_m <= 0.0:
        return 0
    rate = cluster_rate_for_speed(speed_kmh, cfg, vehicle_class)
    if rate <= 0.0:
        return 0
    visible = rate * steady_state_cluster_factor(speed_kmh, cfg)
    return int(np.floor(visible + 0.5))


def cluster_count_for_speed(
    speed_kmh: float,
    config: PlumeConfig | None = None,
    vehicle_class: str = "crafter",
) -> int:
    """Số cụm nhìn thấy trong một frame cho một box (bảng đo ``cal``, ticket 29c).

    Giữ tên cũ cho caller hiện có. Mặc định lớp ``Crafter`` (lớp duy nhất paper
    định lượng); ``Golf`` có bảng riêng và phải chọn tường minh.
    """
    return visible_cluster_count_for_speed(speed_kmh, config, vehicle_class)


def lifetime_time_constant(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """[CODE] dee.cpp:530 — hằng số thời gian ``T`` (giây) của cụm.

    ``T = 0,02·wfh_mm·(v − 50) + 0,2``. ``water_film_height_m`` is stored in
    metres (``0.001`` = 1 mm); the reference formula is in millimetres, so the
    field is converted here. Before ticket 29e it was used as if it already
    were millimetres, which made ``T`` collapse to ``0.2 s`` at every speed.
    """
    cfg = config or PlumeConfig()
    wfh_mm = 1000.0 * cfg.water_film_height_m
    return (
        cfg.lifetime_water_film_coeff
        * wfh_mm
        * (speed_kmh - cfg.cluster_count_velocity_offset_kmh)
        + cfg.lifetime_base_s
    )


def steady_state_factor(
    time_constant: float,
    *,
    dt: float = _UPDATE_CYCLE_TIME_S,
    max_age_factor: float = 4.0,
) -> float:
    """``K = Σ_{k=0}^{4T/Δt} exp(-k·Δt/T)`` cho một ``T`` bất kỳ (giây).

    Tách khỏi ``steady_state_cluster_factor`` để caller có thể truyền ``T`` đã
    tính theo đơn vị khác mà không lặp lại công thức cấp số nhân.
    """
    if time_constant <= 0.0:
        return 0.0
    steps = int(np.floor(max_age_factor * time_constant / dt))
    k = np.arange(steps + 1, dtype=np.float64)
    return float(np.exp(-k * dt / time_constant).sum())


def steady_state_cluster_factor(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """Hệ số tích luỹ ``K`` của số cụm ở trạng thái dừng (ticket 22).

    ``T = lifetime_time_constant(v)`` (dee.cpp:530), ``Δt = 0,1 s`` từ profile
    ``update_cycle_time``. Với ``T = 0,2 s`` → ``K ≈ 2,51``; không hard-code vì
    ``T`` tăng nhẹ theo tốc độ.
    """
    cfg = config or PlumeConfig()
    return steady_state_factor(
        lifetime_time_constant(speed_kmh, cfg),
        max_age_factor=cfg.lifetime_max_age_factor,
    )


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
    ``cluster_count_for_speed`` = ``round(rate × K)``, với ``rate`` lấy từ bảng
    đo ``cal`` và ``K`` là tổng cấp số nhân của xác suất sống ``exp(-age/T)``
    trên ``[0, 4T]`` (ticket 29c mục 7). Generator chạy per-frame, không có
    state qua frame; **không** còn dropout ``age ~ U(0,4T)`` vì suy giảm lifetime
    đã nằm trong ``K`` (ticket 22). Deterministic theo ``seed``/``token``.
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
            lateral = _lateral_offset(rng, cfg.lateral_half_width_m)
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

    budget = _injected_budget(len(clean))
    if len(injected) > budget:
        keep = rng.choice(len(injected), budget, replace=False)
        keep.sort()
        stats.capped = len(injected) - budget
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


def inject_plume_stateful(
    points: np.ndarray,
    boxes: np.ndarray,
    context,
    state,
    *,
    seed: int,
    token: str = "",
    config: PlumeConfig | None = None,
    dt: float = _UPDATE_CYCLE_TIME_S,
    wet_ground: WetGroundConfig | None = None,
    vehicle_class: str = "crafter",
) -> PlumeResult:
    """Add a plume that keeps clusters alive across frames.

    Each call advances and prunes the existing clusters once, then spawns this
    frame's clusters inside a block behind every box:

    - clusters carry a ground-frame velocity, so the ego velocity
      ``[ego_speed_mps, 0, 0]`` is passed to ``advance`` and only the position
      integration happens in the ego frame;
    - block length ``|v_abs| * dt``, width 3.4 m, height ``0.05–0.92`` of the
      box height (ticket 29e-c);
    - block centre ``box_pos - (L_box/2 + L_block/2) * [cos yaw, sin yaw]``;
    - the block bottom sits at 5 % of the box height above the box bottom;
    - clusters are removed once they rise above the box top, so the rise from
      ``initial_vz`` cannot leave the plume tall after the box disappears;
    - ``|y - y_block|`` is clamped to 2.43 m every step (ticket 29e-c).

    Clusters are materialised as points of radius ``cluster.radius`` with the
    per-range point count from ``_POINTS_MEDIAN_BY_RANGE``, ``intensity = 0``
    and ``ring = -1`` (not assigned yet). The marker line is printed once per
    call.
    """
    cfg = config or PlumeConfig()
    clean = _as_five_columns(points)
    if wet_ground is not None and wet_ground.enabled:
        base, wet_stats = apply_wet_ground(
            clean,
            road_z_m=context.road_z_m,
            wfh_mm=context.wfh_mm,
            config=wet_ground,
        )
    else:
        base = clean
        wet_stats = None
    box_arr = _as_boxes(boxes)
    rng = _rng(seed, token or context.scene_token)
    stats = PlumeStats()

    state.advance(
        dt, ego_velocity=np.array([context.ego_speed_mps, 0.0, 0.0])
    )
    ceilings = {}
    for index, box in enumerate(box_arr):
        if np.isfinite(box[:7]).all():
            ceilings[index] = float(box[2] + box[5] / 2.0)
    expired = state.prune(ceilings=ceilings)

    block_length = abs(float(context.object_speed_mps)) * dt
    spawned = 0
    assumed = False
    for index, box in enumerate(box_arr):
        if not np.isfinite(box[:7]).all():
            continue
        if not _in_range(box[:3], cfg.point_cloud_range):
            continue

        x, y, z = (float(value) for value in box[:3])
        _, length, height, yaw = (float(value) for value in box[3:7])
        offset = length / 2.0 + block_length / 2.0
        frac_lo, frac_hi = cfg.tail_block_height_frac
        box_bottom = z - height / 2.0
        block_bottom = box_bottom + frac_lo * height
        block_top = box_bottom + frac_hi * height
        center = np.array(
            [
                x - offset * np.cos(yaw),
                y - offset * np.sin(yaw),
                0.5 * (block_bottom + block_top),
            ],
            dtype=np.float64,
        )
        extents = np.array(
            [
                block_length / 2.0,
                cfg.tail_block_width_m / 2.0,
                0.5 * (block_top - block_bottom),
            ],
            dtype=np.float64,
        )

        created = state.spawn(
            context,
            object_id=index,
            rng=rng,
            dt=dt,
            center=center,
            extents=extents,
            vehicle_class=vehicle_class,
        )
        if created:
            stats.eligible_boxes += 1
            stats.clusters_spawned += len(created)
            spawned += len(created)
            assumed = assumed or any(
                cluster.velocity_assumed for cluster in created
            )

    chunks: list[np.ndarray] = []
    for cluster in state.all_alive():
        distance = float(np.linalg.norm(cluster.pos))
        count = _count_for_distance(rng, distance, cfg)
        offsets = _ball(rng, count, cluster.radius)
        if distance > 0.0:
            offsets = _thin_radial(
                offsets, cluster.pos / distance, cfg.radial_squash
            )
        cloud = np.empty((count, 5), dtype=np.float32)
        cloud[:, 0:3] = offsets + cluster.pos
        cloud[:, 3] = 0.0
        cloud[:, 4] = -1.0
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

    budget = _injected_budget(len(clean))
    if len(injected) > budget:
        keep = rng.choice(len(injected), budget, replace=False)
        keep.sort()
        stats.capped = len(injected) - budget
        injected = injected[keep]

    stats.injected = int(len(injected))
    if wet_stats is not None:
        stats.wet_points_in = wet_stats.points_in
        stats.wet_mean_ratio = wet_stats.mean_ratio
    augmented = (
        np.concatenate([base, injected], axis=0)
        if len(injected)
        else base.copy()
    )

    print(
        "PLUME_STATE "
        f"scene={token or context.scene_token} "
        f"frame={context.frame_index} "
        f"spawned={spawned} "
        f"alive={state.counters.alive} "
        f"expired={expired} "
        f"capped={stats.capped} "
        f"assumed={1 if assumed else 0}"
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


def _lateral_offset(rng: np.random.Generator, half_width: float) -> float:
    """Tâm cụm lệch ngang ~ **phân bố đều** trên ``±half_width`` [PAPER] §III-B."""
    return float(rng.uniform(-half_width, half_width))


def _injected_budget(real_point_count: int) -> int:
    """Ngân sách điểm plume mỗi frame: ``max(500, round(0,05 × N_thật))``.

    Thay trần tuyệt đối 2.000 (lỗi D7): hình học đúng cho 807–1.555 điểm/frame,
    trần cũ cắt oan frame dày. Sàn 500 giữ frame thưa vẫn có plume.
    """
    return max(500, int(round(0.05 * int(real_point_count))))


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
    # 9 cột: (x, y, z, w, l, h, yaw, vx, vy), w = ngang, l = dọc yaw — nuscenes_converter.py:250
    cx, cy, cz, width, length, height, yaw = (float(v) for v in box[:7])
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    cos_yaw = np.cos(-yaw)
    sin_yaw = np.sin(-yaw)
    local_x = dx * cos_yaw - dy * sin_yaw
    local_y = dx * sin_yaw + dy * cos_yaw
    return (
        (np.abs(local_x) <= length / 2.0 + margin)
        & (np.abs(local_y) <= width / 2.0 + margin)
        & (points[:, 2] >= cz - height / 2.0 - margin)
        & (points[:, 2] <= cz + height / 2.0 + margin)
    )