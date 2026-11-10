"""Ticket 07: PlumeTransform + points_clean on one real scene-0796 frame.

Builds val infos for scene-0796 (frozen split), patches DefaultFormatBundle3D
to wrap points_clean, inserts PlumeTransform after PointsRangeFilter, then
runs spray off/on on the same real frame.
"""

import json
import os
import sys

WORK = os.environ.get("SMOKE_WORK", "/kaggle/working/smoke_test")
sys.path.insert(0, WORK)
import smoke_common as sc  # noqa: E402

SPRAY_INIT = ""
PLUME = r'''
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PlumeConfig:
    """Tham số sinh plume.

    Ba nhóm giá trị, phân biệt rõ nguồn (xem docs/measurements/semantic-spray-stats.md,
    docs/adr/0003):

    - Hiệu chỉnh theo Linnhoff et al. 2022 (arXiv 2212.08558): ngưỡng tốc độ
      50 km/h, phân bố lognormal của bán kính cụm và số điểm/cụm.
    - Đo trên SemanticSpray (bản release local): số cụm dense mỗi frame.
    - Lựa chọn của repo, không có nguồn ngoài: bù hình học, biên an toàn.
    """

    point_cloud_range: tuple[float, float, float, float, float, float] = (
        -54.0,
        -54.0,
        -5.0,
        54.0,
        54.0,
        3.0,
    )
    # Linnhoff §III-A: spray bắt đầu ở 50 km/h.
    min_speed_kmh: float = 50.0
    # Dung sai để 50,0 km/h không bị loại vì làm tròn float32
    # (float32(50/3.6)*3.6 = 50.0000015, nhưng float32(30/3.6)*3.6 = 29.999999).
    speed_epsilon_kmh: float = 1e-3
    # Số cụm tăng tuyến tính theo tốc độ; hai đầu là lựa chọn của repo, được
    # chọn để khớp dense clusters/frame median = 5 của SemanticSpray ở dải giữa.
    clusters_speed_bounds_kmh: tuple[float, float] = (50.0, 130.0)
    clusters_at_speed_bounds: tuple[int, int] = (2, 8)
    # Số điểm mỗi cụm: lognormal, median 17 (đo được), sigma chọn để p90 ~ 40.
    points_per_cluster_median: float = 17.0
    points_per_cluster_sigma: float = 0.67
    points_per_cluster_bounds: tuple[int, int] = (3, 200)
    # Bán kính cụm: lognormal median 0,30 m (Linnhoff Fig. 5, μ=-1,2 sigma=0,8).
    cluster_radius_median_m: float = 0.30
    cluster_radius_sigma: float = 0.8
    cluster_radius_bounds_m: tuple[float, float] = (0.10, 1.50)
    distance_range_m: tuple[float, float] = (1.0, 10.0)
    height_range_m: tuple[float, float] = (0.2, 2.0)
    lateral_sigma_m: float = 0.5
    box_margin_m: float = 0.2
    max_injected_points: int = 2000
    intensity: float = 0.0
    time_lag: float = 0.0


@dataclass
class PlumeStats:
    eligible_boxes: int = 0
    skipped_no_velocity: int = 0
    skipped_low_speed: int = 0
    clusters: int = 0
    injected: int = 0
    rejected_range: int = 0
    rejected_box: int = 0
    capped: int = 0


@dataclass
class PlumeResult:
    points: np.ndarray
    points_clean: np.ndarray
    injected: np.ndarray
    stats: PlumeStats


def cluster_count_for_speed(speed_kmh: float, config: PlumeConfig | None = None) -> int:
    """Số cụm cho một box ở tốc độ cho trước (0 nếu dưới ngưỡng)."""
    cfg = config or PlumeConfig()
    if speed_kmh < cfg.min_speed_kmh - cfg.speed_epsilon_kmh:
        return 0
    lo_speed, hi_speed = cfg.clusters_speed_bounds_kmh
    lo_count, hi_count = cfg.clusters_at_speed_bounds
    if hi_speed <= lo_speed:
        return lo_count
    t = (speed_kmh - lo_speed) / (hi_speed - lo_speed)
    t = min(max(t, 0.0), 1.0)
    return int(round(lo_count + t * (hi_count - lo_count)))


def inject_plume(
    points: np.ndarray,
    boxes: np.ndarray,
    *,
    seed: int,
    token: str = "",
    config: PlumeConfig | None = None,
) -> PlumeResult:
    cfg = config or PlumeConfig()
    clean = _as_five_columns(points)
    box_arr = _as_boxes(boxes)
    rng = _rng(seed, token)
    stats = PlumeStats()
    chunks: list[np.ndarray] = []
    has_velocity = box_arr.shape[1] >= 9

    for box in box_arr:
        if not np.isfinite(box[:7]).all():
            continue
        if not _in_range(box[:3], cfg.point_cloud_range):
            continue
        if not has_velocity:
            stats.skipped_no_velocity += 1
            continue
        vx, vy = float(box[7]), float(box[8])
        if not np.isfinite(vx) or not np.isfinite(vy):
            stats.skipped_no_velocity += 1
            continue
        speed = float(np.hypot(vx, vy))
        if speed <= 1e-6:
            stats.skipped_no_velocity += 1
            continue
        speed_kmh = speed * 3.6
        n_clusters = cluster_count_for_speed(speed_kmh, cfg)
        if n_clusters == 0:
            stats.skipped_low_speed += 1
            continue

        stats.eligible_boxes += 1
        direction = -np.array([vx, vy], dtype=np.float64) / speed
        perp = np.array([-direction[1], direction[0]])

        for _ in range(n_clusters):
            distance = rng.uniform(*cfg.distance_range_m)
            lateral = rng.normal(0.0, cfg.lateral_sigma_m)
            z = rng.uniform(*cfg.height_range_m)
            center = (
                np.asarray(box[:2], dtype=np.float64)
                + direction * distance
                + perp * lateral
            )
            radius = _lognormal_clipped(
                rng,
                cfg.cluster_radius_median_m,
                cfg.cluster_radius_sigma,
                cfg.cluster_radius_bounds_m,
            )
            count = int(
                round(
                    _lognormal_clipped(
                        rng,
                        cfg.points_per_cluster_median,
                        cfg.points_per_cluster_sigma,
                        (
                            float(cfg.points_per_cluster_bounds[0]),
                            float(cfg.points_per_cluster_bounds[1]),
                        ),
                    )
                )
            )
            offsets = _ball(rng, count, radius)
            cloud = np.empty((count, 5), dtype=np.float32)
            cloud[:, 0] = offsets[:, 0] + center[0]
            cloud[:, 1] = offsets[:, 1] + center[1]
            cloud[:, 2] = offsets[:, 2] + z
            cloud[:, 3] = cfg.intensity
            cloud[:, 4] = cfg.time_lag
            chunks.append(cloud)
            stats.clusters += 1

    injected = (
        np.concatenate(chunks, axis=0)
        if chunks
        else np.empty((0, 5), dtype=np.float32)
    )

    x_min, y_min, z_min, x_max, y_max, z_max = cfg.point_cloud_range
    in_range = (
        (injected[:, 0] >= x_min)
        & (injected[:, 0] <= x_max)
        & (injected[:, 1] >= y_min)
        & (injected[:, 1] <= y_max)
        & (injected[:, 2] >= z_min)
        & (injected[:, 2] <= z_max)
    )
    stats.rejected_range = int((~in_range).sum())
    injected = injected[in_range]

    if len(injected) and len(box_arr):
        inside = np.zeros(len(injected), dtype=bool)
        for box in box_arr:
            if not np.isfinite(box[:7]).all():
                continue
            inside |= _inside_box(injected, box, cfg.box_margin_m)
        stats.rejected_box = int(inside.sum())
        injected = injected[~inside]

    if len(injected) > cfg.max_injected_points:
        keep = rng.choice(len(injected), cfg.max_injected_points, replace=False)
        keep.sort()
        stats.capped = len(injected) - cfg.max_injected_points
        injected = injected[keep]

    stats.injected = int(len(injected))
    augmented = (
        np.concatenate([clean, injected], axis=0) if len(injected) else clean.copy()
    )
    return PlumeResult(
        points=augmented,
        points_clean=clean.copy(),
        injected=injected,
        stats=stats,
    )


def _as_five_columns(points: np.ndarray) -> np.ndarray:
    arr = np.asarray(points)
    if arr.ndim != 2 or arr.shape[1] not in (4, 5):
        raise ValueError("points must have shape (N, 4) or (N, 5)")
    if arr.shape[1] == 4:
        arr = np.concatenate(
            [arr, np.zeros((arr.shape[0], 1), dtype=arr.dtype)], axis=1
        )
    return arr.astype(np.float32, copy=True)


def _as_boxes(boxes: np.ndarray) -> np.ndarray:
    arr = np.asarray(boxes, dtype=np.float32)
    if arr.size == 0:
        return arr.reshape(0, 9)
    if arr.ndim != 2 or arr.shape[1] < 7:
        raise ValueError("boxes must have shape (M, >=7)")
    return arr


def _rng(seed: int, token: str) -> np.random.Generator:
    digest = hashlib.blake2b(
        f"{token}:{seed}".encode("utf-8"), digest_size=8
    ).digest()
    return np.random.default_rng(int.from_bytes(digest, "little"))


def _in_range(
    point: np.ndarray,
    bounds: tuple[float, float, float, float, float, float],
) -> bool:
    x_min, y_min, z_min, x_max, y_max, z_max = bounds
    return (
        x_min <= point[0] <= x_max
        and y_min <= point[1] <= y_max
        and z_min <= point[2] <= z_max
    )


def _lognormal_clipped(
    rng: np.random.Generator,
    median: float,
    sigma: float,
    bounds: tuple[float, float],
) -> float:
    """Lognormal với median cho trước, kẹp vào bounds."""
    lo, hi = bounds
    value = median * float(np.exp(sigma * rng.normal()))
    return float(min(max(value, lo), hi))


def _ball(
    rng: np.random.Generator, count: int, radius: float
) -> np.ndarray:
    vec = rng.normal(size=(count, 3))
    norms = np.linalg.norm(vec, axis=1, keepdims=True)
    vec = np.divide(vec, norms, out=np.zeros_like(vec), where=norms > 0)
    scale = radius * rng.random((count, 1)) ** (1.0 / 3.0)
    return (vec * scale).astype(np.float32)


def _inside_box(points: np.ndarray, box: np.ndarray, margin: float) -> np.ndarray:
    cx, cy, cz, width, length, height, yaw = (float(v) for v in box[:7])
    dx = points[:, 0] - cx
    dy = points[:, 1] - cy
    cos_yaw = np.cos(-yaw)
    sin_yaw = np.sin(-yaw)
    local_x = dx * cos_yaw - dy * sin_yaw
    local_y = dx * sin_yaw + dy * cos_yaw
    return (
        (np.abs(local_x) <= width / 2.0 + margin)
        & (np.abs(local_y) <= length / 2.0 + margin)
        & (points[:, 2] >= cz - height / 2.0 - margin)
        & (points[:, 2] <= cz + height / 2.0 + margin)
    )
'''

