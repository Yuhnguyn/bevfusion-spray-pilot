#!/usr/bin/env python3
"""Fetch SemanticSprayDataset through the Oparu DSpace REST API.

The upstream download.sh relies on wget and on bitstream URLs that now return
the DSpace HTML shell, so this script resolves the ORIGINAL bundle at runtime
and downloads the split zip parts with resume support.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

BASE = "https://oparu.uni-ulm.de/server/api"
ITEM = "a4b310b9-bf50-431b-9676-7398f6da7dd0"
CHUNK = 64 << 10
MIN_SEG = 32 << 20
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS_ZIP = os.path.join(
    REPO, "third_party", "semantic_spray_dataset", "storage",
    "object_and_radar_labels.zip")


def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def original_files():
    bundles = api(f"{BASE}/core/items/{ITEM}/bundles?size=50")["_embedded"][
        "bundles"]
    for bundle in bundles:
        if bundle["name"] != "ORIGINAL":
            continue
        href = bundle["_links"]["bitstreams"]["href"] + "?size=100"
        streams = api(href)["_embedded"]["bitstreams"]
        return [(s["name"], s.get("sizeBytes", 0),
                 s["_links"]["content"]["href"]) for s in streams]
    raise SystemExit("ORIGINAL bundle not found")


def _fetch_range(url, path, start, end, retries=60):
    want = end - start + 1
    for attempt in range(retries):
        local = os.path.getsize(path) if os.path.exists(path) else 0
        if local == want:
            return
        if local > want:
            os.remove(path)
            local = 0
        try:
            req = urllib.request.Request(
                url, headers={"Range": f"bytes={start + local}-{end}"})
            with urllib.request.urlopen(req, timeout=20) as resp, open(
                    path, "ab") as out:
                remaining = want - local
                while remaining > 0:
                    chunk = resp.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
        except Exception as exc:  # connection drops are common upstream
            print(f"\n  retry {os.path.basename(path)}: {exc}")
        if os.path.getsize(path) != want:
            time.sleep(min(5 * (attempt + 1), 60))
    if os.path.getsize(path) != want:
        raise RuntimeError(f"size mismatch for {path}")


def download(url, path, size, jobs=8):
    have = os.path.getsize(path) if os.path.exists(path) else 0
    if size and have == size:
        print(f"skip {os.path.basename(path)} (already complete)")
        return
    if size and have > size:
        os.remove(path)
        have = 0
    if not size:
        with urllib.request.urlopen(
                urllib.request.Request(url), timeout=120) as resp, open(
                    path, "ab") as out:
            shutil.copyfileobj(resp, out)
        return

    name = os.path.basename(path)
    remaining = size - have
    nseg = max(1, min(jobs, (remaining + MIN_SEG - 1) // MIN_SEG))
    seg_size = (remaining + nseg - 1) // nseg
    print(f"download {name}: {have / 1e6:.1f} -> {size / 1e6:.1f} MB "
          f"with {nseg} connections")

    segs = []
    for i in range(nseg):
        start = have + i * seg_size
        end = min(start + seg_size, size) - 1
        segs.append((start, end, f"{path}.seg{i:02d}"))

    errors = []

    def run(seg):
        try:
            _fetch_range(url, seg[2], seg[0], seg[1])
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(s,)) for s in segs]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(2)
        got = have + sum(os.path.getsize(s[2]) for s in segs
                         if os.path.exists(s[2]))
        print(f"\r  {100 * got / size:5.1f}%  "
              f"{got / 1e6:8.1f}/{size / 1e6:.1f} MB  ({nseg} conn)",
              end="",
              flush=True)
    for t in threads:
        t.join()
    if errors:
        raise SystemExit(f"download failed for {name}: {errors[0]}")

    with open(path, "ab") as out:
        for _, _, segpath in segs:
            with open(segpath, "rb") as s:
                shutil.copyfileobj(s, out)
            os.remove(segpath)
    print()
    if os.path.getsize(path) != size:
        raise SystemExit(f"size mismatch for {path}")


def extract(dest):
    for tool in ("zip", "unzip"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} is required for extraction")

    tmp = os.path.join(dest, "tmp")
    first = os.path.join(tmp, "SemanticSprayDataset.zip")
    single = os.path.join(tmp, "SemanticSprayDataset_single_file.zip")
    if not os.path.exists(single):
        print("combining split archive...")
        subprocess.run(["zip", "-F", first, "--out", single], check=True)

    print("extracting dataset...")
    subprocess.run(["unzip", "-q", "-o", single, "-d", tmp], check=True)

    if os.path.exists(LABELS_ZIP):
        print("merging object and radar labels...")
        subprocess.run(["unzip", "-q", "-o", LABELS_ZIP, "-d", tmp], check=True)
        scene_root = os.path.join(tmp, "SemanticSprayDataset")
        for name in ("radar_labels", "object_labels"):
            src = os.path.join(tmp, name)
            if os.path.isdir(src):
                for child in os.listdir(src):
                    shutil.copytree(
                        os.path.join(src, child),
                        os.path.join(scene_root, child),
                        dirs_exist_ok=True)
    else:
        print(f"warning: label zip not found at {LABELS_ZIP}")

    final = os.path.join(dest, "SemanticSprayDataset")
    if os.path.exists(final):
        raise SystemExit(f"{final} already exists; move it away first")
    print(f"moving to {final}")
    shutil.move(os.path.join(tmp, "SemanticSprayDataset"), final)
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default=os.path.join(REPO, "data"))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--jobs", type=int, default=8,
                        help="parallel connections per file (default 8)")
    args = parser.parse_args()

    files = original_files()
    total = sum(size for _, size, _ in files)
    print(f"{len(files)} files, {total / 1e9:.2f} GB total")
    for name, size, _ in files:
        print(f"  {name:32} {size / 1e6:8.1f} MB")

    if args.list or not (args.download or args.extract or args.all):
        return

    os.makedirs(os.path.join(args.dest, "tmp"), exist_ok=True)
    if args.download or args.all:
        lock = os.path.join(args.dest, "tmp", ".download.lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(open(lock).read().strip() or 0)
            except ValueError:
                pid = 0
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
            if alive:
                raise SystemExit(
                    f"another download is already running (pid {pid})")
            os.remove(lock)
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        try:
            for name, size, href in files:
                download(href, os.path.join(args.dest, "tmp", name), size,
                         jobs=args.jobs)
        finally:
            os.remove(lock)
    if args.extract or args.all:
        extract(args.dest)


if __name__ == "__main__":
    sys.exit(main())
