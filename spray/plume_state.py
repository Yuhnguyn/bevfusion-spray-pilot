"""Time-varying state of spray clusters: spawn, advect and expire.

The v1 generator rebuilds the plume from scratch every frame, so no cluster has
an age and there is no trail behind the lead vehicle. This module keeps the
clusters alive across frames.

Frames of reference (corrected in ticket 28c):

- clusters carry their velocity in the **ground frame**, not relative to the
  ego. The paper sets the object velocity as the initial cluster velocity and
  the reference implementation advects in world coordinates, rendering into
  the sensor frame only afterwards (``dee.cpp:396-426``, ``:250``).
- drag acts in the ground frame: ``v_air = v_ground - wind``.
- positions live in the **ego frame**: ``pos += (vel - ego_velocity) * dt``.
  The ego is what the LiDAR sees, so this is the render frame.

What makes the trail long is the drag, not the relative speed: ``|v_air|^2``
for a cluster moving at road speed is of order 1300 m^2/s^2, so ``-0.15 * |air|^2``
removes tens of m/s within the first cycles. A cluster spawned while ego and
lead vehicle move at the same speed ends up ~0 relative velocity at birth and
then falls far behind in the ego frame.

Two speeds, two roles:

- ``v_abs`` = ``context.object_speed_mps``, the lead vehicle's speed over the
  road. It drives the number of clusters spawned per cycle and the lifetime
  ``T``: the amount of water thrown up scales with the wet road the tyres cross
  every second.
- the ground velocity is ``object_velocity_ego_mps + [ego_speed, 0, 0]``: the
  object's own velocity carried into the ground frame by the ego's motion.

``wfh_mm`` is in millimetres for both the cluster count and ``T``. Passing
metres by mistake gives a different count on purpose (pinned by a test).

Sign conventions follow the reference implementation
``DetectionEnvironmentalEffects.cpp`` (openMSL/sl-1-2, MPL-2.0):

- clusters spawn with ``age = -dt`` so they are not active on their birth frame;
- ``T ~ N(wfh_mm*0.02*(v_abs_kmh - 50) + 0.2, 0.2)``, clamped at zero;
- drag uses the paper's constant coefficient ``C = -0.15 1/m`` [PAPER] arXiv
  2212.08558, acting as ``v += C * v_air_hat * |v_air|^2 * dt`` with
  ``v_air = v_cluster - wind``. The reference code (``dee.cpp:542``) draws
  ``N(-0.12; 0.04)`` per cluster instead; we deliberately follow the paper and
  default the sampling knobs to a constant.
- a cluster is removed once ``age > 4*T``;
- the displayed survival probability is ``P_t = exp(-age/T)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spray.plume import (
    PlumeConfig,
    cluster_rate_for_speed,
    steady_state_alive_factor,
    steady_state_cluster_factor,
)

# [CODE] dee.cpp:509-512 and the VLP-32 profile (num_clusters_velocity_offset_kmh).
CLUSTER_COUNT_WFH_COEFF = 0.2
CLUSTER_COUNT_BASE = 0.1
VELOCITY_OFFSET_KMH = 50.0
# [CODE] DetectionEnvironmentalEffects.cpp: activate above 40 km/h and wfh > 0.
ACTIVATION_SPEED_KMH = 40.0
# [CODE] dee.cpp:530 and hpp:47.
LIFETIME_WFH_COEFF = 0.02
LIFETIME_BASE_S = 0.2
LIFETIME_SIGMA_S = 0.2
# [CODE] dee.cpp:446.
MAX_AGE_FACTOR = 4.0
# [PAPER] Linnhoff Fig. 5: ``r_cl`` là **một** phân bố lognormal duy nhất,
# median 0,30 m (mu = -1,2), sigma ~0,8 — paper KHÔNG cho bán kính phụ thuộc tốc độ.
#
# `[ĐO] 2026-11-19` — đo lại trên **RoadSpray `*_static`**, cột bề dày lát **Δ=1,0 m**
# (cột chuẩn thức; xem docs/measurements/roadspray-static-clusters-by-speed.md §6):
#
#     v=50  km/h -> r50 = 0,349 m, sigma = 0,754
#     v=100 km/h -> r50 = 0,292 m, sigma = 0,727
#     v=130 km/h -> r50 = 0,311 m, sigma = 0,711
# (9 tốc độ: r50 0,288–0,349; rsig median 0,720, dải 0,701–0,771 — xem
#  .scratch/roadspray-cal/tmp/plume_crafter_v5.jsonl, lọc 18–38 m.)
#
# Ba mốc gần như KHÔNG phụ thuộc tốc độ (0,29–0,35 m) và trùng paper (0,30 m)
# ⇒ dùng MỘT hằng số, đúng như paper.
#
# Vì sao bảng theo tốc độ trước đây (0,45–0,70 m) bị bỏ: nó lấy từ cột **Δ=2,5 m**,
# cột đó bị chain-merging dọc tia làm phình 1,6–2,1×. Số điểm tỉ lệ tiết diện (r²)
# nên phần phình này từng làm khối lượng plume sai ~5×.
RADIUS_MU = -1.2
RADIUS_SIGMA = 0.72
# [BỎ CLIP 1,0 m 2026-11-19 — paper-faithful] Paper định nghĩa r_cl = khoảng cách
# xa nhất từ tâm cụm tới detection ⇒ đuôi lognormal là THẬT, không bị cắt.
# Với mu = -1,2, sigma = 0,72: p99 = exp(-1,2 + 2,326*0,72) = 1,94 m. Clip 1,0 m
# (ticket 23, từ dee.cpp:528 — là code tham chiếu, không phải paper) cắt đúng phần
# đuôi tạo ra các cụm lớn mà đích static Δ=1,0 có (p95 172 điểm/cụm @50 km/h).
RADIUS_MAX_M = 2.0
# [ĐO] trung vị 3 mốc static Δ=1,0 = 0,311 m; paper = 0,301 m — lấy 0,31.
# (D5 — bảng 9 tốc độ Δ=1,0 — sẽ áp ở Mốc 4 sau khi đo lại survival.)
RADIUS_MEDIAN_M = 0.31


def cluster_radius_median_for_speed(speed_kmh: float) -> float:
    """Trung vị bán kính cụm (m) — **hằng số**, không phụ thuộc tốc độ.

    Giữ hàm để call site không đổi. Tham số tốc độ được bỏ qua có chủ ý: cả paper
    (một lognormal) lẫn phép đo static Δ=1,0 đều cho bán kính không đổi theo tốc độ.
    """
    del speed_kmh
    return RADIUS_MEDIAN_M


# [PAPER] arXiv 2212.08558 Sec. III-C: no vertical initial velocity; v0 = object
# velocity, purely horizontal. The paper has no gravity and no z equation, so a
# cluster never rises on its own (ticket 29h). ``dee.cpp:540`` does draw a
# ``vz``, but that is the reference code, not the paper. The spawn line
# ``vz = rng.uniform(0, cfg.initial_vz_max_mps)`` is kept: to re-enable it,
# change this constant only.
INITIAL_VZ_MAX_MPS = 0.0
# [PAPER] arXiv 2212.08558, Sec. III-C: drag coefficient C = -0.15 1/m,
# constant. See the module docstring for how this differs from dee.cpp:542.
DRAG_MEAN = -0.15
DRAG_STD = 0.0
# [CODE] dee.cpp wind: 2 m/s from 208 deg in meteorological convention.
WIND_SPEED_MPS = 2.0
WIND_FROM_DEG = 208.0
# [CODE] profile VLP-32 update_cycle_time.
DEFAULT_DT_S = 0.1

# Placeholder spawn jitter around the sensor origin; 28b replaces it with the
# real block behind the vehicle tail. Only seed determinism matters here.
_SPAWN_JITTER_HALF_M = 0.5


@dataclass(frozen=True)
class PlumeStateConfig:
    """Stochastic knobs of the cluster state, with reference defaults.

    The model constants live in the module; this config only lets tests and
    the caller pin distributions or change the wind. Drag defaults to the
    paper's constant (``drag_std = 0``), but the knobs stay so a caller can
    still sample it.

    ``radius_mu`` / ``radius_sigma`` are the paper's lognormal for ``r_cl``.
    """

    lifetime_sigma_s: float = LIFETIME_SIGMA_S
    max_age_factor: float = MAX_AGE_FACTOR
    radius_mu: float = RADIUS_MU
    radius_sigma: float = RADIUS_SIGMA
    radius_max_m: float = RADIUS_MAX_M
    initial_vz_max_mps: float = INITIAL_VZ_MAX_MPS
    drag_mean: float = DRAG_MEAN
    drag_std: float = DRAG_STD
    wind_speed_mps: float = WIND_SPEED_MPS
    wind_from_deg: float = WIND_FROM_DEG
    # Overdispersion (A3): 0 = đặt đều trong hộp như paper ("uniform
    # distribution ... chosen as a first estimate", §III-B); >0 = đặt quanh
    # `placement_knots` tâm knot với sigma `placement_knot_sigma_m`, tạo các
    # đám dày để cụm chồng nhau thành chuỗi. Không có trong paper — đây là
    # [CHỌN] dựa trên đo: plume thật có 1-2 chuỗi ~1000 điểm mỗi frame.
    placement_knots: int = 0
    placement_knot_sigma_m: float = 0.25
    # [CHỌN] Nguồn phát spray CỐ ĐỊNH theo vật thể (A3 việc 1).
    # Vật lý: nước bắn từ LỐP SAU, không phải rải đều trên cả mặt cắt 3,4 m.
    # Hai nguồn hẹp ⇒ cụm của các chu kỳ liên tiếp chồng lên nhau quanh cùng
    # một đường ⇒ nối thành chuỗi ("băng nước") như dữ liệu thật, thay vì mỗi
    # cụm đứng rời. `source_count=0` = tắt, quay lại rải đều trong hộp.
    # [CHỌN] Hệ số nhân số cụm sinh — núm hiệu chỉnh của A3 việc 2.
    # Lý do cần: bảng `visible` là số **detection-cluster** đo trên dữ liệu thật,
    # nhưng code đang dùng nó làm số **quả cầu sống**; nhiều quả cầu gộp thành một
    # detection-cluster nên cần nhiều cầu hơn bảng để khớp ở tầng detector.
    # `[ĐO] 2026-11-19`: hệ số 3,0 làm `det/frame` và cụm/frame khớp bảng ở
    # 100 km/h (det 777 vs 875; share ≥50đ 88,9 % vs 82 %; p95 355 vs 182). Bảng
    # `visible` là số **detection-cluster** nên phải sinh nhiều cầu hơn mới đạt.
    spawn_scale: float = 1.0
    # `[CHỌN] — ĐÃ TẮT 2026-11-19 sau khi đối chiếu paper.` Ý tưởng "nguồn phát ở
    # hai bánh sau" là của tôi, KHÔNG có trong paper: Paper A L393-395 nói
    # *"spheres are positioned with a uniform distribution in the region behind
    # every moving object"*, và code tác giả dùng hộp RỘNG 3,4 m (cả mặt cắt đuôi
    # xe). Bật 2 nguồn ±0,85 m làm điểm dồn thành hai vệt bánh — thấy rõ trong
    # clip; người dùng đã chỉ ra đúng. Mặc định 0 = rải đều như paper.
    source_count: int = 0
    # [KHÔNG DÙNG TỪ QĐ7 2026-11-19] nguồn rời rạc (hai bánh) — nguồn SSPP, R2
    # audit đánh PHẢI BỎ. Giữ field để không phá chữ ký `PlumeStateConfig`.
    source_lateral_m: tuple[float, ...] = (-0.85, 0.85)
    source_sigma_m: float = 0.18
    # [BỎ THEO AUDIT R2 2026-11-19] `streak` KHÔNG có trong paper Linnhoff 2022
    # (R2 audit 49 tham số: 9 tham số phải bỏ, trong đó có `streak_scale`).
    # Cơ chế kéo dài cụm theo phương trôi để nối các đám thành băng; ở 130 km/h
    # nó từng làm `max` điểm/cụm ~3.500 trong khi static chỉ có p95 36–181.
    # Đặt 0.0 = tắt; chỉ bật lại nếu có bằng chứng static chứng minh cần.
    streak_scale: float = 0.0
    # [CHỌN] Độ cao nguồn tính từ **mặt đường** (m), không phải theo chiều cao
    # hộp: lớp nước bắn lên có cùng độ dày bất kể xe cao hay thấp. Dùng chiều
    # cao hộp làm mâu thuẫn giữa các cự ly (cùng một khối cho elevation khác
    # nhau ở 10 m và 17 m) — xem plan A3.
    # [KHÔNG DÙNG TỪ QĐ7 2026-11-19] (nguồn SSPP) — giữ field vì API.
    source_height_m: tuple[float, float] = (0.05, 0.90)


@dataclass
class SprayCluster:
    """One cluster with its own position, velocity and age.

    ``pos`` is in the ego (sensor) frame, the frame the LiDAR renders in.
    ``vel`` is in the **ground frame** (m/s): drag and wind live there, and
    the ego velocity is subtracted only when integrating ``pos``.
    """

    pos: np.ndarray
    vel: np.ndarray
    radius: float
    age: float
    ttl: float
    drag: float
    object_id: int
    cluster_id: int
    velocity_assumed: bool = False
    # ``y`` of the spray block centre in the ego frame; the lateral clamp in
    # :meth:`PlumeState.advance` keeps ``|pos[1] - lateral_center_y|`` inside
    # clamp ngang 2,43 m cũ). ``None`` = không clamp (hand-built clusters
    # in tests).
    lateral_center_y: float | None = None
    # ``[CHỌN]`` Độ dài vệt (m) dọc phương trôi: cụm được cảm biến nhìn như một
    # **vệt** quét qua trong một chu kỳ, không phải quả cầu đứng yên. Đây là bản
    # sửa cho lỗ hổng định lượng của A3: cầu cách nhau 2,2 m (trôi 22 m/s × 0,1 s)
    # mà bán kính chỉ 0,31 m nên không bao giờ chồng nhau ⇒ plume bị "chặt vụn".
    # Với vệt dài ≈ quãng trôi một chu kỳ, vệt của chu kỳ trước chạm chu kỳ sau
    # ⇒ tạo băng liên tục như dữ liệu thật.
    streak_m: float = 0.0

    def probability(self) -> float:
        """Displayed survival probability ``P_t = exp(-age/T)`` [PAPER] III-C.

        A newborn cluster has ``age = -dt``, so the raw value is slightly above
        one; the displayed probability is clamped to ``[0, 1]``.
        """
        if self.ttl <= 0.0:
            return 0.0
        return float(min(1.0, np.exp(-self.age / self.ttl)))


@dataclass
class PlumeCounters:
    """Counts for the cycle that just ran, for the 28b marker."""

    spawned: int = 0
    alive: int = 0
    expired: int = 0


def cluster_spawn_rate_for_speed_abs(
    v_abs_kmh: float, vehicle_class: str = "crafter"
) -> float:
    """Clusters **spawned per 0.1 s cycle**, from the ``cal`` table (29e).

    ``rate(v) = visible_ref(v) / K(T_ref(v))`` is independent of ``wfh``; the
    humidity only changes how long a cluster lives (through ``T``). Keeping the
    rate fractional matters at low speed: rounding 1.44 to 1 would undershoot
    Golf at 50 km/h by 30 %. :class:`PlumeState` accumulates the fraction over
    frames, so the long-run spawn rate stays exact while each frame still
    spawns an integer number of clusters.

    ``vehicle_class`` only selects the visible-cluster table; the cluster
    radius and ``P_det`` are the paper's lognormals for every class
    (ticket 29e-d-iii).
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH:
        return 0.0
    return cluster_rate_for_speed(v_abs_kmh, PlumeConfig(), vehicle_class)


