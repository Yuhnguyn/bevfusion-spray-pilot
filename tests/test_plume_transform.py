import numpy as np

from spray.plume import PlumeConfig
from spray.plume_transform import PlumeTransform


def _config():
    return PlumeConfig(
        point_cloud_range=(-54.0, -54.0, -5.0, 54.0, 54.0, 3.0),
        distance_range_m=(3.0, 6.0),
        points_per_cluster_median=20.0,
        points_per_cluster_sigma=0.0,
        cluster_radius_sigma=0.0,
        max_injected_points=200,
    )


def test_disabled_keeps_clean_and_points_identical():
    points = np.zeros((3, 5), dtype=np.float32)
    out = PlumeTransform(enabled=False).__call__(
        {"points": points, "gt_bboxes_3d": np.empty((0, 9), dtype=np.float32)}
    )

    assert np.array_equal(out["points"], points)
    assert np.array_equal(out["points_clean"], points)
    assert out["spray_stats"]["injected"] == 0


def test_enabled_injects_and_keeps_pre_injection_points():
    points = np.zeros((1, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )
    out = PlumeTransform(config=_config(), seed=1).__call__(
        {"points": points, "gt_bboxes_3d": boxes}
    )

    assert np.array_equal(out["points_clean"], points)
    assert len(out["points"]) > len(points)
    assert out["spray_stats"]["injected"] > 0
