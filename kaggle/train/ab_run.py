"""Ticket 11-c1: train the two A/B arms for a fixed number of steps.

Runs inside the pinned Python 3.8 venv that ``kaggle/e2e/main.py`` builds and
that ``kaggle/train/main.py`` boots (torch 1.10.1+cu113, mmcv-full 1.4.0,
mmdet 2.20.0, mmdet3d from da93b27) with ``nuscenes-devkit`` already installed.
The mini split, the pipeline builder, the loader and the pretrained-checkpoint
path are reused from ``smoke.py``; this module only adds the training loop, the
per-arm checkpoints and the summary.

Both arms see the same seed, the same split and the same initial weights; the
only difference is the arm's pipeline slice (arm B carries ``PlumeTransform``).
Every torch import lives inside a function so the helpers can be unit-tested
without torch.

Log lines:

* ``AB_STEP arm=<A|B> i=<i> loss=<f> s=<f>`` -- every ``--log-every`` steps;
* ``AB_ARM_OK arm=<A|B> steps=<n> s_per_step=<f> loss_first=<f>
  loss_last=<f> loss_mean_last100=<f> peak_gb=<f>`` -- once per finished arm;
* ``AB_TRAIN_OK arms=<n> steps=<n> time_s=<f>`` -- last line on success;
* ``AB_FAILED <reason> [detail]`` -- on a missing dataroot/checkpoint, a
  non-finite loss or an exhausted ``--time-budget-s``, then exit 1.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import smoke  # noqa: E402  (needs the directory above on sys.path)

REPO = pathlib.Path(__file__).resolve().parents[2]
MINI_N = 4000
GRAD_CLIP = 5.0


def log(*parts):
    print(*parts, flush=True)


def fail(reason, detail=None):
    log("AB_FAILED %s" % reason)
    if detail:
        log(detail)
    sys.exit(1)


# ------------------------------------------------------------------- helpers
def arm_specs(arms, steps=2000, lr=1e-4, seed=0):
    """Return one symmetric spec per arm.

    ``steps``, ``lr`` and ``seed`` are deliberately shared: changing the budget
    for one arm only would make the A/B comparison meaningless.
    """
    return [
        {"arm": arm, "steps": steps, "lr": lr, "seed": seed}
        for arm in arms
    ]


def summarize_records(records):
    """Aggregate per-step ``{"loss": float, "s": float}`` records.

    ``s_per_step`` is the mean of the measured step times; the loss fields are
    the first value, the last value and the mean of the last 100 values (a
    full arm is a lot longer than that, so the tail is a stable noise gauge).
    """
    times = [float(record["s"]) for record in records]
    losses = [float(record["loss"]) for record in records]
    return {
        "s_per_step": statistics.mean(times) if times else None,
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "loss_mean_last100": statistics.mean(losses[-100:]) if losses else None,
    }


def checkpoint_payload(state_dict, arm, steps, lr, sweeps_num):
    """Build the dict saved as ``ckpt_arm<arm>.pth``."""
    return {
        "state_dict": state_dict,
        "arm": arm,
        "steps": steps,
        "lr": lr,
        "sweeps_num": sweeps_num,
    }


def loss_keys(losses):
    """Keys used to compute the training loss.

    Some mmdet3d heads return both the total ``loss`` and its components
    (``loss_cls``, ``loss_bbox``, ``loss_dir``); summing both would count the
    same gradient twice.  Prefer the total when present, otherwise sum every
    component in sorted order for a deterministic result.
    """
    if "loss" in losses:
        return ["loss"]
    return sorted(name for name in losses if "loss" in name)


def time_budget_exceeded(started, budget, now=None):
    """True once ``budget`` seconds have elapsed since ``started``.

    ``budget <= 0`` is treated as no budget.  ``now`` exists so the boundary
    can be tested without sleeping.
    """
    if budget is None or budget <= 0:
        return False
    current = time.time() if now is None else now
    return current - started >= budget


# --------------------------------------------------------------- setup helpers
def resolve_dataroot(explicit=None):
    if explicit:
        root = pathlib.Path(explicit)
        if not (root / "v1.0-trainval" / "sample.json").is_file():
            fail("dataroot", "no v1.0-trainval/sample.json under %s" % root)
        return root
    try:
        return smoke.find_dataroot()
    except SystemExit:
        fail("dataroot", "find_dataroot found no v1.0-trainval/sample.json")


def ensure_mini_split(dataroot):
    if smoke.MINI_PKL.is_file():
        log("AB_INFO mini_split=reuse path=%s" % smoke.MINI_PKL)
        return
    try:
        smoke.run_mini_split(dataroot, "v1.0-trainval", MINI_N)
    except SystemExit:
        fail("mini_split", "smoke.run_mini_split failed")


def set_seeds(seed):
    import random

    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def build_arm_loader(arm, cfg, dataroot, sweeps_num, steps):
    """Build the arm loader with as many valid samples as the split allows.

    ``smoke.build_loader`` sizes its subset from ``smoke.ARM_STEPS * BATCH``
    and exits when the split has fewer non-empty samples.  The mini split keeps
    as few as 95 % of the requested 4,000, so try the full need and halve it
    on shortage; ``train_arm`` cycles the loader, so even a smaller subset
    still feeds exactly ``steps`` optimiser steps.
    """
    need = steps
    while need >= 1:
        smoke.ARM_STEPS[arm] = need
        try:
            return smoke.build_loader(arm, cfg, dataroot, sweeps_num=sweeps_num)
        except SystemExit:
            if need == 1:
                fail("valid_indices", "arm=%s" % arm)
            need //= 2
            log("AB_INFO arm=%s loader_need_reduced steps=%d" % (arm, need))


# ------------------------------------------------------------------ training
def train_arm(arm, model, loader, optimizer, device_index, steps, log_every,
              started, budget):
    """Run ``steps`` optimisation steps; return ``(records, stop_reason)``.

    ``stop_reason`` is ``None`` on a full arm and ``"time_budget"`` when the
    loop stopped early, so the caller can still persist a checkpoint.
    """
    import torch
    from mmcv.parallel import scatter

    model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    records = []
    iterator = iter(loader)
    for index in range(steps):
        if time_budget_exceeded(started, budget):
            return records, "time_budget"
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            try:
                batch = next(iterator)
            except StopIteration:
                fail("empty_loader", "arm=%s step=%d" % (arm, index))
        batch = scatter(batch, [device_index])[0]
        torch.cuda.synchronize()

        step_started = time.perf_counter()
        try:
            losses = model(return_loss=True, **batch)
        except Exception:  # noqa: BLE001 - the traceback is the evidence
            traceback.print_exc()
            fail("forward", "arm=%s step=%d" % (arm, index))

        keys = loss_keys(losses)
        if index == 0:
            log("AB_INFO arm=%s loss_keys=%s" % (arm, ",".join(keys)))
        terms = [losses[name] for name in keys if torch.is_tensor(losses[name])]
        if not terms:
            fail("no_loss", "arm=%s step=%d keys=%s" % (arm, index, sorted(losses)))
        loss = sum(terms)
        if not torch.isfinite(loss):
            fail("non_finite_loss", "arm=%s step=%d loss=%r" % (arm, index, float(loss)))

        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, GRAD_CLIP)
        optimizer.step()
        optimizer.zero_grad()
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - step_started

        records.append({"loss": float(loss.item()), "s": elapsed})
        if log_every and (index + 1) % log_every == 0:
            log(
                "AB_STEP arm=%s i=%d loss=%.6f s=%.4f"
                % (arm, index + 1, records[-1]["loss"], elapsed)
            )
    return records, None


def save_checkpoint(path, payload):
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, str(path))


def write_summary(path, args, specs, results, raw_records, started):
    payload = {
        "config": {
            "arms": [spec["arm"] for spec in specs],
            "steps": args.steps,
            "batch": args.batch,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "sweeps_num": args.sweeps_num,
            "time_budget_s": args.time_budget_s,
            "log_every": args.log_every,
        },
        "seed": args.seed,
        "arms": results,
        "records": raw_records,
        "time_s": round(time.time() - started, 1),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)


# ----------------------------------------------------------------------- main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataroot", default=None, help="nuScenes root")
    parser.add_argument("--steps", type=int, default=2000, help="steps per arm")
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sweeps-num", type=int, default=0)
    parser.add_argument("--out", default="/kaggle/working")
    parser.add_argument("--arms", nargs="+", default=["A", "B"])
    parser.add_argument("--time-budget-s", type=float, default=9000)
    parser.add_argument("--log-every", type=int, default=100)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    started = time.time()

    dataroot = resolve_dataroot(args.dataroot)
    log("AB_INFO dataroot=%s" % dataroot)

    # Loader shape lives on the smoke module; mutate the runtime knobs rather
    # than editing smoke.py (its BATCH/LR stay the ticket-11-b values).
    smoke.SEED = args.seed
    smoke.BATCH = args.batch
    smoke.ARM_STEPS = {arm: args.steps for arm in args.arms}

    ensure_mini_split(dataroot)

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
    device_index = torch.cuda.current_device()
    log(
        "AB_INFO device=%s gpu=%s torch=%s"
        % (device, torch.cuda.get_device_name(device_index), torch.__version__)
    )

    cfg, _files = probe.load_config(smoke.DATASET_CONFIG)

    try:
        checkpoint = probe.ensure_checkpoint()
    except SystemExit:
        fail("checkpoint", "probe.ensure_checkpoint failed")
    except Exception as exc:  # noqa: BLE001 - reported verbatim
        fail("checkpoint", repr(exc)[:2000])

    try:
        model, choice, _freeze_payload = smoke.prepare_model(
            probe, checkpoint, device
        )
    except SystemExit:
        fail("checkpoint", "model build or weight load failed")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    specs = arm_specs(args.arms, steps=args.steps, lr=args.lr, seed=args.seed)
    log(
        "AB_INFO arms=%s steps=%d batch=%d lr=%s sweeps_num=%d model_config=%s"
        % (
            ",".join(spec["arm"] for spec in specs),
            args.steps,
            args.batch,
            args.lr,
            args.sweeps_num,
            choice["chosen"],
        )
    )
    results = {}
    raw_records = {}

    for spec in specs:
        arm = spec["arm"]
        # Reseed before building the loader so both arms start from the same
        # RNG stream; the checkpoint is reloaded so neither arm inherits the
        # other's weights.
        set_seeds(spec["seed"])
        loader, step_types = build_arm_loader(
            arm, cfg, dataroot, args.sweeps_num, spec["steps"]
        )
        try:
            smoke.load_weights(probe, model, checkpoint)
        except SystemExit:
            fail("checkpoint", "reload before arm %s failed" % arm)

        params = [p for p in model.parameters() if p.requires_grad]
        if not params:
            fail("optimizer", "arm %s has no trainable parameters" % arm)
        optimizer = torch.optim.AdamW(
            params, lr=spec["lr"], weight_decay=args.weight_decay
        )

        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

        records, reason = train_arm(
            arm,
            model,
            loader,
            optimizer,
            device_index,
            spec["steps"],
            args.log_every,
            started,
            args.time_budget_s,
        )
        del loader

        summary = summarize_records(records)
        summary["peak_gb"] = torch.cuda.max_memory_allocated() / float(1 << 30)
        summary["steps"] = len(records)
        summary["pipeline"] = step_types
        results[arm] = summary
        raw_records[arm] = {
            "times": [record["s"] for record in records],
            "losses": [record["loss"] for record in records],
        }

        payload = checkpoint_payload(
            model.state_dict(),
            arm=arm,
            steps=len(records),
            lr=spec["lr"],
            sweeps_num=args.sweeps_num,
        )
        try:
            save_checkpoint(out / ("ckpt_arm%s.pth" % arm), payload)
        except Exception as exc:  # noqa: BLE001 - reported verbatim
            fail("checkpoint_save", repr(exc)[:2000])

        log(
            "AB_ARM_OK arm=%s steps=%d s_per_step=%.4f loss_first=%.6f "
            "loss_last=%.6f loss_mean_last100=%.6f peak_gb=%.3f"
            % (
                arm,
                summary["steps"],
                summary["s_per_step"],
                summary["loss_first"],
                summary["loss_last"],
                summary["loss_mean_last100"],
                summary["peak_gb"],
            )
        )

        if reason is not None:
            write_summary(
                out / "ab_train_summary.json",
                args,
                specs,
                results,
                raw_records,
                started,
            )
            fail(
                reason,
                "arm=%s steps=%d time_s=%.1f"
                % (arm, summary["steps"], time.time() - started),
            )

    write_summary(
        out / "ab_train_summary.json", args, specs, results, raw_records, started
    )
    log(
        "AB_TRAIN_OK arms=%d steps=%d time_s=%.1f"
        % (len(specs), args.steps, time.time() - started)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
