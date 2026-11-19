#!/usr/bin/env python3
"""Kaggle script kernel for Gate C (see docs/measurements/gate-c-runbook.md).

The bootstrap is NOT re-implemented here: the pinned stack recipe (uv venv with
Python 3.8, torch 1.10.1+cu113 / mmcv-full 1.4.0 / mmdet 2.20.0, CUDA toolkit
selection, compiling the 12 mmdet3d CUDA extensions) lives in
``kaggle/e2e/main.py`` from branch ``main`` and is shipped inside the
``sspp-gate-c-code`` dataset. This file only wires that proven bootstrap to the
gate C inference script.

Inputs (Kaggle datasets, mounted read-only; Kaggle extracts uploaded archives,
so both mounts are directory trees, not archives):
  * ``sspp-gate-c-code``  — tracked repo tree + ``scripts/sspp_infer.py`` +
    ``kaggle/e2e/main.py`` + ``checkpoints/lidar-only-det.pth``
  * ``sspp-gate-c-data``  — the 12 test scenes / 954 frames (``Crafter_dynamic``
    /``Golf_dynamic`` with ``velodyne`` + ``labels``), ``sspp_infos_test.pkl``
    and ``sspp_split.json`` at the mount root

Outputs (``/kaggle/working``, preserved as kernel output):
  * ``gate_c_out/gate_c_detections.jsonl``
  * ``gate_c_out/gate_c_detections_summary.json``
  * kernel log markers ``GATE_C_KERNEL_OK`` / ``GATE_C_KERNEL_FAILED``
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path

WORK = Path("/kaggle/working")
REPO = WORK / "repo"
DATASET = WORK / "sspp"
OUT = WORK / "gate_c_out"
PIN_SHORT = "da93b27"
PIN_FULL = "da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea"

_LINES = []


def log(*parts):
    print(*parts, flush=True)


def _remember(line):
    _LINES.append(line)
    if len(_LINES) > 4000:
        del _LINES[:2000]


def stream(cmd, cwd=None, env=None, timeout=None):
    log("$ " + " ".join(str(part) for part in cmd))
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=None if cwd is None else str(cwd),
        env=env,
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
            _remember(line)
            print(line, flush=True)
    finally:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log("[timeout after %ss]" % timeout)
    log("[exit=%s]" % proc.returncode)
    return proc.returncode, "\n".join(lines)


def fail(step, detail):
    log("")
    log("GATE_C_KERNEL_FAILED step=%s" % step)
    log(detail)
    sys.exit(1)


def find_input(predicate, label):
    roots = [Path("/kaggle/input")]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            try:
                if predicate(path):
                    return path
            except OSError:
                continue
    fail("mount", "could not find %s under /kaggle/input" % label)


def find_code_mount():
    """Return the code dataset root (tree form or a code.tar archive path)."""
    candidates = [
        Path("/kaggle/input/sspp-gate-c-code"),
        Path("/kaggle/input/datasets/nguynhuy9669/sspp-gate-c-code"),
    ]
    for path in candidates:
        if (path / "kaggle" / "e2e" / "main.py").is_file():
            return path
    try:
        marker = find_input(
            lambda p: p.name == "main.py"
            and p.parent.name == "e2e"
            and p.parent.parent.name == "kaggle",
            "kaggle/e2e/main.py (code dataset)",
        )
        return marker.parents[2]
    except SystemExit:
        archive = find_input(lambda p: p.name == "code.tar", "code.tar (code dataset)")
        log("code dataset is a code.tar payload:", archive)
        REPO.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:*") as handle:
            handle.extractall(REPO)
        return REPO


def find_data_mount():
    """Directory holding the test frames + infos (Kaggle extracts the tarball)."""
    candidates = [
        Path("/kaggle/input/sspp-gate-c-data"),
        Path("/kaggle/input/datasets/nguynhuy9669/sspp-gate-c-data"),
    ]
    for path in candidates:
        if (path / "sspp_infos_test.pkl").is_file() and (path / "Crafter_dynamic").is_dir():
            return path
    marker = find_input(
        lambda p: p.name == "sspp_infos_test.pkl", "sspp_infos_test.pkl (data dataset)"
    )
    return marker.parent


def load_bootstrap(code_mount):
    import importlib.util

    path = code_mount / "kaggle" / "e2e" / "main.py"
    spec = importlib.util.spec_from_file_location("gate_c_e2e_bootstrap", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        fail("bootstrap", "cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patch_bootstrap(bootstrap, code_mount):
    """Point the proven bootstrap at this kernel's paths and datasets."""
    bootstrap.DATASET_MOUNT = code_mount
    bootstrap.REPO = REPO
    bootstrap.WORK = WORK
    bootstrap.MIT = REPO / "mit" / "bevfusion"
    bootstrap.SCRATCH = Path("/root/gate_c_e2e")
    bootstrap.VENV = bootstrap.SCRATCH / "env"
    bootstrap.PY = bootstrap.VENV / "bin" / "python"
    bootstrap.LOGS = bootstrap.SCRATCH / "logs"
    bootstrap.GPU_PYTHON = sys.executable
    bootstrap.PIN_SHORT = PIN_SHORT
    bootstrap.PIN_FULL = PIN_FULL
    # The code dataset is a single code.tar payload (Kaggle files mode skips
    # directories), so bypass the tree-marker mount lookup: point it at the
    # mount and let the proven extract_code() unpack the archive.
    bootstrap.find_mount = lambda: code_mount
    log("bootstrap patched: REPO=%s SCRATCH=%s" % (bootstrap.REPO, bootstrap.SCRATCH))
    return bootstrap


