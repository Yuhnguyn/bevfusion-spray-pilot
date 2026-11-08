#!/usr/bin/env python3
"""Script kernel: run the ticket 10-ii probe on the pinned vendor stack.

The boot steps are not re-implemented here. ``kaggle/e2e/main.py`` already
extracts the code dataset, clones ``mit/bevfusion`` at the pin, builds the
Python 3.8 venv, compiles the mmdet3d CUDA extensions and verifies the stack;
this kernel imports that module and calls its functions, then runs
``kaggle/train/probe.py`` inside the venv it built.

Everything printed by the probe is prefixed ``PROBE_STEP`` / ``PROBE_OK`` /
``PROBE_FAILED`` so the evidence can be grepped out of the kernel log.
"""

import importlib.util
import pathlib
import sys

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

    rc, text = e2e.stream(
        [str(e2e.PY), "kaggle/train/probe.py"],
        cwd=e2e.REPO,
        timeout=3600,
        log_name="probe.log",
    )

    passed = rc == 0 and "PROBE_OK" in text
    log("")
    log("=" * 72)
    log("chosen config : %s" % _field(text, "cfg_leaf"))
    log("probe rc      : %d" % rc)
    log("probe verdict : %s" % ("PROBE_OK" if passed else "PROBE_FAILED"))
    if not passed:
        log("last 30 lines of the probe run:")
        log("\n".join(text.splitlines()[-30:]))
    return 0 if passed else 1


def _field(text, name):
    """Return the payload of the last ``PROBE_STEP <name> ...`` line, if any."""
    found = None
    prefix = "PROBE_STEP %s " % name
    for line in text.splitlines():
        if line.startswith(prefix):
            found = line[len(prefix):]
    return found


if __name__ == "__main__":
    sys.exit(main())
