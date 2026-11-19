import inspect

import numpy as np
import pytest

from spray import plume_state
from spray.plume_context import PlumeContext
from spray.plume_state import (
    PlumeState,
    PlumeStateConfig,
    SprayCluster,
    cluster_count_for_speed_abs,
    cluster_spawn_rate_for_speed_abs,
    lifetime_mean_s,
)


def _context(**overrides):
    fields = {
        "scene_token": "scene-0001",
        "frame_index": 0,
        "epoch": 0,
        "sensor_origin": np.array([0.0, 0.0, 1.8], dtype=np.float64),
        "ego_speed_mps": 130.0 / 3.6,
        "object_speed_mps": 130.0 / 3.6,
        "wfh_mm": 1.0,
        "road_z_m": -0.411,
    }
    fields.update(overrides)
    return PlumeContext(**fields)


def _cluster(age, ttl):
    return SprayCluster(
        pos=np.zeros(3, dtype=np.float64),
        vel=np.zeros(3, dtype=np.float64),
        radius=0.30,
        age=age,
        ttl=ttl,
        drag=0.0,
        object_id=0,
        cluster_id=0,
    )


def _spawn_nonempty(state, object_id, rng, context=None, **kwargs):
    """Spawn until at least one cluster exists (rate is fractional in 29e)."""
    context = context or _context()
    clusters = []
    while not clusters:
        clusters = state.spawn(
            context, object_id=object_id, rng=rng, **kwargs
        )
    return clusters


def test_cluster_count_for_speed_abs_uses_the_cal_table_and_mm_water_film():
    # Ticket 29e: visible = round(rate * K(T(wfh))), same table as the
    # per-frame generator.
    # [ĐO] Δ=1,0 (a3_targets_static.json) — bảng cũ Δ=2,5 đã bị bỏ.
    assert cluster_count_for_speed_abs(130.0, 1.0) == 33
    assert cluster_count_for_speed_abs(100.0, 1.0) == 36
    assert cluster_count_for_speed_abs(50.0, 1.0) == 9
    assert cluster_count_for_speed_abs(40.0, 1.0) == 0
    # Passing metres by mistake gives a different count, so the unit is pinned.
    assert cluster_count_for_speed_abs(130.0, 0.001) == 4


def test_spawn_rate_is_fractional_and_uses_the_cal_table():
    # Golf at 50 km/h needs 4.73 visible clusters (RoadSpray static, D2); a
    # rounded rate of 1 would
    # undershoot by 30 %, so the rate stays fractional and is accumulated.
    # Ticket 29f: T = 0.2 s at 50 km/h, hard prune at 4T with age starting at
    # -dt, so a cluster lives 4*0.2/0.1 + 1 = 9 cycles — that is the divisor,
    # not K = 2.51.
    rate = cluster_spawn_rate_for_speed_abs(50.0, "golf")
    assert rate == pytest.approx(4.73 / 9.0, rel=0.02)
    assert cluster_count_for_speed_abs(50.0, 1.0, "golf") == 5


def test_lifetime_mean_matches_reference_formula():
    assert lifetime_mean_s(130.0, 1.0) == pytest.approx(1.80, abs=1e-9)
    assert lifetime_mean_s(50.0, 1.0) == pytest.approx(0.20, abs=1e-9)


def test_clusters_from_frame_k_survive_later_frames():
    state = PlumeState()
    config = PlumeStateConfig(lifetime_sigma_s=0.0)
    rng = np.random.default_rng(3)

    # Ticket 29f: the per-cycle rate at 130 km/h is 0.25, so one call usually
    # spawns nothing. `_spawn_nonempty` accumulates cycles until a cohort
    # exists; this test is about survival, not about the spawn count.
    created = _spawn_nonempty(state, 7, rng, config=config)
    assert created
    for cluster in created:
        assert cluster.ttl == pytest.approx(1.8)

    alive_before = len(state.alive(7))
    for _ in range(2):
        state.advance(0.1)
        assert len(state.alive(7)) == alive_before

    # 68 more steps leave the oldest cohort at age ~6.9 s, still below
    # 4*T = 7.2 s.
    for _ in range(68):
        state.advance(0.1)

    assert all(cluster.age < 4.0 * cluster.ttl for cluster in state.alive(7))
    assert state.prune() == 0
    assert len(state.alive(7)) == alive_before


