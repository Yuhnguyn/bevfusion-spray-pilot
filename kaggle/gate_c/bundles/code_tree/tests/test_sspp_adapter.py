import json

import numpy as np
import pytest

from spray.sspp_adapter import (
    BOX_DIM,
    build_info,
    ego_speed_kmh,
    load_points,
    object_speed_kmh,
    read_frame_boxes,
    read_metadata,
)

# Values of the first box of Crafter_dynamic/0000 (docs/PROJECT.md §3a).
FIRST_BOX = {
    "instances": [
        {
            "id": "ffdd55aa",
            "type": "3D_BOX",
            "contour": {
                "center3D": {"x": 23.2387, "y": -0.1798, "z": 0.899},
                "pointN": 303,
                "rotation3D": {"x": 0, "y": 0, "z": -0.044},
                "size3D": {"x": 6.8268, "y": 2.4183, "z": 2.6206},
            },
            "className": "Van",
        }
    ]
}

METADATA = {
    "file_name": "2021-09-08-14-36-56_0.bag",
    "object_name": "Crafter",
    "object_velocity": "50",
    "object_direction": "1",
    "ego_velocity": "50",
    "distance_to_object": "20.0",
    "amb_tmp": "26.0",
    "unimod": "nan",
    "measurement_itr": "1",
    "itr_after_water": "1",
    "comment": "South wind",
}

REQUIRED_KEYS = {
    "token",
    "lidar_path",
    "sweeps",
    "timestamp",
    "location",
    "ego2global",
    "lidar2ego",
    "gt_boxes",
    "gt_names",
    "num_lidar_pts",
    "valid_flag",
    "ego_speed_kmh",
    "group",
    "scene",
    "scan_id",
}


def _make_scene(root, frames, metadata=None):
    """Write a fake scene; ``frames`` maps scan_id -> list of instances."""

    scene_dir = root / "Crafter_dynamic" / "0000_scene"
    (scene_dir / "object_labels" / "lidar").mkdir(parents=True)
    (scene_dir / "velodyne").mkdir()
    row = dict(metadata or METADATA)
    header = ",".join(row)
    values = ",".join(row[column] for column in row)
    (scene_dir / "metadata.txt").write_text(
        f"{header}\n{values}\n", encoding="utf-8"
    )
    for scan_id, instances in frames.items():
        entries = [{"instances": instances}]
        (scene_dir / "object_labels" / "lidar" / f"{scan_id}.json").write_text(
            json.dumps(entries), encoding="utf-8"
        )
        points = np.arange(10, dtype=np.float32).reshape(2, 5)
        (scene_dir / "velodyne" / f"{scan_id}.bin").write_bytes(
            points.tobytes()
        )
    return root, "Crafter_dynamic/0000_scene"


def _build(root, scan_id, instances, metadata=None, frame_index=None):
    root, rel_scene = _make_scene(root, {scan_id: instances}, metadata)
    return build_info(
        root,
        rel_scene,
        scan_id,
        read_metadata(root / rel_scene / "metadata.txt"),
        frame_index=frame_index,
    )


def test_first_box_conversion_matches_measured_values(tmp_path):
    info = _build(tmp_path, "000000", FIRST_BOX["instances"])

    box = info["gt_boxes"][0]
    assert box[2] == pytest.approx(-0.4113, abs=0.001)
    assert box[6] == pytest.approx(-0.044, abs=0.001)
    # no size swap: size3D.x -> length, size3D.y -> width
    assert box[3] == pytest.approx(6.8268, abs=1e-4)
    assert box[4] == pytest.approx(2.4183, abs=1e-4)
    assert box[5] == pytest.approx(2.6206, abs=1e-4)
    assert box[0] == pytest.approx(23.2387, abs=1e-4)
    assert box[1] == pytest.approx(-0.1798, abs=1e-4)


def test_box_speed_comes_from_metadata_and_is_zero_laterally(tmp_path):
    info = _build(tmp_path, "000000", FIRST_BOX["instances"])

    assert info["gt_boxes"][0, 7] == pytest.approx(50 / 3.6, abs=1e-5)
    assert info["gt_boxes"][0, 8] == pytest.approx(0.0, abs=1e-6)


