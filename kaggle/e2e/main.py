#!/usr/bin/env python3
"""Script kernel: run the spray pilot test suite on the pinned vendor stack.

Pipeline (mirrors the proven ``kaggle/smoke_test`` recipe):

1. extract ``code.tar`` from the private dataset
   ``nguynhuy9669/bevfusion-spray-pilot-code`` into ``/kaggle/working/repo``;
2. clone ``mit-han-lab/bevfusion`` into ``repo/mit/bevfusion``, check out the
   pin ``da93b27`` and assert the checkout really is that commit;
3. build the pinned Python 3.8 venv: torch 1.10.1+cu113, mmcv-full 1.4.0,
   mmdet 2.20.0, numpy 1.22.4, numba 0.58.1;
4. pick a CUDA 11.x ``nvcc`` (plus gcc-11) and compile the mmdet3d CUDA
   extensions with ``python setup.py develop``;
5. verify that mmcv / mmdet / mmdet3d / mmdet3d.ops import;
6. run ``pytest -q tests/`` and fail the kernel when it fails.

The venv and caches live in ``/root/bevfusion_e2e`` so they are not uploaded
with the kernel version. Nothing here downloads a checkpoint.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

DATASET_MOUNT = Path("/kaggle/input/bevfusion-spray-pilot-code")
WORK = Path("/kaggle/working")
REPO = WORK / "repo"
SCRATCH = Path("/root/bevfusion_e2e")
VENV = SCRATCH / "env"
PY = VENV / "bin" / "python"
LOGS = SCRATCH / "logs"

REPO_URL = "https://github.com/mit-han-lab/bevfusion.git"
PIN_SHORT = "da93b27"
PIN_FULL = "da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea"
MIT = REPO / "mit" / "bevfusion"

PINNED_PROBE = "1.10.1+cu113 1.4.0 2.20.0"
GPU_PYTHON = sys.executable

CUDA_KEYRING = Path("/usr/share/keyrings/cuda-archive-keyring.gpg")
CUDA_SOURCE_LIST = Path("/etc/apt/sources.list.d/cuda-ubuntu2204.list")
CUDA_REPO_2204 = (
    "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/"
)

BUILD_WRAPPER = '''"""Compile the pinned mmdet3d CUDA extensions (setup.py develop)."""

import os
import runpy
import sys

repo = os.environ["REPO"]

if os.environ.get("SMOKE_BYPASS_CUDA_GUARD") == "1":
    import torch.utils.cpp_extension as cpp

    def _bypassed(self):
        print(
            "[smoke] WARNING: torch CUDA major-version guard bypassed "
            "(nvcc major != torch.version.cuda major). Documented deviation."
        )

    cpp.BuildExtension._check_cuda_version = _bypassed

os.chdir(repo)
sys.argv = ["setup.py", "develop"]
runpy.run_path(os.path.join(repo, "setup.py"), run_name="__main__")
'''

OPS_CHECK = '''"""Check every compiled mmdet3d extension, and run two GPU micro-smokes."""

import json
import traceback

EXTENSIONS = [
    "mmdet3d.ops.bev_pool.bev_pool_ext",
    "mmdet3d.ops.voxel.voxel_layer",
    "mmdet3d.ops.iou3d.iou3d_cuda",
    "mmdet3d.ops.roiaware_pool3d.roiaware_pool3d_ext",
    "mmdet3d.ops.ball_query.ball_query_ext",
    "mmdet3d.ops.knn.knn_ext",
    "mmdet3d.ops.paconv.assign_score_withk_ext",
    "mmdet3d.ops.group_points.group_points_ext",
    "mmdet3d.ops.interpolate.interpolate_ext",
    "mmdet3d.ops.furthest_point_sample.furthest_point_sample_ext",
    "mmdet3d.ops.gather_points.gather_points_ext",
    "mmdet3d.ops.spconv.sparse_conv_ext",
]

report = {"extensions": {}, "package_import": None, "gpu_smoke": {}}

try:
    import mmdet3d

    report["mmdet3d_path"] = mmdet3d.__file__
except Exception as exc:  # noqa: BLE001
    report["mmdet3d_path"] = "IMPORT FAILED: " + repr(exc)

for name in EXTENSIONS:
    try:
        __import__(name)
        report["extensions"][name] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        report["extensions"][name] = {
            "ok": False,
            "error": repr(exc)[:1500],
            "traceback": traceback.format_exc()[-1500:],
        }

try:
    import mmdet3d.ops as ops

    report["package_import"] = {"ok": True}
    report["symbols"] = {
        "bev_pool": hasattr(ops, "bev_pool"),
        "Voxelization": hasattr(ops, "Voxelization"),
        "SparseBasicBlock": hasattr(ops, "SparseBasicBlock"),
    }
except Exception as exc:  # noqa: BLE001
    report["package_import"] = {"ok": False, "error": repr(exc)[:2000]}

if report["package_import"].get("ok"):
    import torch
    from mmdet3d.ops import Voxelization, bev_pool

    device = "cuda"
    try:
        torch.manual_seed(0)
        feats = torch.rand(64, 4, device=device)
        coords = torch.stack(
            [
                torch.randint(0, 8, (64,), device=device),
                torch.randint(0, 8, (64,), device=device),
                torch.randint(0, 4, (64,), device=device),
                torch.zeros(64, device=device, dtype=torch.long),
            ],
            dim=1,
        ).long()
        out = bev_pool(feats, coords, 1, 4, 8, 8)
        report["gpu_smoke"]["bev_pool"] = {
            "ok": True,
            "shape": list(out.shape),
            "finite": bool(torch.isfinite(out).all()),
        }
    except Exception as exc:  # noqa: BLE001
        report["gpu_smoke"]["bev_pool"] = {"ok": False, "error": repr(exc)[:2000]}

    try:
        torch.manual_seed(0)
        points = torch.rand(50000, 5, device=device)
        points[:, 0] = points[:, 0] * 108.0 - 54.0
        points[:, 1] = points[:, 1] * 108.0 - 54.0
        points[:, 2] = points[:, 2] * 8.0 - 5.0
        voxelize = Voxelization(
            voxel_size=[0.075, 0.075, 0.2],
            point_cloud_range=[-54.0, -54.0, -5.0, 54.0, 54.0, 3.0],
            max_num_points=10,
            max_voxels=[120000, 160000],
        ).to(device)
        feats, coords, counts = voxelize(points)
        report["gpu_smoke"]["voxelize"] = {
            "ok": True,
            "voxels": int(feats.shape[0]),
            "feat_shape": list(feats.shape),
            "coord_shape": list(coords.shape),
            "counts_shape": list(counts.shape),
        }
    except Exception as exc:  # noqa: BLE001
        report["gpu_smoke"]["voxelize"] = {"ok": False, "error": repr(exc)[:2000]}

report["ok"] = bool(
    report["package_import"].get("ok")
    and all(item.get("ok") for item in report["extensions"].values())
    and all(item.get("ok") for item in report["gpu_smoke"].values())
)

print(json.dumps(report, indent=2, sort_keys=True))
print("OPS_OK" if report["ok"] else "OPS_FAILED")
'''

_LINES = []


def log(*parts):
    print(*parts, flush=True)


def _remember(line):
    _LINES.append(line)
    if len(_LINES) > 6000:
        del _LINES[:3000]


def tail(count=40):
    return "\n".join(_LINES[-count:])


def stream(cmd, cwd=None, env=None, timeout=None, log_name=None):
    """Run a command, echo its output live, return (rc, text)."""
    printable = " ".join(str(part) for part in cmd)
    log("$ " + printable)
    handle = None
    if log_name:
        LOGS.mkdir(parents=True, exist_ok=True)
        handle = open(LOGS / log_name, "a")
        handle.write("\n$ " + printable + "\n")
        handle.flush()
    started = time.time()
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
            if handle:
                handle.write(line + "\n")
                handle.flush()
            print(line, flush=True)
    finally:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log("[timeout after %ss]" % timeout)
        if handle:
            handle.close()
    log("[exit=%s in %.1fs]" % (proc.returncode, time.time() - started))
    return proc.returncode, "\n".join(lines)


def shell(command, timeout=None, log_name=None):
    return stream(["bash", "-c", command], timeout=timeout, log_name=log_name)


def capture(cmd, cwd=None, env=None, timeout=600):
    """Run a command and return combined output; never raises."""
    try:
        done = subprocess.run(
            [str(part) for part in cmd],
            cwd=None if cwd is None else str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        return done.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - diagnostic helper
        return "ERROR: %r" % (exc,)


def fail(step, detail):
    log("")
    log("E2E_FAILED step=%s" % step)
    log(detail)
    sys.exit(1)


# --------------------------------------------------------------- step 1: code
def find_mount():
    # Kaggle has used both layouts: /kaggle/input/<slug> and the owner-nested
    # /kaggle/input/datasets/<owner>/<slug>. Fall back to locating the repo by
    # its marker files so a layout change cannot sink the run.
    candidates = [
        Path("/kaggle/input/datasets/nguynhuy9669/bevfusion-spray-pilot-code"),
        DATASET_MOUNT,
    ]
    for candidate in candidates:
        if (candidate / "pytest.ini").is_file():
            return candidate

    for marker in sorted(Path("/kaggle/input").rglob("pytest.ini")):
        root = marker.parent
        if (root / "spray").is_dir() and (root / "tests").is_dir():
            return root

    log("input tree:")
    for path in sorted(Path("/kaggle/input").rglob("*")):
        depth = len(path.relative_to("/kaggle/input").parts)
        if depth <= 3:
            log("  " * depth + path.name)
    fail("extract", "dataset mount not found: %s" % DATASET_MOUNT)


def extract_code():
    mount = find_mount()
    log("[1/7] code dataset:", mount)
    log("mount contents:", sorted(entry.name for entry in mount.iterdir()))

    if REPO.exists():
        shutil.rmtree(REPO)
    REPO.mkdir(parents=True)

    tars = sorted(mount.glob("*.tar")) + sorted(mount.glob("*.tar.gz")) + sorted(
        mount.glob("*.tgz")
    )
    zips = sorted(mount.glob("*.zip"))
    if tars:
        for path in tars:
            log("extracting", path.name)
            with tarfile.open(path, "r:*") as archive:
                try:
                    archive.extractall(REPO, filter="fully_trusted")
                except TypeError:  # Python < 3.12 has no extraction filter
                    archive.extractall(REPO)
    elif zips:
        for path in zips:
            log("extracting", path.name)
            with zipfile.ZipFile(path) as archive:
                archive.extractall(REPO)
    else:
        log("no archive found; copying the mounted tree")
        for entry in mount.iterdir():
            target = REPO / entry.name
            if entry.is_dir():
                shutil.copytree(entry, target)
            else:
                shutil.copy2(entry, target)

    required = ("pytest.ini", "spray", "tests", "proxy_eval")
    missing = [name for name in required if not (REPO / name).exists()]
    if missing:
        fail("extract", "repo is missing %s after extract" % missing)

    # Dataset mounts are read-only; make the working copy writable so pytest
    # and the vendored build can write caches next to the sources.
    for path in [REPO, *REPO.rglob("*")]:
        try:
            mode = path.stat().st_mode
            path.chmod(mode | 0o200 | (0o100 if path.is_dir() else 0))
        except OSError:
            pass

    count = sum(1 for path in REPO.rglob("*") if path.is_file())
    log("extracted %d files into %s" % (count, REPO))


# -------------------------------------------------------------- step 2: clone
def clone_pin():
    log("")
    log("[2/7] vendor clone @", PIN_SHORT)
    MIT.parent.mkdir(parents=True, exist_ok=True)
    if not (MIT / ".git").is_dir():
        rc, _ = stream(["git", "clone", "--quiet", REPO_URL, MIT], timeout=1800)
        if rc != 0:
            fail("clone", "git clone failed (rc=%d)" % rc)
    else:
        log("clone already present:", MIT)

    rc, _ = stream(["git", "-C", MIT, "checkout", "--quiet", PIN_SHORT])
    if rc != 0:
        fail("clone", "git checkout %s failed (rc=%d)" % (PIN_SHORT, rc))

    short = capture(["git", "-C", MIT, "rev-parse", "--short", "HEAD"])
    full = capture(["git", "-C", MIT, "rev-parse", "HEAD"])
    subject = capture(["git", "-C", MIT, "log", "-1", "--format=%ci %s"])
    dirty = capture(["git", "-C", MIT, "status", "--porcelain"])
    log("mit/bevfusion HEAD: %s (%s)" % (short, full))
    log("commit: %s" % subject)
    if short != PIN_SHORT:
        fail("pin", "expected %s, got %r" % (PIN_SHORT, short))
    if full != PIN_FULL:
        fail("pin", "expected full sha %s, got %r" % (PIN_FULL, full))
    if dirty:
        fail("pin", "pinned clone is dirty:\n" + dirty)
    log("MIT_PIN_OK %s %s" % (PIN_SHORT, full))


# ---------------------------------------------------------- step 3: pinned env
def uv_prefix():
    exe = shutil.which("uv")
    if exe:
        return [exe]
    sibling = Path(GPU_PYTHON).parent / "uv"
    if sibling.is_file():
        return [str(sibling)]
    return [GPU_PYTHON, "-m", "uv"]


def pip_into_env(*packages, extra=None):
    cmd = uv_prefix() + ["pip", "install", "--python", str(PY)]
    if extra:
        cmd += extra
    return stream(cmd + list(packages), timeout=3600)


def install_env():
    log("")
    log("[3/7] pinned Python 3.8 venv")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    if shutil.which("uv") is None:
        rc, _ = stream(
            [GPU_PYTHON, "-m", "pip", "install", "-q", "uv"], timeout=900
        )
        if rc != 0:
            fail("env", "pip install uv failed (rc=%d)" % rc)
    uv = uv_prefix()
    log("uv:", " ".join(uv))

    # 3.8.20 is what uv's python-build-standalone channel provides for cp38.
    rc, _ = stream(uv + ["python", "install", "3.8.20"], timeout=1800)
    if rc != 0:
        fail("env", "uv python install 3.8.20 failed (rc=%d)" % rc)
    rc, _ = stream(
        uv + ["venv", "--python", "3.8.20", str(VENV)], timeout=900
    )

    version = capture([str(PY), "-c", "import sys; print(sys.version.split()[0])"])
    if not version.startswith("3.8"):
        # Fallback: let uv resolve any 3.8 it has.
        rc, _ = stream(uv + ["venv", "--python", "3.8", str(VENV)], timeout=900)
        version = capture(
            [str(PY), "-c", "import sys; print(sys.version.split()[0])"]
        )
    log("venv python:", version)
    if not version.startswith("3.8"):
        fail("env", "venv is not Python 3.8: %r" % version)

    steps = [
        ("setuptools",
         ["setuptools==59.5.0", "wheel", "packaging==21.3", "ninja"],
         None),
        ("torch",
         ["torch==1.10.1+cu113", "torchvision==0.11.2+cu113", "numpy==1.22.4"],
         ["--index-url", "https://download.pytorch.org/whl/cu113",
          "--extra-index-url", "https://pypi.org/simple",
          "--index-strategy", "unsafe-best-match"]),
        ("mmcv-full",
         ["mmcv-full==1.4.0"],
         ["-f", "https://download.openmmlab.com/mmcv/dist/cu113/torch1.10.0/index.html"]),
        ("mmdet",
         ["mmdet==2.20.0", "matplotlib", "terminaltables", "pycocotools",
          "six", "scipy", "pyyaml", "numpy==1.22.4", "numba==0.58.1"],
         None),
        ("pytest", ["pytest"], None),
    ]
    for name, packages, extra in steps:
        rc, text = pip_into_env(*packages, extra=extra)
        if rc != 0:
            fail("env:" + name, "pip install failed (rc=%d):\n%s" % (rc, text[-4000:]))

    probe = capture(
        [str(PY), "-c",
         "import torch, mmcv, mmdet; "
         "print(torch.__version__, mmcv.__version__, mmdet.__version__)"]
    )
    log("pinned probe:", probe)
    if probe != PINNED_PROBE:
        fail("env", "pinned versions mismatch: expected %r, got %r"
             % (PINNED_PROBE, probe))
    log("PINNED_WHEELS_OK %s" % PINNED_PROBE)


# ------------------------------------------------------- step 4: cuda toolchain
def nvcc_release(nvcc):
    raw = capture([str(nvcc), "--version"])
    match = re.search(r"release (\d+\.\d+)", raw)
    return match.group(1) if match else None


def discover_toolkits():
    bases = set()
    for line in capture(["bash", "-c", "ls -d /usr/local/cuda* 2>/dev/null"]).splitlines():
        bases.add(line.strip())
    for nvcc in Path("/usr/local").glob("cuda*/bin/nvcc"):
        bases.add(str(nvcc.parent.parent))
    which = shutil.which("nvcc")
    if which:
        bases.add(str(Path(which).parent.parent))

    found = []
    for base in sorted(b for b in bases if b):
        nvcc = Path(base) / "bin" / "nvcc"
        if not nvcc.is_file():
            continue
        found.append(
            {
                "path": base,
                "nvcc": str(nvcc),
                "release": nvcc_release(nvcc),
                "cudart_header": (Path(base) / "include" / "cuda_runtime.h").is_file(),
            }
        )
    return found


def install_cuda_11_8():
    if not CUDA_KEYRING.is_file():
        shell(
            "curl -fsSL %s3bf863cc.pub | gpg --dearmor -o %s"
            % (CUDA_REPO_2204, CUDA_KEYRING),
            timeout=600,
        )
    CUDA_SOURCE_LIST.write_text(
        "deb [signed-by=%s] %s /\n" % (CUDA_KEYRING, CUDA_REPO_2204)
    )
    shell("apt-get update -qq", timeout=1200, log_name="apt.log")
    log("apt policy:", capture(
        ["bash", "-c", "apt-cache policy cuda-nvcc-11-8 | head -6"]
    ))
    rc, _ = shell(
        "apt-get install -y -qq --no-install-recommends "
        "cuda-nvcc-11-8 cuda-cudart-dev-11-8",
        timeout=3600,
        log_name="apt.log",
    )
    log("cuda-nvcc install rc=%d" % rc)
    # CUDA 11.8 developer libraries live under lib*-dev-11-8 in NVIDIA's repo.
    # Installed separately so a rename in that repo cannot sink the toolkit.
    rc_libs, _ = shell(
        "apt-get install -y -qq --no-install-recommends "
        "libcusparse-dev-11-8 libcublas-dev-11-8 libcurand-dev-11-8",
        timeout=3600,
        log_name="apt.log",
    )
    log("cuda libs install rc=%d" % rc_libs)
    # cusolverDn.h is pulled in by ATen/cuda/CUDAContext.h (spconv .cc files).
    rc_solver, _ = shell(
        "apt-get install -y -qq --no-install-recommends libcusolver-dev-11-8",
        timeout=3600,
        log_name="apt.log",
    )
    log("cuda cusolver install rc=%d" % rc_solver)


def cuda_11_candidates():
    candidates = []
    for base in sorted(Path("/usr/local").glob("cuda-11*")):
        nvcc = base / "bin" / "nvcc"
        if not nvcc.is_file():
            continue
        candidates.append(
            {
                "path": str(base),
                "nvcc": str(nvcc),
                "release": nvcc_release(nvcc),
                "cudart_header": (base / "include" / "cuda_runtime.h").is_file(),
            }
        )
    return candidates


def choose_toolchain():
    log("")
    log("[4/7] CUDA 11.x toolchain (torch 1.10.1 requires nvcc 11.3-compatible)")
    initial = discover_toolkits()
    log("toolkits on disk:", json.dumps(initial, indent=2))

    chosen = None
    for toolkit in initial:
        if (toolkit["release"] or "").startswith("11."):
            toolkit["strategy"] = "existing-11x"
            chosen = toolkit
            break

    if chosen is None:
        install_cuda_11_8()
        candidates = cuda_11_candidates()
        log("cuda-11 candidates after apt:", json.dumps(candidates, indent=2))
        for toolkit in candidates:
            if (toolkit["release"] or "").startswith("11."):
                toolkit["strategy"] = "apt-ubuntu2204-cuda-11-8"
                chosen = toolkit
                break

    bypass = False
    if chosen is None:
        toolkits = discover_toolkits()
        if toolkits:
            chosen = sorted(toolkits, key=lambda item: item["release"] or "0")[-1]
            chosen["strategy"] = "system-nvcc-with-guard-bypass"
            bypass = True

    if chosen is None:
        fail("toolchain", "no nvcc found on the image")

    if not any(shutil.which(c) for c in ("gcc-11", "gcc-10", "gcc-9")):
        shell(
            "apt-get install -y -qq --no-install-recommends gcc-11 g++-11",
            timeout=1800,
            log_name="apt.log",
        )

    cc = cxx = None
    for candidate in ("gcc-11", "gcc-10", "gcc-9", "gcc-12", "gcc-13"):
        path = shutil.which(candidate)
        if path:
            cc = path
            cxx = shutil.which(candidate.replace("gcc", "g++"))
            break

    chosen["bypass_cuda_guard"] = bypass
    chosen["cc"] = cc
    chosen["cxx"] = cxx
    log("chosen toolchain:", json.dumps(chosen, indent=2))
    log("cuda guard bypass:", bypass)
    return chosen


# ----------------------------------------------------------- step 5: build ops
def build_ops(toolchain):
    log("")
    log("[5/7] compile mmdet3d CUDA ops")

    before = capture([str(PY), "-c", "import mmdet3d.ops"])
    skipped = "Error" not in before and "Traceback" not in before
    log("mmdet3d.ops import before:", "already importable" if skipped else before[-2000:])

    arch = capture(
        [str(PY), "-c",
         "import torch; a = torch.cuda.get_device_capability(0);"
         " print(str(a[0]) + chr(46) + str(a[1]))"]
    ).strip()
    if not arch or "." not in arch or arch.startswith("ERROR"):
        arch = "7.5"
    log("TORCH_CUDA_ARCH_LIST =", arch)
    log(
        "gpu:",
        capture(
            ["nvidia-smi", "--query-gpu=index,name,compute_cap",
             "--format=csv,noheader"]
        ),
    )

    build_rc = None
    if not skipped:
        env = dict(os.environ)
        env.update(
            {
                "REPO": str(MIT),
                "CUDA_HOME": toolchain["path"],
                "PATH": toolchain["path"] + "/bin:" + env.get("PATH", ""),
                "FORCE_CUDA": "1",
                "MAX_JOBS": str(max(1, min(4, os.cpu_count() or 2))),
                "TORCH_CUDA_ARCH_LIST": arch,
                "TORCH_EXTENSIONS_DIR": str(SCRATCH / "torch_extensions"),
                # torch 1.10 predates newer libstdc++/gcc: add the headers that
                # newer <limits>/<cstdint> users assume, and let nvcc accept a
                # newer host gcc.
                "CXXFLAGS": "-O2 -include limits -include cstdint",
                "NVCC_PREPEND_FLAGS": (
                    "--allow-unsupported-compiler -include limits -include cstdint"
                ),
            }
        )
        if toolchain.get("cc"):
            env["CC"] = toolchain["cc"]
        if toolchain.get("cxx"):
            env["CXX"] = toolchain["cxx"]
        if toolchain.get("bypass_cuda_guard"):
            env["SMOKE_BYPASS_CUDA_GUARD"] = "1"

        log("nvcc:", capture([toolchain["path"] + "/bin/nvcc", "--version"]))
        wrapper = SCRATCH / "build_ops.py"
        wrapper.write_text(BUILD_WRAPPER)
        build_rc, _ = stream(
            [str(PY), str(wrapper)],
            cwd=MIT,
            env=env,
            timeout=7200,
            log_name="build_ops.log",
        )
        build_log = LOGS / "build_ops.log"
        if build_rc != 0 and build_log.is_file():
            log("BUILD LOG TAIL:")
            log("\n".join(build_log.read_text().splitlines()[-120:]))

    check = SCRATCH / "check_ops.py"
    check.write_text(OPS_CHECK)
    rc, text = stream(
        [str(PY), str(check)], timeout=1800, log_name="check_ops.log"
    )
    ok = "OPS_OK" in text
    if not ok:
        log("ops check failed (rc=%d):" % rc)
        log(text[-4000:])
    return ok, {"arch": arch, "build_rc": build_rc, "build_skipped": skipped}


def verify_stack():
    log("")
    log("[6/7] stack import check")
    probe = capture(
        [str(PY), "-c",
         "import torch, mmcv, mmdet, mmdet3d; "
         "print('STACK_OK', torch.__version__, mmcv.__version__, "
         "mmdet.__version__, getattr(mmdet3d, '__version__', 'n/a'))"]
    )
    log(probe[-4000:])
    return "STACK_OK" in probe, probe


# --------------------------------------------------------------- step 6: tests
def run_tests():
    log("")
    log("[7/7] pytest -q tests/ in", REPO)
    rc, text = stream(
        [str(PY), "-m", "pytest", "-q", "tests/"],
        cwd=REPO,
        timeout=3600,
        log_name="pytest.log",
    )
    log("")
    log("pytest tail:")
    log("\n".join(text.splitlines()[-20:]))

    match = re.search(r"(\d+) passed", text)
    passed = int(match.group(1)) if match else 0
    failed = re.search(r"(\d+) failed", text)
    errors = re.search(r"(\d+) error", text)
    log(
        "pytest summary: rc=%d passed=%d failed=%s errors=%s"
        % (
            rc,
            passed,
            failed.group(1) if failed else "0",
            errors.group(1) if errors else "0",
        )
    )
    return rc, passed, text


def main():
    started = time.time()
    log("kernel run type:", os.environ.get("KAGGLE_KERNEL_RUN_TYPE"))
    log("cwd:", os.getcwd())

    extract_code()
    clone_pin()
    install_env()
    toolchain = choose_toolchain()

    stack_ok, ops_report = build_ops(toolchain)
    log("build report:", json.dumps(ops_report))

    import_ok, probe = verify_stack()
    stack_ok = stack_ok and import_ok
    log("STACK_OK" if stack_ok else "STACK_FAILED")

    # Build artifacts are not needed at runtime; keep the kernel output small.
    # The extensions were installed in place by `setup.py develop`, after the
    # import check above.
    build_dir = MIT / "build"
    if build_dir.is_dir():
        shutil.rmtree(build_dir, ignore_errors=True)
        log("removed build artifacts:", build_dir)

    rc, passed, _ = run_tests()
    tests_ok = rc == 0

    log("")
    log("=" * 72)
    log("mit/bevfusion : %s (%s)" % (PIN_SHORT, PIN_FULL))
    log("pinned stack  : %s" % ("OK" if stack_ok else "FAILED"))
    log("pytest        : %s (%d passed)" % ("PASSED" if tests_ok else "FAILED", passed))
    log("elapsed_s     : %.0f" % (time.time() - started))

    if tests_ok and stack_ok:
        log("PYTEST_PASSED %d" % passed)
        log("E2E_OK")
        return 0

    if not stack_ok:
        log("E2E_FAILED stack setup (see build/ops logs above)")
    else:
        log("E2E_FAILED pytest rc=%d" % rc)
    return 1


if __name__ == "__main__":
    sys.exit(main())
