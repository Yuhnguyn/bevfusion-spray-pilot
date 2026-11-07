"""Adapt BEVFusion (MIT) raw detections to :mod:`proxy_eval.matcher`.

The Kaggle step writes ``real_frame_detections.json`` (boxes_3d, scores_3d,
labels_3d, class_names) and ``real_frame_eval_info.json`` (gt_boxes, gt_names)
for one real frame. This module is the only place that knows those JSON keys;
the evaluator stays format-agnostic.

CLI:
    python -m proxy_eval.mit_adapter PRED.json INFO.json [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .matcher import EvalConfig, average_precision, evaluate_frame

# Order from NuScenesDataset.CLASSES / the MIT model's label indices.
MIT_CLASSES = (
    "car",
    "truck",
    "trailer",
    "bus",
    "construction_vehicle",
    "bicycle",
    "motorcycle",
    "pedestrian",
    "traffic_cone",
    "barrier",
)


def load_predictions(path: str | Path):
    payload = json.loads(Path(path).read_text())
    boxes = np.asarray(payload["boxes_3d"], dtype=np.float64).reshape(-1, 7)
    scores = np.asarray(payload["scores_3d"], dtype=np.float64).reshape(-1)
    labels = np.asarray(payload["labels_3d"], dtype=np.int64).reshape(-1)
    class_names = tuple(payload.get("class_names") or MIT_CLASSES)
    return boxes, scores, labels, class_names


def load_ground_truth(path: str | Path, class_names: tuple[str, ...]):
    payload = json.loads(Path(path).read_text())
    boxes = np.asarray(payload["gt_boxes"], dtype=np.float64).reshape(-1, 7)
    name_to_index = {name: index for index, name in enumerate(class_names)}
    unknown = sorted({name for name in payload["gt_names"] if name not in name_to_index})
    if unknown:
        raise ValueError(f"GT classes not in class_names: {unknown}")
    labels = np.asarray([name_to_index[name] for name in payload["gt_names"]], dtype=np.int64)
    return boxes, labels


def evaluate_files(
    pred_path: str | Path,
    info_path: str | Path,
    score_threshold: float = 0.05,
    range_m: float = 54.0,
    iou_threshold: float = 0.5,
) -> dict:
    boxes, scores, labels, class_names = load_predictions(pred_path)
    gt_boxes, gt_labels = load_ground_truth(info_path, class_names)
    config = EvalConfig(
        class_names=class_names,
        iou_threshold=iou_threshold,
        score_threshold=score_threshold,
        range_m=range_m,
    )
    result = evaluate_frame(boxes, scores, labels, gt_boxes, gt_labels, config)
    return {
        "class_names": list(class_names),
        "config": {
            "score_threshold": score_threshold,
            "range_m": range_m,
            "iou_threshold": iou_threshold,
        },
        "num_predictions": int(len(boxes)),
        "num_predictions_kept": int((scores >= score_threshold).sum()),
        "num_gt": int(len(gt_boxes)),
        "tp": result.tp,
        "fp": result.fp,
        "fn": result.fn,
        "precision": result.precision,
        "recall": result.recall,
        "map": float(average_precision([result], config)),
        "gt_outside_range": result.gt_outside_range,
        "recall_by_range": result.recall_by_range,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions")
    parser.add_argument("info")
    parser.add_argument("--json")
    parser.add_argument("--score-threshold", type=float, default=0.05)
    parser.add_argument("--range-m", type=float, default=54.0)
    args = parser.parse_args()
    report = evaluate_files(
        args.predictions,
        args.info,
        score_threshold=args.score_threshold,
        range_m=args.range_m,
    )
    text = json.dumps(report, indent=1)
    if args.json:
        Path(args.json).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
