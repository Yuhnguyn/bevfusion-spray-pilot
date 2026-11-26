#!/usr/bin/env python3
"""Dump plume của MỘT scene ra .npz, chạy được trên cả code cũ và mới.

Khác biệt interface giữa 2 bản:
  cũ  (<= ff6d5e8): env PLUME_PAPER_DOMAIN=1 bật miền; wfh luôn 1.0 nếu env tắt
  mới (>= d9646ec): tham số sample_water_film / water_film_mm; miền là default

Chế độ:
  --mode old        production trước A9: alpha=0.06, miền ∞, wfh=1.0 cố định
  --mode old-cacha  Cách A trước A9: alpha=0, miền 2.5-50, wfh mẫu theo scene
  --mode new        default hiện tại: không tán xạ, miền 2.5-50, wfh mẫu
"""
from __future__ import annotations

import argparse
import inspect
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(os.environ.get("SPRAY_REPO", "/Users/huynguyen/projects/bevfusion-spray-pilot"))
sys.path.insert(0, str(REPO))

from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import RaycastConfig, raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

SPRAY, VEH = 2, 1
SEED = 20261119
CLASS_DIMS = {"crafter": (6.829, 2.419, 2.621), "golf": (4.250, 2.020, 1.501)}

_PARAMS = inspect.signature(inject_plume_stateful).parameters
HAS_WFH_PARAMS = "water_film_mm" in _PARAMS


def build_state(mode: str) -> PlumeState:
    cfg = PlumeStateConfig()
    if mode == "new":
        return PlumeState(cfg)
    # bản cũ: miền ∞ + alpha 0.06 (production) hoặc miền bật + alpha 0 (Cách A)
    from dataclasses import replace

    if mode == "old":
        return PlumeState(replace(cfg, diffusion_alpha=0.06,
                                  min_range_m=0.0, max_range_m=float("inf")))
    return PlumeState(replace(cfg, diffusion_alpha=0.0,
                             min_range_m=2.5, max_range_m=50.0))


def call_inject(mode, clean, boxes, ctx, state, seed, token, cfg, cls):
    if HAS_WFH_PARAMS:
        return inject_plume_stateful(
            clean, boxes, ctx, state, seed=seed, token=token,
            config=cfg, vehicle_class=cls,
            sample_water_film=(mode != "old"),
            water_film_mm=(1.0 if mode == "old" else None),
        )
    return inject_plume_stateful(
        clean, boxes, ctx, state, seed=seed, token=token,
        config=cfg, vehicle_class=cls,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["old", "old-cacha", "new"])
    ap.add_argument("--scene", required=True)
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.mode in ("old", "old-cacha"):
        if HAS_WFH_PARAMS:
            raise SystemExit("mode cu nhung code moi — sai SPRAY_REPO?")
    if args.mode == "old-cacha":
        os.environ["PLUME_PAPER_DOMAIN"] = "1"
    elif args.mode == "old":
        os.environ.pop("PLUME_PAPER_DOMAIN", None)

    sc = REPO / "data" / "SemanticSprayDataset" / args.scene
    meta = read_metadata(sc / "metadata.txt")
    obj_kmh = float(meta["object_velocity"])
    ego_kmh = float(meta.get("ego_velocity") or obj_kmh)
    obj_v, ego_v = obj_kmh / 3.6, ego_kmh / 3.6
    cls = "crafter" if "Crafter" in args.scene else "golf"

    scans = sorted(p.stem for p in (sc / "velodyne").glob("*.bin"))
    selected = scans[args.start:args.start + args.frames]

    table = load_beam_table()
    cfg = PlumeConfig()
    state = build_state(args.mode)
    # PHẢI khớp đúng seed mà inject dùng: _rng(seed=SEED, ...) => sample_wfh_mm(...,SEED).
    # Lấy seed=0 sẽ lệch (1.20 thay vì 0.609) và nhãn trên hình thành sai.
    wfh_used = sample_wfh_mm(args.scene, 0, SEED) if args.mode != "old" else 1.0

    out = {"real": [], "gen": [], "clean_bg": [], "veh": [], "boxes": [],
           "frame": [], "radius": [], "range": [], "n_alive": []}

    for pos, sid in enumerate(selected):
        pts = np.fromfile(sc / "velodyne" / f"{sid}.bin", dtype=np.float32).reshape(-1, 5)
        lab = np.fromfile(sc / "labels" / f"{sid}.label", dtype=np.uint32)
        if lab.size != pts.shape[0]:
            lab = np.zeros(pts.shape[0], dtype=np.uint32)
        bp = sc / "object_labels" / "lidar" / f"{sid}.json"
        if bp.is_file():
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(bp), obj_v)
            road_z = float(np.median(boxes[:, 2]))
        else:
            xyz = pts[lab == VEH][:, :3]
            if xyz.shape[0] < 10:
                continue
            L, W, H = CLASS_DIMS[cls]
            rear = float(np.percentile(xyz[:, 0], 2.0))
            boxes = np.array([[rear + L / 2, float(np.median(xyz[:, 1])),
                               float(np.percentile(xyz[:, 2], 2.0)), L, W, H, 0, 0, 0]],
                             dtype=np.float32)
            road_z = float(np.percentile(pts[:, 2], 5.0))

        clean = pts[lab != SPRAY].astype(np.float32)
        ctx = PlumeContext(
            scene_token=args.scene, frame_index=pos, epoch=0,
            sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
            object_speed_mps=obj_v, road_z_m=road_z,
            wfh_mm=(1.0 if args.mode == "old" else wfh_used),
        )
        # Token KHONG duoc chua mode: _rng(seed, token) hash ca token, nen token
        # khac nhau => RNG stream khac nhau => so cum khac nhau. Do la nhieu, khong
        # phai thay doi cua code. Ba mode phai dung CHUNG mot token.
        res = call_inject(args.mode, clean, boxes, ctx, state, SEED,
                          f"viz/cmp/{pos}", cfg, cls)
        alive = state.select_alive()
        rc = raycast_frame(res.points, alive, table=table, road_z_m=road_z,
                           rng=np.random.default_rng(SEED),
                           config=RaycastConfig(max_distance_m=50.0))
        det = rc.detections[:, :3] if len(rc.detections) else np.zeros((0, 3))

        out["real"].append(pts[lab == SPRAY][:, :3])
        out["gen"].append(det)
        out["clean_bg"].append(clean[:, :3][::3])
        out["veh"].append(clean[:, :3][lab[lab != SPRAY] == VEH])
        out["boxes"].append(boxes[:7])
        out["frame"].append(pos)
        out["radius"].append(np.array([c.radius for c in alive], dtype=np.float32))
        out["range"].append(np.array([float(np.linalg.norm(c.pos)) for c in alive],
                                     dtype=np.float32))
        out["n_alive"].append(len(alive))
        if pos % 10 == 0 or pos == len(selected) - 1:
            print(f"  [{pos+1}/{len(selected)}] real {len(pts[lab == SPRAY]):5d} "
                  f"gen {len(det):5d} alive {len(alive):4d}", flush=True)

    np.savez_compressed(
        args.out,
        mode=args.mode, scene=args.scene, obj_kmh=obj_kmh, ego_kmh=ego_kmh,
        wfh_mm=wfh_used, road_z=road_z,
        **{k: np.array(v, dtype=object) for k, v in out.items()},
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
