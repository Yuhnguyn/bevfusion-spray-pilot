import ast
import gc
import glob
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from collections import defaultdict

import numpy as np

INPUT_DIR = "/kaggle/input"
WORK_DIR = "/kaggle/working"
OUT_PATH = os.path.join(WORK_DIR, "eligibility.json")

VERSION = "v1.0-trainval"
DEVKIT_VERSION = "1.1.11"
SPLITS_URL = (
    "https://raw.githubusercontent.com/nutonomy/nuscenes-devkit/"
    "master/python-sdk/nuscenes/utils/splits.py"
)
KERNEL_ID = "nguynhuy9669/nuscenes-eligibility-scan"

BOX_SPEED_KMH = 50.0
DISTANCES_M = (10.0, 15.0, 20.0, 30.0, 40.0, 50.0)
EGO_THRESHOLDS_KMH = (None, 30.0, 50.0, 60.0)
EGO_DT_S = 0.5
EPS = 1e-9
VELOCITY_MAX_TIME_DIFF_S = 0.5
LEGACY_EXPECTED_BOXES = 952
LEGACY_EXPECTED_FRAMES = 697

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
CAR_CATEGORY = "vehicle.car"
VEHICLE_CLASSES = sorted(set(NAME_MAPPING.values()))

REQUIRED_TABLES = (
    "scene.json",
    "sample.json",
    "sample_data.json",
    "sample_annotation.json",
    "ego_pose.json",
    "calibrated_sensor.json",
    "category.json",
    "sensor.json",
)


def log(*parts):
    print(*parts, flush=True)


def run_pip(args):
    # Every pip invocation must be --no-deps so the Kaggle numpy build is never
    # replaced. Failure is non-fatal: the pure-python path takes over.
    cmd = [sys.executable, "-m", "pip", "install", "-q", *args]
    log("$", " ".join(cmd))
    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:
        log("pip invocation failed (ignored):", repr(exc))


def import_devkit():
    try:
        from nuscenes.nuscenes import NuScenes
        from nuscenes.utils.data_classes import Box
        from nuscenes.utils.splits import val as val_names

        return NuScenes, Box, list(val_names)
    except Exception as exc:
        log("devkit import check failed:", repr(exc))
        return None


def install_devkit_no_deps():
    run_pip(
        [
            "--no-deps",
            f"nuscenes-devkit=={DEVKIT_VERSION}",
            "pyquaternion",
            "descartes",
        ]
    )


def find_dataroot():
    hits = sorted(
        glob.glob(
            os.path.join(INPUT_DIR, "**", "sample_annotation.json"),
            recursive=True,
        )
    )
    log("sample_annotation.json hits:")
    for hit in hits:
        log("  ", hit)

    roots = []
    for hit in hits:
        meta_dir = os.path.dirname(hit)
        if os.path.basename(meta_dir) != VERSION:
            continue
        root = os.path.dirname(meta_dir)
        if all(os.path.isfile(os.path.join(meta_dir, name)) for name in REQUIRED_TABLES):
            if root not in roots:
                roots.append(root)

    log("candidate dataroots (parent of */v1.0-trainval/):", roots)
    if not roots:
        raise RuntimeError(
            "no nuScenes dataroot found: looked for "
            f"{INPUT_DIR}/**/{VERSION}/sample_annotation.json; hits={hits}"
        )
    return roots[0]


def download_val_split():
    log("downloading val split:", SPLITS_URL)
    try:
        with urllib.request.urlopen(SPLITS_URL, timeout=30) as handle:
            text = handle.read().decode("utf-8")
        tree = ast.parse(text)
    except Exception as exc:
        log("val split download/parse failed:", repr(exc))
        return None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "val":
                try:
                    names = ast.literal_eval(node.value)
                    return set(names)
                except Exception as exc:
                    log("val split literal_eval failed:", repr(exc))
                    return None
    log("val assignment not found in splits.py")
    return None


