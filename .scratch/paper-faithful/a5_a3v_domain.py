#!/usr/bin/env python3
"""A5 — A3-V trên tập B với miền hợp lệ bật, theo ADR-0006 §5.7.

Khác `scripts/measure_following_scenario.py`:
  * bật `PLUME_PAPER_DOMAIN` (qua `PlumeStateConfig` trực tiếp, không cần env)
  * in THÊM, theo §5.7 mục 4: `R_det` p05/p50/p95, `det < 3 m` (phải 0), `x` p01/min
  * báo median + CI95 bootstrap THEO SCENE (resample scene), không pool frame

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        .scratch/paper-faithful/a5_a3v_domain.py --frames-per-scene 30
"""

from __future__ import annotations

import argparse
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

SPRAY, VEH = 2, 1
SEED = 20261119
BOOT = 2000
CI_SEED = 20261119
CLASS_DIMS = {"crafter": (6.829, 2.419, 2.621), "golf": (4.250, 2.020, 1.501)}
SPEED_BANDS = (("50–70", (50, 60, 70)), ("80–110", (80, 90, 100, 110)),
               ("120–130", (120, 130)))
REGION_DEPTH, REGION_HALF_W = 60.0, 5.0


def domain_config(wfh_mm: float, on: bool) -> PlumeStateConfig:
    """PlumeStateConfig cho một scene; `wfh_mm` chỉ dùng để tính T (spawn/T)."""
    base = PlumeStateConfig()
    if not on:
        return base
    return replace(base, diffusion_alpha=0.0, min_range_m=2.5, max_range_m=50.0)


def scene_meta(root: Path) -> list[dict]:
    out = []
    for group in ("Crafter_dynamic", "Golf_dynamic"):
        for d in sorted((root / group).iterdir(), key=lambda p: p.name):
            if not d.is_dir():
                continue
            m = read_metadata(d / "metadata.txt")
            out.append({
                "rel": f"{group}/{d.name}",
                "class": "crafter" if group.startswith("Crafter") else "golf",
                "speed": int(round(float(m["object_velocity"]))),
                "ego": float(m.get("ego_velocity") or m["object_velocity"]),
                "has_box": (d / "object_labels" / "lidar").is_dir(),
            })
    return out


def sample_b(scenes: list[dict]) -> list[dict]:
    """Tập B: 4 scene/(group, tốc độ) trong các scene KHÔNG có box — tất định."""
    unboxed = [s for s in scenes if not s["has_box"]]
    out = []
    for group in ("Crafter_dynamic", "Golf_dynamic"):
        for speed in sorted({s["speed"] for s in unboxed}):
            members = sorted((s for s in unboxed
                              if s["rel"].startswith(group) and s["speed"] == speed),
                             key=lambda s: s["rel"])
            out.extend(members[:4])
    return out


def pseudo_box(points, labels, cls):
    L, W, H = CLASS_DIMS[cls]
    xyz = points[labels == VEH][:, :3]
    if xyz.shape[0] < 10:
        return None
    rear = float(np.percentile(xyz[:, 0], 2.0))
    return np.array([[rear + L / 2, float(np.median(xyz[:, 1])),
                      float(np.percentile(xyz[:, 2], 2.0)), L, W, H, 0, 0, 0]],
                    dtype=np.float32)


def region_mask(xyz, rear_x, road_z):
    if xyz.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    depth = rear_x - xyz[:, 0]
    h = xyz[:, 2] - road_z
    return ((depth >= 0) & (depth < REGION_DEPTH)
            & (np.abs(xyz[:, 1]) <= REGION_HALF_W) & (h >= 0) & (h <= 3.0))


