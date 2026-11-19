#!/usr/bin/env python3
"""ROOT CAUSE: điểm spray có tranh chỗ trong voxel của hộp GT không?

Giả thuyết H1 — "voxel eviction":
  BEVFusion voxelize với ``max_num_points = 10`` (voxelnet_0p075.yaml). Nếu điểm
  spray rơi vào cùng voxel 0,075×0,075×0,2 m với điểm xe, và số điểm/voxel vượt
  10, phần dư bị **cắt**. Khi đó detector mất điểm của vật thể ⇒ confidence tụt
  ⇒ recall tụt, mà **không** cần che khuất gì cả. Đây khớp với mọi thứ đã đo:
  lượng spray nhỏ, hộp không dịch, score tụt.

Giả thuyết H2 — "distribution shift":
  Điểm spray nằm ngoài hộp, chỉ làm lệch phân bố chung ⇒ nhưng khi đó không giải
  thích được score của hộp ĐÚNG tụt mạnh như vậy.

Phép đo phân biệt H1 vs H2:
  * đếm điểm GT-box trước/sau khi inject, theo từng voxel;
  * đếm số voxel vượt 10 điểm (bị cắt) trước/sau;
  * đếm số điểm xe **thật sự bị cắt** trước/sau.

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_voxel.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import RaycastConfig, raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

ROOT = REPO / "data/SemanticSprayDataset"
SPRAY, VEH = 2, 1
SEED = 0
# voxel của config model0
VOXEL = np.array([0.075, 0.075, 0.2])
MAX_POINTS = 10
RANGE = (-54.0, -54.0, -5.0, 54.0, 54.0, 3.0)

SCENES = [
    ("Crafter_dynamic/0000_2021-09-08-14-36-56_0", 40),
    ("Crafter_dynamic/0048_2021-09-08-16-02-18_0", 40),
    ("Golf_dynamic/0102_2021-09-08-12-00-19_0", 40),
]


def voxel_keys(xyz: np.ndarray) -> np.ndarray:
    """Chỉ số voxel (int) cho từng điểm, đúng cách BEVFusion rời rạc hoá."""
    ix = np.floor((xyz[:, 0] - RANGE[0]) / VOXEL[0]).astype(np.int64)
    iy = np.floor((xyz[:, 1] - RANGE[1]) / VOXEL[1]).astype(np.int64)
    iz = np.floor((xyz[:, 2] - RANGE[2]) / VOXEL[2]).astype(np.int64)
    nx = int(round((RANGE[3] - RANGE[0]) / VOXEL[0]))
    ny = int(round((RANGE[4] - RANGE[1]) / VOXEL[1]))
    return (ix * ny + iy) * 1000 + iz


def in_box(xyz: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Điểm nằm trong hộp 3D (dùng yaw của hộp). box[2] = đáy hộp."""
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    local_x = cos * dx - sin * dy
    local_y = sin * dx + cos * dy
    dz = xyz[:, 2] - box[2]
    return ((np.abs(local_x) <= box[3] / 2) & (np.abs(local_y) <= box[4] / 2)
            & (dz >= 0) & (dz <= box[5]))


def eviction_stats(xyz: np.ndarray, keys: np.ndarray, mask_vehicle: np.ndarray):
    """Số điểm xe bị cắt do voxel vượt ``MAX_POINTS``.

    Điểm trong voxel **không** vượt ``MAX_POINTS`` được giữ hết; chỉ voxel vượt
    mới cắt phần dư (giữ ``MAX_POINTS`` điểm đầu theo thứ tự mảng, đúng như
    BEVFusion làm). Bản đầu của hàm này chỉ đếm điểm xe trong voxel bị cắt rồi
    lấy ``total - kept`` ⇒ luôn ra 100 % bị cắt. Đã sửa: cộng cả phần được giữ.
    """
    uniq, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    over = counts > MAX_POINTS
    total_vehicle = int(mask_vehicle.sum())
    if not over.any():
        return 0, 0, total_vehicle

    kept_vehicle = 0
    for voxel_index in np.nonzero(over)[0]:
        member = np.nonzero(inverse == voxel_index)[0]
        keep = member[:MAX_POINTS]
        kept_vehicle += int(mask_vehicle[keep].sum())

    # điểm xe nằm NGOÀI các voxel bị cắt đều được giữ
    in_over_voxel = np.isin(inverse, np.nonzero(over)[0])
    kept_vehicle += int(mask_vehicle[~in_over_voxel].sum())

    return int(over.sum()), total_vehicle - kept_vehicle, total_vehicle


