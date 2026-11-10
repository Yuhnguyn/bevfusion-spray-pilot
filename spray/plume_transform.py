
"""mmdet3d pipeline transform that wraps :func:`spray.plume.inject_plume`.

Contract (spec v1.5, Interface contract #1):

- input ``results`` has ``points`` (N, 5) and ``gt_bboxes_3d`` (M, >=9:
  x, y, z, dx, dy, dz, yaw, vx, vy);
- output ``points`` (N+K, 5), ``points_clean`` (N, 5) and ``spray_stats``
  (dict). ``points_clean`` is the exact input at the moment of injection,
  so the camera branch and the LiDAR branch share one frame.

The transform only calls the generator; it does not reimplement it. The
mmdet3d import is optional so the class can be tested on a laptop CPU.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

import numpy as np

from spray.plume import (
    PlumeConfig,
    PlumeStats,
    inject_plume,
    inject_plume_stateful,
)
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.wet_ground import WetGroundConfig

try:  # pragma: no cover - exercised only inside the pinned MIT env
    from mmdet3d.datasets import PIPELINES
except Exception:  # noqa: BLE001 - laptop tests run without mmdet3d
    PIPELINES = None


def _register(cls):
    if PIPELINES is None:
        return cls
    return PIPELINES.register_module()(cls)


@_register
class PlumeTransform:
    """Insert a synthetic spray plume and keep the clean points."""

    def __init__(
        self,
        config: PlumeConfig | dict | None = None,
        enabled: bool = True,
        seed: int = 0,
        wet_ground: WetGroundConfig | None = None,
        **kwargs,
    ) -> None:
        if isinstance(config, PlumeConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = PlumeConfig(**config)
        else:
            self.config = PlumeConfig(**kwargs)
        self.enabled = bool(enabled)
        self.seed = int(seed)
        self.wet_ground = wet_ground
        self.epoch = 0
        self._state = None

    def set_epoch(self, epoch: int) -> None:
        """Record the augmentation epoch used to seed scene-level draws."""
        self.epoch = int(epoch)

    def __call__(self, results: dict) -> dict:
        points_obj = results["points"]
        points = _tensor(points_obj)
        boxes_obj = results.get("gt_bboxes_3d")
        boxes = _tensor(boxes_obj) if boxes_obj is not None else np.empty((0, 9))
        metadata = results.get("metadata") or {}
        token = str(metadata.get("token", results.get("token", "")))
        seed = int(metadata.get("seed", results.get("seed", self.seed)))

        context = results.get("plume_context")
        if context is not None:
            if not isinstance(context, PlumeContext):
                raise TypeError(
                    "results['plume_context'] must be a PlumeContext, got "
                    f"{type(context).__name__}"
                )
            seed = seed_for(
                context.scene_token, context.frame_index, context.epoch, self.seed
            )

        if not self.enabled:
            results["points_clean"] = _like(points_obj, points.copy())
            results["spray_stats"] = asdict(PlumeStats())
            return results

        if context is None:
            result = inject_plume(
                points,
                boxes,
                seed=seed,
                token=token,
                config=self.config,
            )
        else:
            state = results.get("plume_state")
            if state is None:
                if self._state is None:
                    self._state = PlumeState()
                state = self._state
            result = inject_plume_stateful(
                points,
                boxes,
                context,
                state,
                seed=seed,
                token=token,
                config=self.config,
                wet_ground=self.wet_ground,
            )
        results["points"] = _like(points_obj, result.points)
        results["points_clean"] = _like(points_obj, result.points_clean)
        results["spray_stats"] = (
            asdict(result.stats) if is_dataclass(result.stats) else dict(result.stats)
        )
        return results


def _tensor(value):
    if hasattr(value, "tensor"):
        value = value.tensor
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _like(reference, array):
    if hasattr(reference, "tensor"):
        kwargs = {}
        if hasattr(reference, "points_dim"):
            kwargs["points_dim"] = reference.points_dim
        if hasattr(reference, "attribute_dims"):
            kwargs["attribute_dims"] = reference.attribute_dims
        return type(reference)(array, **kwargs)
    if hasattr(reference, "detach"):
        import torch

        return torch.as_tensor(array, device=reference.device, dtype=reference.dtype)
    return array

