"""Per-frame statistics for SemanticSpray label-2 noise points (ticket 29d).

Gate recipe (paper, ``[CHỌN 2026-11-11]``): **DBSCAN in the discretized
(azimuth, elevation) plane** -- ``minPts = 3``, ``eps = 0.7°``, elevation
snapped to a ``0.333°`` grid (VLP-32C), azimuth wrapped modulo 360, Euclidean
distance inside the angular plane. The paper does not state whether the
neighborhood is a box or a disc in that plane, so a disc is chosen ``[CHỌN]``.

The legacy recipe (``single-linkage`` on ``(x, y)`` at 0.5 m, then keep
clusters with at least 3 points) is still available for the secondary table
that compares against ticket 16's ``17,06`` clusters/frame. The gate reads
only G1..G7 of the paper recipe; ``metrics()`` exposes the legacy cluster
counts under ``legacy_*`` keys.

Units: ``abs_y`` and ``height_above_road`` in metres, ``elevation_deg`` in
degrees, ``intensity`` in the dataset's raw unit, ``ring`` in the LiDAR ring
index. ``ring`` is read from column 4; elevation is computed from geometry, not
from ``ring``.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from spray.spray_stats import NOISE_LABEL, single_linkage

MIN_PTS = 3
RADIUS_M = 0.5
ANGULAR_EPS_DEG = 0.7
ELEVATION_STEP_DEG = 0.333


def fit_ground_plane(points: np.ndarray) -> tuple[float, float, float]:
    """Robust ground plane ``z = a*x + b*y + c`` fitted inside 3-40 m.

    Copied verbatim from ``scripts/measure_spray_height.py:_plane`` (3 IRLS
    rounds, ``|z| < 0.4`` window, fallback ``(0.0, 0.0, -0.411)``) so the
    numbers match the committed height measurements. The original file must not
    be modified, and ``scripts/`` is not an importable package, hence the copy.
    """

    mask = (
        (points[:, 0] > 3.0)
        & (points[:, 0] < 40.0)
        & (np.abs(points[:, 2]) < 0.4)
    )
    subset = points[mask]
    if subset.shape[0] < 50:
        return 0.0, 0.0, -0.411
    design = np.column_stack(
        [subset[:, 0], subset[:, 1], np.ones(subset.shape[0])]
    )
    coef, *_ = np.linalg.lstsq(design, subset[:, 2], rcond=None)
    for _ in range(3):
        residual = subset[:, 2] - design @ coef
        keep = np.abs(residual) < 0.05
        if keep.sum() < 50:
            break
        coef, *_ = np.linalg.lstsq(design[keep], subset[keep, 2], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def _angular_coordinates(
    points: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    x = points[:, 0].astype(np.float64)
    y = points[:, 1].astype(np.float64)
    z = points[:, 2].astype(np.float64)
    azimuth = np.degrees(np.arctan2(y, x))
    elevation = np.degrees(np.arctan2(z, np.hypot(x, y)))
    elevation = np.round(elevation / ELEVATION_STEP_DEG) * ELEVATION_STEP_DEG
    return azimuth, elevation


def cluster_angular(
    points: np.ndarray,
    *,
    eps_deg: float = ANGULAR_EPS_DEG,
    min_pts: int = MIN_PTS,
) -> np.ndarray:
    """DBSCAN on noise points in the ``(azimuth, elevation)`` plane.

    ``points`` must already contain only noise points; columns ``x, y, z`` are
    used. Azimuth comes from ``atan2(y, x)`` and is wrapped modulo 360;
    elevation comes from ``atan2(z, hypot(x, y))`` and is snapped to the
    ``0.333°`` grid. Two points are neighbors when their Euclidean distance in
    that plane is ``<= eps_deg``. Returns integer cluster labels with ``-1``
    for points in no cluster (DBSCAN core/border semantics).
    """

    pts = np.asarray(points, dtype=np.float64)
    count = pts.shape[0]
    labels = np.full(count, -1, dtype=np.int64)
    if count == 0:
        return labels

    azimuth, elevation = _angular_coordinates(pts)
    neighbors: list[np.ndarray] = []
    core = np.zeros(count, dtype=bool)
    for index in range(count):
        delta_az = (azimuth - azimuth[index] + 180.0) % 360.0 - 180.0
        delta_el = elevation - elevation[index]
        members = np.nonzero(
            np.hypot(delta_az, delta_el) <= eps_deg
        )[0]
        neighbors.append(members)
        core[index] = members.size >= min_pts

    cluster_id = 0
    for index in range(count):
        if labels[index] != -1 or not core[index]:
            continue
        labels[index] = cluster_id
        queue = deque(int(member) for member in neighbors[index])
        while queue:
            member = queue.popleft()
            if labels[member] != -1:
                continue
            labels[member] = cluster_id
            if core[member]:
                queue.extend(int(other) for other in neighbors[member])
        cluster_id += 1

    return labels


def _cluster_geometry(
    noise: np.ndarray,
    cluster_labels: np.ndarray,
    min_pts: int,
) -> tuple[np.ndarray, np.ndarray]:
    point_ranges = np.linalg.norm(noise[:, :3], axis=1)
    sizes: list[int] = []
    range_over_extent: list[float] = []
    for cluster_id in np.unique(cluster_labels):
        if cluster_id < 0:
            continue
        member_mask = cluster_labels == cluster_id
        size = int(member_mask.sum())
        if size < min_pts:
            continue
        sizes.append(size)
        members = noise[member_mask][:, :3].astype(np.float64)
        centroid = members.mean(axis=0)
        r_extent = float(
            np.max(np.linalg.norm(members - centroid, axis=1))
        )
        if r_extent == 0.0:
            continue
        member_ranges = point_ranges[member_mask]
        r_range = float(member_ranges.max() - member_ranges.min())
        range_over_extent.append(r_range / r_extent)
    return (
        np.asarray(sizes, dtype=np.int64),
        np.asarray(range_over_extent, dtype=np.float64),
    )


def _empty() -> np.ndarray:
    return np.zeros(0, dtype=np.float64)


def _empty_cluster_fields() -> dict:
    return {
        "cluster_sizes": np.zeros(0, dtype=np.int64),
        "range_over_extent": _empty(),
    }


def _empty_point_fields() -> dict:
    return {
        "n_noise": 0,
        "abs_y": _empty(),
        "height_above_road": _empty(),
        "elevation_deg": _empty(),
        "intensity": _empty(),
        "ring": _empty(),
    }


def _point_fields(points: np.ndarray, noise: np.ndarray) -> dict:
    if noise.shape[0] == 0:
        return _empty_point_fields()
    a, b, c = fit_ground_plane(points)
    x = noise[:, 0].astype(np.float64)
    y = noise[:, 1].astype(np.float64)
    z = noise[:, 2].astype(np.float64)
    height = z - (a * x + b * y + c)
    return {
        "n_noise": int(noise.shape[0]),
        "abs_y": np.abs(y),
        "height_above_road": height,
        "elevation_deg": np.degrees(np.arctan2(z, np.hypot(x, y))),
        "intensity": noise[:, 3].astype(np.float64),
        "ring": noise[:, 4].astype(np.float64),
    }


def _cluster_fields(
    noise: np.ndarray,
    cluster_labels: np.ndarray,
    min_pts: int,
) -> dict:
    sizes, ratios = _cluster_geometry(noise, cluster_labels, min_pts)
    return {
        "cluster_sizes": sizes,
        "range_over_extent": ratios,
    }


def frame_stats(
    points: np.ndarray,
    labels: np.ndarray,
    *,
    recipe: str = "paper",
    min_pts: int = MIN_PTS,
    radius_m: float = RADIUS_M,
) -> dict:
    """Statistics of one frame's label-2 noise points.

    ``recipe="paper"`` clusters with :func:`cluster_angular` (the gate recipe);
    ``recipe="legacy"`` keeps single-linkage on ``(x, y)`` at ``radius_m`` plus
    the ``min_pts`` size filter (secondary table only).

    Keys: ``n_noise`` (count), ``cluster_sizes`` (points per kept cluster),
    ``range_over_extent`` (``r_range / r_extent`` per kept cluster, zero-extent
    clusters dropped), ``abs_y`` (m), ``height_above_road`` (m, plane from
    :func:`fit_ground_plane`), ``elevation_deg`` (degrees,
    ``atan2(z, hypot(x, y))``), ``intensity`` (column 3) and ``ring``
    (column 4).
    """

    if recipe not in ("paper", "legacy"):
        raise ValueError(f"unknown recipe: {recipe!r}")

    noise = points[labels == NOISE_LABEL]
    frame = {**_point_fields(points, noise), **_empty_cluster_fields()}
    if frame["n_noise"] == 0:
        return frame

    if recipe == "paper":
        cluster_labels = cluster_angular(noise, min_pts=min_pts)
    else:
        cluster_labels = single_linkage(noise[:, :2], radius_m)
    frame.update(_cluster_fields(noise, cluster_labels, min_pts))
    return frame


def frame_stats_pair(
    points: np.ndarray,
    labels: np.ndarray,
    *,
    min_pts: int = MIN_PTS,
    radius_m: float = RADIUS_M,
) -> dict[str, dict]:
    """Return ``{"paper": ..., "legacy": ...}`` sharing one plane fit.

    Same values as two :func:`frame_stats` calls; the ground plane is fitted
    once per frame because it depends only on the point cloud, not the cluster
    recipe.
    """

    noise = points[labels == NOISE_LABEL]
    base = _point_fields(points, noise)
    if base["n_noise"] == 0:
        empty = _empty_cluster_fields()
        return {
            "paper": {**base, **empty},
            "legacy": {**base, **empty},
        }

    paper = {
        **base,
        **_cluster_fields(
            noise, cluster_angular(noise, min_pts=min_pts), min_pts
        ),
    }
    legacy = {
        **base,
        **_cluster_fields(
            noise, single_linkage(noise[:, :2], radius_m), min_pts
        ),
    }
    return {"paper": paper, "legacy": legacy}


def _concat(chunks: list[np.ndarray]) -> np.ndarray:
    if not chunks:
        return _empty()
    return np.concatenate(chunks)


class StatsAccumulator:
    """Pool many :func:`frame_stats` results into flat arrays."""

    _SCALAR_KEYS = (
        "cluster_sizes",
        "range_over_extent",
        "abs_y",
        "height_above_road",
        "elevation_deg",
        "intensity",
        "ring",
    )

    def __init__(self) -> None:
        self.frames = 0
        self._noise_per_frame: list[int] = []
        self._clusters_per_frame: list[int] = []
        self._chunks: dict[str, list[np.ndarray]] = {
            key: [] for key in self._SCALAR_KEYS
        }

    def add(self, frame: dict) -> None:
        self.frames += 1
        self._noise_per_frame.append(int(frame["n_noise"]))
        cluster_sizes = np.asarray(frame["cluster_sizes"])
        self._clusters_per_frame.append(int(cluster_sizes.shape[0]))
        for key in self._SCALAR_KEYS:
            self._chunks[key].append(
                np.asarray(frame[key], dtype=np.float64).ravel()
            )

    def summary(self) -> dict:
        return {
            "frames": self.frames,
            "noise_per_frame": np.asarray(
                self._noise_per_frame, dtype=np.float64
            ),
            "clusters_per_frame": np.asarray(
                self._clusters_per_frame, dtype=np.float64
            ),
            **{
                key: _concat(chunks)
                for key, chunks in self._chunks.items()
            },
        }


def _percentile(values: np.ndarray, q: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.percentile(array, q)) if array.size else float("nan")


def _mean(values: np.ndarray) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(array.mean()) if array.size else float("nan")


def metrics(
    summary: dict,
    legacy_summary: dict | None = None,
) -> dict[str, float]:
    """Map a pooled summary onto G1..G7 plus bookkeeping and ``legacy_*``.

    G1..G7 come from the paper recipe, which is what the gate reads.
    ``frames`` and ``n_clusters`` let
    :func:`spray.semantic_split.evaluate_criteria` enforce the minimum-data
    gate. ``legacy_G2``/``legacy_G3``/``legacy_G4`` describe the Euclidean
    0.5 m recipe and are reported only for comparison with ticket 16.
    """

    noise = np.asarray(summary["noise_per_frame"], dtype=np.float64)
    clusters = np.asarray(summary["clusters_per_frame"], dtype=np.float64)
    sizes = np.asarray(summary["cluster_sizes"], dtype=np.float64)
    ratios = np.asarray(summary["range_over_extent"], dtype=np.float64)
    abs_y = np.asarray(summary["abs_y"], dtype=np.float64)
    heights = np.asarray(summary["height_above_road"], dtype=np.float64)
    elevation = np.asarray(summary["elevation_deg"], dtype=np.float64)

    p5, p50, p95 = (
        np.percentile(heights, [5, 50, 95]) if heights.size
        else (float("nan"), float("nan"), float("nan"))
    )

    if legacy_summary is None:
        legacy_G2 = legacy_G3 = legacy_G4 = float("nan")
        legacy_frames = 0
        legacy_n_clusters = 0
    else:
        legacy_clusters = np.asarray(
            legacy_summary["clusters_per_frame"], dtype=np.float64
        )
        legacy_sizes = np.asarray(
            legacy_summary["cluster_sizes"], dtype=np.float64
        )
        legacy_ratios = np.asarray(
            legacy_summary["range_over_extent"], dtype=np.float64
        )
        legacy_G2 = _mean(legacy_clusters)
        legacy_G3 = _percentile(legacy_sizes, 50)
        legacy_G4 = _percentile(legacy_ratios, 50)
        legacy_frames = int(legacy_summary["frames"])
        legacy_n_clusters = int(legacy_sizes.shape[0])

    return {
        "G1": _percentile(noise, 50),
        "G2": _mean(clusters),
        "G3": _percentile(sizes, 50),
        "G4": _percentile(ratios, 50),
        "G5": _percentile(abs_y, 95),
        "G6_p5": float(p5),
        "G6_med": float(p50),
        "G6_p95": float(p95),
        "G7": _percentile(elevation, 50),
        "frames": int(summary["frames"]),
        "n_clusters": int(sizes.shape[0]),
        "legacy_G2": legacy_G2,
        "legacy_G3": legacy_G3,
        "legacy_G4": legacy_G4,
        "legacy_frames": legacy_frames,
        "legacy_n_clusters": legacy_n_clusters,
    }