def test_info_has_all_keys_and_dtypes(tmp_path):
    info = _build(tmp_path, "000000", FIRST_BOX["instances"])

    assert REQUIRED_KEYS <= set(info)
    assert info["token"] == "Crafter_dynamic/0000_scene/000000"
    assert info["lidar_path"] == (
        "Crafter_dynamic/0000_scene/velodyne/000000.bin"
    )
    assert info["sweeps"] == []
    assert info["timestamp"] == 0
    assert info["location"] == "Crafter_dynamic"
    assert info["group"] == "Crafter_dynamic"
    assert info["scene"] == "0000_scene"
    assert info["scan_id"] == "000000"
    assert info["ego_speed_kmh"] == pytest.approx(50.0)
    assert info["ego2global"].shape == (4, 4)
    assert info["ego2global"].dtype == np.float32
    assert info["lidar2ego"].shape == (4, 4)
    assert np.array_equal(info["ego2global"], np.eye(4, dtype=np.float32))
    assert np.array_equal(info["lidar2ego"], np.eye(4, dtype=np.float32))
    assert info["gt_boxes"].dtype == np.float32
    assert info["gt_names"].tolist() == ["Van"]
    assert info["num_lidar_pts"].tolist() == [303]
    assert info["valid_flag"].tolist() == [True]


def test_box_dim_is_nine(tmp_path):
    info = _build(tmp_path, "000000", FIRST_BOX["instances"])

    assert info["gt_boxes"].shape[1] == BOX_DIM == 9


def test_empty_frame_has_empty_boxes(tmp_path):
    info = _build(tmp_path, "000042", [])

    assert info["gt_boxes"].shape == (0, 9)
    assert info["gt_boxes"].dtype == np.float32
    assert info["gt_names"].shape == (0,)
    assert info["num_lidar_pts"].shape == (0,)
    assert info["valid_flag"].shape == (0,)
    assert info["valid_flag"].all() in (True, np.True_)
    assert info["lidar_path"].endswith("000042.bin")


def test_other_vehicle_and_non_3d_boxes_are_dropped(tmp_path):
    other = json.loads(json.dumps(FIRST_BOX["instances"][0]))
    other["className"] = "Other Vehicle"
    two_d = json.loads(json.dumps(FIRST_BOX["instances"][0]))
    two_d["type"] = "2D_BOX"
    car = json.loads(json.dumps(FIRST_BOX["instances"][0]))
    car["className"] = "Car"

    info = _build(tmp_path, "000000", [other, two_d, car, FIRST_BOX["instances"][0]])

    assert info["gt_names"].tolist() == ["Car", "Van"]
    assert info["gt_boxes"].shape == (2, 9)


def test_frame_index_overrides_timestamp(tmp_path):
    info = _build(tmp_path, "000007", FIRST_BOX["instances"], frame_index=99)

    assert info["timestamp"] == 99


def test_read_metadata_returns_columns(tmp_path):
    root, rel_scene = _make_scene(tmp_path, {"000000": []})

    row = read_metadata(root / rel_scene / "metadata.txt")

    assert row["object_velocity"] == "50"
    assert row["ego_velocity"] == "50"
    assert row["itr_after_water"] == "1"
    assert object_speed_kmh(row) == pytest.approx(50.0)
    assert ego_speed_kmh(row, 50.0) == pytest.approx(50.0)


def test_ego_speed_falls_back_to_object_speed(tmp_path):
    root, rel_scene = _make_scene(tmp_path, {"000000": []})
    metadata = dict(METADATA)
    del metadata["ego_velocity"]
    header = ",".join(metadata)
    values = ",".join(metadata[column] for column in metadata)
    (root / rel_scene / "metadata.txt").write_text(
        f"{header}\n{values}\n", encoding="utf-8"
    )

    row = read_metadata(root / rel_scene / "metadata.txt")

    assert "ego_velocity" not in row
    assert ego_speed_kmh(row, object_speed_kmh(row)) == pytest.approx(50.0)


def test_read_frame_boxes_keeps_file_order(tmp_path):
    root, rel_scene = _make_scene(tmp_path, {"000000": FIRST_BOX["instances"]})
    path = root / rel_scene / "object_labels" / "lidar" / "000000.json"

    boxes = read_frame_boxes(path)

    assert len(boxes) == 1
    assert boxes[0]["name"] == "Van"
    assert boxes[0]["num_lidar_pts"] == 303
    assert boxes[0]["z_bottom"] == pytest.approx(-0.4113, abs=1e-3)


def test_load_points_reads_five_columns(tmp_path):
    root, rel_scene = _make_scene(tmp_path, {"000000": FIRST_BOX["instances"]})
    info = build_info(
        root,
        rel_scene,
        "000000",
        read_metadata(root / rel_scene / "metadata.txt"),
    )

    points = load_points(info, root)

    assert points.shape == (2, 5)
    assert points.dtype == np.float32
    assert points[0, 0] == pytest.approx(0.0)
    assert points[1, 4] == pytest.approx(9.0)
