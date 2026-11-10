"""The measured beam table and the ray/sphere geometry built on it."""

import numpy as np
import pytest

from spray.beam_model import (
    build_beams,
    load_beam_table,
    ray_directions,
    ray_sphere_intersect,
)

# Rows measured by the PM in docs/history/plume-beam-table.md ("Đo 1"), in degrees.
DOC_ELEVATION_DEG = {1: -2.50, 14: -0.08}


def test_loaded_table_matches_the_measured_document():
    table = load_beam_table()

    assert len(table.elevation_deg) >= 18
    assert all(-6.0 <= value <= 3.0 for value in table.elevation_deg)
    for ring, documented in DOC_ELEVATION_DEG.items():
        assert table.elevation_deg[ring] == pytest.approx(documented, abs=0.3)


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
