"""Verify: hệ số 4× có thật là lỗi không? Và điểm/cụm sinh vs thật sau khi sửa quy ước."""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.beam_model import load_beam_table
from spray.plume import (
    PlumeConfig,
    inject_plume_stateful,
    cluster_visible_target_for_speed,
    cluster_rate_for_speed,
    steady_state_cluster_factor,
)
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.semantic_stats import cluster_angular
from spray.wet_ground import WetGroundConfig

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)
    by_scene = defaultdict(list)
    for info in infos:
        by_scene[info["token"].rsplit("/", 1)[0]].append(info)

    # ---------- 1. Kiểm "4× là lỗi hay thiết kế" ----------
    print("=" * 72)
    print("1. alive = 4×visible, NHƯNG raycast nhân survival = exp(-age/T)")
    print("   ⇒ số detection KỲ VỌNG = rate × Σexp(-k·dt/T) = rate × K = visible")
    print("   ⇒ 4× alive KHÔNG phải lỗi nếu survival được áp đúng.\n")
    cfg = PlumeConfig()
    for v_kmh in (60, 100, 120):
        vis = cluster_visible_target_for_speed(v_kmh, "crafter")
        rate = cluster_rate_for_speed(v_kmh, cfg, "crafter")
        K = steady_state_cluster_factor(v_kmh, cfg)
        T = (0.02 * 1.0 * (v_kmh - 50) + 0.2)
        n_alive = int(4 * T / 0.1)
        # kỳ vọng detection-weighted = rate × K
        print(f" v={v_kmh}: visible={vis:.1f} rate={rate:.3f} K={K:.2f} "
              f"alive=rate×4T/dt={rate*n_alive:.1f} | rate×K={rate*K:.1f} (=visible)")

    # ---------- 2. Điểm/cụm: sinh vs thật, cùng DBSCAN ----------
    print("\n" + "=" * 72)
    print("2. Điểm/cụm DBSCAN (0.7°/minPts 3) — sinh vs thật, SAU khi sửa quy ước")
    table = load_beam_table()
    wg = WetGroundConfig(enabled=True)

    for scene, ks in [
        ("Crafter_dynamic/0060_2021-09-08-16-27-14_0", (16, 24, 32)),
    ]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        state = PlumeState()
        for k, info in enumerate(frames[:40]):
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            clean = pts[lab != 2]
            real = pts[lab == 2][:, :3]
            boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(boxes) == 0:
                continue
            v = float(np.hypot(boxes[0, 7], boxes[0, 8]))
            road_z = float(np.median(boxes[:, 2]))  # ĐÁY box = mặt đường
            ctx = PlumeContext(
                scene_token=scene, frame_index=k, epoch=0,
                sensor_origin=np.zeros(3), ego_speed_mps=info["ego_speed_kmh"] / 3.6,
                object_speed_mps=v, wfh_mm=1.0, road_z_m=road_z,
            )
            res = inject_plume_stateful(clean, boxes, ctx, state, seed=0,
                                        token=scene, config=cfg, wet_ground=wg,
                                        vehicle_class="crafter")
            rc = raycast_frame(res.points_clean, state.all_alive(), table=table,
                               road_z_m=road_z, rng=np.random.default_rng(0))
            gen = np.asarray(rc.detections)
            gen = gen[:, :3] if gen.size else np.empty((0, 3))

            if k not in ks:
                continue
            print(f"\n  f={k} v={v*3.6:.0f} km/h | alive={state.counters.alive} "
                  f"det={len(gen)} | thật={len(real)}")
            for name, cloud in (("THẬT", real), ("SINH", gen)):
                if len(cloud) < 3:
                    print(f"   {name}: quá ít điểm")
                    continue
                lbl = cluster_angular(cloud, eps_deg=0.7, min_pts=3)
                ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
                if len(counts) == 0:
                    print(f"   {name}: 0 cụm")
                    continue
                print(f"   {name}: n={len(cloud)} cụm={len(counts)} | "
                      f"điểm/cụm mean={counts.mean():.1f} median={np.median(counts):.0f} "
                      f"p95={np.percentile(counts,95):.0f} max={counts.max()}")

    # ---------- 3. Wet ground: phân bố y của điểm mặt đường ----------
    print("\n" + "=" * 72)
    print("3. Wet ground: cửa sổ y=(2.0,7.0) cứng từ nguồn — có hợp SSPP không?")
    info = sorted(by_scene["Crafter_dynamic/0060_2021-09-08-16-27-14_0"],
                  key=lambda i: i["scan_id"])[16]
    pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
    lab = np.fromfile(ROOT / "Crafter_dynamic/0060_2021-09-08-16-27-14_0"
                      / "labels" / f"{info['scan_id']}.label", dtype=np.uint32)
    clean = pts[lab != 2]
    boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
    road_z = float(np.median(boxes[:, 2]))
    band = np.abs(clean[:, 2] - road_z) <= 0.2
    y = clean[band, 1]
    print(f" road_z={road_z:.2f} band n={band.sum()} ({band.mean():.1%} của frame)")
    print(f" y của điểm mặt đường: p5={np.percentile(y,5):.1f} "
          f"p25={np.percentile(y,25):.1f} p50={np.median(y):.1f} "
          f"p75={np.percentile(y,75):.1f} p95={np.percentile(y,95):.1f}")
    in_win = (y > 2.0) & (y < 7.0)
    print(f" trong cửa sổ (2,7): {in_win.sum()} ({in_win.mean():.1%}) → attenuate")
    print(f" ngoài cửa sổ: {(~in_win).sum()} ({(~in_win).mean():.1%}) → BOOST")
    print(f" |y|<2 (làn của ego): {((np.abs(y)<2)).sum()} "
          f"({(np.abs(y)<2).mean():.1%}) — đều bị BOOST")


if __name__ == "__main__":
    main()
