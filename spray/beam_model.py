"""LiDAR beam geometry for the spray ray-casting step.

The elevation angle of a ring comes from ``docs/plume-beam-table.md``, measured
on SemanticSpray itself. The manufacturer's VLP-32C table must **not** be used:
the release was clipped vertically and its ring ids were renumbered ``0..N-1``,
so matching ids against the manual is off by 3.49 deg median. Ring id is used
as the beam index; the angle is always read from the measured table.

Units are degrees at the API boundary and metres inside the intersection
helpers. Azimuth follows the LiDAR frame: ``atan2(y, x)``, so 0 deg is ``+x``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

__all__ = [
    "BeamTable",
    "BeamTableError",
    "build_beams",
    "load_beam_table",
    "ray_directions",
    "ray_sphere_intersect",
]

DEFAULT_TABLE_PATH = (
    Path(__file__).resolve().parent / "config" / "beam_elevation.yaml"
)

_REQUIRED_KEYS = ("elevation_deg", "azimuth_step_deg")


class BeamTableError(ValueError):
    """The beam table file is missing a key or holds an invalid value."""


@dataclass(frozen=True)
class BeamTable:
    """Measured beam angles: one elevation per ring plus the azimuth step.

    ``elevation_deg[i]`` belongs to ring ``i``. The tuple is the beam index to
    angle map; nothing here assumes the manufacturer's laser ordering.
    """

    elevation_deg: tuple[float, ...]
    azimuth_step_deg: float


def load_beam_table(path: str | Path = DEFAULT_TABLE_PATH) -> BeamTable:
    """Load a measured beam table from YAML.

    Raises :class:`BeamTableError` with the missing key names when the file is
    incomplete, and when the angles or step are not finite/positive.
    """
    table_path = Path(path)
    try:
        with open(table_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except OSError as exc:
        raise BeamTableError(f"cannot read beam table {table_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise BeamTableError(f"beam table {table_path} must be a mapping")

    missing = [key for key in _REQUIRED_KEYS if key not in data]
    if missing:
        raise BeamTableError(
            f"beam table {table_path} is missing keys: {', '.join(missing)}"
        )

    try:
        elevation = np.asarray(data["elevation_deg"], dtype=np.float64).ravel()
    except (TypeError, ValueError) as exc:
        raise BeamTableError(
            f"elevation_deg in {table_path} must be a list of numbers"
        ) from exc
    if elevation.size == 0:
        raise BeamTableError(f"elevation_deg in {table_path} is empty")
    if not np.isfinite(elevation).all():
        raise BeamTableError(f"elevation_deg in {table_path} must be finite")

    try:
        step = float(data["azimuth_step_deg"])
    except (TypeError, ValueError) as exc:
        raise BeamTableError(
            f"azimuth_step_deg in {table_path} must be a number"
        ) from exc
    if not np.isfinite(step) or step <= 0.0:
        raise BeamTableError(
            f"azimuth_step_deg in {table_path} must be finite and > 0, got {step}"
        )

    return BeamTable(
        elevation_deg=tuple(float(value) for value in elevation),
        azimuth_step_deg=step,
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
