"""LiDAR beam geometry for the spray ray-casting step.

The measured ``ring -> elevation`` table was rejected: ring ids on this release
are not beam ids, and the table was produced by a filter that dropped the
upward rings which see the plume (``docs/history/plume-beam-table.md``
§ĐÍNH CHÍNH). Casting therefore uses a **uniform grid**: ``0.333°`` in
elevation over the measured FOV and ``0.197307°`` in azimuth, as decided in
ticket 29c. The old measured ring table file is deleted and nothing may read
it.

Units are degrees at the API boundary and metres inside the intersection
helpers. Azimuth follows the LiDAR frame: ``atan2(y, x)``, so 0 deg is ``+x``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "AZIMUTH_STEP_DEG",
    "ELEVATION_MAX_DEG",
    "ELEVATION_MIN_DEG",
    "ELEVATION_STEP_DEG",
    "BeamTable",
    "BeamTableError",
    "build_beams",
    "load_beam_table",
    "ray_directions",
    "ray_sphere_intersect",
]

# [PAPER] VLP-32C elevation discretisation in the central FOV (0.333°); the
# release is clipped to the measured FOV -4.06…+5.88°.
ELEVATION_MIN_DEG = -4.06
ELEVATION_MAX_DEG = 5.88
ELEVATION_STEP_DEG = 0.333
# [ĐO] measured azimuth step of the local release; 360 / step = 1,825 columns.
AZIMUTH_STEP_DEG = 0.197307


class BeamTableError(ValueError):
    """A beam-grid parameter is invalid."""


@dataclass(frozen=True)
class BeamTable:
    """Uniform beam angles: one elevation per ring plus the azimuth step."""

    elevation_deg: tuple[float, ...]
    azimuth_step_deg: float


def load_beam_table() -> BeamTable:
    """Return the uniform grid over the measured FOV.

    Elevation runs from ``ELEVATION_MIN_DEG`` in steps of
    ``ELEVATION_STEP_DEG`` while staying inside ``ELEVATION_MAX_DEG`` — 30
    rings here. There is no YAML file any more (ticket 29c mục 6).
    """
    elevation = np.arange(
        ELEVATION_MIN_DEG,
        ELEVATION_MAX_DEG,
        ELEVATION_STEP_DEG,
        dtype=np.float64,
    )
    if elevation.size == 0 or not np.isfinite(elevation).all():
        raise BeamTableError("uniform elevation grid is empty or non-finite")
    return BeamTable(
        elevation_deg=tuple(float(value) for value in elevation),
        azimuth_step_deg=AZIMUTH_STEP_DEG,
    )


def build_beams(
    table: BeamTable,
    azimuth_range_deg: tuple[float, float] = (0.0, 360.0),
) -> tuple[np.ndarray, np.ndarray]:
    """Build the discrete beam grid, flattened to one pair of 1-D arrays.

    The full scan has ``M = len(elevation_deg)`` elevations and
    ``N = round(360 / azimuth_step_deg)`` equally spaced azimuths, ordered
    azimuth-major, so ``elev_out[k]`` and ``az_out[k]`` describe the same beam.
    ``azimuth_range_deg`` keeps only the grid columns inside ``[start, stop)``,
    for partial-scan callers; the default returns the whole circle.
    """
    elevation = np.asarray(table.elevation_deg, dtype=np.float64)
    step = float(table.azimuth_step_deg)
    n_azimuth = int(round(360.0 / step))

    start, stop = (float(value) for value in azimuth_range_deg)
    if not 0.0 <= start < stop <= 360.0:
        raise BeamTableError(
            f"azimuth_range_deg must satisfy 0 <= start < stop <= 360, "
            f"got ({start}, {stop})"
        )

    azimuth = np.arange(n_azimuth, dtype=np.float64) * step
    if start != 0.0 or stop != 360.0:
        azimuth = azimuth[(azimuth >= start) & (azimuth < stop)]

    elevation_grid, azimuth_grid = np.meshgrid(elevation, azimuth)
    return elevation_grid.ravel(), azimuth_grid.ravel()


def ray_directions(elev_deg, az_deg) -> np.ndarray:
    """Unit ray direction per beam, ``[cos e cos a, cos e sin a, sin e]``.

    Returns a float64 array of shape ``(K, 3)`` for 1-D inputs, which is what
    ``build_beams`` produces. Both arguments are in degrees.
    """
    elevation = np.radians(np.asarray(elev_deg, dtype=np.float64))
    azimuth = np.radians(np.asarray(az_deg, dtype=np.float64))
    elevation, azimuth = np.broadcast_arrays(elevation, azimuth)
    return np.stack(
        [
            np.cos(elevation) * np.cos(azimuth),
            np.cos(elevation) * np.sin(azimuth),
            np.sin(elevation),
        ],
        axis=-1,
    )


def ray_sphere_intersect(
    dirs: np.ndarray, center: np.ndarray, radius: float
) -> tuple[np.ndarray, np.ndarray]:
    """Intersect rays from the origin with one sphere, vectorised.

    With ``a = d·d``, ``b = -2 c·d`` and ``c0 = c·c - r²``, the roots are
    ``t = (-b ∓ sqrt(b² - 4 a c0)) / (2a)``. ``t0`` and ``t1`` are ``nan`` when
    the discriminant is negative or when the near root is not in front of the
    origin (``t0 <= 0``); a ray that only exits the sphere is not counted.
    """
    directions = np.asarray(dirs, dtype=np.float64)
    if directions.ndim != 2 or directions.shape[1] != 3:
        raise ValueError(
            f"dirs must have shape (K, 3), got {directions.shape}"
        )
    sphere_center = np.asarray(center, dtype=np.float64).ravel()
    if sphere_center.shape != (3,):
        raise ValueError(
            f"center must have shape (3,), got {sphere_center.shape}"
        )
    r = float(radius)

    a = np.einsum("ij,ij->i", directions, directions)
    b = -2.0 * (directions @ sphere_center)
    c = float(sphere_center @ sphere_center) - r * r
    discriminant = b * b - 4.0 * a * c

    hit = (discriminant >= 0.0) & (a > 0.0)
    root = np.sqrt(np.where(hit, discriminant, 0.0))
    denominator = np.where(hit, 2.0 * a, 1.0)
    t0 = np.where(hit, (-b - root) / denominator, np.nan)
    t1 = np.where(hit, (-b + root) / denominator, np.nan)

    in_front = hit & (t0 > 0.0)
    return (
        np.where(in_front, t0, np.nan),
        np.where(in_front, t1, np.nan),
    )
