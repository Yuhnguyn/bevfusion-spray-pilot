"""Per-frame inputs for the spray plume generator v2.

The v1 generator only needs ``points`` and ``boxes``. Steps 3-5 of
``spec-v2-paper-faithful.md`` also need the ego transform, the ray origin, the
beam elevation table, both speeds, the water film height, the road plane and a
reproducible seed per scene. This module is the data contract that carries
them; it does not call the generator.
"""

from __future__ import annotations

import hashlib
import numbers
from dataclasses import dataclass

import numpy as np


class PlumeContextError(ValueError):
    """A plume context field is missing or violates its contract."""


@dataclass(frozen=True)
class PlumeContext:
    """Everything one augmented frame needs besides points and boxes.

    Units follow ``spec-v2-paper-faithful.md`` §2: metres and metres/second,
    except ``wfh_mm`` which stays in millimetres (§1: the paper's unit, used by
    both the cluster count and the lifetime formula).

    ``ego_speed_mps`` and ``object_speed_mps`` are separate fields on purpose:
    ticket 25 measured them as equal in all 207 SemanticSpray scenes, but they
    are different physical quantities and must not be collapsed into one.
    """

    scene_token: str
    frame_index: int
    epoch: int
    sensor_origin: np.ndarray
    ego_speed_mps: float
    object_speed_mps: float
    wfh_mm: float
    road_z_m: float
    ego_pose: np.ndarray | None = None
    elevation_angles_deg: np.ndarray | None = None
    boxes: np.ndarray | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scene_token, str) or not self.scene_token:
            raise PlumeContextError("scene_token must be a non-empty string")
        object.__setattr__(self, "frame_index", _index("frame_index", self.frame_index))
        object.__setattr__(self, "epoch", _index("epoch", self.epoch))
        object.__setattr__(
            self,
            "sensor_origin",
            _array("sensor_origin", self.sensor_origin, (3,)),
        )
        object.__setattr__(
            self, "ego_speed_mps", _speed("ego_speed_mps", self.ego_speed_mps)
        )
        object.__setattr__(
            self,
            "object_speed_mps",
            _speed("object_speed_mps", self.object_speed_mps),
        )
        object.__setattr__(self, "wfh_mm", _water_film_height(self.wfh_mm))
        object.__setattr__(self, "road_z_m", _finite("road_z_m", self.road_z_m))

        if self.ego_pose is not None:
            pose = _array("ego_pose", self.ego_pose, (4, 4))
            rotation = pose[:3, :3]
            error = np.abs(rotation @ rotation.T - np.eye(3)).max()
            if error >= 1e-6:
                raise PlumeContextError(
                    "ego_pose 3x3 block must be an orthogonal rotation "
                    f"(max |R R^T - I| = {error:.3e} >= 1e-6)"
                )
            object.__setattr__(self, "ego_pose", pose)

        if self.elevation_angles_deg is not None:
            object.__setattr__(
                self,
                "elevation_angles_deg",
                _array("elevation_angles_deg", self.elevation_angles_deg, (32,)),
            )

        if self.boxes is not None:
            object.__setattr__(self, "boxes", _boxes(self.boxes))

    @classmethod
    def from_sample(
        cls,
        sample: dict,
        *,
        epoch: int,
        wfh_mm: float,
        road_z_m: float,
        frame_index: int,
        ego_speed_mps: float | None = None,
    ) -> "PlumeContext":
        """Build a context from a nuScenes/mmdet3d style sample dict.

        ``wfh_mm`` and ``road_z_m`` deliberately have no default: the water
        film height is sampled per frame and the road plane depends on the
        dataset being augmented (ticket 25 measured different ground heights
        for SemanticSpray and nuScenes), so the caller must pass both.

        Ego speed is never derived from ego-pose displacement: SemanticSpray
        ``poses.txt`` carries no translation at all. It is read from the sample
        or from the explicit ``ego_speed_mps`` override.

        ``ego2global`` (ego -> world) is inverted so ``ego_pose`` keeps the
        contract direction of world -> ego; an ``ego_pose`` key is already in
        that direction and is used as-is.
        """
        missing: list[str] = []

        scene_token = sample.get("scene_token")
        if not isinstance(scene_token, str) or not scene_token:
            missing.append("scene_token")

        timestamp = sample.get("timestamp")
        if timestamp is None:
            missing.append("timestamp")
        elif not _is_finite_number(timestamp):
            raise PlumeContextError("timestamp must be a finite number")

        ego_pose = sample.get("ego_pose")
        ego2global = sample.get("ego2global")
        if ego_pose is None and ego2global is None:
            missing.append("ego2global or ego_pose")

        origin = sample.get("sensor_origin")
        if origin is None:
            lidar2ego = sample.get("lidar2ego")
            if lidar2ego is not None:
                transform = _tensor_to_array(lidar2ego)
                if transform.shape != (4, 4):
                    raise PlumeContextError(
                        f"lidar2ego must have shape (4, 4), got {transform.shape}"
                    )
                origin = transform[:3, 3]
        if origin is None:
            missing.append("sensor_origin")

        speed = ego_speed_mps if ego_speed_mps is not None else sample.get(
            "ego_speed_mps"
        )
        if speed is None:
            missing.append("ego_speed_mps")

        object_speed = sample.get("object_speed_mps")
        if object_speed is None:
            missing.append("object_speed_mps")

        if missing:
            raise PlumeContextError(
                "missing required sample keys: " + ", ".join(sorted(missing))
            )

        if ego_pose is not None:
            pose = _tensor_to_array(ego_pose)
        else:
            pose = _world_to_ego(_tensor_to_array(ego2global))

        boxes = sample.get("gt_bboxes_3d")
        if boxes is not None:
            boxes = _tensor_to_array(boxes)

        return cls(
            scene_token=scene_token,
            frame_index=frame_index,
            epoch=epoch,
            sensor_origin=origin,
            ego_speed_mps=speed,
            object_speed_mps=object_speed,
            wfh_mm=wfh_mm,
            road_z_m=road_z_m,
            ego_pose=pose,
            boxes=boxes,
        )


