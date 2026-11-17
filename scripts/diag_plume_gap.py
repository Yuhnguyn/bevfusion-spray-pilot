"""Chẩn đoán: vì sao plume sinh ra thưa/cao/xa hơn spray thật.

Đo trên cùng frame, cùng scene: spray thật (label==2) vs plume sinh (raycast detections).
In bảng số theo từng đại lượng nghi vấn.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.beam_model import load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.semantic_stats import cluster_angular
from spray.wet_ground import WetGroundConfig


def load_infos(split="train"):
    with open(f"data/sspp_infos_{split}.pkl", "rb") as fh:
        return pickle.load(fh)


def load_points(info):
    path = Path(info["lidar_path"])
    if not path.exists():
        path = Path("data/SemanticSprayDataset") / info["lidar_path"]
    return np.fromfile(path, dtype=np.float32).reshape(-1, 5)


def load_labels(info):
    rel = info["token"].rsplit("/", 1)[0]
    p = Path("data/SemanticSprayDataset") / rel / "labels" / f"{info['scan_id']}.label"
    return np.fromfile(p, dtype=np.uint32)


def stats_block(name, pts):
    if len(pts) == 0:
        print(f"  {name}: n=0")
        return
    d = np.linalg.norm(pts[:, :3], axis=1)
    z = pts[:, 2]
    print(
        f"  {name}: n={len(pts)} "
        f"d_p50={np.median(d):.2f} d_p95={np.percentile(d,95):.2f} "
        f"z_p5={np.percentile(z,5):.2f} z_p50={np.median(z):.2f} "
        f"z_p95={np.percentile(z,95):.2f} z_max={z.max():.2f}"
    )


def cluster_stats(name, pts):
    if len(pts) < 3:
        print(f"  {name} clusters: n/a")
        return
    labels = cluster_angular(pts[:, :3], eps_deg=0.7, min_pts=3)
    ids, counts = np.unique(labels[labels >= 0], return_counts=True)
    if len(counts) == 0:
        print(f"  {name} clusters: 0")
        return
    print(
        f"  {name} clusters: n={len(counts)} "
        f"pts/cluster mean={counts.mean():.1f} median={np.median(counts):.0f} "
        f"p95={np.percentile(counts,95):.0f} max={counts.max()} "
        f"top5_share={np.sort(counts)[-5:].sum()/counts.sum():.2%}"
    )


def main():
    infos = load_infos("train")
    # chọn scene Crafter có box nhanh
    by_scene = {}
    for info in infos:
        by_scene.setdefault(info["token"].rsplit("/", 1)[0], []).append(info)

    targets = [
        "Crafter_dynamic/0012_2021-09-08-14-50-58_0",
        "Crafter_dynamic/0060_2021-09-08-16-27-14_0",
        "Crafter_dynamic/0084_2021-09-08-17-31-03_0",
    ]
    cfg = PlumeConfig()
    wg = WetGroundConfig(enabled=True)
    table = load_beam_table()

    for scene in targets:
        if scene not in by_scene:
            print(f"MISSING {scene}")
            continue
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        print(f"\n=== {scene} ({len(frames)} frame) ===")
        state = PlumeState()
        for k, info in enumerate(frames[:40]):
            pts = load_points(info)
            lab = load_labels(info)
            clean = pts[lab != 2]
            real = pts[lab == 2]
            boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(boxes) == 0:
                continue
            speed = float(np.hypot(boxes[0, 7], boxes[0, 8])) * 3.6
            road_z = float(np.median(boxes[:, 2] - boxes[:, 5] / 2.0))
            ctx = PlumeContext(
                scene_token=info["token"].rsplit("/", 1)[0],
                frame_index=k,
                epoch=0,
                sensor_origin=np.zeros(3, dtype=np.float64),
                ego_speed_mps=info["ego_speed_kmh"] / 3.6,
                object_speed_mps=speed / 3.6,
                wfh_mm=1.0,
                road_z_m=road_z,
            )
            res = inject_plume_stateful(
                clean, boxes, ctx, state, seed=0,
                token=info["token"], config=cfg, wet_ground=wg,
                vehicle_class="crafter",
            )
            rc = raycast_frame(
                res.points_clean, state.all_alive(), table=table,
                road_z_m=road_z, rng=np.random.default_rng(0),
            )
            gen = np.asarray(rc.detections)
            if len(gen) and gen.shape[1] >= 3:
                gen = gen[:, :3]
            else:
                gen = np.empty((0, 3))

            if k % 8 == 0 or k == len(frames) - 1:
                # hình học box
                bx = boxes[0]
                print(
                    f"\n frame={k} v={speed:.0f}km/h box: x={bx[0]:.1f} y={bx[1]:.1f} "
                    f"z={bx[2]:.2f} w={bx[3]:.2f} l={bx[4]:.2f} h={bx[5]:.2f} "
                    f"yaw={bx[6]:.2f} road_z={road_z:.2f} nbox={len(boxes)}"
                )
                print(f"  alive={state.counters.alive} spawned={state.counters.spawned}")
                stats_block("THAT", real)
                stats_block("SINH", gen)
                cluster_stats("THAT", real)
                cluster_stats("SINH", gen)


if __name__ == "__main__":
    main()
