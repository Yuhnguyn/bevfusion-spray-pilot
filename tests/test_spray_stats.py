import numpy as np
import pytest

from spray.spray_stats import (
    StatsAccumulator,
    compare_to_simulator,
    load_scan,
    noise_points,
    render_markdown,
    scan_clusters,
    simulator_estimate,
    single_linkage,
)


def _points(*rows):
    return np.asarray(rows, dtype=np.float32)


def test_single_linkage_groups_nearby_points_only():
    xy = np.array([[0.0, 0.0], [0.3, 0.0], [2.0, 0.0], [2.2, 0.0]])

    labels = single_linkage(xy, radius=0.5)

    assert labels.tolist() == [0, 0, 1, 1]


def test_single_linkage_chains_adjacent_points():
    xy = np.array([[0.0, 0.0], [0.4, 0.0], [0.8, 0.0]])

    labels = single_linkage(xy, radius=0.5)

    assert len(set(labels.tolist())) == 1


def test_single_linkage_empty_input():
    assert single_linkage(np.zeros((0, 2)), radius=0.5).shape == (0,)


def test_noise_points_filters_by_label_and_checks_length():
    points = _points([0, 0, 0, 0, 0], [1, 1, 1, 2, 3])
    labels = np.array([0, 2], dtype=np.int32)

    assert np.array_equal(noise_points(points, labels), points[[1]])

    with pytest.raises(ValueError):
        noise_points(points, np.array([0], dtype=np.int32))


def test_scan_clusters_reports_centroid_extent_and_distances():
    points = _points(
        [10.0, 0.0, 1.0, 0.0, 0.0],
        [10.2, 0.0, 1.2, 0.0, 0.0],
        [0.0, 20.0, 0.0, 0.0, 0.0],
        [12.0, 0.0, 0.0, 0.0, 0.0],
    )
    labels = np.array([2, 2, 2, 1], dtype=np.int32)

    clusters = scan_clusters(points, labels, radius=0.5)

    assert len(clusters) == 2
    near = clusters[0]
    assert near.point_count == 2
    assert near.centroid == pytest.approx((10.1, 0.0, 1.1))
    assert near.extent == pytest.approx((0.2, 0.0, 0.2), abs=1e-6)
    assert near.ego_distance_m == pytest.approx(float(np.hypot(10.1, 0.0)))
    assert near.vehicle_distance_m == pytest.approx(float(np.hypot(1.9, 0.0)))


def test_scan_clusters_without_noise_or_foreground():
    points = _points([1.0, 1.0, 0.0, 0.0, 0.0])
    labels = np.array([0], dtype=np.int32)

    assert scan_clusters(points, labels) == []

    noise_only = _points([5.0, 0.0, 0.0, 0.0, 0.0])
    clusters = scan_clusters(noise_only, np.array([2], dtype=np.int32))
    assert clusters[0].vehicle_distance_m is None


def test_accumulator_summarizes_frames_and_clusters():
    accumulator = StatsAccumulator(radius=0.5, dense_min=2)

    accumulator.add(
        _points([0, 0, 0, 0, 0], [0.2, 0, 0.5, 4, 0], [9, 9, 1, 0, 0]),
        np.array([2, 2, 1], dtype=np.int32),
    )
    accumulator.add(
        _points([1, 1, 1, 0, 0]),
        np.array([2], dtype=np.int32),
    )

    summary = accumulator.summary()

    assert summary["frames"] == 2
    assert summary["frames_with_noise"] == 2
    assert summary["noise_frame_median"] == pytest.approx(1.5)
    assert summary["cluster_size_max"] == pytest.approx(2)
    assert summary["dense_cluster_count"] == 1
    assert summary["dense_points_frame_median"] == pytest.approx(1.0)
    assert summary["dense_clusters_frame_median"] == pytest.approx(0.5)
    assert summary["intensity_median"] == pytest.approx(0.0)
    assert summary["height_median_m"] == pytest.approx(0.5)


def test_simulator_estimate_respects_min_speed_and_clips():
    at_fifty = simulator_estimate(speed_kmh=50.0)
    stopped = simulator_estimate(speed_kmh=0.0)
    at_fast = simulator_estimate(speed_kmh=500.0)

    assert at_fifty["clusters_per_frame"] == 2
    assert at_fifty["points_per_frame"] == 34
    assert stopped["clusters_per_frame"] == 0
    assert stopped["points_per_frame"] == 0
    assert at_fast["clusters_per_frame"] == 8


def test_compare_rows_expose_simulator_values():
    summary = StatsAccumulator().summary()

    rows = {row["metric"]: row for row in compare_to_simulator(summary)}

    assert rows["points/cluster (dense median)"]["simulator"] == 17.0
    assert rows["distance to nearest vehicle point (m)"]["simulator"] == (1.0, 10.0)
    assert rows["intensity (median)"]["simulator"] == 0.0


def test_render_markdown_mentions_simulator_and_caveats():
    accumulator = StatsAccumulator()
    accumulator.add(
        _points([1, 1, 1, 3, 0], [1.1, 1.0, 1.2, 0, 0]),
        np.array([2, 2], dtype=np.int32),
    )
    summary = accumulator.summary()

    report = render_markdown(
        summary,
        compare_to_simulator(summary),
        scenes=1,
        sampled_frames=1,
    )

    assert "# SemanticSpray statistics" in report
    assert "So với simulator" in report
    assert "intensity" in report
    assert "CC BY 4.0" in report


def test_load_scan_reads_points_and_labels(tmp_path):
    scene = tmp_path / "scene"
    (scene / "velodyne").mkdir(parents=True)
    (scene / "labels").mkdir()
    points = np.arange(10, dtype=np.float32).reshape(2, 5)
    points.tofile(scene / "velodyne" / "000000.bin")
    np.array([0, 2], dtype=np.int32).tofile(scene / "labels" / "000000.label")

    loaded, labels = load_scan(scene, "000000")

    assert np.array_equal(loaded, points)
    assert labels.tolist() == [0, 2]

    points.tofile(scene / "velodyne" / "000001.bin")
    np.array([0], dtype=np.int32).tofile(scene / "labels" / "000001.label")
    with pytest.raises(ValueError):
        load_scan(scene, "000001")