def run_scene(scene, root, frames, domain_on, use_wfh_sampling):
    sc = root / scene["rel"]
    scans = sorted(p.stem for p in (sc / "velodyne").glob("*.bin"))
    idx = sorted({int(i) for i in np.linspace(0, len(scans) - 1, frames).round().tolist()})
    obj_v, ego_v = scene["speed"] / 3.6, scene["ego"] / 3.6
    scfg = domain_config(1.0, domain_on)
    state = PlumeState(scfg)
    cfg = PlumeConfig()
    table = load_beam_table()

    wfh = (sample_wfh_mm(scene["rel"], 0, 0) if use_wfh_sampling else None)
    rows = []
    for pos, i in enumerate(idx):
        sid = scans[i]
        pts = np.fromfile(sc / "velodyne" / f"{sid}.bin", dtype=np.float32).reshape(-1, 5)
        lab = np.fromfile(sc / "labels" / f"{sid}.label", dtype=np.uint32)
        if lab.size != pts.shape[0]:
            continue
        if scene["has_box"]:
            bp = sc / "object_labels" / "lidar" / f"{sid}.json"
            if not bp.is_file():
                continue
            boxes, _, _ = _boxes_to_arrays(read_frame_boxes(bp), obj_v)
            road_z = float(np.median(boxes[:, 2]))
        else:
            b = pseudo_box(pts, lab, scene["class"])
            if b is None:
                continue
            boxes = b
            road_z = float(np.percentile(pts[:, 2], 5.0))
        if len(boxes) == 0:
            continue

        clean = pts[lab != SPRAY].astype(np.float32)
        ctx = PlumeContext(scene_token=scene["rel"], frame_index=pos, epoch=0,
                           sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                           object_speed_mps=obj_v,
                           wfh_mm=float(wfh) if wfh is not None else 1.0,
                           road_z_m=road_z)
        res = inject_plume_stateful(clean, boxes, ctx, state, seed=SEED,
                                    token=f"a5/{scene['rel']}/{pos}", config=cfg,
                                    vehicle_class=scene["class"])
        keep = state.select_alive()
        ray = raycast_frame(
            res.points, keep, table=table, road_z_m=road_z,
            rng=np.random.default_rng(SEED),
            config=RaycastConfig(max_distance_m=(50.0 if domain_on else 100.0)),
        )
        det = ray.detections
        rear_x = float(boxes[0][0]) - float(boxes[0][3]) / 2.0
        m_real = region_mask(pts[:, :3].astype(np.float64), rear_x, road_z) & (lab == SPRAY)
        m_gen = region_mask(det[:, :3].astype(np.float64), rear_x, road_z) if len(det) \
            else np.zeros(0, dtype=bool)
        n_real, n_gen = int(m_real.sum()), int(m_gen.sum())

        det_r = np.linalg.norm(det[:, :3], axis=1) if len(det) else np.zeros(0)
        det_x = det[:, 0] if len(det) else np.zeros(0)
        rows.append({
            "real": n_real, "gen": n_gen,
            "det": int(len(det)),
            "r_p05": float(np.percentile(det_r, 5)) if det_r.size else float("nan"),
            "r_p50": float(np.percentile(det_r, 50)) if det_r.size else float("nan"),
            "r_p95": float(np.percentile(det_r, 95)) if det_r.size else float("nan"),
            "lt3": int((det_r < 3.0).sum()),
            "x_p01": float(np.percentile(det_x, 1)) if det_x.size else float("nan"),
            "x_min": float(det_x.min()) if det_x.size else float("nan"),
        })
    return {"scene": scene, "wfh": wfh, "frames": rows}


