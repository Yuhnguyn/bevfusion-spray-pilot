"""Deterministic mini-train split and info validation, no devkit needed."""

import numpy as np
import pytest

from spray.mini_split import (
    load_camera_types,
    load_val_scenes,
    select_tokens,
    summarize,
    validate_info,
)

CAMERA_TYPES = load_camera_types()


def _samples(count=20, scenes=2):
    return [
        {"token": f"tok-{i:03d}", "scene_token": f"scene-{i % scenes}"}
        for i in range(count)
    ]


def _cam(name):
    return {
        "data_path": f"{name}.jpg",
        "sample_data_token": f"sd-{name}",
        "sensor2ego_translation": [0.0, 0.0, 0.0],
        "sensor2ego_rotation": [1.0, 0.0, 0.0, 0.0],
        "ego2global_translation": [0.0, 0.0, 0.0],
        "ego2global_rotation": [1.0, 0.0, 0.0, 0.0],
        "camera_intrinsics": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    }


def _info(token="tok-001", scene="scene-0001", names=("car", "pedestrian")):
    return {
        "token": token,
        "scene_token": scene,
        "timestamp": 1532402927647951,
        "lidar_path": "samples/LIDAR_TOP/lidar.pcd.bin",
        "sweeps": [
            {"data_path": "sweeps/LIDAR_TOP/a.pcd.bin"},
            {"data_path": "sweeps/LIDAR_TOP/b.pcd.bin"},
        ],
        "cams": {name: _cam(name) for name in CAMERA_TYPES},
        "gt_boxes": np.zeros((len(names), 7)),
        "gt_names": np.array(list(names)),
        "gt_velocity": np.zeros((len(names), 2)),
        "num_lidar_pts": np.ones(len(names), dtype=int),
        "num_radar_pts": np.zeros(len(names), dtype=int),
        "valid_flag": np.ones(len(names), dtype=bool),
    }


def test_select_tokens_is_seed_deterministic():
    samples = _samples(50)

    assert select_tokens(samples, 5, 0, frozenset()) == select_tokens(
        samples, 5, 0, frozenset()
    )
    assert select_tokens(samples, 5, 0, frozenset()) != select_tokens(
        samples, 5, 1, frozenset()
    )


def test_select_tokens_returns_n_unique_tokens():
    picked = select_tokens(_samples(50), 12, 7, frozenset())

    assert len(picked) == 12
    assert len(set(picked)) == 12


def test_select_tokens_drops_val_scenes():
    samples = _samples(40, scenes=2)

    picked = select_tokens(samples, 10, 3, frozenset({"scene-0"}))

    scene_of = {sample["token"]: sample["scene_token"] for sample in samples}
    assert all(scene_of[token] != "scene-0" for token in picked)
    assert len(picked) == 10


def test_select_tokens_output_sorted_and_order_independent():
    samples = _samples(40)

    forward = select_tokens(samples, 9, 11, frozenset())
    backward = select_tokens(list(reversed(samples)), 9, 11, frozenset())

    assert forward == sorted(forward)
    assert forward == backward


def test_select_tokens_more_than_candidates_raises_with_numbers():
    samples = _samples(6, scenes=2)

    with pytest.raises(ValueError) as excinfo:
        select_tokens(samples, 5, 0, frozenset({"scene-0"}))

    message = str(excinfo.value)
    assert "5" in message
    assert "3" in message


def test_validate_info_accepts_a_valid_info():
    assert validate_info(_info()) == []


def test_validate_info_reports_broken_infos():
    missing_cam = _info()
    missing_cam["cams"].pop(CAMERA_TYPES[0])
    errors = " ".join(validate_info(missing_cam))
    assert "missing camera" in errors
    assert CAMERA_TYPES[0] in errors

    bad_boxes = _info()
    bad_boxes["gt_boxes"] = np.zeros((2, 6))
    assert any("gt_boxes shape" in error for error in validate_info(bad_boxes))

    no_sweeps = _info()
    no_sweeps["sweeps"] = []
    assert any("sweeps_prev empty" in error for error in validate_info(no_sweeps))


def test_summarize_counts_three_infos():
    infos = [
        _info(token="tok-a", scene="scene-0001", names=("car", "pedestrian")),
        _info(token="tok-b", scene="scene-0001", names=()),
        _info(token="tok-c", scene="scene-0002", names=("car",)),
    ]

    summary = summarize(infos)

    assert summary["n_samples"] == 3
    assert summary["n_scenes"] == 2
    assert summary["gt_boxes_total"] == 3
    assert summary["per_class_counts"] == {"car": 2, "pedestrian": 1}
    assert summary["per_cam_count"] == {cam: 3 for cam in CAMERA_TYPES}


def test_load_val_scenes_reads_only_the_val_assignment(tmp_path):
    splits = tmp_path / "splits.py"
    splits.write_text(
        "train = ['scene-0009']\n"
        "val = [\n"
        "    'scene-0001',\n"
        "    'scene-0002',\n"
        "]\n"
        "test = []\n"
        "mini_val = ['scene-0003']\n"
    )

    assert load_val_scenes(splits) == frozenset({"scene-0001", "scene-0002"})


def test_load_val_scenes_raises_when_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_val_scenes(tmp_path / "does-not-exist.py")


def test_vendor_camera_channels_are_six_cam_entries():
    assert len(CAMERA_TYPES) == 6
    assert all(name.startswith("CAM_") for name in CAMERA_TYPES)
