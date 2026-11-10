"""Beam ray casting for the spray plume: detection, attenuation, occlusion.

This is step 4-5 of ``spec-v2-paper-faithful.md`` and a port of
``dee.cpp:230-281``. It is **not** wired into the generator yet: it takes a real
point cloud and a list of spray clusters and returns one echo per beam.

Three mechanisms from the reference implementation [CODE]:

- a beam that intersects a sphere spawns a detection with probability
  ``min(1, lognormal(mu, sigma)) * min(1, exp(-age/T))``;
- the segment already travelled through earlier clusters attenuates both the
  new detection and the real point behind it by ``exp(-2 * mean * L)``;
- ``add_max_detection`` keeps the strongest echo per beam, so a plume can hide
  a weak real return and vice versa.

Deliberate difference from the reference: segments on one beam are sorted by
``t0`` before the travelled length ``L`` is accumulated. The reference walks
clusters in list order (``dee.cpp:230-281``), which depends on spawn order; the
physical attenuation depends on the order the ray meets them.

Units: positions and lengths in metres, angles in degrees at the API boundary.
Only numpy and the standard library are used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from spray.beam_model import (
    BeamTable,
    build_beams,
    ray_sphere_intersect,
)
from spray.plume_state import SprayCluster

__all__ = ["RaycastConfig", "RaycastResult", "RaycastStats", "raycast_frame"]


@dataclass(frozen=True)
class RaycastConfig:
    """Knobs of the ray-casting step, with the reference defaults.

    ``mean_attenuation_per_m`` enters ``exp(-2 * mean * L)`` [CODE]
    ``dee.cpp:279``. The detection probability is the clamped lognormal of the
    published profile; the intensity is ``N(0.5, 0.05)`` clipped to ``[0, 1]``
    and scaled to 0-255 [CODE] ``normal_distrib_0_5``.
    """

    mean_attenuation_per_m: float = 0.02
    p_det_mu: float = -2.3
    p_det_sigma: float = 1.1
    intensity_mu: float = 0.5
    intensity_sigma: float = 0.05
    max_distance_m: float = 100.0
    min_intensity: float = 0.0


@dataclass
class RaycastStats:
    """Counters for one frame."""

    beams_total: int = 0
    beams_hit: int = 0
    det: int = 0
    det_dropped_stronger_real: int = 0
    real_dropped_plume_stronger: int = 0
    att_m_total: float = 0.0
    att_real_points: int = 0


@dataclass
class RaycastResult:
    """Ray-cast output of one frame.

    ``detections`` is ``(K, 5)`` as ``x, y, z, intensity, ring``; the ring
    column keeps the beam id for later pipeline stages. ``real_points`` is the
    input cloud with attenuated intensities and the occluded points removed.
    """

    detections: np.ndarray
    real_points: np.ndarray
    stats: RaycastStats


def raycast_frame(
    points: np.ndarray,
    clusters: Sequence[SprayCluster],
    *,
    table: BeamTable,
    road_z_m: float,
    rng: np.random.Generator,
    config: RaycastConfig | None = None,
) -> RaycastResult:
    """Cast the measured beam grid through ``clusters`` for one frame.

    ``points`` is ``(N, 5)`` ``x, y, z, intensity, ring``. Every real point is
    assigned to its beam by ``ring`` and the nearest measured azimuth
    (``round(azimuth / step) % N``); points with ``ring`` outside ``0..M-1``
    stay in the output but take no part in intersection or occlusion.

    Clusters are pre-filtered with an angular box around the cone they subtend,
    so the 36,500-beam grid is never tested against every cluster.
    """
    cfg = config or RaycastConfig()
    real = _as_points(points)
    cluster_list = list(clusters)

    elevation_flat, azimuth_flat = build_beams(table)
    elevation_count = len(table.elevation_deg)
    azimuth_count = int(round(360.0 / table.azimuth_step_deg))
    if elevation_flat.size != elevation_count * azimuth_count:
        raise ValueError(
            "build_beams returned "
            f"{elevation_flat.size} beams, expected "
            f"{elevation_count} x {azimuth_count}"
        )
    # build_beams is azimuth-major: row = azimuth index, column = ring.
    elevation_grid = elevation_flat.reshape(azimuth_count, elevation_count)
    azimuth_grid = azimuth_flat.reshape(azimuth_count, elevation_count)
    elevation_axis = elevation_grid[0]
    azimuth_axis = azimuth_grid[:, 0]
    elevation_rad = np.radians(elevation_flat)
    azimuth_rad = np.radians(azimuth_flat)
    cosine_elevation = np.cos(elevation_rad)
    directions = np.empty((elevation_flat.size, 3), dtype=np.float64)
    directions[:, 0] = cosine_elevation * np.cos(azimuth_rad)
    directions[:, 1] = cosine_elevation * np.sin(azimuth_rad)
    directions[:, 2] = np.sin(elevation_rad)
    sin_elevation = directions[:, 2]

    stats = RaycastStats(beams_total=elevation_count * azimuth_count)
    keys, point_valid = _point_beams(
        real,
        elevation_count=elevation_count,
        azimuth_count=azimuth_count,
        step_deg=table.azimuth_step_deg,
    )

    hits = _collect_hits(
        cluster_list,
        directions=directions,
        elevation_axis=elevation_axis,
        azimuth_axis=azimuth_axis,
        elevation_count=elevation_count,
        azimuth_count=azimuth_count,
    )
    if hits is None:
        return RaycastResult(
            detections=np.empty((0, 5), dtype=np.float64),
            real_points=real,
            stats=stats,
        )

    keys_hit, t0_hit, t1_hit, cluster_hit = hits
    order = np.lexsort((t1_hit, t0_hit, keys_hit))
    keys_hit = keys_hit[order]
    t0_hit = t0_hit[order]
    t1_hit = t1_hit[order]
    cluster_hit = cluster_hit[order]

    unique_keys, starts, counts = np.unique(
        keys_hit, return_index=True, return_counts=True
    )
    stats.beams_hit = int(unique_keys.size)

    beam_ring = keys_hit // azimuth_count
    beam_azimuth = keys_hit % azimuth_count
    beam_global = beam_azimuth * elevation_count + beam_ring
    segment_lengths = t1_hit - t0_hit

    # Travelled length entering each segment, within its own beam.
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    segment_start = np.repeat(starts, counts)
    travelled = cumulative[:-1] - cumulative[segment_start]

    # Real points grouped by beam key, for log-time lookup.
    valid_indices = np.flatnonzero(point_valid)
    valid_keys = keys[point_valid]
    point_order = np.argsort(valid_keys, kind="stable")
    sorted_keys = valid_keys[point_order]
    sorted_points = valid_indices[point_order]

    real_max_by_hit = np.full(unique_keys.size, -np.inf, dtype=np.float64)
    stats.att_m_total = 0.0
    dropped = np.zeros(len(real), dtype=bool)

    positions = np.searchsorted(unique_keys, sorted_keys)
    has_hit = (positions < unique_keys.size) & (
        unique_keys[np.minimum(positions, unique_keys.size - 1)] == sorted_keys
    )
    group_counts = np.zeros(0, dtype=np.int64)
    group_hit = np.zeros(0, dtype=np.int64)
    point_indices = np.zeros(0, dtype=np.int64)
    if has_hit.any():
        positions = positions[has_hit]
        point_indices = sorted_points[has_hit]
        point_keys = sorted_keys[has_hit]
        point_segment_start = starts[positions]
        point_segment_count = counts[positions]
        ranges = np.linalg.norm(real[point_indices, :3], axis=1)

        pair_offsets = np.concatenate(
            ([0], np.cumsum(point_segment_count))
        ).astype(np.int64)
        pair_flat = np.arange(int(pair_offsets[-1]), dtype=np.int64)
        point_of_pair = np.repeat(
            np.arange(point_indices.size), point_segment_count
        )
        local_offset = pair_flat - np.repeat(
            pair_offsets[:-1], point_segment_count
        )
        segment_of_pair = (
            np.repeat(point_segment_start, point_segment_count) + local_offset
        )
        range_of_pair = ranges[point_of_pair]
        start_of_pair = t0_hit[segment_of_pair]
        end_of_pair = np.minimum(t1_hit[segment_of_pair], range_of_pair)
        inside = np.where(
            start_of_pair < range_of_pair,
            np.maximum(end_of_pair - start_of_pair, 0.0),
            0.0,
        )
        lengths = np.add.reduceat(inside, pair_offsets[:-1])
        attenuated = lengths > 0.0
        if attenuated.any():
            real[point_indices, 3] *= np.exp(
                -2.0 * cfg.mean_attenuation_per_m * lengths
            )
            stats.att_real_points = int(attenuated.sum())
            stats.att_m_total = float(lengths[attenuated].sum())

        group_start = np.concatenate(
            ([0], np.flatnonzero(np.diff(point_keys) != 0) + 1)
        )
        group_counts = np.diff(
            np.concatenate((group_start, [point_keys.size]))
        )
        group_hit = np.searchsorted(unique_keys, point_keys[group_start])
        real_max_by_hit[group_hit] = np.maximum.reduceat(
            real[point_indices, 3], group_start
        )

    # One draw per intersected segment, bulk.
    lognormal = rng.lognormal(cfg.p_det_mu, cfg.p_det_sigma, size=keys_hit.size)
    survival_by_cluster = _survival(cluster_list)
    survival = survival_by_cluster[cluster_hit]
    probability = np.minimum(1.0, lognormal) * survival
    detected = rng.random(keys_hit.size) > 1.0 - probability

    midpoints = 0.5 * (t0_hit + t1_hit)
    sigma = segment_lengths / 6.0
    distances = rng.normal(midpoints, sigma)
    intensity = np.clip(
        rng.normal(cfg.intensity_mu, cfg.intensity_sigma, size=keys_hit.size),
        0.0,
        1.0,
    )
    intensity *= 255.0 * np.exp(
        -2.0 * cfg.mean_attenuation_per_m * travelled
    )

    valid = (
        detected
        & (distances <= cfg.max_distance_m)
        & (distances * sin_elevation[beam_global] > float(road_z_m))
        & (intensity >= cfg.min_intensity)
    )

    detection_indices = np.flatnonzero(valid)
    detections = np.empty((0, 5), dtype=np.float64)
    winning_keys = np.zeros(0, dtype=np.int64)
    if detection_indices.size:
        detection_indices, winning_keys = _keep_strongest_per_beam(
            detection_indices,
            keys_hit,
            intensity,
            unique_keys,
            real_max_by_hit,
            stats,
        )
        if detection_indices.size:
            ring = keys_hit[detection_indices] // azimuth_count
            beam = keys_hit[detection_indices] % azimuth_count * elevation_count + ring
            points_3d = distances[detection_indices, np.newaxis] * directions[beam]
            detections = np.column_stack(
                [points_3d, intensity[detection_indices], ring]
            )
            stats.att_m_total += float(travelled[detection_indices].sum())

    if winning_keys.size and point_indices.size:
        wins = np.zeros(unique_keys.size, dtype=bool)
        wins[np.searchsorted(unique_keys, winning_keys)] = True
        point_dropped = np.repeat(wins[group_hit], group_counts)
        dropped[point_indices[point_dropped]] = True
        stats.real_dropped_plume_stronger = int(point_dropped.sum())

    stats.det = int(detections.shape[0])
    return RaycastResult(
        detections=detections,
        real_points=real[~dropped],
        stats=stats,
    )


def _as_points(points: np.ndarray) -> np.ndarray:
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] < 5:
        raise ValueError(f"points must have shape (N, 5), got {array.shape}")
    return array[:, :5].copy()


def _point_beams(
    points: np.ndarray,
    *,
    elevation_count: int,
    azimuth_count: int,
    step_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Beam key ``ring * N + az_idx`` per point and the association mask."""
    count = len(points)
    keys = np.full(count, -1, dtype=np.int64)
    if count == 0:
        return keys, np.zeros(0, dtype=bool)

    finite = (
        np.isfinite(points[:, :3]).all(axis=1)
        & np.isfinite(points[:, 4])
    )
    if not finite.any():
        return keys, np.zeros(count, dtype=bool)

    safe_coords = np.where(finite[:, np.newaxis], points[:, :3], 0.0)
    safe_rings = np.where(finite, points[:, 4], 0.0)
    rings = np.trunc(safe_rings).astype(np.int64)
    azimuth = np.degrees(np.arctan2(safe_coords[:, 1], safe_coords[:, 0])) % 360.0
    azimuth_indices = (
        np.rint(azimuth / step_deg).astype(np.int64) % azimuth_count
    )
    valid = finite & (rings >= 0) & (rings < elevation_count)
    keys[valid] = rings[valid] * azimuth_count + azimuth_indices[valid]
    return keys, valid


