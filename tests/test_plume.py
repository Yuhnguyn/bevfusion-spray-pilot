import numpy as np
import pytest

from spray.plume import (
    PlumeConfig,
    _ball,
    _count_for_distance,
    _lognormal_clipped,
    _thin_radial,
    cluster_count_for_speed,
    inject_plume,
    steady_state_cluster_factor,
)


def _config(**overrides):
    values = dict(
        point_cloud_range=(-54.0, -54.0, -5.0, 54.0, 54.0, 3.0),
        distance_range_m=(3.0, 6.0),
        points_per_cluster_median=20.0,
        points_per_cluster_sigma=0.0,
        cluster_radius_sigma=0.0,
    )
    values.update(overrides)
    return PlumeConfig(**values)


def test_no_boxes_returns_clean_points_unchanged():
    points = np.array([[1.0, 2.0, 0.5, 0.0, 0.0]], dtype=np.float32)

    result = inject_plume(points, np.empty((0, 9), dtype=np.float32), seed=0)

    assert np.array_equal(result.points, points)
    assert np.array_equal(result.points_clean, points)
    assert result.injected.shape == (0, 5)
    assert result.stats.injected == 0


def test_injects_behind_lead_vehicle_within_range():
    points = np.array([[0.0, 0.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )

    for seed in range(50):
        result = inject_plume(points, boxes, seed=seed, config=_config())
        if result.stats.injected:
            break

    assert result.stats.eligible_boxes == 1
    assert result.stats.injected == len(result.injected) > 0
    assert (result.injected[:, 0] < -2.4).all()
    assert (result.injected[:, 0] > -6.4).all()
    x_min, y_min, z_min, x_max, y_max, z_max = _config().point_cloud_range
    assert (result.injected[:, 0] >= x_min).all()
    assert (result.injected[:, 0] <= x_max).all()
    assert (result.injected[:, 1] >= y_min).all()
    assert (result.injected[:, 1] <= y_max).all()
    assert (result.injected[:, 2] >= z_min).all()
    assert (result.injected[:, 2] <= z_max).all()
    assert np.array_equal(result.points_clean, points)
    assert result.points.shape == (len(points) + len(result.injected), 5)


def test_skips_low_speed_and_missing_velocity():
    points = np.zeros((1, 5), dtype=np.float32)
    config = _config()

    slow = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 1.0, 0.0]], dtype=np.float32
    )
    slow_result = inject_plume(points, slow, seed=2, config=config)
    assert slow_result.stats.injected == 0
    assert slow_result.stats.skipped_low_speed == 1

    no_velocity = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0]], dtype=np.float32
    )
    missing_result = inject_plume(points, no_velocity, seed=2, config=config)
    assert missing_result.stats.injected == 0
    assert missing_result.stats.skipped_no_velocity == 1