def quat_to_rot(q):
    w, x, y, z = (float(v) for v in q)
    n = w * w + x * x + y * y + z * z
    if n < EPS:
        return np.eye(3)
    s = 2.0 / n
    wx, wy, wz = s * w * x, s * w * y, s * w * z
    xx, xy, xz = s * x * x, s * x * y, s * x * z
    yy, yz, zz = s * y * y, s * y * z, s * z * z
    return np.array(
        [
            [1.0 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1.0 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1.0 - (xx + yy)],
        ]
    )


def make_geo(pose, cs):
    R_ep = quat_to_rot(pose["rotation"])
    t_ep = np.asarray(pose["translation"], dtype=float)
    R_cs = quat_to_rot(cs["rotation"])
    t_cs = np.asarray(cs["translation"], dtype=float)
    return R_ep, t_ep, R_cs, t_cs


def to_lidar(points_global, geo):
    R_ep, t_ep, R_cs, t_cs = geo
    ego = R_ep.T @ (points_global - t_ep[:, None])
    return R_cs.T @ (ego - t_cs[:, None])


def box_corners(center, size, rotation):
    # Same convention as nuscenes.utils.data_classes.Box.corners:
    # x along length, y along width, z along height.
    w, l, h = (float(v) for v in size)
    x = l / 2.0 * np.array([1, 1, 1, 1, -1, -1, -1, -1], dtype=float)
    y = w / 2.0 * np.array([1, -1, -1, 1, 1, -1, -1, 1], dtype=float)
    z = h / 2.0 * np.array([1, 1, -1, -1, 1, 1, -1, -1], dtype=float)
    local = np.vstack((x, y, z))
    return quat_to_rot(rotation) @ local + np.asarray(center, dtype=float)[:, None]


def fallback_velocity(ann, anns_by_token, sample_ts):
    first = anns_by_token.get(ann["prev"]) if ann["prev"] else None
    last = anns_by_token.get(ann["next"]) if ann["next"] else None
    instance = ann["instance_token"]
    if first is not None and first["instance_token"] != instance:
        first = None
    if last is not None and last["instance_token"] != instance:
        last = None

    has_prev = first is not None
    has_next = last is not None
    if not has_prev and not has_next:
        return None
    if not has_prev:
        first = ann
    if not has_next:
        last = ann

    t_first = sample_ts.get(first["sample_token"])
    t_last = sample_ts.get(last["sample_token"])
    if t_first is None or t_last is None:
        return None

    dt = (t_last - t_first) / 1e6
    # devkit box_velocity(max_time_diff=VELOCITY_MAX_TIME_DIFF_S): the centered
    # difference is allowed double the gap, so two adjacent 0.5 s keyframes pass.
    limit = VELOCITY_MAX_TIME_DIFF_S * (2.0 if (has_prev and has_next) else 1.0)
    if dt <= 0 or dt > limit + 1e-6:
        return None

    pos_first = np.asarray(first["translation"], dtype=float)
    pos_last = np.asarray(last["translation"], dtype=float)
    return (pos_last - pos_first) / dt


def process_frame(anns, velocity_fn, geo, counters):
    boxes = []
    for ann in anns:
        counters["vehicle_anns"] += 1
        velocity = velocity_fn(ann)
        if velocity is None or not np.all(np.isfinite(velocity)):
            counters["nonfinite_velocity"] += 1
            continue

        speed = float(np.linalg.norm(velocity)) * 3.6
        if speed < BOX_SPEED_KMH - EPS:
            continue

        center_global = np.asarray(ann["translation"], dtype=float)[:, None]
        center_lidar = to_lidar(center_global, geo)[:, 0]
        if center_lidar[0] <= 0:
            counters["behind"] += 1
            continue

        corners_global = box_corners(ann["translation"], ann["size"], ann["rotation"])
        corners_lidar = to_lidar(corners_global, geo)
        d_m = float(np.min(np.linalg.norm(corners_lidar[:2], axis=0)))
        d_legacy_m = float(np.linalg.norm(center_lidar[:2]))

        boxes.append(
            {
                "category": ann["category_name"],
                "class": NAME_MAPPING[ann["category_name"]],
                "speed_kmh": round(speed, 3),
                "d_m": round(d_m, 3),
                "d_legacy_m": round(d_legacy_m, 3),
            }
        )
    return boxes


