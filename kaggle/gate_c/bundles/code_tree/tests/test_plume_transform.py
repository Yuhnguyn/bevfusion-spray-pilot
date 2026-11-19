"""Ticket 29e: ``PlumeTransform`` always runs stateful + ray casting.

The transform refuses a missing context instead of silently falling back to the
stateless generator, keeps ``points_clean`` byte-equal, and reports the ray
cast counters in ``spray_stats``.
"""

import re

import numpy as np
import pytest

from spray.beam_model import (
    ELEVATION_MIN_DEG,
    ELEVATION_STEP_DEG,
    load_beam_table,
)
from spray.plume_context import PlumeContext
from spray.plume_transform import PlumeTransform

ROAD_Z_M = -0.411
SPEED_MPS = 100.0 / 3.6
BOX = np.array(
    [[20.0, 0.0, 0.899, 2.42, 6.8268, 2.6206, 0.0, SPEED_MPS, 0.0]],
    dtype=np.float32,
)


def _context(frame_index=0):
    return PlumeContext(
        scene_token="scene-29e",
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=SPEED_MPS,
        object_speed_mps=SPEED_MPS,
        wfh_mm=1.0,
        road_z_m=ROAD_Z_M,
    )


def _points():
    return np.array(
        [
            [30.0, 0.0, 0.5, 100.0, 12.0],
            [10.0, 2.0, 0.2, 80.0, 12.0],
            [5.0, -1.0, 1.0, 60.0, 13.0],
        ],
        dtype=np.float32,
    )


def _run(transform, frame_index, points=None, boxes=BOX):
    return transform(
        {
            "points": _points() if points is None else points,
            "gt_bboxes_3d": boxes,
            "plume_context": _context(frame_index),
            "metadata": {"token": "scene-29e", "seed": 0},
        }
    )


def test_disabled_keeps_clean_and_points_identical():
    points = np.zeros((3, 5), dtype=np.float32)
    out = PlumeTransform(enabled=False).__call__(
        {"points": points, "gt_bboxes_3d": np.empty((0, 9), dtype=np.float32)}
    )

    assert np.array_equal(out["points"], points)
    assert np.array_equal(out["points_clean"], points)
    assert out["spray_stats"]["injected"] == 0


def test_enabled_without_context_raises():
    with pytest.raises(RuntimeError, match="requires plume_context"):
        PlumeTransform()(
            {"points": _points(), "gt_bboxes_3d": BOX}
        )


def test_clean_points_are_byte_equal_and_points_are_real_then_detections():
    transform = PlumeTransform(seed=3)
    points = _points()
    det = 0
    for frame in range(10):
        out = _run(transform, frame, points=points.copy())
        if out["spray_stats"]["det"] > 0:
            det = out["spray_stats"]["det"]
            break

    assert det > 0
    assert out["points_clean"].tobytes() == points.tobytes()
    augmented = np.asarray(out["points"])
    assert len(augmented) >= det
    # Detections are appended after the real returns and always have intensity 0.
    assert np.all(augmented[-det:, 3] == 0.0)


def test_marker_has_the_six_keys_once_per_frame(capsys):
    regex = re.compile(
        r"PLUME_RAYCAST beams=(\d+) hit=(\d+) det=(\d+) "
        r"att_m=([0-9.]+) capped=(\d+) ms=([0-9.]+)"
    )
    transform = PlumeTransform(seed=5)
    for frame in range(5):
        _run(transform, frame)

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("PLUME_RAYCAST")
    ]
    assert lines
    assert all(regex.fullmatch(line) for line in lines)


def test_real_points_behind_a_cluster_are_attenuated():
    transform = PlumeTransform(seed=7)
    table = load_beam_table()
    points = np.random.default_rng(0).uniform(
        [-40.0, -20.0, -1.0], [40.0, 20.0, 2.0], size=(20_000, 3)
    )
    elevation = np.degrees(
        np.arctan2(points[:, 2], np.hypot(points[:, 0], points[:, 1]))
    )
    ring = np.clip(
        np.rint((elevation - ELEVATION_MIN_DEG) / ELEVATION_STEP_DEG),
        0,
        len(table.elevation_deg) - 1,
    )
    cloud = np.column_stack(
        [points, np.full(len(points), 100.0), ring]
    ).astype(np.float32)

    # Warm the state with tiny point clouds (ray casting on 20k points is
    # expensive), then cast one dense frame through the resulting clusters.
    for frame in range(10):
        _run(transform, frame, points=np.zeros((3, 5), dtype=np.float32))
    out = _run(transform, 10, points=cloud.copy())
    att = out["spray_stats"]["att_real_points"]

    assert att > 0
    # ``points_clean`` must not carry the attenuation.
    assert out["points_clean"].tobytes() == cloud.tobytes()
    assert np.all(out["points_clean"][:, 3] == 100.0)
