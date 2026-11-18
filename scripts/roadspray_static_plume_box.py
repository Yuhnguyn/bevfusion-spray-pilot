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
# Nua chieu dai than xe, do theo chieu chuyen dong. Khong dung nguong chieu cao
# lam cue: xe thap (VW Golf cao ~1,45 m) khong co diem nao tren muc plume 1,5 m,
# nen cue cu cho ra 0 frame voi ca 171 bag Golf `[DO] 2026-11-18`.
# Crafter 3,5 m lay tu chinh du lieu (cue chieu cao cho rear = car_range - 3,5 m
# tren 54 bag); Golf 2,15 m tu chieu dai xe 4,26 m.
OBJECT_HALF_LENGTH_M = {"Crafter": 3.5, "Golf": 2.15}
DEFAULT_HALF_LENGTH_M = 2.5
TRACK_MAX_AGE_S = 0.30
BOX_LENGTHS_M = (2.8, 5.0, 8.6, 12.0, 20.0)
MAX_BOX_LENGTH_M = max(BOX_LENGTHS_M)
# Cat lat cu ly de pha "chain doc tia": DBSCAN cua paper chay tren (az, el)
# KHONG co chieu cu ly, nen hai diem cung tia cach nhau 5 m va 20 m van la
# hang xom -> ca ong plume dinh thanh mot cum. Paper do o MOT cu ly co dinh
# ("object distance of 25 m ... distinct and stable clusters are observed"),
# nen cat lat la cach tai lap dung dieu kien do.
SLICE_WIDTHS_M = (1.0, 1.5, 2.5, 4.0, 6.0)
CONTROL_SLICE_M = 2.5


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


