"""Đo hậu quả của các phương án tái cấu trúc split."""

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
    meta = {m.rel_path: m for m in metas}

    infos = {}
    for name in ("train", "val", "test"):
        with open(f"data/sspp_infos_{name}.pkl", "rb") as fh:
            infos[name] = pickle.load(fh)

    # scene -> n_frame
    nframe = defaultdict(int)
    for name, lst in infos.items():
        for info in lst:
            nframe[info["token"].rsplit("/", 1)[0]] += 1

    print("=== 1. Leak hiện tại: scene nào vừa calibrate vừa evaluate ===")
    for name in ("train", "val", "test"):
        scenes = {i["token"].rsplit("/", 1)[0] for i in infos[name]}
        leak = {s for s in scenes if roles.get(s) == ROLE_CAL}
        print(f"  {name:5s}: {len(leak)}/{len(scenes)} scene là cal "
              f"({sum(nframe[s] for s in leak)}/{sum(nframe[s] for s in scenes)} frame)")

    print("\n=== 2. Cal table hiện tại dùng bao nhiêu scene cal, bao nhiêu trong đó là test ===")
    test_scenes = {i["token"].rsplit("/", 1)[0] for i in infos["test"]}
    by_speed = defaultdict(lambda: {"cal": [], "cal_in_test": []})
    for m in metas:
        if roles[m.rel_path] != ROLE_CAL:
            continue
        if m.object_velocity_kmh < 45:
            continue
        v = int(m.object_velocity_kmh)
        by_speed[v]["cal"].append(m.rel_path)
        if m.rel_path in test_scenes:
            by_speed[v]["cal_in_test"].append(m.rel_path)
    print(" v  | cal scene | trong đó là test scene | % nhiễm")
    for v in sorted(by_speed):
        c = by_speed[v]["cal"]
        t = by_speed[v]["cal_in_test"]
        pct = 100.0 * len(t) / len(c) if c else 0.0
        print(f" {v:3d} | {len(c):9d} | {len(t):22d} | {pct:6.1f}%")

    print("\n=== 3. Phương án A: test = held-out only ===")
    for name in ("train", "val", "test"):
        scenes = {i["token"].rsplit("/", 1)[0] for i in infos[name]}
        held = {s for s in scenes if roles.get(s) not in (None, ROLE_CAL)}
        print(f"  {name:5s}: {len(held)} scene / {sum(nframe[s] for s in held)} frame "
              f"(hiện tại {len(scenes)} scene / {sum(nframe[s] for s in scenes)} frame)")

    print("\n=== 4. Phương án B: calibrate chỉ trên cal ∩ (train ∪ val) ===")
    tv = {i["token"].rsplit("/", 1)[0] for i in infos["train"]} | \
         {i["token"].rsplit("/", 1)[0] for i in infos["val"]}
    cal_tv = [m for m in metas
              if roles[m.rel_path] == ROLE_CAL and m.rel_path in tv
              and m.object_velocity_kmh >= 45]
    speeds = sorted({int(m.object_velocity_kmh) for m in cal_tv})
    print(f"  cal ∩ (train∪val) = {len(cal_tv)} scene, tốc độ có: {speeds}")
    print(f"  tốc độ TEST cần (50/90/130) có trong tập calibrate? "
          f"{[v for v in (50, 90, 130) if v in speeds] or 'KHÔNG — phải ngoại suy'}")

    print("\n=== 5. Kích thước dataset local (so với RoadSpray 5,71+5,60 GB) ===")
    root = Path("data/SemanticSprayDataset")
    total = 0
    for group in ("Crafter_dynamic", "Golf_dynamic"):
        g = root / group
        if not g.is_dir():
            continue
        size = sum(f.stat().st_size for f in g.rglob("*") if f.is_file())
        n = len([p for p in g.iterdir() if p.is_dir()])
        total += size
        print(f"  {group}: {n} scene, {size / 1e9:.2f} GB")
    print(f"  TỔNG: {total / 1e9:.2f} GB")

    print("\nSPLIT_OPTIONS_OK")


if __name__ == "__main__":
    main()