def check_data_mount(data_mount):
    log("")
    log("[data] dataset mount:", data_mount)
    infos = data_mount / "sspp_infos_test.pkl"
    split = data_mount / "sspp_split.json"
    if not infos.is_file() or not split.is_file():
        fail("data", "data mount is missing sspp_infos_test.pkl / sspp_split.json")
    n_bin = len(list(data_mount.rglob("*.bin")))
    n_label = len(list(data_mount.rglob("*.label")))
    if n_bin != 954 or n_label != 954:
        fail(
            "data",
            "expected 954 .bin + 954 .label under the mount, got %d / %d"
            % (n_bin, n_label),
        )
    log("GATE_C_DATA_OK frames_bin=%d labels=%d infos=%s split=%s" % (n_bin, n_label, infos, split))
    return data_mount


def checked_checkpoint():
    path = REPO / "checkpoints" / "lidar-only-det.pth"
    if not path.is_file():
        fail("checkpoint", "missing %s (code dataset must ship it)" % path)
    return path


def dry_run(checkpoint):
    """Validate data/config/checkpoint plumbing before the ~25 min env build."""
    log("")
    log("[dry-run] scripts/sspp_infer.py --dry-run")
    command = [
        sys.executable,
        str(REPO / "scripts" / "sspp_infer.py"),
        "--dry-run",
        "--config", "model0",
        "--checkpoint", str(checkpoint),
        "--dataset-root", str(DATASET),
        "--infos", str(DATASET / "sspp_infos_test.pkl"),
        "--split-json", str(DATASET / "sspp_split.json"),
        "--split", "test",
        "--arms", "clean", "plume", "real",
        # Phải khớp run_gate_c(): nếu thiếu cờ này, dòng GATE_C_PLUME của dry-run
        # in `paper_domain=0` và người đọc log tưởng nhánh chính chạy production
        # (đã xảy ra ở kernel v5, mất một lượt kiểm tra chéo).
        "--paper-domain",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    rc, text = stream(command, cwd=REPO, env=env, timeout=1800)
    if rc != 0 or "GATE_C_DRY_RUN_OK" not in text:
        fail("dry_run", "dry-run failed rc=%d; fix data/config before the env build" % rc)
    return True


def run_gate_c(checkpoint):
    log("")
    log("[inference] scripts/sspp_infer.py")
    OUT.mkdir(parents=True, exist_ok=True)
    command = [
        str(bootstrap.PY),
        "scripts/sspp_infer.py",
        "--config", "model0",
        "--checkpoint", str(checkpoint),
        "--dataset-root", str(DATASET),
        "--infos", str(DATASET / "sspp_infos_test.pkl"),
        "--split-json", str(DATASET / "sspp_split.json"),
        "--split", "test",
        "--arms", "clean", "plume", "real",
        "--seed", "0",
        "--score-thresh", "0.2",
        # [ADR-0006 §5.7] Cách A: nhánh plume chỉ phát trong miền paper đã kiểm chứng
        # (diffusion_alpha=0, 2.5 <= |pos| <= 50 m, wfh lấy mẫu theo scene). Hai nhánh
        # clean/real không đi qua generator nên không bị ảnh hưởng.
        "--paper-domain",
        "--log-every", "50",
        "--out", str(OUT / "gate_c_detections.jsonl"),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    rc, text = stream(command, cwd=REPO, env=env, timeout=14400)
    for line in text.splitlines():
        if line.startswith(("GATE_C_ARM ", "GATE_C_PAIRED ", "GATE_C_OUTPUT ")):
            log("RESULT " + line)
    if rc != 0 or "GATE_C_OK" not in text:
        fail("inference", "sspp_infer.py rc=%d; see log above" % rc)
    return True


def main():
    started = time.time()
    global bootstrap

    global DATASET
    code_mount = find_code_mount()
    data_mount = find_data_mount()
    DATASET = check_data_mount(data_mount)
    log("GATE_C_CODE_MOUNT", code_mount)
    log("gpu:", subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True,
    ).stdout.strip())

    tar_form = code_mount == REPO
    bootstrap = patch_bootstrap(load_bootstrap(code_mount), code_mount)

    log("")
    log("[1/7] extract tracked repo tree")
    if tar_form:
        log("code dataset was a code.tar payload; already extracted into", REPO)
    else:
        bootstrap.extract_code()
    log("")
    log("[2/7] clone mit/bevfusion @", PIN_SHORT)
    bootstrap.clone_pin()
    log("")
    log("[3/7] fast dry-run (system python, no mmcv needed; needs the vendor tree)")
    checkpoint = checked_checkpoint()
    dry_run(checkpoint)
    log("")
    log("[4/7] pinned Python 3.8 venv")
    bootstrap.install_env()
    log("")
    log("[5/7] CUDA toolchain")
    toolchain = bootstrap.choose_toolchain()
    log("")
    log("[6/7] compile mmdet3d CUDA ops")
    ops_ok, ops_report = bootstrap.build_ops(toolchain)
    log("build report:", json.dumps(ops_report))
    if not ops_ok:
        fail("ops", "CUDA extension build failed")
    stack_ok, probe = bootstrap.verify_stack()
    if not stack_ok:
        fail("stack", "pinned stack import failed:\n%s" % probe[-4000:])

    log("")
    log("[7/7] gate C inference")
    run_gate_c(checkpoint)

    summary = OUT / "gate_c_detections_summary.json"
    lines = sum(1 for _ in (OUT / "gate_c_detections.jsonl").open())
    log("GATE_C_OUTPUT_LINES %d" % lines)
    log("GATE_C_OUTPUT_SUMMARY %s" % summary)
    log("elapsed_s=%.0f" % (time.time() - started))
    log("GATE_C_KERNEL_OK frames=954 arms=3")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        log("GATE_C_KERNEL_FAILED step=unhandled")
        sys.exit(1)
