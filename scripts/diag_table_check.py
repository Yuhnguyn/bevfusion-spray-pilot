"""Chẩn đoán 8: bảng _CLUSTER_VISIBLE_BY_SPEED có khớp số đo trực tiếp không?

Đo trên TOÀN BỘ scene train có box: cụm/frame và điểm/frame theo mốc 10 km/h,
dùng đúng DBSCAN 0.7°/minPts 3 như bảng gốc.
"""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.plume import _CLUSTER_VISIBLE_BY_SPEED
from spray.semantic_stats import cluster_angular

ROOT = Path("data/SemanticSprayDataset")


def main():
    with open("data/sspp_infos_train.pkl", "rb") as fh:
        infos = pickle.load(fh)

    # gom theo (lớp, mốc 10 km/h)
    buckets = defaultdict(lambda: {"clusters": [], "points": [], "pts_per_cluster": []})

    seen = set()
    for info in infos:
        rel = info["token"].rsplit("/", 1)[0]
        cls = rel.split("/")[0].replace("_dynamic", "").lower()
        boxes = np.asarray(info["gt_boxes"], dtype=np.float32)
        if len(boxes) == 0:
            continue
        v = float(np.hypot(boxes[0, 7], boxes[0, 8])) * 3.6
        if v < 45:
            continue
        speed_bin = int(round(v / 10.0) * 10)

        pts = np.fromfile(ROOT / info["lidar_path"], dtype=np.float32).reshape(-1, 5)
        lab = np.fromfile(
            ROOT / rel / "labels" / f"{info['scan_id']}.label", dtype=np.uint32
        )
        real = pts[lab == 2][:, :3]
        if len(real) < 3:
            continue
        lbl = cluster_angular(real, eps_deg=0.7, min_pts=3)
        ids, counts = np.unique(lbl[lbl >= 0], return_counts=True)
        n_clusters = len(counts)
        key = (cls, speed_bin)
        buckets[key]["clusters"].append(n_clusters)
        buckets[key]["points"].append(len(real))
        if n_clusters:
            buckets[key]["pts_per_cluster"].append(counts.mean())

    print("=== ĐO TRỰC TIẾP (toàn bộ train, DBSCAN 0.7°/minPts 3) vs BẢNG ===")
    print("cls     v  | n_frame | cụm/frame p50 | bảng | ratio | điểm/frame p50 | điểm/cụm p50")
    for cls in ("crafter", "golf"):
        table = dict(_CLUSTER_VISIBLE_BY_SPEED.get(cls, ()))
        for v in range(50, 131, 10):
            key = (cls, v)
            if key not in buckets:
                continue
            b = buckets[key]
            nf = len(b["clusters"])
            c50 = float(np.median(b["clusters"]))
            p50 = float(np.median(b["points"]))
            ppc = float(np.median(b["pts_per_cluster"])) if b["pts_per_cluster"] else 0.0
            tbl = table.get(float(v), float("nan"))
            ratio = c50 / tbl if tbl else float("nan")
            print(
                f"{cls:7s} {v:3d} | {nf:7d} | {c50:13.1f} | {tbl:4.1f} | {ratio:5.2f} | "
                f"{p50:14.0f} | {ppc:13.1f}"
            )


if __name__ == "__main__":
    main()