def bootstrap_median(scene_ratios):
    pooled = [v for r in scene_ratios for v in r]
    if not pooled:
        return float("nan"), float("nan"), float("nan")
    med = float(np.median(pooled))
    if len(scene_ratios) < 2:
        return med, med, med
    rng = np.random.default_rng(CI_SEED)
    boots = np.empty(BOOT)
    n = len(scene_ratios)
    for b in range(BOOT):
        pick = rng.integers(0, n, n)
        sample = [v for p in pick for v in scene_ratios[int(p)]]
        boots[b] = np.median(sample) if sample else np.nan
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return med, float(lo), float(hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO / "data" / "SemanticSprayDataset"))
    ap.add_argument("--frames-per-scene", type=int, default=30)
    ap.add_argument("--no-wfh-sampling", dest="wfh_sampling", action="store_false", default=True,
                    help="lấy mẫu wfh theo scene (§V); mặc định giữ 1,0 mm")
    ap.add_argument("--out", default=str(REPO / ".scratch/tmp/a5_domain.json"))
    args = ap.parse_args()

    root = Path(args.root)
    members = sample_b(scene_meta(root))
    print(f"A5: {len(members)} scene (tập B), {args.frames_per_scene} frame/scene, "
          f"PLUME domain ON, wfh={'sampled' if args.wfh_sampling else '1.0 mm'}",
          flush=True)

    results = []
    for k, scene in enumerate(members, 1):
        results.append(run_scene(scene, root, args.frames_per_scene, True,
                                 args.wfh_sampling))
        print(f"  [{k}/{len(members)}] {scene['rel']} {scene['speed']} km/h", flush=True)

    print(f"\n{'class':>8} {'band':>8} {'scene':>5} {'frame':>6} {'real/f':>8} "
          f"{'gen/f':>8} {'median [CI95]':>22} {'R p05/p50/p95 (m)':>20} "
          f"{'<3 med':>6} {'<3 mean':>7} {'<3 max':>6} {'frames w/ <3m':>13} "
          f"{'x p01':>7} {'x min':>7}", flush=True)
    summary = []
    for band, speeds in SPEED_BANDS:
        for cls in ("crafter", "golf"):
            sel = [r for r in results
                   if r["scene"]["class"] == cls and r["scene"]["speed"] in speeds
                   and r["frames"]]
            if not sel:
                continue
            ratios = [[f["gen"] / f["real"] for f in r["frames"] if f["real"] > 0]
                      for r in sel]
            ratios = [r for r in ratios if r]
            med, lo, hi = bootstrap_median(ratios)
            allf = [f for r in sel for f in r["frames"]]
            real = np.mean([f["real"] for f in allf])
            gen = np.mean([f["gen"] for f in allf])
            r05 = np.nanmedian([f["r_p05"] for f in allf])
            r50 = np.nanmedian([f["r_p50"] for f in allf])
            r95 = np.nanmedian([f["r_p95"] for f in allf])
            lt3 = int(np.median([f["lt3"] for f in allf]))
            lt3_max = int(max(f["lt3"] for f in allf))
            lt3_mean = float(np.mean([f["lt3"] for f in allf]))
            lt3_frames = int(sum(1 for f in allf if f["lt3"] > 0))
            xp = np.nanmedian([f["x_p01"] for f in allf])
            xm = np.nanmin([f["x_min"] for f in allf])
            print(f"{cls:>8} {band:>8} {len(sel):>5} {len(allf):>6} {real:8.1f} "
                  f"{gen:8.1f} {med:7.2f} [{lo:6.2f}; {hi:6.2f}] "
                  f"{r05:6.1f}/{r50:5.1f}/{r95:5.1f} "
                  f"{lt3:5d} {lt3_mean:5.1f} {lt3_max:4d} {lt3_frames:4d}/{len(allf):<4d} "
                  f"{xp:7.1f} {xm:7.1f}",
                  flush=True)
            summary.append({"class": cls, "band": band, "n_scene": len(sel),
                            "n_frame": len(allf), "real_per_frame": real,
                            "gen_per_frame": gen, "median_ratio": med,
                            "ci95": [lo, hi], "r_p05": float(r05),
                            "r_p50": float(r50), "r_p95": float(r95),
                            "det_lt3m_median": lt3,
                            "det_lt3m_mean": lt3_mean,
                            "det_lt3m_max": lt3_max,
                            "frames_with_lt3m": lt3_frames,
                            "x_p01": float(xp), "x_min": float(xm)})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"wfh_sampling": args.wfh_sampling,
                               "domain": {"diffusion_alpha": 0.0,
                                          "min_range_m": 2.5, "max_range_m": 50.0},
                               "summary": summary}, indent=1), encoding="utf-8")
    print(f"\nA5_WRITTEN {out}")


if __name__ == "__main__":
    main()
