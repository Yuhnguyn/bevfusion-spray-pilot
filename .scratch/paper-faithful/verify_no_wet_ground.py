#!/usr/bin/env python3
"""Kiểm nhanh: `WetGroundConfig(enabled=False)` có thật sự tắt stage không?

Trước khi đốt một lượt GPU (~15 phút) cho A7-b, xác nhận cờ tắt có hiệu lực:
chạy cùng một frame với wet_ground BẬT và TẮT, so số điểm bị đổi intensity.
  * BẬT  -> phải rất nhiều (đo trước: 75,9 % điểm nền)
  * TẮT  -> phải đúng 0
Nếu TẮT vẫn ra số lớn thì cờ không ăn, không được push kernel.
"""

from __future__ import annotations

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
SPRAY = 2


def main() -> None:
    scenes = sorted(p for p in (ROOT / "Crafter_dynamic").iterdir() if p.is_dir())
    if not scenes:
        print("KHÔNG thấy scene Crafter_dynamic")
        return

    for scene_dir in scenes[:3]:
        meta = read_metadata(scene_dir / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
        ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
        scans = sorted(p.stem for p in (scene_dir / "velodyne").glob("*.bin"))
        if not scans:
            continue
        scan = scans[0]
        boxes_json = scene_dir / "object_labels" / "lidar" / f"{scan}.json"
        if not boxes_json.is_file():
            continue
        points = np.fromfile(scene_dir / "velodyne" / f"{scan}.bin",
                             dtype=np.float32).reshape(-1, 5)
        labels = np.fromfile(scene_dir / "labels" / f"{scan}.label",
                             dtype=np.uint32)
        if labels.size != points.shape[0]:
            continue
        boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
        if len(boxes) == 0:
            continue
        road_z = float(np.median(boxes[:, 2]))
        clean = points[labels != SPRAY].astype(np.float32)
        context = PlumeContext(scene_token=scene_dir.name, frame_index=0, epoch=0,
                               sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                               object_speed_mps=obj_v,
                               wfh_mm=sample_wfh_mm(scene_dir.name, 0, 0),
                               road_z_m=road_z)
        print(f"\n=== {scene_dir.name}  ({clean.shape[0]} điểm nền, "
              f"road_z={road_z:+.3f})")
        for label, wet in (
            ("BẬT ", WetGroundConfig(enabled=True)),
            ("TẮT ", WetGroundConfig(enabled=False)),
            ("None", None),
        ):
            state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                       min_range_m=2.5, max_range_m=50.0))
            result = inject_plume_stateful(
                clean, boxes, context, state, seed=0, token=f"wgk/{scan}",
                config=PlumeConfig(), vehicle_class="crafter", wet_ground=wet)
            n = clean.shape[0]
            if result.points.shape[0] < n:
                print(f"  wet_ground={label}: points ngắn hơn nền, bỏ qua")
                continue
            base_out = result.points[:n]
            same_xyz = np.allclose(base_out[:, :3], clean[:, :3], atol=1e-4)
            changed = int((~np.isclose(base_out[:, 3], clean[:, 3],
                                       atol=1e-3)).sum()) if same_xyz else -1
            print(f"  wet_ground={label}: đổi intensity = {changed:7d}"
                  f"  ({100*changed/max(n,1):6.2f} %)"
                  f"   tổng điểm = {result.points.shape[0]}")


if __name__ == "__main__":
    main()
