#!/usr/bin/env python3
"""Select the fixed evaluation set from the nuScenes val split.

The evaluation set is the one agreed after the eligibility scan:

* ``split == val`` (``nuscenes.utils.splits.val``, 150 scenes)
* a vehicle-class box
  (``bicycle, bus, car, construction_vehicle, motorcycle, trailer, truck``)
* box speed ``>= 50 km/h``
* box center in front of the LiDAR (``x > 0`` in the LiDAR frame)
* min BEV distance from the LiDAR origin to the box footprint ``<= 50 m``

That definition yields **196 frames over 16 scenes**.  Real mode needs the
nuScenes devkit (Kaggle only)::

    python scripts/make_eval_split.py \
        --dataroot /kaggle/input/... --out /kaggle/working/eval_196.json

Local mode needs no devkit or dataset::

    python scripts/make_eval_split.py --selftest

The math mirrors ``kaggle/eligibility/main.py`` (the scan that produced
``kaggle/smoke_test/evidence/eligibility.json``) so both agree on the count.
It only walks the 150 val scenes, never the full ~28k keyframes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

VEHICLE_CLASSES = frozenset(
    {
        "bicycle",
        "bus",
        "car",
        "construction_vehicle",
        "motorcycle",
        "trailer",
        "truck",
    }
)
NAME_MAPPING = {
    "vehicle.car": "car",
    "vehicle.truck": "truck",
    "vehicle.trailer": "trailer",
    "vehicle.bus.bendy": "bus",
    "vehicle.bus.rigid": "bus",
    "vehicle.construction": "construction_vehicle",
    "vehicle.bicycle": "bicycle",
    "vehicle.motorcycle": "motorcycle",
}

BOX_SPEED_KMH = 50.0
MAX_DISTANCE_M = 50.0
EPS = 1e-9
EXPECTED_FRAMES = 196
EXPECTED_SCENES = 16

__all__ = [
    "BOX_SPEED_KMH",
    "EXPECTED_FRAMES",
    "EXPECTED_SCENES",
    "MAX_DISTANCE_M",
    "VEHICLE_CLASSES",
    "eligible",
    "frame_distance",
    "select_frames",
    "selftest",
    "summarize",
]


def eligible(boxes):
    """Return the boxes that pass every eval-set filter.

    A box is a mapping with ``class``, ``speed_kmh``, ``d_m`` and ``x``
    (the center's LiDAR x coordinate).  Boundaries are inclusive: exactly
    50 km/h and exactly 50 m pass; ``x`` must be strictly positive.
    """
    passing = []
    for box in boxes:
        if box.get("class") not in VEHICLE_CLASSES:
            continue

        speed = float(box["speed_kmh"])
        if not math.isfinite(speed) or speed < BOX_SPEED_KMH - EPS:
            continue

        if float(box["x"]) <= 0.0:
            continue

        distance = float(box["d_m"])
        if not math.isfinite(distance) or distance > MAX_DISTANCE_M + EPS:
            continue

        passing.append(box)
    return passing


def frame_distance(corners, origin):
    """Min BEV distance from ``origin`` to any corner, ignoring z."""
    points = np.asarray(corners, dtype=np.float64)
    if points.ndim != 2 or points.shape[0] == 0 or points.shape[1] < 2:
        raise ValueError("corners must have shape (N, 2) or (N, 3)")
    origin_xy = np.asarray(origin, dtype=np.float64)[:2]
    return float(np.min(np.linalg.norm(points[:, :2] - origin_xy, axis=1)))


def select_frames(records):
    """Keep val frames with at least one eligible box, as output rows.

    ``records`` are frame dicts carrying ``sample_token``, ``scene``,
    ``scene_token``, ``split`` and ``boxes``.  The output rows drop the boxes
    and keep only what the kernel needs to join metrics back to a scene.
    """
    selected = []
    for record in records:
        if record.get("split") != "val":
            continue
        passing = eligible(record.get("boxes", ()))
        if not passing:
            continue
        selected.append(
            {
                "sample_token": record["sample_token"],
                "scene_token": record["scene_token"],
                "scene": record["scene"],
                "n_eligible": len(passing),
            }
        )
    return selected


def summarize(frames):
    """Frame and scene counts for the log marker and JSON payload."""
    return {
        "frames": len(frames),
        "scenes": len({frame["scene_token"] for frame in frames}),
    }


def _quat_to_rot(quaternion):
    w, x, y, z = (float(value) for value in quaternion)
    norm = w * w + x * x + y * y + z * z
    if norm < EPS:
        return np.eye(3)
    scale = 2.0 / norm
    wx, wy, wz = scale * w * x, scale * w * y, scale * w * z
    xx, xy, xz = scale * x * x, scale * x * y, scale * x * z
    yy, yz, zz = scale * y * y, scale * y * z, scale * z * z
    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1.0 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1.0 - (xx + yy)],
        ]
    )


def _make_geo(pose, calibrated_sensor):
    return (
        _quat_to_rot(pose["rotation"]),
        np.asarray(pose["translation"], dtype=np.float64),
        _quat_to_rot(calibrated_sensor["rotation"]),
        np.asarray(calibrated_sensor["translation"], dtype=np.float64),
    )


def _to_lidar(points_global, geo):
    pose_rotation, pose_translation, sensor_rotation, sensor_translation = geo
    ego = pose_rotation.T @ (points_global - pose_translation[:, None])
    return sensor_rotation.T @ (ego - sensor_translation[:, None])


def _box_corners(center, size, rotation):
    width, length, height = (float(value) for value in size)
    x = length / 2.0 * np.array([1, 1, 1, 1, -1, -1, -1, -1], dtype=np.float64)
    y = width / 2.0 * np.array([1, -1, -1, 1, 1, -1, -1, 1], dtype=np.float64)
    z = height / 2.0 * np.array([1, 1, -1, -1, 1, 1, -1, -1], dtype=np.float64)
    local = np.vstack((x, y, z))
    return _quat_to_rot(rotation) @ local + np.asarray(
        center, dtype=np.float64
    )[:, None]


def _frame_boxes(nusc, annotations, geo):
    boxes = []
    for annotation in annotations:
        category = annotation["category_name"]
        if category not in NAME_MAPPING:
            continue

        velocity = np.asarray(nusc.box_velocity(annotation["token"]), dtype=np.float64)
        if not np.all(np.isfinite(velocity)):
            continue
        speed_kmh = float(np.linalg.norm(velocity)) * 3.6
        if speed_kmh < BOX_SPEED_KMH - EPS:
            continue

        center_lidar = _to_lidar(
            np.asarray(annotation["translation"], dtype=np.float64)[:, None], geo
        )[:, 0]
        if center_lidar[0] <= 0.0:
            continue

        corners_lidar = _to_lidar(
            _box_corners(
                annotation["translation"],
                annotation["size"],
                annotation["rotation"],
            ),
            geo,
        )
        boxes.append(
            {
                "class": NAME_MAPPING[category],
                "speed_kmh": round(speed_kmh, 3),
                "d_m": round(frame_distance(corners_lidar.T, [0.0, 0.0]), 3),
                "x": float(center_lidar[0]),
            }
        )
    return boxes


def scan_val_frames(nusc, val_scenes):
    """Walk only the val scenes and return frame records (devkit needed)."""
    records = []
    for scene in nusc.scene:
        if scene["name"] not in val_scenes:
            continue
        token = scene["first_sample_token"]
        while token:
            sample = nusc.get("sample", token)
            lidar = nusc.get("sample_data", sample["data"]["LIDAR_TOP"])
            pose = nusc.get("ego_pose", lidar["ego_pose_token"])
            calibrated = nusc.get(
                "calibrated_sensor", lidar["calibrated_sensor_token"]
            )
            geo = _make_geo(pose, calibrated)
            annotations = [
                nusc.get("sample_annotation", ann_token)
                for ann_token in sample["anns"]
            ]
            boxes = _frame_boxes(nusc, annotations, geo)
            if boxes:
                records.append(
                    {
                        "sample_token": sample["token"],
                        "scene": scene["name"],
                        "scene_token": scene["token"],
                        "split": "val",
                        "boxes": boxes,
                    }
                )
            token = sample["next"]
    return records


def selftest():
    """Boundary checks on synthetic boxes; no devkit or dataset required."""

    def box(class_="car", speed_kmh=60.0, d_m=30.0, x=10.0):
        return {"class": class_, "speed_kmh": speed_kmh, "d_m": d_m, "x": x}

    assert len(eligible([box(speed_kmh=50.0)])) == 1
    assert eligible([box(speed_kmh=49.9)]) == []
    assert len(eligible([box(d_m=50.0)])) == 1
    assert eligible([box(d_m=50.1)]) == []
    assert eligible([box(x=-0.1)]) == []
    assert eligible([box(class_="pedestrian")]) == []
    assert frame_distance([[3.0, 4.0], [-3.0, -4.0]], [0.0, 0.0]) == 5.0

    records = [
        {
            "sample_token": "s1",
            "scene": "scene-0001",
            "scene_token": "tok-a",
            "split": "val",
            "boxes": [box(), box(d_m=10.0), box(speed_kmh=49.9)],
        },
        {
            "sample_token": "s2",
            "scene": "scene-0002",
            "scene_token": "tok-b",
            "split": "train",
            "boxes": [box()],
        },
    ]
    picked = select_frames(records)
    assert len(picked) == 1
    assert picked[0]["sample_token"] == "s1"
    assert picked[0]["n_eligible"] == 2
    return True


def _parse_check(value):
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--check must look like 196,16")
    try:
        frames, scenes = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--check must look like 196,16") from exc
    return frames, scenes


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataroot", help="nuScenes root (real mode)")
    parser.add_argument("--out", help="output eval-set JSON path (real mode)")
    parser.add_argument("--version", default="v1.0-trainval")
    parser.add_argument(
        "--check",
        type=_parse_check,
        default=(EXPECTED_FRAMES, EXPECTED_SCENES),
        help="expected frames,scenes (default: 196,16)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run pure boundary checks without the devkit",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.selftest:
        selftest()
        print("EVAL_SET_SELFTEST_OK")
        return 0

    if not args.dataroot or not args.out:
        print("EVAL_SET_FAILED missing --dataroot/--out", file=sys.stderr)
        return 1

    expected_frames, expected_scenes = args.check

    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.splits import val as val_names

    nusc = NuScenes(
        version=args.version, dataroot=args.dataroot, verbose=False
    )
    selected = select_frames(scan_val_frames(nusc, set(val_names)))
    got = summarize(selected)

    payload = {
        "frames": selected,
        "expected": {"frames": expected_frames, "scenes": expected_scenes},
        "got": got,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        json.dump(payload, handle, indent=1)
        handle.write("\n")

    if got["frames"] == expected_frames and got["scenes"] == expected_scenes:
        print(f"EVAL_SET_OK frames={got['frames']} scenes={got['scenes']}")
        return 0

    print(
        f"EVAL_SET_FAILED expected={expected_frames},{expected_scenes} "
        f"got={got['frames']},{got['scenes']}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
