"""Sample 10 evenly spaced frames from each of the 36 boxed SSPP scenes and
measure spray statistics with the repo's own paper recipe.

Writes tmp/frame_stats.json. Run:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
      .scratch/roadspray-cal/tmp/measure.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from spray.semantic_stats import cluster_angular  # noqa: E402

ROOT = REPO / "data" / "SemanticSprayDataset"
FRAMES_PER_SCENE = 10


def scene_dirs() -> list[Path]:
    return sorted(
        p.parent
        for p in ROOT.glob("*/*/object_labels")
        if p.is_dir()
    )


def metadata(scene: Path) -> dict:
    lines = (scene / "metadata.txt").read_text().strip().splitlines()
    head = lines[0].split(",")
    vals = lines[1].split(",")
    row = dict(zip(head, vals))
    return {
        "group": scene.parent.name,
        "scene": scene.name,
        "rel_path": f"{scene.parent.name}/{scene.name}",
        "frames_on_disk": len(list((scene / "velodyne").glob("*.bin"))),
        "speed_kmh": float(row["object_velocity"]),
        "distance_m": float(row["distance_to_object"]),
        "itr_after_water": int(row["itr_after_water"]),
    }


def measure_frame(scene: Path, index: int) -> dict:
    pts = np.fromfile(
        scene / "velodyne" / f"{index:06d}.bin", dtype=np.float32
    ).reshape(-1, 5)
    labels = np.fromfile(scene / "labels" / f"{index:06d}.label", dtype=np.uint32)
    if labels.shape[0] != pts.shape[0]:
        raise ValueError(f"{scene.name}/{index}: labels != points")
    noise = pts[labels == 2]
    if noise.shape[0] == 0:
        clusters = 0
    else:
        cl = cluster_angular(noise)
        clusters = int(np.unique(cl[cl >= 0]).size)
    return {
        "index": index,
        "n_points": int(pts.shape[0]),
        "n_noise": int(noise.shape[0]),
        "n_clusters": clusters,
    }


def main() -> None:
    scenes = scene_dirs()
    assert len(scenes) == 36, len(scenes)
    out = []
    t0 = time.time()
    for n, scene in enumerate(scenes, 1):
        meta = metadata(scene)
        nf = meta["frames_on_disk"]
        picks = sorted(
            {int(round(v)) for v in np.linspace(0, nf - 1, FRAMES_PER_SCENE)}
        )
        frames = [measure_frame(scene, i) for i in picks]
        out.append({**meta, "sampled_frames": picks, "frames": frames})
        done = sum(f["n_noise"] for rec in out for f in rec["frames"])
        print(
            f"[{n:2d}/36] {meta['rel_path']} nf={nf} frames={len(picks)} "
            f"noise_total={done} elapsed={time.time()-t0:.0f}s",
            flush=True,
        )
    path = Path(__file__).with_name("frame_stats.json")
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path}  total_elapsed={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
