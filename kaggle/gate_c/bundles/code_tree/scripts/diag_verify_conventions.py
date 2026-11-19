"""Verify 5 góp ý về quy ước z / trục / thống kê.

Mỗi mục in ĐÚNG/SAI kèm số đo.
"""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.semantic_stats import cluster_angular
from spray.wet_ground import WetGroundConfig, apply_wet_ground

ROOT = Path("data/SemanticSprayDataset")


def load_infos(split="train"):
    with open(f"data/sspp_infos_{split}.pkl", "rb") as fh:
        return pickle.load(fh)


def main():
    infos = load_infos("train")
    by_scene = defaultdict(list)
    for info in infos:
        by_scene[info["token"].rsplit("/", 1)[0]].append(info)

    # ---------- (a) box[2] là đáy hay tâm? ----------
    print("=" * 70)
    print("(a) box[2] là ĐÁY box hay TÂM box?")
    info = sorted(by_scene["Crafter_dynamic/0060_2021-09-08-16-27-14_0"],
                  key=lambda i: i["scan_id"])[16]
    bx = np.asarray(info["gt_boxes"], dtype=np.float32)[0]
    pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
    # đáy thật = z thấp nhất của điểm trong box footprint
    dx = pts[:, 0] - bx[0]
    dy = pts[:, 1] - bx[1]
    c, s = np.cos(-bx[6]), np.sin(-bx[6])
    lx = dx * c - dy * s
    ly = dx * s + dy * c
    inside = (np.abs(lx) < 3.0) & (np.abs(ly) < 1.2)
    z_in = pts[inside, 2]
    print(f" box[2]={bx[2]:.3f} box[3]={bx[3]:.2f} box[4]={bx[4]:.2f} "
          f"box[5]={bx[5]:.2f} box[6]={bx[6]:.3f}")
    print(f" điểm trong footprint: n={inside.sum()} z_min={z_in.min():.2f} "
          f"z_p5={np.percentile(z_in,5):.2f} z_p50={np.median(z_in):.2f}")
    print(f" → nếu box[2] là ĐÁY: z_min ≈ box[2] = {bx[2]:.2f}")
    print(f" → nếu box[2] là TÂM : z_min ≈ box[2]-h/2 = {bx[2]-bx[5]/2:.2f}")
    print(f" KẾT LUẬN: box[2] là "
          f"{'ĐÁY' if abs(z_in.min()-bx[2]) < abs(z_in.min()-(bx[2]-bx[5]/2)) else 'TÂM'}")

    # ---------- (e) box[3], box[4] là gì? ----------
    print("=" * 70)
    print("(e) box[3]/box[4] = (dài, rộng) hay (rộng, dài)?")
    ext_x = lx[inside].max() - lx[inside].min()
    ext_y = ly[inside].max() - ly[inside].min()
    print(f" extent thật của điểm trong box: dọc={ext_x:.2f} m ngang={ext_y:.2f} m")
    print(f" box[3]={bx[3]:.2f} box[4]={bx[4]:.2f}")
    print(f" → box[3] khớp {'dọc(dài)' if abs(bx[3]-ext_x)<abs(bx[3]-ext_y) else 'ngang(rộng)'}")
    print(f" → box[4] khớp {'dọc(dài)' if abs(bx[4]-ext_x)<abs(bx[4]-ext_y) else 'ngang(rộng)'}")
    print("\n plume.py:511 unpack `_, length, height, yaw = box[3:7]`:")
    print(f"   _       = box[3] = {bx[3]:.2f}  (bị BỎ)")
    print(f"   length  = box[4] = {bx[4]:.2f}  ← dùng làm offset")
    print(f"   height  = box[5] = {bx[5]:.2f}")
    print(f"   yaw     = box[6] = {bx[6]:.3f}")
    print(f"   Nếu box[3]=dài và box[4]=rộng ⇒ length bị nhầm = {bx[4]:.2f} "
          f"thay vì {bx[3]:.2f}")

    # ---------- (a) road_z đúng vs sai ----------
    print("=" * 70)
    print("(a) road_z: sai (box[2]-h/2) vs đúng (box[2])")
    for scene, ks in [
        ("Crafter_dynamic/0060_2021-09-08-16-27-14_0", (16, 24, 32)),
        ("Crafter_dynamic/0084_2021-09-08-17-31-03_0", (16, 24, 32)),
    ]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        for k in ks:
            if k >= len(frames):
                continue
            info = frames[k]
            bxs = np.asarray(info["gt_boxes"], dtype=np.float32)
            if len(bxs) == 0:
                continue
            wrong = float(np.median(bxs[:, 2] - bxs[:, 5] / 2.0))
            right = float(np.median(bxs[:, 2]))
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            real = pts[lab == 2]
            if len(real) == 0:
                continue
            z = real[:, 2]
            print(f" {scene.split('/')[0]}/{scene.split('/')[1][:4]} f={k}: "
                  f"road_z sai={wrong:.2f} đúng={right:.2f} (lệch {right-wrong:+.2f} m)")
            print(f"   z trên mặt đường: SAI p50={np.median(z)-wrong:.2f} "
                  f"p95={np.percentile(z,95)-wrong:.2f} | "
                  f"ĐÚNG p50={np.median(z)-right:.2f} p95={np.percentile(z,95)-right:.2f}")
            print(f"   nóc box = {right + bxs[0,5]:.2f} m; z_max thật = {z.max():.2f}")

    # ---------- (a) wet ground với road_z đúng ----------
    print("=" * 70)
    print("(a) wet ground: points_in với road_z sai vs đúng")
    scene = "Crafter_dynamic/0060_2021-09-08-16-27-14_0"
    frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
    info = frames[16]
    bxs = np.asarray(info["gt_boxes"], dtype=np.float32)
    pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
    lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label", dtype=np.uint32)
    clean = pts[lab != 2]
    wg = WetGroundConfig(enabled=True)
    for name, rz in [("SAI", float(np.median(bxs[:, 2] - bxs[:, 5] / 2.0))),
                     ("ĐÚNG", float(np.median(bxs[:, 2])))]:
        out, st = apply_wet_ground(clean, road_z_m=rz, wfh_mm=1.0, config=wg)
        print(f" road_z={name} ({rz:.2f}): points_in={st.points_in} "
              f"({st.points_in/len(clean):.1%}) attenuated={st.attenuated} "
              f"boosted={st.boosted} mean_ratio={st.mean_ratio:.3f}")

    # ---------- (b) generator box_bottom ----------
    print("=" * 70)
    print("(b) generator đặt khối ở đâu (box_bottom = z - h/2 vs z)")
    cfg = PlumeConfig()
    state = PlumeState()
    bxs1 = np.asarray([[22.0, 0.0, -1.6, 6.83, 2.42, 2.62, 0.0, 27.8, 0.0]],
                      dtype=np.float32)
    ctx = PlumeContext(scene_token="probe", frame_index=0, epoch=0,
                       sensor_origin=np.zeros(3), ego_speed_mps=27.8,
                       object_speed_mps=27.8, wfh_mm=1.0, road_z_m=-1.6)
    inject_plume_stateful(np.zeros((100, 5), dtype=np.float32), bxs1, ctx, state,
                          seed=0, token="probe", config=cfg, wet_ground=None)
    alive = state.all_alive()
    zs = np.array([c.pos[2] for c in alive])
    frac_lo, frac_hi = cfg.tail_block_height_frac
    wrong_lo = -1.6 - 2.62 / 2 + frac_lo * 2.62
    wrong_hi = -1.6 - 2.62 / 2 + frac_hi * 2.62
    right_lo = -1.6 + frac_lo * 2.62
    right_hi = -1.6 + frac_hi * 2.62
    print(f" box[2]={-1.6:.2f} (đáy), h=2.62")
    print(f" CODE HIỆN TẠI: khối z ∈ [{wrong_lo:.2f}, {wrong_hi:.2f}] "
          f"(đo được: {zs.min():.2f} … {zs.max():.2f})")
    print(f" NẾU box_bottom=z: khối z ∈ [{right_lo:.2f}, {right_hi:.2f}]")
    print(f" → code đặt khối THẤP hơn {right_lo-wrong_lo:.2f} m")

    # ---------- (c) median vs mean điểm/cụm ----------
    print("=" * 70)
    print("(c) điểm/cụm: mean vs median, và đuôi phân bố")
    for scene in ["Crafter_dynamic/0060_2021-09-08-16-27-14_0",
                  "Crafter_dynamic/0084_2021-09-08-17-31-03_0"]:
        frames = sorted(by_scene[scene], key=lambda i: i["scan_id"])
        for k in (16, 24, 32):
            if k >= len(frames):
                continue
            info = frames[k]
            pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
            lab = np.fromfile(ROOT / scene / "labels" / f"{info['scan_id']}.label",
                              dtype=np.uint32)
            real = pts[lab == 2][:, :3]
            if len(real) < 10:
                continue
            lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
            ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
            if len(counts) == 0:
                continue
            print(f" {scene.split('/')[1][:4]} f={k} n={len(real)} "
                  f"clusters={len(counts)} | điểm/cụm: "
                  f"mean={counts.mean():.1f} median={np.median(counts):.0f} "
                  f"p95={np.percentile(counts,95):.0f} max={counts.max()}")

    # ---------- (d) độ dài scene toàn train ----------
    print("=" * 70)
    print("(d) độ dài scene trên toàn train")
    lens = sorted(len(v) for v in by_scene.values())
    arr = np.array(lens)
    print(f" n_scene={len(arr)} min={arr.min()} p25={np.percentile(arr,25):.0f} "
          f"median={np.median(arr):.0f} p75={np.percentile(arr,75):.0f} max={arr.max()}")
    print(f" scene < 64 frame (chưa đạt dừng @120): {(arr<64).sum()}/{len(arr)} "
          f"= {(arr<64).mean():.0%}")
    print(f" scene < 48 frame (chưa đạt dừng @100): {(arr<48).sum()}/{len(arr)} "
          f"= {(arr<48).mean():.0%}")
    print(f" phân bố: {dict(zip(*np.unique(arr//10*10, return_counts=True)))}")


if __name__ == "__main__":
    main()
