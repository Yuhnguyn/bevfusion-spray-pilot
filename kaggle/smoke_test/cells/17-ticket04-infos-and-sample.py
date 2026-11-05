"""Ticket 04b: create nuScenes infos + load one sample through the MIT pipeline.

Run in the SAME Kaggle session as the smoke test: it reuses
/root/bevfusion_smoke/{env,bevfusion}. The input dataset is read-only, so we
build a writable symlink root at /kaggle/working/data/nuscenes and write the
infos there.

MAX_SCENES=3 keeps the gate fast; set 0 for the full 850-scene split.
"""

import glob
import json
import os
import subprocess
import time
from pathlib import Path

WORK = "/kaggle/working/smoke_test"
REPO = "/root/bevfusion_smoke/bevfusion"
PY = "/root/bevfusion_smoke/env/bin/python"
DATA = "/kaggle/working/data/nuscenes"
CONFIG = (
    REPO
    + "/configs/nuscenes/det/transfusion/secfpn/camera+lidar/swint_v0p075/convfuser.yaml"
)
MAX_SCENES = int(os.environ.get("MAX_SCENES", "3"))
ART = os.path.join(WORK, "artifacts")
SCRIPTS = os.path.join(WORK, "scripts")
os.makedirs(ART, exist_ok=True)
os.makedirs(SCRIPTS, exist_ok=True)


def run(args, env=None, cwd="/kaggle/working"):
    print("$", " ".join(args), flush=True)
    proc = subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd)
    print(proc.stdout[-4000:])
    if proc.returncode != 0:
        print(proc.stderr[-8000:])
        raise RuntimeError(f"rc={proc.returncode}: {args}")
    return proc


assert Path(PY).exists(), "venv missing: run the smoke-test setup cells first"
assert Path(REPO).exists(), "repo missing: run the clone/pin cell first"

# 1) writable dataset root with symlinks to the read-only mount
sources = sorted(glob.glob("/kaggle/input/datasets/*/nuscenes-v1-0-full-keyframes"))
sources += sorted(glob.glob("/kaggle/input/nuscenes-v1-0-full-keyframes"))
assert sources, "nuScenes dataset mount not found"
SRC = sources[0]
Path(DATA).mkdir(parents=True, exist_ok=True)
for name in ("v1.0-trainval", "samples", "maps", "LICENSE"):
    src, dst = Path(SRC) / name, Path(DATA) / name
    if src.exists() and not dst.exists():
        os.symlink(src, dst)
json.dump(
    {"source": SRC, "root": DATA, "entries": sorted(p.name for p in Path(DATA).iterdir())},
    open(os.path.join(ART, "dataset_layout.json"), "w"),
    indent=1,
)

# 2) devkit inside the pinned Python 3.8 venv; keep numpy at 1.22.4
run(["uv", "pip", "install", "--python", PY, "nuscenes-devkit==1.1.11"])
run(
    [
        "uv",
        "pip",
        "install",
        "--python",
        PY,
        "--no-deps",
        "--force-reinstall",
        "numpy==1.22.4",
    ]
)
run(
    [
        PY,
        "-c",
        "import numpy, nuscenes, shapely, torch; "
        "print('devkit ok', numpy.__version__, shapely.__version__, torch.__version__)",
    ]
)

# 3) infos (subset for the gate; MAX_SCENES=0 writes the full split)
STEP_INFOS = r'''import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.environ["REPO"])
from nuscenes.utils import splits  # noqa: E402
from tools.data_converter import nuscenes_converter as nc  # noqa: E402

max_scenes = int(os.environ.get("MAX_SCENES", "0"))
if max_scenes > 0:
    splits.train = splits.train[:max_scenes]
    splits.val = splits.val[:max_scenes]

data_root = os.environ["DATA"]
started = time.time()
nc.create_nuscenes_infos(data_root, "nuscenes", version="v1.0-trainval", max_sweeps=0)

import mmcv  # noqa: E402

report = {"data_root": data_root, "max_scenes": max_scenes, "max_sweeps": 0}
for split in ("train", "val"):
    path = Path(data_root) / f"nuscenes_infos_{split}.pkl"
    payload = mmcv.load(str(path))
    infos = payload["infos"]
    sample = infos[0] if infos else {}
    report[split] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "num_infos": len(infos),
        "metadata": payload.get("metadata"),
        "first": {
            "token": sample.get("token"),
            "lidar_path": sample.get("lidar_path"),
            "num_cams": len(sample.get("cams", {})),
            "num_sweeps": len(sample.get("sweeps", [])),
            "num_gt": int(len(sample.get("gt_boxes", []))),
        },
    }
report["seconds"] = round(time.time() - started, 1)
Path(os.environ["WORK"], "artifacts", "infos.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
'''
Path(SCRIPTS, "step_infos.py").write_text(STEP_INFOS)
env = dict(os.environ, REPO=REPO, DATA=DATA, MAX_SCENES=str(MAX_SCENES), WORK=WORK)
t0 = time.time()
run([PY, os.path.join(SCRIPTS, "step_infos.py")], env=env)
print(f"infos done in {time.time() - t0:.1f}s")

