"""Hình học tia LiDAR cho bước ray-casting của plume.

Ray-cast dùng **lưới tia đều**: ``0,333°`` theo elevation trên FOV đo được, và
``0,197307°`` theo azimuth. Bảng ``ring → elevation`` **đo từ release thì không
dùng**: ``ring`` trên release này không phải beam id, và bảng đo được còn bị
một filter cắt mất các ring hướng lên — đúng những ring nhìn thấy plume. Không
file nào được đọc bảng cũ đó (``tests/test_beam_model.py`` assert).

Đơn vị: độ ở biên API, mét bên trong các hàm giao cắt. Azimuth theo khung LiDAR:
``atan2(y, x)``, nên 0° là ``+x``.
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
    "beams_intersecting_sphere",
    "build_beams",
    "load_beam_table",
    "omega_tia_sr",
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
    """Lưới đều trên FOV đo được — 30 ring.

    Elevation chạy từ ``ELEVATION_MIN_DEG`` theo bước ``ELEVATION_STEP_DEG``
    trong khi vẫn nằm trong ``ELEVATION_MAX_DEG``. Không còn file YAML nào.
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


def omega_tia_sr(table: BeamTable) -> float:
    """Solid angle of one beam cell: ``Δaz · Δel`` in steradians."""
    azimuth_step = np.radians(table.azimuth_step_deg)
    elevation_step = np.radians(ELEVATION_STEP_DEG)
    return float(azimuth_step * elevation_step)


def beams_intersecting_sphere(
    radius_m: float, distance_m: float, omega_sr: float
) -> float:
    """Number of uniform beams intersecting a sphere, ``n_max`` of eq. (7).

    The sphere subtends ``2π(1 - sqrt(1 - (r/d)^2))`` sr as seen from the
    sensor, so the expected beam count is that solid angle divided by the
    per-beam cell ``omega_sr``. When the sensor lies inside the sphere every
    direction hits it: ``4π / omega_sr``.
    """
    if omega_sr <= 0.0:
        raise ValueError(f"omega_sr must be positive, got {omega_sr}")
    if distance_m <= 0.0:
        raise ValueError(f"distance_m must be positive, got {distance_m}")
    radius = float(radius_m)
    if radius <= 0.0:
        return 0.0
    ratio = radius / float(distance_m)
    if ratio >= 1.0:
        solid_angle = 4.0 * np.pi
    else:
        solid_angle = 2.0 * np.pi * (1.0 - np.sqrt(1.0 - ratio * ratio))
    return float(solid_angle / omega_sr)


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
