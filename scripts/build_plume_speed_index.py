#!/usr/bin/env python3
"""Build the per-frame speed sidecar used by ``SprayContextTransform``.

nuScenes infos (MIT ``create_data.py``) carry ``scene_token``, ``timestamp``
and ``ego2global_translation`` but no speeds. The plume needs
``ego_speed_mps`` and ``object_speed_mps`` per frame, so this script derives
them offline and writes one JSON keyed by ``lidar_path``:

    {lidar_path: {"ego_speed_mps": ..., "object_speed_mps": ...,
                  "scene_token": ..., "frame_index": ...}}

Keying by ``lidar_path`` makes the lookup safe under ``ShuffleDataset``: the
transform never depends on the order frames are visited at training time.

``ego_speed_mps = ||t_{k+1} - t_k|| / dt`` from the ego translations of two
consecutive *keyframes* of the same scene, sorted by ``timestamp``. The last
frame of a scene has no successor, so it reuses the previous frame's speed.

``object_speed_mps = ego_speed_mps`` has a measured basis: ticket 25 compared
the two on all 207 SemanticSpray scenes and found them equal (the lead vehicle
runs at the ego speed in that dataset). nuScenes itself does not report the
lead vehicle's speed, so the sidecar cannot do better than this.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import pickle

import numpy as np

DEFAULT_OUT = pathlib.Path("data/plume_speed_index.json")


def load_infos(path: pathlib.Path) -> list[dict]:
    """Return the info list from a ``nuscenes_infos_*.pkl`` file."""
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if isinstance(payload, dict):
        infos = payload.get("infos")
        if infos is None:
            raise ValueError(f"{path}: dict payload has no 'infos' key")
    else:
        infos = payload
    return list(infos)


def _translation(info: dict) -> np.ndarray:
    try:
        value = info["ego2global_translation"]
    except KeyError as exc:
        raise KeyError(
            "ego2global_translation missing from an info record"
        ) from exc
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,) or not np.isfinite(array).all():
        raise ValueError(f"ego2global_translation must be finite (3,), got {array}")
    return array


def build_index(infos: list[dict]) -> dict[str, dict]:
    """Group infos by scene, sort by timestamp and derive per-frame speeds."""
    scenes: dict[str, list[tuple[int, dict]]] = {}
    for info in infos:
        scene_token = info.get("scene_token")
        if not isinstance(scene_token, str) or not scene_token:
            raise KeyError(
                "scene_token missing from an info record (rebuild the pkl with "
                "scripts/make_mini_split.py or add it before running this script)"
            )
        timestamp = info.get("timestamp")
        if timestamp is None:
            raise KeyError("timestamp missing from an info record")
        lidar_path = info.get("lidar_path")
        if not isinstance(lidar_path, str) or not lidar_path:
            raise KeyError("lidar_path missing from an info record")
        scenes.setdefault(scene_token, []).append((int(timestamp), info))

    index: dict[str, dict] = {}
    for scene_token, rows in scenes.items():
        rows.sort(key=lambda row: row[0])
        speeds = np.zeros(len(rows), dtype=np.float64)
        for position in range(len(rows) - 1):
            timestamp, info = rows[position]
            next_timestamp, next_info = rows[position + 1]
            delta_s = (next_timestamp - timestamp) / 1e6
            if delta_s <= 0.0:
                raise ValueError(
                    f"scene {scene_token}: non-increasing timestamps "
                    f"({timestamp} then {next_timestamp})"
                )
            displacement = _translation(next_info) - _translation(info)
            speeds[position] = float(np.linalg.norm(displacement) / delta_s)
        if len(rows) > 1:
            speeds[-1] = speeds[-2]
        for position, (_, info) in enumerate(rows):
            speed = float(speeds[position])
            index[info["lidar_path"]] = {
                "ego_speed_mps": speed,
                "object_speed_mps": speed,
                "scene_token": scene_token,
                "frame_index": position,
            }
    return index


def merge_indices(indices: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for index in indices:
        overlap = merged.keys() & index.keys()
        if overlap:
            raise ValueError(
                f"{len(overlap)} lidar_path keys appear in more than one infos "
                "file; pass disjoint splits"
            )
        merged.update(index)
    return merged


def write_index(index: dict[str, dict], out: pathlib.Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "infos",
        nargs="+",
        type=pathlib.Path,
        help="nuscenes_infos_*.pkl files (disjoint splits)",
    )
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    index = merge_indices([build_index(load_infos(path)) for path in args.infos])
    write_index(index, args.out)
    scenes = len({entry["scene_token"] for entry in index.values()})
    print(
        f"PLUME_SPEED_INDEX frames={len(index)} scenes={scenes} out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
