"""Eval-set selection (196 val frames / 16 scenes), no devkit needed."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "scripts/make_eval_split.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("make_eval_split", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


eval_split = _load_module()


def _box(class_="car", speed_kmh=60.0, d_m=30.0, x=10.0):
    return {"class": class_, "speed_kmh": speed_kmh, "d_m": d_m, "x": x}


def _frame(token, scene, scene_token, boxes, split="val"):
    return {
        "sample_token": token,
        "scene": scene,
        "scene_token": scene_token,
        "split": split,
        "boxes": boxes,
    }


@pytest.mark.parametrize("speed_kmh,expected", [(49.9, False), (50.0, True)])
def test_speed_threshold(speed_kmh, expected):
    assert bool(eval_split.eligible([_box(speed_kmh=speed_kmh)])) is expected


@pytest.mark.parametrize("d_m,expected", [(50.0, True), (50.1, False)])
def test_distance_threshold(d_m, expected):
    assert bool(eval_split.eligible([_box(d_m=d_m)])) is expected


def test_box_behind_the_sensor_is_not_eligible():
    assert eval_split.eligible([_box(x=-0.1)]) == []


def test_non_vehicle_class_is_not_eligible():
    assert eval_split.eligible([_box(class_="pedestrian")]) == []


def test_eligible_keeps_only_passing_boxes():
    passing = _box()
    boxes = [passing, _box(class_="pedestrian"), _box(speed_kmh=49.9)]

    assert eval_split.eligible(boxes) == [passing]


def test_frame_distance_is_min_bev_distance_to_the_corners():
    corners = np.array(
        [[3.0, 4.0], [-3.0, -4.0], [1.0, 1.0], [0.0, 2.0]]
    )

    distance = eval_split.frame_distance(corners, [0.0, 0.0])

    assert distance == pytest.approx(np.hypot(1.0, 1.0))


def test_frame_distance_ignores_z_and_uses_the_origin():
    corners = np.array([[3.0, 4.0, 100.0], [-3.0, -4.0, -50.0]])

    assert eval_split.frame_distance(corners, [3.0, 0.0]) == pytest.approx(4.0)


def test_select_frames_keeps_only_val_frames_with_an_eligible_box():
    records = [
        _frame("s1", "scene-0001", "tok-a", [_box()]),
        _frame("s2", "scene-0001", "tok-a", [_box(class_="pedestrian")]),
        _frame("s3", "scene-0002", "tok-b", []),
        _frame("s4", "scene-0003", "tok-c", [_box()], split="train"),
    ]

    picked = eval_split.select_frames(records)

    assert [frame["sample_token"] for frame in picked] == ["s1"]
    assert picked[0]["n_eligible"] == 1
    assert set(picked[0]) == {"sample_token", "scene_token", "scene", "n_eligible"}


def test_select_frames_counts_frames_scenes_and_eligible_boxes():
    records = [
        _frame("s1", "scene-0001", "tok-a", [_box(), _box(d_m=10.0)]),
        _frame("s2", "scene-0001", "tok-a", [_box()]),
        _frame("s3", "scene-0002", "tok-b", [_box(speed_kmh=49.0)]),
        _frame("s4", "scene-0002", "tok-b", [_box()]),
        _frame("s5", "scene-0003", "tok-c", [_box()], split="train"),
    ]

    picked = eval_split.select_frames(records)

    assert {frame["sample_token"] for frame in picked} == {"s1", "s2", "s4"}
    assert {frame["scene"] for frame in picked} == {"scene-0001", "scene-0002"}
    assert sum(frame["n_eligible"] for frame in picked) == 4
    assert next(f for f in picked if f["sample_token"] == "s1")["n_eligible"] == 2


def test_selftest_passes():
    assert eval_split.selftest() is True
