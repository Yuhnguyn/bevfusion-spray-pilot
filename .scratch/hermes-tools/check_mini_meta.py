#!/usr/bin/env python3
"""Check what aadimator/nuscenes-mini actually ships: metadata jsons, lidar keyframes, lidar sweeps."""
import collections
import subprocess
import sys

REF = "aadimator/nuscenes-mini"
WANT = {
    "meta": lambda p: p.startswith("v1.0-mini/"),
    "lidar_kf": lambda p: p.startswith("samples/LIDAR_TOP/"),
    "lidar_sw": lambda p: p.startswith("sweeps/LIDAR_TOP/"),
}
found = {k: [] for k in WANT}
counts = collections.Counter()
tok = ""
total = 0
for i in range(1, 201):
    cmd = ["kaggle", "datasets", "files", REF, "--format", "csv", "--page-size", "200"]
    if tok:
        cmd += ["--page-token", tok]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    tok = ""
    rows = []
    for ln in out.splitlines():
        if ln.startswith("Next Page Token ="):
            tok = ln.split("=", 1)[1].strip()
        elif ln.startswith("Warning:") or ln.startswith("name,") or not ln.strip():
            continue
        else:
            rows.append(ln.split(",")[0])
    total += len(rows)
    for p in rows:
        counts["/".join(p.split("/")[:2])] += 1
        for k, pred in WANT.items():
            if pred(p) and len(found[k]) < 3:
                found[k].append(p)
    if all(found.values()):
        print(f"ALL FOUND at page {i}, files={total}")
        break
    if not tok:
        print(f"END OF LISTING page={i} files={total}")
        break
for k, v in found.items():
    print(f"{k:9s} {len(v)>0}  {v[:2]}")
print("top prefixes:")
for k, v in counts.most_common(10):
    print(f"{v:6d}  {k}")