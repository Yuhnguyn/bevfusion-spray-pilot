#!/usr/bin/env python3
"""Build a fixed 4,000-sample nuScenes *train* infos pickle for ticket 11.

Runs on Kaggle, where the nuScenes devkit is installed::

    python scripts/make_mini_split.py \
        --dataroot /kaggle/input/nuscenes-v1-0-full-keyframes \
        --out data/infos/mini_train_4000.pkl \
        --n 4000 --seed 0 --max-sweeps 10

The token subset is chosen by :func:`spray.mini_split.select_tokens`, so arms A
and B of the mini run train on the exact same samples.  The info dicts are a
reduced copy of the pinned vendor converter
(``mit/bevfusion/tools/data_converter/nuscenes_converter.py``):

* ``_fill_trainval_infos`` -- lines 163-292: per-sample loop, ``info`` keys,
  camera loop, sweep chain, and annotation conversion.
* ``obtain_sensor2top`` -- lines 295-352: sensor -> top-LiDAR transforms.

The vendor function is not reused because it only accepts scene filters and
would walk all ~28k samples; this runs on the selected tokens only.

Two deliberate additions to the vendor key set, both required downstream:

* ``scene_token`` -- the vendor info omits it; :func:`validate_info` and
  :func:`summarize` need it to count scenes and the CLI uses it to prove no val
  scene slipped in.
* ``cam_intrinsic`` -- ``NuScenesDataset.get_data_info`` reads ``cam_intrinsic``
  while the pinned converter writes ``camera_intrinsics`` (da93b27 mismatch).
  Both aliases are stored so the pickle loads as-is.

Candidates are limited to LiDAR keyframes that declare a previous
``sample_data`` pointer; only the first frame of each scene is dropped by this
rule.  The sweep chain is best-effort: when the dataset ships keyframes only
(no ``sweeps/LIDAR_TOP`` files), the chain stops at the first missing file and
``info["sweeps"]`` stays empty.  ``validate_info`` accepts an empty sweep list.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spray.mini_split import (  # noqa: E402
    DEFAULT_SPLITS_PATH,
    load_camera_types,
    load_val_scenes,
    select_tokens,
    summarize,
    validate_info,
)

MIN_KEEP_RATIO = 0.95  # ticket 11: >= 3,800 of 4,000 must build


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataroot", required=True, help="nuScenes root")
    parser.add_argument("--out", required=True, help="output pickle path")
    parser.add_argument("--n", type=int, default=4000, help="number of samples")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-sweeps", type=int, default=10)
    parser.add_argument("--version", default="v1.0-trainval")
    parser.add_argument(
        "--splits",
        default=None,
        help="official nuScenes splits.py (default: vendor path, else installed devkit)",
    )
    parser.add_argument(
        "--tokens-json",
        default=None,
        help="JSON from make_eval_split.py; build exactly its `frames` tokens",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the selection count only; read no images/LiDAR and write nothing",
    )
    return parser.parse_args(argv)


def _resolve_splits_path(explicit):
    """Return a splits.py path, or None to let load_val_scenes use its default.

    The pinned vendor clone does not contain ``nuscenes/utils/splits.py``; on
    Kaggle the devkit is installed, so fall back to its ``splits.py``.  If
    neither exists, return None and let load_val_scenes raise.
    """
    if explicit:
        return explicit
    if DEFAULT_SPLITS_PATH.is_file():
        return None
    try:
        from nuscenes.utils import splits as devkit_splits
    except ImportError:
        return None
    return getattr(devkit_splits, "__file__", None)


def _to_relative(path: str) -> str:
    """Vendor ``obtain_sensor2top`` strips the cwd prefix from lyft paths."""
    path = str(path)
    cwd = os.getcwd()
    if cwd in path:
        path = path.split(f"{cwd}/")[-1]
    return path


def _obtain_sensor2top(
    nusc, sensor_token, l2e_t, l2e_r_mat, e2g_t, e2g_r_mat, sensor_type, np, Quaternion
):
    """Reduced copy of vendor ``obtain_sensor2top`` (lines 295-352)."""
    sd_rec = nusc.get("sample_data", sensor_token)
    cs_record = nusc.get("calibrated_sensor", sd_rec["calibrated_sensor_token"])
    pose_record = nusc.get("ego_pose", sd_rec["ego_pose_token"])
    data_path = _to_relative(nusc.get_sample_data_path(sd_rec["token"]))
    sweep = {
        "data_path": data_path,
        "type": sensor_type,
        "sample_data_token": sd_rec["token"],
        "sensor2ego_translation": cs_record["translation"],
        "sensor2ego_rotation": cs_record["rotation"],
        "ego2global_translation": pose_record["translation"],
        "ego2global_rotation": pose_record["rotation"],
        "timestamp": sd_rec["timestamp"],
    }
    l2e_r_s = sweep["sensor2ego_rotation"]
    l2e_t_s = sweep["sensor2ego_translation"]
    e2g_r_s = sweep["ego2global_rotation"]
    e2g_t_s = sweep["ego2global_translation"]

    l2e_r_s_mat = Quaternion(l2e_r_s).rotation_matrix
    e2g_r_s_mat = Quaternion(e2g_r_s).rotation_matrix
    R = (l2e_r_s_mat.T @ e2g_r_s_mat.T) @ (
        np.linalg.inv(e2g_r_mat).T @ np.linalg.inv(l2e_r_mat).T
    )
    T = (l2e_t_s @ e2g_r_s_mat.T + e2g_t_s) @ (
        np.linalg.inv(e2g_r_mat).T @ np.linalg.inv(l2e_r_mat).T
    )
    T -= (
        e2g_t @ (np.linalg.inv(e2g_r_mat).T @ np.linalg.inv(l2e_r_mat).T)
        + l2e_t @ np.linalg.inv(l2e_r_mat).T
    )
    sweep["sensor2lidar_rotation"] = R.T
    sweep["sensor2lidar_translation"] = T
    return sweep


def _build_info(nusc, sample, max_sweeps, camera_types, name_mapping, np, Quaternion):
    """Reduced copy of vendor ``_fill_trainval_infos`` (lines 181-290)."""
    lidar_token = sample["data"]["LIDAR_TOP"]
    lidar_abs = nusc.get_sample_data_path(lidar_token)
    if not os.path.exists(lidar_abs):
        raise FileNotFoundError(lidar_abs)

    sd_rec = nusc.get("sample_data", lidar_token)
    cs_record = nusc.get("calibrated_sensor", sd_rec["calibrated_sensor_token"])
    pose_record = nusc.get("ego_pose", sd_rec["ego_pose_token"])
    location = nusc.get(
        "log", nusc.get("scene", sample["scene_token"])["log_token"]
    )["location"]
    lidar_path, boxes, _ = nusc.get_sample_data(lidar_token)

    info = {
        "lidar_path": lidar_path,
        "token": sample["token"],
        "sweeps": [],
        "cams": dict(),
        "lidar2ego_translation": cs_record["translation"],
        "lidar2ego_rotation": cs_record["rotation"],
        "ego2global_translation": pose_record["translation"],
        "ego2global_rotation": pose_record["rotation"],
        "timestamp": sample["timestamp"],
        "location": location,
        "scene_token": sample["scene_token"],
    }

    l2e_r = info["lidar2ego_rotation"]
    l2e_t = info["lidar2ego_translation"]
    e2g_r = info["ego2global_rotation"]
    e2g_t = info["ego2global_translation"]
    l2e_r_mat = Quaternion(l2e_r).rotation_matrix
    e2g_r_mat = Quaternion(e2g_r).rotation_matrix

    for cam in camera_types:
        cam_token = sample["data"][cam]
        cam_abs = nusc.get_sample_data_path(cam_token)
        if not os.path.exists(cam_abs):
            raise FileNotFoundError(cam_abs)
        _, _, camera_intrinsics = nusc.get_sample_data(cam_token)
        cam_info = _obtain_sensor2top(
            nusc, cam_token, l2e_t, l2e_r_mat, e2g_t, e2g_r_mat, cam, np, Quaternion
        )
        # Vendor writes camera_intrinsics; the pinned dataset reads cam_intrinsic.
        cam_info.update(
            camera_intrinsics=camera_intrinsics, cam_intrinsic=camera_intrinsics
        )
        info["cams"].update({cam: cam_info})

    sd_rec = nusc.get("sample_data", lidar_token)
    sweeps = []
    while len(sweeps) < max_sweeps:
        if sd_rec["prev"] == "":
            break
        sweep_abs = nusc.get_sample_data_path(sd_rec["prev"])
        if not os.path.exists(sweep_abs):
            break  # dataset keyframes-only: stop the chain, keep what we have
        sweeps.append(
            _obtain_sensor2top(
                nusc,
                sd_rec["prev"],
                l2e_t,
                l2e_r_mat,
                e2g_t,
                e2g_r_mat,
                "lidar",
                np,
                Quaternion,
            )
        )
        sd_rec = nusc.get("sample_data", sd_rec["prev"])
    info["sweeps"] = sweeps

    annotations = [
        nusc.get("sample_annotation", token) for token in sample["anns"]
    ]
    locs = np.array([b.center for b in boxes]).reshape(-1, 3)
    dims = np.array([b.wlh for b in boxes]).reshape(-1, 3)
    rots = np.array([b.orientation.yaw_pitch_roll[0] for b in boxes]).reshape(-1, 1)
    velocity = np.array(
        [nusc.box_velocity(token)[:2] for token in sample["anns"]]
    )
    valid_flag = np.array(
        [
            (anno["num_lidar_pts"] + anno["num_radar_pts"]) > 0
            for anno in annotations
        ],
        dtype=bool,
    ).reshape(-1)
    for i in range(len(boxes)):
        velo = np.array([*velocity[i], 0.0])
        velo = velo @ np.linalg.inv(e2g_r_mat).T @ np.linalg.inv(l2e_r_mat).T
        velocity[i] = velo[:2]

    names = [b.name for b in boxes]
    for i in range(len(names)):
        if names[i] in name_mapping:
            names[i] = name_mapping[names[i]]
    names = np.array(names)

    gt_boxes = np.concatenate([locs, dims, -rots - np.pi / 2], axis=1)
    assert len(gt_boxes) == len(annotations), f"{len(gt_boxes)}, {len(annotations)}"
    info["gt_boxes"] = gt_boxes
    info["gt_names"] = names
    info["gt_velocity"] = velocity.reshape(-1, 2)
    info["num_lidar_pts"] = np.array([a["num_lidar_pts"] for a in annotations])
    info["num_radar_pts"] = np.array([a["num_radar_pts"] for a in annotations])
    info["valid_flag"] = valid_flag
    return info


def load_tokens_from_json(path) -> list[str]:
    """Read ``sample_token`` values from a ``make_eval_split.py`` payload.

    The order of the ``frames`` list is preserved; ``scene`` is ignored.
    """
    payload = json.loads(Path(path).read_text())
    return [frame["sample_token"] for frame in payload["frames"]]


def build_infos_for_tokens(tokens, build_info):
    """Build one info per token with the injected ``build_info(token)``.

    Returns ``(infos, missing)``.  A token whose builder raises
    ``FileNotFoundError`` or ``KeyError`` lands in ``missing`` instead of
    aborting the run, so the caller can fail loudly with a count.  Input
    order is preserved.
    """
    infos = []
    missing = []
    for token in tokens:
        try:
            infos.append(build_info(token))
        except (FileNotFoundError, KeyError):
            missing.append(token)
    return infos, missing


def main(argv=None) -> int:
    args = parse_args(argv)

    # Imported inside main on purpose: the devkit only exists on Kaggle.
    from nuscenes.nuscenes import NuScenes

    nusc = NuScenes(version=args.version, dataroot=args.dataroot, verbose=False)

    val_scenes = load_val_scenes(_resolve_splits_path(args.splits))

    scene_names = {scene["token"]: scene["name"] for scene in nusc.scene}
    by_token = {}
    samples = []
    for sample in nusc.sample:
        token = sample["token"]
        by_token[token] = sample
        sd_rec = nusc.get("sample_data", sample["data"]["LIDAR_TOP"])
        if sd_rec["prev"] == "":
            continue  # first frame of the scene has no sweep; validate_info wants >= 1
        samples.append(
            {"token": token, "scene_token": scene_names[sample["scene_token"]]}
        )

    try:
        if args.tokens_json:
            selected = load_tokens_from_json(args.tokens_json)
        else:
            selected = select_tokens(samples, args.n, args.seed, val_scenes)
    except ValueError as exc:
        candidates = sum(1 for s in samples if s["scene_token"] not in val_scenes)
        print(f"MINI_SPLIT_FAILED got={candidates}")
        print(str(exc), file=sys.stderr)
        return 1

    if args.dry_run:
        candidates = sum(1 for s in samples if s["scene_token"] not in val_scenes)
        print(
            f"MINI_SPLIT_DRY_RUN n={len(selected)} candidates={candidates} "
            f"val_scenes={len(val_scenes)} seed={args.seed}"
        )
        return 0

    import numpy as np
    from mmdet3d.datasets import NuScenesDataset
    from pyquaternion import Quaternion

    camera_types = load_camera_types()

    def _build_one(token):
        return _build_info(
            nusc,
            by_token[token],
            args.max_sweeps,
            camera_types,
            NuScenesDataset.NameMapping,
            np,
            Quaternion,
        )

    if args.tokens_json:
        infos, missing_tokens = build_infos_for_tokens(selected, _build_one)
        if missing_tokens:
            print(f"TOKENS_MISSING n={len(missing_tokens)}")
            return 1
        missing = 0
        nosweeps = sum(1 for info in infos if not info["sweeps"])
    else:
        infos = []
        missing = 0
        nosweeps = 0
        for token in selected:
            try:
                info = _build_one(token)
            except FileNotFoundError as exc:
                missing += 1
                if missing <= 5:
                    print(
                        f"MINI_SPLIT_MISSING token={token} path={exc}",
                        file=sys.stderr,
                    )
                continue
            if not info["sweeps"]:
                nosweeps += 1
            infos.append(info)

    if missing:
        print(f"MINI_SPLIT_MISSING_TOTAL n={missing}", file=sys.stderr)
    print(f"MINI_SPLIT_NOSWEEPS n={nosweeps}", file=sys.stderr)

    if args.tokens_json:
        split_counts = {}
        for info in infos:
            scene = scene_names[info["scene_token"]]
            split = "val" if scene in val_scenes else "train"
            split_counts[split] = split_counts.get(split, 0) + 1
        print(
            f"MINI_SPLIT_TOKENS n={len(infos)} "
            f"splits={json.dumps(split_counts, sort_keys=True)}"
        )

    min_required = len(selected) if args.tokens_json else int(args.n * MIN_KEEP_RATIO)
    if len(infos) < min_required:
        print(f"MINI_SPLIT_FAILED got={len(infos)}")
        return 1

    summary = summarize(infos)
    metadata = dict(
        version=args.version,
        source="eval_tokens" if args.tokens_json else "mini_split",
        seed=args.seed,
        n_requested=len(selected) if args.tokens_json else args.n,
        n_built=len(infos),
        max_sweeps=args.max_sweeps,
        val_scenes=len(val_scenes),
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as handle:
        pickle.dump(dict(infos=infos, metadata=metadata), handle, protocol=4)

    invalid = sum(1 for info in infos if validate_info(info))
    if invalid:
        print(f"MINI_SPLIT_WARN invalid={invalid}", file=sys.stderr)
    if missing:
        print(f"MINI_SPLIT_WARN missing={missing}", file=sys.stderr)

    print(
        f"MINI_SPLIT_OK n={summary['n_samples']} scenes={summary['n_scenes']} "
        f"gt_boxes={summary['gt_boxes_total']} val_scenes={len(val_scenes)} "
        f"seed={args.seed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
