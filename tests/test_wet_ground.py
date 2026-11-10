"""Tests for ``spray.wet_ground`` (ticket 27a).

The module ports ``simulate_wet_pavement`` from
``DetectionEnvironmentalEffects.cpp:305-380`` (MPL-2.0).  These tests pin the
contract of the brief: a copy is returned, only column 3 changes, no point is
removed, and the real frame in the local SemanticSpray release produces a
non-trivial attenuation.

Note on water-film direction: eq. 19 uses
``gamma = clip(wfh / pavement_depth, 0, 1)`` with ``pavement_depth = 0.5 mm``,
so ``gamma`` saturates at ``wfh = 0.5 mm``.  In the source formula the wet term
``t_p`` is smaller than the dry term ``Gamma``, so more water means a *lower*
retained intensity.  Test 3 pins that direction instead of the brief's
"mean_ratio increases" sentence, which contradicts the formula.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from spray.wet_ground import WetGroundConfig, apply_wet_ground

REAL_FRAME = pathlib.Path(
    "data/SemanticSprayDataset/Crafter_dynamic/"
    "0000_2021-09-08-14-36-56_0/velodyne/000000.bin"
)
ROAD_Z_M = -0.411


def _cloud() -> np.ndarray:
    """One point per regime, all with distinct intensities.

    Row 0: on the road, y inside (2, 7) -> attenuated.
    Row 1: on the road, y outside (2, 7) -> boosted.
    Row 2: 1.5 m above the road -> untouched.
    """
    return np.array(
        [
            [10.0, 4.0, ROAD_Z_M, 200.0, 3.0],
            [10.0, 10.0, ROAD_Z_M, 100.0, 3.0],
            [10.0, 4.0, 1.5, 120.0, 3.0],
        ],
        dtype=np.float32,
    )


def test_disabled_returns_an_untouched_copy_and_zero_stats(capsys):
    points = _cloud()

    out, stats = apply_wet_ground(points, road_z_m=ROAD_Z_M, wfh_mm=1.0)

    assert out is not points
    assert np.array_equal(out, points)
    assert stats.points_in == 0
    assert stats.attenuated == 0
    assert stats.boosted == 0
    assert stats.mean_ratio == 0.0
    marker = capsys.readouterr().out.strip()
    assert marker == "WET_GROUND_STATS points_in=0 attenuated=0 boosted=0 mean_ratio=0.000"


def test_three_regimes_attenuate_boost_and_leave_high_points_alone():
    points = _cloud()
    config = WetGroundConfig(enabled=True)

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=config
    )

    assert out[0, 3] < points[0, 3], "in-window road point must be attenuated"
    assert out[1, 3] > points[1, 3], "out-of-window road point must be boosted"
    assert out[2, 3] == points[2, 3], "point 1.5 m above the road must be untouched"
    assert stats.points_in == 2
    assert stats.attenuated == 1
    assert stats.boosted == 1


def test_mean_ratio_falls_with_water_film_and_saturates_at_pavement_depth():
    points = np.array(
        [
            [4.0, 3.0, ROAD_Z_M, 90.0, 1.0],
            [8.0, 5.0, ROAD_Z_M, 120.0, 2.0],
            [12.0, 4.0, ROAD_Z_M, 160.0, 3.0],
        ],
        dtype=np.float32,
    )
    config = WetGroundConfig(enabled=True)

    ratios = [
        apply_wet_ground(points, road_z_m=ROAD_Z_M, wfh_mm=w, config=config)[1].mean_ratio
        for w in (0.0, 0.1, 0.25, 0.5)
    ]

    assert all(a > b for a, b in zip(ratios, ratios[1:])), ratios
    saturated = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=config
    )[1].mean_ratio
    assert saturated == pytest.approx(ratios[-1])


def test_no_points_removed_and_only_intensity_column_changes():
    points = _cloud()
    config = WetGroundConfig(enabled=True)

    out, _ = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=0.25, config=config
    )

    assert len(out) == len(points)
    assert np.array_equal(out[:, :3], points[:, :3])
    assert np.array_equal(out[:, 4], points[:, 4])


def test_real_semantic_spray_frame(capsys):
    points = np.fromfile(REAL_FRAME, dtype=np.float32).reshape(-1, 5)
    config = WetGroundConfig(enabled=True)

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=config
    )

    print(
        "real frame: "
        f"points_in={stats.points_in} "
        f"attenuated={stats.attenuated} "
        f"boosted={stats.boosted} "
        f"mean_ratio={stats.mean_ratio:.4f}"
    )
    assert len(out) == len(points)
    assert stats.points_in > 0
    assert stats.attenuated > 0
    assert 0.2 <= stats.mean_ratio <= 1.0
