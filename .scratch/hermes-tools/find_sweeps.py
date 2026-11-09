#!/usr/bin/env python3
"""Walk the aadimator/nuscenes-mini file listing until sweeps/LIDAR_TOP is seen."""
import collections
import subprocess
import sys

REF = "aadimator/nuscenes-mini"
TARGET = "sweeps/LIDAR_TOP/"


def page(token):
    cmd = ["kaggle", "datasets", "files", REF, "--format", "csv", "--page-size", "200"]
    if token:
        cmd += ["--page-token", token]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    tok, rows = "", []
    for ln in out.splitlines():
        if ln.startswith("Next Page Token ="):
            tok = ln.split("=", 1)[1].strip()
        elif ln.startswith("Warning:") or ln.startswith("name,") or not ln.strip():
            continue
        else:
            rows.append(ln.split(",")[0])
    return tok, rows


tok = ""
counts = collections.Counter()
total = 0
for i in range(1, 161):
    tok, rows = page(tok)
    total += len(rows)
    for p in rows:
        counts["/".join(p.split("/")[:2])] += 1
        if TARGET in p:
            print(f"FOUND {p}")
            print(f"pages={i} files={total}")
            for k, v in counts.most_common(12):
                print(f"{v:6d}  {k}")
            sys.exit(0)
    if not tok:
        print(f"END OF LISTING pages={i} files={total} -> no {TARGET}")
        for k, v in counts.most_common(20):
            print(f"{v:6d}  {k}")
        sys.exit(1)
    if i % 20 == 0:
        print(f"...page {i}, files {total}", flush=True)
print(f"GAVE UP after 160 pages, files={total}")
sys.exit(2)