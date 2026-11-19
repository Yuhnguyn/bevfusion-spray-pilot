#!/usr/bin/env python3
"""Build (and optionally upload) the two Kaggle bundles gate C needs.

Two datasets, because the code changes often while the frames do not:

* ``sspp-gate-c-code`` — tracked repo tree (``git ls-files``) + the new
  ``scripts/sspp_infer.py`` + ``kaggle/e2e/main.py`` copied from branch
  ``main`` (the proven bootstrap recipe) + ``checkpoints/lidar-only-det.pth``;
* ``sspp-gate-c-data`` — ``sspp_test.tar.gz``: the 12 test scenes / 954 frames
  (``velodyne/*.bin`` + ``labels/*.label``) + ``sspp_infos_test.pkl`` +
  ``sspp_split.json``.

The script only stages by default. ``--upload`` runs ``kaggle datasets
create/version``, ``--push`` runs ``kaggle kernels push``. Every command is
printed first so it can be run by hand if the API is blocked.

Usage::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
        kaggle/gate_c/make_bundles.py --stage
    ... make_bundles.py --upload
    ... make_bundles.py --push
"""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "kaggle" / "gate_c"
CODE_DIR = GATE / "bundles" / "code"
CODE_TREE = GATE / "bundles" / "code_tree"
DATA_DIR = GATE / "bundles" / "data"
CHECKPOINT = REPO / "data" / "lidar-only-det.pth"
KAGGLE = shutil.which("kaggle") or str(Path.home() / ".local" / "bin" / "kaggle")
CODE_DATASET = "nguynhuy9669/sspp-gate-c-code"
DATA_DATASET = "nguynhuy9669/sspp-gate-c-data"
KERNEL_ID = "nguynhuy9669/bevfusion-gate-c-plume-vs-detector"

CODE_METADATA = {
    "title": "SSPP gate C code + bootstrap + checkpoint",
    "id": CODE_DATASET,
    "licenses": [{"name": "CC0-1.0"}],
    "subtitle": "Tracked repo tree, proven Kaggle bootstrap, lidar-only checkpoint",
    "description": (
        "Gate C bundle A: tracked files of the sspp branch (spray/, proxy_eval/, "
        "tests/, scripts/sspp_infer.py), kaggle/e2e/main.py from branch main "
        "(pinned torch/mmcv/mmdet3d bootstrap), and checkpoints/lidar-only-det.pth "
        "(33.362.653 byte, LiDAR-only BEVFusion baseline)."
    ),
    "isPrivate": True,
}

DATA_METADATA = {
    "title": "SSPP gate C test split (12 scenes, 954 frames)",
    "id": DATA_DATASET,
    "licenses": [{"name": "CC0-1.0"}],
    "subtitle": "SemanticSpray++ test frames + semantic labels + infos for gate C",
    "description": (
        "Gate C bundle B: the 12 test scenes (954 frames) of the frozen speed "
        "split: velodyne/*.bin, labels/*.label, sspp_infos_test.pkl, "
        "sspp_split.json, packed as sspp_test.tar.gz (extract to a working dir, "
        "pass --dataset-root/--infos to scripts/sspp_infer.py)."
    ),
    "isPrivate": True,
}


def log(*parts):
    print(*parts, flush=True)


def run(cmd, check=True, cwd=None):
    log("$ " + " ".join(str(part) for part in cmd))
    completed = subprocess.run([str(part) for part in cmd], cwd=cwd)
    if check and completed.returncode != 0:
        raise SystemExit("command failed rc=%d" % completed.returncode)
    return completed.returncode


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        stdout=subprocess.PIPE,
        check=True,
    )
    return [name for name in completed.stdout.decode().split("\0") if name]