def split_of(scene_name, val_set):
    if val_set is None:
        return "all"
    return "val" if scene_name in val_set else "train"


def scan_devkit(nusc, val_set, counters):
    started = time.time()
    frames = []
    scene_rows = []
    n_samples_total = 0
    velocity_fn = lambda ann: nusc.box_velocity(ann["token"])

    for scene in nusc.scene:
        name = scene["name"]
        is_highway = "highway" in scene["description"].lower()
        split = split_of(name, val_set)
        frames_in_scene = 0
        prev_pos = None
        token = scene["first_sample_token"]

        while token:
            sample = nusc.get("sample", token)
            lidar_sd = nusc.get("sample_data", sample["data"]["LIDAR_TOP"])
            pose = nusc.get("ego_pose", lidar_sd["ego_pose_token"])
            cs = nusc.get("calibrated_sensor", lidar_sd["calibrated_sensor_token"])
            geo = make_geo(pose, cs)

            pos = np.asarray(pose["translation"], dtype=float)[:2]
            if prev_pos is None:
                v_ego = None
            else:
                v_ego = float(np.linalg.norm(pos - prev_pos) / EGO_DT_S * 3.6)
            prev_pos = pos

            anns = []
            for ann_token in sample["anns"]:
                ann = nusc.get("sample_annotation", ann_token)
                if ann["category_name"] in NAME_MAPPING:
                    anns.append(ann)

            boxes = process_frame(anns, velocity_fn, geo, counters)
            frames_in_scene += 1
            n_samples_total += 1
            if boxes:
                frames.append(
                    {
                        "scene": name,
                        "scene_token": scene["token"],
                        "split": split,
                        "highway": is_highway,
                        "v_ego_kmh": None if v_ego is None else round(v_ego, 3),
                        "boxes": boxes,
                    }
                )
            if n_samples_total % 5000 == 0:
                log(
                    f"scanned {n_samples_total} frames | {len(frames)} with "
                    f">=1 eligible box | {time.time() - started:.0f}s"
                )
            token = sample["next"]

        scene_rows.append(
            {
                "name": name,
                "token": scene["token"],
                "description": scene["description"],
                "highway": is_highway,
                "split": split,
                "frames": frames_in_scene,
            }
        )

    return frames, scene_rows, n_samples_total, time.time() - started


def load_table(root, name):
    path = os.path.join(root, VERSION, name)
    with open(path, "r") as handle:
        return json.load(handle)


