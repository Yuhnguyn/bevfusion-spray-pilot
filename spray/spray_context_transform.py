"""Pipeline transform that builds the per-frame :class:`PlumeContext`.

``PlumeTransform`` needs speeds, the ego pose, the lidar origin and the water
film height before it can run the stateful plume and the ray casting. Neither
the infos nor the vendor pipeline carry speeds, so they come from the sidecar
written by ``scripts/build_plume_speed_index.py`` and keyed by ``lidar_path``.

The transform only reads ``results``; it raises instead of silently skipping a
frame, because a missing context would make ``PlumeTransform`` fall back to the
old stateless generator and quietly change the experiment.
"""

from __future__ import annotations

import json
import pathlib

from spray.plume import PlumeConfig
from spray.plume_context import PlumeContext, PlumeContextError

try:  # pragma: no cover - exercised only inside the pinned MIT env
    from mmdet3d.datasets import PIPELINES
except Exception:  # noqa: BLE001 - laptop tests run without mmdet3d
    PIPELINES = None


def _register(cls):
    if PIPELINES is None:
        return cls
    return PIPELINES.register_module()(cls)


@_register
class SprayContextTransform:
    """Attach ``results["plume_context"]`` from the offline speed sidecar.

    ``wfh_mm`` and ``road_z_m`` are experiment parameters, not scene
    properties: the water film height comes from ``PlumeConfig`` (millimetres)
    and the road plane is passed by the caller (SemanticSpray and nuScenes have
    different ground heights, ticket 25).
    """

    def __init__(
        self,
        sidecar_path: str | pathlib.Path,
        wfh_mm: float | None = None,
        road_z_m: float = -0.411,
        config: PlumeConfig | dict | None = None,
        enabled: bool = True,
        **kwargs,
    ) -> None:
        if isinstance(config, dict):
            config = PlumeConfig(**config)
        elif config is None:
            config = PlumeConfig(**kwargs)
        self.config = config
        self.road_z_m = float(road_z_m)
        self.wfh_mm = (
            float(wfh_mm)
            if wfh_mm is not None
            else 1000.0 * float(self.config.water_film_height_m)
        )
        self.enabled = bool(enabled)
        self.epoch = 0
        self.sidecar_path = pathlib.Path(sidecar_path)
        with self.sidecar_path.open(encoding="utf-8") as handle:
            self.sidecar = json.load(handle)
        if not isinstance(self.sidecar, dict):
            raise TypeError(
                f"{self.sidecar_path}: sidecar must be a JSON object keyed by "
                "lidar_path"
            )

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __call__(self, results: dict) -> dict:
        if not self.enabled:
            return results

        lidar_path = results.get("lidar_path")
        if not lidar_path:
            raise PlumeContextError(
                "missing required sample key: lidar_path (needed to look up the "
                "plume speed sidecar)"
            )

        entry = self.sidecar.get(str(lidar_path))
        if entry is None:
            raise PlumeContextError(
                f"no sidecar entry for lidar_path={lidar_path!r}; run "
                "scripts/build_plume_speed_index.py on the infos used here"
            )
        for key in ("ego_speed_mps", "object_speed_mps"):
            if key not in entry:
                raise PlumeContextError(f"sidecar entry for {lidar_path!r} lacks {key}")

        scene_token = results.get("scene_token") or entry.get("scene_token")
        if not scene_token:
            raise PlumeContextError(
                "missing required sample key: scene_token (not present in results "
                "or the sidecar)"
            )

        frame_index = results.get("sample_idx")
        if frame_index is None:
            frame_index = entry.get("frame_index")
        if frame_index is None:
            raise PlumeContextError(
                "missing required sample key: sample_idx (not present in results "
                "or the sidecar)"
            )

        epoch = results.get("epoch", self.epoch)
        sample = dict(results)
        sample["scene_token"] = scene_token
        sample["ego_speed_mps"] = entry["ego_speed_mps"]
        sample["object_speed_mps"] = entry["object_speed_mps"]
        results["plume_context"] = PlumeContext.from_sample(
            sample,
            epoch=epoch,
            wfh_mm=self.wfh_mm,
            road_z_m=self.road_z_m,
            frame_index=frame_index,
            ego_speed_mps=entry["ego_speed_mps"],
        )
        return results
