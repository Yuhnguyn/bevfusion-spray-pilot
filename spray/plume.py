from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from typing import ClassVar

import numpy as np

from spray.plume_context import sample_wfh_mm
from spray.wet_ground import WetGroundConfig, apply_wet_ground

# Số điểm/cụm median theo cự ly 3D của tâm cụm trong khung LiDAR [ĐO].
# Ngoại suy phẳng: mọi cự ly > 30 m dùng 10 (không bịa đường cong mới).
_POINTS_MEDIAN_BY_RANGE: tuple[tuple[float, float, int], ...] = (
    (0.0, 5.0, 30),
    (5.0, 10.0, 20),
    (10.0, 20.0, 14),
    (20.0, 30.0, 10),
    (30.0, float("inf"), 10),
)

# [ĐO] Cụm/frame trên RoadSpray `*_static` — nguồn calibration độc lập của ADR-0006 D2
# (DBSCAN 0,7° / minPts 3, lát chuẩn thức Δ = 1,0 m).
#
# Đơn vị = số cụm **nhìn thấy** trong một frame; `rate` = bảng / K (xem
# cluster_rate_for_speed). Mốc 50/100/130 đo trực tiếp trên
# `.scratch/roadspray-cal/tmp/a3_targets_static.json` (key `"{v}_1.0"`, field `cpf`:
# 9,04 / 35,86 / 33,08); 6 mốc 10 km/h còn lại nội suy tuyến tính.
#
# Dải bất định **±30–40 %** do định nghĩa vùng (Δ từ 1,0 → 6,0 m), không phải do mẫu —
# cổng B phải đọc cùng dải này.
#
# Golf: chưa có phép đo static Δ=1,0 tương ứng; các giá trị dưới đây là Δ=2,5 cũ, nên
# **không cùng chuẩn** với Crafter. Lý do + toàn bộ lịch sử đổi nguồn: `docs/adr/decision-log.md`
# (ADR-0006 D2).
_CLUSTER_VISIBLE_BY_SPEED: dict[str, tuple[tuple[float, float], ...]] = {
    "crafter": (
        # Đích cụm/frame, lát Δ=1,0 m [ĐO]: 9,04 @50 · 35,86 @100 · 33,08 @130
        # (a3_targets_static.json, đo trên plume_crafter_v5.jsonl, lọc
        # 18 ≤ car_range ≤ 38 m). 6 mốc còn lại nội suy tuyến tính.
        (50.0, 9.04),
        (60.0, 14.40),
        (70.0, 19.77),
        (80.0, 25.13),
        (90.0, 30.50),
        (100.0, 35.86),
        (110.0, 34.93),
        (120.0, 34.01),
        (130.0, 33.08),
    ),
    "golf": (
        (50.0, 4.73),
        (60.0, 8.79),
        (70.0, 13.19),
        (80.0, 17.80),
        (90.0, 20.88),
        (100.0, 22.56),
        (110.0, 21.95),
        (120.0, 25.75),
        (130.0, 25.18),
    ),
}

# [CHỌN] Mức ẩm chuẩn 1 mm — neo để tách `alive = rate × K` thành hai thừa số.
# `rate` tính tại mức này nên không phụ thuộc `wfh` của frame; `wfh` chỉ tác động
# qua `T`. Vì sao phải neo + bất nhất với bảng: `docs/adr/decision-log.md` (29e-c).
WFH_REF_MM = 1.0

# Vùng **SINH** cụm: slab ngay sau đuôi xe, dài = |v|·Δt (1,4 m @50 · 2,8 @100 ·
# 3,6 @130), rộng 3,4 m, cao 1,5 m tính từ mặt đường. Paper chỉ nói phân bố đều
# "in the region behind every moving object", không cho kích thước ⇒ lấy từ
# `define_spray_volumes()` của code tác giả + hộp đo calibration static.
SPAWN_BOX_WIDTH_M = 3.4
SPAWN_BOX_HEIGHT_M = 1.5
_REFERENCE_WATER_FILM_M = WFH_REF_MM / 1000.0

# [CODE] profile VLP-32 `update_cycle_time` = 0,1 s — chu kỳ sinh cụm, cũng là `Δt`
# trong `K = 1/(1−exp(−Δt/T))`.
_UPDATE_CYCLE_TIME_S = 0.1