def scan_fallback(root, val_set, counters):
    started = time.time()

    scenes = load_table(root, "scene.json")
    samples = load_table(root, "sample.json")
    sample_data = load_table(root, "sample_data.json")
    sample_annotations = load_table(root, "sample_annotation.json")
    ego_poses = load_table(root, "ego_pose.json")
    calibrated_sensors = load_table(root, "calibrated_sensor.json")
    sensor_table = load_table(root, "sensor.json")

    sample_by_token = {s["token"]: s for s in samples}
    sample_ts = {s["token"]: s["timestamp"] for s in samples}
    del samples

    pose_by_token = {p["token"]: p for p in ego_poses}
    del ego_poses

    cs_by_token = {c["token"]: c for c in calibrated_sensors}
    sensor_channel = {s["token"]: s["channel"] for s in sensor_table}
    lidar_cs_tokens = {
        token
        for token, cs in cs_by_token.items()
        if sensor_channel.get(cs["sensor_token"]) == "LIDAR_TOP"
    }
    del calibrated_sensors, sensor_table

    keyframe_by_sample = {}
    for record in sample_data:
        if (
            record["is_key_frame"]
            and record["calibrated_sensor_token"] in lidar_cs_tokens
        ):
            keyframe_by_sample[record["sample_token"]] = record
    del sample_data

    anns_by_token = {}
    ann_tokens_by_sample = defaultdict(list)
    for ann in sample_annotations:
        category = ann["category_name"]
        if category not in NAME_MAPPING:
            continue
        anns_by_token[ann["token"]] = {
            "token": ann["token"],
            "instance_token": ann["instance_token"],
            "prev": ann["prev"],
            "next": ann["next"],
            "sample_token": ann["sample_token"],
            "translation": ann["translation"],
            "size": ann["size"],
            "rotation": ann["rotation"],
            "category_name": category,
        }
        ann_tokens_by_sample[ann["sample_token"]].append(ann["token"])
    del sample_annotations
    gc.collect()

    log(
        "fallback tables:",
        {
            "scenes": len(scenes),
            "samples": len(sample_by_token),
            "vehicle_annotations": len(anns_by_token),
            "lidar_keyframes": len(keyframe_by_sample),
        },
    )

    velocity_fn = lambda ann: fallback_velocity(ann, anns_by_token, sample_ts)
    frames = []
    scene_rows = []
    n_samples_total = 0

    for scene in scenes:
        name = scene["name"]
        is_highway = "highway" in scene["description"].lower()
        split = split_of(name, val_set)
        frames_in_scene = 0
        prev_pos = None
        token = scene["first_sample_token"]

        while token:
            sample = sample_by_token.get(token)
            if sample is None:
                counters["missing_sample"] += 1
                break
            lidar_sd = keyframe_by_sample.get(token)
            if lidar_sd is None:
                counters["missing_lidar"] += 1
                token = sample["next"]
                continue

            pose = pose_by_token.get(lidar_sd["ego_pose_token"])
            cs = cs_by_token.get(lidar_sd["calibrated_sensor_token"])
            if pose is None or cs is None:
                counters["missing_pose"] += 1
                token = sample["next"]
                continue

            geo = make_geo(pose, cs)
            pos = np.asarray(pose["translation"], dtype=float)[:2]
            if prev_pos is None:
                v_ego = None
            else:
                v_ego = float(np.linalg.norm(pos - prev_pos) / EGO_DT_S * 3.6)
            prev_pos = pos

            anns = [
                anns_by_token[t]
                for t in ann_tokens_by_sample.get(token, ())
            ]
            boxes = process_frame(anns, velocity_fn, geo, counters)
            frames_in_scene += 1
            n_samples_total += 1
            if boxes:
                frames.append(
                    {
                        "scene": name,
                        "scene_token": scene["token"],
                        "split": split,
                        "highway": is_highway,
                        "v_ego_kmh": None if v_ego is None else round(v_ego, 3),
                        "boxes": boxes,
                    }
                )
            if n_samples_total % 5000 == 0:
                log(
                    f"scanned {n_samples_total} frames | {len(frames)} with "
                    f">=1 eligible box | {time.time() - started:.0f}s"
                )
            token = sample["next"]

        scene_rows.append(
            {
                "name": name,
                "token": scene["token"],
                "description": scene["description"],
                "highway": is_highway,
                "split": split,
                "frames": frames_in_scene,
            }
        )

    return frames, scene_rows, n_samples_total, time.time() - started


def build_meta(scene_rows, frames, n_samples_total, counters, scan_seconds):
    split_totals = {}
    for split in ("all", "val", "train"):
        rows = [
            row for row in scene_rows if split == "all" or row["split"] == split
        ]
        split_totals[split] = {
            "scenes": len(rows),
            "frames": int(sum(row["frames"] for row in rows)),
        }

    return {
        "n_scenes_total": len(scene_rows),
        "n_samples_total": n_samples_total,
        "highway_scenes_total": sum(1 for row in scene_rows if row["highway"]),
        "highway_frames_total": int(
            sum(row["frames"] for row in scene_rows if row["highway"])
        ),
        "frames_with_eligible_box": len(frames),
        "split_totals": split_totals,
        "counters": dict(counters),
        "scan_seconds": round(scan_seconds, 1),
        "scenes": scene_rows,
    }


def select_split(frames, split):
    if split == "all":
        return frames
    return [frame for frame in frames if frame["split"] == split]


def matches(box, car_only):
    return (not car_only) or box["category"] == CAR_CATEGORY


