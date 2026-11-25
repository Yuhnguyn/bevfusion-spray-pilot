#!/usr/bin/env python3
"""Đo **CDF của khoảng cách detection trên 0–50 m** — đúng thước Paper A Fig. 12.

Paper Linnhoff 2022 (arXiv 2212.08558) Fig. 12: hai panel (a) Measured /
(b) Simulated, trục x = *"Detection Distance in m"* 0–50, trục y = CDF chuẩn
hoá 0–1, cho plume của Crafter ở **50 m** với các tốc độ 50–130 km/h. Paper kết
luận hai bên *"show the same trend"* và chỉ nêu lệch định tính: ở 80–110 km/h
detection mô phỏng *"visible at a greater distance"* (mô phỏng xa hơn thật).

Script này áp **đúng** đại lượng đó cho repo: range = ``|p|`` từ gốc khung
velodyne (paper: *"The origin of these plots is the origin of the sensor"*),
CDF chuẩn hoá trên cửa sổ 0–50 m, bin 1 m, tách 3 nhóm tốc độ
(50–70 / 80–110 / 120–130 km/h) và lớp xe. Hai vế **cùng tầng**: detection của
cảm biến — vế thật là residual spray (RoadSpray) hoặc ``label == 2`` (SSPP), vế
sinh là ``RaycastResult.detections``.

Bốn chế độ ghi JSONL (mỗi frame một dòng, histogram range 1 m + metadata), rồi
một chế độ ``aggregate`` dựng CDF/KS/quantile:

    # 1) THẬT — RoadSpray `*_static`, bag xe đang RỜI XA (tái dùng logic T4)
    ... scripts/measure_cdf_over_range.py --mode real-static
    # 2) THẬT — SSPP dynamic, `label == 2`, scene không box (paired với (4))
    # 4) SINH — following: cùng scene/frame với (2), paired
    ... scripts/measure_cdf_over_range.py --mode following
    # 3) SINH — static: ego đứng yên, xe chạy ra xa (tái dùng QĐ14)
    ... scripts/measure_cdf_over_range.py --mode gen-static
    # 5) tổng hợp: CDF 10/20/30/40/50 m, %<10 m, KS, quartile; kèm chẩn đoán
    #    depth sau mặt đuôi (không phải đại lượng paper) và biến thể static
    #    "plume nằm trọn trong 0–50 m" / "chỉ detection sau mặt đuôi"
    ... scripts/measure_cdf_over_range.py --mode aggregate

KHÔNG sửa generator, KHÔNG tune tham số: mọi tham số lấy mặc định production.
Chỉ đo. Ghi chú trung thực:

* **Static không phải hình học của paper.** Paper đo plume của xe ở *50 m cố
  định*; RoadSpray static là ego ĐỖ, xe chạy ra xa 20→200 m, nên range của
  plume trượt theo xe. Vì vậy với static có thêm biến thể "cửa sổ đầy đủ"
  (`rear_range <= 50 m`, plume nằm trọn trong 0–50 m) để so cùng hình học.
* CDF 0–50 m chỉ chuẩn hoá trong cửa sổ; phần detection > 50 m được báo riêng
  (`pct_beyond_50`) — không được bỏ im lặng.
* Không nội suy chỗ thiếu dữ liệu: nhóm nào không đo được thì ghi
  ``KHONG_DO_DUOC``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:  # chạy như script (scripts/ trong sys.path) hoặc import từ repo root
    from roadspray_static_clusters import (
        AZ_BIN_DEG,
        MIN_BG_OBS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        measurement_meta,
    )
    from roadspray_static_depth_profile import (
        BODY_DIMS_M,
        BODY_MARGIN_M,
        HEIGHT_MAX_M,
        HEIGHT_MIN_M,
        INTENSITY_MAX_SPRAY,
        LATERAL_HALF_M,
        MAX_RANGE_EXT_M,
        NEAR_FIELD_M,
        background_lookup_mode,
        fit_ground_plane_ext,
        height_above,
    )
    from roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        TRACK_MAX_AGE_S,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )
except ImportError:  # pragma: no cover - import từ repo root
    from scripts.roadspray_static_clusters import (
        AZ_BIN_DEG,
        MIN_BG_OBS,
        RANGE_TOL_FRAC,
        RANGE_TOL_M,
        angular_coords,
        measurement_meta,
    )
    from scripts.roadspray_static_depth_profile import (
        BODY_DIMS_M,
        BODY_MARGIN_M,
        HEIGHT_MAX_M,
        HEIGHT_MIN_M,
        INTENSITY_MAX_SPRAY,
        LATERAL_HALF_M,
        MAX_RANGE_EXT_M,
        NEAR_FIELD_M,
        background_lookup_mode,
        fit_ground_plane_ext,
        height_above,
    )
    from scripts.roadspray_static_plume_box import (
        DEFAULT_HALF_LENGTH_M,
        OBJECT_HALF_LENGTH_M,
        TRACK_MAX_AGE_S,
        car_track,
        read_lidar,
        sensor_to_velodyne,
    )

# --- tham số phép đo --------------------------------------------------------
# Cửa sổ của paper: 0–50 m, bin 1 m. Histogram lưu rộng 0–250 m để quantile
# KHÔNG bị censor (không nội suy phần thiếu).
WINDOW_M = 50.0
BIN_M = 1.0
HIST_MAX_M = 250.0
RANGE_EDGES = np.arange(0.0, HIST_MAX_M + BIN_M, BIN_M)
N_BINS = RANGE_EDGES.size - 1
# Nhóm tốc độ của paper (Fig. 12 phủ 50–130 km/h).
SPEED_BANDS = (
    ("50-70", (50, 60, 70)),
    ("80-110", (80, 90, 100, 110)),
    ("120-130", (120, 130)),
)
BAND_OF = {speed: label for label, speeds in SPEED_BANDS for speed in speeds}
BAND_ORDER = [label for label, _ in SPEED_BANDS]
# T4/A3 `geom`: loại hộp 3D thân xe (track pose + dims), nới sau 0,2 m.
BODY_BACK_EXTRA_M = 0.2
# Chẩn đoán độ sâu (depth sau mặt đuôi xe) — chỉ để giải thích, KHÔNG phải đại
# lượng của paper; dùng cùng bin 1 m, 0–60 m.
DEPTH_MAX_M = 60.0
DEPTH_EDGES = np.arange(0.0, DEPTH_MAX_M + BIN_M, BIN_M)
# Static: coi là "plume nằm trọn trong cửa sổ paper" khi mặt đuôi xe <= 50 m.
WINDOW_FULL_REAR_M = 50.0
# Following: 3 nhóm tốc độ × 2 lớp × 2 scene = 12 scene (>= 10 theo yêu cầu),
# toàn bộ là scene KHÔNG human box (không nằm trong tập eval D1).
SCENES_PER_CELL = 2
FRAMES_PER_SCENE = 30
GEN_STATIC_SEEDS = 4


# ---------------------------------------------------------------------------
# tiện ích
# ---------------------------------------------------------------------------
def range_hist(values: np.ndarray) -> tuple[list[int], int]:
    """Histogram 1 m của ``|p|``; trả (counts 0–250 m, số điểm >= 250 m)."""
    if values.size == 0:
        return [0] * N_BINS, 0
    inside = values[values < HIST_MAX_M]
    counts, _ = np.histogram(inside, bins=RANGE_EDGES)
    return counts.astype(int).tolist(), int(values.size - inside.size)


def depth_hist(values: np.ndarray) -> tuple[list[int], int, int]:
    """Histogram depth 0–60 m sau mặt đuôi; trả (counts, n_ahead, n_beyond)."""
    if values.size == 0:
        return [0] * (DEPTH_EDGES.size - 1), 0, 0
    inside = values[(values >= 0.0) & (values < DEPTH_MAX_M)]
    counts, _ = np.histogram(inside, bins=DEPTH_EDGES)
    return (counts.astype(int).tolist(), int((values < 0.0).sum()),
            int((values >= DEPTH_MAX_M).sum()))


def band_label(speed: float) -> str:
    return BAND_OF.get(int(round(speed)), "other")


# ---------------------------------------------------------------------------
# 1) THẬT — RoadSpray `*_static`
# ---------------------------------------------------------------------------
def process_static_bag(
    bag_name: str,
    bag_path: str,
    info: dict,
    to_velodyne: np.ndarray,
    rng: np.random.Generator,
    height_max: float,
) -> tuple[list[dict], str]:
    """Đo 1 bag static; trả (records, lý do bỏ nếu có).

    Tái dùng nguyên pipeline T4 (`roadspray_static_depth_profile.process_bag`):
    trừ nền range-image theo mode, RANSAC mặt đường, residual + intensity <= 2,
    loại hộp thân xe, mask ngang ±5 m / cao 0,15–3,0 m. Khác duy nhất: ghi
    **histogram range từ gốc velodyne** thay vì depth sau đuôi xe.
    """
    clouds, stamps = read_lidar(bag_path)
    if not clouds:
        return [], "no_clouds"
    track = car_track(bag_path, to_velodyne, info.get("speed_kmh"))
    if track.shape[0] < 5:
        return [], "no_track"
    delta_t = np.diff(track[:, 0])
    valid_t = delta_t > 1e-3
    if not valid_t.any():
        return [], "no_track_dt"
    track_r = np.hypot(track[:, 1], track[:, 2])
    range_rate = float(np.median(np.diff(track_r)[valid_t] / delta_t[valid_t]))
    if range_rate <= 0.0:          # chỉ đo bag xe đang rời xa
        return [], "approaching"

    motion = track[-1, 1:3] - track[0, 1:3]
    norm = float(np.linalg.norm(motion))
    if norm < 1e-6:
        return [], "no_motion"
    motion = motion / norm
    lateral_dir = np.array([-motion[1], motion[0]])
    half_length = OBJECT_HALF_LENGTH_M.get(
        str(info.get("object_name")), DEFAULT_HALF_LENGTH_M)

    lut_bg, lut_obs = background_lookup_mode(clouds)
    coef = fit_ground_plane_ext(clouds[len(clouds) // 2], rng)
    if coef is None:
        return [], "no_ground"

    length, width, body_height = BODY_DIMS_M.get(
        str(info.get("object_name")), (5.0, 2.0, 2.0))
    records: list[dict] = []
    track_t = track[:, 0]
    track_xyz = track[:, 1:4]
    t_min, t_max = float(track_t[0]), float(track_t[-1])
    for index, cloud in enumerate(clouds):
        stamp = stamps[index]
        if stamp < t_min - TRACK_MAX_AGE_S or stamp > t_max + TRACK_MAX_AGE_S:
            continue
        centre = np.array([
            float(np.interp(stamp, track_t, track_xyz[:, axis]))
            for axis in range(3)
        ])
        centre_s = float(centre[:2] @ motion)
        centre_t = float(centre[:2] @ lateral_dir)
        rear = centre_s - half_length

        height = height_above(coef, cloud)
        ranges = np.linalg.norm(cloud[:, :3], axis=1)
        az, _el = angular_coords(cloud)
        az_bin = np.floor((az + 180.0) / AZ_BIN_DEG).astype(np.int64)
        key = cloud[:, 3].astype(np.int64) * 1024 + az_bin
        tolerance = np.maximum(RANGE_TOL_M, RANGE_TOL_FRAC * ranges)
        residual = (ranges <= MAX_RANGE_EXT_M) & (
            (lut_obs[key] < MIN_BG_OBS)
            | (np.abs(ranges - lut_bg[key]) > tolerance))
        residual &= ranges > NEAR_FIELD_M

        along = cloud[:, :2] @ motion
        lateral = cloud[:, :2] @ lateral_dir
        depth = rear - along
        lateral_rel = np.abs(lateral - centre_t)
        spray_like = cloud[:, 4] <= INTENSITY_MAX_SPRAY
        # --- loại thân xe bằng hình học (--body-box, "geom") ---
        s_rel = along - centre_s
        t_rel = lateral - centre_t
        body = (
            (np.abs(t_rel) <= width / 2.0 + BODY_MARGIN_M)
            & (s_rel >= -length / 2.0 - BODY_MARGIN_M - BODY_BACK_EXTRA_M)
            & (s_rel <= length / 2.0 + BODY_MARGIN_M)
            & (height >= -BODY_MARGIN_M)
            & (height <= body_height + BODY_MARGIN_M)
        )
        spray_like = spray_like & ~body
        behind = (residual & spray_like
                  & (depth >= 0.0) & (depth < 60.0))
        masked = (behind
                  & (height >= HEIGHT_MIN_M) & (height <= height_max)
                  & (lateral_rel <= LATERAL_HALF_M))
        # Biến thể "TẤT CẢ detection trong vùng": KHÔNG ràng buộc `depth >= 0`.
        # Cần biến thể này vì vế sinh (`gen_static`) đo `depth_hist` trên toàn
        # bộ detection; so `masked` (đã lọc depth) với vế sinh là so hai định
        # nghĩa khác nhau — đúng lỗi đã mắc 2026-11-25 (xem
        # docs/measurements/cdf-vs-roadspray-static.md §0).
        region_all = (residual & spray_like
                      & (height >= HEIGHT_MIN_M) & (height <= height_max)
                      & (lateral_rel <= LATERAL_HALF_M))
        sel = np.nonzero(masked)[0]
        sel_all = np.nonzero(region_all)[0]
        hist, beyond = range_hist(ranges[sel])
        dhist, ahead, dbeyond = depth_hist(depth[sel])
        hist_all, beyond_all = range_hist(ranges[sel_all])
        dhist_all, ahead_all, dbeyond_all = depth_hist(depth[sel_all])
        car_range = float(np.hypot(centre[0], centre[1]))
        records.append({
            "scenario": "real_static",
            "bag": bag_name,
            "frame": index,
            "vehicle_class": str(info.get("object_name")),
            "speed_kmh": info.get("speed_kmh"),
            "band": band_label(float(info.get("speed_kmh") or 0)),
            "itr_after_water": info.get("itr_after_water"),
            "measurement_itr": info.get("measurement_itr"),
            "car_range": round(car_range, 2),
            "rear_range": round(car_range - half_length, 2),
            "range_rate_mps": round(range_rate, 2),
            "n_cloud": int(cloud.shape[0]),
            "n_residual": int(residual.sum()),
            "n_spray": int(sel.size),
            "n_spray_all": int(sel_all.size),
            "range_hist": hist,
            "n_beyond_hist": beyond,
            "range_hist_all": hist_all,
            "n_beyond_hist_all": beyond_all,
            "depth_hist_all": dhist_all,
            "n_ahead_of_rear_all": ahead_all,
            "n_ahead_of_rear": ahead,
            "n_depth_beyond_60": dbeyond,
        })
    return records, ""


def build_candidates(
    members: list[str], meta: dict, speed: int
) -> list[str]:
    """Bag ứng viên cho 1 (lớp, tốc độ): ưu tiên `direction == +1`, tên tăng dần."""
    rows = [n for n in members
            if meta.get(Path(n).name, {}).get("speed_kmh") == speed]
    rows.sort(key=lambda n: (
        0 if meta[Path(n).name].get("direction") == 1 else 1, n))
    return rows


def run_real_static(args: argparse.Namespace) -> None:
    meta = measurement_meta(Path(args.xlsx))
    to_velodyne = sensor_to_velodyne(Path(args.meta))
    rng = np.random.default_rng(20261119)
    speeds = [int(v) for v in args.speeds.split(",") if v.strip()]
    tmp_dir = Path(args.tmp)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    rows_out: list[dict] = []
    summary: dict = {}
    started = time.time()
    for vehicle_class, zip_path in (
        ("Crafter", args.crafter_zip), ("Golf", args.golf_zip)
    ):
        if not Path(zip_path).is_file():
            # Golf_static chưa có trong release local; Crafter mới là lớp paper
            # định lượng (Fig. 4/5/7). Bỏ qua lớp thiếu thay vì crash, nhưng in
            # rõ — không được im lặng.
            print(f"  !! BỎ QUA lớp {vehicle_class}: không có {zip_path}",
                  flush=True)
            summary[f"{vehicle_class}_missing"] = str(zip_path)
            continue
        archive = zipfile.ZipFile(zip_path)
        members = sorted(n for n in archive.namelist() if n.endswith(".bag"))
        for speed in speeds:
            valid = 0
            used: list[str] = []
            tried = 0
            for name in build_candidates(members, meta, speed):
                if valid >= args.bags_per_speed or tried >= args.max_candidates:
                    break
                tried += 1
                bag_name = Path(name).name
                if bag_name not in meta:
                    continue
                tmp_bag = tmp_dir / bag_name
                if not tmp_bag.exists():
                    archive.extract(name, tmp_dir)
                    Path(tmp_dir / name).replace(tmp_bag)
                records, why = process_static_bag(
                    bag_name, str(tmp_bag), meta[bag_name], to_velodyne,
                    rng, args.height_max)
                if args.keep_bags is False and tmp_bag.exists():
                    tmp_bag.unlink()
                if not records:
                    print(f"  [{vehicle_class} {speed}] bỏ {bag_name}: {why}",
                          flush=True)
                    continue
                valid += 1
                used.append(bag_name)
                rows_out.extend(records)
                print(f"[{vehicle_class:7s} {speed:3d}] {bag_name} "
                      f"frames={len(records)} valid={valid} "
                      f"{time.time() - started:.0f}s", flush=True)
            summary[f"{vehicle_class}_{speed}"] = {
                "bags": used, "frames": sum(
                    1 for r in rows_out
                    if r["vehicle_class"] == vehicle_class
                    and int(r["speed_kmh"]) == speed),
            }
            if valid == 0:
                print(f"  !! KHÔNG ĐO ĐƯỢC {vehicle_class} {speed} km/h",
                      flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        for record in rows_out:
            handle.write(json.dumps(record) + "\n")
    print(f"xong {len(rows_out)} frame -> {out}", flush=True)


# ---------------------------------------------------------------------------
# 2+4) THẬT + SINH — SSPP dynamic (following), paired từng frame
# ---------------------------------------------------------------------------
def select_scenes(scenes: list[dict]) -> list[dict]:
    """2 scene/(lớp, nhóm tốc độ) trong các scene KHÔNG human box.

    Tất định: trong mỗi ô lấy scene ở tốc độ thấp nhất và cao nhất có sẵn (để
    trải hết bề rộng nhóm), mỗi tốc độ lấy scene đầu theo `rel_path`.
    """
    unboxed = [s for s in scenes if not s["has_box"]]
    picked: list[dict] = []
    for vehicle_class in ("crafter", "golf"):
        for band, speeds in SPEED_BANDS:
            cell = [s for s in unboxed
                    if s["vehicle_class"] == vehicle_class
                    and int(s["speed_kmh"]) in speeds]
            if not cell:
                continue
            for speed in (min(s["speed_kmh"] for s in cell),
                          max(s["speed_kmh"] for s in cell)):
                members = sorted((s for s in cell if s["speed_kmh"] == speed),
                                 key=lambda s: s["rel_path"])
                if members:
                    picked.append(members[0])
    return picked


def _scripts_module(name: str):
    """Import module trong `scripts/` dù chạy từ repo root hay từ `scripts/`."""
    import importlib

    try:
        return importlib.import_module(f"scripts.{name}")
    except ImportError:
        return importlib.import_module(name)


def run_following(args: argparse.Namespace) -> None:
    following_mod = _scripts_module("measure_following_scenario")
    FIXED_SEED = following_mod.FIXED_SEED
    REGION_DEPTH_M = following_mod.REGION_DEPTH_M
    REGION_HALF_WIDTH_M = following_mod.REGION_HALF_WIDTH_M
    REGION_HEIGHT_MIN_M = following_mod.REGION_HEIGHT_MIN_M
    REGION_HEIGHT_MAX_M = following_mod.REGION_HEIGHT_MAX_M
    SPRAY_LABEL_LOCAL = following_mod.SPRAY_LABEL
    _human_boxes = following_mod._human_boxes
    _pseudo_box_from_vehicle_points = (
        following_mod._pseudo_box_from_vehicle_points)
    _sample_scene_indices = following_mod._sample_scene_indices
    _scene_meta = following_mod._scene_meta
    from spray.beam_model import load_beam_table
    from spray.plume import PlumeConfig, inject_plume_stateful
    from spray.plume_context import PlumeContext
    from spray.plume_state import PlumeState, PlumeStateConfig
    from spray.raycast import raycast_frame

    root = Path(args.root)
    scenes = select_scenes(_scene_meta(root))
    if args.limit_scenes > 0:
        scenes = scenes[: args.limit_scenes]
    table = load_beam_table()
    config = PlumeConfig()
    rows: list[dict] = []
    started = time.time()

    def region_mask(xyz: np.ndarray, box: np.ndarray, road_z: float) -> np.ndarray:
        if xyz.shape[0] == 0:
            return np.zeros(0, dtype=bool)
        rear_x = float(box[0]) - float(box[3]) / 2.0
        depth = rear_x - xyz[:, 0]
        height = xyz[:, 2] - road_z
        return ((depth >= 0.0) & (depth < REGION_DEPTH_M)
                & (np.abs(xyz[:, 1]) <= REGION_HALF_WIDTH_M)
                & (height >= REGION_HEIGHT_MIN_M)
                & (height <= REGION_HEIGHT_MAX_M))

    for position, scene in enumerate(scenes, start=1):
        scene_dir = root / scene["rel_path"]
        scan_ids = sorted(p.stem for p in (scene_dir / "velodyne").glob("*.bin"))
        indices = _sample_scene_indices(len(scan_ids), args.frames_per_scene)
        object_speed_mps = scene["speed_kmh"] / 3.6
        ego_speed_mps = scene["ego_kmh"] / 3.6
        state = PlumeState(PlumeStateConfig())
        n_frames = 0
        for position_in_scene, index in enumerate(indices):
            scan_id = scan_ids[index]
            points = np.fromfile(scene_dir / "velodyne" / f"{scan_id}.bin",
                                 dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(scene_dir / "labels" / f"{scan_id}.label",
                                 dtype=np.uint32)
            if labels.size != points.shape[0]:
                continue
            if scene["has_box"]:
                boxes = _human_boxes(scene_dir, scan_id, object_speed_mps)
                road_z = (float(np.median(boxes[:, 2])) if len(boxes)
                          else float(np.percentile(points[:, 2], 5.0)))
            else:
                boxes = _pseudo_box_from_vehicle_points(
                    points, labels, scene["vehicle_class"])
                road_z = float(np.percentile(points[:, 2], 5.0))
            if boxes is None or len(boxes) == 0:
                continue
            box = np.asarray(boxes[0], dtype=np.float64)
            clean = points[labels != SPRAY_LABEL_LOCAL].astype(np.float32)
            context = PlumeContext(
                scene_token=scene["rel_path"], frame_index=position_in_scene,
                epoch=0, sensor_origin=np.zeros(3, dtype=np.float64),
                ego_speed_mps=ego_speed_mps,
                object_speed_mps=object_speed_mps, wfh_mm=1.0,
                road_z_m=road_z)
            result = inject_plume_stateful(
                clean, boxes, context, state, seed=FIXED_SEED,
                token=f"follow/{scene['rel_path']}/{position_in_scene}",
                config=config, vehicle_class=scene["vehicle_class"])
            ray = raycast_frame(
                result.points, state.all_alive(), table=table,
                road_z_m=road_z, rng=np.random.default_rng(FIXED_SEED))
            synthetic = ray.detections
            gen_xyz = synthetic[:, :3].astype(np.float64)
            real_xyz = points[labels == SPRAY_LABEL_LOCAL][:, :3].astype(np.float64)

            real_hist, real_beyond = range_hist(
                np.linalg.norm(real_xyz, axis=1))
            gen_hist, gen_beyond = range_hist(
                np.linalg.norm(gen_xyz, axis=1))
            # biến thể "trong vùng A3-V" cho cả hai vế
            real_region = region_mask(real_xyz, box, road_z)
            gen_region = region_mask(gen_xyz, box, road_z)
            real_region_hist, real_region_beyond = range_hist(
                np.linalg.norm(real_xyz[real_region], axis=1))
            gen_region_hist, gen_region_beyond = range_hist(
                np.linalg.norm(gen_xyz[gen_region], axis=1))

            n_frames += 1
            rows.append({
                "scenario": "following",
                "scene": scene["rel_path"],
                "vehicle_class": scene["vehicle_class"],
                "speed_kmh": scene["speed_kmh"],
                "band": band_label(float(scene["speed_kmh"])),
                "has_box": scene["has_box"],
                "scan_id": scan_id,
                "frame": index,
                "n_label2": int(real_xyz.shape[0]),
                "n_gen": int(gen_xyz.shape[0]),
                "range_hist_label2": real_hist,
                "n_beyond_label2": real_beyond,
                "range_hist_gen": gen_hist,
                "n_beyond_gen": gen_beyond,
                "range_hist_label2_region": real_region_hist,
                "n_beyond_label2_region": real_region_beyond,
                "range_hist_gen_region": gen_region_hist,
                "n_beyond_gen_region": gen_region_beyond,
                "vehicle_range_m": round(float(np.linalg.norm(box[:3])), 2),
            })
        print(f"  [{position}/{len(scenes)}] {scene['rel_path']} "
              f"{scene['speed_kmh']:.0f} km/h frames={n_frames} "
              f"{time.time() - started:.0f}s", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        for record in rows:
            handle.write(json.dumps(record) + "\n")
    print(f"xong {len(rows)} frame -> {out}", flush=True)


# ---------------------------------------------------------------------------
# 3) SINH — static (ego đứng yên, xe chạy ra xa) — tái dùng QĐ14
# ---------------------------------------------------------------------------
def run_gen_static(args: argparse.Namespace) -> None:
    tail_mod = _scripts_module("measure_plume_size_tail")
    ROAD_Z_M = tail_mod.ROAD_Z_M
    STATIC_DT_S = tail_mod.STATIC_DT_S
    STATIC_END_X_M = tail_mod.STATIC_END_X_M
    STATIC_MIN_TAIL_RANGE_M = tail_mod.STATIC_MIN_TAIL_RANGE_M
    VEHICLE_BOX_LENGTH_M = tail_mod.VEHICLE_BOX_LENGTH_M
    _static_box = tail_mod._static_box
    _static_context = tail_mod._static_context
    production_table = tail_mod.production_table
    from spray.plume import PlumeConfig, inject_plume_stateful
    from spray.plume_state import PlumeState, PlumeStateConfig
    from spray.raycast import RaycastConfig, raycast_frame

    table = production_table()
    config = PlumeConfig(point_cloud_range=(-60.0, -20.0, -6.0, 220.0, 20.0, 6.0))
    speeds = [float(v) for v in args.speeds.split(",") if v.strip()]
    rows: list[dict] = []
    started = time.time()
    for speed_kmh in speeds:
        for seed in range(args.seeds):
            defaults = PlumeStateConfig()
            state = PlumeState(PlumeStateConfig(
                spawn_scale=defaults.spawn_scale,
                radius_sigma=defaults.radius_sigma))
            speed_mps = speed_kmh / 3.6
            step_m = speed_mps * STATIC_DT_S
            start_x = STATIC_MIN_TAIL_RANGE_M + step_m + 0.5
            n_steps = int(np.ceil((STATIC_END_X_M - start_x) / step_m)) + 1
            n_steps = max(n_steps, 1)
            rng_background = np.random.default_rng(seed)
            background = np.zeros((args.background_points, 5), dtype=np.float32)
            background[:, 0] = rng_background.uniform(
                -27, 27, args.background_points)
            background[:, 1] = rng_background.uniform(
                -27, 27, args.background_points)
            background[:, 2] = ROAD_Z_M
            n_written = 0
            for index in range(n_steps):
                car_x = start_x + step_m * index
                result = inject_plume_stateful(
                    background, _static_box(car_x, speed_mps),
                    _static_context(speed_kmh, index), state,
                    seed=seed * 100_000 + index, token=f"tail/{index}",
                    config=config)
                ray = raycast_frame(
                    result.points, state.all_alive(), table=table,
                    road_z_m=ROAD_Z_M,
                    rng=np.random.default_rng(seed * 777 + index),
                    config=RaycastConfig())
                detections = ray.detections
                hist, beyond = range_hist(
                    np.linalg.norm(detections[:, :3], axis=1))
                rear_range = car_x - VEHICLE_BOX_LENGTH_M / 2.0
                det_range = np.linalg.norm(detections[:, :3], axis=1)
                det_depth = rear_range - detections[:, 0].astype(np.float64)
                dhist, ahead, dbeyond = depth_hist(det_depth)
                # Biến thể "plume SAU xe": bỏ detection nằm trước mặt đuôi xe
                # (depth < 0). Vế thật luôn có depth >= 0 theo định nghĩa vùng đo,
                # nên đây là phép so cùng định nghĩa; phần bị bỏ được báo riêng.
                hist_behind, beyond_behind = range_hist(
                    det_range[det_depth >= 0.0])
                rows.append({
                    "scenario": "gen_static",
                    "vehicle_class": "crafter",
                    "speed_kmh": speed_kmh,
                    "band": band_label(speed_kmh),
                    "seed": seed,
                    "frame": index,
                    "car_x": round(float(car_x), 2),
                    "rear_range": round(rear_range, 2),
                    "n_det": int(detections.shape[0]),
                    "range_hist": hist,
                    "n_beyond_hist": beyond,
                    "range_hist_behind": hist_behind,
                    "n_beyond_hist_behind": beyond_behind,
                    "depth_hist": dhist,
                    "n_ahead_of_rear": ahead,
                    "n_depth_beyond_60": dbeyond,
                })
                n_written += 1
            print(f"  gen-static {speed_kmh:.0f} km/h seed={seed} "
                  f"frames={n_written} {time.time() - started:.0f}s",
                  flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as handle:
        for record in rows:
            handle.write(json.dumps(record) + "\n")
    print(f"xong {len(rows)} frame -> {out}", flush=True)


# ---------------------------------------------------------------------------
# 5) tổng hợp: CDF / KS / quantile
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def cdf_at(counts: np.ndarray, x: float) -> float:
    """F(x) = P(range < x) trên histogram 1 m (bin chứa x không tính)."""
    total = float(counts.sum())
    if total <= 0.0:
        return float("nan")
    index = int(min(max(np.floor(x / BIN_M), 0), counts.size))
    return float(counts[:index].sum() / total)


def quantile_from_hist(counts: np.ndarray, q: float) -> float:
    """Quantile nội suy tuyến tính TRONG bin (không ngoại suy ngoài dữ liệu)."""
    total = float(counts.sum())
    if total <= 0.0:
        return float("nan")
    target = q / 100.0 * total
    cum = np.cumsum(counts)
    index = int(np.searchsorted(cum, target, side="left"))
    index = min(index, counts.size - 1)
    before = 0.0 if index == 0 else float(cum[index - 1])
    frac = (target - before) / max(float(counts[index]), 1.0)
    return float(RANGE_EDGES[index] + frac * BIN_M)


def ks_distance(real: np.ndarray, gen: np.ndarray) -> tuple[float, float]:
    """KS trên lưới 0–50 m (1 m) của hai CDF đã chuẩn hoá trong cửa sổ."""
    if real.sum() <= 0 or gen.sum() <= 0:
        return float("nan"), float("nan")
    n = int(WINDOW_M / BIN_M)
    cdf_real = np.cumsum(real[:n]) / real[:n].sum()
    cdf_gen = np.cumsum(gen[:n]) / gen[:n].sum()
    diff = np.abs(cdf_real - cdf_gen)
    index = int(diff.argmax())
    return float(diff[index]), float(RANGE_EDGES[index + 1])


def pool(rows: list[dict], hist_key: str, sub: str = "all") -> np.ndarray:
    """Gộp histogram của các frame (lọc biến thể con nếu cần)."""
    total = np.zeros(N_BINS, dtype=np.float64)
    for row in rows:
        if sub == "window_full" and float(row["rear_range"]) > WINDOW_FULL_REAR_M:
            continue
        total += np.asarray(row[hist_key], dtype=np.float64)
    return total


def describe(counts: np.ndarray, label: str) -> dict:
    """Mọi số của một vế: CDF mốc 10–50 m, %<10, median, quantile, >50 m."""
    n_total = float(counts.sum())
    n_window = float(counts[: int(WINDOW_M / BIN_M)].sum())
    out = {
        "label": label,
        "n_det": int(n_total),
        "n_le_50": int(n_window),
        "pct_beyond_50": (100.0 * (n_total - n_window) / n_total
                          if n_total else float("nan")),
        "n_lt_10": int(counts[:10].sum()),
    }
    if n_window <= 0:
        out["status"] = "KHONG_DO_DUOC"
        return out
    for mark in (10, 20, 30, 40, 50):
        out[f"cdf_{mark}"] = 100.0 * counts[:mark].sum() / n_window
    out["pct_lt_10"] = 100.0 * counts[:10].sum() / n_window
    out["median_window"] = quantile_from_hist(
        counts[: int(WINDOW_M / BIN_M)], 50.0)
    for q in (25, 50, 75):
        out[f"p{q}_all"] = quantile_from_hist(counts, float(q))
    out["status"] = "ok"
    return out


def side_rows(rows: list[dict], scenario: str, vehicle_class: str | None,
              band: str) -> list[dict]:
    return [r for r in rows
            if r["scenario"] == scenario
            and r["band"] == band
            and (vehicle_class is None
                 or r["vehicle_class"] == vehicle_class)]


def compare_pair(real_counts: np.ndarray, gen_counts: np.ndarray,
                 real_label: str, gen_label: str) -> dict:
    real = describe(real_counts, real_label)
    gen = describe(gen_counts, gen_label)
    ks, ks_at = ks_distance(real_counts, gen_counts)
    out = {"real": real, "gen": gen, "ks": ks, "ks_at_m": ks_at}
    for mark in (10, 20, 30, 40, 50):
        key = f"cdf_{mark}"
        if real.get(key) is not None and gen.get(key) is not None:
            out[f"delta_{mark}"] = gen[key] - real[key]
    return out


def aggregate(args: argparse.Namespace) -> None:
    real_static = load_jsonl(Path(args.real_static_jsonl))
    following = load_jsonl(Path(args.following_jsonl))
    gen_static = load_jsonl(Path(args.gen_static_jsonl))
    summary: dict = {
        "generated_by": "scripts/measure_cdf_over_range.py",
        "quantity": ("CDF của range = |p| từ gốc velodyne, cửa sổ 0–50 m, "
                     "bin 1 m (Paper A Fig. 12)"),
        "params": {
            "window_m": WINDOW_M, "bin_m": BIN_M,
            "hist_max_m": HIST_MAX_M, "bands": dict(SPEED_BANDS),
            "static_window_full_rear_m": WINDOW_FULL_REAR_M,
            "frames_per_scene": FRAMES_PER_SCENE,
            "gen_static_seeds": GEN_STATIC_SEEDS,
        },
        "inputs": {},
        "pairs": {},
    }
    for name, rows in (("real_static", real_static),
                       ("following", following),
                       ("gen_static", gen_static)):
        summary["inputs"][name] = {
            "frames": len(rows),
            "bags": len({r.get("bag") for r in rows if r.get("bag")}),
            "scenes": len({r.get("scene") for r in rows if r.get("scene")}),
            "classes": sorted({r["vehicle_class"] for r in rows}),
        }

    # --- A. static: thật vs sinh, 3 biến thể ---
    for variant, gen_key, sub in (
        ("all", "range_hist", "all"),
        ("window_full", "range_hist", "window_full"),
        ("behind_window_full", "range_hist_behind", "window_full"),
    ):
        key = f"static_{variant}"
        summary["pairs"][key] = {}
        for vehicle_class in ("Crafter", None):
            class_key = vehicle_class or "pooled"
            for band in BAND_ORDER:
                rs = side_rows(real_static, "real_static", vehicle_class, band)
                gs = side_rows(gen_static, "gen_static", None, band)
                if not rs or not gs:
                    summary["pairs"][key][f"{class_key}_{band}"] = {
                        "status": "KHONG_DO_DUOC"}
                    continue
                real_counts = pool(rs, "range_hist", sub)
                gen_counts = pool(gs, gen_key, sub)
                pair = compare_pair(real_counts, gen_counts, "real", "gen")
                pair["n_frames"] = {"real": len(rs), "gen": len(gs)}
                pair["n_bags"] = len({r["bag"] for r in rs})
                pair["n_seeds"] = len({r["seed"] for r in gs})
                pair["rear_range_p50"] = {
                    "real": float(np.percentile(
                        [r["rear_range"] for r in rs], 50)),
                    "gen": float(np.percentile(
                        [r["rear_range"] for r in gs], 50)),
                }
                summary["pairs"][key][f"{class_key}_{band}"] = pair

    # --- B. following: label==2 vs sinh, 2 biến thể vùng ---
    for variant in ("all", "region"):
        key = f"following_{variant}"
        summary["pairs"][key] = {}
        for vehicle_class in ("crafter", "golf", None):
            class_key = vehicle_class or "pooled"
            for band in BAND_ORDER:
                rows = side_rows(following, "following", vehicle_class, band)
                if not rows:
                    summary["pairs"][key][f"{class_key}_{band}"] = {
                        "status": "KHONG_DO_DUOC"}
                    continue
                hist_real = ("range_hist_label2" if variant == "all"
                             else "range_hist_label2_region")
                hist_gen = ("range_hist_gen" if variant == "all"
                            else "range_hist_gen_region")
                real_counts = pool(rows, hist_real)
                gen_counts = pool(rows, hist_gen)
                pair = compare_pair(real_counts, gen_counts, "real", "gen")
                pair["n_frames"] = len(rows)
                pair["n_scenes"] = len({r["scene"] for r in rows})
                pair["vehicle_range_p50"] = float(np.percentile(
                    [r["vehicle_range_m"] for r in rows], 50))
                summary["pairs"][key][f"{class_key}_{band}"] = pair

    out = Path(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")

    # --- in bảng markdown ---
    def fmt(value: float, digits: int = 1) -> str:
        return "—" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"

    def _is_ok(pair: dict) -> bool:
        return (pair.get("status") != "KHONG_DO_DUOC"
                and pair.get("real", {}).get("status") == "ok"
                and pair.get("gen", {}).get("status") == "ok")

    def print_pair_table(pairs: dict, title: str) -> None:
        print(f"\n### {title}\n")
        print("| ô | CDF10 thật | CDF10 sinh | CDF20 thật | CDF20 sinh "
              "| CDF30 thật | CDF30 sinh | CDF40 thật | CDF40 sinh "
              "| CDF50 thật | CDF50 sinh | %<10 thật | %<10 sinh "
              "| KS | tại (m) |")
        print("|" + "---|" * 15)
        for cell, pair in pairs.items():
            if not _is_ok(pair):
                print("| " + " | ".join([cell, "KHONG_DO_DUOC"]
                                        + ["—"] * 13) + " |")
                continue
            real, gen = pair["real"], pair["gen"]
            cells = [cell]
            for mark in (10, 20, 30, 40, 50):
                cells.append(fmt(real[f"cdf_{mark}"]))
                cells.append(fmt(gen[f"cdf_{mark}"]))
            cells.append(fmt(real["pct_lt_10"]))
            cells.append(fmt(gen["pct_lt_10"]))
            cells.append(fmt(pair["ks"], 3))
            cells.append(fmt(pair["ks_at_m"], 0))
            print("| " + " | ".join(cells) + " |")

    def print_side_table(pairs: dict, title: str) -> None:
        print(f"\n### {title}\n")
        print("| ô | n det thật | n det sinh | p25 thật | p25 sinh "
              "| p50 thật | p50 sinh | p75 thật | p75 sinh "
              "| % >50 m thật | % >50 m sinh |")
        print("|" + "---|" * 11)
        for cell, pair in pairs.items():
            if not _is_ok(pair):
                print("| " + " | ".join([cell, "KHONG_DO_DUOC"]
                                        + ["—"] * 9) + " |")
                continue
            real, gen = pair["real"], pair["gen"]
            cells = [
                cell, str(real["n_det"]), str(gen["n_det"]),
                fmt(real["p25_all"]), fmt(gen["p25_all"]),
                fmt(real["p50_all"]), fmt(gen["p50_all"]),
                fmt(real["p75_all"]), fmt(gen["p75_all"]),
                fmt(real["pct_beyond_50"]), fmt(gen["pct_beyond_50"]),
            ]
            print("| " + " | ".join(cells) + " |")

    for key in ("static_all", "static_window_full", "static_behind_window_full"):
        print_pair_table(summary["pairs"][key],
                         f"{key} — CDF 0–50 m (%) + KS")
        print_side_table(summary["pairs"][key],
                         f"{key} — quantile toàn dải + % mass > 50 m")
    for key in ("following_all", "following_region"):
        print_pair_table(summary["pairs"][key],
                         f"{key} — CDF 0–50 m (%) + KS")
        print_side_table(summary["pairs"][key],
                         f"{key} — quantile toàn dải + % mass > 50 m")
    # --- C. chẩn đoán: depth sau mặt đuôi (không phải đại lượng của paper) ---
    print("\n### depth sau mặt đuôi xe — chẩn đoán (CDF % tại 5/10/20/30/45 m)\n")
    print("| vế | nhóm | frame | det | ≤5 m | ≤10 m | ≤20 m | ≤30 m | ≤45 m "
          "| p50 (m) | % ở trước mặt đuôi |")
    print("|" + "---|" * 10)
    depth_edges = DEPTH_EDGES
    for band in BAND_ORDER:
        for name, rows_, sub in (
            ("thật static", side_rows(real_static, "real_static", None, band),
             "all"),
            ("sinh static (mọi frame)",
             side_rows(gen_static, "gen_static", None, band), "all"),
            ("sinh static (rear≤50)",
             side_rows(gen_static, "gen_static", None, band), "window_full"),
        ):
            selected = [r for r in rows_
                        if sub == "all"
                        or float(r["rear_range"]) <= WINDOW_FULL_REAR_M]
            if not selected:
                print(f"| {name} | {band} | KHONG_DO_DUOC " + "|" * 8)
                continue
            counts = np.sum([np.asarray(r["depth_hist"], dtype=float)
                             for r in selected], axis=0)
            n = float(counts.sum())
            ahead = sum(int(r.get("n_ahead_of_rear", 0)) for r in selected)
            cells = [name, band, str(len(selected)), str(int(n))]
            for mark in (5, 10, 20, 30, 45):
                index = int(mark / BIN_M)
                cells.append(fmt(100.0 * counts[:index].sum() / n) if n else "—")
            cells.append(fmt(quantile_from_hist(counts, 50.0)))
            cells.append(fmt(100.0 * ahead / (ahead + n)) if (ahead + n) else "—")
            print("| " + " | ".join(cells) + " |")
            summary.setdefault("depth_diagnostic", {}).setdefault(
                f"{band}_{name}", {
                    "frames": len(selected), "n_det": int(n),
                    "cdf_le_5_10_20_30_45": [
                        100.0 * counts[:int(m / BIN_M)].sum() / n
                        if n else None for m in (5, 10, 20, 30, 45)],
                    "p50_m": quantile_from_hist(counts, 50.0),
                    "pct_ahead_of_rear": (100.0 * ahead / (ahead + n)
                                          if (ahead + n) else None),
                })
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\nsummary -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="aggregate",
                        choices=("real-static", "following", "gen-static",
                                 "aggregate"))
    parser.add_argument("--crafter-zip",
                        default="data/roadspray/Crafter_static.zip")
    parser.add_argument("--golf-zip", default="data/roadspray/Golf_static.zip")
    parser.add_argument("--xlsx",
                        default="data/roadspray/meta_data_measurement.xlsx")
    parser.add_argument("--meta", default="data/roadspray/meta_data_dataset.json")
    parser.add_argument("--root", default="data/SemanticSprayDataset")
    parser.add_argument("--tmp", default=".scratch/tmp/cdf/bags")
    parser.add_argument("--speeds", default="50,60,70,80,90,100,110,120,130")
    parser.add_argument("--bags-per-speed", type=int, default=2)
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--height-max", type=float, default=HEIGHT_MAX_M)
    parser.add_argument("--keep-bags", action="store_true")
    parser.add_argument("--frames-per-scene", type=int,
                        default=FRAMES_PER_SCENE)
    parser.add_argument("--limit-scenes", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=GEN_STATIC_SEEDS)
    parser.add_argument("--background-points", type=int, default=30_000)
    parser.add_argument("--real-static-jsonl",
                        default=".scratch/tmp/cdf/real_static.jsonl")
    parser.add_argument("--following-jsonl",
                        default=".scratch/tmp/cdf/following.jsonl")
    parser.add_argument("--gen-static-jsonl",
                        default=".scratch/tmp/cdf/gen_static.jsonl")
    parser.add_argument("--summary", default=".scratch/tmp/cdf/cdf_summary.json")
    args = parser.parse_args()
    if args.mode == "real-static":
        args.out = args.real_static_jsonl
        run_real_static(args)
    elif args.mode == "following":
        args.out = args.following_jsonl
        run_following(args)
    elif args.mode == "gen-static":
        args.out = args.gen_static_jsonl
        run_gen_static(args)
    else:
        aggregate(args)


if __name__ == "__main__":
    main()
