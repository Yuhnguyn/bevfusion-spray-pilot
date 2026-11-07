from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class RorConfig:
    k: int = 8
    r: float = 0.5


def ror_filter(
    points: np.ndarray,
    k: int = 8,
    r: float = 0.5,
    config: RorConfig | None = None,
) -> tuple[np.ndarray, dict]:
    """Radius outlier removal for arm B0.

    ``points`` is ``(N, 4)`` or ``(N, 5)`` float32; only ``x, y, z`` are used
    and the remaining columns never affect the mask. A point is removed when
    it has fewer than ``k`` neighbours (excluding itself) within ``r`` metres.
    The returned mask is ``bool (N,)``, keeps the input order, and the input
    array is not modified.

    Edge cases: ``N == 0`` returns an empty mask and zero counts. Because a
    point can see at most ``N - 1`` other points, ``N <= k`` removes every
    point.

    ``config`` overrides ``k`` and ``r`` when given.
    """
    if config is not None:
        k, r = config.k, config.r

    start = time.perf_counter()
    xyz = np.asarray(points, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] < 3:
        raise ValueError(f"points must be (N, >=3), got {xyz.shape}")

    n_in = int(xyz.shape[0])
    if n_in == 0:
        keep_mask = np.zeros(0, dtype=bool)
    else:
        tree = cKDTree(xyz[:, :3])
        neighbours = tree.query_ball_point(
            xyz[:, :3], r, return_length=True
        )
        keep_mask = (neighbours - 1) >= k

    n_out = int(keep_mask.sum())
    stats = {
        "n_in": n_in,
        "n_out": n_out,
        "frac_removed": 0.0 if n_in == 0 else 1.0 - n_out / n_in,
        "time_ms": (time.perf_counter() - start) * 1000.0,
        "k": int(k),
        "r": float(r),
    }
    return keep_mask, stats
