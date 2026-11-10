"""Ticket 27b: wet-ground attenuation wired into the stateful plume.

Wet ground is applied to the cloud used as the plume background *before* the
injected points are appended.  ``points_clean`` stays the untouched camera
input, and the feature is off by default so the legacy call path is unchanged.
"""

from __future__ import annotations

import numpy as np

from spray.plume import inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.wet_ground import WetGroundConfig

TOKEN = "scene-wet-integration"
ROAD_Z_M = -0.411
SPEED_MPS = 22.0
BOX = np.array(
    [[23.2, 0.0, 0.899, 2.42, 6.83, 2.62, 0.0, SPEED_MPS, 0.0]],
    dtype=np.float32,
)
EMPTY_BOXES = np.empty((0, 9), dtype=np.float32)


def _context(frame_index: int = 0) -> PlumeContext:
    return PlumeContext(
        scene_token=TOKEN,
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.array([0.0, 0.0, 1.8], dtype=np.float64),
        ego_speed_mps=SPEED_MPS,
        object_speed_mps=SPEED_MPS,
        wfh_mm=1.0,
        road_z_m=ROAD_Z_M,
    )


def _run(points, *, boxes=BOX, wet_ground=None, seed=11):
    return inject_plume_stateful(
        points,
        boxes,
        _context(),
        PlumeState(),
        seed=seed,
        token=TOKEN,
        wet_ground=wet_ground,
    )


def test_none_matches_call_without_the_parameter():
    points = np.array(
        [
            [6.0, 4.0, ROAD_Z_M, 180.0, 3.0],
            [8.0, 9.0, ROAD_Z_M, 90.0, 4.0],
            [10.0, -3.0, 2.5, 40.0, 5.0],
        ],
        dtype=np.float32,
    )

    without = _run(points, seed=5)
    explicit_none = _run(points, seed=5, wet_ground=None)

    assert np.array_equal(without.points, explicit_none.points)
    assert np.array_equal(without.points_clean, explicit_none.points_clean)
    assert np.array_equal(without.injected, explicit_none.injected)
    assert without.stats.injected == explicit_none.stats.injected


def test_high_cloud_is_untouched_and_reports_no_pavement_points():
    points = np.array(
        [
            [5.0, 0.0, 5.0, 120.0, 1.0],
            [7.0, 2.0, 5.0, 80.0, 2.0],
            [9.0, 4.0, 5.0, 60.0, 3.0],
        ],
        dtype=np.float32,
    )

    result = _run(
        points,
        boxes=EMPTY_BOXES,
        wet_ground=WetGroundConfig(enabled=True),
    )

    assert np.array_equal(result.points, points)
    assert result.stats.wet_points_in == 0


def test_pavement_point_attenuates_background_but_not_points_clean():
    points = np.array(
        [
            [10.0, 4.0, ROAD_Z_M, 200.0, 3.0],
            [12.0, 5.0, ROAD_Z_M, 120.0, 4.0],
            [14.0, 4.0, 1.5, 90.0, 5.0],
        ],
        dtype=np.float32,
    )

    result = _run(
        points,
        boxes=EMPTY_BOXES,
        wet_ground=WetGroundConfig(enabled=True),
    )

    print(
        f"wet_points_in={result.stats.wet_points_in} "
        f"wet_mean_ratio={result.stats.wet_mean_ratio:.4f}"
    )

    assert np.array_equal(result.points_clean[:, 3], points[:, 3])
    assert result.points[: len(points)][0, 3] < points[0, 3]
    assert result.stats.wet_points_in == 2
    assert 0.0 < result.stats.wet_mean_ratio < 1.0


def test_marker_only_printed_when_wet_ground_is_enabled(capsys):
    points = np.array([[10.0, 4.0, ROAD_Z_M, 200.0, 3.0]], dtype=np.float32)

    _run(points, boxes=EMPTY_BOXES, wet_ground=WetGroundConfig(enabled=True))
    enabled_lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("WET_GROUND_STATS")
    ]
    assert len(enabled_lines) == 1

    _run(points, boxes=EMPTY_BOXES, wet_ground=None)
    disabled_lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("WET_GROUND_STATS")
    ]
    assert len(disabled_lines) == 0
