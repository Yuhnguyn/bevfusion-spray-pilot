#!/usr/bin/env python3
"""ROOT CAUSE: mẫu số của recall — số GT box mỗi frame — có phải confound chính?

Recall mỗi frame = (số box khớp) / (số GT box). Nếu frame chỉ có **1** GT box thì
một lần trượt làm recall sụt **1,00**; nếu frame có **10** box thì cùng một lần
trượt chỉ làm sụt **0,10**. Vì vậy Δrecall theo scene KHÔNG cùng thang đo nếu số
GT box/frame khác nhau — và đây có thể là toàn bộ "nghịch lý liều".

Script này đo:
  1. số GT box/frame theo scene;
  2. Δrecall chuẩn hoá lại: Δ **tính trên từng box** (tỉ lệ box bị mất),
     độc lập với mẫu số;
  3. nếu nghịch lý biến mất khi dùng thang "tỉ lệ box mất" thì kết luận: tương
     quan dương cũ là **artefact của mẫu số**, không phải cơ chế sinh học nào.
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
SUMMARY = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections_summary.json"
ROOT = REPO / "data/SemanticSprayDataset"
IOU_THRESH = 0.5
SCORE_THRESH = 0.2
RANGE_M = 54.0


def main() -> None:
    summary = json.load(open(SUMMARY))
    rec = summary["summary"]["paired"]["plume_minus_clean"]["recall_per_scene"]

    # gom theo scene
    frames: dict[tuple[str, int], dict] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["scene_token"], row["frame_idx"])
            frames.setdefault(key, {})[row["arm"]] = row

    n_gt_cache: dict[tuple[str, int], int] = {}
    per_scene: dict[str, dict[str, list]] = {}
    box_lost = {"clean": [0, 0], "plume": [0, 0]}   # [mất, tổng]

    for (scene, frame_idx), arms in sorted(frames.items()):
        clean, plume = arms.get("clean"), arms.get("plume")
        if clean is None or plume is None:
            continue
        path = ROOT / scene
        scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[frame_idx]
        boxes_json = path / "object_labels" / "lidar" / f"{scan}.json"
        if not boxes_json.is_file():
            continue
        if (scene, frame_idx) not in n_gt_cache:
            meta = read_metadata(path / "metadata.txt")
            gt, _, _ = _boxes_to_arrays(
                read_frame_boxes(boxes_json), float(meta["object_velocity"]) / 3.6)
            gt = np.asarray(gt, dtype=np.float64).reshape(-1, 9)[:, :7]
            keep = np.linalg.norm(gt[:, :2], axis=1) <= RANGE_M
            n_gt_cache[(scene, frame_idx)] = int(keep.sum())
        n_gt = n_gt_cache[(scene, frame_idx)]
        if n_gt == 0:
            continue

        def matched(record) -> int:
            det = np.array([[b["x"], b["y"], b["z"], b["dx"], b["dy"], b["dz"],
                             b["yaw"]] for b in record["boxes"]], dtype=float)
            scores = np.array([float(b["score"]) for b in record["boxes"]])
            if len(det) == 0:
                return 0
            mask = ((np.linalg.norm(det[:, :2], axis=1) <= RANGE_M)
                    & (scores >= SCORE_THRESH))
            det, scores = det[mask], scores[mask]
            gt = np.asarray(_gt_of(scene, frame_idx, path, scan), dtype=np.float64)
            used = np.zeros(len(det), dtype=bool)
            hits = 0
            for gi in range(len(gt)):
                for di in np.argsort(-scores, kind="stable"):
                    if used[di]:
                        continue
                    if bev_iou(det[di], gt[gi]) >= IOU_THRESH:
                        used[di] = True
                        hits += 1
                        break
            return hits

        entry = per_scene.setdefault(scene, {"n_gt": [], "d": []})
        entry["n_gt"].append(n_gt)
        for arm in ("clean", "plume"):
            hit = matched(arms[arm])
            box_lost[arm][1] += n_gt
            box_lost[arm][0] += n_gt - hit
        entry["d"].append((matched(plume) - matched(clean)) / n_gt)

    print(f"{'scene':<24} {'n_gt/f':>7} {'Δrecall':>8} {'Δ box-lost':>11} {'spray/f':>8}")
    spray_by_scene: dict[str, float] = {}
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["arm"] == "plume":
                spray_by_scene.setdefault(row["scene_token"], []).append(
                    int(row["n_injected"]))
    spray_by_scene = {k: float(np.mean(v)) for k, v in spray_by_scene.items()}

    deltas, deltas_box, ngts, sprays = [], [], [], []
    for scene in sorted(per_scene):
        e = per_scene[scene]
        n_gt = float(np.mean(e["n_gt"]))
        d = float(np.mean(e["d"]))
        # Δ theo thang "tỉ lệ box bị mất": cùng đơn vị với recall nhưng KHÔNG phụ
        # thuộc số box trong frame, vì mỗi frame đã chia cho n_gt của chính nó
        deltas.append(rec["plume"][scene] - rec["clean"][scene])
        deltas_box.append(d)
        ngts.append(n_gt)
        sprays.append(spray_by_scene.get(scene, float("nan")))
        print(f"{scene.split('/')[1][:22]:<24} {n_gt:7.2f} "
              f"{deltas[-1]:+8.3f} {d:+11.3f} {sprays[-1]:8.1f}")

    d = np.array(deltas); db = np.array(deltas_box)
    ng = np.array(ngts); sp = np.array(sprays)

    def corr(x, y):
        mask = np.isfinite(x) & np.isfinite(y)
        return float(np.corrcoef(x[mask], y[mask])[0, 1])

    print()
    print("So sánh hai thang đo Δ:")
    print(f"  Δrecall (harness)      p50 = {np.median(d):+.3f}")
    print(f"  Δ theo từng box        p50 = {np.median(db):+.3f}")
    print(f"  corr(Δrecall, Δbox)    = {corr(d, db):+.3f}")
    print()
    print("Nghịch lý liều dưới hai thang:")
    print(f"  corr(spray/f, Δrecall) = {corr(sp, d):+.3f}")
    print(f"  corr(spray/f, Δbox)    = {corr(sp, db):+.3f}")
    print(f"  corr(n_gt/f, Δrecall)  = {corr(ng, d):+.3f}")
    print(f"  corr(n_gt/f, spray/f)  = {corr(ng, sp):+.3f}")
    print()
    print("Tổng toàn tập:")
    for arm in ("clean", "plume"):
        lost, total = box_lost[arm]
        print(f"  {arm:<6} box mất {lost}/{total} = {100*lost/total:.2f} %")


_GT_CACHE: dict = {}


def _gt_of(scene: str, frame_idx: int, path: Path, scan: str):
    key = (scene, frame_idx)
    if key in _GT_CACHE:
        return _GT_CACHE[key]
    meta = read_metadata(path / "metadata.txt")
    gt, _, _ = _boxes_to_arrays(
        read_frame_boxes(path / "object_labels" / "lidar" / f"{scan}.json"),
        float(meta["object_velocity"]) / 3.6)
    gt = np.asarray(gt, dtype=np.float64).reshape(-1, 9)[:, :7]
    keep = np.linalg.norm(gt[:, :2], axis=1) <= RANGE_M
    _GT_CACHE[key] = gt[keep]
    return _GT_CACHE[key]


if __name__ == "__main__":
    main()
