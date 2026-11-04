import numpy as np
import pytest

from spray.plume import PlumeConfig, inject_plume


def _config(**overrides):
    values = dict(
        point_cloud_range=(-54.0, -54.0, -5.0, 54.0, 54.0, 3.0),
        distance_range_m=(3.0, 6.0),
        points_per_cluster=20,
        max_injected_points=200,
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
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 10.0, 0.0]], dtype=np.float32
    )

    result = inject_plume(points, boxes, seed=1, config=_config())

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
    points = np.zeros((1, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )
    config = _config(
        points_per_cluster=100,
        clusters_per_kmh=1.0,
        max_injected_points=25,
    )

    result = inject_plume(points, boxes, seed=3, config=config)

    assert result.stats.injected == 25
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
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 12.0, 0.0]], dtype=np.float32
    )
    config = _config()

    first = inject_plume(points, boxes, seed=7, token="scene-1", config=config)
    second = inject_plume(points, boxes, seed=7, token="scene-1", config=config)
    other = inject_plume(points, boxes, seed=8, token="scene-1", config=config)

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
