"""Do cum spray trong HOP SAU DUOI XE tren RoadSpray `*_static` (label-free).

Cach lam bam theo Paper A + reference implementation (openMSL/sl-1-2):

* Paper A §II: *"The initialization of clusters is restricted to the vehicle
  trajectory and no clusters are spawned randomly in the scene."*
* Paper A §III-B: so cum duoc dem trong **"spray filter region behind the
  vehicle"**, roi chia cho ti le `do dai vung / quang xe di 1 scan`, nen **do dai
  vung tu trieu tieu** trong ket qua chuan hoa.
* `define_spray_volumes()` (code tac gia): hop ngay sau duoi xe,
  `width = 3.4 m`, `height = 1.5 m`, `length = |v| * update_cycle_time`.

Nho khoanh hop hep sau duoi xe ma loai duoc cay coi ben duong **bang rang buoc
hinh hoc** thay vi nguong doan — do la ly do khong dem ca khung hinh.

Ba thu duoc do bang du lieu, khong gia dinh:

1. **Quy dao xe** — `/front_ibeo_lux/as_tx/objects`, marker `ns == 'Car'`, doi ve
   khung `velodyne` bang transform tinh trong `meta_data_dataset.json`
   (khong dung TF cua bag: `tf2_msgs` khong co trong typestore).
2. **Mat duoi xe** — van cao ~2,6 m, plume theo paper cao <= 1,5 m, nen diem cao
   hon `CAR_CUE_HEIGHT_M` chi co the thuoc than xe; diem cue xa nhat ve phia sau
   chinh la mat duoi.
3. **Chieu di** — `object_direction`: `+1` = cung chieu ego (ego thay DUOI xe,
   plume huong ve ego); `-1` = nguoc chieu (ego thay mat truoc, plume bi che).
   `[DO] 2026-11-18`: bag dir=+1 cho y 29,5 -> 139,1 m; bag dir=-1 cho
   y 130,2 -> 20,3 m. Script chi do tren `direction == +1`.

Moi frame gom cum **mot lan** tren vung hop dai nhat `BOX_LENGTHS_M[-1]`; moi cum
duoc ghi kem `depth` = khoang cach sau mat duoi, nen so cum cho moi do dai L
tinh duoc offline. Cung mot lan gom cum do **ca hop doi chung phia truoc xe**
(vung le ra khong co spray) de do nen nhieu.

Su dung:
    python scripts/roadspray_static_plume_box.py --bags A.bag,B.bag
    python scripts/roadspray_static_plume_box.py --speed 100 --water 1
"""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from pathlib import Path

import numpy as np

try:  # chay nhu script (scripts/ trong sys.path) hoac import tu repo root
    from roadspray_static_clusters import (
    AZ_BIN_DEG,
    H_ABOVE_M,
    MAX_RANGE_M,
    MIN_BG_OBS,
    MIN_PTS,
    RANGE_TOL_FRAC,
    RANGE_TOL_M,
    angular_coords,
    angular_dbscan,
    background_lookup,
    fit_ground_plane,
    height_above_plane,
        measurement_meta,
    )
except ImportError:  # pragma: no cover - duong import tu repo root
    from scripts.roadspray_static_clusters import (
        AZ_BIN_DEG,
        H_ABOVE_M,
        MAX_RANGE_M,
        MIN_BG_OBS,
        MIN_PTS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        angular_dbscan,
        background_lookup,
        fit_ground_plane,
        height_above_plane,
        measurement_meta,
    )

# --- hop spray theo reference implementation cua paper ---------------------
BOX_WIDTH_M = 3.4
BOX_HEIGHT_M = 1.5
CAR_CUE_HEIGHT_M = 1.6
CAR_CUE_MAX_HEIGHT_M = 3.4
TRACK_MAX_AGE_S = 0.30
BOX_LENGTHS_M = (2.8, 5.0, 8.6, 12.0, 20.0)
MAX_BOX_LENGTH_M = max(BOX_LENGTHS_M)


def pose_matrix(params: dict) -> np.ndarray:
    roll, pitch, yaw = params["roll"], params["pitch"], params["yaw"]
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    matrix = np.eye(4)
    matrix[:3, :3] = np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])
    matrix[:3, 3] = [params["x"], params["y"], params["z"]]
    return matrix


def sensor_to_velodyne(meta_path: Path) -> np.ndarray:
    """Ma tran doi tu khung `ibeo_lux_front` sang khung `velodyne`."""
    meta = json.loads(meta_path.read_text())
    by_topic = {sensor["ros_topic"]: sensor for sensor in meta["sensors"]}
    velodyne = pose_matrix(by_topic["/velodyne_points"]["tf_from_reference_point"])
    ibeo = pose_matrix(by_topic["/front_ibeo_lux"]["tf_from_reference_point"])
    return np.linalg.inv(velodyne) @ ibeo


