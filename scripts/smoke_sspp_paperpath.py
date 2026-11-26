#!/usr/bin/env python3
"""Run the paper's full spray simulation chain on SemanticSpray++ info dicts.

The chain is exactly the one in ``spec-v2-paper-faithful.md``:

    clean points -> wet ground -> stateful clusters -> beam ray casting

and every stage is an existing function of ``spray/``; nothing in the generator
is modified here. This script only wires the stages in the paper's order and
reports the counters so a smoke run can be checked.

Per frame:

1. ``points`` from ``info["lidar_path"]``; ``clean = points[labels != 2]``
   (label 2 is "spray and other noise", so the augmentation starts from a
   spray-free cloud);
2. ``PlumeContext`` with ``ego_speed_mps`` from ``info["ego_speed_kmh"]``,
   ``object_speed_mps`` from ``gt_boxes`` column 7, ``wfh_mm = 1.0``
   (``[CHỌN]``: the dataset does not declare wetness) and ``road_z_m`` = the
   median box bottom of that frame;
3. ``inject_plume_stateful`` with wet ground enabled;
4. ``raycast_frame`` through one VLP-32C beam grid built once per run.

Two identities are kept apart on purpose:

- ``PlumeContext.scene_token`` is the **scene**, because ``PlumeState`` resets
  its clusters whenever that field changes. Passing the per-frame
  ``info["token"]`` there would rebuild the plume every frame and no cluster
  would ever survive, which is the one thing this smoke run must demonstrate.
- the per-frame ``info["token"]`` is passed as ``token``, so the RNG (and the
  ``PLUME_STATE`` marker) is keyed per frame as before.

One ``PlumeState`` lives per scene; frames are consumed in ascending
``timestamp`` order. The run ends with ``SSPP_PAPERPATH_OK`` or, when no frame
produced a detection, ``SSPP_PAPERPATH_BLOCKED`` plus ray-cast and cluster
diagnostics.

Run with::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
        scripts/smoke_sspp_paperpath.py
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from spray.beam_model import (  # noqa: E402
    ELEVATION_MAX_DEG,
    ELEVATION_MIN_DEG,
    BeamTable,
    build_beams,
)
from spray.plume import inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, seed_for  # noqa: E402
from spray.plume_state import PlumeState  # noqa: E402
from spray.raycast import raycast_frame  # noqa: E402
from spray.sspp_adapter import load_points  # noqa: E402
from spray.wet_ground import WetGroundConfig  # noqa: E402

NOISE_LABEL = 2
WFH_MM = 1.0
SCENES_IN_SMOKE = 4
FRAMES_PER_SCENE = 10
EPOCH = 0
SEED = 0
VEHICLE_CLASS = {
    "Crafter_dynamic": "crafter",
    "Golf_dynamic": "golf",
}
# [PAPER] VLP-32C: 32 lasers over the measured FOV, azimuth steps of 0.1-0.4 deg.
# One of these steps is chosen (0.2 deg = 1,800 columns), inside the measured
# 0.197307 deg of the release, so the grid stays close to the real scans.
VLP32C_RINGS = 32
VLP32C_AZIMUTH_STEP_DEG = 0.2

DEFAULT_DATASET_ROOT = REPO / "data" / "SemanticSprayDataset"
DEFAULT_INFOS = REPO / "data" / "sspp_infos_train.pkl"
DEFAULT_SPLIT_JSON = REPO / "data" / "sspp_split.json"


def vlp32c_beam_table() -> BeamTable:
    """The 32-ring VLP-32C grid used by the ray-casting step."""

    elevation = np.linspace(
        ELEVATION_MIN_DEG, ELEVATION_MAX_DEG, VLP32C_RINGS, dtype=np.float64
    )
    return BeamTable(
        elevation_deg=tuple(float(value) for value in elevation),
        azimuth_step_deg=VLP32C_AZIMUTH_STEP_DEG,
    )


def frames_of_scene(infos: list[dict], rel_scene: str, limit: int) -> list[dict]:
    """First ``limit`` frames of one scene, in ascending timestamp order."""

    prefix = rel_scene + "/"
    frames = [info for info in infos if str(info["token"]).startswith(prefix)]
    frames.sort(key=lambda info: info["timestamp"])
    return frames[:limit]


def read_labels(dataset_root: Path, rel_scene: str, scan_id: str) -> np.ndarray:
    path = dataset_root / rel_scene / "labels" / f"{scan_id}.label"
    return np.fromfile(path, dtype=np.int32)


def object_speed_mps(boxes: np.ndarray) -> float:
    """Fastest box speed from ``gt_boxes`` column 7, in m/s."""

    if boxes.shape[0] == 0:
        return 0.0
    return float(np.max(np.abs(boxes[:, 7].astype(np.float64))))


def road_z_m(boxes: np.ndarray) -> float:
    """Median box bottom of this frame; the road plane is rebuilt per frame."""

    return float(np.median(boxes[:, 2].astype(np.float64)))


def build_context(
    info: dict, rel_scene: str, frame_index: int, boxes: np.ndarray
) -> PlumeContext:
    return PlumeContext(
        scene_token=rel_scene,
        frame_index=frame_index,
        epoch=EPOCH,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=float(info["ego_speed_kmh"]) / 3.6,
        object_speed_mps=object_speed_mps(boxes),
        wfh_mm=WFH_MM,
        road_z_m=road_z_m(boxes),
    )


def smoke_scene(
    dataset_root: Path,
    rel_scene: str,
    frames: list[dict],
    table: BeamTable,
) -> dict:
    """Run the chain over one scene; returns per-frame counters and diagnostics."""

    vehicle_class = VEHICLE_CLASS[rel_scene.split("/")[0]]
    state = PlumeState()
    rows: list[dict] = []

    for frame_index, info in enumerate(frames):
        points = load_points(info, dataset_root)
        labels = read_labels(dataset_root, rel_scene, info["scan_id"])
        if labels.shape[0] != points.shape[0]:
            raise ValueError(
                f"{info['token']}: {labels.shape[0]} labels vs "
                f"{points.shape[0]} points"
            )
        noise = labels == NOISE_LABEL
        clean = points[~noise]

        boxes = info["gt_boxes"]
        context = build_context(info, rel_scene, frame_index, boxes)

        result = inject_plume_stateful(
            clean,
            boxes,
            context,
            state,
            seed=SEED,
            token=info["token"],
            wet_ground=WetGroundConfig(enabled=True),
            vehicle_class=vehicle_class,
        )
        raycast = raycast_frame(
            result.points_clean,
            state.all_alive(),
            table=table,
            road_z_m=context.road_z_m,
            rng=np.random.default_rng(
                seed_for(info["token"], frame_index, EPOCH)
            ),
        )

        alive = len(state.all_alive())
        rows.append(
            {
                "scene": rel_scene,
                "frame": frame_index,
                "spawned": int(state.counters.spawned),
                "alive": alive,
                "det": int(raycast.stats.det),
                "att_m": float(raycast.stats.att_m_total),
                "wet_in": int(result.stats.wet_points_in),
                "beams_hit": int(raycast.stats.beams_hit),
                "beams_total": int(raycast.stats.beams_total),
                "clusters": list(state.all_alive()),
            }
        )
        print(
            "SSPP_PAPERPATH "
            f"scene={rel_scene} "
            f"frame={frame_index} "
            f"spawned={rows[-1]['spawned']} "
            f"alive={rows[-1]['alive']} "
            f"det={rows[-1]['det']} "
            f"att_m={rows[-1]['att_m']:.2f} "
            f"wet_in={rows[-1]['wet_in']}"
        )

    return {"scene": rel_scene, "frames": rows}


def print_blocked(scenes: list[dict], table: BeamTable) -> None:
    """Diagnostics when no frame of the whole run produced a detection."""

    print("SSPP_PAPERPATH_BLOCKED reason=zero_detections_on_every_frame")
    elevation, azimuth = build_beams(table)
    print(
        "SSPP_PAPERPATH_BEAMS "
        f"rings={len(table.elevation_deg)} "
        f"azimuth_step_deg={table.azimuth_step_deg:.6f} "
        f"beams={elevation.size} "
        f"elevation_min_deg={min(table.elevation_deg):.3f} "
        f"elevation_max_deg={max(table.elevation_deg):.3f}"
    )
    for scene in scenes:
        last = scene["frames"][-1] if scene["frames"] else None
        if last is None:
            continue
        clusters = last["clusters"]
        radii = np.asarray([cluster.radius for cluster in clusters], dtype=float)
        distances = np.asarray(
            [float(np.linalg.norm(cluster.pos)) for cluster in clusters],
            dtype=float,
        )
        half_angles = (
            np.degrees(np.arcsin(np.clip(radii / distances, 0.0, 1.0)))
            if clusters
            else np.zeros(0)
        )
        beam_step = min(
            float(np.diff(np.asarray(table.elevation_deg)).min()),
            table.azimuth_step_deg,
        )
        print(
            "SSPP_PAPERPATH_CLUSTERS "
            f"scene={scene['scene']} "
            f"frame={last['frame']} "
            f"alive={last['alive']} "
            f"beams_hit={last['beams_hit']} "
            f"beams_total={last['beams_total']} "
            f"radius_min_m={radii.min() if radii.size else 0.0:.3f} "
            f"radius_max_m={radii.max() if radii.size else 0.0:.3f} "
            f"whole_cone_deg_min="
            f"{2.0 * half_angles.min() if half_angles.size else 0.0:.3f} "
            f"whole_cone_deg_max="
            f"{2.0 * half_angles.max() if half_angles.size else 0.0:.3f} "
            f"finest_beam_step_deg={beam_step:.6f} "
            f"cone_smaller_than_grid={bool(half_angles.size and 2.0 * half_angles.max() < beam_step)}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--infos", type=Path, default=DEFAULT_INFOS)
    parser.add_argument("--split-json", type=Path, default=DEFAULT_SPLIT_JSON)
    parser.add_argument("--split", default="train")
    parser.add_argument("--scenes", type=int, default=SCENES_IN_SMOKE)
    parser.add_argument("--frames-per-scene", type=int, default=FRAMES_PER_SCENE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_root = args.dataset_root.resolve()
    with args.infos.open("rb") as handle:
        infos = pickle.load(handle)
    split_doc = json.loads(args.split_json.read_text(encoding="utf-8"))
    rel_scenes = list(split_doc["split"][args.split])[: args.scenes]

    table = vlp32c_beam_table()
    scenes: list[dict] = []
    for rel_scene in rel_scenes:
        frames = frames_of_scene(infos, rel_scene, args.frames_per_scene)
        if not frames:
            print(f"SSPP_PAPERPATH_EMPTY scene={rel_scene}")
            continue
        scenes.append(smoke_scene(dataset_root, rel_scene, frames, table))

    rows = [row for scene in scenes for row in scene["frames"]]
    total_det = sum(row["det"] for row in rows)
    peak_alive = max((row["alive"] for row in rows), default=0)

    if total_det == 0:
        print_blocked(scenes, table)
        return 2

    print(
        "SSPP_PAPERPATH_OK "
        f"scenes={len(scenes)} "
        f"frames={len(rows)} "
        f"total_det={total_det} "
        f"total_alive_peak={peak_alive}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
