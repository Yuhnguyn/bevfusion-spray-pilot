"""Extra numbers for power-design.md: m-corrected CI widths, decision-rule power,
fold balances, held-out-only fallback, budget arithmetic.

Run:
  CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
      .scratch/roadspray-cal/tmp/extras.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from spray.semantic_split import assign_roles, read_dataset  # noqa: E402

TMP = Path(__file__).parent
RNG = np.random.default_rng(7)
Z95, Z80 = 1.959964, 0.8416212

data = json.loads((TMP / "frame_stats.json").read_text())
roles = assign_roles(read_dataset(REPO / "data/SemanticSprayDataset"))
split = json.loads((REPO / "data/sspp_split.json").read_text())["split"]
split_of = {s: k for k, ss in split.items() for s in ss}
for r in data:
    r["role"] = roles[r["rel_path"]]
    r["split"] = split_of[r["rel_path"]]
    r["clu"] = np.array([f["n_clusters"] for f in r["frames"]], float)
    r["noi"] = np.array([f["n_noise"] for f in r["frames"]], float)
    r["mean_clu"] = r["clu"].mean()
    r["mean_noi"] = r["noi"].mean()
mean = lambda rs, k: float(np.mean([r[k] for r in rs]))


def within_between(groups: list[np.ndarray]) -> tuple[float, float]:
    m = np.array([g.size for g in groups])
    gm = np.array([g.mean() for g in groups])
    grand = gm.mean()
    msb = (m * (gm - grand) ** 2).sum() / (len(groups) - 1)  # m * var(means)
    msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (m.sum() - len(groups))
    var_means = msb / m[0]
    var_between = var_means - msw / m[0]
    return var_between, msw


def boot_cv(vals: np.ndarray, n_boot: int = 20000) -> tuple[float, float, float]:
    idx = RNG.integers(0, vals.size, size=(n_boot, vals.size))
    means = vals[idx].mean(axis=1)
    sds = vals[idx].std(axis=1, ddof=1)
    cvs = sds / means
    return np.median(cvs), *np.percentile(cvs, [2.5, 97.5])


print("=" * 78)
print("A. m-corrected CI widths (10-frame per-scene noise removed, m=80 at eval)")
print("=" * 78)
for key, label in (("clu", "clusters/frame"), ("noi", "noise points/frame")):
    groups = [r[key] for r in data]
    var_b, var_w = within_between(groups)
    mu = float(np.mean([r[f"mean_{key}"] for r in data]))
    cv_b = np.sqrt(var_b) / mu
    cv_w = np.sqrt(var_w) / mu
    print(f"{label}: grand mean={mu:.2f} CV_between={cv_b:.3f} CV_within={cv_w:.3f} "
          f"(observed CV of 10-frame scene means={np.std([r[f'mean_{key}'] for r in data], ddof=1)/mu:.3f})")
    for n, m in ((6, 80.0), (12, 80.0), (36, 72.0)):
        se_rel = np.sqrt(var_b / n + var_w / (n * m)) / mu
        print(f"   n={n:2d} m={m:4.0f}: analytic SE_rel={se_rel:.3f} hw95={Z95*se_rel:.3f} "
              f"CI of a 30% effect=[{0.30-Z95*se_rel:.3f}, {0.30+Z95*se_rel:.3f}]")
    print(f"   n needed for hw95=30%: {(Z95*cv_b/0.30)**2:.1f}; for 80% power (CI leg): "
          f"{(2.8*cv_b/0.30)**2:.1f}")

print()
print("=" * 78)
print("B. uncertainty of the CV itself (bootstrap over scenes)")
print("=" * 78)
for key, label in (("clu", "clusters"), ("noi", "noise")):
    for name, rs in (("test12", [r for r in data if r["split"] == "test"]),
                     ("all36", data)):
        vals = np.array([r[f"mean_{key}"] for r in rs])
        med, lo, hi = boot_cv(vals)
        cv = vals.std(ddof=1) / vals.mean()
        print(f"  {label:9s} {name:6s} n={len(vals):2d} CV={cv:.3f} bootstrap CI of CV=[{lo:.3f},{hi:.3f}]")

print()
print("=" * 78)
print("C. P(pass) of the frozen decision rule, normal model on scene-level SE")
print("   pass = (point estimate >= 30% relative reduction) AND (95% CI excludes 0)")
print("=" * 78)
from math import erf, sqrt
ncdf = lambda z: 0.5 * (1 + erf(z / sqrt(2)))
for key, label in (("clu", "clusters/frame"), ("noi", "noise/frame")):
    var_b, var_w = within_between([r[key] for r in data])
    mu = float(np.mean([r[f"mean_{key}"] for r in data]))
    cv_b = np.sqrt(var_b) / mu
    print(f"{label}: SE_rel = CV_b/sqrt(n), CV_b={cv_b:.3f}")
    print("   true effect |" + "".join(f"{f'n={n}':>10s}" for n in (6, 12, 36)))
    for delta in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
        cells = []
        for n in (6, 12, 36):
            se = cv_b / np.sqrt(n)
            p_ge30 = 1 - ncdf((0.30 - delta) / se)
            p_ci = 1 - ncdf((Z95 * se - delta) / se)
            cells.append(f"{min(p_ge30, p_ci):10.2f}")
        print(f"   {delta:.0%}        |" + "".join(cells))

print()
print("=" * 78)
print("D. FOLDS: fold = rank(speed) mod 3")
print("=" * 78)
speeds = sorted({r["speed_kmh"] for r in data})
rank = {s: i for i, s in enumerate(speeds)}
for r in data:
    r["fold"] = rank[r["speed_kmh"]] % 3 + 1
folds = {}
for k in (1, 2, 3):
    test = sorted([r for r in data if r["fold"] == k], key=lambda x: (x["speed_kmh"], x["group"], x["distance_m"]))
    train = sorted([r for r in data if r["fold"] != k], key=lambda x: x["rel_path"])
    folds[k] = (test, train)
    print(f"fold {k}: held-out speeds={sorted({r['speed_kmh'] for r in test})} "
          f"test={len(test)} scenes/{sum(r['frames_on_disk'] for r in test)} frames "
          f"train={len(train)} scenes/{sum(r['frames_on_disk'] for r in train)} frames")
    print(f"   test scenes per speed: " + ", ".join(
        f"{s:.0f}km/h:{sum(1 for r in test if r['speed_kmh']==s)}" for s in speeds if s in {x['speed_kmh'] for x in test}))
    print(f"   test mean clusters/frame={mean(test,'mean_clu'):.2f} noise/frame={mean(test,'mean_noi'):.0f} "
          f"| train mean noise/frame={mean(train,'mean_noi'):.0f}")
    print(f"   test CV clusters={np.std([r['mean_clu'] for r in test],ddof=1)/mean(test,'mean_clu'):.3f} "
          f"noise={np.std([r['mean_noi'] for r in test],ddof=1)/mean(test,'mean_noi'):.3f}")
    print(f"   test cal scenes={sum(1 for r in test if r['role']=='cal')}/12 "
          f"cal frames={sum(r['frames_on_disk'] for r in test if r['role']=='cal')}/"
          f"{sum(r['frames_on_disk'] for r in test)}")
print("   fold-mean split check: ", {k: f"{mean(folds[k][0],'mean_noi'):.0f}" for k in folds})

print()
print("=" * 78)
print("E. FALLBACK: held-out-only evaluation with SSPP cal in train only")
print("=" * 78)
ho = [r for r in data if r["role"] == "held-out"]
print(f"held-out scenes on 36 = {len(ho)}; per speed: " +
      ", ".join(f"{s:.0f}:{sum(1 for r in ho if r['speed_kmh']==s)}" for s in speeds))
for k in (1, 2, 3):
    speeds_k = {s for s, rk in rank.items() if rk % 3 == k - 1}
    test = [r for r in ho if r["speed_kmh"] in speeds_k]
    train = [r for r in data if r not in test]
    print(f"  fold {k}: test={len(test)} scenes/{sum(r['frames_on_disk'] for r in test)} frames "
          f"train={len(train)} scenes/{sum(r['frames_on_disk'] for r in train)} frames "
          f"cal-in-test={sum(1 for r in test if r['role']=='cal')}")
ho_all = ho
print(f"  pooled held-out units=18 -> hw95 for clusters at n=18: "
      f"{Z95*np.sqrt(within_between([r['clu'] for r in data])[0])/np.mean([r['mean_clu'] for r in data])/np.sqrt(18):.3f}")

print()
print("=" * 78)
print("F. current test set: interpolation vs extrapolation")
print("=" * 78)
train_speeds = sorted({r["speed_kmh"] for r in data if r["split"] == "train"})
for r in data:
    sp = r["speed_kmh"]
    r["kind"] = "extrapolated" if sp < min(train_speeds) or sp > max(train_speeds) else "interpolated"
test = [r for r in data if r["split"] == "test"]
for kind in ("interpolated", "extrapolated"):
    rs = [r for r in test if r["kind"] == kind]
    print(f"  {kind}: {len(rs)}/12 scenes {sum(r['frames_on_disk'] for r in rs)}/954 frames")
print("  train speeds", train_speeds)

print()
print("=" * 78)
print("G. budget arithmetic (assumed per-run wall times; verify with timed dry run)")
print("=" * 78)
for name, mins, matrix in (
    ("light from-scratch", 20, {"3 folds x 3 arms x 3 seeds": 27, "3 folds x 3 arms x 2 seeds": 18}),
    ("BEVFusion fine-tune", 50, {"3 folds x 2 arms x 3 seeds": 18, "3 folds x 2 arms x 2 seeds": 12,
                                 "current split x 2 arms x 3 seeds": 6}),
):
    for label, runs in matrix.items():
        h = runs * mins / 60
        print(f"  {name:22s} {label:32s} {runs:2d} runs x {mins} min = {h:5.1f} h "
              f"({h/30:.0%} of 30 h/week)")
print("  model-0 inference (no training): 2587 frames once, ~5 min; +11 min Kaggle env build per push")
