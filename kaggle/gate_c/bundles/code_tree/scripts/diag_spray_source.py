"""Chẩn đoán 4: spray thật sinh ra từ XE NÀO — ego hay xe dẫn đường?

Đo: (a) tâm spray vs tâm box vs ego, (b) spray có nằm trong "wake" của box không,
(c) spray có đứng yên trong hệ world (⇒ do ego hắt) hay bám box (⇒ do xe trước hắt).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)
    by_scene = {}
    for info in infos:
        by_scene.setdefault(info["token"].rsplit("/", 1)[0], []).append(info)

    scene = "Crafter_dynamic/0060_2021-09-08-16-27-14_0"
    frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])

    print(f"=== {scene} ===")
    print("frame | box_x box_y | spray_centroid_x spray_centroid_y | "
          "frac_in_box_wake | frac_behind_ego")
    for k in range(0, min(40, len(frames)), 4):
        info = frames[k]
        pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
        lab = np.fromfile(
            ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
        )
        real = pts[lab == 2][:, :3]
        boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
        if len(real) == 0 or len(boxes) == 0:
            continue
        bx = boxes[0]
        # wake của box: sau đuôi (theo yaw), bán kính ngang 3 m, dài 20 m
        dx = real[:, 0] - bx[0]
        dy = real[:, 1] - bx[1]
        c, s = np.cos(-bx[6]), np.sin(-bx[6])
        lx = dx * c - dy * s   # dọc trục xe
        ly = dx * s + dy * c   # ngang
        in_wake = (lx < -bx[4] / 2) & (lx > -bx[4] / 2 - 20.0) & (np.abs(ly) < 3.0)
        behind_ego = real[:, 0] < 0.0
        print(
            f"{k:5d} | {bx[0]:6.1f} {bx[1]:5.1f} | "
            f"{np.median(real[:,0]):8.1f} {np.median(real[:,1]):8.1f} | "
            f"{in_wake.mean():6.1%} ({in_wake.sum():4d}) | "
            f"{behind_ego.mean():6.1%}"
        )

    # Kiểm: spray có đứng yên trong world frame không?
    # Nếu do ego hắt: cụm spray ở frame k và k+1 phải dịch về phía sau đúng bằng
    # quãng đường ego đi (|v|*dt) trong hệ ego.
    print("\n=== Spray có trôi ngược trong hệ ego (⇒ do ego hắt) ? ===")
    for k in (16, 20, 24):
        if k + 1 >= len(frames):
            continue
        a, b = frames[k], frames[k + 1]
        pa = np.fromfile(ROOT / a["lidar_path"], dtype=np.float32).reshape(-1, 5)
        la = np.fromfile(ROOT / scene / "labels" / f"{a['scan_id']}.label", dtype=np.uint32)
        pb = np.fromfile(ROOT / b["lidar_path"], dtype=np.float32).reshape(-1, 5)
        lb = np.fromfile(ROOT / scene / "labels" / f"{b['scan_id']}.label", dtype=np.uint32)
        ra, rb = pa[la == 2][:, :3], pb[lb == 2][:, :3]
        if len(ra) == 0 or len(rb) == 0:
            continue
        v = float(a["ego_speed_kmh"]) / 3.6
        print(
            f" f{k}->{k+1}: ego v={v*3.6:.0f} km/h, ego đi {v*0.1:.2f} m/frame | "
            f"spray_x p50: {np.median(ra[:,0]):.2f} -> {np.median(rb[:,0]):.2f} "
            f"(Δ={np.median(rb[:,0])-np.median(ra[:,0]):+.2f} m)"
        )

    # object_labels: box là gì?
    print("\n=== Box trong object_labels là gì? ===")
    ol = ROOT / scene / "object_labels" / "lidar"
    if ol.exists():
        files = sorted(ol.glob("*.json"))
        print(f" {len(files)} file, ví dụ {files[0].name}")
        data = json.loads(files[0].read_text())
        for entry in data[:2]:
            print(f"  keys={list(entry.keys())}")
            for inst in entry.get("instances", [])[:2]:
                print(f"   type={inst.get('type')} "
                      f"center={inst.get('center3D')} size={inst.get('size3D')} "
                      f"vel={inst.get('object_velocity_kmh')}")


if __name__ == "__main__":
    main()