def summary_row(frames, dist, car_only, ego_min):
    n_boxes = 0
    n_frames = 0
    scenes = set()
    for frame in frames:
        if ego_min is not None:
            v_ego = frame["v_ego_kmh"]
            if v_ego is None or v_ego < ego_min - EPS:
                continue
        count = 0
        for box in frame["boxes"]:
            if not matches(box, car_only):
                continue
            if box["d_m"] <= dist + EPS:
                count += 1
        if count:
            n_boxes += count
            n_frames += 1
            scenes.add(frame["scene_token"])
    n_scenes = len(scenes)
    return {
        "d_max_m": dist,
        "boxes": n_boxes,
        "frames": n_frames,
        "scenes": n_scenes,
        "frames_per_scene": (n_frames / n_scenes) if n_scenes else 0.0,
    }


def distance_table(frames, car_only, ego_min):
    return [summary_row(frames, dist, car_only, ego_min) for dist in DISTANCES_M]


def print_distance_rows(title, rows):
    log("")
    log(title)
    log(f"  {'d_m':>5} {'boxes':>8} {'frames':>8} {'scenes':>7} {'frames/scene':>13}")
    for row in rows:
        log(
            f"  {row['d_max_m']:>5.0f} {row['boxes']:>8} {row['frames']:>8} "
            f"{row['scenes']:>7} {row['frames_per_scene']:>13.2f}"
        )
    thin = [row["d_max_m"] for row in rows if row["frames"] and row["scenes"] < 10]
    if thin:
        log(f"  WARN: < 10 scenes at d <= {thin} - not usable for scene bootstrap")


def compute_control_row(frames):
    out = {}
    log("")
    log("=" * 78)
    log(
        "TABLE 0 | CONTROL ROW | d_legacy <= 30 m, box speed >= 50 km/h, "
        "x > 0, no ego filter, ALL keyframes"
    )
    log(f"  expected from the old table: {LEGACY_EXPECTED_BOXES} boxes / "
        f"{LEGACY_EXPECTED_FRAMES} frames")
    for name, car_only in (("vehicle_ish", False), ("car_only", True)):
        n_boxes = 0
        n_frames = 0
        scenes = set()
        for frame in frames:
            count = 0
            for box in frame["boxes"]:
                if not matches(box, car_only):
                    continue
                if box["d_legacy_m"] <= 30.0 + EPS:
                    count += 1
            if count:
                n_boxes += count
                n_frames += 1
                scenes.add(frame["scene_token"])
        dev_boxes = 100.0 * (n_boxes - LEGACY_EXPECTED_BOXES) / LEGACY_EXPECTED_BOXES
        dev_frames = 100.0 * (n_frames - LEGACY_EXPECTED_FRAMES) / LEGACY_EXPECTED_FRAMES
        status = (
            "OK (<5%)"
            if abs(dev_boxes) < 5.0 and abs(dev_frames) < 5.0
            else "MISMATCH (>=5%)"
        )
        log(
            f"  {name:<12} {n_boxes:>6} boxes / {n_frames:>6} frames / "
            f"{len(scenes):>4} scenes | delta {dev_boxes:+.2f}% boxes, "
            f"{dev_frames:+.2f}% frames | {status}"
        )
        out[name] = {
            "expected_boxes": LEGACY_EXPECTED_BOXES,
            "expected_frames": LEGACY_EXPECTED_FRAMES,
            "boxes": n_boxes,
            "frames": n_frames,
            "scenes": len(scenes),
            "delta_boxes_pct": round(dev_boxes, 3),
            "delta_frames_pct": round(dev_frames, 3),
            "status": status,
        }
    return out


def compute_split_breakdown(frames, meta, val_available):
    log("")
    log("=" * 78)
    log("SPLIT BREAKDOWN | box speed >= 50 km/h, d <= 30 m, x > 0, no ego filter")
    log(
        f"  n_scenes_total={meta['n_scenes_total']} "
        f"n_samples_total={meta['n_samples_total']} "
        f"(old table reference: 34149 keyframes, 6019 val)"
    )
    out = {}
    for split in ("all", "val", "train"):
        totals = meta["split_totals"][split]
        if split != "all" and not val_available:
            log(f"  {split}: unavailable (val split not loaded)")
            out[split] = {"available": False}
            continue
        split_frames = select_split(frames, split)
        row = {"available": True, "scenes_total": totals["scenes"],
               "frames_total": totals["frames"]}
        for name, car_only in (("vehicle_ish", False), ("car_only", True)):
            r = summary_row(split_frames, 30.0, car_only, None)
            row[name] = r
            log(
                f"  {split:<5} scenes_total={totals['scenes']:>4} "
                f"frames_total={totals['frames']:>6} | {name:<12} "
                f"{r['boxes']:>6} boxes / {r['frames']:>6} frames / "
                f"{r['scenes']:>4} scenes / {r['frames_per_scene']:>6.2f} frames-per-scene"
            )
        out[split] = row
    return out


