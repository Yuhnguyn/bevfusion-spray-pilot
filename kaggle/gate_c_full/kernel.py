#!/usr/bin/env python3
"""Kaggle script kernel for the **full** Gate C rerun after the channel-4 fix.

This is the run that replaces the invalid v4 numbers (runbook §7b): the v4
harness fed column 4 of the SSPP ``.bin`` files (``ring``, 0..31) into the slot
nuScenes uses for **time-lag** ([-0.5; 0]), which blinded Model 0 (TP = 0/954
frames). ``scripts/sspp_infer.py`` now zeroes that column (with an assert) by
default; verify5 measured TP = 5/5 on 5 frames
(kernel ``bevfusion-gate-c-verify5-channel4-fix``). This kernel runs the whole
pre-registered experiment again: 954 test frames, 3 paired arms, tau = 0.20,
jsonl keeps every box >= 0.05.

Guard rails added on top of the v4 kernel (they check the *setup*; they do not
change any pre-registered threshold):

* ``check_harness()`` greps the mounted ``scripts/sspp_infer.py`` for the fix
  and fails at ``step=harness`` if the code dataset is stale;
* ``verify_outputs()`` fails at ``step=outputs`` unless the summary records
  ``legacy_channel4=false`` / ``z_shift_m=0``, every arm covers 954 frames, and
  the fixed detector finds at least one TP somewhere (a blind detector would
  mean the fix did not reach the GPU).

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

import hashlib
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


HARNESS_FIX_TOKENS = ("cloud[:, 4] = 0.0", "--legacy-channel4")


def check_harness():
    """Fail fast if the mounted code dataset predates the channel-4 fix.

    The verify5 kernel proved that zeroing column 4 turns Model 0 from blind
    (TP = 0/5) into a working detector (TP = 5/5); this guard makes sure the
    full rerun cannot silently reuse the stale dataset that produced the
    invalid v4 numbers.
    """
    path = REPO / "scripts" / "sspp_infer.py"
    if not path.is_file():
        fail("harness", "missing %s (code dataset must ship it)" % path)
    text = path.read_text(encoding="utf-8")
    missing = [token for token in HARNESS_FIX_TOKENS if token not in text]
    if missing:
        fail(
            "harness",
            "scripts/sspp_infer.py lacks the channel-4 fix: missing %r. The code "
            "dataset is stale; re-version sspp-gate-c-code before pushing." % (missing,),
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    log(
        "GATE_C_HARNESS path=%s sha256=%s bytes=%d channel4_fix=1 legacy_flag=1"
        % (path, digest, path.stat().st_size)
    )
    return digest


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
        "--min-score", "0.05",
        "--limit", "0",
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


def verify_outputs(harness_sha):
    """Check the run really is the fixed, full, pre-registered configuration."""
    jsonl = OUT / "gate_c_detections.jsonl"
    summary_path = OUT / "gate_c_detections_summary.json"
    if not jsonl.is_file() or not summary_path.is_file():
        fail("outputs", "missing %s or %s" % (jsonl, summary_path))
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    summary = payload["summary"]
    expected_frames = 954
    if bool(payload.get("legacy_channel4")):
        fail("outputs", "summary records legacy_channel4=true: the fix did not run")
    if float(payload.get("z_shift_m", 0.0)) != 0.0:
        fail("outputs", "summary records z_shift_m=%r, want 0.0"
             % payload.get("z_shift_m"))
    if int(payload.get("frames", 0)) != expected_frames:
        fail("outputs", "summary frames=%r, want %d"
             % (payload.get("frames"), expected_frames))
    per_arm = summary["per_arm"]
    for arm in ("clean", "plume", "real"):
        got = int(per_arm.get(arm, {}).get("n_frames", 0))
        if got != expected_frames:
            fail("outputs", "arm %s has %d frames, want %d" % (arm, got, expected_frames))
    n_lines = sum(1 for _ in jsonl.open(encoding="utf-8"))
    if n_lines != expected_frames * 3:
        fail("outputs", "jsonl has %d lines, want %d" % (n_lines, expected_frames * 3))
    tp_total = sum(
        float(item["tp_per_frame"]) * int(item["n_frames"]) for item in per_arm.values()
    )
    if tp_total <= 0.0:
        fail(
            "outputs",
            "TP total = 0 across all arms: the detector is still blind, so the "
            "channel-4 fix did not reach the model (verify5 measured TP = 5/5)",
        )
    log(
        "GATE_C_SANITY arms=%d frames=%d jsonl_lines=%d tp_total=%.1f "
        "recall_clean=%.4f harness_sha256=%s legacy_channel4=0 z_shift_m=0.000"
        % (
            len(per_arm),
            expected_frames,
            n_lines,
            tp_total,
            float(per_arm["clean"]["recall"]),
            harness_sha,
        )
    )
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
    log("[2b/7] channel-4 fix present in the mounted harness")
    harness_sha = check_harness()
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
    log("")
    log("[sanity] outputs")
    verify_outputs(harness_sha)

    summary = OUT / "gate_c_detections_summary.json"
    lines = sum(1 for _ in (OUT / "gate_c_detections.jsonl").open())
    log("GATE_C_OUTPUT_LINES %d" % lines)
    log("GATE_C_OUTPUT_SUMMARY %s" % summary)
    log("elapsed_s=%.0f" % (time.time() - started))
    log("GATE_C_KERNEL_OK frames=954 arms=3 channel4_fix=1")
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