def stage_code() -> None:
    """Pack the code tree into one ``code.tar``.

    Kaggle ``datasets create`` in files mode SKIPS directories, so the proven
    layout (main branch) is a single tarball payload: the kernel's bootstrap
    extracts ``*.tar`` from the dataset mount. Anything tree-shaped is built
    in ``CODE_TREE`` first and only the archive is uploaded.
    """
    log("[code] staging tree", CODE_TREE)
    if CODE_TREE.is_dir():
        shutil.rmtree(CODE_TREE)
    CODE_TREE.mkdir(parents=True)
    copied = 0
    for rel in tracked_files():
        source = REPO / rel
        if not source.is_file():
            continue
        target = CODE_TREE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    # The new inference script is not committed yet (Lead commits after review).
    for rel in ("scripts/sspp_infer.py",):
        source = REPO / rel
        if not source.is_file():
            raise SystemExit("missing file to bundle: %s" % source)
        target = CODE_TREE / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    # Bootstrap recipe: deleted on branch sspp, still in branch main history.
    bootstrap = subprocess.run(
        ["git", "-C", str(REPO), "show", "main:kaggle/e2e/main.py"],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
    target = CODE_TREE / "kaggle" / "e2e" / "main.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bootstrap)
    copied += 1
    if not CHECKPOINT.is_file():
        raise SystemExit("missing checkpoint: %s" % CHECKPOINT)
    target = CODE_TREE / "checkpoints" / "lidar-only-det.pth"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKPOINT, target)

    if CODE_DIR.is_dir():
        shutil.rmtree(CODE_DIR)
    CODE_DIR.mkdir(parents=True)
    archive = CODE_DIR / "code.tar"
    with tarfile.open(archive, "w") as handle:
        # One recursive add of the root: adding every rglob entry would add
        # each directory's content once per ancestor.  e2e bootstrap extracts
        # the archive into REPO, so the members must sit at the archive root.
        handle.add(CODE_TREE, arcname=".")
    (CODE_DIR / "dataset-metadata.json").write_text(
        json.dumps(CODE_METADATA, indent=2) + "\n", encoding="utf-8"
    )
    log("[code] files=%d payload=%s bytes=%d" % (copied, archive, archive.stat().st_size))


def stage_data(force: bool = False) -> None:
    log("[data] staging", DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    archive = DATA_DIR / "sspp_test.tar.gz"
    if archive.is_file() and not force:
        log("[data] archive already present:", archive, archive.stat().st_size)
    else:
        root = REPO / "data" / "SemanticSprayDataset"
        with (REPO / "data" / "sspp_infos_test.pkl").open("rb") as handle:
            infos = pickle.load(handle)
        entries = set()
        for info in infos:
            bin_path = root / info["lidar_path"]
            label = bin_path.parent.parent / "labels" / (bin_path.stem + ".label")
            entries.add(bin_path.relative_to(root))
            entries.add(label.relative_to(root))
        with tarfile.open(archive, "w:gz", compresslevel=6) as handle:
            for rel in sorted(entries, key=str):
                handle.add(root / rel, arcname=str(rel))
            handle.add(REPO / "data" / "sspp_infos_test.pkl", arcname="sspp_infos_test.pkl")
            handle.add(REPO / "data" / "sspp_split.json", arcname="sspp_split.json")
        log("[data] archive", archive, archive.stat().st_size)
    (DATA_DIR / "dataset-metadata.json").write_text(
        json.dumps(DATA_METADATA, indent=2) + "\n", encoding="utf-8"
    )


def dataset_exists(slug: str) -> bool:
    completed = subprocess.run(
        [KAGGLE, "datasets", "list", "-m"], capture_output=True, text=True
    )
    return slug in completed.stdout


def upload(directory: Path, slug: str, message: str) -> None:
    metadata = json.loads((directory / "dataset-metadata.json").read_text())
    # No --dir-mode: the proven code dataset (main branch) mounts individual
    # files, and both kernel lookups and the bootstrap find_mount() rely on
    # the directory tree being visible as-is.
    if dataset_exists(slug):
        run([KAGGLE, "datasets", "version", "-p", directory, "-m", message])
    else:
        run([KAGGLE, "datasets", "create", "-p", directory])


def upload_all() -> None:
    upload(CODE_DIR, CODE_DATASET, "gate C code bundle")
    upload(DATA_DIR, DATA_DATASET, "gate C test split (954 frames)")


def push_kernel(submit: bool = False) -> None:
    command = [KAGGLE, "kernels", "push", "-p", GATE]
    run(command)
    if submit:
        run([KAGGLE, "kernels", "status", KERNEL_ID])
    log("watch: %s kernels status %s" % (KAGGLE, KERNEL_ID))
    log("logs : %s kernels output %s -p /tmp/gate_c_out" % (KAGGLE, KERNEL_ID))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true", help="stage both bundles")
    parser.add_argument("--force", action="store_true", help="rebuild the data tarball")
    parser.add_argument("--upload", action="store_true", help="create/version both datasets")
    parser.add_argument("--push", action="store_true", help="push the kernel")
    parser.add_argument("--submit", action="store_true", help="push and poll status")
    args = parser.parse_args(argv)
    if not (args.stage or args.upload or args.push or args.submit):
        parser.print_help()
        return 2
    if args.stage or args.upload:
        stage_code()
        stage_data(force=args.force)
    if args.upload:
        upload_all()
    if args.push or args.submit:
        push_kernel(submit=args.submit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
