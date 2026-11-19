"""Contract tests for the Hahner et al. (2022) wet-ground model.

``spray/wet_ground.py`` ports section 3.1 and Algorithm 2 of arXiv 2203.15118,
the model Linnhoff et al. (2022) use for the wet road surface.  These tests pin
the three properties that make the port different from the old
``dee.cpp``-derived version: a dry film is a no-op, a wet film only ever
attenuates, and grazing incidence attenuates more than a close return.
"""

from __future__ import annotations

import numpy as np

from spray.wet_ground import WetGroundConfig, apply_wet_ground

ROAD_Z_M = -0.411
WET = WetGroundConfig(enabled=True)


def _road_points() -> np.ndarray:
    """Four pavement points at different ranges, all with positive intensity."""

    return np.array(
        [
            [0.2, 0.0, ROAD_Z_M, 120.0, 3.0],
            [5.0, 2.0, ROAD_Z_M, 160.0, 3.0],
            [20.0, -8.0, ROAD_Z_M, 200.0, 3.0],
            [80.0, 15.0, ROAD_Z_M, 90.0, 3.0],
        ],
        dtype=np.float32,
    )


def test_dry_water_film_leaves_intensity_unchanged():
    points = _road_points()

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=0.0, config=WET
    )

    assert stats.points_in == len(points)
    assert stats.points_removed == 0
    assert stats.mean_ratio == 1.0
    assert np.array_equal(out, points)


def test_wet_water_film_attenuates():
    points = _road_points()

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=WET
    )

    assert stats.points_in == len(points)
    assert stats.points_removed == 0
    assert 0.0 < stats.mean_ratio < 1.0
    assert np.all(out[:, 3] < points[:, 3])


def test_grazing_angle_attenuates_more():
    # 0.2 m horizontally from the sensor: alpha ~ 26 deg.  100 m away:
    # alpha ~ 90 deg.  Same intensity, so the ratio isolates the Fresnel term.
    points = np.array(
        [
            [0.2, 0.0, ROAD_Z_M, 150.0, 3.0],
            [100.0, 0.0, ROAD_Z_M, 150.0, 3.0],
        ],
        dtype=np.float32,
    )

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=WET
    )

    near_ratio = out[0, 3] / points[0, 3]
    far_ratio = out[1, 3] / points[1, 3]
    print(f"near_ratio={near_ratio:.5f} far_ratio={far_ratio:.5f}")
    assert far_ratio < near_ratio
    assert 0.0 < stats.mean_ratio < 1.0
    assert stats.mean_alpha_deg > 45.0


def test_points_outside_band_untouched():
    points = np.array(
        [
            [10.0, 0.0, ROAD_Z_M, 180.0, 3.0],
            [10.0, 0.0, ROAD_Z_M + 1.0, 180.0, 3.0],
            [10.0, 0.0, ROAD_Z_M + 0.6, 70.0, 3.0],
        ],
        dtype=np.float32,
    )

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=WET
    )

    assert stats.points_in == 1
    assert out[0, 3] < points[0, 3]
    assert np.array_equal(out[1:, 3], points[1:, 3])


def test_no_boost_branch():
    y = np.linspace(-50.0, 50.0, 1000)
    points = np.column_stack(
        [
            np.full(1000, 10.0),
            y,
            np.full(1000, ROAD_Z_M),
            np.full(1000, 200.0),
            np.full(1000, 3.0),
        ]
    ).astype(np.float32)

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=WET
    )

    assert stats.points_in == len(points)
    assert np.all(out[:, 3] <= points[:, 3])
    assert np.any(out[:, 3] < points[:, 3])
    assert stats.mean_ratio < 1.0
