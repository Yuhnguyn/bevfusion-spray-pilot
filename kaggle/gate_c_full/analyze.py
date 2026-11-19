#!/usr/bin/env python3
"""Offline paired analysis of a full Gate C run (3 arms, jsonl, any tau).

The Kaggle harness writes ``gate_c_detections.jsonl`` with **every** box above
0.05 so the numbers can be recomputed here at another threshold. This script
reuses ``proxy_eval.matcher`` (same BEV IoU >= 0.5, label-agnostic, range 54 m)
so its primary tau = 0.20 numbers must match the summary the harness printed.

It reports, for the pooled split and per speed group (50 / 90 / 130):

* FP/frame, recall, % frames with >= 1 FP, dets/frame per arm;
* paired-by-scene deltas ``plume - clean`` and ``real - clean`` with the
  scene-level percentile bootstrap (2000 resamples, seed 0) used by the
  pre-registered protocol;
* the tau sweep 0.10 / 0.20 / 0.30 / 0.50.

Usage::

    python kaggle/gate_c_full/analyze.py \
        --jsonl /tmp/gate_c_full/gate_c_out/gate_c_detections.jsonl \
        --infos data/sspp_infos_test.pkl \
        --out-dir .scratch/tmp/gate_c_full_analysis
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from proxy_eval.bootstrap import scene_bootstrap  # noqa: E402
from proxy_eval.matcher import EvalConfig, evaluate_frame  # noqa: E402

ARMS = ("clean", "plume", "real")
PAIRS = (("plume", "clean"), ("real", "clean"), ("plume", "real"))
TAUS = (0.10, 0.20, 0.30, 0.50)
PRIMARY_TAU = 0.20
SPEEDS = (50, 90, 130)
IOU_GATE = 0.5
RANGE_M = 54.0
N_BOOT = 2000
BOOT_SEED = 0


def config(tau: float) -> EvalConfig:
    return EvalConfig(
        class_names=("object",),
        iou_threshold=IOU_GATE,
        score_threshold=float(tau),
        range_m=RANGE_M,
    )


def load_infos(path: Path) -> dict[str, dict]:
    with path.open("rb") as handle:
        infos = pickle.load(handle)
    return {str(info["token"]): info for info in infos}


def load_jsonl(path: Path) -> dict[tuple[str, int, str], list[dict]]:
    frames: dict[tuple[str, int, str], list[dict]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            key = (record["scene_token"], int(record["frame_idx"]), record["arm"])
            frames[key] = record["boxes"]
    return frames


def frame_result(boxes: list[dict], gt: np.ndarray, tau: float) -> dict:
    pred = np.asarray(
        [
            [box["x"], box["y"], box["z"], box["dx"], box["dy"], box["dz"], box["yaw"]]
            for box in boxes
        ],
        dtype=np.float64,
    ).reshape(-1, 7)
    scores = np.asarray([box["score"] for box in boxes], dtype=np.float64).reshape(-1)
    labels = np.zeros(len(scores), dtype=np.int64)
    gt_labels = np.zeros(len(gt), dtype=np.int64)
    result = evaluate_frame(pred, scores, labels, gt, gt_labels, config(tau))
    return {
        "tp": int(result.tp),
        "fp": int(result.fp),
        "fn": int(result.fn),
        "recall": float(result.recall),
        "precision": float(result.precision),
        "n_pred": int(len(pred)),
    }


def mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def arm_stats(keys: list[tuple[str, int]], metrics: dict, arm: str) -> dict:
    rows = [metrics[(scene, idx, arm)] for scene, idx in keys]
    return {
        "n_frames": len(rows),
        "fp_per_frame": mean([row["fp"] for row in rows]),
        "tp_per_frame": mean([row["tp"] for row in rows]),
        "recall": mean([row["recall"] for row in rows]),
        "precision": mean([row["precision"] for row in rows]),
        "dets_per_frame": mean([row["n_pred"] for row in rows]),
        "frames": len(rows),
        "frames_with_fp": int(sum(1 for row in rows if row["fp"] >= 1)),
        "pct_frames_with_fp": (
            100.0 * sum(1 for row in rows if row["fp"] >= 1) / len(rows) if rows else 0.0
        ),
        "total_fp": int(sum(row["fp"] for row in rows)),
        "total_tp": int(sum(row["tp"] for row in rows)),
    }


def scene_deltas(
    keys: list[tuple[str, int]], metrics: dict, arm_a: str, arm_b: str, field: str
) -> dict[str, float]:
    by_scene: dict[str, list[float]] = {}
    for scene, idx in keys:
        delta = metrics[(scene, idx, arm_a)][field] - metrics[(scene, idx, arm_b)][field]
        by_scene.setdefault(scene, []).append(float(delta))
    return {scene: float(np.mean(values)) for scene, values in by_scene.items()}


def paired_stats(
    keys: list[tuple[str, int]], metrics: dict, arm_a: str, arm_b: str
) -> dict:
    fp = scene_deltas(keys, metrics, arm_a, arm_b, "fp")
    recall = scene_deltas(keys, metrics, arm_a, arm_b, "recall")
    if len(fp) < 2:
        return {"error": "paired delta needs >= 2 scenes, got %d" % len(fp)}
    return {
        "n_frames": len(keys),
        "n_scenes": len(fp),
        "scene_fp_delta": fp,
        "scene_recall_delta": recall,
        "fp_delta_bootstrap": scene_bootstrap(fp, n=N_BOOT, seed=BOOT_SEED),
        "recall_delta_bootstrap": scene_bootstrap(recall, n=N_BOOT, seed=BOOT_SEED),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--infos", default=str(REPO / "data" / "sspp_infos_test.pkl"))
    parser.add_argument("--out-dir", default=str(REPO / ".scratch" / "tmp" / "gate_c_full_analysis"))
    parser.add_argument("--tag", default="")
    args = parser.parse_args(argv)

    jsonl_path = Path(args.jsonl)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    infos = load_infos(Path(args.infos))
    boxes_by_key = load_jsonl(jsonl_path)
    keys = sorted({(scene, idx, arm) for scene, idx, arm in boxes_by_key})
    frames = sorted({(scene, idx) for scene, idx, _ in keys})
    if not frames:
        raise SystemExit("no frames in %s" % jsonl_path)
    missing_arms = [
        (scene, idx, arm)
        for scene, idx in frames
        for arm in ARMS
        if (scene, idx, arm) not in boxes_by_key
    ]
    if missing_arms:
        raise SystemExit("%d frame/arm pairs missing, e.g. %r"
                         % (len(missing_arms), missing_arms[:3]))

    gt_by_frame = {}
    speed_by_frame = {}
    for scene, idx in frames:
        token = "%s/%06d" % (scene, idx)
        if token not in infos:
            raise SystemExit("token %s not in infos" % token)
        info = infos[token]
        gt = np.asarray(info["gt_boxes"], dtype=np.float64).reshape(-1, 9)[:, :7]
        gt_by_frame[(scene, idx)] = gt
        speed_by_frame[(scene, idx)] = int(round(float(info["ego_speed_kmh"])))

    metrics_by_tau = {}
    for tau in TAUS:
        metrics = {}
        for scene, idx in frames:
            for arm in ARMS:
                metrics[(scene, idx, arm)] = frame_result(
                    boxes_by_key[(scene, idx, arm)], gt_by_frame[(scene, idx)], tau
                )
        metrics_by_tau[tau] = metrics

    def group_keys(speed=None):
        return [
            (scene, idx)
            for scene, idx in frames
            if speed is None or speed_by_frame[(scene, idx)] == speed
        ]

    def frame_keys(speed=None):
        return [(scene, idx) for scene, idx in frames
                if speed is None or speed_by_frame[(scene, idx)] == speed]

    payload = {
        "jsonl": str(jsonl_path),
        "infos": str(args.infos),
        "n_frames": len(frames),
        "n_scenes": len({scene for scene, _ in frames}),
        "taus": list(TAUS),
        "primary_tau": PRIMARY_TAU,
        "iou_threshold": IOU_GATE,
        "range_m": RANGE_M,
        "n_boot": N_BOOT,
        "boot_seed": BOOT_SEED,
        "frames_by_speed": {
            str(speed): len(frame_keys(speed)) for speed in SPEEDS
        },
        "scenes_by_speed": {
            str(speed): sorted({scene for scene, idx in frames
                                if speed_by_frame[(scene, idx)] == speed})
            for speed in SPEEDS
        },
    }

    # Primary tau: per arm + paired, pooled and per speed group.
    metrics = metrics_by_tau[PRIMARY_TAU]
    arm_block = {}
    for arm in ARMS:
        arm_block[arm] = {"overall": arm_stats(group_keys(), metrics, arm)}
        for speed in SPEEDS:
            arm_block[arm][str(speed)] = arm_stats(group_keys(speed), metrics, arm)
    payload["per_arm"] = arm_block

    paired_block = {}
    for arm_a, arm_b in PAIRS:
        name = "%s_minus_%s" % (arm_a, arm_b)
        paired_block[name] = {"overall": paired_stats(group_keys(), metrics, arm_a, arm_b)}
        for speed in SPEEDS:
            paired_block[name][str(speed)] = paired_stats(
                group_keys(speed), metrics, arm_a, arm_b
            )
    payload["paired"] = paired_block

    # tau sweep: FP/frame, recall, % frames with FP per arm.
    sweep = {}
    for tau in TAUS:
        tau_metrics = metrics_by_tau[tau]
        sweep["%.2f" % tau] = {
            arm: arm_stats(group_keys(), tau_metrics, arm) for arm in ARMS
        }
    payload["tau_sweep"] = sweep

    # Per-scene table at the primary tau.
    per_scene = {}
    for scene in sorted({scene for scene, _ in frames}):
        scene_keys = [(s, i) for s, i in frames if s == scene]
        per_scene[scene] = {
            "speed_kmh": speed_by_frame[scene_keys[0]],
            "n_frames": len(scene_keys),
            **{
                arm: arm_stats(scene_keys, metrics, arm) for arm in ARMS
            },
        }
    payload["per_scene"] = per_scene

    # Reading aid for the pre-registered decision rule (runbook §2, §4): the
    # rule itself lives in the runbook and is not redefined here.
    primary = paired_block["plume_minus_clean"]["overall"]
    if "error" in primary:
        payload["verdict"] = {"error": primary["error"]}
    else:
        fp_boot = primary["fp_delta_bootstrap"]
        recall_boot = primary["recall_delta_bootstrap"]
        plume_overall = arm_block["plume"]["overall"]
        clean_overall = arm_block["clean"]["overall"]
        payload["verdict"] = {
            "tau": PRIMARY_TAU,
            "fp_delta_mean": fp_boot["mean"],
            "fp_delta_ci95": [fp_boot["lo"], fp_boot["hi"]],
            "fp_ci_excludes_zero_with_positive_lo": bool(fp_boot["lo"] > 0.0),
            "recall_delta_mean": recall_boot["mean"],
            "recall_delta_ci95_lo": recall_boot["lo"],
            "recall_lower_bound_ge_minus_0p02": bool(recall_boot["lo"] >= -0.02),
            "train_direction_alive": bool(
                fp_boot["lo"] > 0.0 and recall_boot["lo"] >= -0.02
            ),
            "fp_per_frame": {
                "clean": clean_overall["fp_per_frame"],
                "plume": plume_overall["fp_per_frame"],
                "real": arm_block["real"]["overall"]["fp_per_frame"],
            },
            "recall": {
                "clean": clean_overall["recall"],
                "plume": plume_overall["recall"],
                "real": arm_block["real"]["overall"]["recall"],
            },
        }

    stem = "gate_c_full_analysis"
    if args.tag:
        stem += "_" + args.tag
    (out_dir / (stem + ".json")).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    def fmt(value: float, digits: int = 4) -> str:
        return ("%." + str(digits) + "f") % value

    lines = [
        "# Gate C full rerun (channel-4 fixed) — offline paired analysis",
        "",
        "- jsonl: `%s`" % jsonl_path,
        "- frames: **%d** · scenes: **%d** · tau primary **%.2f** · IoU >= %.2f (label-agnostic) · range <= %.0f m"
        % (len(frames), payload["n_scenes"], PRIMARY_TAU, IOU_GATE, RANGE_M),
        "- frames/speed: %s"
        % ", ".join("%d km/h: %d" % (speed, payload["frames_by_speed"][str(speed)])
                    for speed in SPEEDS),
        "",
        "## Per arm (tau = %.2f)" % PRIMARY_TAU,
        "",
        "| group | arm | FP/frame | recall | % frame co FP | dets/frame | TP/frame |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group in ("overall",) + tuple(str(speed) for speed in SPEEDS):
        for arm in ARMS:
            item = arm_block[arm][group]
            lines.append(
                "| %s | %s | %s | %s | %.1f%% | %s | %s |"
                % (group, arm, fmt(item["fp_per_frame"]), fmt(item["recall"]),
                   item["pct_frames_with_fp"], fmt(item["dets_per_frame"]),
                   fmt(item["tp_per_frame"]))
            )

    lines += ["", "## Paired by scene (bootstrap %d, tau = %.2f)" % (N_BOOT, PRIMARY_TAU), "",
              "| group | pair | FP delta | CI95 FP | recall delta | CI95 recall | n scene |",
              "|---|---|---:|---|---:|---|---:|"]
    for name, block in paired_block.items():
        label = name.replace("_minus_", " - ")
        for group in ("overall",) + tuple(str(speed) for speed in SPEEDS):
            item = block[group]
            if "error" in item:
                lines.append("| %s | %s | n/a | n/a | n/a | n/a | <2 |" % (group, label))
                continue
            fp_boot = item["fp_delta_bootstrap"]
            rec_boot = item["recall_delta_bootstrap"]
            lines.append(
                "| %s | %s | %+.4f | [%+.4f; %+.4f] | %+.4f | [%+.4f; %+.4f] | %d |"
                % (group, label, fp_boot["mean"], fp_boot["lo"], fp_boot["hi"],
                   rec_boot["mean"], rec_boot["lo"], rec_boot["hi"], item["n_scenes"])
            )

    lines += ["", "## Tau sensitivity (pooled)", "",
              "| tau | arm | FP/frame | recall | % frame co FP |", "|---:|---|---:|---:|---:|"]
    for tau_text, block in sweep.items():
        for arm in ARMS:
            item = block[arm]
            lines.append(
                "| %s | %s | %s | %s | %.1f%% |"
                % (tau_text, arm, fmt(item["fp_per_frame"]), fmt(item["recall"]),
                   item["pct_frames_with_fp"])
            )

    verdict = payload["verdict"]
    lines += ["", "## Pre-registered decision rule (reading aid; runbook §2/§4)", ""]
    if "error" in verdict:
        lines.append("- cannot evaluate: %s" % verdict["error"])
    else:
        lines += [
            "- FP delta (plume - clean) = %+.4f, CI95 [%+.4f; %+.4f] -> CI excludes 0 with positive lower bound: **%s**"
            % (verdict["fp_delta_mean"], verdict["fp_delta_ci95"][0],
               verdict["fp_delta_ci95"][1],
               "YES" if verdict["fp_ci_excludes_zero_with_positive_lo"] else "NO"),
            "- recall delta (plume - clean) = %+.4f, CI95 lower bound %+.4f >= -0.02: **%s**"
            % (verdict["recall_delta_mean"], verdict["recall_delta_ci95_lo"],
               "YES" if verdict["recall_lower_bound_ge_minus_0p02"] else "NO"),
            "- TRAIN DIRECTION ALIVE: **%s**"
            % ("YES" if verdict["train_direction_alive"] else "NO"),
        ]

    (out_dir / (stem + ".md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\nGATE_C_ANALYSIS %s" % (out_dir / (stem + ".json")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
