#!/usr/bin/env python3
"""wet_ground có đụng điểm nào không — đo ĐÚNG cách (có truyền config).

Phép đo trước ra "0 điểm đổi intensity" là **lỗi của script**, không phải kết quả:
``inject_plume_stateful`` chỉ chạy ``apply_wet_ground`` khi tham số ``wet_ground``
được truyền vào và ``.enabled`` = True. Script trước gọi không truyền ⇒ luôn tắt.

Cổng C thật có bật: ``--wet-ground`` default **True** (`sspp_infer.py:1356-1358`),
và log kernel xác nhận ``wet_ground=1``.

Đo lại: truyền ``WetGroundConfig(enabled=True)``, rồi so intensity của điểm nền
trước/sau. Đếm:
  - tổng điểm đổi intensity;
  - trong đó bao nhiêu nằm ở mặt đường (|z - road_z| < 0,15) vs thân xe (z > road+0,4);
  - bao nhiêu nằm trong hộp GT;
  - mức đổi trung vị (giảm bao nhiêu %).
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)
from spray.wet_ground import WetGroundConfig  # noqa: E402

ROOT = REPO / "data/SemanticSprayDataset"
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SPRAY = 2
SEED = 0
N_FRAMES = 6


def _in_box(xyz: np.ndarray, box: np.ndarray) -> np.ndarray:
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    dz = xyz[:, 2] - box[2]
    return ((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)
            & (dz >= -0.1) & (dz <= box[5] + 0.1))


def main() -> None:
    scenes: dict[str, list[int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] == "clean":
                scenes.setdefault(row["scene_token"], []).append(row["frame_idx"])

    tot_changed = 0
    tot_road = 0
    tot_high = 0
    tot_box = 0
    tot_pts = 0
    drops = []

    for scene in sorted(scenes)[:6]:
        path = ROOT / scene
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
        ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
        cls = "crafter" if "Crafter" in scene else "golf"
        scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))

        for frame_idx in scenes[scene][:N_FRAMES]:
            scan = scans[frame_idx]
            boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
            if not boxes_json.is_file():
                continue
            points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                                 dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
            if len(boxes) == 0:
                continue
            road_z = float(np.median(boxes[:, 2]))
            clean = points[labels != SPRAY].astype(np.float32)

            state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                       min_range_m=2.5, max_range_m=50.0))
            context = PlumeContext(scene_token=scene, frame_index=frame_idx, epoch=0,
                                   sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                                   object_speed_mps=obj_v,
                                   wfh_mm=sample_wfh_mm(scene, 0, 0),
                                   road_z_m=road_z)
            result = inject_plume_stateful(
                clean, boxes, context, state, seed=SEED, token=f"wg2/{frame_idx}",
                config=PlumeConfig(), vehicle_class=cls,
                wet_ground=WetGroundConfig(enabled=True))

            n_clean = clean.shape[0]
            if result.points.shape[0] < n_clean:
                continue
            base_out = result.points[:n_clean]
            if not np.allclose(base_out[:, :3], clean[:, :3], atol=1e-4):
                print(f"  {scene}#{frame_idx}: toạ độ nền đổi thứ tự, bỏ qua")
                continue
            changed = ~np.isclose(base_out[:, 3], clean[:, 3], atol=1e-3)
            tot_pts += n_clean
            tot_changed += int(changed.sum())
            tot_road += int((changed & (np.abs(clean[:, 2] - road_z) < 0.15)).sum())
            tot_high += int((changed & (clean[:, 2] > road_z + 0.4)).sum())
            for box in boxes:
                tot_box += int((changed
                                & _in_box(clean[:, :3].astype(np.float64), box)).sum())
            if changed.any():
                ratio = (base_out[changed, 3] / np.maximum(clean[changed, 3], 1e-6))
                drops.append(ratio)

    print(f"điểm nền xét: {tot_pts}")
    print(f"điểm ĐỔI intensity: {tot_changed} ({100*tot_changed/max(tot_pts,1):.3f} %)")
    print(f"  ở mặt đường (|z-road|<0,15): {tot_road} "
          f"= {100*tot_road/max(tot_changed,1):.1f} % số đổi")
    print(f"  ở thân xe (z>road+0,4)     : {tot_high} "
          f"= {100*tot_high/max(tot_changed,1):.1f} % số đổi")
    print(f"  TRONG hộp GT               : {tot_box} "
          f"= {100*tot_box/max(tot_changed,1):.1f} % số đổi")
    if drops:
        allr = np.concatenate(drops)
        print(f"  tỉ lệ intensity sau/trước: p05/p50/p95 = "
              f"{np.percentile(allr,5):.3f} / {np.median(allr):.3f} / "
              f"{np.percentile(allr,95):.3f}")
        print(f"  giảm >50 %: {100*np.mean(allr < 0.5):.1f} % số điểm đổi")


if __name__ == "__main__":
    main()
