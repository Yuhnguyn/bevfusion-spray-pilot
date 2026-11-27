"""Time-varying state of spray clusters: spawn, advect and expire.

Đây là module giữ cụm sống qua nhiều frame. Không có nó thì mỗi frame phải dựng lại plume
từ đầu: cụm không có tuổi, không có vệt sau xe dẫn.

Ba hệ quy chiếu, đừng lẫn:

- **vận tốc** của cụm ở hệ **mặt đất** (``vel``) — drag và gió là hiện tượng vật lý so với
  không khí, không so với cảm biến.
- **vị trí** ở hệ **ego** (``pos``) — đây là hệ mà LiDAR nhìn.
- mỗi bước cập nhật vị trí phải trừ ``ego_velocity`` đúng **một lần**:
  ``pos += (vel - ego_velocity) * dt``.

Hai tốc độ, hai vai trò:

- ``v_abs`` = ``context.object_speed_mps``, tốc độ xe dẫn so với mặt đường. Nó quyết định
  **số cụm sinh mỗi chu kỳ** và **lifetime** ``T``: lượng nước bắn lên tỉ lệ với mặt đường ướt
  mà lốp đi qua mỗi giây.
- **vận tốc mặt đất** = ``object_velocity_ego_mps + [ego_speed, 0, 0]`` — vận tốc riêng của xe
  dẫn, cộng vận tốc ego để đưa về hệ mặt đất.

Hệ quả của drag (đây là điều làm vệt dài): ``|v_air|^2`` ở tốc độ đường là bậc 1300 m²/s², nên
``C·|air|^2`` với ``C = -0,15`` lấy đi hàng chục m/s trong vài chu kỳ đầu. Một cụm sinh ra khi
ego và xe dẫn **cùng tốc độ** có vận tốc tương đối lúc sinh ≈ 0, rồi tụt lại rất xa trong hệ ego.

Quy ước dấu theo reference implementation ``openMSL/sl-1-2`` (MPL-2.0):

- cụm sinh với ``age = -dt`` nên **không** hoạt động ngay frame đầu;
- ``T ~ N(0,02·wfh_mm·(v_abs_kmh − 50) + 0,2, 0,2)``, chặn dưới ở 0;
- drag dùng hằng số của paper ``C = -0,15 1/m`` [PAPER] arXiv 2212.08558, tác động
  ``v += C·v_air_hat·|v_air|²·dt`` với ``v_air = v_cluster − wind``. Reference code
  (``dee.cpp:542``) bốc ``N(−0,12; 0,04)`` cho từng cụm; module này **cố ý** theo paper và để
  các núm lấy mẫu ở hằng số;
- cụm tan theo **xác suất** ``P = exp(−Δt/T)`` mỗi chu kỳ [PAPER] Eq. 1, cộng trần số học
  ``12·T`` để chặn đuôi;
- xác suất sống hiển thị là ``P_t = exp(−age/T)``.

Lịch sử các lần đổi cơ chế (cắt cứng ``4T``, ``vz`` ban đầu, trần chiều cao, nguồn hai bánh):
``docs/adr/decision-log.md``.
"""


