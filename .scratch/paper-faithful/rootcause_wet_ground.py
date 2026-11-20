#!/usr/bin/env python3
"""ROOT CAUSE: wet_ground có phải biến gây sụt score? (confound cuối chưa loại)

Đã đo và LOẠI:
  - voxel eviction (max_num_points=10) : 0 điểm xe bị cắt
  - mất điểm vật thể                     : 176 070 -> 176 190 (+0,1 %), KHÔNG mất
  - hộp giả tranh chỗ (decoy)            : nhóm giữ có decoy NHIỀU hơn nhóm mất
  - che khuất ở tầng điểm                 : điểm xe còn nguyên => không thể
  - hiệu ứng toàn cục                     : cục bộ trong ~6 m

Vậy clean và plume chỉ khác nhau đúng HAI thứ:
  (1) điểm plume được THÊM vào (không lấy mất điểm nào);
  (2) `wet_ground` đổi INTENSITY của điểm mặt đường — và chỉ bật ở nhánh plume
      (982 814 điểm attenuate = 3,48 %, clean/real không có).

Nếu (1) không đụng tới vật thể (đã đo: 0 điểm trong footprint ở 1592/1761 hộp) mà
score vẫn sụt 12,9 %, thì (2) là ứng viên chính. Script này đo:

  a. per-scene: số điểm bị wet_ground đổi intensity, số điểm trong hộp GT bị đổi;
  b. tương quan với retention (biến sạch, đã định nghĩa ở rootcause_retention.py);
  c. kiểm tra wet_ground có đụng điểm CAO (thân xe) hay chỉ mặt đường.

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_wet_ground.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from proxy_eval.matcher import bev_iou  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext, sample_wfh_mm  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

ROOT = REPO / "data/SemanticSprayDataset"
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
SPRAY = 2
SEED = 0
IOU_THRESH = 0.5
SCORE_THRESH = 0.2
RANGE_M = 54.0


def _load() -> dict:
    frames: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            frames.setdefault((row["scene_token"], row["frame_idx"]), {})[
                row["arm"]] = row
    return frames


def _in_box(xyz: np.ndarray, box: np.ndarray) -> np.ndarray:
    cos, sin = np.cos(-box[6]), np.sin(-box[6])
    dx = xyz[:, 0] - box[0]
    dy = xyz[:, 1] - box[1]
    lx = cos * dx - sin * dy
    ly = sin * dx + cos * dy
    dz = xyz[:, 2] - box[2]
    return ((np.abs(lx) <= box[3] / 2) & (np.abs(ly) <= box[4] / 2)
            & (dz >= -0.1) & (dz <= box[5] + 0.1))


def main() -> None:
    frames = _load()
    per_scene: dict[str, dict] = {}

    for (scene, frame_idx), arms in sorted(frames.items()):
        clean_rec, plume_rec = arms.get("clean"), arms.get("plume")
        if clean_rec is None or plume_rec is None:
            continue
        path = ROOT / scene
        scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
        boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
        if not boxes_json.is_file():
            continue
        meta = read_metadata(path / "metadata.txt")
        obj_v = float(meta["object_velocity"]) / 3.6
        ego_v = float(meta.get("ego_velocity") or meta["object_velocity"]) / 3.6
        cls = "crafter" if "Crafter" in scene else "golf"
        points = np.fromfile(path / "velodyne" / f"{scan}.bin",
                             dtype=np.float32).reshape(-1, 5)
        labels = np.fromfile(path / "labels" / f"{scan}.label", dtype=np.uint32)
        boxes, _, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
        if len(boxes) == 0:
            continue
        road_z = float(np.median(boxes[:, 2]))
        clean_pts = points[labels != SPRAY].astype(np.float32)

        # Hai lần inject: bật và tắt wet_ground
        state_on = PlumeState(replace(PlumeStateConfig(), diffusion_alpha=0.0,
                                      min_range_m=2.5, max_range_m=50.0))
        context = PlumeContext(scene_token=scene, frame_index=frame_idx, epoch=0,
                               sensor_origin=np.zeros(3), ego_speed_mps=ego_v,
                               object_speed_mps=obj_v,
                               wfh_mm=sample_wfh_mm(scene, 0, 0), road_z_m=road_z)
        on = inject_plume_stateful(clean_pts, boxes, context, state_on, seed=SEED,
                                   token=f"wg/{frame_idx}", config=PlumeConfig(),
                                   vehicle_class=cls)

        entry = per_scene.setdefault(scene, {
            "n_frame": 0, "n_int_changed": 0, "n_int_in_box": 0,
            "n_road": 0, "n_high_changed": 0, "d_int_sum": [], "n": 0,
        })
        entry["n_frame"] += 1

        # điểm nền (không phải plume) trong `on.points`
        n_clean = clean_pts.shape[0]
        base_out = on.points[:n_clean]
        same_xyz = (np.allclose(base_out[:, :3], clean_pts[:, :3], atol=1e-5)
                    if base_out.shape[0] >= n_clean else False)
        if not same_xyz:
            # các điểm nền bị đổi thứ tự -> ghép lại theo toạ độ
            continue
        int_changed = ~np.isclose(base_out[:, 3], clean_pts[:, 3], atol=1e-3)
        entry["n_int_changed"] += int(int_changed.sum())
        entry["n_road"] += int((np.abs(clean_pts[:, 2] - road_z) < 0.15).sum())

        # thay đổi intensity ở điểm CAO (thân xe, z > road_z + 0,4)
        high = clean_pts[:, 2] > road_z + 0.4
        entry["n_high_changed"] += int((int_changed & high).sum())

        # thay đổi trong hộp GT
        for box in boxes:
            mask = _in_box(clean_pts[:, :3].astype(np.float64), box)
            if mask.sum() == 0:
                continue
            entry["n_int_in_box"] += int((int_changed & mask).sum())

        # điểm hộp nào bị mất score
        cb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"],
                        b["yaw"]] for b in clean_rec["boxes"]], dtype=float)
        cs = np.array([float(b["score"]) for b in clean_rec["boxes"]])
        pb = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"],
                        b["yaw"]] for b in plume_rec["boxes"]], dtype=float)
        ps = np.array([float(b["score"]) for b in plume_rec["boxes"]])
        for gt in cb:
            ious = [bev_iou(b, gt) for b in cb]
            if max(ious) < IOU_THRESH:
                continue
            ci = int(np.argmax(ious))
            if cs[ci] < SCORE_THRESH:
                continue
            pi = int(np.argmax([bev_iou(b, gt) for b in pb])) if len(pb) else -1
            p_score = float(ps[pi]) if pi >= 0 else 0.0
            p_iou = bev_iou(pb[pi], gt) if pi >= 0 else 0.0
            kept = p_iou >= IOU_THRESH and p_score >= SCORE_THRESH
            entry["d_int_sum"].append(p_score - float(cs[ci]))
            entry["n"] += 1
            entry.setdefault("kept", 0)
            entry["kept"] += int(kept)

    print(f"{'scene':<24} {'int_chg':>8} {'in_box':>7} {'high_chg':>9} "
          f"{'int_chg%':>9} {'retention':>10} {'d_score':>8}")
    names, ratios, rets, dsc = [], [], [], []
    for scene in sorted(per_scene):
        e = per_scene[scene]
        if e["n"] == 0:
            continue
        n_base = 30000 * e["n_frame"]
        pct = 100.0 * e["n_int_changed"] / max(n_base, 1)
        ret = e.get("kept", 0) / e["n"]
        ds = float(np.median(e["d_int_sum"]))
        names.append(scene); ratios.append(pct); rets.append(ret); dsc.append(ds)
        print(f"{scene.split('/')[1][:22]:<24} {e['n_int_changed']:8d} "
              f"{e['n_int_in_box']:7d} {e['n_high_changed']:9d} {pct:9.3f} "
              f"{ret:10.3f} {ds:+8.3f}")

    ratios = np.array(ratios); rets = np.array(rets); dsc = np.array(dsc)
    print()
    print("Tương quan:")
    print(f"  corr(intensity đổi %, retention) = "
          f"{float(np.corrcoef(ratios, rets)[0,1]):+.3f}")
    print(f"  corr(intensity đổi %, Δscore)    = "
          f"{float(np.corrcoef(ratios, dsc)[0,1]):+.3f}")
    print()
    tot_chg = sum(per_scene[s]["n_int_changed"] for s in per_scene)
    tot_high = sum(per_scene[s]["n_high_changed"] for s in per_scene)
    tot_box = sum(per_scene[s]["n_int_in_box"] for s in per_scene)
    tot_n = sum(per_scene[s]["n_frame"] for s in per_scene)
    print(f"Tổng: {tot_chg} điểm đổi intensity trên {tot_n} frame")
    print(f"      trong đó {tot_high} điểm ở thân xe (z > road+0,4) "
          f"= {100*tot_high/max(tot_chg,1):.2f} %")
    print(f"      {tot_box} điểm đổi nằm TRONG hộp GT "
          f"= {100*tot_box/max(tot_chg,1):.2f} %")


if __name__ == "__main__":
    main()
