import numpy as np
import pytest

from spray.semantic_stats import (
    StatsAccumulator,
    cluster_angular,
    fit_ground_plane,
    frame_stats,
    frame_stats_pair,
    metrics,
)


def _cloud(rows, labels):
    points = np.asarray(rows, dtype=np.float32).reshape(-1, 5)
    return points, np.asarray(labels, dtype=np.uint32)


def test_legacy_recipe_keeps_only_clusters_with_min_pts():
    points, labels = _cloud(
        [
            [10.0, 0.0, 0.0, 0.0, 0.0],
            [10.3, 0.0, 0.0, 0.0, 0.0],
            [20.0, 0.0, 0.0, 0.0, 0.0],
            [20.3, 0.0, 0.0, 0.0, 0.0],
            [20.6, 0.0, 0.0, 0.0, 0.0],
            [30.0, 0.0, 0.0, 0.0, 0.0],
        ],
        [2, 2, 2, 2, 2, 1],
    )

    stats = frame_stats(points, labels, recipe="legacy")

    assert stats["n_noise"] == 5
    assert stats["cluster_sizes"].tolist() == [3]
    assert len(stats["abs_y"]) == 5


def test_range_over_extent_matches_hand_calculation():
    points, labels = _cloud(
        [
            [10.0, 0.0, 0.0, 0.0, 0.0],
            [10.3, 0.0, 0.0, 0.0, 0.0],
            [10.6, 0.0, 0.0, 0.0, 0.0],
        ],
        [2, 2, 2],
    )

    stats = frame_stats(points, labels, recipe="legacy")

    assert len(stats["range_over_extent"]) == 1
    assert stats["range_over_extent"][0] == pytest.approx(2.0, abs=1e-6)


def test_abs_y_uses_noise_points_only():
    points, labels = _cloud(
        [
            [10.0, 2.5, 0.0, 0.0, 0.0],
            [10.0, -2.5, 0.0, 0.0, 0.0],
            [10.0, 9.0, 0.0, 0.0, 0.0],
        ],
        [2, 2, 1],
    )

    stats = frame_stats(points, labels)

    np.testing.assert_allclose(stats["abs_y"], [2.5, 2.5])


def test_height_above_road_subtracts_fitted_ground_plane():
    rows = []
    labels = []
    for x in np.linspace(5.0, 35.0, 31):
        for y in np.linspace(-5.0, 5.0, 5):
            rows.append([x, y, 0.0, 0.0, 0.0])
            labels.append(0)
    for x in (10.0, 12.0, 14.0, 16.0, 18.0):
        rows.append([x, 0.0, 0.5, 0.0, 0.0])
        labels.append(2)
    points, labels = _cloud(rows, labels)

    a, b, c = fit_ground_plane(points)
    assert a == pytest.approx(0.0, abs=1e-6)
    assert b == pytest.approx(0.0, abs=1e-6)
    assert c == pytest.approx(0.0, abs=1e-6)

    stats = frame_stats(points, labels)

    assert float(np.median(stats["height_above_road"])) == pytest.approx(
        0.5, abs=0.05
    )


def test_elevation_intensity_and_ring_columns():
    points, labels = _cloud(
        [
            [10.0, 0.0, 1.00, 7.0, 3.0],
            [10.2, 0.0, 1.02, 8.0, 4.0],
            [10.4, 0.0, 1.04, 9.0, 5.0],
            [0.0, 0.0, 0.00, 100.0, 31.0],
        ],
        [2, 2, 2, 1],
    )

    stats = frame_stats(points, labels)
    expected = np.degrees(
        np.arctan2(points[:3, 2], np.hypot(points[:3, 0], points[:3, 1]))
    )

    np.testing.assert_allclose(stats["elevation_deg"], expected, atol=1e-6)
    np.testing.assert_allclose(stats["intensity"], [7.0, 8.0, 9.0])
    np.testing.assert_allclose(stats["ring"], [3.0, 4.0, 5.0])

    summary = StatsAccumulator()
    summary.add(stats)
    legacy = StatsAccumulator()
    legacy.add(frame_stats(points, labels, recipe="legacy"))
    values = metrics(summary.summary(), legacy.summary())

    assert values["G1"] == pytest.approx(3.0)
    assert values["G2"] == pytest.approx(1.0)
    assert values["G3"] == pytest.approx(3.0)
    assert values["frames"] == 1
    assert values["n_clusters"] == 1
    assert values["legacy_G2"] == pytest.approx(1.0)
    assert values["legacy_G3"] == pytest.approx(3.0)


def test_frame_stats_pair_matches_single_recipe_calls():
    points, labels = _cloud(
        [
            [10.0, 0.0, 0.0, 0.0, 0.0],
            [10.3, 0.0, 0.0, 0.0, 0.0],
            [20.0, 0.0, 0.0, 0.0, 0.0],
            [20.3, 0.0, 0.0, 0.0, 0.0],
            [20.6, 0.0, 0.0, 0.0, 0.0],
        ],
        [2, 2, 2, 2, 2],
    )

    pair = frame_stats_pair(points, labels)

    assert pair["paper"]["cluster_sizes"].tolist() == [5]
    for recipe in ("paper", "legacy"):
        direct = frame_stats(points, labels, recipe=recipe)
        assert pair[recipe]["n_noise"] == direct["n_noise"]
        np.testing.assert_array_equal(
            pair[recipe]["cluster_sizes"], direct["cluster_sizes"]
        )
        np.testing.assert_allclose(
            pair[recipe]["range_over_extent"],
            direct["range_over_extent"],
        )
        np.testing.assert_allclose(
            pair[recipe]["height_above_road"],
            direct["height_above_road"],
        )


def test_cluster_angular_rejects_pair_below_min_pts():
    points = np.asarray(
        [
            [10.0, 0.00, 0.0],
            [10.0, 0.05, 0.0],
            [10.0, 0.10, 0.0],
            [10.0, 2.00, 0.0],
            [10.0, 2.05, 0.0],
        ],
        dtype=np.float64,
    )

    labels = cluster_angular(points)

    assert int((labels < 0).sum()) == 2
    assert len(set(labels[labels >= 0].tolist())) == 1


def test_cluster_angular_wraps_azimuth():
    azimuth = np.radians([359.0, 0.0, 1.0])
    points = np.column_stack(
        [10.0 * np.cos(azimuth), 10.0 * np.sin(azimuth), np.zeros(3)]
    )

    labels = cluster_angular(points, eps_deg=3.0)

    assert np.all(labels >= 0)
    assert len(set(labels.tolist())) == 1


def test_cluster_angular_snaps_elevation_to_grid():
    offset = 10.0 * np.tan(np.radians(0.34))
    points = np.asarray(
        [
            [10.0, 0.0, 0.0],
            [10.0, 0.0, offset],
            [10.0, 0.0, 0.0],
        ],
        dtype=np.float64,
    )

    labels = cluster_angular(points, eps_deg=0.335)

    assert np.all(labels >= 0)