def compute_table1(frames, val_available):
    out = {}
    log("")
    log("=" * 78)
    log("TABLE 1 | box speed >= 50 km/h | d <= 10/15/20/30/40/50 m | by split")
    for split in ("all", "val", "train"):
        if split != "all" and not val_available:
            log(f"  split {split}: unavailable (val split not loaded)")
            out[split] = {"available": False}
            continue
        split_frames = select_split(frames, split)
        out[split] = {"available": True}
        for name, car_only in (("vehicle_ish", False), ("car_only", True)):
            rows = distance_table(split_frames, car_only, None)
            print_distance_rows(f"split={split} | {name}", rows)
            out[split][name] = rows
    return out


def compute_table2(frames, val_available):
    out = {}
    log("")
    log("=" * 78)
    log("TABLE 2 | table 1 with v_ego filter | all and val: 30/50/60 | train: no ego filter")
    for split in ("all", "val", "train"):
        if split != "all" and not val_available:
            log(f"  split {split}: unavailable (val split not loaded)")
            out[split] = {"available": False}
            continue
        split_frames = select_split(frames, split)
        egos = (None,) if split == "train" else EGO_THRESHOLDS_KMH
        out[split] = {"available": True}
        for ego in egos:
            key = "no_ego_filter" if ego is None else f"ego_ge_{int(ego)}"
            label = (
                "no filter (first frame of scene kept, v_ego=null)"
                if ego is None
                else f"v_ego >= {ego:.0f} km/h (first frame of scene excluded)"
            )
            out[split][key] = {"ego_min_kmh": ego}
            for name, car_only in (("vehicle_ish", False), ("car_only", True)):
                rows = distance_table(split_frames, car_only, ego)
                print_distance_rows(
                    f"split={split} | {key} | {label} | {name}", rows
                )
                out[split][key][name] = rows
    return out


def compute_table3(frames, scene_rows, meta, val_available):
    log("")
    log("=" * 78)
    log("TABLE 3 | highway scenes (scene.description contains 'highway')")
    if not val_available:
        log("  unavailable (val split not loaded)")
        return {"available": False}

    val_rows = [row for row in scene_rows if row["split"] == "val"]
    highway_rows = [row for row in val_rows if row["highway"]]
    log(
        f"  (i) val highway: {len(highway_rows)} scenes / {len(val_rows)} val scenes, "
        f"{int(sum(r['frames'] for r in highway_rows))} frames / "
        f"{meta['split_totals']['val']['frames']} val frames"
    )

    highway_frames = [f for f in select_split(frames, "val") if f["highway"]]
    out = {
        "available": True,
        "val_highway_scenes": len(highway_rows),
        "val_scenes": len(val_rows),
        "val_highway_frames": int(sum(r["frames"] for r in highway_rows)),
        "val_frames": meta["split_totals"]["val"]["frames"],
    }
    for name, car_only in (("vehicle_ish", False), ("car_only", True)):
        n_speed = 0
        n_d30 = 0
        n_ego = 0
        for frame in highway_frames:
            if not any(matches(box, car_only) for box in frame["boxes"]):
                continue
            n_speed += 1
            if not any(
                matches(box, car_only) and box["d_m"] <= 30.0 + EPS
                for box in frame["boxes"]
            ):
                continue
            n_d30 += 1
            v_ego = frame["v_ego_kmh"]
            if v_ego is not None and v_ego >= 50.0 - EPS:
                n_ego += 1
        out[name] = {
            "frames_speed_ge_50": n_speed,
            "frames_speed_ge_50_and_d_le_30": n_d30,
            "frames_speed_ge_50_d_le_30_ego_ge_50": n_ego,
        }
        log(
            f"  (ii) {name}: >=50 km/h {n_speed} frames | +d<=30 m {n_d30} frames"
            f" | +v_ego>=50 {n_ego} frames"
        )
    return out


