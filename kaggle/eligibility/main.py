import glob
import json
import os
import subprocess
import sys
import time
import traceback

import numpy as np

INPUT_DIR = "/kaggle/input"
WORK_DIR = "/kaggle/working"
OUT_PATH = os.path.join(WORK_DIR, "eligibility.json")

VERSION = "v1.0-trainval"
BOX_SPEED_KMH = 50.0
DISTANCES_M = (10.0, 15.0, 20.0, 30.0, 40.0, 50.0)
EGO_THRESHOLDS_KMH = (None, 30.0, 50.0, 60.0)
EGO_DT_S = 0.5
EPS = 1e-9

# Exactly the vehicle set of ticket 03: the 7 mmdet3d vehicle classes produced
# by NuScenesDataset.NameMapping. Emergency vehicles are not in NameMapping,
# so they were never part of the old numbers either.
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


def log(*parts):
    print(*parts, flush=True)


def run_pip(args):
    cmd = [sys.executable, "-m", "pip", "install", "-q", *args]
    log("$", " ".join(cmd))
    subprocess.run(cmd, check=False)


def devkit_imports_ok():
    try:
        from nuscenes.nuscenes import NuScenes  # noqa: F401
        from nuscenes.utils.geometry_utils import Box  # noqa: F401
        from nuscenes.utils.splits import val as _val  # noqa: F401
        from pyquaternion import Quaternion  # noqa: F401

        return True
    except Exception as exc:
        log("devkit import check failed:", repr(exc))
        return False


def install_devkit():
    run_pip(["nuscenes-devkit"])
    if devkit_imports_ok():
        log("nuscenes-devkit usable after plain install")
        return

    # Kaggle images on Python >= 3.13 cannot build the Shapely<2 pin of devkit
    # 1.1.11 from source; same workaround the dataset gate kernel documented.
    run_pip(
        [
            "shapely==2.0.7",
            "pyquaternion",
            "descartes",
            "scikit-learn",
            "tqdm",
            "opencv-python-headless",
            "matplotlib",
            "Pillow",
        ]
    )
    run_pip(["nuscenes-devkit==1.1.11", "--no-deps"])
    if not devkit_imports_ok():
        raise RuntimeError("nuscenes-devkit is not importable in this image")
    log("nuscenes-devkit usable after fallback install")


def find_dataroot():
    hits = sorted(
        glob.glob(os.path.join(INPUT_DIR, "**", "sample_annotation.json"), recursive=True)
    )
    log("sample_annotation.json hits:")
    for hit in hits:
        log("  ", hit)

    required = (
        "scene.json",
        "sample.json",
        "sample_data.json",
        "sample_annotation.json",
        "ego_pose.json",
        "calibrated_sensor.json",
        "category.json",
    )
    roots = []
    for hit in hits:
        meta_dir = os.path.dirname(hit)
        if os.path.basename(meta_dir) != VERSION:
            continue
        root = os.path.dirname(meta_dir)
        if all(os.path.isfile(os.path.join(meta_dir, name)) for name in required):
            if root not in roots:
                roots.append(root)

    log("candidate dataroots (parent of */v1.0-trainval/):", roots)
    if not roots:
        raise RuntimeError(
            "no nuScenes dataroot found: looked for "
            f"{INPUT_DIR}/**/{VERSION}/sample_annotation.json; hits={hits}"
        )
    return roots[0]


def min_footprint_distance(ann, R_ep, t_ep, R_cs, t_cs, Box, Quaternion):
    """Min BEV distance from the LiDAR origin to the 4 footprint corners."""
    box = Box(
        center=ann["translation"],
        size=ann["size"],
        orientation=Quaternion(ann["rotation"]),
    )
    corners = box.corners()
    ego = R_ep.T @ (corners - t_ep[:, None])
    lidar = R_cs.T @ (ego - t_cs[:, None])
    return float(np.min(np.linalg.norm(lidar[:2], axis=0)))


