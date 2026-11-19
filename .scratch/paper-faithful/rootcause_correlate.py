#!/usr/bin/env python3
"""ROOT CAUSE bước 3: đặc trưng nào của plume DỰ BÁO được mức sụt recall?

Cách làm: Δrecall theo scene đã có (12 scene, −0,078 … −0,526). Tính cho từng scene
một loạt đặc trưng đo được của plume, rồi tìm cái nào tương quan mạnh với Δrecall.
Đây là con đường tìm nguyên nhân **không cần thêm lượt GPU**.

Các đặc trưng thử:
  - `inj_pct`      : điểm plume / điểm nền (%)
  - `n_det_plume`  : số detection plume / frame
  - `r_p50`        : cự ly điểm plume (p50)
  - `z_p50`,`z_p95`: độ cao plume — giả thuyết "plume quá thấp, nằm trên mặt đường"
  - `rz_ratio`     : tỉ lệ điểm plume có z trong dải hộp GT (0..2,6 m)
  - `bear_hit`     : % điểm plume có góc phương vị TRÙNG hộp GT (che tầm nhìn)
  - `front_pct`    : % điểm plume NẰM TRƯỚC hộp GT (gần cảm biến hơn)
  - `vox_frac`     : số voxel bị plume chiếm / số voxel nền
  - `dens`         : mật độ điểm plume trong hộp bao (điểm/m³)
"""

from __future__ import annotations

import json
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
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SPRAY, VEH = 2, 1
SEED = 0
VOXEL = np.array([0.075, 0.075, 0.2])
FRAMES = 12


def voxel_keys(xyz: np.ndarray) -> np.ndarray:
    ix = np.floor((xyz[:, 0] + 54.0) / VOXEL[0]).astype(np.int64)
    iy = np.floor((xyz[:, 1] + 54.0) / VOXEL[1]).astype(np.int64)
    iz = np.floor((xyz[:, 2] + 5.0) / VOXEL[2]).astype(np.int64)
    return (ix * 1440 + iy) * 41 + iz


def scene_features(scene: str, table) -> dict | None:
    path = ROOT / scene
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
    cls = "crafter" if "Crafter" in scene else "golf"
    cfg = replace(PlumeStateConfig(), diffusion_alpha=0.0,
                  min_range_m=2.5, max_range_m=50.0)
    state = PlumeState(cfg)
    wfh = sample_wfh_mm(scene, 0, 0)

    dets, inj_pct, base_pts, n_base = [], [], [], 0
    bear_hits, front_hits, rz_hits, voxel_counts = [], [], [], []
    scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[:FRAMES]

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
        if len(boxes) == 0:
            continue
        road_z = float(np.median(boxes[:, 2]))
        clean = points[labels != SPRAY].astype(np.float32)
        context = PlumeContext(scene_token=scene, frame_index=pos, epoch=0,
                               sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                               object_speed_mps=obj_v, wfh_mm=wfh, road_z_m=road_z)
        result = inject_plume_stateful(clean, boxes, context, state, seed=SEED,
                                       token=f"f/{pos}", config=PlumeConfig(),
                                       vehicle_class=cls)
        ray = raycast_frame(result.points, state.select_alive(), table=table,
                            road_z_m=road_z, rng=np.random.default_rng(SEED),
                            config=RaycastConfig(max_distance_m=50.0))
        det = ray.detections
        if len(det) == 0:
            continue
        dets.append(det)
        inj_pct.append(100.0 * len(det) / max(len(clean), 1))
        base_pts.append(clean)

        # góc phương vị: trùng hộp / nằm trước hộp
        bear_d = np.arctan2(det[:, 1], det[:, 0])
        r_d = np.linalg.norm(det[:, :2], axis=1)
        hit = np.zeros(len(det), dtype=bool)
        front = np.zeros(len(det), dtype=bool)
        in_z = np.zeros(len(det), dtype=bool)
        for box in boxes:
            bear_b = np.arctan2(box[1], box[0])
            r_b = float(np.hypot(box[0], box[1]))
            half = np.arctan2(box[4] / 2, max(r_b, 1.0))
            near_bear = np.abs(np.angle(np.exp(1j * (bear_d - bear_b)))) <= half
            hit |= near_bear
            front |= near_bear & (r_d < r_b)
            in_z |= (det[:, 2] >= box[2]) & (det[:, 2] <= box[2] + box[5])
        bear_hits.append(float(hit.mean()))
        front_hits.append(float(front.mean()))
        rz_hits.append(float(in_z.mean()))
        voxel_counts.append(len(np.unique(voxel_keys(det[:, :3].astype(float)))))

    if not dets:
        return None
    all_det = np.concatenate(dets, axis=0)
    ext = all_det[:, :3].max(axis=0) - all_det[:, :3].min(axis=0)
    volume = float(np.prod(np.maximum(ext, 1e-3)))
    return {
        "inj_pct": float(np.mean(inj_pct)),
        "n_det": float(np.mean([len(d) for d in dets])),
        "r_p50": float(np.median(np.linalg.norm(all_det[:, :2], axis=1))),
        "z_p50": float(np.median(all_det[:, 2])),
        "z_p95": float(np.percentile(all_det[:, 2], 95)),
        "rz_ratio": float(np.mean(rz_hits)),
        "bear_hit": float(np.mean(bear_hits)),
        "front_pct": float(np.mean(front_hits)),
        "n_voxel": float(np.mean(voxel_counts)),
        "density": float(len(all_det) / volume),
    }


def main() -> None:
    table = load_beam_table()
    paired = json.load(open(REPO / ".scratch/diag/a7/gate_c_out/"
                            "gate_c_detections_summary.json"))
    delta = paired["summary"]["paired"]["plume_minus_clean"][
        "recall_per_scene"]["delta_plume_minus_clean"]

    rows = []
    for scene in sorted(delta):
        feat = scene_features(scene, table)
        if feat is None:
            continue
        feat["scene"] = scene
        feat["delta"] = float(delta[scene])
        rows.append(feat)

    keys = ["inj_pct", "n_det", "r_p50", "z_p50", "z_p95", "rz_ratio",
            "bear_hit", "front_pct", "n_voxel", "density"]
    print(f"{'scene':<26} " + " ".join(f"{k:>9}" for k in keys) + f" {'delta':>7}")
    for row in rows:
        print(f"{row['scene'].split('/')[1][:24]:<26} "
              + " ".join(f"{row[k]:9.3f}" for k in keys)
              + f" {row['delta']:+7.3f}")

    print()
    print("Tương quan với Δrecall (âm = đặc trưng cao thì recall sụt nhiều):")
    d = np.array([r["delta"] for r in rows])
    scored = []
    for k in keys:
        x = np.array([r[k] for r in rows])
        if x.std() < 1e-12:
            continue
        scored.append((abs(float(np.corrcoef(x, d)[0, 1])),
                       float(np.corrcoef(x, d)[0, 1]), k))
    scored.sort(reverse=True)
    for _, corr, k in scored:
        print(f"  {k:<12} r = {corr:+.3f}")


if __name__ == "__main__":
    main()
