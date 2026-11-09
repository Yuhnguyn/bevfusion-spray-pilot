#!/usr/bin/env python3
"""Script kernel: run the ticket 11-b smoke run on the pinned vendor stack.

The boot steps are not re-implemented here. ``kaggle/e2e/main.py`` already
extracts the code dataset, clones ``mit/bevfusion`` at the pin, builds the
Python 3.8 venv, compiles the mmdet3d CUDA extensions and verifies the stack;
this kernel imports that module and calls its functions, installs
``nuscenes-devkit`` into the venv (the mini split builder needs the real
devkit), then runs ``kaggle/train/smoke.py`` inside that venv.

``TASK`` names the script under ``kaggle/train`` that is executed; the smoke
run prints ``SMOKE_DEVKIT_OK`` / ``MINI_SPLIT_OK`` / ``SMOKE_STEP`` /
``SMOKE_OK`` so the evidence can be grepped out of the kernel log.
"""

import importlib.util
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from devkit_deps import devkit_packages

TASK = "smoke"
TASK_SCRIPT = "kaggle/train/%s.py" % TASK
DEVKIT_PINS = ("1.1.11", "1.1.10")

# The dataset mount layout has been both /kaggle/input/<slug> and
# /kaggle/input/datasets/<owner>/<slug>; rglob finds the boot module in either.
BOOT = next(pathlib.Path("/kaggle/input").rglob("kaggle/e2e/main.py"))


def log(*parts):
    print(*parts, flush=True)


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

    rc, text = e2e.stream(
        [str(e2e.PY), TASK_SCRIPT],
        cwd=e2e.REPO,
        timeout=10800,
        log_name="%s.log" % TASK,
    )

    passed = rc == 0 and "SMOKE_OK" in text
    log("")
    log("=" * 72)
    log("task          : %s (%s)" % (TASK, TASK_SCRIPT))
    log("devkit        : %s" % version)
    log("mini split    : %s" % _field(text, "MINI_SPLIT_OK"))
    log("smoke rc      : %d" % rc)
    log("smoke verdict : %s" % ("SMOKE_OK" if passed else "SMOKE_FAILED"))
    if not passed:
        log("last 30 lines of the smoke run:")
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
