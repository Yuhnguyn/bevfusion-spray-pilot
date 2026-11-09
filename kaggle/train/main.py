#!/usr/bin/env python3
"""Script kernel: run the ticket 11-b smoke run on the pinned vendor stack.

The boot steps are not re-implemented here. ``kaggle/e2e/main.py`` already
extracts the code dataset, clones ``mit/bevfusion`` at the pin, builds the
Python 3.8 venv, compiles the mmdet3d CUDA extensions and verifies the stack;
this kernel imports that module and calls its functions, installs
``nuscenes-devkit`` into the venv (the mini split builder needs the real
devkit), then runs ``kaggle/train/smoke.py`` inside that venv.

``--task <name>`` in ``task_args.txt`` selects the script under ``kaggle/train``
that is executed (default ``smoke``); the smoke run prints ``SMOKE_DEVKIT_OK`` /
``MINI_SPLIT_OK`` / ``SMOKE_STEP`` / ``SMOKE_OK`` and the A/B training run
prints ``AB_STEP`` / ``AB_ARM_OK`` / ``AB_TRAIN_OK`` so the evidence can be
grepped out of the kernel log.
"""

import importlib.util
import pathlib
import sys

DEFAULT_TASK = "smoke"
DEVKIT_PINS = ("1.1.11", "1.1.10")
ARGS_FILE = pathlib.Path(__file__).resolve().parent / "task_args.txt"
TASK_MARKERS = ("SMOKE_OK", "SWEEPS_OK", "AB_TRAIN_OK", "EVAL_OK")


def task_script(task):
    """Return the repo-relative path of the script that runs ``task``."""
    return "kaggle/train/%s.py" % task.replace("-", "_")


TASK_SCRIPT = task_script(DEFAULT_TASK)


def devkit_packages(version):
    """Return the packages that install ``nuscenes-devkit==<version>`` safely.

    numpy and opencv-python stay pinned: the devkit's ``numpy`` requirement is
    loose and letting the resolver upgrade it breaks the pinned torch 1.10 /
    numba stack.
    """
    return [
        "nuscenes-devkit==%s" % version,
        "numpy==1.22.4",
        "opencv-python==4.8.1.78",
    ]


# The dataset mount layout has been both /kaggle/input/<slug> and
# /kaggle/input/datasets/<owner>/<slug>; rglob finds the boot module in either.
BOOT = next(pathlib.Path("/kaggle/input").rglob("kaggle/e2e/main.py"))


def log(*parts):
    print(*parts, flush=True)


def resolve_args_file(candidates):
    """Return the first existing path in ``candidates``, or ``None``.

    The kernel script is started as ``/kaggle/src/main.py`` while the code tree
    is extracted to ``e2e.REPO`` (``/kaggle/working/repo``), so
    ``__file__`` cannot be the only source for ``task_args.txt``.
    """
    for candidate in candidates:
        path = pathlib.Path(candidate)
        if path.is_file():
            return path
    return None


def task_args(path=ARGS_FILE):
    """Extra CLI tokens for the task script, read from ``task_args.txt``.

    Kaggle starts the kernel script without arguments and a script kernel
    cannot set environment variables for it, so the pushed source tree is the
    only channel.  A missing file means no extra tokens; blank lines and lines
    starting with ``#`` are ignored.
    """
    if path is None:
        return []
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens.extend(token for token in line.split() if token)
    return tokens


def parse_task(args):
    """Split ``--task <name>`` out of the task-script arguments.

    ``--task`` may appear anywhere and accepts both ``--task name`` and
    ``--task=name``.  It is never forwarded to the task script: the kernel is
    the only component that reads it.  Without the flag the default task
    (``smoke``) is used and every token is kept.
    """
    task = DEFAULT_TASK
    rest = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--task":
            if index + 1 < len(args):
                task = args[index + 1]
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--task="):
            task = token[len("--task="):]
            index += 1
            continue
        rest.append(token)
        index += 1
    return task, rest


def verdict(rc, text):
    """Return ``(passed, marker)`` for a finished task run.

    ``marker`` is the success line found in the log, or ``""`` when the run
    failed.  The A/B smoke run (``SMOKE_OK``) and the sweeps probe
    (``SWEEPS_OK``) both count as success.
    """
    if rc != 0:
        return False, ""
    for marker in TASK_MARKERS:
        if marker in text:
            return True, marker
    return False, ""


