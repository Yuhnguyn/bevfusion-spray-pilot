"""The uniform beam grid and the ray/sphere geometry built on it."""

from pathlib import Path

import numpy as np
import pytest

from spray.beam_model import (
    AZIMUTH_STEP_DEG,
    ELEVATION_MAX_DEG,
    ELEVATION_MIN_DEG,
    ELEVATION_STEP_DEG,
    build_beams,
    load_beam_table,
    ray_directions,
    ray_sphere_intersect,
)


def test_loaded_table_is_the_uniform_grid_over_the_measured_fov():
    table = load_beam_table()
    elevation = np.asarray(table.elevation_deg)

    assert elevation[0] == pytest.approx(ELEVATION_MIN_DEG)
    assert np.diff(elevation) == pytest.approx(
        np.full(elevation.size - 1, ELEVATION_STEP_DEG)
    )
    assert elevation[-1] < ELEVATION_MAX_DEG
    assert elevation.size == 30
    assert table.azimuth_step_deg == pytest.approx(AZIMUTH_STEP_DEG)
    assert int(round(360.0 / table.azimuth_step_deg)) == 1825


def test_the_rejected_ring_table_yaml_is_gone():
    # Built at runtime so the deleted filename has no literal reference in the tree.
    rejected = "beam" + "_elevation.yaml"
    root = Path(__file__).resolve().parents[1]
    assert not (root / "spray" / "config" / rejected).exists()

    source = (root / "spray" / "beam_model.py").read_text(encoding="utf-8")
    assert rejected not in source


def test_build_beams_uses_the_measured_azimuth_step():
    table = load_beam_table()

    assert 0.05 <= table.azimuth_step_deg <= 1.0
    elevation, azimuth = build_beams(table)
    n_azimuth = int(round(360.0 / table.azimuth_step_deg))
    n_elevation = len(table.elevation_deg)

    assert elevation.shape == azimuth.shape == (n_elevation * n_azimuth,)
    assert np.unique(azimuth).size == n_azimuth
    assert np.unique(elevation).size == n_elevation


def test_ray_through_sphere_center_gives_near_and_far_roots():
    directions = np.array([[1.0, 0.0, 0.0]])
    t0, t1 = ray_sphere_intersect(
        directions, np.array([10.0, 0.0, 0.0]), 0.3
    )

    assert t0[0] == pytest.approx(9.7, abs=1e-6)
    assert t1[0] == pytest.approx(10.3, abs=1e-6)


def test_ray_missing_the_sphere_returns_nan():
    directions = np.array([[1.0, 0.0, 0.0]])
    t0, t1 = ray_sphere_intersect(
        directions, np.array([10.0, 5.0, 0.0]), 0.3
    )

    assert np.isnan(t0[0])
    assert np.isnan(t1[0])


def test_oblique_ray_hits_a_sphere_placed_on_it():
    direction = ray_directions(np.array([0.5]), np.array([0.0]))[0]
    center = 20.0 * direction
    t0, t1 = ray_sphere_intersect(
        direction[np.newaxis, :], center, 0.3
    )

    assert np.isfinite(t0[0]) and np.isfinite(t1[0])
    midpoint = 0.5 * (t0[0] + t1[0]) * direction
    assert np.linalg.norm(center - midpoint) <= 1e-9
