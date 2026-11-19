"""Kiểm cấu trúc split: cal / held-out / train / val / test có chồng lấn không."""

from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.semantic_split import ROLE_CAL, assign_roles, read_dataset


def main() -> None:
    metas = read_dataset("data/SemanticSprayDataset")
    roles = assign_roles(metas)
    meta_by_path = {m.rel_path: m for m in metas}

    splits = {}
    for name in ("train", "val", "test"):
        with open(f"data/sspp_infos_{name}.pkl", "rb") as fh:
            infos = pickle.load(fh)
        scenes = sorted({i["token"].rsplit("/", 1)[0] for i in infos})
        splits[name] = scenes
        print(f"{name}: {len(scenes)} scene / {len(infos)} frame")

    print("\n=== Chồng lấn scene giữa các split ===")
    for a in ("train", "val", "test"):
        for b in ("train", "val", "test"):
            if a >= b:
                continue
            inter = set(splits[a]) & set(splits[b])
            print(f"  {a} ∩ {b} = {len(inter)}")

    print("\n=== Vai cal/held-out trong từng split ===")
    print("split  | cal | held-out | tốc độ (km/h)")
    for name, scenes in splits.items():
        n_cal = sum(1 for s in scenes if roles.get(s) == ROLE_CAL)
        n_held = sum(1 for s in scenes if roles.get(s) not in (None, ROLE_CAL))
        speeds = sorted({meta_by_path[s].object_velocity_kmh for s in scenes if s in meta_by_path})
        print(f"{name:6s} | {n_cal:3d} | {n_held:8d} | {speeds}")

    print("\n=== RỦI RO: scene cal có nằm trong test không? ===")
    cal_scenes = {s for s in roles if roles[s] == ROLE_CAL}
    for name in ("train", "val", "test"):
        leak = cal_scenes & set(splits[name])
        print(f"  cal ∩ {name} = {len(leak)} scene")
        for s in sorted(leak):
            print(f"      {s}")

    print("\n=== Cự ly trong từng split ===")
    for name, scenes in splits.items():
        dists = defaultdict(int)
        for s in scenes:
            if s in meta_by_path:
                dists[int(meta_by_path[s].distance_to_object_m)] += 1
        print(f"  {name}: {dict(sorted(dists.items()))}")

    print("\n=== Lớp xe trong từng split ===")
    for name, scenes in splits.items():
        groups = defaultdict(int)
        for s in scenes:
            if s in meta_by_path:
                groups[meta_by_path[s].group] += 1
        print(f"  {name}: {dict(groups)}")

    print("\n=== Số frame theo tốc độ, mỗi split ===")
    for name in ("train", "val", "test"):
        with open(f"data/sspp_infos_{name}.pkl", "rb") as fh:
            infos = pickle.load(fh)
        by_speed = defaultdict(int)
        for info in infos:
            scene = info["token"].rsplit("/", 1)[0]
            if scene in meta_by_path:
                by_speed[int(meta_by_path[scene].object_velocity_kmh)] += 1
        print(f"  {name}: {dict(sorted(by_speed.items()))}")

    print("\nSPLIT_STRUCTURE_OK")


if __name__ == "__main__":
    main()
