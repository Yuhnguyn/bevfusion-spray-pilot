"""Build arm A (clean) and arm B (spray) training configs.

The only thing that may differ between the two arms is the presence of
``PlumeTransform`` in ``train_pipeline`` (plus the ``spray`` block that
describes it).  The training budget lives in :data:`TRAIN_SPEC` and is shared,
and :func:`diff_paths` on the two configs is the machine-checkable proof.

No mmcv/mmdet3d import here: the builder runs on a laptop so the diff can be
inspected before any GPU work.
"""

from __future__ import annotations

import copy
import pathlib

from spray.config_merge import diff_paths, load_yaml, resolve

__all__ = [
    "CONFIG_DIR",
    "DATASET_CONFIG",
    "KEEP_STEPS",
    "MODEL_CONFIG",
    "SPRAY_CONFIG",
    "SPRAY_PARAMS",
    "TRAIN_SPEC",
    "build_cfg",
    "diff_paths",
    "train_pipeline",
]

CONFIG_DIR = pathlib.Path("mit/bevfusion/configs/nuscenes")
DATASET_CONFIG = CONFIG_DIR / "default.yaml"
MODEL_CONFIG = (
    CONFIG_DIR / "det/transfusion/secfpn/camera+lidar/swint_v0p075/default.yaml"
)
SPRAY_CONFIG = pathlib.Path("spray/config/plume_default.yaml")

# The augmentation slice shared by both arms, in config order.
KEEP_STEPS = (
    "GlobalRotScaleTrans",
    "RandomFlip3D",
    "PointsRangeFilter",
    "ObjectRangeFilter",
    "PointShuffle",
)

# Formatting steps that carry ``points_clean`` to the model.  Both arms use the
# spray replacements so that the Clean* swap is not part of the A/B diff.
RENAMED_STEPS = {
    "DefaultFormatBundle3D": "CleanPointsFormatBundle3D",
    "Collect3D": "CleanPointsCollect3D",
}

ARMS = ("A", "B")

# [CHỌN] Identical for both arms; changing it changes both budgets at once.
TRAIN_SPEC = dict(
    seed=0,
    batch_size=2,
    lr=1e-4,
    weight_decay=0.01,
    optimizer="AdamW",
    max_iters=2000,
    warmup_iters=100,
    grad_clip=5.0,
    eval_every=500,
)

SPRAY_PARAMS = load_yaml(SPRAY_CONFIG)


def _check_arm(arm: str) -> None:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")


def _rename(step: dict) -> dict:
    return {"type": RENAMED_STEPS[step["type"]], **{
        key: value for key, value in step.items() if key != "type"
    }}


def _plume_step() -> dict:
    return {
        "type": "PlumeTransform",
        "enabled": True,
        "seed": 0,
        "config": copy.deepcopy(SPRAY_PARAMS),
    }


def train_pipeline(arm: str) -> list[dict]:
    """Return the resolved pipeline slice for ``arm``.

    Steps are taken in config order: the five ``KEEP_STEPS`` plus the two
    formatting steps renamed to their ``Clean*`` replacements.  Arm B inserts
    one ``PlumeTransform`` right after ``RandomFlip3D``.
    """
    _check_arm(arm)
    raw = load_yaml(DATASET_CONFIG)
    steps: list[dict] = []
    for step in raw["train_pipeline"]:
        kind = step["type"]
        if kind in KEEP_STEPS:
            steps.append(resolve(step, raw))
        elif kind in RENAMED_STEPS:
            steps.append(_rename(resolve(step, raw)))
    if arm == "B":
        steps = _with_plume(steps)
    return steps


def _with_plume(steps: list[dict]) -> list[dict]:
    out: list[dict] = []
    for step in steps:
        out.append(step)
        if step["type"] == "RandomFlip3D":
            out.append(_plume_step())
    return out


def build_cfg(arm: str) -> dict:
    """Return the JSON-serializable config for ``arm``."""
    _check_arm(arm)
    return {
        "arm": arm,
        "train_spec": dict(TRAIN_SPEC),
        "model_config": str(MODEL_CONFIG),
        "train_pipeline": train_pipeline(arm),
        "spray": copy.deepcopy(SPRAY_PARAMS) if arm == "B" else None,
    }