@dataclass(frozen=True)
class PlumeConfig:
    """Tham số sinh plume.

    Xem docs/history/plume-model-provenance.md

    Ba nhóm giá trị, phân biệt rõ nguồn (xem docs/measurements/semantic-spray-stats.md,
    docs/adr/0003):

    - Cơ chế port từ code tham chiếu của Linnhoff et al. 2022
      (openMSL/sl-1-2, MPL-2.0): kích hoạt trên 40 km/h, lifetime
      `T = 0,02·wfh_mm·(v_kmh − 50) + 0,2`. Số cụm lấy từ bảng đo
      `_CLUSTER_VISIBLE_BY_SPEED`, không từ công thức.
    - Đo trên SemanticSpray: số điểm/cụm median **theo cự ly**
      (`_POINTS_MEDIAN_BY_RANGE`) và bề dày theo tia `r_range/r_extent = 1,28`
      (hiệu chỉnh bằng `radial_squash`).
    - Lựa chọn của repo, không có nguồn ngoài: `water_film_height_m` mặc định
      1 mm (dataset không khai báo độ ướt), bù hình học, biên an toàn.

    `cluster_radius_median_m` = 0,30 dù phép đo single-linkage cho `r_extent`
    median 0,755 m: con số 0,755 là **cận trên** vì single-linkage trên `(x, y)`
    nối chuỗi các cụm gần nhau; paper Fig. 5 cho lognormal μ=−1,2, σ=0,8 ⇒
    median 0,30.
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
    # Trần **SỐ HỌC** 12·T, không phải mô hình: paper Eq. 1 cho cụm tan theo xác
    # suất P(age) = exp(−age/T); exp(−12) = 6e−6 nên trần này chỉ cắt phần đuôi
    # không còn ý nghĩa (< 1 cụm trên 10⁵).
    lifetime_max_age_factor: float = 12.0
    # Số điểm mỗi cụm: lognormal quanh median theo cự ly, sigma chọn để p90 ~ 40.
    # Trường `points_per_cluster_median` giữ lại cho tương thích constructor; generator
    # không đọc nữa vì median giờ phụ thuộc cự ly (ticket 16), xem
    # `_POINTS_MEDIAN_BY_RANGE`. 17 vẫn là median gộp của mọi cụm [ĐO].
    points_per_cluster_median: float = 17.0
    points_per_cluster_sigma: float = 0.67
    points_per_cluster_bounds: tuple[int, int] = (3, 200)
    # Bán kính cụm: lognormal median 0,30 m (paper Fig. 5, μ=−1,2, σ=0,8).
    cluster_radius_median_m: float = 0.30
    cluster_radius_sigma: float = 0.8
    # Paper KHÔNG đặt trần cho `r_cl`. Đây là **clip SỐ HỌC** ở p99 của chính
    # lognormal đó — `exp(−1,2 + 2,326·0,72) = 1,94 m` ⇒ 2,00 m. Không phải
    # ràng buộc của paper, và không dùng trần 4,0 m của cơ chế tán xạ (đã bỏ).
    cluster_radius_bounds_m: tuple[float, float] = (0.10, 2.00)
    # Hệ số bẹp cụm dọc theo tia (hướng từ gốc LiDAR tới tâm cụm). Khối cầu đặc
    # vô hạn điểm cho S = 0,64, nhưng cụm chỉ có vài chục điểm rời rạc nên max |p|
    # hụt so với biên ellipsoid; S = 0,885 hiệu chỉnh để median
    # per-cluster `r_range/r_extent` = 1,28 như số đo. Đây là `[CHỌN]`, không có
    # trong paper.
    radial_squash: float = 0.885
    distance_range_m: tuple[float, float] = (1.0, 10.0)
    height_range_m: tuple[float, float] = (0.2, 2.0)
    # Nửa bề rộng phân bố ĐỀU của tâm cụm: p95(|y − y_tâm_box|) đo được 2,22 m;
    # đều trên ±a có p95 = 0,95a ⇒ a = 2,34 m. [PAPER] §III-B: phân bố đều.
    lateral_half_width_m: float = 2.34
    box_margin_m: float = 0.2
    intensity: float = 0.0
    # Cột 5 là ring index; điểm tổng hợp gán ring 0; không dùng cho occlusion.
    ring: float = 0.0
    # ClassVar: ba hằng số dưới đây KHÔNG phải field của dataclass nên không đi
    # qua `PlumeConfig(...)` hay `asdict()`. Chúng giữ lại vì
    # `scripts/diag_verify_conventions.py` và 2 test đọc qua
    # `PlumeConfig.<name>`. Đường production đọc `SPAWN_BOX_*` ở đầu module.
    water_film_height_mm: ClassVar[float] = 1.0
    tail_block_width_m: ClassVar[float] = 3.4
    tail_block_height_frac: ClassVar[tuple[float, float]] = (0.05, 0.92)


@dataclass
class PlumeStats:
    eligible_boxes: int = 0
    skipped_no_velocity: int = 0
    skipped_low_speed: int = 0
    clusters_spawned: int = 0
    # Giữ field cho tương thích; luôn 0 — suy giảm nằm trong hệ số `K`.
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

    Bảng ``_CLUSTER_VISIBLE_BY_SPEED``. Đường cong không đơn
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

    ``rate(v) = visible_ref(v) / K(T_ref(v))`` với ``K = 1/(1−exp(−Δt/T))``
    [PAPER] Eq. 1 — **không** chứa ``wfh``; độ ẩm chỉ tác động qua ``T`` khi
    caller tính số cụm hiển thị. ``T_ref`` lấy tại ``WFH_REF_MM`` (1 mm) để
    ``rate`` không đổi khi caller đổi ``wfh`` — lý do phải neo: xem
    `docs/adr/decision-log.md` (29e-c).
    """
    cfg = config or PlumeConfig()
    visible_ref = cluster_visible_target_for_speed(speed_kmh, vehicle_class)
    if visible_ref <= 0.0:
        return 0.0
    reference = replace(cfg, water_film_height_m=_REFERENCE_WATER_FILM_M)
    k_ref = steady_state_alive_factor(speed_kmh, reference)
    return visible_ref / k_ref