PLUME_TRANSFORM = r'''
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

from spray.plume import PlumeConfig, PlumeStats, inject_plume

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

        result = inject_plume(
            points,
            boxes,
            seed=seed,
            token=token,
            config=self.config,
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

'''

STEP_INFOS = r'''
"""Ticket 07: build val infos for one fast frozen scene (scene-0796)."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["REPO"])

# numba 0.58 removed numba.errors; the pinned pipeline imports it.
try:
    import numba.errors  # noqa: F401
except Exception:
    try:
        from numba.core import errors as _numba_core_errors
        import types as _types

        _shim = _types.ModuleType("numba.errors")
        _shim.NumbaPerformanceWarning = _numba_core_errors.NumbaPerformanceWarning
        sys.modules["numba.errors"] = _shim
    except Exception:
        pass

from nuscenes.utils import splits  # noqa: E402
from tools.data_converter import nuscenes_converter as nc  # noqa: E402

SCENE = "scene-0796"
DATA = "/kaggle/working/data/nuscenes"

splits.train = []
splits.val = [SCENE]
_orig_fill = nc._fill_trainval_infos


def _fill_selected(nusc, train_scenes, val_scenes, test=False, max_sweeps=10):
    keep = set(train_scenes) | set(val_scenes)
    nusc.sample = [s for s in nusc.sample if s["scene_token"] in keep]
    nusc._token2ind["sample"] = {s["token"]: i for i, s in enumerate(nusc.sample)}
    return _orig_fill(nusc, train_scenes, val_scenes, test=test, max_sweeps=max_sweeps)


nc._fill_trainval_infos = _fill_selected
nc.create_nuscenes_infos(DATA, "nuscenes", version="v1.0-trainval", max_sweeps=0)

import mmcv  # noqa: E402

for split in ("train", "val"):
    path = Path(DATA) / ("nuscenes_infos_%s.pkl" % split)
    payload = mmcv.load(str(path))
    patched = 0
    for info in payload["infos"]:
        for cam in info.get("cams", {}).values():
            if "cam_intrinsic" not in cam and "camera_intrinsics" in cam:
                cam["cam_intrinsic"] = cam["camera_intrinsics"]
                patched += 1
    if patched:
        mmcv.dump(payload, str(path))
    print(split, "infos", len(payload["infos"]), "patched_cams", patched)

payload = mmcv.load(str(Path(DATA) / "nuscenes_infos_val.pkl"))
infos = payload["infos"]
assert infos, "scene-0796 produced no val infos"
tokens = [str(i["token"]) for i in infos]
report = {
    "scene": SCENE,
    "num_val_infos": len(infos),
    "first_token": tokens[0],
    "num_gt_first": int(len(infos[0]["gt_boxes"])),
    "num_sweeps": int(len(infos[0].get("sweeps", []))),
}
with open(os.path.join(os.environ["ART"], "ticket07_infos.json"), "w") as handle:
    json.dump(report, handle, indent=1)
print(json.dumps(report, indent=1))
print("TICKET07_INFOS_OK")

'''

