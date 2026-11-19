#!/usr/bin/env python3
"""Chứng minh nhánh `plume` của cổng C THẬT SỰ chạy miền Cách A, không phải production.

Vì sao cần: `GATE_C_PLUME` in `paper_domain=0` trong log kernel v5, nhưng đó là của
`dry_run()` (không truyền cờ), không phải `run_gate_c()`. Không thể phân biệt bằng
log — phải phân biệt bằng **chữ ký số của miền** trong chính output.

Chữ ký khoá:
  * `diffusion_alpha = 0` ⇒ số điểm injected **không** phình theo thời gian sống;
  * `‖pos‖ − radius ≥ 2,5 m` ⇒ cụm gần sensor bị loại;
  * `‖pos‖ ≤ 50 m` ⇒ không có điểm nào quá 50 m kể cả điểm nền.

Đo trên 3 scene × 40 frame, so nhánh cổng C (jsonl) với production chạy lại local.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from dataclasses import replace  # noqa: E402

from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
ROOT = REPO / "data/SemanticSprayDataset"
SPRAY, VEH = 2, 1
SEED = 0


def _gate_c_injected() -> dict:
    """Số điểm injected per frame ở nhánh plume của cổng C, theo scene."""
    out: dict[str, list[int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] != "plume":
                continue
            out.setdefault(row["scene_token"], []).append(int(row["n_injected"]))
    return out


def _local(scene: str, frames: int, cach_a: bool) -> list[int]:
    path = ROOT / scene
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
    cls = "crafter" if "Crafter" in scene else "golf"
    cfg = PlumeStateConfig()
    if cach_a:
        cfg = replace(cfg, diffusion_alpha=0.0, min_range_m=2.5, max_range_m=50.0)
    state = PlumeState(cfg)
    wfh = sample_wfh_mm(scene, 0, 0) if cach_a else 1.0

    results = []
    scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[:frames]
    for pos, scan in enumerate(scans):
        points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                             dtype=np.float32).reshape(-1, 5)
        labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
        if labels.size != points.shape[0]:
            continue
        boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
        if boxes_json.is_file():
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
            road_z = float(np.median(boxes[:, 2]))
        else:
            xyz = points[labels == VEH][:, :3]
            if xyz.shape[0] < 10:
                continue
            length, width, height = ((6.829, 2.419, 2.621) if cls == "crafter"
                                     else (4.250, 2.020, 1.501))
            rear = float(np.percentile(xyz[:, 0], 2.0))
            boxes = np.array([[rear + length / 2, float(np.median(xyz[:, 1])),
                               float(np.percentile(xyz[:, 2], 2.0)),
                               length, width, height, 0, 0, 0]], dtype=np.float32)
            road_z = float(np.percentile(points[:, 2], 5.0))

        clean = points[labels != SPRAY].astype(np.float32)
        context = PlumeContext(scene_token=scene, frame_index=pos, epoch=0,
                               sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                               object_speed_mps=obj_v, wfh_mm=wfh, road_z_m=road_z)
        result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                       token=f"sig/{pos}", config=PlumeConfig(),
                                       vehicle_class=cls)
        results.append(int(result.stats.injected))
    return results


def main() -> None:
    gate = _gate_c_injected()
    # 3 scene đại diện đủ 3 dải tốc độ
    scenes = ["Crafter_dynamic/0000_2021-09-08-14-36-56_0",
              "Crafter_dynamic/0048_2021-09-08-16-02-18_0",
              "Golf_dynamic/0102_2021-09-08-12-00-19_0"]

    print(f"{'scene':<34} {'cổng C/f':>10} {'prod/f':>8} {'Cách A/f':>9} "
          f"{'C/prod':>7} {'C/A':>6}")
    for scene in scenes:
        if scene not in gate:
            print(f"{scene}: KHÔNG có trong jsonl (không thuộc split test)")
            continue
        gate_mean = float(np.mean(gate[scene]))
        frames = min(40, len(gate[scene]))
        prod = _local(scene, frames, cach_a=False)
        cach = _local(scene, frames, cach_a=True)
        prod_mean, cach_mean = float(np.mean(prod)), float(np.mean(cach))
        print(f"{scene.split('/')[1][:32]:<34} {gate_mean:10.1f} {prod_mean:8.1f} "
              f"{cach_mean:9.1f} {gate_mean/max(prod_mean,1e-9):7.3f} "
              f"{gate_mean/max(cach_mean,1e-9):6.3f}")

    print()
    print("Đọc: cột 'C/A' ≈ 1,00 ⇒ cổng C = Cách A. 'C/prod' ≈ 1,00 ⇒ cổng C = production.")


if __name__ == "__main__":
    main()