def scan(nusc, scenes, Box, Quaternion):
    started = time.time()
    box_frames = []
    scene_rows = []
    total_frames = 0
    highway_frames = 0
    highway_scenes = 0
    skipped_nonfinite = 0

    for scene in scenes:
        is_highway = "highway" in scene["description"].lower()
        if is_highway:
            highway_scenes += 1
        frames_in_scene = 0
        prev_pos = None
        token = scene["first_sample_token"]

        while token:
            sample = nusc.get("sample", token)
            if "LIDAR_TOP" not in sample["data"]:
                raise RuntimeError(
                    f"sample {token} has no LIDAR_TOP keyframe: "
                    f"{sorted(sample['data'])}"
                )
            lidar_sd = nusc.get("sample_data", sample["data"]["LIDAR_TOP"])
            pose = nusc.get("ego_pose", lidar_sd["ego_pose_token"])
            cs = nusc.get("calibrated_sensor", lidar_sd["calibrated_sensor_token"])

            R_ep = Quaternion(pose["rotation"]).rotation_matrix
            t_ep = np.asarray(pose["translation"], dtype=float)
            R_cs = Quaternion(cs["rotation"]).rotation_matrix
            t_cs = np.asarray(cs["translation"], dtype=float)

            pos = t_ep[:2].copy()
            if prev_pos is None:
                v_ego = None
            else:
                v_ego = float(np.linalg.norm(pos - prev_pos) / EGO_DT_S * 3.6)
            prev_pos = pos

            boxes = []
            for ann_token in sample["anns"]:
                ann = nusc.get("sample_annotation", ann_token)
                category = ann["category_name"]
                if category not in NAME_MAPPING:
                    continue
                velocity = nusc.box_velocity(ann_token)
                if not np.all(np.isfinite(velocity)):
                    skipped_nonfinite += 1
                    continue
                speed = float(np.linalg.norm(velocity) * 3.6)
                if speed < BOX_SPEED_KMH - EPS:
                    continue
                boxes.append(
                    {
                        "category": category,
                        "class": NAME_MAPPING[category],
                        "speed_kmh": speed,
                        "d_m": min_footprint_distance(
                            ann, R_ep, t_ep, R_cs, t_cs, Box, Quaternion
                        ),
                    }
                )

            frames_in_scene += 1
            total_frames += 1
            if is_highway:
                highway_frames += 1
            if boxes:
                box_frames.append(
                    {
                        "scene": scene["name"],
                        "scene_token": scene["token"],
                        "highway": is_highway,
                        "v_ego_kmh": v_ego,
                        "boxes": boxes,
                    }
                )
            if total_frames % 2000 == 0:
                log(
                    f"scanned {total_frames} frames | {len(box_frames)} with "
                    f">=1 box >=50 km/h | {time.time() - started:.0f}s"
                )
            token = sample["next"]

        scene_rows.append(
            {
                "name": scene["name"],
                "token": scene["token"],
                "description": scene["description"],
                "highway": is_highway,
                "frames": frames_in_scene,
            }
        )

    meta = {
        "val_scenes": len(scenes),
        "val_frames": total_frames,
        "highway_scenes": highway_scenes,
        "highway_frames": highway_frames,
        "frames_with_eligible_box": len(box_frames),
        "skipped_nonfinite_velocity": skipped_nonfinite,
        "scan_seconds": round(time.time() - started, 1),
        "scenes": scene_rows,
    }
    return box_frames, meta


def distance_table(box_frames, car_only, ego_min_kmh):
    rows = []
    for dist in DISTANCES_M:
        n_boxes = 0
        n_frames = 0
        scenes = set()
        for frame in box_frames:
            if ego_min_kmh is not None:
                v_ego = frame["v_ego_kmh"]
                if v_ego is None or v_ego < ego_min_kmh - EPS:
                    continue
            count = 0
            for box in frame["boxes"]:
                if car_only and box["category"] != CAR_CATEGORY:
                    continue
                if box["d_m"] <= dist:
                    count += 1
            if count:
                n_boxes += count
                n_frames += 1
                scenes.add(frame["scene_token"])
        n_scenes = len(scenes)
        rows.append(
            {
                "d_max_m": dist,
                "boxes": n_boxes,
                "frames": n_frames,
                "scenes": n_scenes,
                "frames_per_scene": (n_frames / n_scenes) if n_scenes else 0.0,
            }
        )
    return rows


