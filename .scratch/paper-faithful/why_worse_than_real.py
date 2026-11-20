#!/usr/bin/env python3
"""VÌ SAO plume của mình tệ hơn spray thật 5 lần?

Cùng tập test, cùng checkpoint:
    clean   recall 0,8208
    real    recall 0,7767   -> Δ = −0,0441   (spray THẬT của SemanticSpray)
    plume   recall 0,6080   -> Δ = −0,2188   (generator của mình)

Plume của mình hại gấp **4,96 lần** spray thật. Câu hỏi: khác nhau ở đâu?

Mạng nơ-ron chỉ nhìn thấy các điểm. Nên so đúng thứ nó nhìn thấy: **các điểm nằm
trong vành 2–6 m quanh vật thể**, ở hai nhánh.

  - nhánh `real`: điểm spray thật = điểm có label == 2 trong dữ liệu gốc (chính là
    phần bị loại khỏi `clean`). Đây là thứ cảm biến thật ghi được từ nước.
  - nhánh `plume`: điểm plume generator sinh ra (sau raycast).

So ba thứ, vì cả ba đều đi vào input của detector:
  1. SỐ điểm trong vành (mật độ)
  2. INTENSITY của các điểm đó (kênh thứ 4 trong 5 kênh)
  3. phân bố độ cao z / cự ly
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
N_SCENE = 6
N_FRAME = 8


def main() -> None:
    # scene nào có trong jsonl (== 12 scene test)
    scenes: dict[str, list[int]] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] == "clean":
                scenes.setdefault(row["scene_token"], []).append(row["frame_idx"])

    table = load_beam_table()
    real_ring, plume_ring = [], []
    real_all, plume_all = [], []

    for scene in sorted(scenes)[:N_SCENE]:
        path = ROOT / scene
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
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

            # --- spray THẬT: điểm label == 2
            real_pts = points[labels == SPRAY]
            if len(real_pts):
                real_all.append(real_pts)
                real_ring.append(_ring_count(real_pts[:, :3], boxes))

            # --- plume GENERATOR
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
                token=f"cmp/{frame_idx}", config=PlumeConfig(), vehicle_class=cls)
            ray = raycast_frame(result.points, state.select_alive(), table=table,
                                road_z_m=road_z, rng=np.random.default_rng(SEED),
                                config=RaycastConfig(max_distance_m=50.0))
            if len(ray.detections):
                plume_all.append(ray.detections)
                plume_ring.append(_ring_count(ray.detections[:, :3], boxes))

    def report(name: str, chunks: list[np.ndarray], rings: list[float]) -> dict:
        if not chunks:
            print(f"{name}: không có dữ liệu")
            return {}
        arr = np.concatenate(chunks, axis=0)
        inten = arr[:, 3]
        z = arr[:, 2]
        r = np.linalg.norm(arr[:, :2], axis=1)
        stats = {
            "n_points": len(arr),
            "ring_mean": float(np.mean(rings)),
            "int_p50": float(np.median(inten)),
            "int_mean": float(np.mean(inten)),
            "int_zero_pct": float(100.0 * np.mean(np.isclose(inten, 0.0))),
            "z_p50": float(np.median(z)),
            "r_p50": float(np.median(r)),
        }
        print(f"\n{name}:")
        print(f"  tổng điểm (đã raycast): {stats['n_points']}")
        print(f"  điểm trong vành 2-6 m / frame: {stats['ring_mean']:.1f}")
        print(f"  intensity  p50/mean = {stats['int_p50']:.3f} / {stats['int_mean']:.3f}")
        print(f"  intensity == 0      = {stats['int_zero_pct']:.1f} %")
        print(f"  z p50 = {stats['z_p50']:+.2f} m    r p50 = {stats['r_p50']:.2f} m")
        return stats

    print("=" * 70)
    print("SO SÁNH ĐIỂM MÀ DETECTOR NHÌN THẤY")
    print("=" * 70)
    s_real = report("SPRAY THẬT (label==2, cảm biến thật ghi)", real_all, real_ring)
    s_plume = report("PLUME GENERATOR (sau raycast)", plume_all, plume_ring)

    if s_real and s_plume:
        print()
        print("=" * 70)
        print("TỈ SỐ plume / thật")
        print("=" * 70)
        for key in ("n_points", "ring_mean", "int_p50", "int_mean"):
            a, b = s_real.get(key, 0), s_plume.get(key, 0)
            ratio = b / a if a else float("inf")
            print(f"  {key:<12} {a:10.2f} -> {b:10.2f}   = {ratio:6.2f}x")


def _ring_count(xyz: np.ndarray, boxes: np.ndarray) -> float:
    """Số điểm trong vành BEV 2-6 m quanh BẤT KỲ hộp GT nào (đếm 1 lần/điểm)."""
    if len(xyz) == 0 or len(boxes) == 0:
        return 0.0
    mask_any = np.zeros(len(xyz), dtype=bool)
    for box in boxes:
        dist = np.linalg.norm(xyz[:, :2] - box[:2], axis=1)
        mask_any |= (dist >= 2.0) & (dist < 6.0)
    return float(mask_any.sum())


if __name__ == "__main__":
    main()