def car_track(bag_path: str, to_velodyne: np.ndarray,
              expected_speed_kmh: float | None = None) -> np.ndarray:
    """Chon track cua **xe doi tuong** trong stream object cua ibeo.

    Khong dua vao nhan `ns`: `[DO] 2026-11-18` cung mot chiec VW Crafter duoc
    ibeo goi la `Car` o 100 km/h nhung la `Truck` o 50 km/h, va bag 50 km/h
    khong co mau `Car` nao. Thay vao do dung **toc do da biet tu
    `meta_data_measurement.xlsx`**: ego do nen |d(range)/dt| cua xe doi tuong
    dung bang `object_velocity`; chon track co range-rate gan nhat voi gia tri
    do va nhieu mau nhat. Track tinh (reference target) bi loai vi range-rate ~0.

    Tra ve (N, 4): t, x, y, z trong khung `velodyne`.
    """
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore

    typestore = get_typestore(Stores.ROS1_NOETIC)
    tracks: dict[tuple[str, int], list[tuple[float, float, float, float]]] = {}
    with Reader(bag_path) as reader:
        for conn, stamp, raw in reader.messages():
            if conn.topic != "/front_ibeo_lux/as_tx/objects":
                continue
            msg = typestore.deserialize_ros1(raw, conn.msgtype)
            for marker in msg.markers:
                if marker.type != 5:
                    continue
                position = marker.pose.position
                mapped = to_velodyne @ np.array(
                    [position.x, position.y, position.z, 1.0])
                tracks.setdefault((marker.ns, marker.id), []).append(
                    (stamp / 1e9, mapped[0], mapped[1], mapped[2]))

    best: tuple[float, np.ndarray] | None = None
    for samples in tracks.values():
        # Track rac cua ibeo chi co 4-6 mau; track that di het cuoc xe chay co
        # 50-70 mau. `[DO] 2026-11-18`: chon theo score gan nhat tung vớ phai
        # track 6 mau (rate 100,3 km/h) thay vi track that 51 mau (104,6 km/h)
        # => so cum bi day len ~1,4x. Vi vay: loc theo tolerance roi chon track
        # NHIEU MAU NHAT.
        if len(samples) < 10:
            continue
        array = np.array(sorted(samples))
        delta_t = np.diff(array[:, 0])
        valid = delta_t > 1e-3
        if not valid.any():
            continue
        ranges = np.hypot(array[:, 1], array[:, 2])
        rate = float(np.median(np.diff(ranges)[valid] / delta_t[valid]))
        score = abs(abs(rate) - expected_speed_kmh / 3.6) \
            if expected_speed_kmh else abs(rate)
        if expected_speed_kmh and score > 0.4 * expected_speed_kmh / 3.6:
            continue
        if best is None or array.shape[0] > best[1].shape[0] or (
                array.shape[0] == best[1].shape[0] and score < best[0]):
            best = (score, array)
    return best[1] if best is not None else np.empty((0, 4))


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
    if args.limit:
        names = names[: args.limit]
    print(f"bag duoc chon: {len(names)} (loc chieu bang hinh hoc)", flush=True)

    tmp_dir = Path(".scratch/roadspray-cal/tmp/bags")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261118)
    started = time.time()
    done = 0
    approaching = 0
    receding = 0
    with args.out.open("a") as handle:
        for name in names:
            bag_name = Path(name).name
            info = meta.get(bag_name, {})
            archive.extract(name, tmp_dir)
            bag_path = tmp_dir / bag_name
            Path(tmp_dir / name).replace(bag_path)
            clouds, stamps = read_lidar(str(bag_path))
            track = car_track(str(bag_path), to_velodyne,
                              info.get("speed_kmh"))
            bag_path.unlink()
            if track.shape[0] < 5 or not clouds:
                continue
            # Chieu xe phai quyet dinh bang HINH HOC, khong bang metadata:
            # plume nam SAU xe, chi nhin thay khi xe dang ROI XA ego (ego thay
            # duoi xe). `[DO] 2026-11-18`: cot `object_direction` khong nhat
            # quan giua chien dich Crafter va Golf — bag Golf
            # 2021-09-07-15-45-11 co direction=+1 nhung track 45,4 -> 11,2 m
            # (tien lai gan => ego thay mat truoc, plume bi che).
            track_t = track[:, 0]
            track_r = np.hypot(track[:, 1], track[:, 2])
            delta_t = np.diff(track_t)
            valid_t = delta_t > 1e-3
            if not valid_t.any():
                continue
            range_rate = float(np.median(np.diff(track_r)[valid_t] / delta_t[valid_t]))
            if range_rate <= 0.0:
                approaching += 1
                continue
            receding += 1
            # Huong chuyen dong cua xe, chieu len mat phang (x, y) cua ego.
            motion = track[-1, 1:3] - track[0, 1:3]
            norm = float(np.linalg.norm(motion))
            if norm < 1e-6:
                continue
            motion = motion / norm
            lateral_dir = np.array([-motion[1], motion[0]])
            half_length = OBJECT_HALF_LENGTH_M.get(
                str(info.get("object_name")), DEFAULT_HALF_LENGTH_M)
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
                centre_s = float(centre[:2] @ motion)
                centre_t = float(centre[:2] @ lateral_dir)
                rear = centre_s - half_length
                front = centre_s + half_length

                az, el = angular_coords(cloud)
                ranges = np.linalg.norm(cloud[:, :3], axis=1)
                key = cloud[:, 3].astype(np.int64) * 1024 + np.floor(
                    (az + 180.0) / AZ_BIN_DEG).astype(np.int64)
                tolerance = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
                residual = (ranges <= MAX_RANGE_M) & (
                    (lut_obs[key] < MIN_BG_OBS)
                    | (np.abs(ranges - lut_median[key]) > tolerance))
                residual &= height > H_ABOVE_M

                along_values = cloud[:, :2] @ motion
                lateral_values = cloud[:, :2] @ lateral_dir
                by_lateral = np.abs(lateral_values - centre_t) <= BOX_WIDTH_M / 2.0
                by_height = height <= BOX_HEIGHT_M
                base = residual & by_lateral & by_height
                behind = base & (along_values <= rear) \
                    & (along_values >= rear - MAX_BOX_LENGTH_M)
                ahead = base & (along_values >= front) \
                    & (along_values <= front + MAX_BOX_LENGTH_M)
                depth_values = rear - along_values

                def slice_clusters(mask: np.ndarray, width: float) -> list[dict]:
                    """Gom cum rieng trong tung lat do sau, tra ve moi cum + do sau."""
                    found: list[dict] = []
                    selected_any = np.nonzero(mask)[0]
                    if selected_any.size == 0:
                        return found
                    depths = depth_values[selected_any]
                    capsule = np.floor(depths / width).astype(np.int64)
                    for index_slice in np.unique(capsule):
                        members_slice = selected_any[capsule == index_slice]
                        if members_slice.size < MIN_PTS:
                            continue
                        labels = angular_dbscan(az[members_slice], el[members_slice])
                        n_labels = int(labels.max()) + 1 if labels.size else 0
                        for label in range(n_labels):
                            members = members_slice[labels == label]
                            xyz = cloud[members, :3]
                            found.append({
                                "depth": round(float(depth_values[members].mean()), 2),
                                "n": int(members.size),
                                "range": round(float(np.linalg.norm(xyz.mean(axis=0))), 2),
                                "h": round(float(height[members].mean()), 2),
                                "intensity": round(float(cloud[members, 4].mean()), 2),
                            })
                    return found

                rear_value = round(float(rear), 2)
                rear_by_width = {
                    str(width): slice_clusters(behind, width) for width in SLICE_WIDTHS_M
                }
                front_control = slice_clusters(ahead, CONTROL_SLICE_M)
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
                    "lateral_centre": round(centre_t, 2),
                    "half_length": half_length,
                    "n_residual": int(residual.sum()),
                    "rear_by_width": rear_by_width,
                    "front_control": front_control,
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
    print(f"xong {done} bag trong {time.time() - started:.0f}s -> {args.out}", flush=True)
    print(f"chieu: receding={receding} (do) / approaching={approaching} (bo, plume bi che)",
          flush=True)


if __name__ == "__main__":
    main()
