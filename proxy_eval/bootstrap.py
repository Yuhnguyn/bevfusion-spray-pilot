"""Scene-level paired bootstrap for the A/B proxy mAP comparison.

The statistical unit is a **scene**, not a frame: frames from one scene are
highly correlated (same road, weather, traffic), so resampling frames would
make the confidence interval look falsely narrow.  This module only needs
``numpy`` -- it never imports torch or the nuScenes devkit.

Typical use, after the kernel writes per-frame proxy mAP::

    clean = per_scene_metric(clean_frames, "mAP_proxy")
    spray = per_scene_metric(spray_frames, "mAP_proxy")
    gain = paired_delta(clean, spray)              # G = mAP_clean - mAP_spray
    scene_bootstrap(gain)                         # mean / lo / hi over scenes
"""

from __future__ import annotations

import numpy as np

MIN_SHARED_SCENES = 8

__all__ = [
    "MIN_SHARED_SCENES",
    "paired_delta",
    "per_scene_metric",
    "scene_bootstrap",
]


def per_scene_metric(frames, metric):
    """Average per-frame ``metric`` values inside each scene.

    ``frames`` is an iterable of dicts carrying ``scene_token`` and ``metric``.
    Returns ``{scene_token: mean}`` with sorted keys so the result does not
    depend on input order.
    """
    grouped: dict[str, list[float]] = {}
    for frame in frames:
        scene = frame["scene_token"]
        grouped.setdefault(scene, []).append(float(frame[metric]))
    return {
        scene: float(np.mean(values))
        for scene, values in sorted(grouped.items())
    }


def paired_delta(a, b):
    """Per-scene ``a - b`` over scenes present in both sides.

    Scenes missing from either side are dropped (paired comparison).  With an
    eval set of only ~16 scenes, fewer than :data:`MIN_SHARED_SCENES` shared
    scenes is too small to bootstrap, so this raises instead of returning a
    number nobody should trust.
    """
    common = sorted(set(a) & set(b))
    if len(common) < MIN_SHARED_SCENES:
        raise ValueError(
            f"paired delta needs at least {MIN_SHARED_SCENES} shared scenes, "
            f"got {len(common)}"
        )
    return {scene: float(a[scene]) - float(b[scene]) for scene in common}


def scene_bootstrap(deltas, n=2000, seed=0, alpha=0.05):
    """Percentile bootstrap over scenes.

    Resamples scenes with replacement ``n`` times, so each resample keeps the
    frame weighting inside a scene but ignores between-scene correlation.  The
    point estimate is the observed mean delta; ``lo``/``hi`` are the
    ``alpha/2`` and ``1 - alpha/2`` percentiles of the resampled means.

    ``seed`` makes the result deterministic.  Returns
    ``{"mean", "lo", "hi", "n_scenes", "n_resamples"}``.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    values = np.asarray(
        [float(deltas[scene]) for scene in sorted(deltas)], dtype=np.float64
    )
    if values.size == 0:
        raise ValueError("scene_bootstrap needs at least one scene")

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(n, values.size))
    means = values[indices].mean(axis=1)
    lo, hi = np.percentile(means, [100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0)])

    return {
        "mean": float(values.mean()),
        "lo": float(lo),
        "hi": float(hi),
        "n_scenes": int(values.size),
        "n_resamples": int(n),
    }