def test_display_probability_decays_monotonically():
    ttl = 1.0
    early = _cluster(0.2 * ttl, ttl).probability()
    middle = _cluster(0.5 * ttl, ttl).probability()
    late = _cluster(2.0 * ttl, ttl).probability()

    assert early == pytest.approx(np.exp(-0.2))
    assert middle == pytest.approx(np.exp(-0.5))
    assert late == pytest.approx(np.exp(-2.0))
    assert early > middle > late


def test_prune_removes_clusters_past_four_lifetimes():
    state = PlumeState()
    config = PlumeStateConfig(lifetime_sigma_s=0.0)
    rng = np.random.default_rng(11)

    while not state.alive(2):
        state.spawn(
            _context(), object_id=2, rng=rng, config=config
        )
    alive_before = len(state.alive(2))
    assert alive_before > 0

    # 80 steps leave age at 7.9 s, past 4*T = 7.2 s.
    for _ in range(80):
        state.advance(0.1)

    expired = state.prune()

    assert expired == alive_before
    assert state.counters.expired == expired
    assert len(state.alive(2)) == 0
    assert state.counters.alive == 0


def test_default_drag_is_the_paper_constant():
    state = PlumeState()
    rng = np.random.default_rng(7)
    clusters = []
    # Ticket 29f: rate at 130 km/h is 0.25/cycle, so 120 cycles ≈ 30 clusters.
    for frame in range(120):
        clusters.extend(
            state.spawn(
                _context(frame_index=frame), object_id=8, rng=rng
            )
        )

    assert len(clusters) >= 15
    for cluster in clusters:
        assert cluster.drag == pytest.approx(-0.15)


def test_drag_reduces_air_velocity_and_zero_drag_keeps_it():
    state = PlumeState()
    config = PlumeStateConfig(
        lifetime_sigma_s=0.0, drag_mean=-0.15, drag_std=0.0
    )
    clusters = _spawn_nonempty(
        state, 3, np.random.default_rng(5), config=config
    )
    wind = state.wind
    before = np.array([np.linalg.norm(cluster.vel - wind) for cluster in clusters])

    state.advance(0.1)

    after = np.array([np.linalg.norm(cluster.vel - wind) for cluster in clusters])
    assert np.all(after < before)

    steady = PlumeState()
    steady_config = PlumeStateConfig(
        lifetime_sigma_s=0.0, drag_mean=0.0, drag_std=0.0
    )
    steady_clusters = _spawn_nonempty(
        steady, 3, np.random.default_rng(5), config=steady_config
    )
    steady_wind = steady.wind
    before_steady = np.array(
        [cluster.vel - steady_wind for cluster in steady_clusters]
    )

    steady.advance(0.1)

    after_steady = np.array(
        [cluster.vel - steady_wind for cluster in steady_clusters]
    )
    assert np.allclose(after_steady, before_steady)


def test_spawn_is_deterministic_by_rng_seed():
    def positions(seed):
        state = PlumeState()
        clusters = _spawn_nonempty(
            state, 4, np.random.default_rng(seed)
        )
        return np.array([cluster.pos for cluster in clusters])

    first = positions(9)
    second = positions(9)
    other = positions(10)

    assert first.shape == second.shape == other.shape
    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)


def test_spawn_velocity_is_ground_velocity():
    state = PlumeState()
    ego_speed = 130.0 / 3.6

    clusters = _spawn_nonempty(
        state, 5, np.random.default_rng(0)
    )
    for cluster in clusters:
        # No object velocity supplied: the object runs along +x in the ego
        # frame at spawn, so the ground velocity is the road speed.
        assert cluster.vel[0] == pytest.approx(ego_speed, abs=1e-9)
        assert cluster.velocity_assumed is True

    explicit = PlumeState()
    clusters = _spawn_nonempty(
        explicit,
        5,
        np.random.default_rng(0),
        context=_context(object_velocity_ego_mps=np.array([0.0, 0.0, 0.0])),
    )
    for cluster in clusters:
        # Same speed as the ego -> ground velocity is the ego velocity.
        assert cluster.vel[0] == pytest.approx(ego_speed, abs=1e-9)
        assert cluster.velocity_assumed is False


