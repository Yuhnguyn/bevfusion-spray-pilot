#!/usr/bin/env python3
"""ROOT CAUSE: nghịch lý "spray nhiều hại ít" — biến thật là ĐỘ MONG CỦA VẬT THỂ.

Phân tích trước cho thấy:
    corr(spray/f, base_pts/f)  = −0,627   (điểm nền nhiều -> spray ít)
    corr(clean_rec, spray/f)   = +0,537   (scene dễ -> spray nhiều)
    corr(clean_rec, Δrecall)   = +0,205
⇒ `spray/frame` KHÔNG phải biến nhân quả; nó đang đại diện cho **độ khó scene**.
   Ở scene dễ, detector vốn mạnh nên spray nhiều cũng ít hại. Đó là lý do tương
   quan ra dấu dương — confound, không phải "liều thấp nguy hiểm hơn".

Script này đo biến vật lý đứng sau "độ khó": **số điểm LiDAR trên mỗi vật thể**.
Giả thuyết H-fragile: vật thể càng ít điểm thì confidence càng mỏng manh, nên
cùng một lượng nhiễu sẽ đánh sập dễ hơn. Nếu đúng thì:
  * corr(điểm xe / box, Δrecall) phải DƯƠNG mạnh (nhiều điểm -> sụt ít);
  * và `spray/frame` tương quan với "điểm xe/box" (vì vật thể gần, nhiều điểm,
    cũng cho nhiều tia trúng cụm hơn) ⇒ giải thích luôn dấu dương của spray.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SUMMARY = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections_summary.json"
ROOT = REPO / "data/SemanticSprayDataset"
SPRAY, VEH = 2, 1


def main() -> None:
    summary = json.load(open(SUMMARY))
    paired = summary["summary"]["paired"]["plume_minus_clean"]
    rec = paired["recall_per_scene"]

    agg: dict[str, dict] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            entry = agg.setdefault(row["scene_token"],
                                   {"inj": [], "base": [], "n_frame": 0})
            if row["arm"] == "plume":
                entry["inj"].append(int(row["n_injected"]))
            elif row["arm"] == "clean":
                entry["base"].append(int(row["n_real_points_before"]))
                entry["n_frame"] += 1

    rows = []
    for scene in sorted(agg):
        if scene not in rec["clean"]:
            continue
        path = ROOT / scene
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6

        veh_per_box, dist_p50 = [], []
        scans = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))
        for scan in scans:
            points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                                 dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
            boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
            if labels.size != points.shape[0] or not boxes_json.is_file():
                continue
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
            if len(boxes) == 0:
                continue
            n_veh = int((labels == VEH).sum())
            veh_per_box.append(n_veh / len(boxes))
            dist_p50.append(float(np.median(np.linalg.norm(boxes[:, :2], axis=1))))

        rows.append({
            "scene": scene,
            "clean": rec["clean"][scene],
            "d_plume": rec["plume"][scene] - rec["clean"][scene],
            "spray": float(np.mean(agg[scene]["inj"])),
            "base": float(np.mean(agg[scene]["base"])),
            "veh_per_box": float(np.mean(veh_per_box)) if veh_per_box else float("nan"),
            "dist_p50": float(np.mean(dist_p50)) if dist_p50 else float("nan"),
        })

    print(f"{'scene':<24} {'clean':>6} {'d_plume':>8} {'spray/f':>8} "
          f"{'veh_pts/box':>11} {'box_dist':>8}")
    for row in rows:
        print(f"{row['scene'].split('/')[1][:22]:<24} {row['clean']:6.3f} "
              f"{row['d_plume']:+8.3f} {row['spray']:8.1f} "
              f"{row['veh_per_box']:11.1f} {row['dist_p50']:8.2f}")

    d = np.array([r["d_plume"] for r in rows])
    spray = np.array([r["spray"] for r in rows])
    veh = np.array([r["veh_per_box"] for r in rows])
    dist = np.array([r["dist_p50"] for r in rows])
    clean = np.array([r["clean"] for r in rows])
    base = np.array([r["base"] for r in rows])

    def corr(x, y):
        return float(np.corrcoef(x, y)[0, 1])

    print()
    print("Tương quan với Δrecall:")
    for name, arr in (("điểm xe/box", veh), ("khoảng cách box", dist),
                      ("spray/frame", spray), ("clean_recall", clean),
                      ("điểm nền/frame", base)):
        print(f"  {name:<18} r = {corr(arr, d):+.3f}")

    print()
    print("Giải thích dấu dương của spray/frame:")
    print(f"  corr(spray/f, điểm xe/box) = {corr(spray, veh):+.3f}")
    print(f"  corr(spray/f, box_dist)    = {corr(spray, dist):+.3f}")
    print(f"  corr(điểm xe/box, box_dist) = {corr(veh, dist):+.3f}")

    print()
    print("Chuẩn hoá: mất bao nhiêu ĐIỂM RECALL cho mỗi 1 % điểm plume thêm vào,")
    print("chia theo độ mỏng của vật thể:")
    inj_pct = 100.0 * spray / base
    order = np.argsort(veh)
    third = len(order) // 3
    for label, idx in (("mỏng nhất", order[:third]),
                       ("giữa", order[third:2 * third]),
                       ("dày nhất", order[2 * third:])):
        print(f"  {label:<11} n={len(idx):2d}  điểm xe/box p50 {np.median(veh[idx]):7.1f}  "
              f"Δrecall p50 {np.median(d[idx]):+.3f}  "
              f"inj% p50 {np.median(inj_pct[idx]):5.3f}  "
              f"Δ/1% = {np.median(d[idx]/np.maximum(inj_pct[idx],1e-9)):+.2f}")


if __name__ == "__main__":
    main()
