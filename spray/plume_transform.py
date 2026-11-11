"""mmdet3d pipeline transform that runs the stateful plume and ray casting.

Contract (spec v1.5, Interface contract #1):

- input ``results`` has ``points`` (N, 5), ``gt_bboxes_3d`` (M, >=9:
  x, y, z, dx, dy, dz, yaw, vx, vy) and ``plume_context`` (ticket 29e);
- output ``points`` (N', 5), ``points_clean`` (N, 5) and ``spray_stats``
  (dict). ``points_clean`` is the exact input at the moment of injection,
  so the camera branch and the LiDAR branch share one frame.

With a context the transform always runs the stateful generator and then
:func:`spray.raycast.raycast_frame`:

- the clusters cast through a uniform beam grid; a hit spawns a detection with
  ``P_det = n/n_max`` and the traveled segment attenuates real returns by
  ``exp(-2 * 0.02 * L)``;
- ``points`` is ``real_points`` (attenuated, occluded returns removed)
  followed by ``detections``;
- ``points_clean`` is untouched, so the camera branch never sees attenuation.

There is no silent fallback to the stateless generator: a missing context
raises, because that fallback would change the A/B experiment without saying
so.

The mmdet3d import is optional so the class can be tested on a laptop CPU.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass

import numpy as np

from spray.beam_model import load_beam_table
from spray.plume import (
    PlumeConfig,
    PlumeStats,
    inject_plume_stateful,
)
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
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

        if not self.enabled:
            results["points_clean"] = _like(points_obj, points.copy())
            results["spray_stats"] = asdict(PlumeStats())
            return results

        context = results.get("plume_context")
        if context is None:
            raise RuntimeError(
                "PlumeTransform requires plume_context; enable SprayContextTransform"
            )
        if not isinstance(context, PlumeContext):
            raise TypeError(
                "results['plume_context'] must be a PlumeContext, got "
                f"{type(context).__name__}"
            )
        seed = seed_for(
            context.scene_token, context.frame_index, context.epoch, self.seed
        )

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

        clean = result.points_clean
        raycast = raycast_frame(
            clean,
            state.all_alive(),
            table=load_beam_table(),
            road_z_m=context.road_z_m,
            rng=np.random.default_rng(seed),
            capped=result.stats.capped,
        )

        augmented = np.concatenate(
            [raycast.real_points, raycast.detections], axis=0
        ).astype(points.dtype, copy=False)
        results["points"] = _like(points_obj, augmented)
        results["points_clean"] = _like(points_obj, result.points_clean)
        stats = (
            asdict(result.stats) if is_dataclass(result.stats) else dict(result.stats)
        )
        stats["det"] = int(raycast.stats.det)
        stats["beams_hit"] = int(raycast.stats.beams_hit)
        stats["att_m_total"] = float(raycast.stats.att_m_total)
        stats["att_real_points"] = int(raycast.stats.att_real_points)
        stats["injected"] = int(raycast.stats.det)
        results["spray_stats"] = stats
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
