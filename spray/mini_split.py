"""Deterministic mini-train subset selection for the ticket-11 A/B run.

Pure helpers only: nothing here imports ``nuscenes`` (the local machine has no
devkit).  Channel names and the val split are read from the pinned vendor tree
instead of being copied, so a re-vendor cannot silently change them.

The val split must come from the official nuScenes ``splits.py``.  Guessing a
different split would leak val scenes into training and invalidate the whole
experiment, so :func:`load_val_scenes` raises instead of falling back.
"""

from __future__ import annotations

import ast
import random
from collections import Counter
from pathlib import Path

import numpy as np

__all__ = [
    "DEFAULT_SPLITS_PATH",
    "VAL_SCENES_CACHE",
    "load_camera_types",
    "load_val_scenes",
    "select_tokens",
    "summarize",
    "validate_info",
]

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLITS_PATH = _REPO_ROOT / "mit/bevfusion/nuscenes/utils/splits.py"
VENDOR_CONVERTER_PATH = (
    _REPO_ROOT / "mit/bevfusion/tools/data_converter/nuscenes_converter.py"
)

VAL_SCENES_CACHE = None
_CAMERA_TYPES_CACHE = None


def _top_level_names(tree) -> list[str]:
    seen = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id not in seen:
                seen.append(target.id)
    return seen


def _extract_list_literal(text: str, name: str, source: str):
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(
            f"cannot parse {source}: line {exc.lineno}: {exc.msg}"
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        else:
            continue
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        try:
            return ast.literal_eval(node.value)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"`{name}` in {source} is not a literal: {exc}"
            ) from exc

    seen = _top_level_names(tree)
    raise ValueError(
        f"no `{name}` assignment in {source}; top-level names: {seen}"
    )


def _read_list(path: Path, name: str) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"cannot read `{name}` from missing file: {path}")
    values = _extract_list_literal(path.read_text(), name, str(path))
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ValueError(f"`{name}` in {path} is not a list of strings")
    return values


def load_camera_types(path_or_none=None) -> tuple[str, ...]:
    """nuScenes camera channel names, read from the pinned vendor converter.

    Source: ``mit/bevfusion/tools/data_converter/nuscenes_converter.py``,
    ``_fill_trainval_infos`` (``camera_types = [...]``).
    """
    global _CAMERA_TYPES_CACHE

    if path_or_none is None and _CAMERA_TYPES_CACHE is not None:
        return _CAMERA_TYPES_CACHE

    path = Path(path_or_none) if path_or_none is not None else VENDOR_CONVERTER_PATH
    channel_names = tuple(_read_list(path, "camera_types"))
    if not channel_names or any(not name.startswith("CAM_") for name in channel_names):
        raise ValueError(f"unexpected camera channel list in {path}: {channel_names}")

    if path_or_none is None:
        _CAMERA_TYPES_CACHE = channel_names
    return channel_names


def load_val_scenes(path_or_none=None) -> frozenset[str]:
    """Official nuScenes val scene names (``val = [...]`` in ``splits.py``).

    Default source is the vendor tree at
    ``mit/bevfusion/nuscenes/utils/splits.py``.  When that file is absent (this
    checkout only vendors ``tools/`` and ``mmdet3d/``) pass an explicit
    ``path_or_none`` -- normally the installed devkit's ``splits.py``.  If
    neither is available this raises; no fallback split is ever guessed.
    """
    global VAL_SCENES_CACHE

    if path_or_none is None:
        if VAL_SCENES_CACHE is not None:
            return VAL_SCENES_CACHE
        path = DEFAULT_SPLITS_PATH
    else:
        path = Path(path_or_none)

    scenes = frozenset(_read_list(path, "val"))
    if not scenes:
        raise ValueError(f"official val split is empty in {path}")

    if path_or_none is None:
        VAL_SCENES_CACHE = scenes
    return scenes