STEP_SMOKE = r'''
"""Ticket 07: run the transform on one real scene-0796 frame, spray off/on."""

import json
import os
import sys

os.chdir("/kaggle/working")
sys.path.insert(0, os.environ["WORK"])
sys.path.insert(0, os.path.join(os.environ["WORK"], "scripts"))

# numba 0.58 removed numba.errors; mmdet3d.datasets imports it.
try:
    import numba.errors  # noqa: F401
except Exception:
    try:
        from numba.core import errors as _numba_core_errors
        import types as _types

        _shim = _types.ModuleType("numba.errors")
        _shim.NumbaPerformanceWarning = _numba_core_errors.NumbaPerformanceWarning
        sys.modules["numba.errors"] = _shim
    except Exception:
        pass

import numpy as np
from mmcv import ConfigDict
from mmcv.parallel import collate
from mmdet3d.datasets import build_dataset

import smoke_cfg  # noqa: E402
import spray.plume_transform  # noqa: E402,F401 - registers PlumeTransform
from spray.plume import _inside_box  # noqa: E402

ART = os.environ["ART"]


def build_cfg(enabled):
    cfg, files = smoke_cfg.load(os.environ["CONFIG_PATH"])
    dataset_cfg = ConfigDict(cfg["data"]["val"])
    kept = []
    dropped = []
    for transform in dataset_cfg["pipeline"]:
        if transform.get("type") == "LoadBEVSegmentation":
            dropped.append(transform["type"])
        else:
            kept.append(transform)
    dataset_cfg["pipeline"] = kept
    for transform in dataset_cfg["pipeline"]:
        if transform.get("type") == "Collect3D":
            transform["keys"] = [
                key for key in transform["keys"] if key != "gt_masks_bev"
            ]
            for extra in ("points_clean", "spray_stats"):
                if extra not in transform["keys"]:
                    transform["keys"].append(extra)
            dropped.append("Collect3D.gt_masks_bev")
    pipeline = dataset_cfg["pipeline"]
    index = next(
        i for i, transform in enumerate(pipeline)
        if transform.get("type") == "PointsRangeFilter"
    )
    pipeline.insert(
        index + 1,
        ConfigDict(type="PlumeTransform", enabled=bool(enabled), seed=0),
    )
    return dataset_cfg, files, dropped


on_cfg, files, dropped = build_cfg(True)
off_cfg, _, _ = build_cfg(False)
on_dataset = build_dataset(on_cfg)
off_dataset = build_dataset(off_cfg)

index = None
data_on = None
for candidate in range(len(on_dataset)):
    data = on_dataset[candidate]
    if data is None:
        continue
    stats = data.get("spray_stats") or {}
    if int(stats.get("injected", 0)) > 0:
        index = candidate
        data_on = data
        break
assert index is not None, "no scene-0796 frame with an injected plume"

data_off = off_dataset[index]
on_points = data_on["points"].data.detach().cpu().numpy()
on_clean = data_on["points_clean"].data.detach().cpu().numpy()
off_points = data_off["points"].data.detach().cpu().numpy()
off_clean = data_off["points_clean"].data.detach().cpu().numpy()
stats = data_on["spray_stats"]
boxes = data_on["gt_bboxes_3d"].data.tensor.detach().cpu().numpy()

checks = {
    "points_clean_equals_off_points": bool(np.array_equal(on_clean, off_points)),
    "spray_off_clean_equals_points": bool(np.array_equal(off_points, off_clean)),
    "injected_count_matches_stats": bool(
        len(on_points) - len(on_clean) == int(stats["injected"])
    ),
    "injected_positive": bool(int(stats["injected"]) > 0),
    "clean_count_matches_frame": bool(len(on_clean) == len(off_points)),
}

injected = on_points[len(on_clean) :]
inside = np.zeros(len(injected), dtype=bool)
for box in boxes:
    if np.isfinite(box[:7]).all():
        inside |= _inside_box(injected, box[:7], 0.2)
checks["no_injected_point_inside_gt_box"] = bool(not inside.any())

data_on_again = on_dataset[index]
checks["deterministic_same_seed"] = bool(
    np.array_equal(data_on_again["points"].data.detach().cpu().numpy(), on_points)
)

pipeline_types = [str(t.get("type")) for t in on_cfg["pipeline"]]
checks["plume_after_range_filter"] = pipeline_types.index(
    "PlumeTransform"
) > pipeline_types.index("PointsRangeFilter")
checks["plume_before_format"] = pipeline_types.index(
    "PlumeTransform"
) < pipeline_types.index("DefaultFormatBundle3D")
checks["points_clean_collected"] = "points_clean" in data_on
checks["spray_stats_collected"] = "spray_stats" in data_on

def _batch_shape(entry):
    for _ in range(6):
        if isinstance(entry, (list, tuple)):
            if not entry:
                return None
            entry = entry[0]
        elif hasattr(entry, "data"):
            entry = entry.data
        else:
            break
    return list(entry.shape) if hasattr(entry, "shape") else None


collate_error = None
try:
    batch = collate(
        [{k: v for k, v in data_on.items() if k != "spray_stats"}],
        samples_per_gpu=1,
    )
    checks["collate_points_clean"] = "points_clean" in batch
    batch_clean_shape = _batch_shape(batch["points_clean"])
    batch_points_shape = _batch_shape(batch["points"])
except Exception as exc:  # noqa: BLE001 - reported verbatim
    collate_error = repr(exc)[:2000]
    batch_clean_shape = None
    batch_points_shape = None
    checks["collate_points_clean"] = False

metas = data_on.get("metas")
metas = metas.data if hasattr(metas, "data") else {}
token = str(metas.get("token", "")) if isinstance(metas, dict) else ""

report = {
    "frame_index": index,
    "token": token,
    "pipeline": pipeline_types,
    "dropped_transforms": dropped,
    "config_files": files,
    "points_clean": int(len(on_clean)),
    "points_augmented": int(len(on_points)),
    "stats": stats,
    "gt_boxes": int(len(boxes)),
    "batch_shapes": {
        "points_clean": batch_clean_shape,
        "points": batch_points_shape,
    },
    "collate_error": collate_error,
    "checks": checks,
    "pass": bool(all(checks.values())),
}
with open(os.path.join(ART, "ticket07_transform.json"), "w") as handle:
    json.dump(report, handle, indent=1)
print(json.dumps(report, indent=1))
print("TICKET07_OK" if report["pass"] else "TICKET07_FAILED")

'''