def seed_for(
    scene_token: str, frame_index: int, epoch: int, base_seed: int = 0
) -> int:
    """Deterministic seed for one frame, stable across processes.

    ``hashlib`` is used instead of ``hash()`` because string hashing is
    randomised per process by ``PYTHONHASHSEED``. Changing ``epoch`` changes
    the seed, so repeated augmentation passes draw different plumes.
    """
    payload = f"{scene_token}:{int(frame_index)}:{int(epoch)}:{int(base_seed)}"
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little")


def compute_elevation_deg(points: np.ndarray) -> np.ndarray:
    """Elevation angle in degrees for every point, from its coordinates.

    Ring index (column 4) is not used: ticket 25 measured a 3.49 deg median
    mismatch against the VLP-32C table, so the angle must come from geometry.
    """
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] < 3:
        raise PlumeContextError(
            f"points must have shape (N, >=3), got {arr.shape}"
        )
    return np.degrees(np.arctan2(arr[:, 2], np.hypot(arr[:, 0], arr[:, 1])))


def _index(field: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise PlumeContextError(f"{field} must be an int, got {type(value).__name__}")
    number = int(value)
    if number < 0:
        raise PlumeContextError(f"{field} must be >= 0, got {number}")
    return number


def _finite(field: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise PlumeContextError(
            f"{field} must be a real number, got {type(value).__name__}"
        )
    number = float(value)
    if not np.isfinite(number):
        raise PlumeContextError(f"{field} must be finite, got {number}")
    return number


def _speed(field: str, value) -> float:
    number = _finite(field, value)
    if number < 0.0:
        raise PlumeContextError(f"{field} must be >= 0, got {number}")
    return number


def _water_film_height(value) -> float:
    number = _finite("wfh_mm", value)
    if not 0.0 < number <= 1.2:
        raise PlumeContextError(
            f"wfh_mm must satisfy 0 < wfh_mm <= 1.2 (millimetres), got {number}"
        )
    return number


def _array(field: str, value, shape: tuple[int, ...]) -> np.ndarray:
    if value is None:
        raise PlumeContextError(f"{field} must not be None")
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise PlumeContextError(f"{field} must be a float64 array") from exc
    if array.shape != shape:
        raise PlumeContextError(
            f"{field} must have shape {shape}, got {array.shape}"
        )
    if not np.isfinite(array).all():
        raise PlumeContextError(f"{field} must be finite")
    return array


def _boxes(value) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise PlumeContextError("boxes must be a float64 array") from exc
    if array.ndim != 2 or array.shape[1] != 9:
        raise PlumeContextError(f"boxes must have shape (M, 9), got {array.shape}")
    return array


def _is_finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    return bool(np.isfinite(float(value)))


def _tensor_to_array(value) -> np.ndarray:
    if hasattr(value, "tensor"):
        value = value.tensor
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value, dtype=np.float64)


def _world_to_ego(ego2global: np.ndarray) -> np.ndarray:
    pose = _array("ego_pose", ego2global, (4, 4))
    inverse = np.eye(4)
    rotation = pose[:3, :3]
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ pose[:3, 3]
    return inverse
