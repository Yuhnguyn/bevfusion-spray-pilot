import numpy as np
import pytest

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
    assert cluster_count_for_speed_abs(130.0, 1.0) == 18
    assert cluster_count_for_speed_abs(100.0, 1.0) == 29
    assert cluster_count_for_speed_abs(50.0, 1.0) == 4
    assert cluster_count_for_speed_abs(40.0, 1.0) == 0
    # Passing metres by mistake gives a different count, so the unit is pinned.
    assert cluster_count_for_speed_abs(130.0, 0.001) == 2


def test_spawn_rate_is_fractional_and_uses_the_cal_table():
    # Golf at 50 km/h needs 3.62 visible clusters; a rounded rate of 1 would
    # undershoot by 30 %, so the rate stays fractional and is accumulated.
    rate = cluster_spawn_rate_for_speed_abs(50.0, "golf")
    assert rate == pytest.approx(3.62 / 2.51, rel=0.02)
    assert cluster_count_for_speed_abs(50.0, 1.0, "golf") == 4


def test_lifetime_mean_matches_reference_formula():
    assert lifetime_mean_s(130.0, 1.0) == pytest.approx(1.80, abs=1e-9)
    assert lifetime_mean_s(50.0, 1.0) == pytest.approx(0.20, abs=1e-9)


def test_clusters_from_frame_k_survive_later_frames():
    state = PlumeState()
    config = PlumeStateConfig(lifetime_sigma_s=0.0)
    rng = np.random.default_rng(3)

    # Ticket 29e: the per-cycle rate at 130 km/h is 0.97, so one call does not
    # spawn 24 clusters any more. Accumulate a cohort over several cycles.
    created = []
    for frame in range(4):
        created.extend(
            state.spawn(
                _context(frame_index=frame),
                object_id=7,
                rng=rng,
                config=config,
            )
        )
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
    for frame in range(20):
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