def _collect_hits(
    clusters: Sequence[SprayCluster],
    *,
    directions: np.ndarray,
    elevation_axis: np.ndarray,
    azimuth_axis: np.ndarray,
    elevation_count: int,
    azimuth_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
    """Intersect the angular box of every cluster with the beam grid.

    Only beams whose measured elevation lies within the cone half-angle, and
    whose azimuth lies within ``alpha / cos(e_c)`` (wrapped at 0/360), are
    passed to :func:`ray_sphere_intersect`.
    """
    key_chunks: list[np.ndarray] = []
    t0_chunks: list[np.ndarray] = []
    t1_chunks: list[np.ndarray] = []
    cluster_chunks: list[np.ndarray] = []

    for cluster_index, cluster in enumerate(clusters):
        center = np.asarray(cluster.pos, dtype=np.float64).ravel()
        radius = float(cluster.radius)
        if center.shape != (3,):
            raise ValueError(f"cluster pos must have shape (3,), got {center.shape}")
        distance = float(np.linalg.norm(center))
        if radius <= 0.0 or distance <= 0.0:
            continue

        half_angle = np.degrees(np.arcsin(min(1.0, radius / distance)))
        center_elevation = np.degrees(
            np.arctan2(center[2], float(np.hypot(center[0], center[1])))
        )
        center_azimuth = np.degrees(np.arctan2(center[1], center[0])) % 360.0

        rings = np.flatnonzero(
            (elevation_axis >= center_elevation - half_angle)
            & (elevation_axis <= center_elevation + half_angle)
        )
        if rings.size == 0:
            continue

        cosine = abs(np.cos(np.radians(center_elevation)))
        azimuth_half = (
            180.0 if cosine < 1e-12 else min(180.0, half_angle / cosine)
        )
        if azimuth_half >= 180.0:
            azimuth_indices = np.arange(azimuth_count)
        else:
            difference = (
                azimuth_axis - center_azimuth + 180.0
            ) % 360.0 - 180.0
            azimuth_indices = np.flatnonzero(
                np.abs(difference) <= azimuth_half
            )
        if azimuth_indices.size == 0:
            continue

        azimuth_mesh, ring_mesh = np.broadcast_arrays(
            azimuth_indices[:, np.newaxis], rings[np.newaxis, :]
        )
        azimuth_mesh = azimuth_mesh.ravel()
        ring_mesh = ring_mesh.ravel()
        beam_global = azimuth_mesh * elevation_count + ring_mesh
        t0, t1 = ray_sphere_intersect(directions[beam_global], center, radius)
        hit = np.isfinite(t0)
        if not hit.any():
            continue

        key_chunks.append(ring_mesh[hit] * azimuth_count + azimuth_mesh[hit])
        t0_chunks.append(t0[hit])
        t1_chunks.append(t1[hit])
        cluster_chunks.append(np.full(int(hit.sum()), cluster_index))

    if not key_chunks:
        return None
    return (
        np.concatenate(key_chunks),
        np.concatenate(t0_chunks),
        np.concatenate(t1_chunks),
        np.concatenate(cluster_chunks),
    )


def _survival(clusters: Sequence[SprayCluster]) -> np.ndarray:
    """``min(1, exp(-age/T))`` per cluster, zero when ``T <= 0``."""
    survival = np.zeros(len(clusters), dtype=np.float64)
    for index, cluster in enumerate(clusters):
        if cluster.ttl > 0.0:
            survival[index] = min(1.0, float(np.exp(-cluster.age / cluster.ttl)))
    return survival


def _keep_strongest_per_beam(
    indices: np.ndarray,
    keys_hit: np.ndarray,
    intensity: np.ndarray,
    unique_keys: np.ndarray,
    real_max_by_hit: np.ndarray,
    stats: RaycastStats,
) -> tuple[np.ndarray, np.ndarray]:
    """Keep the strongest surviving detection of each beam, or none.

    A detection is dropped when the strongest real return on the same beam has
    at least its intensity (ties keep the real point). Winning detections hide
    every real point on that beam, which the caller marks afterwards.
    """
    keys = keys_hit[indices]
    group_keys, starts, counts = np.unique(
        keys, return_index=True, return_counts=True
    )
    group_hit = np.searchsorted(unique_keys, group_keys)
    values = intensity[indices]
    group_max = np.maximum.reduceat(values, starts)
    wins = group_max > real_max_by_hit[group_hit]
    stats.det_dropped_stronger_real = int(counts[~wins].sum())

    group_of = np.repeat(np.arange(group_keys.size), counts)
    candidate = np.flatnonzero(
        wins[group_of] & (values == np.repeat(group_max, counts))
    )
    if candidate.size == 0:
        return np.zeros(0, dtype=np.int64), group_keys[wins]
    # ``np.unique`` returns the first index of each group; ties keep the first
    # (lowest) detection, which is deterministic because hits are sorted by t0.
    _, first = np.unique(group_of[candidate], return_index=True)
    return indices[candidate[first]], group_keys[wins]
