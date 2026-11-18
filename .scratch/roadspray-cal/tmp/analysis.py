"""Power analysis + leave-speed-out CV design from tmp/frame_stats.json.

Run:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
      .scratch/roadspray-cal/tmp/analysis.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from spray.semantic_split import assign_roles, read_dataset  # noqa: E402

TMP = Path(__file__).parent
RNG = np.random.default_rng(20261118)
B = 20000
Z95 = 1.959964
Z80 = 0.8416212


def rel_stats(values: np.ndarray) -> dict:
    v = np.asarray(values, dtype=float)
    mean = v.mean()
    sd = v.std(ddof=1)
    return {
        "n": int(v.size),
        "mean": mean,
        "sd": sd,
        "cv": sd / mean,
        "min": v.min(),
        "max": v.max(),
    }


def boot_hw_rel(values: np.ndarray, n: int, n_boot: int = B) -> tuple[float, float]:
    """Percentile-bootstrap 95% half-width / mean for the mean of n scenes."""
    v = np.asarray(values, dtype=float)
    idx = RNG.integers(0, v.size, size=(n_boot, n))
    means = v[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return (hi - lo) / 2 / v.mean(), (hi - lo) / 2


def mde(cv: float, n: int, z: float) -> float:
    return z * cv / np.sqrt(n)


def n_for(cv: float, effect: float, z: float) -> float:
    return (z * cv / effect) ** 2


def main() -> None:
    data = json.loads((TMP / "frame_stats.json").read_text())
    roles_all = assign_roles(read_dataset(REPO / "data/SemanticSprayDataset"))
    split = json.loads((REPO / "data/sspp_split.json").read_text())["split"]
    split_of = {s: k for k, ss in split.items() for s in ss}
    for rec in data:
        rec["role"] = roles_all[rec["rel_path"]]
        rec["split"] = split_of[rec["rel_path"]]
        for f in rec["frames"]:
            f["noise_per_frame"] = f["n_noise"]
        rec["clusters"] = np.array([f["n_clusters"] for f in rec["frames"]])
        rec["noise"] = np.array([f["n_noise"] for f in rec["frames"]])
        rec["mean_clusters"] = float(rec["clusters"].mean())
        rec["mean_noise"] = float(rec["noise"].mean())
        rec["cv_within_clusters"] = float(rec["clusters"].std(ddof=1) / rec["clusters"].mean()) if rec["clusters"].mean() else np.nan
        rec["cv_within_noise"] = float(rec["noise"].std(ddof=1) / rec["noise"].mean())

    by = lambda key: [r[key] for r in data]
    print("=" * 72)
    print("0. SAMPLE + SPLIT SANITY")
    print("=" * 72)
    print("scenes", len(data), "sampled frames", sum(len(r["frames"]) for r in data),
          "of", sum(r["frames_on_disk"] for r in data), "on disk")
    for k in ("train", "val", "test"):
        rs = [r for r in data if r["split"] == k]
        print(f"{k:5s}: {len(rs):2d} scenes {sum(r['frames_on_disk'] for r in rs):5d} frames "
              f"speeds={sorted({r['speed_kmh'] for r in rs})}")
    print("roles on the 36 boxed scenes:", {r: sum(1 for x in data if x["role"] == r) for r in ("cal", "held-out")})
    for k in ("train", "val", "test"):
        rs = [r for r in data if r["split"] == k]
        nf = sum(r["frames_on_disk"] for r in rs)
        cal_f = sum(r["frames_on_disk"] for r in rs if r["role"] == "cal")
        print(f"  {k}: cal scenes {sum(1 for r in rs if r['role']=='cal')}/{len(rs)}, "
              f"cal frames {cal_f}/{nf} = {cal_f/nf:.1%}")

    print()
    print("=" * 72)
    print("1. PER-SCENE SPRAY (10 evenly spaced frames/scene; paper DBSCAN eps=0.7deg minPts=3)")
    print("=" * 72)
    print("cell = group/speed/kmh/distance; sorted by mean clusters/frame")
    print(f"{'scene':62s} {'spd':>3s} {'d':>4s} {'split':>5s} {'role':>8s} "
          f"{'clu/fr':>7s} {'noise/fr':>8s} {'cv_w(clu)':>9s}")
    for r in sorted(data, key=lambda x: x["mean_clusters"]):
        print(f"{r['rel_path']:62s} {r['speed_kmh']:3.0f} {r['distance_m']:4.0f} "
              f"{r['split']:>5s} {r['role']:>8s} {r['mean_clusters']:7.2f} "
              f"{r['mean_noise']:8.1f} {r['cv_within_clusters']:9.2f}")
    strata = {
        "all 36": by("mean_clusters"),
        "train 16": [r["mean_clusters"] for r in data if r["split"] == "train"],
        "val 8": [r["mean_clusters"] for r in data if r["split"] == "val"],
        "test 12 (current)": [r["mean_clusters"] for r in data if r["split"] == "test"],
        "test 6 held-out only": [r["mean_clusters"] for r in data if r["split"] == "test" and r["role"] == "held-out"],
        "test 6 cal": [r["mean_clusters"] for r in data if r["split"] == "test" and r["role"] == "cal"],
    }
    print()
    print("CLUSTERS/FRAME across scenes")
    for name, vals in strata.items():
        s = rel_stats(vals)
        print(f"  {name:22s} n={s['n']:2d} mean={s['mean']:6.2f} sd={s['sd']:6.2f} "
              f"min={s['min']:5.2f} max={s['max']:6.2f} CV={s['cv']:.3f}")
    strata_n = {
        "all 36": by("mean_noise"),
        "train 16": [r["mean_noise"] for r in data if r["split"] == "train"],
        "val 8": [r["mean_noise"] for r in data if r["split"] == "val"],
        "test 12 (current)": [r["mean_noise"] for r in data if r["split"] == "test"],
        "test 6 held-out only": [r["mean_noise"] for r in data if r["split"] == "test" and r["role"] == "held-out"],
    }
    print()
    print("NOISE POINTS/FRAME across scenes")
    for name, vals in strata_n.items():
        s = rel_stats(vals)
        print(f"  {name:22s} n={s['n']:2d} mean={s['mean']:6.1f} sd={s['sd']:6.1f} "
              f"min={s['min']:5.0f} max={s['max']:6.0f} CV={s['cv']:.3f}")

    print()
    print("VALIDATION of the 10-frame sample vs PROJECT.md p50/frame by speed")
    for spd in sorted({r["speed_kmh"] for r in data}):
        frames = [f["n_noise"] for r in data if r["speed_kmh"] == spd for f in r["frames"]]
        print(f"  {spd:3.0f} km/h sampled p50={np.median(frames):5.0f} "
              f"mean={np.mean(frames):6.0f} n_frames={len(frames)}")

    print()
    print("=" * 72)
    print("2. VARIANCE DECOMPOSITION (design effect of frames within scenes)")
    print("=" * 72)
    for key in ("clusters", "noise"):
        groups = [r[key] for r in data]
        m = np.array([g.size for g in groups])
        assert m.min() == m.max() == 10
        gm = np.array([g.mean() for g in groups])
        grand = gm.mean()
        msb = (m * (gm - grand) ** 2).sum() / (len(groups) - 1)
        msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (m.sum() - len(groups))
        icc = (msb - msw) / (msb + (m[0] - 1) * msw)
        deff = 1 + (m[0] - 1) * icc
        print(f"  {key:8s}: between-scene var={msb:10.2f} within-scene var={msw:10.2f} "
              f"ICC={icc:.3f} design_effect={deff:.1f} -> 360 sampled frames "
              f"== {360/deff:.0f} independent units")

    print()
    print("=" * 72)
    print("3. SCENE-LEVEL BOOTSTRAP: CI95 HALF-WIDTH / MEAN")
    print("=" * 72)
    test12_clu = [r["mean_clusters"] for r in data if r["split"] == "test"]
    test12_noise = [r["mean_noise"] for r in data if r["split"] == "test"]
    all_clu = by("mean_clusters")
    all_noise = by("mean_noise")
    # (a) current test, n=12 (b) all 36 (c) 6-subsets
    boot = {}
    for label, vals in (("clusters test12", test12_clu), ("noise test12", test12_noise),
                        ("clusters all36", all_clu), ("noise all36", all_noise)):
        hw_rel, hw_abs = boot_hw_rel(np.asarray(vals), len(vals))
        cv = rel_stats(vals)["cv"]
        mde95 = mde(cv, len(vals), Z95)
        mde80 = mde(cv, len(vals), Z80 + Z95)
        n30_95 = n_for(cv, 0.30, Z95)
        n30_80 = n_for(cv, 0.30, Z80 + Z95)
        boot[label] = dict(hw_rel=hw_rel, cv=cv, mde95=mde95, mde80=mde80, n30_95=n30_95, n30_80=n30_80)
        print(f"  {label:18s} n={len(vals):2d} CV={cv:.3f} "
              f"boot_hw/mean={hw_rel:.3f} | analytic 1.96CV/sqrt(n)={mde95:.3f} | "
              f"detectable@80%power={mde80:.3f} | n for 30%@95CI={n30_95:.1f} n(80%)={n30_80:.1f}")
    # random 6-scene subsets and random 12-of-36
    for name, nsub, n_draw in (("random 6-of-36", 6, 4000), ("random 12-of-36", 12, 4000)):
        cvs, hws = [], []
        for _ in range(n_draw):
            vals = np.asarray(all_clu)[RNG.choice(36, nsub, replace=False)]
            s = rel_stats(vals)
            cvs.append(s["cv"])
            hws.append(mde(s["cv"], nsub, Z95))
        print(f"  {name:18s} draws={n_draw} CV median={np.median(cvs):.3f} "
              f"[p5,p95]=[{np.percentile(cvs,5):.3f},{np.percentile(cvs,95):.3f}] "
              f"| hw_rel median={np.median(hws):.3f} [p5,p95]=[{np.percentile(hws,5):.3f},{np.percentile(hws,95):.3f}]")
    # 6-scene subsets that are currently meaningful: held-out-only test
    ho6_clu = [r["mean_clusters"] for r in data if r["split"] == "test" and r["role"] == "held-out"]
    ho6_noise = [r["mean_noise"] for r in data if r["split"] == "test" and r["role"] == "held-out"]
    for label, vals in (("clusters test6HO", ho6_clu), ("noise test6HO", ho6_noise)):
        hw_rel, _ = boot_hw_rel(np.asarray(vals), len(vals))
        cv = rel_stats(vals)["cv"]
        print(f"  {label:18s} n=6 CV={cv:.3f} boot_hw/mean={hw_rel:.3f} "
              f"detectable@80%={mde(cv,6,Z95+Z80):.3f} n30@80%={n_for(cv,0.3,Z95+Z80):.1f}")
    # paired vs unpaired factor
    print("  paired B-vs-A on identical scenes, proportional effect: hw_rel(effect)=1.96*CV/sqrt(n) "
          "if per-scene effect is exactly 30%; unpaired worst case multiplies by sqrt(2)=1.414")
    for label in ("clusters test12", "clusters all36"):
        print(f"    {label}: paired={boot[label]['mde95']:.3f} unpaired={boot[label]['mde95']*np.sqrt(2):.3f}")

    print()
    print("=" * 72)
    print("4. CURRENT TEST SET COMPOSITION BIAS")
    print("=" * 72)
    for name, rs in (("test 12", [r for r in data if r["split"] == "test"]),
                     ("train 16", [r for r in data if r["split"] == "train"]),
                     ("all 36", data)):
        nf = sum(r["frames_on_disk"] for r in rs)
        pooled_clu = sum(r["mean_clusters"] * r["frames_on_disk"] for r in rs) / nf
        pooled_noise = sum(r["mean_noise"] * r["frames_on_disk"] for r in rs) / nf
        print(f"  {name:9s}: frame-weighted clusters/frame={pooled_clu:5.2f} "
              f"noise/frame={pooled_noise:6.1f} | scene-mean clusters/frame="
              f"{np.mean([r['mean_clusters'] for r in rs]):5.2f} "
              f"noise/frame={np.mean([r['mean_noise'] for r in rs]):6.1f}")
    print(f"  test/all frame-weighted noise ratio = "
          f"{sum(r['mean_noise']*r['frames_on_disk'] for r in data if r['split']=='test') / sum(r['frames_on_disk'] for r in data if r['split']=='test') / (sum(r['mean_noise']*r['frames_on_disk'] for r in data) / sum(r['frames_on_disk'] for r in data)):.3f}")

    print()
    print("=" * 72)
    print("5. LEAVE-SPEED-OUT FOLDS (3 folds x 3 held-out speeds), all 36 scenes")
    print("=" * 72)
    speeds = sorted({r["speed_kmh"] for r in data})
    assert speeds == [50, 60, 70, 80, 90, 100, 110, 120, 130], speeds
    fold_speeds = [
        [50, 80, 110],
        [60, 90, 120],
        [70, 100, 130],
    ]
    folds = []
    for k, held in enumerate(fold_speeds, 1):
        test = [r for r in data if r["speed_kmh"] in held]
        train = [r for r in data if r["speed_kmh"] not in held]
        folds.append({"fold": k, "held_out_speeds": held, "test": test, "train": train})
        print(f"  fold {k}: held-out speeds {held}")
        print(f"    test  {len(test):2d} scenes {sum(r['frames_on_disk'] for r in test):5d} frames "
              f"| train {len(train):2d} scenes {sum(r['frames_on_disk'] for r in train):5d} frames "
              f"| test cal {sum(1 for r in test if r['role']=='cal')}/{len(test)}")
        print(f"    test frame-weighted noise/frame="
              f"{sum(r['mean_noise']*r['frames_on_disk'] for r in test)/sum(r['frames_on_disk'] for r in test):6.1f} "
              f"clusters/frame={sum(r['mean_clusters']*r['frames_on_disk'] for r in test)/sum(r['frames_on_disk'] for r in test):5.2f} "
              f"| train scene-mean CV="
              f"{rel_stats([r['mean_noise'] for r in train])['cv']:.3f}")
        # cell balance
        cells = sorted({(r["speed_kmh"], r["distance_m"]) for r in test})
        print(f"    cells in test: {len(cells)} (={len(held)} speeds x 2 distances x 2 groups)")
    print()
    print("  VERIFICATION")
    ok = True
    all_test = []
    for f in folds:
        ts = {r["rel_path"] for r in f["test"]}
        trs = {r["rel_path"] for r in f["train"]}
        overlap = ts & trs
        all_test += list(ts)
        print(f"   fold {f['fold']}: |test|={len(ts)} |train|={len(trs)} "
              f"overlap={sorted(overlap) or 'NONE'} speeds_disjoint="
              f"{not ({r['speed_kmh'] for r in f['test']} & {r['speed_kmh'] for r in f['train']})}")
        ok &= not overlap
    from collections import Counter
    counts = Counter(all_test)
    print(f"   all_test_total={len(all_test)} unique={len(counts)} "
          f"tested_exactly_once={all(c==1 for c in counts.values())} "
          f"covers_all_36={set(counts)=={r['rel_path'] for r in data}}")
    ok &= len(all_test) == 36 and all(c == 1 for c in counts.values()) and len(counts) == 36
    print(f"   FOLD_VERIFICATION={'PASS' if ok else 'FAIL'}")
    # spray balance across fold test sets and cal leakage if SSPP calibration kept
    print()
    print("  cal leakage if generator stays calibrated on SSPP cal scenes:")
    cal_total = sum(1 for r in data if r["role"] == "cal")
    cal_frames = sum(r["frames_on_disk"] for r in data if r["role"] == "cal")
    print(f"   cal on the 36 boxed scenes: {cal_total} scenes / {cal_frames} frames "
          f"({cal_frames/sum(r['frames_on_disk'] for r in data):.1%}); "
          f"held-out {36-cal_total} scenes")
    for f in folds:
        cal_test = sum(1 for r in f["test"] if r["role"] == "cal")
        cal_frames_test = sum(r["frames_on_disk"] for r in f["test"] if r["role"] == "cal")
        print(f"   fold {f['fold']}: cal in test {cal_test}/12 scenes = "
              f"{cal_frames_test}/{sum(r['frames_on_disk'] for r in f['test'])} frames -> "
              f"{'LEAKY' if cal_test else 'clean'}")
    # store
    out = {
        "per_scene": [
            {k: r[k] for k in ("rel_path", "group", "speed_kmh", "distance_m", "split", "role",
                               "frames_on_disk", "mean_clusters", "mean_noise", "role")}
            for r in data
        ],
        "strata": {k: rel_stats(v) for k, v in strata.items()},
        "strata_noise": {k: rel_stats(v) for k, v in strata_n.items()},
        "bootstrap": boot,
        "folds": [
            {"fold": f["fold"], "held_out_speeds": f["held_out_speeds"],
             "test_scenes": [r["rel_path"] for r in f["test"]],
             "train_scenes": [r["rel_path"] for r in f["train"]],
             "test_frames": sum(r["frames_on_disk"] for r in f["test"]),
             "train_frames": sum(r["frames_on_disk"] for r in f["train"])}
            for f in folds
        ],
    }
    (TMP / "analysis.json").write_text(json.dumps(out, indent=1, default=float))
    print("\nwrote tmp/analysis.json")


if __name__ == "__main__":
    main()
