"""Audit bảng cal — CHỈ scene vai `cal`, đúng protocol bảng gốc.

Bảng gốc (docs/measurements/semantic-spray-clusters-by-speed.md):
  - 15 frame/scene × 3 scene/ô, frame lấy cách đều trong scene
  - DBSCAN eps=0.7deg minPts=3 trên (azimuth, elevation)
  - chỉ scene vai `cal` (luật ticket 29d)

Script audit trước dùng sspp_infos_train.pkl (split train/val/test của model) → TRỘN
cal với held-out → số bẩn. Script này dùng read_dataset + assign_roles để lọc đúng.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_split import ROLE_CAL, assign_roles, read_dataset
from spray.semantic_stats import cluster_angular

ROOT = Path("data/SemanticSprayDataset")
FRAMES_PER_SCENE = 15
MIN_SPEED_KMH = 45.0


def load_label(path: Path) -> np.ndarray:
    return np.fromfile(path, dtype=np.uint32)


def frame_indices(n: int, k: int) -> list[int]:
    if n <= k:
        return list(range(n))
    return [int(round(x)) for x in np.linspace(0, n - 1, k)]


def main() -> None:
    metas = read_dataset(ROOT)
    roles = assign_roles(metas)

    cells: dict[tuple[str, float, float], list] = defaultdict(list)
    for meta in metas:
        if roles[meta.rel_path] != ROLE_CAL:
            continue
        if meta.object_velocity_kmh < MIN_SPEED_KMH:
            continue
        cells[(meta.group, meta.object_velocity_kmh, meta.distance_to_object_m)].append(meta)

    print(f"AUDIT_SCOPE role=cal cells={len(cells)} "
          f"frames_per_scene={FRAMES_PER_SCENE} min_speed={MIN_SPEED_KMH}")

    rows_a: list[tuple] = []
    for key in sorted(cells):
        group, kmh, dist = key
        for meta in sorted(cells[key], key=lambda m: m.scene):
            scene_dir = ROOT / meta.rel_path
            scans = sorted((scene_dir / "velodyne").glob("*.bin"))
            if not scans:
                continue
            n_clusters, n_points = [], []
            for idx in frame_indices(len(scans), FRAMES_PER_SCENE):
                scan = scans[idx]
                pts = np.fromfile(scan, dtype=np.float32).reshape(-1, 5)
                lab = load_label(scene_dir / "labels" / f"{scan.stem}.label")
                if lab.size != pts.shape[0]:
                    continue
                spray = pts[lab == 2][:, :3]
                if len(spray) < 3:
                    n_clusters.append(0)
                    n_points.append(0)
                    continue
                lbl = cluster_angular(spray, eps_deg=0.7, min_pts=3)
                ids = np.unique(lbl[lbl >= 0])
                n_clusters.append(int(len(ids)))
                n_points.append(int(len(spray)))
            if not n_clusters:
                continue
            rows_a.append((
                group, kmh, dist, meta.scene[:4], len(n_clusters),
                float(np.percentile(n_clusters, 25)),
                float(np.median(n_clusters)),
                float(np.percentile(n_clusters, 75)),
                float(np.median(n_points)),
            ))

    print("\nAUDIT_TABLE_A")
    print("group    kmh  dist  scene  n_frame  c_p25  c_p50  c_p75  p_p50")
    for r in rows_a:
        print(f"{r[0][:8]:8s} {r[1]:3.0f} {r[2]:4.0f}  {r[3]:5s} {r[4]:7d} "
              f"{r[5]:6.1f} {r[6]:6.1f} {r[7]:6.1f} {r[8]:7.0f}")

    # Bảng B: median-of-medians theo (group, kmh), gộp cả 2 cự ly
    print("\nAUDIT_TABLE_B")
    print("group    kmh  n_scene  med_of_med   min    max  scene_CV  frame_CV")
    agg: dict[tuple[str, float], list[tuple[float, float]]] = defaultdict(list)
    for r in rows_a:
        agg[(r[0], r[1])].append((r[6], r[4]))
    for key in sorted(agg):
        vals = np.array([v[0] for v in agg[key]], dtype=float)
        nfr = np.array([v[1] for v in agg[key]], dtype=float)
        scene_cv = float(vals.std() / vals.mean()) if vals.mean() > 0 else 0.0
        frame_cv = float(nfr.std() / nfr.mean()) if nfr.mean() > 0 else 0.0
        print(f"{key[0][:8]:8s} {key[1]:3.0f} {len(vals):7d} {np.median(vals):11.2f} "
              f"{vals.min():6.1f} {vals.max():6.1f} {scene_cv:9.2f} {frame_cv:9.2f}")

    # Bảng C: theo cự ly
    print("\nAUDIT_TABLE_C")
    print("group    dist  n_scene  n_frame  c_p50  p_p50")
    by_dist: dict[tuple[str, float], list[tuple[float, float, int]]] = defaultdict(list)
    for r in rows_a:
        by_dist[(r[0], r[2])].append((r[6], r[8], r[4]))
    for key in sorted(by_dist):
        vals = np.array([v[0] for v in by_dist[key]], dtype=float)
        pts = np.array([v[1] for v in by_dist[key]], dtype=float)
        nfr = sum(v[2] for v in by_dist[key])
        print(f"{key[0][:8]:8s} {key[1]:4.0f} {len(vals):7d} {nfr:7d} "
              f"{np.median(vals):6.1f} {np.median(pts):7.0f}")

    print(f"\nAUDIT_CAL_OK cells={len(cells)} scenes={len(rows_a)}")


if __name__ == "__main__":
    main()
