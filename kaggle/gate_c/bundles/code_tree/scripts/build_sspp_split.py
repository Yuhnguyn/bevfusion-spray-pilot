#!/usr/bin/env python3
"""Build the SemanticSpray++ train/val/test split and per-frame info pickles.

The split is by object speed so the test speeds are unseen in training
(``docs/PROJECT.md`` §3, ADR-0005):

    train = {60, 80, 100, 120}   val = {70, 110}   test = {50, 90, 130}

Writes ``data/sspp_infos_{split}.pkl`` (a ``list`` of info dicts, one per
frame) and ``data/sspp_split.json`` (scenes and frame counts per split).
An info dict is the per-frame mapping ``NuScenesDataset.get_data_info`` and
``get_ann_info`` consume; wrapping the list as ``{"infos": ..., "metadata":
...}`` is left to the training step.

Run with::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
        scripts/build_sspp_split.py
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from spray.sspp_adapter import (  # noqa: E402
    BOX_DIM,
    build_info,
    read_frame_boxes,
    read_metadata,
)

GROUPS = ("Crafter_dynamic", "Golf_dynamic")
SPLIT_BY_VELOCITY = {
    "train": (60, 80, 100, 120),
    "val": (70, 110),
    "test": (50, 90, 130),
}
KNOWN_VELOCITIES = {v for values in SPLIT_BY_VELOCITY.values() for v in values}

EXPECTED_SCENES = 36
EXPECTED_FRAMES = 2587

REPORTED_COLUMNS = (
    "object_velocity",
    "ego_velocity",
    "distance_to_object",
    "itr_after_water",
)

SELF_CHECK_SCENE = "Crafter_dynamic/0000_2021-09-08-14-36-56_0"
SELF_CHECK_SCAN = "000000"
SELF_CHECK_Z_BOTTOM = -0.4113
SELF_CHECK_YAW = -0.044
SELF_CHECK_TOL = 0.001


def discover_scenes(dataset_root: Path) -> list[tuple[str, Path]]:
    """Every ``<group>/<scene>`` directory, sorted by relative path."""

    scenes: list[tuple[str, Path]] = []
    for group in GROUPS:
        group_dir = dataset_root / group
        if not group_dir.is_dir():
            raise FileNotFoundError(f"missing dataset group: {group_dir}")
        for scene_dir in sorted(group_dir.iterdir(), key=lambda p: p.name):
            if scene_dir.is_dir():
                scenes.append((f"{group}/{scene_dir.name}", scene_dir))
    return scenes


def frame_scan_ids(scene_dir: Path) -> list[str]:
    """Scan ids of the frames holding at least one Car/Van ``3D_BOX``."""

    labels_dir = scene_dir / "object_labels" / "lidar"
    if not labels_dir.is_dir():
        return []
    return [
        path.stem
        for path in sorted(labels_dir.glob("*.json"), key=lambda p: p.name)
        if read_frame_boxes(path)
    ]


def split_for_velocity(velocity_kmh: int) -> str:
    for split, velocities in SPLIT_BY_VELOCITY.items():
        if velocity_kmh in velocities:
            return split
    raise ValueError(f"unexpected object_velocity: {velocity_kmh} km/h")


def main() -> int:
    dataset_root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "SemanticSprayDataset"
    data_dir = REPO / "data"

    scene_frames: dict[str, list[str]] = {}
    for rel_scene, scene_dir in discover_scenes(dataset_root):
        scan_ids = frame_scan_ids(scene_dir)
        if scan_ids:
            scene_frames[rel_scene] = scan_ids

    total_frames = sum(len(ids) for ids in scene_frames.values())
    print(
        f"SSPP_SCAN scenes={len(scene_frames)} frames={total_frames}",
        flush=True,
    )
    if len(scene_frames) != EXPECTED_SCENES or total_frames != EXPECTED_FRAMES:
        print(
            f"SSPP_SPLIT_MISMATCH expected scenes={EXPECTED_SCENES} "
            f"frames={EXPECTED_FRAMES}, measured scenes={len(scene_frames)} "
            f"frames={total_frames}",
            flush=True,
        )
        return 1

    metadata_columns: set[str] = set()
    scene_splits: dict[str, str] = {}
    velocities: dict[int, list[str]] = {}
    for rel_scene in sorted(scene_frames):
        scene_dir = dataset_root / rel_scene
        metadata_path = scene_dir / "metadata.txt"
        row = read_metadata(metadata_path)
        metadata_columns.update(row)
        missing = [c for c in REPORTED_COLUMNS if c not in row]
        if missing:
            print(
                f"SSPP_SPLIT_MISSING_COLUMNS scene={rel_scene} "
                f"columns={','.join(missing)}",
                flush=True,
            )
        if "object_velocity" not in row:
            print(f"SSPP_SPLIT_MISSING_VELOCITY scene={rel_scene}", flush=True)
            return 1
        velocity = int(round(float(row["object_velocity"])))
        velocities.setdefault(velocity, []).append(rel_scene)
        try:
            scene_splits[rel_scene] = split_for_velocity(velocity)
        except ValueError as exc:
            print(f"SSPP_SPLIT_UNKNOWN_VELOCITY scene={rel_scene}: {exc}", flush=True)
            return 1

    print(
        "SSPP_COLUMNS present="
        + ",".join(c for c in REPORTED_COLUMNS if c in metadata_columns)
        + " absent="
        + ",".join(c for c in REPORTED_COLUMNS if c not in metadata_columns),
        flush=True,
    )
    for velocity in sorted(velocities):
        print(
            f"SSPP_VELOCITY kmh={velocity} scenes={len(velocities[velocity])}",
            flush=True,
        )

    infos: dict[str, list[dict]] = {split: [] for split in SPLIT_BY_VELOCITY}
    for rel_scene in sorted(scene_frames):
        row = read_metadata(dataset_root / rel_scene / "metadata.txt")
        split = scene_splits[rel_scene]
        for scan_id in scene_frames[rel_scene]:
            info = build_info(
                dataset_root, rel_scene, scan_id, row, len(infos[split])
            )
            if info["gt_boxes"].shape[1] != BOX_DIM:
                raise AssertionError(
                    f"{info['token']}: box_dim={info['gt_boxes'].shape[1]}"
                )
            infos[split].append(info)

    scene_counts = {split: 0 for split in SPLIT_BY_VELOCITY}
    for rel_scene, split in scene_splits.items():
        scene_counts[split] += 1
    frame_counts = {split: len(items) for split, items in infos.items()}

    data_dir.mkdir(parents=True, exist_ok=True)
    for split, items in infos.items():
        path = data_dir / f"sspp_infos_{split}.pkl"
        with path.open("wb") as handle:
            pickle.dump(items, handle, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"SSPP_WROTE {path.name} frames={len(items)}")

    split_doc = {
        "split": {
            split: sorted(
                rel_scene
                for rel_scene, value in scene_splits.items()
                if value == split
            )
            for split in SPLIT_BY_VELOCITY
        },
        "scene_counts": scene_counts,
        "frame_counts": frame_counts,
        "velocity_kmh": {
            split: list(values) for split, values in SPLIT_BY_VELOCITY.items()
        },
    }
    split_path = data_dir / "sspp_split.json"
    split_path.write_text(
        json.dumps(split_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"SSPP_WROTE {split_path.name}")

    check_info = next(
        (
            info
            for split_items in infos.values()
            for info in split_items
            if info["token"] == f"{SELF_CHECK_SCENE}/{SELF_CHECK_SCAN}"
        ),
        None,
    )
    if check_info is None:
        print(f"SSPP_SELFCHECK missing token={SELF_CHECK_SCENE}/{SELF_CHECK_SCAN}")
        return 1
    z_bottom = float(check_info["gt_boxes"][0, 2])
    yaw = float(check_info["gt_boxes"][0, 6])
    ok = (
        abs(z_bottom - SELF_CHECK_Z_BOTTOM) <= SELF_CHECK_TOL
        and abs(yaw - SELF_CHECK_YAW) <= SELF_CHECK_TOL
    )
    print(
        f"SSPP_SELFCHECK token={check_info['token']} "
        f"z_bottom={z_bottom:.4f} expected={SELF_CHECK_Z_BOTTOM} "
        f"yaw={yaw:.4f} expected={SELF_CHECK_YAW} ok={ok}",
        flush=True,
    )
    if not ok:
        return 1

    marker_counts = {
        split: scene_counts[split] for split in sorted(scene_counts)
    }
    print(
        f"SSPP_SPLIT_OK scenes={len(scene_splits)} frames={total_frames} "
        f"{json.dumps(marker_counts)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
