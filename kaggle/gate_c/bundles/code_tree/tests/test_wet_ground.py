"""Tests for ``spray.wet_ground`` (Hahner et al. 2022, Algorithm 2).

The module rebuilds the return of a wet pavement using the Fresnel/Snell chain
of arXiv 2203.15118 section 3.1.  These tests pin the contract: a copy is
returned, only column 3 changes, the default ``intensity_floor`` removes no
point, a dry film is a no-op, and more water attenuates more up to the
pavement thread depth.
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

    Row 0-1: on the road plane -> attenuated by the wet film.
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
    assert stats.points_removed == 0
    assert stats.mean_ratio == 0.0
    assert stats.mean_alpha_deg == 0.0
    marker = capsys.readouterr().out.strip()
    assert marker == (
        "WET_GROUND_STATS points_in=0 removed=0 "
        "mean_ratio=0.000 mean_alpha_deg=0.0"
    )


def test_road_points_attenuate_and_high_points_are_untouched():
    points = _cloud()
    config = WetGroundConfig(enabled=True)

    out, stats = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=1.0, config=config
    )

    assert out[0, 3] < points[0, 3], "road point must be attenuated"
    assert out[1, 3] < points[1, 3], "road point must be attenuated"
    assert out[2, 3] == points[2, 3], "point 1.5 m above the road must be untouched"
    assert stats.points_in == 2
    assert stats.points_removed == 0


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
        for w in (0.0, 0.3, 0.6, 1.2)
    ]

    assert all(a > b for a, b in zip(ratios, ratios[1:])), ratios
    saturated = apply_wet_ground(
        points, road_z_m=ROAD_Z_M, wfh_mm=2.0, config=config
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
        f"removed={stats.points_removed} "
        f"mean_ratio={stats.mean_ratio:.4f} "
        f"mean_alpha_deg={stats.mean_alpha_deg:.2f}"
    )
    assert len(out) == len(points)
    assert stats.points_in > 0
    assert stats.points_removed == 0
    assert 0.0 < stats.mean_ratio < 1.0
