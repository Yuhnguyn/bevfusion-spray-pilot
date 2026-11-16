"""Read one SemanticSpray++ frame as a BEVFusion ``info`` dict.

The info dict has the shape that
``mit/bevfusion/mmdet3d/datasets/nuscenes_dataset.py`` expects from
``get_data_info`` / ``get_ann_info``: ``token``, ``lidar_path``, ``sweeps``,
``timestamp``, ``location``, ``ego2global``, ``lidar2ego``, ``gt_boxes``,
``gt_names``, ``num_lidar_pts`` and ``valid_flag``.  No mmdet3d import is
needed: everything here is numpy plus the standard library.

Box conversion (``[ĐO]``, verified 2026-11-16 on 534 Car/Van boxes; see
``.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md`` step 2)::

    dims = (size3D.x, size3D.y, size3D.z)   # no swap
    yaw' = +rotation3D.z                    # same convention as mmdet, CCW from +x
    z'   = center3D.z - size3D.z / 2        # bottom of the box, not the centre

The earlier ``swap x<->y`` + ``yaw = -theta - pi/2`` rule is wrong: on the
three tilted boxes it drops the fraction of vehicle points inside the box
from 90-100 % to 73-87 %.  ``center3D.z`` as-is is wrong too (46.8 % instead
of 97.5 %) because the box would float half a height above the road.

Because velocity is already part of ``gt_boxes`` (columns 7-8), a config
using these infos must keep ``with_velocity=False``.  ``get_ann_info`` would
otherwise concatenate a second velocity pair and make the boxes 11-dim.

Points are already in the LiDAR frame and the dataset has a single sensor,
so ``lidar2ego`` and ``ego2global`` are identity matrices.  ``poses.txt``
carries no translation (``docs/PROJECT.md`` §3b), so there is no ego
displacement to encode either.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

CLASS_NAMES = ("Car", "Van")
BOX_DIM = 9
POINT_DIM = 5

# A frame JSON holds a list of entries, each with an ``instances`` list.
_BOX_TYPE = "3D_BOX"

_METADATA_VALUE_COLUMNS = ("object_velocity", "ego_velocity")


def read_metadata(metadata_path: str | Path) -> dict[str, str]:
    """Read ``metadata.txt`` (header line + one value line) as a dict."""

    with Path(metadata_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(
            f"{metadata_path}: expected exactly 1 data row, got {len(rows)}"
        )
    return {
        key.strip(): (value or "").strip()
        for key, value in rows[0].items()
        if key is not None
    }


def object_speed_kmh(metadata_row: dict[str, str]) -> float:
    """Object speed in km/h from the scene metadata; raises when missing."""

    value = metadata_row.get("object_velocity", "")
    if value == "":
        raise ValueError("metadata.txt is missing object_velocity")
    return float(value)


def ego_speed_kmh(
    metadata_row: dict[str, str], object_kmh: float
) -> float:
    """Ego speed in km/h, falling back to the object speed.

    ``object_velocity == ego_velocity`` in all 207 scenes (``docs/PROJECT.md``
    §3c), so the fallback only matters if the column is ever dropped.
    """

    value = metadata_row.get("ego_velocity", "")
    if value == "":
        return float(object_kmh)
    return float(value)


def read_frame_boxes(json_path: str | Path) -> list[dict]:
    """Car/Van ``3D_BOX`` instances of one frame, in file order.

    ``Other Vehicle`` boxes are dropped: the detection domain has two classes
    only (``docs/PROJECT.md`` §2).  Each dict carries the converted geometry,
    the class name and ``pointN``, which becomes ``num_lidar_pts``.
    """

    entries = json.loads(Path(json_path).read_text(encoding="utf-8"))
    boxes: list[dict] = []
    for entry in entries:
        for instance in entry.get("instances") or []:
            if instance.get("type") != _BOX_TYPE:
                continue
            name = instance.get("className")
            if name not in CLASS_NAMES:
                continue
            contour = instance["contour"]
            center = contour["center3D"]
            size = contour["size3D"]
            rotation = contour["rotation3D"]
            size_z = float(size["z"])
            boxes.append(
                {
                    "name": name,
                    "x": float(center["x"]),
                    "y": float(center["y"]),
                    "z_bottom": float(center["z"]) - size_z / 2.0,
                    "size_x": float(size["x"]),
                    "size_y": float(size["y"]),
                    "size_z": size_z,
                    "yaw": float(rotation["z"]),
                    "num_lidar_pts": int(contour["pointN"]),
                }
            )
    return boxes


def _boxes_to_arrays(
    boxes: list[dict], speed_mps: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not boxes:
        return (
            np.zeros((0, BOX_DIM), dtype=np.float32),
            np.zeros(0, dtype="<U16"),
            np.zeros(0, dtype=np.int64),
        )
    rows = [
        [
            box["x"],
            box["y"],
            box["z_bottom"],
            box["size_x"],
            box["size_y"],
            box["size_z"],
            box["yaw"],
            speed_mps,
            0.0,
        ]
        for box in boxes
    ]
    return (
        np.asarray(rows, dtype=np.float32),
        np.asarray([box["name"] for box in boxes]),
        np.asarray([box["num_lidar_pts"] for box in boxes], dtype=np.int64),
    )


def build_info(
    dataset_root: str | Path,
    rel_scene: str,
    scan_id: str | int,
    metadata_row: dict[str, str],
    frame_index: int | None = None,
) -> dict:
    """Build the info dict of one frame.

    Args:
        dataset_root: directory holding ``Crafter_dynamic`` / ``Golf_dynamic``.
        rel_scene: ``"<group>/<scene>"``.
        scan_id: frame stem, e.g. ``"000000"``.
        metadata_row: one row of the scene's ``metadata.txt``.
        frame_index: value used as ``timestamp``.  The split builder passes a
            global running index because ``load_annotations`` sorts the whole
            list by ``timestamp``; without it, frames of different scenes
            would interleave.  Defaults to ``int(scan_id)``, which is already
            increasing inside a scene.
    """

    dataset_root = Path(dataset_root)
    rel_scene = rel_scene.strip("/")
    scan_id = str(scan_id)
    group = rel_scene.split("/")[0]

    boxes_path = (
        dataset_root / rel_scene / "object_labels" / "lidar" / f"{scan_id}.json"
    )
    boxes = read_frame_boxes(boxes_path)

    object_kmh = object_speed_kmh(metadata_row)
    ego_kmh = ego_speed_kmh(metadata_row, object_kmh)
    speed_mps = object_kmh / 3.6

    gt_boxes, gt_names, num_lidar_pts = _boxes_to_arrays(boxes, speed_mps)

    return {
        "token": f"{rel_scene}/{scan_id}",
        "lidar_path": f"{rel_scene}/velodyne/{scan_id}.bin",
        "sweeps": [],
        "timestamp": int(scan_id) if frame_index is None else int(frame_index),
        "location": group,
        "ego2global": np.eye(4, dtype=np.float32),
        "lidar2ego": np.eye(4, dtype=np.float32),
        "ego2global_rotation": [1.0, 0.0, 0.0, 0.0],
        "ego2global_translation": [0.0, 0.0, 0.0],
        "lidar2ego_rotation": [1.0, 0.0, 0.0, 0.0],
        "lidar2ego_translation": [0.0, 0.0, 0.0],
        "gt_boxes": gt_boxes,
        "gt_names": gt_names,
        "num_lidar_pts": num_lidar_pts,
        "valid_flag": np.ones(gt_boxes.shape[0], dtype=bool),
        "ego_speed_kmh": ego_kmh,
        "group": group,
        "scene": rel_scene.split("/")[-1],
        "scan_id": scan_id,
    }


def load_points(info: dict, dataset_root: str | Path) -> np.ndarray:
    """Read ``info["lidar_path"]`` as an ``(N, 5)`` float32 array.

    The file is ``x, y, z, intensity, ring``.  Spray points (``labels == 2``)
    are **not** filtered here: dropping them is the training pipeline's job.
    """

    path = Path(dataset_root) / info["lidar_path"]
    raw = np.fromfile(path, dtype=np.float32)
    if raw.size % POINT_DIM:
        raise ValueError(
            f"{path}: {raw.size} floats is not a multiple of {POINT_DIM}"
        )
    return raw.reshape(-1, POINT_DIM)