def print_distance_block(title, rows):
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


def compute_table1(box_frames):
    vehicle = distance_table(box_frames, False, None)
    car = distance_table(box_frames, True, None)
    log("")
    log("=" * 78)
    log("TABLE 1 | box speed >= 50 km/h | d <= 10/15/20/30/40/50 m")
    log("cells: boxes / frames / scenes / frames-per-scene")
    print_distance_block("all vehicle-ish (ticket-03 set)", vehicle)
    print_distance_block("car only", car)
    return {"vehicle_ish": vehicle, "car_only": car}


def compute_table2(box_frames):
    out = {}
    log("")
    log("=" * 78)
    log("TABLE 2 | table 1 with ego-speed filter applied")
    for ego in EGO_THRESHOLDS_KMH:
        key = "no_ego_filter" if ego is None else f"ego_ge_{int(ego)}"
        label = (
            "v_ego: no filter (first frame of scene kept, v_ego = null)"
            if ego is None
            else f"v_ego >= {ego:.0f} km/h (first frame of scene excluded)"
        )
        vehicle = distance_table(box_frames, False, ego)
        car = distance_table(box_frames, True, ego)
        print_distance_block(f"TABLE 2 row {key} | {label} | vehicle-ish", vehicle)
        print_distance_block(f"TABLE 2 row {key} | {label} | car only", car)
        out[key] = {"ego_min_kmh": ego, "vehicle_ish": vehicle, "car_only": car}
    return out


def compute_table3(box_frames, meta):
    highway_frames = [frame for frame in box_frames if frame["highway"]]
    out = {
        "val_scenes": meta["val_scenes"],
        "val_frames": meta["val_frames"],
        "highway_scenes": meta["highway_scenes"],
        "highway_frames": meta["highway_frames"],
    }
    log("")
    log("=" * 78)
    log("TABLE 3 | highway scenes (scene.description contains 'highway')")
    log(
        f"  (i) val highway: {meta['highway_scenes']} scenes / "
        f"{meta['val_scenes']} val scenes, {meta['highway_frames']} frames / "
        f"{meta['val_frames']} val frames"
    )
    for name, car_only in (("vehicle_ish", False), ("car_only", True)):
        n_speed = 0
        n_near = 0
        n_ego = 0
        for frame in highway_frames:
            boxes = [
                box
                for box in frame["boxes"]
                if not car_only or box["category"] == CAR_CATEGORY
            ]
            if not boxes:
                continue
            n_speed += 1
            if not any(box["d_m"] <= 30.0 for box in boxes):
                continue
            n_near += 1
            v_ego = frame["v_ego_kmh"]
            if v_ego is not None and v_ego >= 50.0 - EPS:
                n_ego += 1
        out[name] = {
            "frames_speed_ge_50": n_speed,
            "frames_speed_ge_50_and_d_le_30": n_near,
            "frames_speed_ge_50_d_le_30_ego_ge_50": n_ego,
        }
        log(
            f"  (ii) {name}: >=50 km/h {n_speed} frames | +d<=30 m {n_near} frames"
            f" | +v_ego>=50 {n_ego} frames"
        )
    return out


def scene_rows_table(box_frames, meta, car_only):
    counts = {}
    for frame in box_frames:
        if any(
            (not car_only or box["category"] == CAR_CATEGORY) and box["d_m"] <= 30.0
            for box in frame["boxes"]
        ):
            counts[frame["scene_token"]] = counts.get(frame["scene_token"], 0) + 1
    total_eligible = sum(counts.values())
    info_by_token = {row["token"]: row for row in meta["scenes"]}
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
                ),
                "pct_of_val_frames": round(100.0 * n_frames / meta["val_frames"], 3),
                "scene_val_frames": info["frames"],
            }
        )
    rows.sort(key=lambda row: (-row["frames"], row["scene"]))
    return rows, total_eligible