def compute_table4(frames, scene_rows, meta, val_available):
    log("")
    log("=" * 78)
    log("TABLE 4 | top 10 scenes by eligible frames (>=50 km/h, d<=30 m, v_ego>=50) | val")
    if not val_available:
        log("  unavailable (val split not loaded)")
        return {"available": False}

    val_frames = select_split(frames, "val")
    val_total = meta["split_totals"]["val"]["frames"]
    info_by_token = {row["token"]: row for row in scene_rows}
    out = {"available": True}
    for name, car_only in (("vehicle_ish", False), ("car_only", True)):
        counts = defaultdict(int)
        for frame in val_frames:
            eligible = any(
                matches(box, car_only) and box["d_m"] <= 30.0 + EPS
                for box in frame["boxes"]
            )
            if not eligible:
                continue
            v_ego = frame["v_ego_kmh"]
            if v_ego is None or v_ego < 50.0 - EPS:
                continue
            counts[frame["scene_token"]] += 1
        total_eligible = int(sum(counts.values()))
        rows = []
        for token, n_frames in counts.items():
            info = info_by_token[token]
            rows.append(
                {
                    "scene": info["name"],
                    "scene_token": token,
                    "highway": info["highway"],
                    "frames": n_frames,
                    "pct_of_eligible_frames": round(
                        100.0 * n_frames / total_eligible, 2
                    )
                    if total_eligible
                    else 0.0,
                    "pct_of_val_frames": round(100.0 * n_frames / val_total, 3)
                    if val_total
                    else 0.0,
                    "scene_val_frames": info["frames"],
                }
            )
        rows.sort(key=lambda row: (-row["frames"], row["scene"]))
        out[name] = {"total_eligible_frames": total_eligible, "scenes": rows}
        log("")
        log(f"  {name}: {total_eligible} eligible frames over {len(rows)} scenes")
        log(
            f"  {'#':>2} {'scene':<12} {'hw':>5} {'frames':>7} "
            f"{'%elig':>7} {'%val':>6}"
        )
        for rank, row in enumerate(rows[:10], start=1):
            log(
                f"  {rank:>2} {row['scene']:<12} {str(row['highway']):>5} "
                f"{row['frames']:>7} {row['pct_of_eligible_frames']:>7.2f} "
                f"{row['pct_of_val_frames']:>6.3f}"
            )
    return out


def guarded(label, fn, *args):
    try:
        return fn(*args)
    except Exception:
        log(f"{label} FAILED")
        traceback.print_exc()
        return {"error": traceback.format_exc()}