def visible_cluster_count_for_speed(
    speed_kmh: float,
    config: PlumeConfig | None = None,
    vehicle_class: str = "crafter",
) -> int:
    """Số cụm **nhìn thấy trong một frame** = ``round(rate × K)`` [PAPER] Eq. 1.

    Hệ số nhân :func:`steady_state_alive_factor` = ``K``, đúng bằng tuổi kỳ vọng
    của một cụm tính theo frame (``prune`` tan theo xác suất).
    """
    cfg = config or PlumeConfig()
    if speed_kmh <= cfg.min_speed_kmh or cfg.water_film_height_m <= 0.0:
        return 0
    rate = cluster_rate_for_speed(speed_kmh, cfg, vehicle_class)
    if rate <= 0.0:
        return 0
    visible = rate * steady_state_alive_factor(speed_kmh, cfg)
    return int(np.floor(visible + 0.5))


def cluster_count_for_speed(
    speed_kmh: float,
    config: PlumeConfig | None = None,
    vehicle_class: str = "crafter",
) -> int:
    """Số cụm nhìn thấy trong một frame cho một box, đọc từ bảng cụm/frame.

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
    field is converted here. (Dùng như milimét sẽ làm ``T`` sập về 0,2 s.)
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
) -> float:
    """``K = Σ_{k≥0} exp(−k·Δt/T) = 1 / (1 − exp(−Δt/T))`` [PAPER] Eq. 1.

    Cụm tan theo **xác suất** ``P = exp(−Δt/T)`` mỗi bước, nên hệ số tích luỹ là
    tổng cấp số nhân **vô hạn**; ``max_age_factor`` không xuất hiện trong công
    thức (trần số học ``12·T`` chỉ chặn đuôi, ảnh hưởng < 1e−5).
    """
    if time_constant <= 0.0:
        return 0.0
    return float(1.0 / (1.0 - np.exp(-dt / time_constant)))


def steady_state_cluster_factor(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """Hệ số tích luỹ ``K = Σ exp(−k·Δt/T) = 1/(1−exp(−Δt/T))`` [PAPER] Eq. 1.

    ``T = lifetime_time_constant(v)`` `[CODE]`, ``Δt = 0,1 s``. Với ``T = 0,2 s``
    ⇒ ``K ≈ 2,51``. ``alive = arrival × K``.

    Giá trị **bằng** :func:`steady_state_alive_factor`; hai tên giữ lại vì caller
    cũ dùng cả hai.
    """
    cfg = config or PlumeConfig()
    return steady_state_factor(lifetime_time_constant(speed_kmh, cfg))


def steady_state_alive_factor(
    speed_kmh: float, config: PlumeConfig | None = None
) -> float:
    """Số frame kỳ vọng một cụm còn sống = ``K = 1/(1−exp(−Δt/T))``.

    ``prune()`` cho cụm tan với xác suất ``P = exp(−Δt/T)`` mỗi bước [PAPER]
    Eq. 1 ⇒ tuổi kỳ vọng ``T/Δt`` frame, chính là tổng cấp số nhân ``K``.

    Hệ số đổi ``visible`` (số cụm/frame đo được) ↔ ``rate`` (số cụm sinh mỗi chu
    kỳ): ``arrival = visible / K``, ``alive = arrival × K = visible``.
    """
    cfg = config or PlumeConfig()
    return steady_state_factor(lifetime_time_constant(speed_kmh, cfg))


def inject_plume(
    points: np.ndarray,
    boxes: np.ndarray,
    *,
    seed: int,
    token: str = "",
    config: PlumeConfig | None = None,
) -> PlumeResult:
    """Thêm cụm plume vào sau các box đang chạy — đường **stateless**.

    Mỗi frame dựng lại plume từ đầu: **không** có state qua frame, **không** có
    tuổi, **không** có vệt. Đường production KHÔNG dùng hàm này —
    :func:`inject_plume_stateful` mới là đường sống (``plume_transform.py``), và
    ``PlumeTransform`` cũng không gọi hàm này. Chỉ ``scripts/probe_sspp_plume.py``
    và test dùng.

    Số cụm mỗi box = ``cluster_count_for_speed`` = ``round(rate × K)``, ``rate``
    từ bảng cụm/frame và ``K`` là tổng cấp số nhân của xác suất sống
    ``exp(−age/T)`` [PAPER] Eq. 1. Suy giảm lifetime đã nằm trong ``K``.
    Deterministic theo ``seed``/``token``.
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
            count = _count_for_distance(rng, d, cfg, radius)
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