def compute_table4(box_frames, meta):
    log("")
    log("=" * 78)
    log("TABLE 4 | top 10 scenes by eligible frames (>=50 km/h, d<=30 m)")
    out = {}
    for name, car_only in (("vehicle_ish", False), ("car_only", True)):
        rows, total = scene_rows_table(box_frames, meta, car_only)
        out[name] = {"total_eligible_frames": total, "scenes": rows}
        log("")
        log(f"  {name}: {total} eligible frames over {len(rows)} scenes")
        log(
            f"  {'#':>2} {'scene':<40} {'hw':>3} {'frames':>7} "
            f"{'%elig':>7} {'%val':>6}"
        )
        for rank, row in enumerate(rows[:10], start=1):
            log(
                f"  {rank:>2} {row['scene']:<40} {str(row['highway']):>5} "
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
    install_devkit()

    from nuscenes.nuscenes import NuScenes
    from nuscenes.utils.geometry_utils import Box
    from nuscenes.utils.splits import val as VAL_SCENE_NAMES
    from pyquaternion import Quaternion

    root = find_dataroot()
    log("dataroot:", root)
    nusc = NuScenes(version=VERSION, dataroot=root, verbose=False)
    log(
        "devkit tables:",
        {
            name: len(getattr(nusc, name))
            for name in ("scene", "sample", "sample_annotation")
        },
    )

    scene_by_name = {scene["name"]: scene for scene in nusc.scene}
    missing = [name for name in VAL_SCENE_NAMES if name not in scene_by_name]
    val_scenes = [scene_by_name[name] for name in VAL_SCENE_NAMES if name in scene_by_name]
    log(
        f"val split: {len(val_scenes)}/{len(VAL_SCENE_NAMES)} scenes present | "
        f"missing={missing}"
    )
    if not val_scenes:
        raise RuntimeError("val split empty: scene names do not match the dataset")

    box_frames, meta = scan(nusc, val_scenes, Box, Quaternion)
    log(
        f"scan done: {meta['val_frames']} val frames | "
        f"{meta['frames_with_eligible_box']} with >=1 box >=50 km/h | "
        f"highway {meta['highway_scenes']} scenes / {meta['highway_frames']} frames"
    )

    tables = {
        "table1": guarded("table1", compute_table1, box_frames),
        "table2": guarded("table2", compute_table2, box_frames),
        "table3": guarded("table3", compute_table3, box_frames, meta),
        "table4": guarded("table4", compute_table4, box_frames, meta),
    }

    payload = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE"),
        "kernel": "nguynhuy9669/bevfusion-eligibility",
        "version": VERSION,
        "dataroot": root,
        "definition": {
            "split": "nuScenes devkit val split (nuscenes.utils.splits.val); keyframes only via nusc.sample",
            "d": (
                "min BEV distance from the LIDAR_TOP origin of the current keyframe "
                "to the 4 footprint corners; box moved global->ego with inverse "
                "ego_pose, then ego->LiDAR with inverse calibrated_sensor"
            ),
            "v_box_kmh": "||nusc.box_velocity(ann_token)|| * 3.6",
            "v_ego_kmh": (
                "||ego_pose(t) - ego_pose(t-1)|| / 0.5 s inside the same scene; "
                "first keyframe of a scene has null and is excluded from ego filters"
            ),
            "vehicle_classes": sorted(set(NAME_MAPPING.values())),
            "vehicle_categories": sorted(NAME_MAPPING),
            "car_only": CAR_CATEGORY,
            "box_speed_threshold_kmh": BOX_SPEED_KMH,
            "distance_ladder_m": list(DISTANCES_M),
            "ego_thresholds_kmh": list(EGO_THRESHOLDS_KMH),
        },
        "totals": meta,
        "tables": tables,
        "frames": box_frames,
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


main()
