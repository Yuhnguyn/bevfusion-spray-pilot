"""Do cum spray tren RoadSpray `*_static` (ego do, xe chay qua) — label-free.

Vi sao: `_CLUSTER_VISIBLE_BY_SPEED` hien tai duoc do tren SSPP `cal`, ma `cal`
chua 6/12 scene test (V2, ADR-0006 D2). RoadSpray static la chien dich
calibration cua Paper A va khong nam trong tap danh gia => nguon khong leak.

Nguyen ly tach spray khong can nhan (ego DO nen moi thu la co dinh):

1. **Nen theo range-image.** Voi `(ring, az_bin)` co dinh, tia lidar luon tra ve
   cung mot vat the cung range qua moi frame. Lay median range moi bin tren ca
   bag; diem co `|r - median| > tol` (hoac bin chua du quan sat) la "residual".
2. **Bo mat duong.** Residual van con nhieu diem mat duong ngap nuoc (range
   nhay). Fit mat phang mat duong tu cac diem gan `z=0` (2 vong loai outlier)
   roi bo diem residual thap hon mat phang + `H_ABOVE_M`.
3. **Cum.** DBSCAN tren mat phang `(azimuth, elevation)` voi `eps=0,7°`,
   `minPts=3` — dung tham so Paper A §III-B (L365-374). Cai dat bang cKDTree +
   union-find (khong O(n^2), khong phu thuoc sklearn).

Moi cum duoc ghi lai day du descriptor (so diem, tam, range, extent, do cao
trung binh, intensity) de viec tach "than xe vs spray" lam **offline**, khong
phai chay lai bag.

Su dung:
    python scripts/roadspray_static_clusters.py --limit 3        # thu
    python scripts/roadspray_static_clusters.py                 # ca zip
    python scripts/roadspray_static_clusters.py --out FILE.jsonl
"""

from __future__ import annotations

import argparse

import json
import os
import time
import zipfile
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

# --- tham so Paper A ------------------------------------------------------
ANGULAR_EPS_DEG = 0.7
MIN_PTS = 3
ELEVATION_STEP_DEG = 0.333
# --- tham so rieng cua phep do nay ---------------------------------------
AZ_BIN_DEG = 0.4      # do phan giai range-image
RANGE_TOL_M = 0.7     # dung sai toi thieu (m)
RANGE_TOL_FRAC = 0.02  # dung sai ty le cu ly
MIN_BG_OBS = 5         # so frame toi thieu de tin median cua mot bin
MAX_RANGE_M = 60.0     # vung phan tich (plume cua paper trong 50 m)
H_ABOVE_M = 0.15       # bo diem thap hon mat duong + 0,15 m
GROUND_MAX_RANGE = 45.0


def load_bag_clouds(path: str) -> list[np.ndarray]:
    """Doc `/velodyne_points`, tra ve list (N, 5): x, y, z, ring, intensity."""
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore

    typestore = get_typestore(Stores.ROS1_NOETIC)
    clouds: list[np.ndarray] = []
    with Reader(path) as reader:
        for conn, _t, raw in reader.messages():
            if conn.topic != "/velodyne_points":
                continue
            msg = typestore.deserialize_ros1(raw, conn.msgtype)
            data = np.frombuffer(msg.data, dtype=np.uint8)
            cloud = data.reshape(-1, msg.point_step)
            xyz = cloud[:, 0:12].copy().view(np.float32).reshape(-1, 3)
            ring = cloud[:, 20:22].copy().view(np.uint16).reshape(-1, 1)
            intensity = cloud[:, 16:20].copy().view(np.float32).reshape(-1, 1)
            clouds.append(np.hstack([xyz, ring.astype(np.float32), intensity]))
    return clouds