from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spray.plume import (
    PlumeConfig,
    cluster_rate_for_speed,
    steady_state_alive_factor,
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
# Paper Eq. 1 cho `T` là hàm TẤT ĐỊNH của tốc độ + màng nước, không có nhiễu
# Gaussian ⇒ sigma = 0. (Nhiễu `N(0; 0,2)` là `[CODE]` reference impl.)
LIFETIME_SIGMA_S = 0.0
# Trần **SỐ HỌC** 12·T, không phải mô hình. Cụm tan theo xác suất
# `P = exp(−Δt/T)` [PAPER] Eq. 1; `exp(−12) = 6e-6` nên trần này cắt < 1 cụm/10⁵.
MAX_AGE_FACTOR = 12.0
# [PAPER] Fig. 5: `r_cl` là **một** lognormal duy nhất. Paper KHÔNG cho bán kính
# phụ thuộc tốc độ ⇒ dùng hằng số, không dùng bảng theo tốc độ.
RADIUS_MU = -1.2
# [PAPER] Fig. 5 nguyên văn: "The parameters of the distribution are µ = −1.2 and
# σ = 0.8 as an example." ⇒ σ = 0,8. (Trước đây dùng 0,720 — đó là σ của phép đo
# RoadSpray `*_static`, KHÔNG phải σ của paper; xem
# docs/measurements/sspp-cluster-radius-by-speed.md §3 mục 2: σ đo bị phồng bởi
# các chuỗi đã gộp nên không so được với số paper.)
RADIUS_SIGMA = 0.8
# [PAPER] Paper §III-B KHÔNG đặt trần cho r_cl — nguyên văn "The parameters of the
# distribution are µ = −1.2 and σ = 0.8 as an example", không có clip. Trần 2,0 m
# trước đây là [CHỌN] của repo, biện minh bằng "cắt ~0,1 % đuôi" — sai số học
# (với σ=0,72 thì P(r>2,0) = 0,43 %; với σ=0,8 là 0,90 %). Giữ hằng số = inf để
# một chỗ duy nhất điều khiển được (test/probe vẫn truyền số hữu hạn khi cần).
RADIUS_MAX_M = float("inf")
# [PAPER] median = e^−1,2 = 0,3012 m (Fig. 5).
RADIUS_MEDIAN_M = 0.3012


def cluster_radius_median_for_speed(speed_kmh: float) -> float:
    """Trung vị bán kính cụm (m) — **hằng số**, không phụ thuộc tốc độ.

    Giữ hàm để call site không đổi. Tham số tốc độ được bỏ qua có chủ ý: cả paper
    (một lognormal) lẫn phép đo static Δ=1,0 đều cho bán kính không đổi theo tốc độ.
    """
    del speed_kmh
    return RADIUS_MEDIAN_M


# [PAPER] §III-C: không có vận tốc thẳng đứng ban đầu, `v0` = vận tốc vật thể,
# thuần nằm ngang. Paper không có gravity và không có phương trình `z`, nên cụm
# không tự bay lên; chiều cao plume đến từ vị trí khối sinh. Dòng
# `vz = rng.uniform(0, initial_vz_max_mps)` trong `spawn` vẫn còn — muốn bật lại
# thì chỉ đổi hằng số này.
INITIAL_VZ_MAX_MPS = 0.0
# [PAPER] §III-C: hệ số drag `C = −0,15 1/m`, hằng số. Reference code bốc
# `N(−0,12; 0,04)` cho từng cụm; module này theo paper nên `DRAG_STD = 0`.
DRAG_MEAN = -0.15
DRAG_STD = 0.0
# [CODE] dee.cpp wind: 2 m/s from 208 deg in meteorological convention.
WIND_SPEED_MPS = 2.0
WIND_FROM_DEG = 208.0
# [CODE] profile VLP-32 update_cycle_time.
DEFAULT_DT_S = 0.1

# Jitter quanh gốc cảm biến, chỉ dùng khi caller gọi `spawn` KHÔNG truyền
# `center` (test, probe). Đường production luôn truyền khối sau đuôi xe nên
# hằng số này không ảnh hưởng plume thật.
_SPAWN_JITTER_HALF_M = 0.5


@dataclass(frozen=True)
class PlumeStateConfig:
    """Stochastic knobs of the cluster state, with reference defaults.

    The model constants live in the module; this config only lets tests and
    the caller pin distributions or change the wind. Drag defaults to the
    paper's constant (``drag_std = 0``), but the knobs stay so a caller can
    still sample it.

    ``radius_mu`` / ``radius_sigma`` are the paper's lognormal for ``r_cl``.
    ``radius_max_m`` defaults to ``inf`` (the paper sets no cap on ``r_cl``);
    pass a finite number to clip.
    """

    lifetime_sigma_s: float = LIFETIME_SIGMA_S
    max_age_factor: float = MAX_AGE_FACTOR
    radius_mu: float = RADIUS_MU
    radius_sigma: float = RADIUS_SIGMA
    radius_max_m: float = RADIUS_MAX_M
    # [MIỀN — ADR-0006 §5.7] Giới hạn miền mô hình phát ngôn.
    #   min/max_range_m: paper §V-D đánh giá 0–50 m; §V cảnh báo biểu diễn cầu vỡ
    #     ở gần cảm biến. Dữ liệu thật: r p01 = 2,75 m, chỉ 0,02 % điểm có r > 50 m.
    min_range_m: float = 2.5
    max_range_m: float = 50.0
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
    # Nguồn phát rời rạc (hai bánh sau): KHÔNG có trong paper — paper nói rải đều
    # "in the region behind every moving object". Mặc định 0 = tắt (rải đều).
    source_count: int = 0
    # Field giữ cho API; không dùng khi `source_count = 0`.
    source_lateral_m: tuple[float, ...] = (-0.85, 0.85)
    source_sigma_m: float = 0.18
    # Độ dài vệt theo phương trôi. `streak` KHÔNG có trong paper ⇒ mặc định 0
    # (tắt); chỉ bật lại nếu có bằng chứng từ dữ liệu static.
    streak_scale: float = 0.0
    # Độ cao nguồn tính từ **mặt đường** (m), không theo chiều cao hộp: lớp nước
    # bắn lên có cùng độ dày bất kể xe cao hay thấp. Field giữ cho API.
    source_height_m: tuple[float, float] = (0.05, 0.90)
    # Hệ số nhân số cụm sinh. Bảng `visible` là số **detection-cluster** đo trên
    # dữ liệu thật, còn code dùng nó làm số **quả cầu sống**; nhiều cầu gộp thành
    # một detection-cluster nên đôi khi cần nhiều cầu hơn. Production giữ 1,0
    # (D2-v2 đã FAIL — xem ADR-0006).
    spawn_scale: float = 1.0


@dataclass
class SprayCluster:
    """Một cụm: vị trí, vận tốc, tuổi.

    ``pos`` ở hệ **ego** (hệ cảm biến, hệ LiDAR render).
    ``vel`` ở hệ **mặt đất** (m/s): drag và gió sống ở đó, và ``ego_velocity``
    chỉ bị trừ đúng một lần khi tích phân ``pos``.
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
    # ``y`` của tâm khối sinh trong hệ ego. Không còn clamp ngang; field giữ
    # lại để cụm dựng tay trong test vẫn khai được. ``None`` = không dùng.
    lateral_center_y: float | None = None
    # ``[CHỌN]`` Độ dài vệt (m) dọc phương trôi — biểu diễn cụm như một **vệt**
    # quét qua trong một chu kỳ thay vì quả cầu đứng yên. Mặc định 0 (tắt):
    # ``streak_scale = 0``; cơ chế này KHÔNG có trong paper.
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
    """Số cụm **sinh mỗi chu kỳ** 0,1 s, lấy từ bảng cụm/frame.

    ``rate(v) = visible_ref(v) / K(T_ref(v))`` — **không** phụ thuộc ``wfh``;
    độ ẩm chỉ đổi tuổi thọ cụm (qua ``T``). Vì sao phải neo tại ``T_ref``:
    `docs/adr/decision-log.md` (29e-c).

    Giữ ``rate`` ở dạng **phân số**: làm tròn sẽ lệch 30–44 % ở tốc độ thấp.
    :class:`PlumeState` cộng dồn phần lẻ qua ``_spawn_credit``, nên trung bình
    dài hạn đúng trong khi mỗi frame vẫn sinh số nguyên cụm.

    ``vehicle_class`` chỉ chọn BẢNG số cụm; bán kính cụm và ``P_det`` là
    lognormal của paper cho mọi lớp.
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH:
        return 0.0
    return cluster_rate_for_speed(v_abs_kmh, PlumeConfig(), vehicle_class)


def cluster_count_for_speed_abs(
    v_abs_kmh: float, wfh_mm: float, vehicle_class: str = "crafter"
) -> int:
    """Số cụm **còn sống trong một frame** ở trạng thái dừng.

    ``visible = round(rate × K)`` với ``K = 1/(1−exp(−Δt/T))`` [PAPER] Eq. 1 —
    cùng bảng với :func:`spray.plume.visible_cluster_count_for_speed`, nên
    đường stateful và generator theo frame báo cùng một số.
    ``T = 0,02·wfh_mm·(v−50) + 0,2`` `[CODE]`. ``wfh_mm`` tính bằng milimét.

    Hệ số nhân là :func:`spray.plume.steady_state_alive_factor` = ``K``:
    :meth:`PlumeState.prune` cho cụm tan với xác suất ``1 − exp(−Δt/T)`` mỗi
    bước.
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
        # RNG dự phòng cho `prune()` khi caller gọi trực tiếp không truyền rng
        # (paper Eq. 1 có thinning xác suất). Seed cố định ⇒ tái lập được.
        self._rng = np.random.default_rng(0)

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
            self.prune(dt=dt, rng=rng)
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
        """Sinh cụm của chu kỳ này cho một vật thể.

        ``count`` theo bảng cụm/frame đo được; phần lẻ cộng dồn qua
        ``_spawn_credit`` nên số cụm sống dài hạn khớp bảng. ``T`` dùng
        ``v_abs`` (``object_speed_mps``).

        Vận tốc ban đầu là vận tốc **mặt đất**: ``object_velocity_ego_mps``
        cộng vận tốc ego ``[ego_speed_mps, 0, 0]``. Nếu caller không truyền
        vận tốc vật thể, hàm rơi về giả định vật chạy theo ``+x`` trong hệ ego
        ⇒ ``v_ground = [object_speed_mps, 0, 0]``, và cụm bị đánh cờ
        ``velocity_assumed``.

        ``age`` bắt đầu ở ``−dt`` nên cụm **không** hoạt động ngay frame sinh.

        ``center`` / ``extents``: tâm và nửa kích thước khối sinh (mét); vị trí
        rải đều trong khối. Truyền ``None`` thì rơi về jitter quanh gốc cảm
        biến — chỉ dùng cho test/probe, không phải đường production.
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
        # Trục dọc của khối sinh (dọc theo yaw của box).
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
            radius_draw = float(
                np.exp(rng.normal(float(np.log(radius_median)),
                                  cfg.radius_sigma))
            )
            # radius_max_m = inf (paper không có trần) ⇒ min() là no-op; caller có thể truyền số hữu hạn.
            radius = min(cfg.radius_max_m, radius_draw)
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
                # Rải ĐỀU trong khối sinh [PAPER] §III-B "uniform distribution in
                # the region behind every moving object". Không có nguồn rời rạc,
                # không có knot, không clamp ngang.
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
                # `streak_scale` mặc định 0 ⇒ streak_m = 0. Cơ chế kéo dài cụm
                # thành vệt KHÔNG có trong paper; knob giữ lại cho thí nghiệm.
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
        """Trôi mọi cụm bằng drag + gió, rồi tăng tuổi thêm ``dt``.

        Drag áp trong hệ **mặt đất** (``vel`` là vận tốc mặt đất). Vị trí tích
        phân trong hệ **ego**, nên ``ego_velocity`` bị trừ ở đó: cụm giữ vận tốc
        mặt đất sẽ tụt lại phía sau với tốc độ ``|vel − ego_velocity|``.
        ``ego_velocity`` mặc định bằng 0 cho caller không mô hình hoá ego.

        Drag chỉ được làm **giảm** tốc độ không khí. Ở tốc độ đường,
        ``|v_air|²`` bậc 1000 m²/s², nên một ``drag`` dương (mặc định là hằng số
        của paper ``−0,15``, nhưng config cho phép giá trị bất kỳ) sẽ tăng theo
        ``v' = +c·v²`` và chạm `inf` trong một đời cụm. Guard bỏ qua cập nhật
        trong trường hợp đó; mọi giá trị tiêu tán thì công thức không đổi.
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
                # Vị trí ở hệ EGO, nên trừ ego_velocity đúng một lần ở đây.
                cluster.pos = cluster.pos + (cluster.vel - ego_velocity) * dt
                cluster.age += dt
        self._counters.alive = self._total_alive()

    def prune(
        self,
        ceilings: dict[int, float] | None = None,
        *,
        dt: float | None = None,
        rng: np.random.Generator | None = None,
    ) -> int:
        """Cho cụm tan theo **xác suất** [PAPER] Eq. 1 + trần số học ``12·T``.

        Xác suất sống mỗi bước là ``P = exp(−Δt/T)`` — nguyên văn paper:
        *"probability ... to still exist after time t is exp(−t/T)"*. Trần
        ``12·T`` chỉ là **trần số học** chặn đuôi (``exp(−12) = 6e−6``), không
        phải mô hình.

        ``dt`` mặc định ``DEFAULT_DT_S`` (0,1 s) khi caller gọi trực tiếp;
        ``rng`` mặc định dùng RNG nội bộ seed 0 để tái lập được. ``ceilings``
        nhận cho tương thích và **bị bỏ qua** — plume không có trần theo chiều
        cao (xem module docstring).
        """
        step = DEFAULT_DT_S if dt is None else float(dt)
        random = self._rng if rng is None else rng
        cap_factor = float(self._config.max_age_factor)
        removed = 0
        for key, clusters in list(self._clusters.items()):
            kept = []
            for cluster in clusters:
                if cluster.age > cap_factor * cluster.ttl:
                    removed += 1
                    continue
                survival = (
                    float(np.exp(-step / cluster.ttl))
                    if cluster.ttl > 0.0
                    else 0.0
                )
                if survival < 1.0 and random.random() >= survival:
                    removed += 1
                    continue
                kept.append(cluster)
            self._clusters[key] = kept
        self._counters.expired = removed
        self._counters.alive = self._total_alive()
        return removed

    def alive(self, object_id: int) -> list[SprayCluster]:
        """Cụm đang sống của một vật thể trong scene hiện hành."""
        key = (self._scene_token, object_id)
        return list(self._clusters.get(key, []))

    def all_alive(self) -> list[SprayCluster]:
        """Mọi cụm còn sống trong scene hiện hành, gộp mọi vật thể."""
        return [
            cluster
            for clusters in self._clusters.values()
            for cluster in clusters
        ]

    def select_alive(self) -> list[SprayCluster]:
        """Cụm còn sống VÀ nằm trong miền hợp lệ của mô hình (ADR-0006 §5.7).

        Mặc định (``min_range_m = 0``, ``max_range_m = inf``) trả về đúng
        ``all_alive()``.

        ``min_range_m`` so với **mặt cầu** (``‖pos‖ − radius``), không phải tâm:
        tâm cụm ở 3 m với bán kính 2 m thì mặt cầu đã ở 1 m. ``max_range_m`` so
        với **tâm** — đó là đại lượng paper đánh giá ở Fig. 11/12.

        Khoảng cách dùng ``‖pos‖`` 3D từ cảm biến. Vì ``‖pos‖ ≥ |x|``, biên này
        bao hàm luôn "không trôi quá xa về phía sau": cắt ``r ≤ 50`` đã cho
        ``x min = −49,4 m``, không cần biên sau riêng.
        """
        clusters = self.all_alive()
        cfg = self._config
        if cfg.min_range_m <= 0.0 and not np.isfinite(cfg.max_range_m):
            return clusters
        kept: list[SprayCluster] = []
        for cluster in clusters:
            distance = float(np.linalg.norm(cluster.pos))
            if distance - float(cluster.radius) < cfg.min_range_m:
                continue
            if distance > cfg.max_range_m:
                continue
            kept.append(cluster)
        return kept

    def _total_alive(self) -> int:
        return sum(len(clusters) for clusters in self._clusters.values())


def _vec3(field: str, value) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,):
        raise ValueError(f"{field} must have shape (3,), got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{field} must be finite")
    return array