def select_tokens(samples, n, seed, val_scenes) -> list[str]:
    """Pick ``n`` train tokens deterministically.

    ``samples`` is a list of dicts carrying ``token`` and ``scene_token``.
    Samples whose ``scene_token`` is in ``val_scenes`` are dropped.  The
    remaining tokens are sorted, then drawn without replacement with
    ``random.Random(seed)``; the result is sorted again so the output never
    depends on the input order or machine.  ``scene_token`` is compared in the
    same namespace as ``val_scenes`` (the CLI passes scene *names* there).

    Raises ``ValueError`` when ``n`` exceeds the number of candidates.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")

    excluded = set(val_scenes or ())
    eligible: dict[str, str] = {}
    for sample in samples:
        token = sample["token"]
        if sample["scene_token"] in excluded:
            continue
        eligible[token] = sample["scene_token"]

    candidates = sorted(eligible)
    if n > len(candidates):
        raise ValueError(
            f"cannot select {n} tokens from {len(candidates)} eligible candidates"
        )

    rng = random.Random(seed)
    pool = list(candidates)
    picked: list[str] = []
    for _ in range(n):
        index = rng.choice(range(len(pool)))
        picked.append(pool.pop(index))
    return sorted(picked)


def _cam_errors(cam_name: str, cam: dict) -> list[str]:
    errors: list[str] = []
    required = (
        "data_path",
        "sample_data_token",
        "sensor2ego_translation",
        "sensor2ego_rotation",
        "ego2global_translation",
        "ego2global_rotation",
    )
    for key in required:
        if key not in cam:
            errors.append(f"camera {cam_name}: missing {key}")
    if "camera_intrinsics" not in cam and "cam_intrinsic" not in cam:
        errors.append(f"camera {cam_name}: missing calibrated_sensor intrinsics")
    return errors


def validate_info(info) -> list[str]:
    """Return a list of problems (empty means valid).

    Checks token, scene_token, timestamp, the 6 ``CAM_*`` channels with
    calibrated_sensor/sensor2ego/ego2global fields, ``lidar_path``
    (``LIDAR_TOP``), a ``sweeps`` list (may be empty if the dataset ships
    keyframes only), and matching ``gt_boxes``/``gt_names`` shapes.
    """
    if not isinstance(info, dict):
        return ["info is not a dict"]

    errors: list[str] = []

    token = info.get("token")
    if not isinstance(token, str) or not token:
        errors.append("missing token")

    scene_token = info.get("scene_token")
    if not isinstance(scene_token, str) or not scene_token:
        errors.append("missing scene_token")

    timestamp = info.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        errors.append("missing timestamp")

    lidar_path = info.get("lidar_path")
    if not isinstance(lidar_path, str) or not lidar_path:
        errors.append("missing lidar_path (LIDAR_TOP keyframe)")

    sweeps = info.get("sweeps")
    if not isinstance(sweeps, (list, tuple)):
        errors.append("missing sweeps")

    cams = info.get("cams")
    if not isinstance(cams, dict):
        errors.append("missing cams")
        cams = {}
    else:
        for cam_name in load_camera_types():
            cam = cams.get(cam_name)
            if cam is None:
                errors.append(f"missing camera {cam_name}")
            elif not isinstance(cam, dict):
                errors.append(f"camera {cam_name}: not a dict")
            else:
                errors.extend(_cam_errors(cam_name, cam))

    gt_boxes = info.get("gt_boxes")
    try:
        boxes = np.asarray(gt_boxes)
    except Exception:  # noqa: BLE001 - report, never raise from validation
        boxes = None
    if boxes is None or boxes.ndim != 2 or boxes.shape[1] != 7:
        shape = None if boxes is None else boxes.shape
        errors.append(f"gt_boxes shape {shape} is not (N, 7)")
    else:
        gt_names = info.get("gt_names")
        if gt_names is None:
            errors.append("missing gt_names")
        elif len(gt_names) != boxes.shape[0]:
            errors.append(
                f"gt_names length {len(gt_names)} != gt_boxes {boxes.shape[0]}"
            )

    return errors


def summarize(infos) -> dict:
    """Counts used by the mini-split report and the training log."""
    camera_types = load_camera_types()
    per_cam_count = {cam: 0 for cam in camera_types}
    per_class_counts: Counter = Counter()
    scenes = set()
    gt_boxes_total = 0

    for info in infos:
        scene_token = info.get("scene_token")
        if scene_token:
            scenes.add(scene_token)

        boxes = info.get("gt_boxes")
        gt_boxes_total += 0 if boxes is None else len(boxes)

        gt_names = info.get("gt_names")
        if gt_names is not None:
            for name in gt_names:
                per_class_counts[str(name)] += 1

        info_cams = info.get("cams") or {}
        for cam in camera_types:
            if cam in info_cams:
                per_cam_count[cam] += 1

    return {
        "n_samples": len(infos),
        "n_scenes": len(scenes),
        "gt_boxes_total": gt_boxes_total,
        "per_cam_count": per_cam_count,
        "per_class_counts": dict(sorted(per_class_counts.items())),
    }