spray_dir = os.path.join(sc.SCRIPTS, "spray")
os.makedirs(spray_dir, exist_ok=True)
with open(os.path.join(spray_dir, "__init__.py"), "w") as handle:
    handle.write(SPRAY_INIT)
with open(os.path.join(spray_dir, "plume.py"), "w") as handle:
    handle.write(PLUME)
with open(os.path.join(spray_dir, "plume_transform.py"), "w") as handle:
    handle.write(PLUME_TRANSFORM)
sc.write_script("step_infos_scene.py", STEP_INFOS)
sc.write_script("step_transform_smoke.py", STEP_SMOKE)

# DefaultFormatBundle3D only wraps points and radar; add points_clean.
format_path = os.path.join(sc.REPO, "mmdet3d/datasets/pipelines/formating.py")
with open(format_path) as handle:
    source = handle.read()
anchor = (
    '        if "points" in results:\n'
    '            assert isinstance(results["points"], BasePoints)\n'
    '            results["points"] = DC(results["points"].tensor)\n'
)
addition = (
    '        if "points_clean" in results:\n'
    '            assert isinstance(results["points_clean"], BasePoints)\n'
    '            results["points_clean"] = DC(results["points_clean"].tensor)\n'
)
if addition not in source:
    if source.count(anchor) != 1:
        raise RuntimeError("formating.py anchor count: %d" % source.count(anchor))
    with open(format_path, "w") as handle:
        handle.write(source.replace(anchor, anchor + addition))
    print("patched formating.py")
else:
    print("formating.py already patched")

rc, text = sc.run_script("step_infos_scene.py", log_name="step_infos_scene.log", timeout=1800)
print("infos rc = %d" % rc)
if rc != 0 or "TICKET07_INFOS_OK" not in text:
    print(text[-4000:])
    raise SystemExit("infos step failed")

rc, text = sc.run_script("step_transform_smoke.py", log_name="step_transform_smoke.log", timeout=1800)
report = sc.load_json("ticket07_transform.json")
print("smoke rc = %d" % rc)
print(json.dumps(report, indent=1))
print("TICKET07_OK" if "TICKET07_OK" in text else "TICKET07_FAILED (see logs/step_transform_smoke.log)")