def cluster_count_for_speed_abs(
    v_abs_kmh: float, wfh_mm: float, vehicle_class: str = "crafter"
) -> int:
    """Clusters **alive in one frame** at steady state.

    ``visible = round(rate * 4T/Δt)`` — the same table as
    :func:`spray.plume.visible_cluster_count_for_speed`, so the stateful path
    and the per-frame generator report the same number. The lifetime ``T`` is
    unchanged (``[CODE] dee.cpp:530``). ``wfh_mm`` is in millimetres.

    The multiplier is :func:`spray.plume.steady_state_alive_factor`, **not**
    ``K``: :meth:`PlumeState.prune` removes clusters hard at ``age > 4T`` (no
    probabilistic thinning), so a cluster lives ``4T/Δt`` frames. Using ``K``
    made the alive count ``max_age_factor`` = 4x the target (ticket 29f).
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH or wfh_mm <= 0.0:
        return 0
    rate = cluster_spawn_rate_for_speed_abs(v_abs_kmh, vehicle_class)
    if rate <= 0.0:
        return 0
    config = PlumeConfig(water_film_height_m=wfh_mm / 1000.0)
    visible = rate * steady_state_alive_factor(v_abs_kmh, config)
    return int(np.floor(visible + 0.5))


def lifetime_mean_s(v_abs_kmh: float, wfh_mm: float) -> float:
    """Mean lifetime ``T = 0.02*wfh_mm*(v_abs_kmh - 50) + 0.2`` seconds."""
    return (
        LIFETIME_WFH_COEFF * wfh_mm * (v_abs_kmh - VELOCITY_OFFSET_KMH)
        + LIFETIME_BASE_S
    )


def wind_vector(config: PlumeStateConfig | None = None) -> np.ndarray:
    """Wind velocity in the ego frame, forward horizontal plane only.

    Meteorological direction 208 deg is where the wind blows *from*, so the
    velocity points toward 28 deg. Assuming ``+x`` east and ``+y`` north.
    """
    cfg = config or PlumeStateConfig()
    heading_from = np.deg2rad(cfg.wind_from_deg)
    east = -cfg.wind_speed_mps * np.sin(heading_from)
    north = -cfg.wind_speed_mps * np.cos(heading_from)
    return np.array([east, north, 0.0], dtype=np.float64)


class PlumeState:
    """Clusters keyed by ``(scene_token, object_id)``, reset per scene."""

    def __init__(self, config: PlumeStateConfig | None = None) -> None:
        self._config = config or PlumeStateConfig()
        self._clusters: dict[tuple[str, int], list[SprayCluster]] = {}
        self._spawn_credit: dict[tuple[str, int], float] = {}
        self._scene_token: str | None = None
        self._next_cluster_id = 0
        self._counters = PlumeCounters()

    @property
    def counters(self) -> PlumeCounters:
        return self._counters

    @property
    def wind(self) -> np.ndarray:
        return wind_vector(self._config)

    def needs_warm_start(self, scene_token: str) -> bool:
        """True khi state chưa từng chạy cho scene này (sẽ reset khi spawn)."""
        return scene_token != self._scene_token

    def warm_start(
        self,
        context,
        *,
        object_id: int,
        rng: np.random.Generator,
        dt: float,
        center: np.ndarray,
        extents: np.ndarray,
        vehicle_class: str = "crafter",
        direction: np.ndarray | None = None,
        cycles: int | None = None,
    ) -> None:
        """Chạy ``cycles`` chu kỳ GIẢ để scene bắt đầu ở trạng thái dừng.

        ``[ĐO] 2026-11-19``: scene SSPP chỉ 40–67 frame, trong khi plume cần
        ``max_age_factor*T/dt`` (48 frame @100 km/h, 73 @130) mới bão hoà. Khởi
        động từ state RỖNG làm nửa đầu mỗi scene thiếu spray và cuối scene lại
        dư — phân tích pixel trên clip cho thấy generator dày 0 lần ở frame đầu
        và 1,9× ở frame giữa. Dữ liệu thật thì frame 0 đã có plume vì xe đã chạy
        từ trước scene. Warm start tái tạo đúng điều kiện đó.
        """
        if cycles is None:
            v_abs_kmh = context.object_speed_mps * 3.6
            ttl = lifetime_mean_s(v_abs_kmh, context.wfh_mm)
            cycles = int(np.ceil(self._config.max_age_factor * ttl / dt)) + 1
        ego_velocity = np.array([context.ego_speed_mps, 0.0, 0.0],
                                dtype=np.float64)
        for _ in range(max(0, cycles)):
            self.advance(dt, ego_velocity=ego_velocity)
            self.prune()
            self.spawn(
                context,
                object_id=object_id,
                rng=rng,
                dt=dt,
                center=center,
                extents=extents,
                vehicle_class=vehicle_class,
                direction=direction,
            )

    def spawn(
        self,
        context,
        *,
        object_id: int,
        rng: np.random.Generator,
        dt: float = DEFAULT_DT_S,
        center: np.ndarray | None = None,
        extents: np.ndarray | None = None,
        config: PlumeStateConfig | None = None,
        vehicle_class: str = "crafter",
        direction: np.ndarray | None = None,
    ) -> list[SprayCluster]:
        """Spawn this cycle's clusters for one object.

        ``n`` follows the measured ``cal`` table (ticket 29e): the per-cycle
        rate is fractional and carried over through ``_spawn_credit`` so the
        long-run number of live clusters matches the table. ``T`` still uses
        ``v_abs`` (``object_speed_mps``). The initial velocity is the
        **ground** velocity: ``object_velocity_ego_mps`` plus the ego velocity
        ``[ego_speed_mps, 0, 0]``. When the caller did not supply the object
        velocity, it falls back to the object moving along ``+x`` in the ego
        frame at spawn time, so ``v_ground = [object_speed_mps, 0, 0]``, and
        the cluster is flagged ``velocity_assumed``. ``age`` starts one cycle
        behind so the cluster is inactive on its birth frame.

        ``center`` and ``extents`` describe the spray block (centre and half
        sizes in metres); positions are uniform inside it. Passing ``None``
        keeps the 28a placeholder jitter around the sensor origin.
        """
        cfg = config or self._config
        if config is not None:
            self._config = config

        if context.scene_token != self._scene_token:
            self._clusters.clear()
            self._spawn_credit.clear()
            self._scene_token = context.scene_token
            self._next_cluster_id = 0
            self._counters = PlumeCounters()

        v_abs_kmh = context.object_speed_mps * 3.6
        rate = cluster_spawn_rate_for_speed_abs(v_abs_kmh, vehicle_class)
        rate *= float(cfg.spawn_scale)
        credit_key = (context.scene_token, object_id)
        credit = self._spawn_credit.get(credit_key, 0.0) + rate
        count = int(np.floor(credit + 1e-9))
        self._spawn_credit[credit_key] = credit - count
        mean_ttl = lifetime_mean_s(v_abs_kmh, context.wfh_mm)
        origin = np.asarray(context.sensor_origin, dtype=np.float64)

        ego_velocity = np.array(
            [context.ego_speed_mps, 0.0, 0.0], dtype=np.float64
        )
        velocity = context.object_velocity_ego_mps
        if velocity is None:
            base_vel = np.array(
                [context.object_speed_mps, 0.0, 0.0], dtype=np.float64
            )
            velocity_assumed = True
        else:
            base_vel = np.asarray(velocity, dtype=np.float64) + ego_velocity
            velocity_assumed = False

        if (center is None) != (extents is None):
            raise ValueError("center and extents must be provided together")
        if center is not None:
            block_center = _vec3("center", center)
            block_extents = _vec3("extents", extents)

        bucket = self._clusters.setdefault(
            (context.scene_token, object_id), []
        )
        lateral_center = (
            float(block_center[1]) if center is not None else float(origin[1])
        )
        # QĐ7: trục dọc của khối (để rải cụm đều trong hộp calibration static).
        forward = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        if center is not None and direction is not None:
            candidate = np.asarray(direction, dtype=np.float64).ravel()
            norm = float(np.linalg.norm(candidate[:2]))
            if norm > 1e-9:
                forward = np.array(
                    [candidate[0] / norm, candidate[1] / norm, 0.0]
                )
        lateral_axis = np.array([-forward[1], forward[0], 0.0])
        created: list[SprayCluster] = []
        for _ in range(count):
            radius_median = cluster_radius_median_for_speed(v_abs_kmh)
            radius = min(
                cfg.radius_max_m,
                float(np.exp(rng.normal(float(np.log(radius_median)),
                                        cfg.radius_sigma))),
            )
            ttl = max(
                0.0, float(rng.normal(mean_ttl, cfg.lifetime_sigma_s))
            )
            drag = float(rng.normal(cfg.drag_mean, cfg.drag_std))
            vz = float(rng.uniform(0.0, cfg.initial_vz_max_mps))
            if center is None:
                pos = origin + rng.uniform(
                    -_SPAWN_JITTER_HALF_M, _SPAWN_JITTER_HALF_M, size=3
                )
            else:
                # QĐ7 2026-11-19: vùng sinh = ĐÚNG hộp đo calibration static D2
                # (W=3,4 m · H=1,5 m từ mặt đường · sâu 20 m sau đuôi xe), phân
                # bố ĐỀU. Bỏ nguồn rời rạc (`source_lateral_m`), knots và clamp
                # ngang 2,43 m (nguồn SSPP) — R2 audit đánh PHẢI BỎ. Paper chỉ
                # nói "uniform distribution in the region behind every moving
                # object", không cho kích thước ⇒ dùng vùng do phép đo
                # calibration định nghĩa là lựa chọn D2-hợp lệ.
                offset = rng.uniform(-1.0, 1.0, size=3) * block_extents
                pos = (
                    block_center
                    + forward * float(offset[0])
                    + lateral_axis * float(offset[1])
                    + np.array([0.0, 0.0, float(offset[2])])
                )
            vel = base_vel.copy()
            vel[2] += vz
            cluster = SprayCluster(
                pos=pos,
                vel=vel,
                radius=radius,
                age=-dt,
                ttl=ttl,
                drag=drag,
                object_id=object_id,
                cluster_id=self._next_cluster_id,
                velocity_assumed=velocity_assumed,
                lateral_center_y=lateral_center,
                # Quãng ego đi trong một chu kỳ = khoảng cách giữa hai lớp cụm,
                # cũng là độ dài vệt cần biểu diễn để hai lớp chạm nhau.
                streak_m=float(np.linalg.norm(ego_velocity)) * dt
                * float(cfg.streak_scale),
            )
            self._next_cluster_id += 1
            bucket.append(cluster)
            created.append(cluster)

        self._counters.spawned = len(created)
        self._counters.expired = 0
        self._counters.alive = self._total_alive()
        return created

    def advance(
        self, dt: float, ego_velocity: np.ndarray | None = None
    ) -> None:
        """Advect every cluster with drag and wind, then age it by ``dt``.

        Drag is applied in the ground frame (``vel`` is a ground velocity).
        Positions are integrated in the ego frame, so the ego velocity is
        subtracted there: a cluster keeping its ground speed falls behind at
        ``|vel - ego_velocity|``. ``ego_velocity`` defaults to zero so callers
        that do not model ego motion get the 28a behaviour.

        Drag may only dissipate air speed. At road speed ``|v_air|^2`` is of
        order 1000 m^2/s^2, so a positive ``drag`` (the default is the paper's
        constant ``-0.15``, but the config can pin any value) would otherwise
        grow as ``v' = +c*v^2`` and reach inf inside one cluster lifetime. The
        guard skips the update in that case; for every dissipative value the
        formula is unchanged.
        """
        wind = self.wind
        if ego_velocity is None:
            ego_velocity = np.zeros(3, dtype=np.float64)
        else:
            ego_velocity = np.asarray(ego_velocity, dtype=np.float64)
        for clusters in self._clusters.values():
            for cluster in clusters:
                air = cluster.vel - wind
                air_speed = float(np.linalg.norm(air))
                if air_speed > 0.0:
                    speed_after = air_speed + cluster.drag * air_speed**2 * dt
                    if speed_after < air_speed:
                        cluster.vel = cluster.vel + (
                            cluster.drag
                            * (air / air_speed)
                            * (air_speed**2)
                            * dt
                        )
                cluster.pos = cluster.pos + (cluster.vel - ego_velocity) * dt
                # QĐ7 2026-11-19: BỎ clamp ngang 2,43 m (nguồn SSPP `cal`
                # labels, R2 audit đánh PHẢI BỎ). Vùng sinh giờ đã bị giới hạn
                # bởi hộp calibration static nên không cần clamp riêng.
                cluster.age += dt
        self._counters.alive = self._total_alive()

    def prune(
        self, ceilings: dict[int, float] | None = None
    ) -> int:
        """Remove expired clusters.

        The only rule is ``age > max_age_factor * T`` (``[CODE]
        dee.cpp:445-450``), which the paper also describes. ``ceilings`` is
        accepted for backwards compatibility and ignored: the box-top ceiling
        was a ``[CHỌN]`` of ours with no paper source, added only to cancel the
        unsourced ``initial_vz``; both are gone in ticket 29h, so a cluster is
        never removed for its height.
        """
        removed = 0
        for key, clusters in list(self._clusters.items()):
            kept = []
            for cluster in clusters:
                if cluster.age > self._config.max_age_factor * cluster.ttl:
                    removed += 1
                else:
                    kept.append(cluster)
            self._clusters[key] = kept
        self._counters.expired = removed
        self._counters.alive = self._total_alive()
        return removed

    def alive(self, object_id: int) -> list[SprayCluster]:
        """Clusters currently alive for one object in the active scene."""
        key = (self._scene_token, object_id)
        return list(self._clusters.get(key, []))

    def all_alive(self) -> list[SprayCluster]:
        """Every live cluster in the active scene, across all objects."""
        return [
            cluster
            for clusters in self._clusters.values()
            for cluster in clusters
        ]

    def _total_alive(self) -> int:
        return sum(len(clusters) for clusters in self._clusters.values())


def _vec3(field: str, value) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,):
        raise ValueError(f"{field} must have shape (3,), got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{field} must be finite")
    return array
