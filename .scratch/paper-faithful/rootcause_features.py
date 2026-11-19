#!/usr/bin/env python3
"""ROOT CAUSE bước 2: điểm plume rơi vào đâu so với hộp, và độc lập với box không?

H1 (voxel eviction) đã bị phủ định: 0 điểm xe bị cắt, voxel quá 10 điểm giống hệt
clean/plume, chỉ 58/120 frame có điểm spray trong hộp.

H2 còn lại — "spray phá cấu trúc hình học mà detector dựa vào". Kiểm hai vế:

  (a) Tỉ lệ điểm plume rơi TRONG / GẦN hộp GT (bán kính 1–5 m quanh tâm hộp).
      Nếu phần lớn nằm trong vùng hộp ⇒ detector bị nhiễu ngay trên vật thể.
  (b) Điểm plume có cùng phân bố đặc trưng (z, intensity, ring) với điểm xe không.
      Nếu z lệch (cao hơn/thấp hơn) hoặc intensity khác (0 vs 0–255) ⇒ đó là
      "out of distribution" ở tầng feature.

Điểm mấu chốt: detector LiDAR-only ăn 5 kênh (x,y,z,intensity,ring). Intensity
của plume = 0 tuyệt đối; spray thật cũng >80 % bằng 0 ⇒ intensity một mình không
giải thích được. Phải đo ring/z.
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

SCENES = [
    ("Crafter_dynamic/0000_2021-09-08-14-36-56_0", 40),
    ("Crafter_dynamic/0048_2021-09-08-16-02-18_0", 40),
    ("Golf_dynamic/0102_2021-09-08-12-00-19_0", 40),
]


def main() -> None:
    table = load_beam_table()
    # Gom điểm plume và điểm xe để so phân bố đặc trưng
    plume_all: list[np.ndarray] = []
    veh_all: list[np.ndarray] = []
    real_spray_all: list[np.ndarray] = []
    dist_to_box: list[float] = []

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
                                           token=f"d/{pos}", config=PlumeConfig(),
                                           vehicle_class=cls)
            ray = raycast_frame(result.points, state.select_alive(), table=table,
                                road_z_m=road_z, rng=np.random.default_rng(SEED),
                                config=RaycastConfig(max_distance_m=50.0))

            if len(ray.detections):
                plume_all.append(ray.detections)
            veh_all.append(clean[labels[labels != SPRAY] == VEH])
            spray_raw = points[labels == SPRAY]
            if len(spray_raw):
                real_spray_all.append(spray_raw)

            # khoảng cách mỗi detection plume tới tâm hộp gần nhất (mặt phẳng xy)
            if len(ray.detections) and len(boxes):
                det_xy = ray.detections[:, :2]
                box_xy = boxes[:, :2]
                d = np.linalg.norm(det_xy[:, None, :] - box_xy[None, :, :], axis=2)
                dist_to_box.extend(d.min(axis=1).tolist())

    def stack(groups: list[np.ndarray]) -> np.ndarray:
        return (np.concatenate(groups, axis=0) if groups
                else np.zeros((0, 5), dtype=np.float32))

    plume = stack(plume_all)
    veh = stack(veh_all)
    real = stack(real_spray_all)

    def describe(name: str, arr: np.ndarray) -> None:
        if len(arr) == 0:
            print(f"{name:<14} (rỗng)")
            return
        inten = arr[:, 3]
        ring = arr[:, 4]
        print(f"{name:<14} n={len(arr):7d}  "
              f"z p05/p50/p95 = {np.percentile(arr[:,2],5):6.2f}/"
              f"{np.percentile(arr[:,2],50):6.2f}/{np.percentile(arr[:,2],95):6.2f}  "
              f"inten p50/p95/max = {np.percentile(inten,50):5.1f}/"
              f"{np.percentile(inten,95):5.1f}/{inten.max():5.1f}  "
              f"inten==0: {100*np.mean(inten==0):5.1f}%  "
              f"ring min/max = {ring.min():4.0f}/{ring.max():4.0f}")

    print("Phân bố đặc trưng (5 kênh mà detector ăn):")
    describe("plume sinh", plume)
    describe("điểm XE", veh)
    describe("spray THẬT", real)
    print()

    d = np.array(dist_to_box)
    if d.size:
        print(f"Khoảng cách detection plume -> tâm hộp GT gần nhất (xy), {d.size} det:")
        for q in (5, 25, 50, 75, 95):
            print(f"  p{q:<2d} = {np.percentile(d, q):6.2f} m")
        for r in (1.0, 2.0, 3.0, 5.0, 10.0):
            print(f"  trong {r:4.1f} m quanh tâm hộp: {100*np.mean(d <= r):5.1f} %")


if __name__ == "__main__":
    main()
