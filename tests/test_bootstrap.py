"""Scene-level paired bootstrap, numpy only."""

import pytest

from proxy_eval.bootstrap import (
    paired_delta,
    per_scene_metric,
    scene_bootstrap,
)


def _frame(scene_token, value, metric="mAP_proxy"):
    return {"scene_token": scene_token, metric: value}


def test_per_scene_metric_means_frames_within_a_scene():
    frames = [
        _frame("scene-a", 0.2),
        _frame("scene-a", 0.4),
        _frame("scene-b", 1.0),
    ]

    result = per_scene_metric(frames, "mAP_proxy")

    assert result["scene-a"] == pytest.approx(0.3)
    assert result["scene-b"] == pytest.approx(1.0)


def test_per_scene_metric_of_no_frames_is_empty():
    assert per_scene_metric([], "mAP_proxy") == {}


def test_paired_delta_keeps_only_shared_scenes():
    a = {f"scene-{index}": float(index) for index in range(10)}
    b = {f"scene-{index}": 1.0 for index in range(10)}
    b["scene-only-in-b"] = 99.0

    result = paired_delta(a, b)

    assert set(result) == {f"scene-{index}" for index in range(10)}
    assert result["scene-9"] == pytest.approx(8.0)


def test_paired_delta_raises_below_eight_shared_scenes():
    a = {f"scene-{index}": 1.0 for index in range(7)}
    b = dict(a)

    with pytest.raises(ValueError) as excinfo:
        paired_delta(a, b)

    assert "7" in str(excinfo.value)


def test_paired_delta_accepts_exactly_eight_shared_scenes():
    a = {f"scene-{index}": float(index) for index in range(8)}
    b = {scene: 0.0 for scene in a}

    assert len(paired_delta(a, b)) == 8


def test_scene_bootstrap_is_deterministic_for_a_seed():
    deltas = {f"scene-{index}": float(index - 4) for index in range(16)}

    assert scene_bootstrap(deltas, n=500, seed=7) == scene_bootstrap(
        deltas, n=500, seed=7
    )


def test_scene_bootstrap_interval_contains_the_mean():
    deltas = {f"scene-{index}": (index - 8) / 10.0 for index in range(17)}

    result = scene_bootstrap(deltas, n=1000, seed=0)

    assert result["n_scenes"] == 17
    assert result["n_resamples"] == 1000
    assert result["mean"] == pytest.approx(
        sum(deltas.values()) / len(deltas)
    )
    assert result["lo"] <= result["mean"] <= result["hi"]


def test_scene_bootstrap_of_all_zero_deltas_is_zero_width():
    deltas = {f"scene-{index}": 0.0 for index in range(10)}

    result = scene_bootstrap(deltas, n=200, seed=0)

    assert result["mean"] == result["lo"] == result["hi"] == 0.0


def test_scene_bootstrap_rejects_no_scenes():
    with pytest.raises(ValueError):
        scene_bootstrap({}, n=10, seed=0)
