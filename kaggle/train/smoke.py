"""Ticket 11-b smoke run: mini infos -> dataloader -> measured train steps.

Runs inside the pinned Python 3.8 venv that ``kaggle/e2e/main.py`` builds and
that ``kaggle/train/main.py`` boots (torch 1.10.1+cu113, mmcv-full 1.4.0,
mmdet 2.20.0, mmdet3d from da93b27) with ``nuscenes-devkit`` installed by the
kernel before this script starts.

Scope is deliberately narrow: no eval, no real training.  Arm A runs 5 steps,
arm B (spray enabled) 15 steps; the first 3 steps of each arm are warmup and
excluded from the mean.  Everything reusable is imported from ``probe.py``
(config chain resolution, model build, checkpoint load, freeze) instead of
being re-implemented here.

Log lines:

* ``SMOKE_STEP arm=<A|B> i=<i> loss=<f> s=<f>`` -- once per step;
* ``SMOKE_OK s_per_step=<f> peak_gb=<f> steps=<n>`` -- last line on success;
* ``SMOKE_FAILED ...`` -- on a non-finite loss, a missing batch key or a
  failed split, with a traceback and the last three batch entries.

``--sweeps-probe`` replaces the A/B arms with a v1.0-mini measurement of the
multi-sweep loader: ``SWEEPS_INFO``, ``SWEEPS_PTS``, ``SWEEPS_UNIQUE``,
``STEP_TIME``, then ``SWEEPS_OK`` or ``SWEEPS_FAILED``.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import subprocess
import sys
import time
import traceback
from importlib import metadata as importlib_metadata

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PROBE_PATH = REPO / "kaggle" / "train" / "probe.py"

DEFAULT_DATAROOT = (
    "/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes"
)
ALT_DATAROOT = "/kaggle/input/nuscenes-v1-0-full-keyframes"
MINI_DATAROOT = "/kaggle/input/nuscenes-mini"
MINI_PKL = pathlib.Path("/kaggle/working/mini_train_4000.pkl")
OUT_JSON = pathlib.Path("/kaggle/working/smoke.json")
# ``nuscenes.utils.splits`` writes ``val = \`` followed by the list on the next
# line, while ``spray.mini_split._read_list`` expects ``val = [`` on one line.
# Re-emit the installed devkit list in the shape the CLI parses instead of
# touching the pinned helper.
SPLITS_FILE = pathlib.Path("/kaggle/working/mini_splits.py")

DATASET_CONFIG = "mit/bevfusion/configs/nuscenes/default.yaml"

# [CHỌN] ticket 11-b: enough steps to average out warmup and allocator noise.
ARM_STEPS = {"A": 5, "B": 15}
WARMUP_STEPS = 3
BATCH = 2
# [CHỌN] ticket 20-b: the sweeps probe needs only a handful of samples to prove
# that the multi-sweep loader loads more than the keyframe, so the split is tiny.
SWEEPS_PROBE_N = 300
SWEEPS_MIN_MULTIPLIER = 2.0
SWEEPS_MIN_RATIO = 0.9
WORKERS = 4
SEED = 0
LR = 1e-4
WEIGHT_DECAY = 0.01
GRAD_CLIP = 5.0

# The smoke pipeline starts from the vendor train pipeline and swaps in the
# ablation slice from ``spray.ab_config``.  These steps cannot run against the
# mini split and are dropped:
#   ObjectPaste         -- needs nuscenes_dbinfos_train.pkl (not in the split);
#   LoadBEVSegmentation -- modality.use_map is false and the map expansion is
#                          incomplete, so a map branch is out of scope.
DROP_STEPS = frozenset({"ObjectPaste", "LoadBEVSegmentation"})


def log(*parts):
    print(*parts, flush=True)


def fail(reason, detail=None):
    log("SMOKE_FAILED %s" % reason)
    if detail:
        log(detail)
    sys.exit(1)


def load_probe():
    import importlib.util

    spec = importlib.util.spec_from_file_location("smoke_probe", str(PROBE_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def devkit_version():
    try:
        return importlib_metadata.version("nuscenes-devkit")
    except importlib_metadata.PackageNotFoundError:
        return None


# ------------------------------------------------------------ step 1: infos
def find_dataroot(explicit=None, version="v1.0-trainval"):
    if explicit:
        return pathlib.Path(explicit)
    for candidate in (DEFAULT_DATAROOT, ALT_DATAROOT, MINI_DATAROOT):
        root = pathlib.Path(candidate)
        if (root / version / "sample.json").is_file():
            return root
    for sample in sorted(pathlib.Path("/kaggle/input").rglob("%s/sample.json" % version)):
        return sample.parent.parent
    fail("dataroot", "no %s/sample.json under /kaggle/input" % version)


def ensure_splits_file(
    version="v1.0-trainval", dataroot=None, scene_names=None, path=None
):
    """Write the devkit ``val`` list in the CLI's parsable form.

    ``v1.0-mini`` has no official val split, so the last two sorted scenes stand
    in for it (enough to keep a couple of scenes out of the mini split).  Every
    other version keeps the official 150-scene ``val`` list.
    """
    target = pathlib.Path(path) if path is not None else SPLITS_FILE
    if version == "v1.0-mini":
        if scene_names is None:
            from nuscenes.nuscenes import NuScenes

            nusc = NuScenes(version=version, dataroot=str(dataroot), verbose=False)
            scene_names = [scene["name"] for scene in nusc.scene]
        names = sorted(scene_names)[-2:]
        if len(names) != 2:
            fail("splits", "expected 2 val scenes for %s, got %d" % (version, len(names)))
        body = "val = [\n%s]\n" % "".join("    %r,\n" % name for name in names)
        target.write_text(body)
        log("SWEEPS_SPLITS val=%d path=%s" % (len(names), target))
        return target

    from nuscenes.utils import splits

    names = sorted(set(splits.val))
    if len(names) != 150:
        fail("splits", "expected 150 val scenes, got %d" % len(names))
    body = "val = [\n%s]\n" % "".join("    %r,\n" % name for name in names)
    target.write_text(body)
    log("SMOKE_SPLITS_OK val=%d path=%s" % (len(names), target))
    return target


def run_mini_split(dataroot, version="v1.0-trainval", n=4000):
    splits_file = ensure_splits_file(version, dataroot)
    cmd = [
        sys.executable,
        "scripts/make_mini_split.py",
        "--dataroot",
        str(dataroot),
        "--out",
        str(MINI_PKL),
        "--n",
        str(n),
        "--seed",
        str(SEED),
        "--max-sweeps",
        "10",
        "--version",
        version,
        "--splits",
        str(splits_file),
    ]
    log("MINI_SPLIT_CMD %s" % " ".join(cmd))
    done = subprocess.run(
        cmd,
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    text = done.stdout or ""
    for line in text.splitlines():
        log(line)
    ok_line = None
    for line in text.splitlines():
        if line.startswith("MINI_SPLIT_OK"):
            ok_line = line
    if done.returncode != 0 or ok_line is None or "n=%d" % n not in ok_line:
        log("last 20 lines of the mini split run:")
        log("\n".join(text.splitlines()[-20:]))
        fail("mini_split", "rc=%d" % done.returncode)
    log(ok_line)
    return ok_line


# --------------------------------------------------------- step 2: pipeline
def _is_renamed(step_type):
    from spray.ab_config import RENAMED_STEPS

    return step_type in RENAMED_STEPS


def build_pipeline_steps(arm, vendor_pipeline):
    """Vendor train pipeline with the arm's shared slice put in place.

    ``spray.ab_config.train_pipeline`` is the augmentation/format slice only
    (loaders live in the vendor config), so each step whose type is in that
    slice is replaced in place.  That keeps loaders, ``ImageAug3D`` and
    ``ImageNormalize`` -- the camera branch needs a normalized fixed-size
    tensor -- while the ablation order is exactly the arm's.
    """
    from spray.ab_config import RENAMED_STEPS, build_cfg

    arm_steps = {
        step["type"]: copy.deepcopy(step)
        for step in build_cfg(arm)["train_pipeline"]
    }
    plume = arm_steps.pop("PlumeTransform", None)

    steps = []
    for step in vendor_pipeline:
        step_type = step["type"]
        if step_type in DROP_STEPS:
            continue
        if _is_renamed(step_type):
            replacement = copy.deepcopy(arm_steps[RENAMED_STEPS[step_type]])
            if replacement["type"] == "CleanPointsCollect3D":
                keys = [k for k in replacement["keys"] if k != "gt_masks_bev"]
                if arm == "B":
                    keys.append("spray_stats")
                replacement["keys"] = keys
            steps.append(replacement)
        elif step_type in arm_steps:
            steps.append(copy.deepcopy(arm_steps[step_type]))
            if step_type == "RandomFlip3D" and plume is not None:
                steps.append(copy.deepcopy(plume))
        else:
            steps.append(copy.deepcopy(step))
    return steps


def _valid_indices(dataset, point_cloud_range, limit):
    """First ``limit`` infos that survive the vendor range/name filters.

    ``NuScenesDataset.prepare_train_data`` returns ``None`` when the filtered
    GT is empty, and a ``None`` inside a collated batch is not handled by
    mmcv's collate.  This reproduces ``ObjectRangeFilter`` (BEV centre inside
    ``point_cloud_range``) plus ``ObjectNameFilter`` (name in ``CLASSES``) on
    the infos and keeps only samples that will produce a non-empty label
    tensor.
    """
    import numpy as np

    classes = frozenset(dataset.CLASSES)
    kept = []
    for index, info in enumerate(dataset.data_infos):
        mask = np.asarray(info["valid_flag"], dtype=bool)
        boxes = np.asarray(info["gt_boxes"])[mask]
        names = np.asarray(info["gt_names"])[mask]
        in_range = (
            (boxes[:, 0] > point_cloud_range[0])
            & (boxes[:, 1] > point_cloud_range[1])
            & (boxes[:, 0] < point_cloud_range[3])
            & (boxes[:, 1] < point_cloud_range[4])
        )
        if any(str(name) in classes for name in names[in_range]):
            kept.append(index)
            if len(kept) >= limit:
                break
    return kept


def _set_sweeps_num(pipeline, sweeps_num):
    for step in pipeline:
        if step["type"] == "LoadPointsFromMultiSweeps":
            step["sweeps_num"] = sweeps_num


def build_loader(arm, cfg, dataroot, sweeps_num=None):
    import torch
    from mmdet3d.datasets import build_dataloader, build_dataset

    dataset_cfg = copy.deepcopy(cfg["data"]["train"]["dataset"])
    dataset_cfg["ann_file"] = str(MINI_PKL)
    dataset_cfg["dataset_root"] = str(dataroot)
    dataset_cfg["pipeline"] = build_pipeline_steps(arm, cfg["data"]["train"]["dataset"]["pipeline"])
    if sweeps_num is not None:
        _set_sweeps_num(dataset_cfg["pipeline"], sweeps_num)
    dataset_cfg["test_mode"] = False

    dataset = build_dataset(dataset_cfg)
    need = ARM_STEPS[arm] * BATCH
    indices = _valid_indices(dataset, cfg["point_cloud_range"], need)
    if len(indices) < need:
        fail(
            "valid_indices",
            "arm %s needs %d non-empty samples, found %d" % (arm, need, len(indices)),
        )
    subset = torch.utils.data.Subset(dataset, indices)
    loader = build_dataloader(
        subset,
        samples_per_gpu=BATCH,
        workers_per_gpu=WORKERS,
        dist=False,
        shuffle=False,
        seed=SEED,
    )
    step_types = [step["type"] for step in dataset_cfg["pipeline"]]
    log(
        "SMOKE_INFO arm=%s dataset=%d selected=%d pipeline=%s"
        % (arm, len(dataset), len(indices), ",".join(step_types))
    )
    return loader, step_types


# ------------------------------------------------------------ step 3: model
def load_weights(probe, model, checkpoint):
    report, ok = probe.load_weights(model, checkpoint)
    if not ok:
        fail("ckpt_load", json.dumps(report, indent=2, default=str))


def prepare_model(probe, checkpoint, device):
    cfg, files, choice = probe.choose_model_config()
    model, build_info = probe.build(cfg)
    model = model.to(device)
    load_weights(probe, model, checkpoint)
    freeze_payload, ok = probe.freeze(model)
    if not ok:
        fail("freeze", json.dumps(freeze_payload, indent=2, default=str))
    return model, choice, freeze_payload


# ------------------------------------------------------------- step 4: loop
def dump_batch(batch):
    lines = []
    for key in sorted(batch):
        value = batch[key]
        shape = getattr(value, "shape", None)
        if shape is None:
            try:
                shape = (len(value),)
            except Exception:  # noqa: BLE001 - a dump helper must never raise
                shape = None
        dtype = getattr(value, "dtype", type(value).__name__)
        lines.append("%s shape=%s dtype=%s" % (key, shape, dtype))
    log("SMOKE_BATCH_DUMP")
    for line in lines[-3:]:
        log(line)


def _mean_points(batch):
    points = batch.get("points")
    if not isinstance(points, (list, tuple)) or not points:
        return None
    lengths = [len(item) for item in points]
    return sum(lengths) / float(len(lengths))


def _reduce_spray(stats):
    import torch

    reduced = {}
    for key, value in stats.items():
        if torch.is_tensor(value):
            value = value.detach().float()
            reduced[key] = float(value.mean().item()) if value.numel() else None
        elif isinstance(value, (int, float)):
            reduced[key] = float(value)
    return reduced


def run_arm(arm, model, loader, device_index, steps):
    import torch
    from mmcv.parallel import scatter

    model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    if not params:
        fail("optimizer", "arm %s has no trainable parameters" % arm)
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=WEIGHT_DECAY)

    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    record = {"times": [], "losses": [], "points": [], "spray": []}
    iterator = iter(loader)
    for index in range(steps):
        batch = scatter(next(iterator), [device_index])[0]
        torch.cuda.synchronize()

        started = time.perf_counter()
        try:
            losses = model(return_loss=True, **batch)
        except Exception:  # noqa: BLE001 - the traceback is the evidence
            log("SMOKE_FAILED forward arm=%s step=%d" % (arm, index))
            traceback.print_exc()
            dump_batch(batch)
            raise

        terms = [
            value
            for name, value in losses.items()
            if "loss" in name and torch.is_tensor(value)
        ]
        if not terms:
            log("SMOKE_FAILED no_loss arm=%s step=%d keys=%s"
                % (arm, index, sorted(losses)))
            dump_batch(batch)
            raise SystemExit(1)
        loss = sum(terms)
        if not torch.isfinite(loss):
            log("SMOKE_FAILED non_finite_step=%d arm=%s" % (index, arm))
            dump_batch(batch)
            raise SystemExit(1)

        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, GRAD_CLIP)
        optimizer.step()
        optimizer.zero_grad()
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started

        record["times"].append(elapsed)
        record["losses"].append(float(loss.item()))
        points = _mean_points(batch)
        if points is not None:
            record["points"].append(points)
        if "spray_stats" in batch:
            record["spray"].append(_reduce_spray(batch["spray_stats"]))

        log(
            "SMOKE_STEP arm=%s i=%d loss=%.6f s=%.4f"
            % (arm, index, record["losses"][-1], elapsed)
        )

    measured = record["times"][WARMUP_STEPS:] or record["times"]
    record["s_per_step"] = sum(measured) / float(len(measured))
    record["peak_gb"] = torch.cuda.max_memory_allocated() / float(1 << 30)
    record["loss_first"] = record["losses"][0]
    record["loss_last"] = record["losses"][-1]
    record["n_points_after_pipeline"] = (
        sum(record["points"]) / float(len(record["points"]))
        if record["points"]
        else None
    )
    if record["spray"]:
        keys = set()
        for item in record["spray"]:
            keys.update(item)
        record["spray_stats"] = {
            key: sum(
                item[key]
                for item in record["spray"]
                if item.get(key) is not None
            )
            / float(sum(1 for item in record["spray"] if item.get(key) is not None))
            for key in sorted(keys)
        }
    else:
        record["spray_stats"] = None
    return record


# ------------------------------------------------------- step 5: sweeps probe
def build_points_pipeline(cfg, sweeps_num=None):
    """Config's LiDAR loader steps only -- enough to count loaded points.

    The camera branch and the augmentation/format steps are irrelevant for this
    measurement, so only ``LoadPointsFromFile`` and ``LoadPointsFromMultiSweeps``
    are instantiated.  ``sweeps_num=None`` keeps the config value (9).
    """
    from mmdet3d.datasets.pipelines import Compose

    steps = []
    for step in build_pipeline_steps("A", cfg["data"]["train"]["dataset"]["pipeline"]):
        if step["type"] not in ("LoadPointsFromFile", "LoadPointsFromMultiSweeps"):
            continue
        if step["type"] == "LoadPointsFromMultiSweeps" and sweeps_num is not None:
            step["sweeps_num"] = sweeps_num
        steps.append(step)
    return Compose(steps)


def sweeps_summary(points_single, points_multi):
    """Point counts and the duplicate ratio of the multi-sweep cloud.

    ``ratio`` is the share of distinct ``(x, y, z)`` rows in ``points_multi``:
    real sweeps give a high value, while a keyframe copied ``sweeps_num`` times
    by ``LoadPointsFromMultiSweeps`` gives roughly ``1 / (1 + sweeps_num)``.
    """
    import numpy as np

    single = np.asarray(points_single)
    multi = np.asarray(points_multi)
    n_single = int(single.shape[0])
    n_multi = int(multi.shape[0])
    if n_multi == 0:
        ratio = 0.0
    else:
        unique = np.unique(multi[:, :3], axis=0).shape[0]
        ratio = round(float(unique) / float(n_multi), 4)
    return {"n_single": n_single, "n_multi": n_multi, "ratio": ratio}


def run_sweeps_probe(probe, cfg, dataroot, version, model, checkpoint, device_index):
    """Prove multi-sweep loading loads more than the keyframe, and time it."""
    import numpy as np
    from mmdet3d.datasets import build_dataset

    dataset_cfg = copy.deepcopy(cfg["data"]["train"]["dataset"])
    dataset_cfg["ann_file"] = str(MINI_PKL)
    dataset_cfg["dataset_root"] = str(dataroot)
    dataset_cfg["pipeline"] = build_pipeline_steps(
        "A", cfg["data"]["train"]["dataset"]["pipeline"]
    )
    dataset_cfg["test_mode"] = False
    dataset = build_dataset(dataset_cfg)
    if not dataset.data_infos:
        fail("sweeps_probe", "the mini split is empty")

    n_sweeps = len(dataset.data_infos[0]["sweeps"])
    log("SWEEPS_INFO version=%s n_sweeps=%d" % (version, n_sweeps))

    modes = (("single", 0), ("multi", None))
    counts = {}
    for mode, sweeps_num in modes:
        pipeline = build_points_pipeline(cfg, sweeps_num)
        example = pipeline(dataset.get_data_info(0))
        points = np.asarray(example["points"].tensor)
        counts[mode] = points
        log("SWEEPS_PTS mode=%s n=%d" % (mode, points.shape[0]))

    summary = sweeps_summary(counts["single"], counts["multi"])
    log("SWEEPS_UNIQUE mode=multi ratio=%.4f" % summary["ratio"])

    for mode, sweeps_num in modes:
        loader, _step_types = build_loader("A", cfg, dataroot, sweeps_num=sweeps_num)
        load_weights(probe, model, checkpoint)
        record = run_arm("A", model, loader, device_index, ARM_STEPS["A"])
        log("STEP_TIME mode=%s s_per_step=%.4f" % (mode, record["s_per_step"]))
        del loader

    if (
        summary["n_multi"] > summary["n_single"] * SWEEPS_MIN_MULTIPLIER
        and summary["ratio"] > SWEEPS_MIN_RATIO
    ):
        log(
            "SWEEPS_OK n_single=%d n_multi=%d ratio=%.4f"
            % (summary["n_single"], summary["n_multi"], summary["ratio"])
        )
        return 0

    log(
        "SWEEPS_FAILED n_single=%d n_multi=%d ratio=%.4f"
        % (summary["n_single"], summary["n_multi"], summary["ratio"])
    )
    return 1


def _serializable(record):
    return {
        key: value
        for key, value in record.items()
        if key in ("s_per_step", "peak_gb", "loss_first", "loss_last",
                   "n_points_after_pipeline", "spray_stats")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataroot", default=None, help="nuScenes root")
    parser.add_argument(
        "--nusc-version",
        default="v1.0-trainval",
        help="nuScenes version directory to read (default: v1.0-trainval)",
    )
    parser.add_argument(
        "--sweeps-probe",
        action="store_true",
        help="measure the multi-sweep loader on v1.0-mini instead of running A/B",
    )
    args = parser.parse_args(argv)
    started = time.time()

    version = "v1.0-mini" if args.sweeps_probe else args.nusc_version
    n = SWEEPS_PROBE_N if args.sweeps_probe else 4000
    dataroot = find_dataroot(args.dataroot, version)
    log("SMOKE_INFO dataroot=%s version=%s" % (dataroot, version))
    run_mini_split(dataroot, version, n)

    probe = load_probe()

    # mmdet3d.datasets imports the nuScenes dataset (devkit is installed by the
    # kernel), so the real package is available; the probe's stub registration
    # is then a no-op and only re-registers the spray pipeline transforms.
    import mmdet3d.datasets  # noqa: F401
    import spray.plume_transform  # noqa: F401  (registers PlumeTransform)

    probe.setup_pipelines()

    import torch
    from spray.pipeline import install as install_spray_pipelines

    install_spray_pipelines()

    if not torch.cuda.is_available():
        fail("cuda", "torch.cuda.is_available() is false")
    device = "cuda"
    device_index = torch.cuda.current_device()
    log(
        "SMOKE_INFO device=%s gpu=%s torch=%s"
        % (device, torch.cuda.get_device_name(device_index), torch.__version__)
    )

    cfg, _files = probe.load_config(DATASET_CONFIG)
    checkpoint = probe.ensure_checkpoint()
    model, choice, _freeze_payload = prepare_model(probe, checkpoint, device)

    if args.sweeps_probe:
        return run_sweeps_probe(
            probe, cfg, dataroot, version, model, checkpoint, device_index
        )

    results = {}
    for arm in ("A", "B"):
        loader, step_types = build_loader(arm, cfg, dataroot)
        # Each arm starts from the same checkpoint so the two step timings are
        # independent; the optimizer is rebuilt inside run_arm.
        load_weights(probe, model, checkpoint)
        record = run_arm(arm, model, loader, device_index, ARM_STEPS[arm])
        record["pipeline"] = step_types
        results[arm] = record
        del loader

    peak_gb = max(results["A"]["peak_gb"], results["B"]["peak_gb"])
    payload = {
        "s_per_step_A": round(results["A"]["s_per_step"], 4),
        "s_per_step_B": round(results["B"]["s_per_step"], 4),
        "peak_gb": round(peak_gb, 3),
        "peak_gb_A": round(results["A"]["peak_gb"], 3),
        "peak_gb_B": round(results["B"]["peak_gb"], 3),
        "loss_first": results["B"]["loss_first"],
        "loss_last": results["B"]["loss_last"],
        "n_points_after_pipeline": results["B"]["n_points_after_pipeline"],
        "spray_stats": results["B"]["spray_stats"],
        "devkit_version": devkit_version(),
        "chosen_model_config": choice["chosen"],
        "steps_A": ARM_STEPS["A"],
        "steps_B": ARM_STEPS["B"],
        "warmup_steps": WARMUP_STEPS,
        "batch_size": BATCH,
        "workers_per_gpu": WORKERS,
        "seed": SEED,
        "optimizer": "AdamW",
        "lr": LR,
        "weight_decay": WEIGHT_DECAY,
        "grad_clip": GRAD_CLIP,
        "arms": {
            arm: dict(_serializable(record), pipeline=record["pipeline"])
            for arm, record in results.items()
        },
        "device": device,
        "gpu": torch.cuda.get_device_name(device_index),
        "torch": torch.__version__,
        "elapsed_s": round(time.time() - started, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(str(OUT_JSON), "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)

    log(
        "SMOKE_OK s_per_step=%.4f peak_gb=%.3f steps=%d"
        % (results["B"]["s_per_step"], peak_gb, sum(ARM_STEPS.values()))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
