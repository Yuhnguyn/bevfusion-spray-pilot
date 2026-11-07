import numpy as np
import pytest

from spray.denoise import (
    ARM_B0_DROR_CONFIG,
    ARM_B0_FILTER,
    DrorConfig,
    RorConfig,
    dror_filter,
    ror_filter,
)


def _dense_ball(center, count, radius, rng):
    direction = rng.normal(size=(count, 3))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    distance = radius * rng.random(count) ** (1.0 / 3.0)
    return center + direction * distance[:, None]


def _with_meta(xyz):
    xyz = np.asarray(xyz, dtype=np.float32)
    meta = np.zeros((len(xyz), 2), dtype=np.float32)
    return np.hstack([xyz, meta])


def test_ror_removes_isolated_points():
    rng = np.random.default_rng(0)
    cluster = _dense_ball(np.zeros(3), 30, 0.2, rng)
    stray = np.array([[5.0, 0.0, 0.0]])
    points = _with_meta(np.vstack([cluster, stray]))

    keep, stats = ror_filter(points)

    assert keep.shape == (31,)
    assert keep.dtype == np.bool_
    assert keep[:30].all()
    assert not keep[30]
    assert stats["n_in"] == 31
    assert stats["n_out"] == 30
    assert stats["frac_removed"] == pytest.approx(1.0 / 31.0)


def test_ror_keeps_dense_structures():
    rng = np.random.default_rng(1)
    left = _dense_ball(np.zeros(3), 30, 0.2, rng)
    right = _dense_ball(np.array([3.0, 0.0, 0.0]), 30, 0.2, rng)
    points = _with_meta(np.vstack([left, right]))

    keep, stats = ror_filter(points)

    assert keep.all()
    assert stats["n_out"] == 60
    assert stats["frac_removed"] == 0.0


def test_ror_edge_cases_preserve_shape_and_order():
    empty_keep, empty_stats = ror_filter(np.zeros((0, 5), dtype=np.float32))
    assert empty_keep.shape == (0,)
    assert empty_keep.dtype == np.bool_
    assert empty_stats["n_in"] == 0
    assert empty_stats["n_out"] == 0
    assert empty_stats["frac_removed"] == 0.0

    single_keep, single_stats = ror_filter(
        np.array([[1.0, 2.0, 3.0, 4.0, 5.0]], dtype=np.float32)
    )
    assert single_keep.tolist() == [False]
    assert single_stats["frac_removed"] == 1.0

    block = np.array(
        [
            [0.0, 0.0, 0.0, 10.0, 20.0],
            [0.1, 0.0, 0.0, 11.0, 21.0],
            [0.2, 0.0, 0.0, 12.0, 22.0],
            [0.0, 0.1, 0.0, 13.0, 23.0],
            [0.1, 0.1, 0.0, 14.0, 24.0],
            [0.2, 0.0, 0.0, 15.0, 25.0],
            [0.0, 0.0, 0.1, 16.0, 26.0],
            [0.2, 0.1, 0.1, 17.0, 27.0],
            [0.1, 0.0, 0.1, 18.0, 28.0],
            [9.0, 9.0, 9.0, 99.0, 99.0],
        ],
        dtype=np.float32,
    )
    before = block.copy()

    keep, stats = ror_filter(block, config=RorConfig(k=3, r=0.5))

    assert keep.shape == (10,)
    assert keep.dtype == np.bool_
    assert keep[:9].all()
    assert not keep[9]
    assert np.array_equal(block, before)
    assert stats["k"] == 3
    assert stats["r"] == pytest.approx(0.5)
    assert RorConfig().k == 8
    assert RorConfig().r == pytest.approx(0.5)


def _hdl32_plane(distance, half_width_deg=12.0):
    vertical = np.deg2rad(-30.67 + 1.33 * np.arange(32))
    half = int(round(half_width_deg / 0.17))
    horizontal = np.deg2rad(0.17 * np.arange(-half, half + 1))
    theta, phi = np.meshgrid(horizontal, vertical)
    x = np.full(theta.shape, float(distance))
    y = distance * np.tan(theta)
    z = distance * np.tan(phi)
    return np.column_stack([x.ravel(), y.ravel(), z.ravel()])


def test_dror_keeps_flat_surface_at_50m():
    points = _with_meta(_hdl32_plane(50.0))

    keep, stats = dror_filter(points)

    assert keep.mean() >= 0.95
    assert stats["alpha"] == pytest.approx(0.03)
    assert stats["k"] == 8


def test_dror_removes_isolated_points():
    rng = np.random.default_rng(0)
    cluster = _dense_ball(np.array([10.0, 0.0, 0.0]), 30, 0.2, rng)
    stray = np.array([[15.0, 0.0, 0.0]])
    points = _with_meta(np.vstack([cluster, stray]))

    keep, stats = dror_filter(points)

    assert keep.shape == (31,)
    assert keep.dtype == np.bool_
    assert keep[:30].all()
    assert not keep[30]
    assert stats["n_out"] == 30
    assert stats["frac_removed"] == pytest.approx(1.0 / 31.0)


def test_dror_keeps_dense_cluster_at_25m():
    rng = np.random.default_rng(2)
    cluster = _dense_ball(np.array([25.0, 0.0, 0.0]), 14, 0.3, rng)

    keep, stats = dror_filter(_with_meta(cluster))

    assert keep.all()
    assert stats["n_in"] == 14
    assert stats["n_out"] == 14
    assert stats["frac_removed"] == 0.0
    assert ARM_B0_FILTER == "dror"
    assert ARM_B0_DROR_CONFIG == DrorConfig()