# 4) one sample through the val pipeline + velocity eligibility counts
STEP_SAMPLE = r'''import json
import os
import sys
import time

os.chdir("/kaggle/working")
sys.path.insert(0, os.environ["WORK"])
sys.path.insert(0, os.path.join(os.environ["WORK"], "scripts"))

import numpy as np
from mmcv import ConfigDict
from mmcv.parallel import collate
from mmdet3d.datasets import build_dataset

import smoke_cfg

cfg, files = smoke_cfg.load(os.environ["CONFIG_PATH"])
dataset_cfg = ConfigDict(cfg["data"]["val"])
started = time.time()
dataset = build_dataset(dataset_cfg)
infos = dataset.data_infos
index = next(
    (i for i, info in enumerate(infos) if len(info.get("gt_boxes", [])) > 0),
    0,
)
data = dataset[index]


def unwrap(value):
    return value.data if hasattr(value, "data") else value


def shape_of(value):
    value = unwrap(value)
    return list(value.shape) if hasattr(value, "shape") else type(value).__name__


report = {}
try:
    batch = collate([data], samples_per_gpu=1)
    report["batch_shapes"] = {key: shape_of(value) for key, value in batch.items()}
    report["batch_keys"] = sorted(batch.keys())
except Exception as exc:  # noqa: BLE001 - keep the raw pipeline output as evidence
    report["collate_error"] = repr(exc)
    report["batch_shapes"] = {key: shape_of(value) for key, value in data.items()}
    report["batch_keys"] = sorted(data.keys())

info = infos[index]
gt_boxes = np.asarray(info.get("gt_boxes", []), dtype=float).reshape(-1, 7)
names = list(info.get("gt_names", []))
velocity = np.asarray(info.get("gt_velocity", []), dtype=float).reshape(-1, 2)
speed_kmh = np.linalg.norm(velocity, axis=1) * 3.6
finite = np.isfinite(velocity).all(axis=1)
vehicle = np.isin(
    names,
    ["car", "truck", "bus", "trailer", "construction_vehicle", "motorcycle", "bicycle"],
)
front = gt_boxes[:, 0] > 0
within_30m = np.linalg.norm(gt_boxes[:, :2], axis=1) <= 30.0
cam_paths = {key: value.get("data_path") for key, value in info.get("cams", {}).items()}
missing_paths = [path for path in cam_paths.values() if path and not os.path.exists(path)]

report.update(
    {
        "config_files": files,
        "num_infos": len(infos),
        "index": index,
        "token": info.get("token"),
        "lidar_path": info.get("lidar_path"),
        "num_cams": len(info.get("cams", {})),
        "num_sweeps": len(info.get("sweeps", [])),
        "num_gt": int(len(gt_boxes)),
        "missing_image_paths": missing_paths,
        "velocity": {
            "finite": int(finite.sum()),
            "vehicle_boxes": int(vehicle.sum()),
            "vehicle_finite": int((vehicle & finite).sum()),
            "speed_ge_30_kmh": int((vehicle & finite & (speed_kmh >= 30.0)).sum()),
            "speed_ge_50_kmh": int((vehicle & finite & (speed_kmh >= 50.0)).sum()),
            "speed_ge_50_front_30m": int(
                (vehicle & finite & (speed_kmh >= 50.0) & front & within_30m).sum()
            ),
            "max_speed_kmh": round(float(speed_kmh[finite].max()), 2)
            if finite.any()
            else None,
        },
        "seconds": round(time.time() - started, 2),
    }
)
path = os.path.join(os.environ["WORK"], "artifacts", "dataset_sample.json")
open(path, "w").write(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
'''
Path(SCRIPTS, "step_sample.py").write_text(STEP_SAMPLE)
run(
    [PY, os.path.join(SCRIPTS, "step_sample.py")],
    env=dict(os.environ, CONFIG_PATH=CONFIG, WORK=WORK),
)

print("TICKET04_OK")