def read_lidar(path: str) -> tuple[list[np.ndarray], np.ndarray]:
    """Doc `/velodyne_points`: list (N, 5) x,y,z,ring,intensity va stamp (s)."""
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore

    typestore = get_typestore(Stores.ROS1_NOETIC)
    clouds: list[np.ndarray] = []
    stamps: list[float] = []
    with Reader(path) as reader:
        for conn, stamp, raw in reader.messages():
            if conn.topic != "/velodyne_points":
                continue
            msg = typestore.deserialize_ros1(raw, conn.msgtype)
            data = np.frombuffer(msg.data, dtype=np.uint8)
            cloud = data.reshape(-1, msg.point_step)
            xyz = cloud[:, 0:12].copy().view(np.float32).reshape(-1, 3)
            ring = cloud[:, 20:22].copy().view(np.uint16).reshape(-1, 1)
            intensity = cloud[:, 16:20].copy().view(np.float32).reshape(-1, 1)
            clouds.append(np.hstack([xyz, ring.astype(np.float32), intensity]))
            stamps.append(stamp / 1e9)
    return clouds, np.array(stamps)


def car_track(bag_path: str, to_velodyne: np.ndarray) -> np.ndarray:
    """Doc marker `ns == 'Car'`, tra ve (N, 4): t, x, y, z trong khung velodyne."""
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore

    typestore = get_typestore(Stores.ROS1_NOETIC)
    rows: list[tuple[float, float, float, float]] = []
    with Reader(bag_path) as reader:
        for conn, stamp, raw in reader.messages():
            if conn.topic != "/front_ibeo_lux/as_tx/objects":
                continue
            msg = typestore.deserialize_ros1(raw, conn.msgtype)
            for marker in msg.markers:
                if marker.type != 5 or marker.ns != "Car":
                    continue
                position = marker.pose.position
                mapped = to_velodyne @ np.array(
                    [position.x, position.y, position.z, 1.0])
                rows.append((stamp / 1e9, mapped[0], mapped[1], mapped[2]))
    rows.sort()
    return np.array(rows) if rows else np.empty((0, 4))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="data/roadspray/Crafter_static.zip",
                        type=Path)
    parser.add_argument("--xlsx", default="data/roadspray/meta_data_measurement.xlsx",
                        type=Path)
    parser.add_argument("--meta", default="data/roadspray/meta_data_dataset.json",
                        type=Path)
    parser.add_argument("--out",
                        default=".scratch/roadspray-cal/tmp/plume_box.jsonl",
                        type=Path)
    parser.add_argument("--bags", default="")
    parser.add_argument("--speed", type=int, default=0)
    parser.add_argument("--water", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    to_velodyne = sensor_to_velodyne(args.meta)
    ego_forward = (to_velodyne @ np.array([1.0, 0.0, 0.0, 1.0]))[:3] \
        - (to_velodyne @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
    ego_forward /= np.linalg.norm(ego_forward)
    axis = int(np.argmax(np.abs(ego_forward)))  # truc chinh cua ego trong khung velodyne
    lateral_axis = 1 - axis if axis in (0, 1) else 0
    print(f"ego forward trong khung velodyne = {np.round(ego_forward, 3)}, "
          f"truc doc = {axis}, truc ngang = {lateral_axis}", flush=True)

    meta = measurement_meta(args.xlsx)
    archive = zipfile.ZipFile(args.zip)
    names = sorted(n for n in archive.namelist() if n.endswith(".bag"))
    if args.bags:
        wanted = {item.strip() for item in args.bags.split(",") if item.strip()}
        names = [n for n in names if Path(n).name in wanted]
    if args.speed:
        names = [n for n in names
                 if meta.get(Path(n).name, {}).get("speed_kmh") == args.speed]
    if args.water:
        names = [n for n in names
                 if meta.get(Path(n).name, {}).get("itr_after_water") == args.water]
    names = [n for n in names
             if meta.get(Path(n).name, {}).get("direction") == 1]
    if args.limit:
        names = names[: args.limit]
    print(f"bag duoc chon: {len(names)} (direction=+1)", flush=True)

    tmp_dir = Path(".scratch/roadspray-cal/tmp/bags")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261118)
    started = time.time()
    done = 0
    with args.out.open("a") as handle:
        for name in names:
            bag_name = Path(name).name
            info = meta.get(bag_name, {})
            archive.extract(name, tmp_dir)
            bag_path = tmp_dir / bag_name
            Path(tmp_dir / name).replace(bag_path)
            clouds, stamps = read_lidar(str(bag_path))
            track = car_track(str(bag_path), to_velodyne)
            bag_path.unlink()
            if track.shape[0] < 5 or not clouds:
                continue
            lut_median, lut_obs, _ = background_lookup(clouds)
            coef = fit_ground_plane(clouds[len(clouds) // 2], rng)
            if coef is None:
                print(f"  !! khong fit duoc mat duong: {bag_name}", flush=True)
                continue
            bag_records = []
            for index, cloud in enumerate(clouds):
                stamp = stamps[index]
                nearest = int(np.argmin(np.abs(track[:, 0] - stamp)))
                if abs(track[nearest, 0] - stamp) > TRACK_MAX_AGE_S:
                    continue
                centre = track[nearest, 1:4]
                height = height_above_plane(cloud, coef)
                cue = np.nonzero((height > CAR_CUE_HEIGHT_M)
                                 & (height < CAR_CUE_MAX_HEIGHT_M))[0]
                if cue.size < 8:
                    continue
                lateral = cloud[cue, lateral_axis] - centre[lateral_axis]
                longitudinal = cloud[cue, axis] - centre[axis]
                keep = (np.abs(lateral) < 2.5) & (np.abs(longitudinal) < 4.0)
                if keep.sum() < 8:
                    continue
                cue_members = cue[keep]
                lateral_centre = float(np.median(cloud[cue_members, lateral_axis]))
                along = cloud[cue_members, axis]
                rear = float(along.min())
                front = float(along.max())

                az, el = angular_coords(cloud)
                ranges = np.linalg.norm(cloud[:, :3], axis=1)
                key = cloud[:, 3].astype(np.int64) * 1024 + np.floor(
                    (az + 180.0) / AZ_BIN_DEG).astype(np.int64)
                tolerance = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
                residual = (ranges <= MAX_RANGE_M) & (
                    (lut_obs[key] < MIN_BG_OBS)
                    | (np.abs(ranges - lut_median[key]) > tolerance))
                residual &= height > H_ABOVE_M

                by_lateral = np.abs(cloud[:, lateral_axis] - lateral_centre) \
                    <= BOX_WIDTH_M / 2.0
                by_height = height <= BOX_HEIGHT_M
                along_values = cloud[:, axis]
                behind = (residual & by_lateral & by_height
                          & (along_values <= rear)
                          & (along_values >= rear - MAX_BOX_LENGTH_M))
                ahead = (residual & by_lateral & by_height
                         & (along_values >= front)
                         & (along_values <= front + MAX_BOX_LENGTH_M))
                selected = np.nonzero(behind | ahead)[0]
                clusters: list[dict] = []
                if selected.size >= MIN_PTS:
                    labels = angular_dbscan(az[selected], el[selected])
                    n_labels = int(labels.max()) + 1 if labels.size else 0
                    for label in range(n_labels):
                        members = selected[labels == label]
                        xyz = cloud[members, :3]
                        centroid_along = float(xyz[:, axis].mean())
                        is_behind = centroid_along <= rear
                        clusters.append({
                            "side": "rear" if is_behind else "front",
                            "n": int(members.size),
                            "depth": round(abs(rear - centroid_along), 2)
                            if is_behind else round(abs(centroid_along - front), 2),
                            "range": round(float(np.linalg.norm(xyz.mean(axis=0))), 2),
                            "h": round(float(height[members].mean()), 2),
                            "intensity": round(float(cloud[members, 4].mean()), 2),
                        })
                bag_records.append({
                    "bag": bag_name,
                    "frame": index,
                    "stamp": round(stamp, 3),
                    "speed_kmh": info.get("speed_kmh"),
                    "itr_after_water": info.get("itr_after_water"),
                    "object_name": info.get("object_name"),
                    "car_range": round(float(np.hypot(centre[0], centre[1])), 2),
                    "rear": round(rear, 2),
                    "front": round(front, 2),
                    "lateral_centre": round(lateral_centre, 2),
                    "n_residual": int(residual.sum()),
                    "clusters": clusters,
                })
            for record in bag_records:
                handle.write(json.dumps(record) + "\n")
            handle.flush()
            done += 1
            elapsed = time.time() - started
            print(f"[{done}/{len(names)}] {bag_name} frames={len(bag_records)} "
                  f"{info.get('object_name')} {info.get('speed_kmh')}km/h "
                  f"water={info.get('itr_after_water')} "
                  f"{elapsed / done:.1f}s/bag", flush=True)
    print(f"xong {done} bag trong {time.time() - started:.0f}s -> {args.out}",
          flush=True)


if __name__ == "__main__":
    main()