def angular_coords(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    az = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
    el = np.degrees(np.arctan2(points[:, 2], np.hypot(points[:, 0], points[:, 1])))
    return az, np.round(el / ELEVATION_STEP_DEG) * ELEVATION_STEP_DEG


def angular_dbscan(az: np.ndarray, el: np.ndarray) -> np.ndarray:
    """DBSCAN tren mat phang (az, el), eps do, wrap 360°, minPts co dinh."""
    count = az.size
    if count == 0:
        return np.empty(0, dtype=np.int64)
    a = np.mod(az, 360.0)
    stacked = np.concatenate([
        np.column_stack([a - 360.0, el]),
        np.column_stack([a, el]),
        np.column_stack([a + 360.0, el]),
    ])
    owner = np.tile(np.arange(count), 3)
    tree = cKDTree(stacked)
    neighbours = [
        np.unique(owner[idx])
        for idx in tree.query_ball_point(stacked[count:2 * count], ANGULAR_EPS_DEG)
    ]
    core = np.array([nb.size >= MIN_PTS for nb in neighbours], dtype=bool)
    parent = np.arange(count)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return int(x)

    for i in range(count):
        if not core[i]:
            continue
        for j in neighbours[i]:
            if not core[j]:
                continue
            ri, rj = find(i), find(int(j))
            if ri != rj:
                parent[rj] = ri

    labels = np.full(count, -1, dtype=np.int64)
    root_to_id: dict[int, int] = {}
    for i in range(count):
        if core[i]:
            root = find(i)
            if root not in root_to_id:
                root_to_id[root] = len(root_to_id)
            labels[i] = root_to_id[root]
    for i in range(count):
        if labels[i] >= 0:
            continue
        for j in neighbours[i]:
            if core[j]:
                labels[i] = root_to_id[find(int(j))]
                break
    return labels


def _fit_plane(points: np.ndarray) -> tuple[float, float, float]:
    design = np.column_stack([points[:, 0], points[:, 1], np.ones(len(points))])
    coef, *_ = np.linalg.lstsq(design, points[:, 2], rcond=None)
    return float(coef[0]), float(coef[1]), float(coef[2])


def ground_relative_height(points: np.ndarray,
                           rng: np.random.Generator) -> np.ndarray:
    """Do cao tung diem so voi mat duong, fit bang RANSAC.

    Sensor VLP32 nam cao 1,686 m tren moc sau nen mat duong o ``z ~ -1,69``
    trong khung ``velodyne`` — **khong** phai ``z ~ 0``. RANSAC chon mat phang
    co nhieu inlier nhat trong cac diem thap (``z < 0``, cu ly <= 40 m), rang
    buoc phap tuyen gan thang dung, roi refine bang binh phuong toi thieu.
    """
    height = points[:, 2].copy()
    far = np.linalg.norm(points[:, :3], axis=1)
    candidate = np.nonzero((points[:, 2] < 0.0) & (far <= GROUND_MAX_RANGE))[0]
    if candidate.size < 500:
        return height
    sample = candidate if candidate.size <= 4000 else rng.choice(
        candidate, size=4000, replace=False)
    xyz = points[sample, :3]
    best_count, best_coef = 0, None
    for _ in range(300):
        pick = rng.choice(sample.size, size=3, replace=False)
        coef = _fit_plane(xyz[pick])
        if abs(coef[0]) > 0.35 or abs(coef[1]) > 0.35:
            continue
        residual = np.abs(xyz[:, 2] - (coef[0] * xyz[:, 0]
                                      + coef[1] * xyz[:, 1] + coef[2]))
        count = int((residual < 0.12).sum())
        if count > best_count:
            best_count, best_coef = count, coef
    if best_coef is None or best_count < 500:
        return height
    coef = best_coef
    for _ in range(2):
        residual = np.abs(xyz[:, 2] - (coef[0] * xyz[:, 0]
                                       + coef[1] * xyz[:, 1] + coef[2]))
        keep = residual < 0.12
        if keep.sum() < 500:
            break
        coef = _fit_plane(xyz[keep])
    return points[:, 2] - (coef[0] * points[:, 0] + coef[1] * points[:, 1]
                           + coef[2])


def background_lookup(clouds: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tra ve (lut_median, lut_observations, key_function_inputs) theo bin."""
    keys, ranges = [], []
    for cloud in clouds:
        az, _ = angular_coords(cloud)
        az_bin = np.floor((az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        keys.append(cloud[:, 3].astype(np.int64) * 1024 + az_bin)
        ranges.append(np.linalg.norm(cloud[:, :3], axis=1))
    flat_k = np.concatenate(keys)
    flat_r = np.concatenate(ranges)
    order = np.argsort(flat_k, kind="stable")
    sorted_k, sorted_r = flat_k[order], flat_r[order]
    uniq, starts = np.unique(sorted_k, return_index=True)
    obs = np.diff(np.append(starts, sorted_k.size))
    size = int(uniq.max()) + 1
    lut_median = np.full(size, np.nan)
    lut_obs = np.zeros(size, dtype=np.int32)
    for i in range(uniq.size):
        lut_median[uniq[i]] = np.median(sorted_r[starts[i]:starts[i] + obs[i]])
        lut_obs[uniq[i]] = obs[i]
    return lut_median, lut_obs, uniq


def frame_records(bag_name: str, clouds: list[np.ndarray],
                  meta: dict[str, object],
                  rng: np.random.Generator) -> list[dict]:
    lut_median, lut_obs, _ = background_lookup(clouds)
    records: list[dict] = []
    for index, cloud in enumerate(clouds):
        az, el = angular_coords(cloud)
        ranges = np.linalg.norm(cloud[:, :3], axis=1)
        az_bin = np.floor((az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        key = cloud[:, 3].astype(np.int64) * 1024 + az_bin
        tolerance = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
        residual = (ranges <= MAX_RANGE_M) & (
            (lut_obs[key] < MIN_BG_OBS) | (np.abs(ranges - lut_median[key]) > tolerance)
        )
        selected = np.nonzero(residual)[0]
        record: dict = {
            "bag": bag_name,
            "frame": index,
            "n_cloud": int(cloud.shape[0]),
            "n_residual": int(selected.size),
            "clusters": [],
        }
        record.update(meta)
        if selected.size >= MIN_PTS:
            height = ground_relative_height(cloud, rng)
            above = selected[height[selected] > H_ABOVE_M]
            record["n_above"] = int(above.size)
            if above.size >= MIN_PTS:
                labels = angular_dbscan(az[above], el[above])
                n_labels = int(labels.max()) + 1 if labels.size else 0
                for label in range(n_labels):
                    members = above[labels == label]
                    if members.size == 0:
                        continue
                    xyz = cloud[members, :3]
                    centre = xyz.mean(axis=0)
                    extent = xyz.max(axis=0) - xyz.min(axis=0)
                    member_range = np.linalg.norm(xyz, axis=1)
                    record["clusters"].append({
                        "n": int(members.size),
                        "cx": round(float(centre[0]), 2),
                        "cy": round(float(centre[1]), 2),
                        "cz": round(float(centre[2]), 2),
                        "range": round(float(np.linalg.norm(centre)), 2),
                        "rmin": round(float(member_range.min()), 2),
                        "rmax": round(float(member_range.max()), 2),
                        "ex": round(float(extent[0]), 2),
                        "ey": round(float(extent[1]), 2),
                        "ez": round(float(extent[2]), 2),
                        "h": round(float(height[members].mean()), 2),
                        "intensity": round(float(cloud[members, 4].mean()), 2),
                    })
        records.append(record)
    return records


def measurement_meta(xlsx: Path) -> dict[str, dict]:
    import openpyxl

    book = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    sheet = book.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header = rows[0]
    meta: dict[str, dict] = {}
    for row in rows[1:]:
        if not row[0]:
            continue
        item = dict(zip(header, row))
        meta[str(item["file_name"])] = {
            "object_name": item["object_name"],
            "speed_kmh": item["object_velocity"],
            "direction": item["object_direction"],
            "itr_after_water": item["itr_after_water"],
            "measurement_itr": item["measurement_itr"],
        }
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default="data/roadspray/Crafter_static.zip",
                        type=Path)
    parser.add_argument("--xlsx", default="data/roadspray/meta_data_measurement.xlsx",
                        type=Path)
    parser.add_argument("--out", default=".scratch/roadspray-cal/tmp/static_clusters.jsonl",
                        type=Path)
    parser.add_argument("--limit", type=int, default=0, help="chi lam N bag dau")
    parser.add_argument("--bags", default="", help="danh sach bag ngan cach dau phay")
    parser.add_argument("--only-water", type=int, default=0,
                        help="chi cac bag co itr_after_water = N (0 = tat ca)")
    args = parser.parse_args()

    rng = np.random.default_rng(20261118)
    meta = measurement_meta(args.xlsx)
    archive = zipfile.ZipFile(args.zip)
    names = sorted(n for n in archive.namelist() if n.endswith(".bag"))

    done: set[str] = set()
    if args.out.exists():
        with args.out.open() as handle:
            for line in handle:
                try:
                    done.add(json.loads(line)["bag"])
                except (json.JSONDecodeError, KeyError):
                    continue
    if args.bags:
        wanted = {item.strip() for item in args.bags.split(",") if item.strip()}
        names = [n for n in names if Path(n).name in wanted]
    if args.limit:
        names = names[: args.limit]
    if args.only_water:
        names = [n for n in names
                 if meta.get(Path(n).name, {}).get("itr_after_water") == args.only_water]

    tmp_dir = Path(".scratch/roadspray-cal/tmp/bags")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    written = 0
    with args.out.open("a") as handle:
        for position, name in enumerate(names, start=1):
            bag_name = Path(name).name
            if bag_name in done:
                continue
            payload = meta.get(bag_name, {})
            tmp_bag = tmp_dir / bag_name
            archive.extract(name, tmp_dir)
            os.replace(tmp_dir / name, tmp_bag)
            clouds = load_bag_clouds(str(tmp_bag))
            records = frame_records(bag_name, clouds, payload, rng)
            for record in records:
                handle.write(json.dumps(record) + "\n")
            handle.flush()
            written += 1
            tmp_bag.unlink()
            elapsed = time.time() - started
            rate = elapsed / written
            print(f"[{position:3d}/{len(names)}] {bag_name} frames={len(records)} "
                  f"({payload.get('object_name')} {payload.get('speed_kmh')} km/h "
                  f"water={payload.get('itr_after_water')}) "
                  f"{rate:.1f}s/bag eta={rate * (len(names) - position) / 60:.0f} min",
                  flush=True)
    print(f"done, {written} bag, {time.time() - started:.0f}s -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