def replace_context_wfh(context, wfh_mm: float):
    """``PlumeContext`` với ``wfh_mm`` khác — frozen nên phải dựng lại."""
    return replace(context, wfh_mm=float(wfh_mm))


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
    """Thêm plume có cụm SỐNG qua nhiều frame — đường production.

    Mỗi call: ``advance()`` + ``prune()`` cụm đang sống một lần, rồi sinh cụm
    của frame này trong khối sau mỗi box.

    - Cụm mang vận tốc **hệ mặt đất**, nên ``advance`` nhận
      ``[ego_speed_mps, 0, 0]`` và chỉ phần tích phân vị trí chạy trong hệ ego.
    - Khối sinh: dài ``|v_abs| · dt``, rộng 3,4 m, cao 1,5 m tính từ **mặt
      đường** (không theo chiều cao box). Tâm khối đặt ngay sau mặt đuôi.
    - Không có trần chiều cao và không có ``vz`` ban đầu [PAPER], nên chiều cao
      plume đến **thuần** từ vị trí khối sinh.
    - Cụm tan theo xác suất ``exp(−Δt/T)`` [PAPER] Eq. 1, trần số học ``12·T``.
    - Không có clamp ngang.

    Box theo quy ước adapter (``spray/sspp_adapter.py:117,141``): ``box[2]`` là
    **đáy** box (không phải tâm), ``box[3]`` dài dọc yaw, ``box[4]`` rộng ngang
    yaw.

    Hàm **materialise** cụm thành điểm (bán kính ``cluster.radius``, số điểm
    theo ``_POINTS_MEDIAN_BY_RANGE``) nhưng đường production **vứt phần đó đi**:
    ``PlumeTransform`` chỉ dùng ``points_clean`` + cụm hình cầu cho raycast.
    Marker ``PLUME_STATE`` in một dòng mỗi call.
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
    expired = state.prune(dt=dt, rng=rng)

    # [MIỀN — ADR-0006 §5.7] Miền mô hình paper đã kiểm chứng — MẶC ĐỊNH BẬT.
    # Chỉ còn một thứ phải bật/tắt: mức ẩm lấy mẫu theo SCENE. Tắt bằng
    # PLUME_LEGACY_DOMAIN=1 để tái lập hành vi cũ (không giới hạn miền, wfh cố định).
    if os.environ.get("PLUME_LEGACY_DOMAIN", "").strip() not in ("", "0"):
        state._config = replace(
            state._config,
            min_range_m=0.0,
            max_range_m=float("inf"),
        )
    else:
        # [PAPER §V] mức ẩm lấy mẫu theo SCENE (không theo frame) — xem sample_wfh_mm.
        context = replace_context_wfh(context, sample_wfh_mm(
            context.scene_token, context.epoch, seed
        ))

    spawned = 0
    assumed = False
    for index, box in enumerate(box_arr):
        if not np.isfinite(box[:7]).all():
            continue
        if not _in_range(box[:3], cfg.point_cloud_range):
            continue

        # 9 cột theo spray/sspp_adapter.py:117,141: box[2] = ĐÁY box (không phải
        # tâm), box[3] = dài (dọc yaw), box[4] = rộng (ngang yaw), box[5] = cao.
        x, y, z = (float(value) for value in box[:3])
        length, _, _, yaw = (float(value) for value in box[3:7])
        # Khối sinh = slab |v|·Δt ngay sau đuôi xe (SPAWN_BOX_* ở đầu module).
        forward = np.array([np.cos(yaw), np.sin(yaw), 0.0],
                           dtype=np.float64)
        rear = np.array([x, y, z], dtype=np.float64) - forward * (length / 2.0)
        slab_length = abs(float(context.object_speed_mps)) * dt
        center = np.array(
            [
                rear[0] - forward[0] * slab_length / 2.0,
                rear[1] - forward[1] * slab_length / 2.0,
                float(context.road_z_m) + SPAWN_BOX_HEIGHT_M / 2.0,
            ],
            dtype=np.float64,
        )
        extents = np.array(
            [
                slab_length / 2.0,
                SPAWN_BOX_WIDTH_M / 2.0,
                SPAWN_BOX_HEIGHT_M / 2.0,
            ],
            dtype=np.float64,
        )

        if state.needs_warm_start(context.scene_token):
            state.warm_start(
                context,
                object_id=index,
                rng=rng,
                dt=dt,
                center=center,
                extents=extents,
                vehicle_class=vehicle_class,
                direction=np.array([np.cos(yaw), np.sin(yaw), 0.0]),
            )
        created = state.spawn(
            context,
            object_id=index,
            rng=rng,
            dt=dt,
            center=center,
            extents=extents,
            vehicle_class=vehicle_class,
            direction=np.array([np.cos(yaw), np.sin(yaw), 0.0]),
        )
        if created:
            stats.eligible_boxes += 1
            stats.clusters_spawned += len(created)
            spawned += len(created)
            assumed = assumed or any(
                cluster.velocity_assumed for cluster in created
            )

    chunks: list[np.ndarray] = []
    for cluster in state.select_alive():
        distance = float(np.linalg.norm(cluster.pos))
        count = _count_for_distance(rng, distance, cfg, cluster.radius)
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
    rng: np.random.Generator,
    distance: float,
    cfg: PlumeConfig,
    radius: float | None = None,
) -> int:
    """Số điểm một cụm, **tỉ lệ với tiết diện quả cầu** như mô hình paper.

    Paper mô hình cụm là quả cầu và *suy ra* số detection từ giao tia × ``P_det``,
    nên cụm to hơn bị nhiều tia cắt qua hơn: số điểm ∝ ``r²``. Bản port trước đây
    lấy ``count`` **độc lập với** ``radius`` (hai lần lấy mẫu rời nhau) — đó là lỗi
    mô hình chứ không phải lựa chọn: nó bỏ mất cơ chế duy nhất khiến đuôi phân bố
    dài ra. `[ĐO] 2026-11-19`: bảng median theo cự ly giữ nguyên (đã hiệu chỉnh ở
    bán kính median), thêm hệ số ``(r / r_median)²``; vì ``r`` là lognormal
    ``σ = 0,8`` (Linnhoff Fig. 5) nên ``r²`` cho ``σ_hiệu_dụng = 1,6`` **không cần
    thêm tham số tự do nào**.
    """
    median = _points_median_for_distance(distance)
    spread = 1.0
    if radius is not None and cfg.cluster_radius_median_m > 0.0:
        spread = (radius / cfg.cluster_radius_median_m) ** 2.0
    value = round(
        median
        * spread
        * float(np.exp(cfg.points_per_cluster_sigma * rng.normal()))
    )
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
    # 9 cột theo adapter (spray/sspp_adapter.py:117,141):
    # (x, y, z_bottom, size_x, size_y, size_z, yaw, vx, vy) trong đó
    # box[2] = ĐÁY box, box[3] = DÀI (dọc yaw), box[4] = RỘNG (ngang yaw).
    cx, cy, cz, length, width, height, yaw = (float(v) for v in box[:7])
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    cos_yaw = np.cos(-yaw)
    sin_yaw = np.sin(-yaw)
    local_x = dx * cos_yaw - dy * sin_yaw
    local_y = dx * sin_yaw + dy * cos_yaw
    return (
        (np.abs(local_x) <= length / 2.0 + margin)
        & (np.abs(local_y) <= width / 2.0 + margin)
        & (points[:, 2] >= cz - margin)
        & (points[:, 2] <= cz + height + margin)
    )