def main() -> None:
    table = load_beam_table()
    print(f"{'scene':<26} {'frame':>5} {'spray_in_box':>12} {'vox_over':>9} "
          f"{'veh_pts':>7} {'veh_evicted':>11} {'veh_dropped%':>12}")
    totals = {"spray_in_box": 0, "vox_over_clean": 0, "vox_over_plume": 0,
              "veh_evict_clean": 0, "veh_evict_plume": 0, "veh_total": 0}

    for scene, frames in SCENES:
        path = ROOT / scene
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
        ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
        cls = "crafter" if "Crafter" in scene else "golf"
        cfg = replace(PlumeStateConfig(), diffusion_alpha=0.0,
                      min_range_m=2.5, max_range_m=50.0)
        state = PlumeState(cfg)
        wfh = sample_wfh_mm(scene, 0, 0)

        scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[:frames]
        for pos, scan in enumerate(scans):
            points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                                 dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
            if labels.size != points.shape[0]:
                continue
            boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
            if not boxes_json.is_file():
                continue
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
            road_z = float(np.median(boxes[:, 2]))

            clean = points[labels != SPRAY].astype(np.float32)
            context = PlumeContext(scene_token=scene, frame_index=pos, epoch=0,
                                   sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                                   object_speed_mps=obj_v, wfh_mm=wfh,
                                   road_z_m=road_z)
            result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                           token=f"rc/{pos}", config=PlumeConfig(),
                                           vehicle_class=cls)
            ray = raycast_frame(result.points, state.select_alive(), table=table,
                                road_z_m=road_z, rng=np.random.default_rng(SEED),
                                config=RaycastConfig(max_distance_m=50.0))
            plume_pts = np.concatenate([ray.real_points, ray.detections], axis=0)

            # điểm xe = label VEH trong frame gốc
            veh_mask_clean = labels[labels != SPRAY] == VEH
            veh_mask_plume = np.zeros(len(plume_pts), dtype=bool)
            n_clean = len(clean)
            veh_mask_plume[:n_clean] = veh_mask_clean

            # spray rơi vào trong hộp GT?
            det_xyz = (ray.detections[:, :3] if len(ray.detections)
                       else np.zeros((0, 3)))
            spray_in_box = 0
            for box in boxes:
                if len(det_xyz):
                    spray_in_box += int(in_box(det_xyz, box).sum())

            keys_clean = voxel_keys(clean[:, :3].astype(np.float64))
            keys_plume = voxel_keys(plume_pts[:, :3].astype(np.float64))
            _, ev_clean, veh_tot = eviction_stats(
                clean[:, :3].astype(np.float64), keys_clean, veh_mask_clean)
            over_plume, ev_plume, _ = eviction_stats(
                plume_pts[:, :3].astype(np.float64), keys_plume, veh_mask_plume)

            uniq_c, cnt_c = np.unique(keys_clean, return_counts=True)
            over_clean = int((cnt_c > MAX_POINTS).sum())

            totals["spray_in_box"] += spray_in_box
            totals["vox_over_clean"] += over_clean
            totals["vox_over_plume"] += over_plume
            totals["veh_evict_clean"] += ev_clean
            totals["veh_evict_plume"] += ev_plume
            totals["veh_total"] += veh_tot

            if pos % 10 == 0:
                pct = 100.0 * ev_plume / max(veh_tot, 1)
                print(f"{scene.split('/')[1][:24]:<26} {pos:5d} {spray_in_box:12d} "
                      f"{over_plume:9d} {veh_tot:7d} {ev_plume:11d} {pct:11.2f}%")

    print()
    print("TỔNG 120 frame:")
    print(f"  điểm spray rơi TRONG hộp GT        : {totals['spray_in_box']}")
    print(f"  voxel > 10 điểm — clean            : {totals['vox_over_clean']}")
    print(f"  voxel > 10 điểm — plume            : {totals['vox_over_plume']}")
    print(f"  điểm XE bị cắt — clean              : {totals['veh_evict_clean']}")
    print(f"  điểm XE bị cắt — plume              : {totals['veh_evict_plume']}")
    print(f"  tổng điểm xe                        : {totals['veh_total']}")


if __name__ == "__main__":
    main()