def test_caps_injected_points_and_keeps_them_outside_boxes():
    # Ticket 29c mục 2: ngân sách = max(500, 5 % số điểm thật). 1.000 điểm
    # thật ⇒ 500; cụm ở 3 m cho 30 điểm/cụm nên 4–29 cụm vượt ngân sách.
    points = np.zeros((1000, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )
    config = _config(distance_range_m=(3.0, 3.0))

    for seed in range(100):
        result = inject_plume(points, boxes, seed=seed, config=config)
        if result.stats.capped > 0:
            break

    assert result.stats.injected == 500
    assert result.stats.capped > 0
    inside = (
        (np.abs(result.injected[:, 0]) <= 2.45)
        & (np.abs(result.injected[:, 1]) <= 1.15)
        & (result.injected[:, 2] >= -0.95)
        & (result.injected[:, 2] <= 0.95)
    )
    assert not inside.any()


def test_same_seed_and_token_are_reproducible():
    points = np.zeros((1, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )
    config = _config()

    populated = [
        seed
        for seed in range(100)
        if inject_plume(points, boxes, seed=seed, config=config).stats.injected
    ]
    first_seed, other_seed = populated[:2]

    first = inject_plume(points, boxes, seed=first_seed, token="scene-1", config=config)
    second = inject_plume(points, boxes, seed=first_seed, token="scene-1", config=config)
    other = inject_plume(points, boxes, seed=other_seed, token="scene-1", config=config)

    assert np.array_equal(first.points, second.points)
    assert not np.array_equal(first.points, other.points)


def test_accepts_four_channel_points():
    points = np.zeros((2, 4), dtype=np.float32)

    result = inject_plume(
        points, np.empty((0, 9), dtype=np.float32), seed=0, config=_config()
    )

    assert result.points.shape == (2, 5)
    assert (result.points[:, 4] == 0).all()


def test_rejects_invalid_shapes():
    with pytest.raises(ValueError):
        inject_plume(np.zeros((2, 3)), np.empty((0, 9)), seed=0)
    with pytest.raises(ValueError):
        inject_plume(np.zeros((2, 5)), np.zeros((1, 6)), seed=0)


def test_activation_threshold_is_40_kmh():
    """Box 39 km/h bị bỏ; 40 km/h đã kích hoạt nhưng công thức cho 0 cụm."""
    points = np.zeros((1, 5), dtype=np.float32)

    def run(speed_kmh):
        boxes = np.array(
            [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, speed_kmh / 3.6, 0.0]],
            dtype=np.float32,
        )
        return inject_plume(points, boxes, seed=4, config=_config())

    below = run(39.0)
    assert below.stats.eligible_boxes == 0
    assert below.stats.skipped_low_speed == 1

    at_threshold = run(40.0)
    assert at_threshold.stats.eligible_boxes == 0
    assert at_threshold.stats.skipped_low_speed == 1

    above = run(55.0)
    assert above.stats.eligible_boxes == 1
    assert above.stats.skipped_low_speed == 0


def test_cluster_count_follows_the_cal_table():
    # Ticket 29c mục 7: bảng `cal` nội suy, không phải (0,2*wfh+0,1)*(v-50).
    assert cluster_count_for_speed(39.0) == 0
    assert cluster_count_for_speed(40.0) == 0
    assert cluster_count_for_speed(45.0) == 0
    assert cluster_count_for_speed(50.0) == 4
    assert cluster_count_for_speed(60.0) == 11
    assert cluster_count_for_speed(80.0) == 22
    assert cluster_count_for_speed(100.0) == 29
    assert cluster_count_for_speed(130.0) == 18


def test_no_clusters_at_45_kmh():
    assert cluster_count_for_speed(45.0) == 0


def test_cluster_count_at_130_kmh_with_one_mm_water_film():
    assert cluster_count_for_speed(130.0, PlumeConfig(water_film_height_m=0.001)) == 18
    assert cluster_count_for_speed(130.0, PlumeConfig(water_film_height_m=0.0)) == 0


def test_cluster_count_at_80_kmh_matches_the_table():
    # Bảng `cal` cho 22,02 cụm/frame ở 80 km/h.
    assert cluster_count_for_speed(80.0) == 22


def test_steady_state_cluster_factor_is_geometric_sum():
    """K = Σ exp(-k·Δt/T), Δt = 0,1 s, T = 0,2 s → 2,51; không phải hằng số bịa."""
    config = PlumeConfig()
    at_fifty = steady_state_cluster_factor(50.0, config)
    expected = sum(np.exp(-k * 0.1 / 0.2) for k in range(9))

    assert at_fifty == pytest.approx(expected)
    assert at_fifty == pytest.approx(2.5133, abs=1e-3)
    # T tăng nhẹ theo tốc độ (dee.cpp:530) nên K ở 130 km/h lớn hơn.
    assert steady_state_cluster_factor(130.0, config) > at_fifty


def test_no_lifetime_dropout_generates_full_steady_state_count():
    """Ticket 22: bỏ dropout age ~ U(0,4T); mọi cụm sinh ra đều còn lại."""
    points = np.zeros((1, 5), dtype=np.float32)
    box = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 80.0 / 3.6, 0.0]], dtype=np.float32
    )
    config = _config(distance_range_m=(5.0, 5.0))

    result = inject_plume(points, box, seed=0, config=config)

    expected = cluster_count_for_speed(80.0, config)
    assert expected == 22
    assert result.stats.clusters_spawned == expected
    assert result.stats.clusters == expected
    assert result.stats.clusters_dropped_lifetime == 0


