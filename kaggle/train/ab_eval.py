"""Ticket 11-c3b: run the A/B checkpoints on the fixed 196-frame eval set.

Four cells: two checkpoints (``ckpt_armA.pth`` / ``ckpt_armB.pth``) times two
conditions (clean / spray plume).  The eval set is the shared 196-frame, 16-scene
selection; the spray condition is the same loader with ``arm="B"`` so the only
difference is ``PlumeTransform``.

The mini split, the pipeline builder and the loader are reused from
``smoke.py``; the per-frame scoring is reused from ``proxy_eval``.  This module
only adds the cell runner and the scene-level summary.

Log lines:

* ``EVAL_SPLIT_OK frames=<n> scenes=<n>`` -- eval set and pickle are ready;
* ``EVAL_FRAME n=<i>/<total>`` -- every 20 frames of a cell;
* ``EVAL_CELL arm=<A|B> cond=<clean|spray> map=<f> recall=<f>`` -- once per cell;
* ``EVAL_DELTA arm=<A|B> dmap=<f>`` -- spray minus clean for that checkpoint;
* ``EVAL_OK delta_A=<f> delta_B=<f> interaction=<f> ci95=<lo,hi>`` -- last line;
* ``EVAL_FAILED <reason> [detail]`` -- on a failed split/checkpoint/CUDA, then
  exit 1.

Every torch/mmcv import lives inside a function so the helpers can be unit
tested without torch.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import pickle
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import smoke  # noqa: E402  (needs the directory above on sys.path)

from proxy_eval.bootstrap import (  # noqa: E402
    paired_delta,
    per_scene_metric,
    scene_bootstrap,
)
from proxy_eval.mit_adapter import evaluate_files  # noqa: E402

EXPECTED_FRAMES = 196
EXPECTED_SCENES = 16
ARMS = ("A", "B")
CONDITIONS = (("clean", False), ("spray", True))
FRAME_LOG_EVERY = 20


def log(*parts):
    print(*parts, flush=True)


def fail(reason, detail=None):
    log("EVAL_FAILED %s" % reason)
    if detail:
        log(detail)
    sys.exit(1)


# ------------------------------------------------------------------- helpers
def run_command(cmd, cwd):
    """Run ``cmd`` and echo its output; return the combined text."""
    log("EVAL_CMD %s" % " ".join(str(token) for token in cmd))
    done = subprocess.run(
        [str(token) for token in cmd],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    text = done.stdout or ""
    for line in text.splitlines():
        log(line)
    return done.returncode, text


def prepare_eval_split(repo, workdir, dataroot=None):
    """Build the fixed eval-set JSON and its pickle, fail loudly on trouble."""
    repo = pathlib.Path(repo)
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    json_path = workdir / "eval_196.json"
    pkl_path = workdir / "eval_196.pkl"

    cmd = [sys.executable, "scripts/make_eval_split.py", "--out", str(json_path)]
    if dataroot:
        cmd.extend(["--dataroot", str(dataroot)])
    rc, text = run_command(cmd, repo)
    if rc != 0 or "EVAL_SET_FAILED" in text or not json_path.is_file():
        fail("eval_split", "rc=%d json=%s" % (rc, json_path))

    cmd = [
        sys.executable,
        "scripts/make_mini_split.py",
        "--tokens-json",
        str(json_path),
        "--out",
        str(pkl_path),
    ]
    if dataroot:
        cmd.extend(["--dataroot", str(dataroot)])
    rc, text = run_command(cmd, repo)
    if rc != 0 or "MINI_SPLIT_FAILED" in text or not pkl_path.is_file():
        fail("eval_pkl", "rc=%d pkl=%s" % (rc, pkl_path))

    frames = json.loads(json_path.read_text())["frames"]
    scenes = {frame.get("scene") or frame.get("scene_token") for frame in frames}
    if len(frames) != EXPECTED_FRAMES or len(scenes) != EXPECTED_SCENES:
        log(
            "EVAL_INFO split_unexpected frames=%d scenes=%d expected=%d,%d"
            % (len(frames), len(scenes), EXPECTED_FRAMES, EXPECTED_SCENES)
        )
    log("EVAL_SPLIT_OK frames=%d scenes=%d" % (len(frames), len(scenes)))
    return json_path, pkl_path


def count_infos(pkl_path):
    with open(str(pkl_path), "rb") as handle:
        payload = pickle.load(handle)
    return len(payload["infos"])


def scene_by_token(json_path):
    """Map ``sample_token`` to its scene identifier from the eval-set JSON."""
    payload = json.loads(pathlib.Path(json_path).read_text())
    mapping = {}
    for frame in payload["frames"]:
        mapping[frame["sample_token"]] = frame.get("scene") or frame["scene_token"]
    return mapping


def build_eval_loader(pkl_path, plume, cfg, dataroot, n_frames):
    """Reuse ``smoke.build_loader``; only the arm and batch size change.

    ``plume=True`` evaluates the spray pipeline (arm B), ``plume=False`` the
    clean one (arm A).  The loader is deterministic (``shuffle=False``) and
    single-frame; the eval pickle is pointed at by mutating the module knob
    ``smoke.MINI_PKL`` that ``build_loader`` reads.
    """
    arm = "B" if plume else "A"
    smoke.MINI_PKL = pathlib.Path(pkl_path)
    smoke.BATCH = 1
    smoke.ARM_STEPS[arm] = int(n_frames)
    loader, _step_types = smoke.build_loader(arm, cfg, dataroot, sweeps_num=0)
    return loader


# ------------------------------------------------------------------- runner
def _unwrap_batch(batch, data_container):
    """Replace every ``DataContainer`` with its ``.data`` before a model call."""
    return {
        key: (value.data if isinstance(value, data_container) else value)
        for key, value in batch.items()
    }


def _loader_class_names(loader):
    dataset = loader.dataset
    while not hasattr(dataset, "CLASSES") and hasattr(dataset, "dataset"):
        dataset = dataset.dataset
    return list(dataset.CLASSES)


def _batch_token(batch):
    metas = batch["metas"]
    if isinstance(metas, (list, tuple)):
        metas = metas[0]
    return str(metas["token"])


def _to_numpy(value):
    """Normalize boxes/labels (possibly CUDA, box objects or containers) to ndarray."""
    import numpy as np

    if isinstance(value, (list, tuple)):
        return _to_numpy(value[0])
    if isinstance(value, np.ndarray):
        return value
    tensor = getattr(value, "tensor", None)
    if tensor is not None:
        return _to_numpy(tensor)
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    data = getattr(value, "data", None)
    if data is not None:
        return _to_numpy(data)
    return np.asarray(value)


def _batch_gt(batch):
    import numpy as np

    tensor = _to_numpy(batch["gt_bboxes_3d"])
    if tensor.size:
        tensor = tensor.reshape(-1, tensor.shape[-1])[:, :7]
    else:
        tensor = np.empty((0, 7), dtype=np.float64)

    labels = _to_numpy(batch["gt_labels_3d"]).reshape(-1).astype(int)
    return tensor, labels


def _write_json(path, payload):
    with open(str(path), "w") as handle:
        json.dump(payload, handle, indent=1)


def run_cell(model, loader, out_dir, limit=0, total=None):
    """Run one cell and write per-frame prediction and GT JSON files."""
    import torch
    from mmcv.parallel import DataContainer, scatter

    model.eval()
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    class_names = _loader_class_names(loader)
    total = total or limit or 0

    device_index = torch.cuda.current_device()
    written = 0
    with torch.no_grad():
        for batch in loader:
            if limit and written >= limit:
                break
            batch = scatter(batch, [device_index])[0]
            batch = _unwrap_batch(batch, DataContainer)
            token = _batch_token(batch)
            gt_boxes, gt_labels = _batch_gt(batch)

            outputs = model(**batch)
            detection = outputs[0]
            boxes = detection["boxes_3d"].tensor.detach().cpu().numpy()
            if boxes.size:
                boxes = boxes.reshape(-1, boxes.shape[-1])[:, :7]
            else:
                boxes = boxes.reshape(-1, 7)
            scores = detection["scores_3d"].detach().cpu().numpy().reshape(-1)
            labels = (
                detection["labels_3d"]
                .detach()
                .cpu()
                .numpy()
                .reshape(-1)
                .astype(int)
            )

            _write_json(
                out_dir / ("%s.pred.json" % token),
                {
                    "boxes_3d": boxes.tolist(),
                    "scores_3d": scores.tolist(),
                    "labels_3d": labels.tolist(),
                    "class_names": class_names,
                },
            )
            gt_names = [
                class_names[int(label)]
                if 0 <= int(label) < len(class_names)
                else "unknown"
                for label in gt_labels
            ]
            _write_json(
                out_dir / ("%s.gt.json" % token),
                {"gt_boxes": gt_boxes.tolist(), "gt_names": gt_names},
            )

            written += 1
            if written % FRAME_LOG_EVERY == 0:
                log("EVAL_FRAME n=%d/%s" % (written, total or "?"))
    return written


# ------------------------------------------------------------------ scoring
def score_cell(pred_dir, gt_dir, arm=None, cond=None):
    """Average ``proxy_eval.evaluate_files`` over every written GT frame."""
    pred_dir = pathlib.Path(pred_dir)
    gt_dir = pathlib.Path(gt_dir)
    gt_files = sorted(gt_dir.glob("*.gt.json"))

    maps = []
    recalls = []
    precisions = []
    per_frame = {}
    for gt_path in gt_files:
        token = gt_path.name[: -len(".gt.json")]
        pred_path = pred_dir / ("%s.pred.json" % token)
        if not pred_path.is_file():
            raise FileNotFoundError(
                "missing prediction for frame %s: %s" % (token, pred_path)
            )
        result = evaluate_files(pred_path, gt_path)
        maps.append(float(result["map"]))
        recalls.append(float(result["recall"]))
        precisions.append(float(result["precision"]))
        per_frame[token] = float(result["map"])

    n_frames = len(maps)
    mean_map = statistics.mean(maps) if maps else 0.0
    mean_recall = statistics.mean(recalls) if recalls else 0.0
    mean_precision = statistics.mean(precisions) if precisions else 0.0

    if arm is not None and cond is not None:
        log(
            "EVAL_CELL arm=%s cond=%s map=%.4f recall=%.4f"
            % (arm, cond, mean_map, mean_recall)
        )
    return {
        "map": mean_map,
        "recall": mean_recall,
        "precision": mean_precision,
        "n_frames": n_frames,
        "per_frame": per_frame,
    }


def summarize_cells(cells, ci=None):
    """Combine the four cells into the two deltas and their interaction.

    ``delta_A`` is arm A spray minus clean, ``delta_B`` the same for arm B, and
    ``interaction`` is ``delta_B - delta_A``.  When ``ci`` is given (a
    ``scene_bootstrap`` result) its ``lo``/``hi`` land in ``ci95``.
    """
    delta_a = float(cells["A"]["spray"]["map"]) - float(cells["A"]["clean"]["map"])
    delta_b = float(cells["B"]["spray"]["map"]) - float(cells["B"]["clean"]["map"])
    summary = {
        "delta_A": delta_a,
        "delta_B": delta_b,
        "interaction": delta_b - delta_a,
    }
    if ci is not None:
        summary["ci95"] = [float(ci["lo"]), float(ci["hi"])]
    return summary


def interaction_ci(cells, scene_map):
    """Paired scene bootstrap of ``delta_B - delta_A`` over the eval scenes."""
    def scene_means(cell):
        frames = [
            {"scene_token": scene_map[token], "map": value}
            for token, value in cell["per_frame"].items()
        ]
        return per_scene_metric(frames, "map")

    try:
        clean_a = scene_means(cells["A"]["clean"])
        spray_a = scene_means(cells["A"]["spray"])
        clean_b = scene_means(cells["B"]["clean"])
        spray_b = scene_means(cells["B"]["spray"])
        delta_a = paired_delta(spray_a, clean_a)
        delta_b = paired_delta(spray_b, clean_b)
        interaction = paired_delta(delta_b, delta_a)
    except ValueError as exc:
        log("EVAL_INFO ci_unavailable=%s" % exc)
        return None
    return scene_bootstrap(interaction)


# --------------------------------------------------------------------- setup
def resolve_dataroot(explicit=None):
    if explicit:
        return pathlib.Path(explicit)
    try:
        return smoke.find_dataroot()
    except SystemExit:
        fail("dataroot", "find_dataroot found no v1.0-trainval/sample.json")


def load_arm_weights(model, ckpt_path):
    import torch

    ckpt = torch.load(str(ckpt_path), map_location="cpu")
    state = ckpt.get("state_dict") if isinstance(ckpt, dict) else ckpt
    if state is None:
        state = ckpt
    if state and all(key.startswith("module.") for key in state):
        state = {key[len("module."):]: value for key, value in state.items()}
    try:
        model.load_state_dict(state)
    except Exception as exc:  # noqa: BLE001 - reported verbatim
        fail("checkpoint_load", "%s: %r" % (ckpt_path, exc))


# ---------------------------------------------------------------------- main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt-dir", default="/kaggle/working")
    parser.add_argument("--out-dir", default="/kaggle/working/ab_eval")
    parser.add_argument("--dataroot", default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="max frames per cell (0 = the full eval set)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=0,
        help="accepted for task_args reuse; eval ignores it",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    started = time.time()

    ckpt_dir = pathlib.Path(args.ckpt_dir)
    workdir = pathlib.Path(args.out_dir)
    workdir.mkdir(parents=True, exist_ok=True)
    log(
        "EVAL_INFO ckpt_dir=%s out_dir=%s limit=%d"
        % (ckpt_dir, workdir, args.limit)
    )

    dataroot = resolve_dataroot(args.dataroot)
    log("EVAL_INFO dataroot=%s" % dataroot)

    json_path, pkl_path = prepare_eval_split(REPO, workdir, dataroot)
    n_infos = count_infos(pkl_path)
    limit = n_infos if args.limit <= 0 else min(args.limit, n_infos)
    log("EVAL_INFO frames=%d scored=%d" % (n_infos, limit))

    probe = smoke.load_probe()

    import mmdet3d.datasets  # noqa: F401
    import spray.plume_transform  # noqa: F401  (registers PlumeTransform)

    probe.setup_pipelines()

    import torch
    from spray.pipeline import install as install_spray_pipelines

    install_spray_pipelines()

    if not torch.cuda.is_available():
        fail("cuda", "torch.cuda.is_available() is false")
    device = "cuda"
    log("EVAL_INFO device=%s torch=%s" % (device, torch.__version__))

    data_cfg, _files = probe.load_config(smoke.DATASET_CONFIG)
    model_cfg, _model_files, choice = probe.choose_model_config()
    model, _build_info = probe.build(model_cfg)
    model = model.to(device)
    log("EVAL_INFO model_config=%s" % choice["chosen"])

    scene_map = scene_by_token(json_path)
    cells = {}
    for arm in ARMS:
        ckpt_path = ckpt_dir / ("ckpt_arm%s.pth" % arm)
        if not ckpt_path.is_file():
            fail("checkpoint", "missing %s" % ckpt_path)
        load_arm_weights(model, ckpt_path)
        cells[arm] = {}
        for cond, plume in CONDITIONS:
            try:
                loader = build_eval_loader(
                    pkl_path, plume, data_cfg, dataroot, limit
                )
            except SystemExit:
                fail("loader", "arm=%s cond=%s" % (arm, cond))
            out = workdir / ("cell_%s_%s" % (arm, cond))
            try:
                run_cell(model, loader, out, limit=limit, total=limit)
            except SystemExit:
                raise
            except Exception:  # noqa: BLE001 - the traceback is the evidence
                import traceback

                traceback.print_exc()
                fail("cell", "arm=%s cond=%s" % (arm, cond))
            del loader
            cells[arm][cond] = score_cell(out, out, arm=arm, cond=cond)

    ci = interaction_ci(cells, scene_map)
    summary = summarize_cells(cells, ci=ci)

    for arm in ARMS:
        log("EVAL_DELTA arm=%s dmap=%.4f" % (arm, summary["delta_%s" % arm]))
    if "ci95" in summary:
        ci_text = "[%.4f,%.4f]" % tuple(summary["ci95"])
    else:
        ci_text = "NA"
    log(
        "EVAL_OK delta_A=%.4f delta_B=%.4f interaction=%.4f ci95=%s"
        % (
            summary["delta_A"],
            summary["delta_B"],
            summary["interaction"],
            ci_text,
        )
    )
    _write_json(
        workdir / "ab_eval_summary.json",
        {
            "config": {
                "ckpt_dir": str(ckpt_dir),
                "limit": args.limit,
                "frames": n_infos,
                "scored": limit,
            },
            "cells": {
                arm: {
                    cond: {
                        key: value
                        for key, value in cell.items()
                        if key != "per_frame"
                    }
                    for cond, cell in by_cond.items()
                }
                for arm, by_cond in cells.items()
            },
            "summary": summary,
            "time_s": round(time.time() - started, 1),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