def test_cluster_drifts_backwards_in_the_ego_frame():
    state = PlumeState()
    config = PlumeStateConfig(
        lifetime_sigma_s=0.0, drag_mean=-0.15, drag_std=0.0
    )
    clusters = _spawn_nonempty(
        state,
        5,
        np.random.default_rng(0),
        dt=0.1,
        center=np.array([16.0, 0.0, 0.34]),
        extents=np.array([1.8, 1.7, 0.75]),
        config=config,
    )
    assert clusters

    ego_velocity = np.array([130.0 / 3.6, 0.0, 0.0])
    x = np.array([cluster.pos[0] for cluster in clusters])
    for _ in range(4):
        state.advance(0.1, ego_velocity=ego_velocity)
        following = np.array([cluster.pos[0] for cluster in clusters])
        assert np.all(np.abs(following) < np.abs(x) - 0.5)
        x = following


def test_drag_uses_ground_velocity_when_ego_and_object_match_speed():
    state = PlumeState()
    config = PlumeStateConfig(
        lifetime_sigma_s=0.0,
        drag_mean=-0.15,
        drag_std=0.0,
        wind_speed_mps=0.0,
    )
    clusters = _spawn_nonempty(
        state, 6, np.random.default_rng(1), config=config
    )
    road_speed = 130.0 / 3.6
    assert all(
        cluster.vel[0] == pytest.approx(road_speed) for cluster in clusters
    )

    state.advance(0.1, ego_velocity=np.array([road_speed, 0.0, 0.0]))

    # Relative speed is zero at birth, yet the ground velocity must decay.
    for cluster in clusters:
        assert cluster.vel[0] < road_speed - 1.0
        assert cluster.pos[0] < -1.0


def test_lateral_clamp_is_removed():
    """QĐ7 2026-11-19: bỏ clamp ngang 2,43 m (nguồn SSPP `cal`, R2 audit PHẢI BỎ).

    Không chỉ xoá test cũ: khẳng định hằng số đã biến mất khỏi module để không
    ai vô tình đưa cơ chế SSPP trở lại.
    """
    assert not hasattr(plume_state, "LATERAL_CLAMP_M")
    assert "LATERAL_CLAMP_M" not in inspect.getsource(plume_state)


def test_spawn_region_is_the_static_calibration_box():
    """QĐ7: mọi cụm sinh ra nằm trong hộp calibration static.

    Hộp = W 3,4 m (|y| ≤ 1,7) × H 1,5 m **tính từ mặt đường** × sâu 20 m sau
    đuôi xe — đúng vùng `roadspray_static_plume_box.py` dùng để đo D2. Đây là
    bất biến thay cho clamp ngang đã bị bỏ.
    """
    state = PlumeState()
    config = PlumeStateConfig(
        lifetime_sigma_s=0.0, drag_mean=0.0, drag_std=0.0, wind_speed_mps=0.0
    )
    road_z = -0.411
    rear_x = 16.6
    center = np.array(
        [rear_x - 10.0, 0.0, road_z + 0.75], dtype=np.float64
    )
    extents = np.array([10.0, 1.7, 0.75], dtype=np.float64)
    rng = np.random.default_rng(7)
    context = _context(road_z_m=road_z)
    positions = []
    for _ in range(2400):
        positions.extend(
            cluster.pos
            for cluster in state.spawn(
                context,
                object_id=0,
                rng=rng,
                dt=0.1,
                center=center,
                extents=extents,
                direction=np.array([1.0, 0.0, 0.0]),
                config=config,
            )
        )
    points = np.asarray(positions)
    assert points.shape[0] > 50, points.shape[0]
    assert np.abs(points[:, 1]).max() <= 1.7 + 1e-9
    assert points[:, 2].min() >= road_z - 1e-9
    assert points[:, 2].max() <= road_z + 1.5 + 1e-9


