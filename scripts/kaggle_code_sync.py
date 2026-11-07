#!/usr/bin/env python3
"""Publish the repo's tracked files as a private Kaggle Dataset.

The GitHub repo is private (the Kaggle kernel cannot clone it) and ``data/`` is
16 GB, so the only thing uploaded is what ``git ls-files`` reports (~2 MB).
``mit/bevfusion`` is a pinned vendor clone and is never tracked; ``data/`` and
``third_party/`` are gitignored. The vendor clone is recreated inside the
kernel by ``kaggle/e2e/main.py``.

The dataset payload is one ``code.tar`` (Kaggle datasets are flat, top-level
directories are skipped by the CLI), so the kernel extracts it into
``/kaggle/working/repo``.

Idempotent: creates the dataset on the first run and adds a new version on
later runs. The dataset is always private; no ``--public`` flag is ever passed.

Usage::

    python3 scripts/kaggle_code_sync.py            # create or add a version
    python3 scripts/kaggle_code_sync.py --dry-run  # stage only, no upload
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

DATASET_ID = "nguynhuy9669/bevfusion-spray-pilot-code"
DATASET_TITLE = "BEVFusion spray pilot code"
DATASET_URL = "https://www.kaggle.com/datasets/" + DATASET_ID
PAYLOAD_NAME = "code.tar"

# Tracked files that must never be uploaded even if someone force-adds them.
FORBIDDEN_TOP_LEVEL = {
    "data",
    "third_party",
    "results",
    "archive",
    "kernel",
    "interactive",
    "notebook-kernel",
}
# Only this tracked path is allowed under mit/ (the vendor clone is not tracked).
ALLOWED_UNDER_MIT = {"mit/PIN.md"}

MAX_FILE_BYTES = 50 * 1024 * 1024
READY_TIMEOUT_S = 15 * 60
POLL_INTERVAL_S = 15


def log(*parts):
    print(*parts, flush=True)


def run(cmd, check=True, timeout=None, cwd=None):
    """Run a command, stream its output, return (rc, text)."""
    printable = " ".join(str(part) for part in cmd)
    log("$", printable)
    started = time.time()
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            log(line)
    finally:
        proc.wait(timeout=timeout)
    rc = proc.returncode
    log("[exit=%s in %.1fs]" % (rc, time.time() - started))
    text = "\n".join(lines)
    if check and rc != 0:
        raise SystemExit("command failed (rc=%d): %s" % (rc, printable))
    return rc, text


def repo_root():
    return Path(__file__).resolve().parents[1]


def git(root, *args):
    done = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return done.stdout


def tracked_files(root):
    raw = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8")
    return [rel for rel in raw.split("\0") if rel]


def check_path_allowed(rel):
    top = rel.split("/", 1)[0]
    if top in FORBIDDEN_TOP_LEVEL:
        raise SystemExit("refusing to upload forbidden path: " + rel)
    if top == "mit" and rel not in ALLOWED_UNDER_MIT:
        raise SystemExit("refusing to upload vendor clone path: " + rel)


def stage(root, staging):
    """Copy only tracked files into ``staging``; return [(rel, size), ...]."""
    files = []
    for rel in tracked_files(root):
        check_path_allowed(rel)
        source = root / rel
        if not source.is_file():
            raise SystemExit("tracked path missing from working tree: " + rel)
        size = source.stat().st_size
        if size > MAX_FILE_BYTES:
            raise SystemExit(
                "tracked file looks like a weight/data blob (%d bytes): %s"
                % (size, rel)
            )
        target = staging / "tree" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files.append((rel, size))
    return files


def make_payload(staging, files):
    payload = staging / PAYLOAD_NAME
    with tarfile.open(payload, "w") as archive:
        for rel, _size in files:
            archive.add(staging / "tree" / rel, arcname=rel, recursive=False)
    return payload


def write_metadata(staging):
    metadata = {
        "title": DATASET_TITLE,
        "id": DATASET_ID,
        "licenses": [{"name": "CC0-1.0"}],
        "isPrivate": True,
        "description": (
            "Tracked source of the bevfusion-spray-pilot repo (git ls-files "
            "only; no data/, no checkpoint, no vendor clone). Payload is "
            "code.tar, extracted by the bevfusion-e2e script kernel."
        ),
    }
    path = staging / "dataset-metadata.json"
    path.write_text(json.dumps(metadata, indent=2) + "\n")
    return path


def kaggle_executable():
    found = shutil.which("kaggle")
    if found is None:
        raise SystemExit(
            "kaggle CLI not found on PATH; it must be authenticated in this env"
        )
    return found


def parse_json_output(text):
    """Parse CLI output that may be preceded by the version warning line.

    The kaggle CLI prints its "outdated version" warning on stdout when stdout
    is not a tty, so the JSON payload is not the whole stream.
    """
    start = text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        for line in reversed(text.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    return None


def dataset_status(kaggle, ref=DATASET_ID):
    """Return the parsed status JSON, or None when the dataset does not exist."""
    done = subprocess.run(
        [kaggle, "datasets", "status", ref, "--format", "json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if done.returncode != 0:
        return None
    return parse_json_output(done.stdout)


def wait_until_ready(kaggle, ref, baseline_version):
    """Wait for a ready dataset whose version is newer than ``baseline_version``."""
    deadline = time.time() + READY_TIMEOUT_S
    last_state = "unknown"
    while True:
        status = dataset_status(kaggle, ref)
        if status is None:
            # Right after create/version the status endpoint can 404 for a
            # few seconds; keep polling instead of failing.
            log("dataset status: not visible yet (upload still registering)")
        else:
            state = str(status.get("status", "")).lower()
            version = int(status.get("current_version_number") or 0)
            last_state = state
            log("dataset status: %s (version %s)" % (state, version))
            if state == "ready" and version > baseline_version:
                return status
        if time.time() > deadline:
            raise SystemExit(
                "dataset %s not ready after %ds (last status: %s)"
                % (ref, READY_TIMEOUT_S, last_state)
            )
        time.sleep(POLL_INTERVAL_S)


def upload_failed(rc, text):
    lowered = text.lower()
    return rc != 0 or "error" in lowered or "already in use" in lowered


def create_or_version(kaggle, staging, notes, baseline_version):
    if baseline_version:
        log("dataset exists (version %d); adding a version" % baseline_version)
        rc, text = run(
            [kaggle, "datasets", "version", "-p", str(staging), "-m", notes],
            check=False,
        )
        if upload_failed(rc, text):
            raise SystemExit("kaggle datasets version failed (rc=%d)" % rc)
        return

    log("dataset does not exist yet; creating it (private)")
    rc, text = run([kaggle, "datasets", "create", "-p", str(staging)], check=False)
    if not upload_failed(rc, text):
        return

    # A stale status lookup (or a title collision) can make create fail while
    # the dataset does exist; falling back to a version keeps reruns idempotent.
    log("create did not succeed; retrying as a dataset version")
    rc, text = run(
        [kaggle, "datasets", "version", "-p", str(staging), "-m", notes],
        check=False,
    )
    if upload_failed(rc, text):
        raise SystemExit("kaggle upload failed (rc=%d)" % rc)


def human_mb(size):
    return "%.2f MB" % (size / (1024.0 * 1024.0))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="stage and measure the payload but do not touch Kaggle",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="dataset version notes (default: git short sha, +dirty marker)",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="keep the staging directory instead of deleting it",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    head = git(root, "rev-parse", "--short", "HEAD").strip()
    dirty = bool(git(root, "status", "--porcelain").strip())
    notes = args.message or (head + ("+dirty" if dirty else ""))

    staging = Path(tempfile.mkdtemp(prefix="kaggle-code-sync-"))
    try:
        files = stage(root, staging)
        total_bytes = sum(size for _rel, size in files)
        payload = make_payload(staging, files)
        write_metadata(staging)

        top_level = sorted(
            entry.name for entry in staging.iterdir() if entry.name != "tree"
        )
        if top_level != sorted([PAYLOAD_NAME, "dataset-metadata.json"]):
            raise SystemExit("unexpected staging layout: %s" % top_level)
        shutil.rmtree(staging / "tree")

        log("")
        log("dataset :", DATASET_ID)
        log("files   :", len(files))
        log("tracked :", "%d bytes (%s)" % (total_bytes, human_mb(total_bytes)))
        log("payload :", "%d bytes (%s)" % (payload.stat().st_size, human_mb(payload.stat().st_size)))
        log("notes   :", notes)
        log("staging :", staging)

        if args.dry_run:
            log("dry run: nothing uploaded")
            log("KAGGLE_CODE_SYNC_OK")
            return 0

        kaggle = kaggle_executable()
        before = dataset_status(kaggle)
        baseline = int(before.get("current_version_number") or 0) if before else 0
        create_or_version(kaggle, staging, notes, baseline)
        status = wait_until_ready(kaggle, DATASET_ID, baseline)

        log("")
        log("dataset :", DATASET_ID)
        log("version :", status.get("current_version_number"))
        log("status  :", status.get("status"))
        log("files   :", len(files))
        log("tracked :", human_mb(total_bytes))
        log("url     :", DATASET_URL)
        log("KAGGLE_CODE_SYNC_OK")
        return 0
    finally:
        if args.keep_staging:
            log("kept staging dir:", staging)
        else:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
