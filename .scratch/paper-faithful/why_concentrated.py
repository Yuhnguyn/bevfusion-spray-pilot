#!/usr/bin/env python3
"""TẠI SAO plume của mình tập trung quanh vật thể gấp 5 lần spray thật?

Đã đo:
    spray THẬT : 27 667 điểm, vành 2-6 m = 24,9 điểm/frame, r p50 = 9,37 m
    plume MÌNH : 10 077 điểm, vành 2-6 m = 47,4 điểm/frame, r p50 = 12,26 m
    => tổng điểm chỉ 0,36x nhưng vành gấp 1,90x
    => mật độ TƯƠNG ĐỐI trong vành: 1,90 / 0,36 = **5,3x**

Nghĩa là plume của mình không nhiều điểm hơn — nó **dồn điểm vào chỗ nguy hiểm**.

Đo hai thứ để tìm nguyên nhân:
  1. Phân bố cự ly (r) của điểm: thật vs mình — mình có thiếu điểm ở xa không?
  2. Khoảng cách từ điểm tới vật thể GẦN NHẤT: thật vs mình — mình có bám vật thể không?
  3. Số cụm và bán kính cụm mình sinh ra, so với paper.
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
from spray.plume import (  # noqa: E402
    PlumeConfig, cluster_count_for_speed, inject_plume_stateful,
)
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import RaycastConfig, raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

ROOT = REPO / "data/SemanticSprayDataset"
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SPRAY = 2
SEED = 0
N_SCENE = 6
N_FRAME = 8
PCT = (5, 25, 50, 75, 95)


def _nearest_box_dist(xyz: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    if len(xyz) == 0 or len(boxes) == 0:
        return np.zeros(0)
    centers = boxes[:, :2]
    d = np.linalg.norm(xyz[:, None, :2] - centers[None, :, :], axis=2)
    return d.min(axis=1)


def main() -> None:
    scenes: dict[str, list[int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] == "clean":
                scenes.setdefault(row["scene_token"], []).append(row["frame_idx"])

    table = load_beam_table()
    real_r, plume_r, real_nb, plume_nb = [], [], [], []
    n_cluster_rows = []
    frames = 0

    for scene in sorted(scenes)[:N_SCENE]:
        path = ROOT / scene
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
        obj_kmh = float(meta["object_velocity"])
        ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
        cls = "crafter" if "Crafter" in scene else "golf"
        scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))

        for frame_idx in scenes[scene][:N_FRAME]:
            scan = scans[frame_idx]
            boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
            if not boxes_json.is_file():
                continue
            points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                                 dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
            if labels.size != points.shape[0]:
                continue
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
            if len(boxes) == 0:
                continue
            road_z = float(np.median(boxes[:, 2]))
            frames += 1
            n_cluster_rows.append((cls, obj_kmh,
                                   cluster_count_for_speed(obj_kmh, PlumeConfig(), cls)))

            real_pts = points[labels == SPRAY]
            if len(real_pts):
                real_r.append(np.linalg.norm(real_pts[:, :2], axis=1))
                real_nb.append(_nearest_box_dist(real_pts[:, :3].astype(np.float64), boxes))

            clean = points[labels != SPRAY].astype(np.float32)
            state = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                       min_range_m=2.5, max_range_m=50.0))
            context = PlumeContext(scene_token=scene, frame_index=frame_idx,
                                   epoch=0, sensor_origin=np.zeros(3),
                                   ego_speed_mps=ego_v, object_speed_mps=obj_v,
                                   wfh_mm=sample_wfh_mm(scene, 0, 0),
                                   road_z_m=road_z)
            result = inject_plume_stateful(
                clean, boxes, context, state, seed=SEED,
                token=f"dist/{frame_idx}", config=PlumeConfig(), vehicle_class=cls)
            ray = raycast_frame(result.points, state.select_alive(), table=table,
                                road_z_m=road_z, rng=np.random.default_rng(SEED),
                                config=RaycastConfig(max_distance_m=50.0))
            if len(ray.detections):
                plume_r.append(np.linalg.norm(ray.detections[:, :2], axis=1))
                plume_nb.append(
                    _nearest_box_dist(ray.detections[:, :3], boxes))

    def pct_line(name: str, chunks: list[np.ndarray]) -> None:
        if not chunks:
            print(f"  {name:<14} (không có)")
            return
        arr = np.concatenate(chunks)
        vals = " / ".join(f"{np.percentile(arr, p):6.2f}" for p in PCT)
        print(f"  {name:<14} n={len(arr):7d}  p5/p25/p50/p75/p95 = {vals}"
              f"   mean={np.mean(arr):6.2f}")

    print(f"frames xét: {frames}")
    print()
    print(f"CỰ LY tới cảm biến (m):")
    pct_line("THẬT", real_r)
    pct_line("MÌNH", plume_r)
    print()
    print("KHOẢNG CÁCH tới vật thể gần nhất (m) — nhỏ = bám vật thể:")
    pct_line("THẬT", real_nb)
    pct_line("MÌNH", plume_nb)

    if real_r and plume_r:
        ra, rb = np.concatenate(real_r), np.concatenate(plume_r)
        na, nb = np.concatenate(real_nb), np.concatenate(plume_nb)
        print()
        print("Tỉ lệ điểm NẰM TRONG 6 m quanh vật thể:")
        print(f"  THẬT: {100*np.mean(na < 6.0):5.1f} %")
        print(f"  MÌNH: {100*np.mean(nb < 6.0):5.1f} %")
        print()
        print("Tỉ lệ điểm Ở XA hơn 25 m:")
        print(f"  THẬT: {100*np.mean(ra > 25.0):5.1f} %")
        print(f"  MÌNH: {100*np.mean(rb > 25.0):5.1f} %")

    print()
    print("SỐ CỤM mình sinh (bảng đo `cal`, cùng thứ tự paper):")
    seen = set()
    for cls, kmh, n in n_cluster_rows:
        key = (cls, round(kmh / 10) * 10)
        if key in seen:
            continue
        seen.add(key)
        print(f"  {cls:<8} {kmh:5.0f} km/h -> {n:5.1f} cụm/frame")


if __name__ == "__main__":
    main()
