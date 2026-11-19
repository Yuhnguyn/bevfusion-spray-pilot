#!/usr/bin/env python3
"""Đo TP thật từ GT gốc cho cổng C — kiểm lại recall bằng tay, không tin summary.

Vì sao cần: recall summary nói plume −0,219 trong khi spray chỉ bằng 0,04–1,47 % điểm
nền và 12/12 scene có detection *tăng*. Phải tự tính TP từ GT để biết số summary có
đúng, và nếu đúng thì cơ chế là gì.

Chạy:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
    /opt/anaconda3/bin/python .scratch/paper-faithful/verify_gate_c_tp.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from proxy_eval.matcher import bev_iou  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"
ROOT = REPO / "data/SemanticSprayDataset"
IOU_THRESH = 0.5
RANGE_M = 54.0
SCORE_THRESH = 0.2  # noqa: F841


def _load_rows() -> dict:
    by: dict = {}
    with JSONL.open() as handle:
        for line in handle:
            record = json.loads(line)
            by.setdefault((record["scene_token"], record["frame_idx"]), {})[
                record["arm"]
            ] = record
    return by


def _gt(scene: str, frame_idx: int, cache: dict):
    key = (scene, frame_idx)
    if key in cache:
        return cache[key]
    path = ROOT / scene
    scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
    boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
    if not boxes_json.is_file():
        cache[key] = None
        return None
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    boxes, labels, _ = _boxes_to_arrays(read_frame_boxes(boxes_json), obj_v)
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 9)[:, :7]
    cache[key] = (boxes, labels)
    return cache[key]


def _as_matrix(detections: list[dict]) -> tuple[np.ndarray, list[str]]:
    if not detections:
        return np.zeros((0, 7)), []
    matrix = np.array(
        [[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"], b["yaw"]]
         for b in detections],
        dtype=float,
    )
    return matrix, [str(b["label"]) for b in detections]


def _recall_frame(detections: list[dict], gt) -> float | None:
    """Recall label-agnostic, đúng như ``make_eval_config`` + ``_match`` của harness.

    Ba chi tiết phải giống harness, nếu không số sẽ sai:
    1. label-agnostic — SSPP có 2 lớp (Car/Van) còn checkpoint dự đoán 10 lớp
       nuScenes, nên harness so **mọi** detection với **mọi** GT.
    2. **mỗi detection chỉ dùng một lần** (greedy theo score giảm dần). Bản đầu
       của script này không đánh dấu, nên một detection khớp được nhiều GT và
       thổi phồng recall của nhánh plume (nhánh có nhiều detection hơn) — đo
       được −0,069 so với −0,219 của harness.
    3. lọc cả GT và detection theo ``range_m`` trên mặt phẳng ``‖xy‖``.
    """
    if gt is None:
        return None
    gt_boxes, _ = gt
    if len(gt_boxes) == 0:
        return None

    in_range = np.linalg.norm(gt_boxes[:, :2], axis=1) <= RANGE_M
    gt_boxes = gt_boxes[in_range]
    if len(gt_boxes) == 0:
        return None

    det_boxes, _ = _as_matrix(detections)
    if len(det_boxes) == 0:
        return 0.0
    det_keep = np.linalg.norm(det_boxes[:, :2], axis=1) <= RANGE_M
    scores_all = np.array([float(b["score"]) for b in detections], dtype=float)
    det_keep &= scores_all >= SCORE_THRESH
    det_boxes = det_boxes[det_keep]
    scores = scores_all[det_keep]

    order = np.argsort(-scores, kind="stable")
    used = np.zeros(len(det_boxes), dtype=bool)
    matched_gt = 0
    for gt_index in range(len(gt_boxes)):
        for det_index in order:
            if used[det_index]:
                continue
            if bev_iou(det_boxes[det_index], gt_boxes[gt_index]) >= IOU_THRESH:
                used[det_index] = True
                matched_gt += 1
                break
    return matched_gt / len(gt_boxes)


def main() -> None:
    rows = _load_rows()
    cache: dict = {}
    per_arm: dict[str, dict[str, list[float]]] = {"clean": {}, "plume": {}, "real": {}}
    diag: dict[str, dict[str, list[float]]] = {}

    for (scene, frame_idx), arms in sorted(rows.items()):
        gt = _gt(scene, frame_idx, cache)
        if gt is None:
            continue
        for arm in ("clean", "plume", "real"):
            record = arms.get(arm)
            if record is None:
                continue
            value = _recall_frame(record["boxes"], gt)
            if value is None:
                continue
            per_arm[arm].setdefault(scene, []).append(value)

            if arm in ("clean", "plume"):
                det_boxes, _ = _as_matrix(record["boxes"])
                d = diag.setdefault(scene, {"n_clean": [], "n_plume": []})
                d[f"n_{arm}"].append(len(det_boxes))

    print(f"{'scene':<34} {'rec_c':>7} {'rec_p':>7} {'delta':>7} "
          f"{'det_c':>6} {'det_p':>6} {'n':>4}")
    deltas = []
    for scene in sorted(per_arm["clean"]):
        c = np.array(per_arm["clean"][scene])
        p = np.array(per_arm["plume"].get(scene, []))
        if len(p) == 0 or len(c) != len(p):
            continue
        delta = float(p.mean() - c.mean())
        deltas.append(delta)
        dc = float(np.mean(diag[scene]["n_clean"]))
        dp = float(np.mean(diag[scene]["n_plume"]))
        print(f"{scene.split('/')[1][:32]:<34} {c.mean():7.3f} {p.mean():7.3f} "
              f"{delta:+7.3f} {dc:6.1f} {dp:6.1f} {len(c):4d}")

    print()
    print(f"recall trung binh nhánh clean = "
          f"{np.mean([np.mean(v) for v in per_arm['clean'].values()]):.4f}")
    print(f"recall trung binh nhánh plume = "
          f"{np.mean([np.mean(v) for v in per_arm['plume'].values()]):.4f}")
    if per_arm["real"]:
        print(f"recall trung binh nhánh real  = "
              f"{np.mean([np.mean(v) for v in per_arm['real'].values()]):.4f}")
    print(f"Δ(plume−clean) trung binh theo scene = {np.mean(deltas):+.4f} "
          f"(min {np.min(deltas):+.4f}, max {np.max(deltas):+.4f})")
    print(f"so scene Δ<0: {sum(1 for d in deltas if d < 0)}/{len(deltas)}")


if __name__ == "__main__":
    main()