def main():
    started = time.time()
    log("os.listdir('/kaggle/input'):", sorted(os.listdir(INPUT_DIR)))

    devkit = import_devkit()
    if devkit is None:
        install_devkit_no_deps()
        devkit = import_devkit()

    devkit_val_set = None
    velocity_source = "fallback_python"
    devkit_scan_failed = False

    root = find_dataroot()
    log("dataroot:", root)

    counters = defaultdict(int)
    frames = None
    scene_rows = None
    n_samples_total = 0
    scan_seconds = 0.0

    if devkit is not None:
        NuScenes, _Box, val_names = devkit
        devkit_val_set = set(val_names) if val_names else None
        try:
            nusc = NuScenes(version=VERSION, dataroot=root, verbose=False)
            log(
                "devkit tables:",
                {
                    name: len(getattr(nusc, name))
                    for name in ("scene", "sample", "sample_annotation")
                },
            )
            log(f"devkit val split: {len(devkit_val_set)} scene names")
            frames, scene_rows, n_samples_total, scan_seconds = scan_devkit(
                nusc, devkit_val_set, counters
            )
            velocity_source = "devkit"
        except Exception:
            log("devkit scan failed, falling back to pure python")
            traceback.print_exc()
            devkit_scan_failed = True

    if frames is None:
        velocity_source = "fallback_python"
        counters = defaultdict(int)
        val_set = download_val_split()
        if val_set is None and devkit_val_set is not None:
            log("using val list imported from devkit instead of download")
            val_set = devkit_val_set
        if val_set is not None:
            log(f"val split: {len(val_set)} scene names")
        else:
            log("val split unavailable: scanning all keyframes only")
        frames, scene_rows, n_samples_total, scan_seconds = scan_fallback(
            root, val_set, counters
        )
    else:
        val_set = devkit_val_set

    val_available = val_set is not None
    meta = build_meta(scene_rows, frames, n_samples_total, counters, scan_seconds)
    log(
        f"scan done: {meta['n_samples_total']} frames / {meta['n_scenes_total']} scenes | "
        f"{meta['frames_with_eligible_box']} with >=1 box >=50 km/h | "
        f"counters={dict(counters)}"
    )
    log(
        f"velocity_source={velocity_source} val_split_available={val_available} "
        f"devkit_scan_failed={devkit_scan_failed}"
    )

    control = guarded("control_row", compute_control_row, frames)
    breakdown = guarded(
        "split_breakdown", compute_split_breakdown, frames, meta, val_available
    )
    tables = {
        "table1": guarded("table1", compute_table1, frames, val_available),
        "table2": guarded("table2", compute_table2, frames, val_available),
        "table3": guarded("table3", compute_table3, frames, scene_rows, meta, val_available),
        "table4": guarded("table4", compute_table4, frames, scene_rows, meta, val_available),
    }

    payload = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE"),
        "kernel": KERNEL_ID,
        "version": VERSION,
        "dataroot": root,
        "velocity_source": velocity_source,
        "val_split_available": val_available,
        "devkit_scan_failed": devkit_scan_failed,
        "definition": {
            "split": (
                "all keyframes; val = nuscenes.utils.splits.val; train = all "
                "scenes not in val (only for cross-check, never eval)"
            ),
            "d": (
                "min BEV distance from the LIDAR_TOP origin of the current "
                "keyframe to the 4 footprint corners, in LiDAR frame; only "
                "boxes whose center has x > 0 in LiDAR frame"
            ),
            "d_legacy": (
                "BEV distance of the box center to the LIDAR origin, only "
                "boxes with x > 0 in LiDAR frame (old table definition)"
            ),
            "v_box_kmh": "||velocity_global|| * 3.6",
            "v_velocity_global": (
                "devkit box_velocity when importable; otherwise (p_next - "
                "p_prev) / ((t_next - t_prev)/1e6) with max_time_diff 0.5 s "
                "and 2x allowance for the centered difference"
            ),
            "v_ego_kmh": (
                "||ego_pose(t)[:2] - ego_pose(t-1)[:2]|| / 0.5 s inside the "
                "same scene; first keyframe of a scene has null and is "
                "excluded from ego filters"
            ),
            "vehicle_classes": VEHICLE_CLASSES,
            "vehicle_categories": sorted(NAME_MAPPING),
            "car_only": CAR_CATEGORY,
            "box_speed_threshold_kmh": BOX_SPEED_KMH,
            "distance_ladder_m": list(DISTANCES_M),
            "ego_thresholds_kmh": list(EGO_THRESHOLDS_KMH),
            "legacy_expected": {
                "boxes": LEGACY_EXPECTED_BOXES,
                "frames": LEGACY_EXPECTED_FRAMES,
            },
        },
        "totals": meta,
        "control_row": control,
        "split_breakdown": breakdown,
        "tables": tables,
        "frames": frames,
    }

    try:
        with open(OUT_PATH, "w") as handle:
            json.dump(payload, handle, indent=1)
        log("wrote", OUT_PATH, f"({os.path.getsize(OUT_PATH)} bytes)")
    except Exception:
        log("writing eligibility.json FAILED")
        traceback.print_exc()

    log("elapsed_s:", round(time.time() - started, 1))
    log("TICKET18_OK")


if __name__ == "__main__":
    main()