def test_radius_slope_constant_is_removed():
    # Ticket 29e-c: the per-km/h median radius was the wrong direction; `r_cl`
    # must be the paper's fixed lognormal (median 0.30 m) at every speed.
    assert not hasattr(plume_state, "RADIUS_MEDIAN_PER_KMH")
    assert "radius_median_per_kmh" not in PlumeStateConfig.__dataclass_fields__
    assert "RADIUS_MEDIAN_PER_KMH" not in inspect.getsource(plume_state)


def test_radius_median_does_not_grow_with_speed():
    def radii(speed_kmh, seed=0):
        state = PlumeState()
        rng = np.random.default_rng(seed)
        context = _context(
            ego_speed_mps=speed_kmh / 3.6,
            object_speed_mps=speed_kmh / 3.6,
        )
        values = []
        # Ticket 29f: rate is 0.61/cycle at 100 km/h and 0.25 at 130 km/h, so
        # the walk needs more cycles to collect a few hundred radii.
        for frame in range(2400):
            values.extend(
                cluster.radius
                for cluster in state.spawn(
                    context, object_id=0, rng=rng, dt=0.1
                )
            )
        return np.asarray(values)

    slow = radii(100.0)
    fast = radii(130.0)
    assert slow.size > 300 and fast.size > 300
    # `[ĐO] 2026-11-19` — bán kính lấy từ **RoadSpray `*_static`, cột Δ=1,0 m**
    # (ADR-0006 D2): 0,349 / 0,292 / 0,311 m tại 50 / 100 / 130 km/h ⇒ gần như
    # KHÔNG phụ thuộc tốc độ, và trùng paper (0,30 m). Vì vậy code dùng một hằng số
    # 0,31 m cho mọi tốc độ. (Con số 0,48 / 0,66 trước đây lấy từ cột Δ=2,5 m — cột
    # bị chain-merging dọc tia làm phình 1,6–2,1×, đã bị loại bỏ.)
    assert np.median(slow) == pytest.approx(0.31, rel=0.20)
    assert np.median(fast) == pytest.approx(0.31, rel=0.20)


def test_spawn_has_no_vertical_velocity():
    # [PAPER] arXiv 2212.08558 Sec. III-C: "the velocity of the moving object is
    # set as an initial cluster velocity" -- purely horizontal. The paper has no
    # gravity and no vertical term, so v0_z is zero (ticket 29h).
    state = PlumeState()
    clusters = []
    for frame in range(40):
        clusters.extend(
            state.spawn(
                _context(frame_index=frame), object_id=0, rng=np.random.default_rng(frame)
            )
        )
    assert clusters
    for cluster in clusters:
        assert cluster.vel[2] == 0.0


def test_clusters_are_not_pruned_for_rising_above_the_box():
    # Ticket 29h: the ceiling prune had no paper source; it only cancelled the
    # (also unsourced) initial vz. A cluster above the box top must stay alive
    # as long as ``age <= 4*T``.
    state = PlumeState()
    config = PlumeStateConfig(lifetime_sigma_s=0.0)
    clusters = _spawn_nonempty(
        state, 0, np.random.default_rng(0), config=config
    )
    for cluster in clusters:
        cluster.pos[2] = 50.0

    assert state.prune() == 0
    assert len(state.alive(0)) == len(clusters)


def test_positive_drag_sample_never_accelerates_a_cluster():
    state = PlumeState()
    config = PlumeStateConfig(
        lifetime_sigma_s=0.0, drag_mean=0.12, drag_std=0.0
    )
    clusters = _spawn_nonempty(
        state, 7, np.random.default_rng(2), config=config
    )
    before = [cluster.vel.copy() for cluster in clusters]

    for _ in range(5):
        state.advance(0.1)

    for initial, cluster in zip(before, clusters):
        assert np.isfinite(cluster.vel).all()
        assert np.isfinite(cluster.pos).all()
        assert cluster.vel[0] == pytest.approx(initial[0])
