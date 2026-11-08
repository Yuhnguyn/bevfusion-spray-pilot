"""The A/B contract: the only difference is the plume transform.

These tests are the evidence that both arms share one training budget and one
data order, so a later comparison of mAP cannot be explained by anything except
the spray augmentation.
"""

import json

import pytest

from spray.ab_config import (
    SPRAY_CONFIG,
    SPRAY_PARAMS,
    TRAIN_SPEC,
    build_cfg,
    diff_paths,
    train_pipeline,
)
from spray.config_merge import load_yaml

KEEP = (
    "GlobalRotScaleTrans",
    "RandomFlip3D",
    "PointsRangeFilter",
    "ObjectRangeFilter",
    "PointShuffle",
)


def _types(steps):
    return [step["type"] for step in steps]


def test_diff_only_in_pipeline_and_spray():
    diff = diff_paths(build_cfg("A"), build_cfg("B"))

    # "arm" differs by definition (it is the arm label), everything else that
    # differs must be the pipeline itself or the spray block.
    assert set(diff) <= {"arm", "train_pipeline", "spray"}
    assert not any(path == "train_spec" or path.startswith("train_spec.") for path in diff)
    assert "model_config" not in diff


def test_train_spec_is_identical():
    assert build_cfg("A")["train_spec"] == build_cfg("B")["train_spec"]
    assert build_cfg("A")["train_spec"] == TRAIN_SPEC


def test_training_budget_values_are_shared():
    for key, value in TRAIN_SPEC.items():
        assert build_cfg("A")["train_spec"][key] == value
        assert build_cfg("B")["train_spec"][key] == value


def test_plume_only_in_arm_b_right_after_random_flip():
    a_types = _types(train_pipeline("A"))
    b_types = _types(train_pipeline("B"))

    assert "PlumeTransform" not in a_types
    assert b_types.count("PlumeTransform") == 1
    assert b_types.index("PlumeTransform") == b_types.index("RandomFlip3D") + 1


def test_pipelines_are_identical_except_plume_step():
    a_steps = train_pipeline("A")
    b_steps = [step for step in train_pipeline("B") if step["type"] != "PlumeTransform"]
    assert a_steps == b_steps


def test_keep_steps_present_in_order_and_resolved():
    for arm in ("A", "B"):
        steps = train_pipeline(arm)
        types = _types(steps)
        kept = [kind for kind in types if kind in KEEP]
        assert kept == list(KEEP)
        dumped = json.dumps(steps)
        assert "${" not in dumped, f"arm {arm} has an unresolved placeholder"


def test_clean_formatting_steps_in_both_arms():
    for arm in ("A", "B"):
        types = _types(train_pipeline(arm))
        assert "CleanPointsFormatBundle3D" in types
        assert "CleanPointsCollect3D" in types
        assert "DefaultFormatBundle3D" not in types
        assert "Collect3D" not in types
        assert types.index("CleanPointsFormatBundle3D") < types.index(
            "CleanPointsCollect3D"
        )


def test_plume_step_config_is_the_yaml_defaults():
    step = next(
        step for step in train_pipeline("B") if step["type"] == "PlumeTransform"
    )
    assert step["enabled"] is True
    assert step["seed"] == 0
    assert step["config"] == SPRAY_PARAMS
    assert step["config"] == load_yaml(SPRAY_CONFIG)


def test_spray_block_only_in_arm_b():
    assert build_cfg("A")["spray"] is None
    assert build_cfg("B")["spray"] == SPRAY_PARAMS


def test_build_cfg_is_json_serializable():
    for arm in ("A", "B"):
        dumped = json.dumps(build_cfg(arm))
        assert json.loads(dumped)["arm"] == arm


def test_unknown_arm_rejected():
    with pytest.raises(ValueError):
        build_cfg("C")
    with pytest.raises(ValueError):
        train_pipeline("a")
