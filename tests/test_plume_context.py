import numpy as np
import pytest

from spray.plume import PlumeConfig, inject_plume
from spray.plume_context import (
    PlumeContext,
    PlumeContextError,
    compute_elevation_deg,
    seed_for,
)
from spray.plume_transform import PlumeTransform


def _context(**overrides):
    fields = {
        "scene_token": "scene-0001",
        "frame_index": 7,
        "epoch": 2,
        "sensor_origin": np.array([0.5, 0.0, 1.8], dtype=np.float64),
        "ego_speed_mps": 13.9,
        "object_speed_mps": 13.9,
        "wfh_mm": 1.0,
        "road_z_m": -0.35,
        "ego_pose": np.eye(4, dtype=np.float64),
        "elevation_angles_deg": np.linspace(-25.0, 15.0, 32),
        "boxes": np.zeros((2, 9), dtype=np.float64),
    }
    fields.update(overrides)
    return PlumeContext(**fields)


def _sample():
    return {
        "scene_token": "scene-0001",
        "timestamp": 1_700_000_000_000_000,
        "ego2global": np.eye(4, dtype=np.float64),
        "sensor_origin": np.array([0.5, 0.0, 1.8], dtype=np.float64),
        "ego_speed_mps": 13.9,
        "object_speed_mps": 13.9,
    }


def test_context_keeps_required_and_optional_fields():
    context = _context(wfh_mm=0.75)

    assert context.scene_token == "scene-0001"
    assert context.frame_index == 7
    assert context.epoch == 2
    assert np.array_equal(context.sensor_origin, np.array([0.5, 0.0, 1.8]))
    assert context.ego_speed_mps == 13.9
    assert context.object_speed_mps == 13.9
    assert context.wfh_mm == 0.75
    assert context.road_z_m == -0.35
    assert np.array_equal(context.ego_pose, np.eye(4))
    assert context.elevation_angles_deg.shape == (32,)
    assert context.boxes.shape == (2, 9)


def test_from_sample_without_scene_token_raises():
    sample = _sample()
    del sample["scene_token"]

    with pytest.raises(PlumeContextError, match="scene_token"):
        PlumeContext.from_sample(
            sample, epoch=0, wfh_mm=1.0, road_z_m=-0.35, frame_index=3
        )


def test_without_context_matches_direct_inject_plume():
    points = np.zeros((4, 5), dtype=np.float32)
    boxes = np.array(
        [[0.0, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, 20.0, 0.0]], dtype=np.float32
    )
    config = PlumeConfig(
        distance_range_m=(3.0, 6.0),
        points_per_cluster_sigma=0.0,
        cluster_radius_sigma=0.0,
    )
    transform = PlumeTransform(config=config, seed=11)
    results = {
        "points": points,
        "gt_bboxes_3d": boxes,
        "metadata": {"token": "scene-legacy", "seed": 11},
    }

    out = transform(results)
    expected = inject_plume(points, boxes, seed=11, token="scene-legacy", config=config)

    assert np.array_equal(out["points"], expected.points)
    assert np.array_equal(out["points_clean"], expected.points_clean)
    assert out["spray_stats"]["injected"] == expected.stats.injected


def test_seed_for_changes_with_epoch_and_is_repeatable():
    base = seed_for("scene-0001", 7, 0)

    assert seed_for("scene-0001", 7, 0) == base
    assert seed_for("scene-0001", 7, 1) != base
    assert seed_for("scene-0001", 7, 2) != base
    assert seed_for("scene-0001", 7, 0, base_seed=5) != base


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"wfh_mm": 0.0}, "wfh_mm"),
        ({"wfh_mm": 1.3}, "wfh_mm"),
        ({"road_z_m": float("nan")}, "road_z_m"),
    ],
)
def test_invalid_context_raises_named_field(overrides, field):
    with pytest.raises(PlumeContextError, match=field):
        _context(**overrides)


def test_none_elevation_falls_back_to_point_geometry():
    context = _context(elevation_angles_deg=None)
    points = np.array(
        [
            [3.0, 4.0, 5.0, 0.0, 0.0],
            [1.0, 0.0, -1.0, 0.0, 0.0],
            [0.0, 2.0, 0.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )

    angles = compute_elevation_deg(points)
    expected = np.degrees(
        np.arctan2(points[:, 2], np.hypot(points[:, 0], points[:, 1]))
    )

    assert context.elevation_angles_deg is None
    assert angles.shape == (len(points),)
    assert np.allclose(angles, expected)