def test_points_per_cluster_matches_measured_median():
    """Trung bình điểm/cụm phải quanh median thật (17) chứ không phải 32 cố định."""
    points = np.zeros((1, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 27.8, 0.0]], dtype=np.float32
    )
    per_cluster = [
        r.stats.injected / r.stats.clusters
        for seed in range(40)
        for r in [inject_plume(points, boxes, seed=seed, token="dist")]
        if r.stats.clusters
    ]

    assert 14 <= float(np.mean(per_cluster)) <= 30


def _single_clusters(distance, *, seeds, tag):
    """Một cụm cho mỗi seed, dựng bằng đúng các primitive của generator.

    Từ ticket 29c, một frame luôn có ít nhất 4 cụm (bảng `cal` bắt đầu ở
    50 km/h), nên không thể lấy "đúng một cụm" bằng ``inject_plume`` nữa.
    Các test dưới chỉ kiểm hình học một cụm, độc lập với số cụm/frame.
    """
    config = PlumeConfig()
    direction = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    clusters = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        count = _count_for_distance(rng, distance, config)
        radius = _lognormal_clipped(
            rng,
            config.cluster_radius_median_m,
            config.cluster_radius_sigma,
            config.cluster_radius_bounds_m,
        )
        offsets = _thin_radial(
            _ball(rng, count, radius), direction, config.radial_squash
        )
        center = direction * distance + np.array([0.0, 0.0, 1.0])
        clusters.append((offsets + center).astype(np.float64))
    return clusters


def test_radial_thinning_matches_measured_ratio():
    """Median per-cluster r_range/r_extent = 1,28 như ticket 16 đo trên dữ liệu thật."""
    ratios = []
    for distance in np.arange(8.0, 30.5, 1.0):
        for xyz in _single_clusters(float(distance), seeds=range(40), tag="ratio"):
            centroid = xyz.mean(axis=0)
            r_extent = np.linalg.norm(xyz - centroid, axis=1).max()
            radii = np.linalg.norm(xyz, axis=1)
            ratios.append((radii.max() - radii.min()) / r_extent)

    assert len(ratios) >= 200
    assert 1.22 <= float(np.median(ratios)) <= 1.34


def test_cluster_radius_capped_at_one_meter():
    """Ticket 23: trần 1,0 m theo dee.cpp:528; ~6,7% lognormal vượt trần bị bóp."""
    config = PlumeConfig()
    assert config.cluster_radius_bounds_m == (0.10, 1.00)

    rng = np.random.default_rng(23)
    radii = np.array(
        [
            _lognormal_clipped(
                rng,
                config.cluster_radius_median_m,
                config.cluster_radius_sigma,
                config.cluster_radius_bounds_m,
            )
            for _ in range(20_000)
        ]
    )

    assert radii.max() <= 1.0
    at_cap = float((radii >= 1.0).mean())
    assert 0.05 <= at_cap <= 0.09, at_cap


def test_points_per_cluster_decreases_with_range():
    """Median điểm/cụm bám bảng đo: 30 ở 0–5 m, 14 ở 10–20 m, 10 ở 20–30 m."""
    for distance, expected in ((4.0, 30), (15.0, 14), (25.0, 10)):
        counts = [
            len(xyz)
            for xyz in _single_clusters(distance, seeds=range(120), tag="count")
        ]
        assert len(counts) >= 100
        median = float(np.median(counts))
        assert abs(median - expected) <= 0.25 * expected, (distance, median, expected)