def load_e2e(path):
    spec = importlib.util.spec_from_file_location("e2e_boot", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_devkit(e2e):
    """Install ``nuscenes-devkit`` into the pinned venv and prove it imports.

    The venv is created with ``uv venv`` and has no ``pip``, so the primary
    path is ``e2e.pip_into_env`` (uv, with ``--python`` pointing at the venv).
    Only if that fails do we bootstrap pip and fall back to ``-m pip``. numpy
    is re-pinned in the same install: the devkit has a loose ``numpy``
    requirement and letting the resolver upgrade it would break the pinned
    torch 1.10 / numba stack.
    """
    installed = None
    for version in DEVKIT_PINS:
        packages = devkit_packages(version)
        via = "uv"
        rc, _ = e2e.pip_into_env(*packages)
        if rc != 0:
            rc_ensurepip, _ = e2e.stream(
                [str(e2e.PY), "-m", "ensurepip", "--upgrade"]
            )
            if rc_ensurepip == 0:
                via = "ensurepip"
                rc, _ = e2e.stream(
                    [str(e2e.PY), "-m", "pip", "install"] + packages,
                    timeout=3600,
                    log_name="devkit.log",
                )
        if rc != 0:
            log("SMOKE_DEVKIT_INSTALL_FAILED version=%s" % version)
            continue
        log("SMOKE_DEVKIT_INSTALL via=%s version=%s" % (via, version))
        probe = e2e.capture(
            [
                str(e2e.PY),
                "-c",
                "from importlib import metadata as md;"
                "from nuscenes.utils import splits;"
                "from nuscenes.nuscenes import NuScenes;"
                "print('SMOKE_DEVKIT_OK version=%s val=%d'"
                " % (md.version('nuscenes-devkit'), len(splits.val)))",
            ]
        )
        log(probe[-2000:])
        if "SMOKE_DEVKIT_OK" in probe and "val=150" in probe:
            installed = version
            break
        log("SMOKE_DEVKIT_VERIFY_FAILED version=%s" % version)

    if installed is None:
        log("SMOKE_FAILED devkit")
        return None

    stack = e2e.capture(
        [
            str(e2e.PY),
            "-c",
            "import numpy, torch, mmcv, mmdet;"
            "print(numpy.__version__, torch.__version__,"
            " mmcv.__version__, mmdet.__version__)",
        ]
    )
    log("post-devkit stack: %s" % stack)
    if "1.22.4" not in stack or e2e.PINNED_PROBE not in stack:
        log("SMOKE_FAILED pinned_stack_drift")
        return None
    return installed


def install_numba_errors_shim(e2e):
    """Alias ``numba.errors`` -> ``numba.core.errors`` (numba >= 0.49 moved it).

    ``mit/bevfusion@da93b27`` does ``from numba.errors import
    NumbaPerformanceWarning`` in ``mmdet3d/datasets/pipelines/utils.py``. The
    pinned numba 0.58.1 dropped that module. Patching the vendor tree would
    break the pin, so write a one-line alias into the venv's site-packages.
    """
    shim = e2e.VENV / "lib" / "python3.8" / "site-packages" / "numba" / "errors.py"
    if not shim.parent.is_dir():
        log("SMOKE_FAILED numba_shim_missing_numba")
        return False
    shim.write_text(
        '"""Compatibility shim: numba moved these classes to numba.core.errors."""\n'
        "from numba.core.errors import *  # noqa: F401,F403\n"
    )
    probe = e2e.capture(
        [
            str(e2e.PY),
            "-c",
            "import numba, numba.errors, mmdet3d.datasets.pipelines;"
            "print('SMOKE_NUMBA_SHIM_OK', numba.__version__)",
        ]
    )
    if "SMOKE_NUMBA_SHIM_OK" in probe:
        log(_field(probe, "SMOKE_NUMBA_SHIM_OK"))
        return True
    log("SMOKE_FAILED numba_shim")
    log(probe[-2000:])
    return False


def main():
    log("PROBE_STEP boot %s" % BOOT)
    e2e = load_e2e(BOOT)

    e2e.extract_code()
    e2e.clone_pin()
    e2e.install_env()
    toolchain = e2e.choose_toolchain()

    ops_ok, ops_report = e2e.build_ops(toolchain)
    log("PROBE_STEP ops %s" % ops_report)
    stack_ok, stack_probe = e2e.verify_stack()
    ok = bool(ops_ok and stack_ok)
    log("PROBE_STEP stack_ready %s" % ok)
    if not ok:
        log("PROBE_FAILED stack_setup")
        log(stack_probe[-4000:])
        return 1

    version = install_devkit(e2e)
    if version is None:
        return 1

    if not install_numba_errors_shim(e2e):
        return 1

    args_path = resolve_args_file(
        [
            pathlib.Path(e2e.REPO) / "kaggle/train/task_args.txt",
            pathlib.Path.cwd() / "kaggle/train/task_args.txt",
            pathlib.Path(__file__).resolve().parent / "task_args.txt",
        ]
    )
    log("TASK_ARGS_FILE %s" % (args_path if args_path else "none"))
    raw_args = task_args(args_path)
    task, args = parse_task(raw_args)
    script = task_script(task)
    log("TASK_NAME %s" % task)
    log("TASK_SCRIPT %s" % script)
    log("TASK_ARGS %s" % (" ".join(args) if args else "(none)"))
    if not (pathlib.Path(e2e.REPO) / script).is_file():
        log("TASK_FAILED script_missing")
        log("script_missing %s" % script)
        return 1
    rc, text = e2e.stream(
        [str(e2e.PY), script] + args,
        cwd=e2e.REPO,
        timeout=10800,
        log_name="%s.log" % task,
    )

    passed, marker = verdict(rc, text)
    log("")
    log("=" * 72)
    log("task          : %s (%s)" % (task, script))
    log("devkit        : %s" % version)
    log("mini split    : %s" % _field(text, "MINI_SPLIT_OK"))
    log("%s rc      : %d" % (task, rc))
    log("%s verdict : %s" % (task, marker if passed else "FAILED"))
    if "SWEEPS_OK" in text or "SWEEPS_FAILED" in text:
        log("SWEEPS_INFO   : %s" % _field(text, "SWEEPS_INFO"))
        log("SWEEPS_PTS    : %s" % _field(text, "SWEEPS_PTS mode=multi"))
        log("SWEEPS_UNIQUE : %s" % _field(text, "SWEEPS_UNIQUE"))
        log("STEP_TIME     : %s" % _field(text, "STEP_TIME"))
    if "AB_TRAIN_OK" in text or "AB_FAILED" in text:
        log("AB_TRAIN_OK   : %s" % _field(text, "AB_TRAIN_OK"))
        log("AB_ARM_A      : %s" % _field(text, "AB_ARM_OK arm=A"))
        log("AB_ARM_B      : %s" % _field(text, "AB_ARM_OK arm=B"))
        log("AB_FAILED     : %s" % _field(text, "AB_FAILED"))
    if "EVAL_OK" in text or "EVAL_FAILED" in text:
        log("EVAL_SPLIT_OK : %s" % _field(text, "EVAL_SPLIT_OK"))
        log("EVAL_CELL_A_C : %s" % _field(text, "EVAL_CELL arm=A cond=clean"))
        log("EVAL_CELL_A_S : %s" % _field(text, "EVAL_CELL arm=A cond=spray"))
        log("EVAL_CELL_B_C : %s" % _field(text, "EVAL_CELL arm=B cond=clean"))
        log("EVAL_CELL_B_S : %s" % _field(text, "EVAL_CELL arm=B cond=spray"))
        log("EVAL_OK       : %s" % _field(text, "EVAL_OK"))
        log("EVAL_FAILED   : %s" % _field(text, "EVAL_FAILED"))
    if not passed:
        log("last 30 lines of the %s run:" % task)
        log("\n".join(text.splitlines()[-30:]))
    return 0 if passed else 1


def _field(text, prefix):
    """Return the last line starting with ``prefix``, if any."""
    found = None
    for line in text.splitlines():
        if line.startswith(prefix):
            found = line
    return found


if __name__ == "__main__":
    sys.exit(main())
