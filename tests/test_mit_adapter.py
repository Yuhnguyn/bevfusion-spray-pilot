import json

import numpy as np

from proxy_eval.mit_adapter import MIT_CLASSES, evaluate_files


def _write(tmp_path, pred, info):
    pred_path = tmp_path / "pred.json"
    info_path = tmp_path / "info.json"
    pred_path.write_text(json.dumps(pred))
    info_path.write_text(json.dumps(info))
    return pred_path, info_path


def test_adapter_matches_one_car_and_rejects_wrong_class(tmp_path):
    box = [10.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]
    pred = {
        "class_names": list(MIT_CLASSES),
        "boxes_3d": [box, [-10.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]],
        "scores_3d": [0.9, 0.8],
        "labels_3d": [0, 1],  # car, truck
    }
    info = {"gt_boxes": [box], "gt_names": ["car"]}
    pred_path, info_path = _write(tmp_path, pred, info)

    out = evaluate_files(pred_path, info_path)

    assert out["tp"] == 1
    assert out["fp"] == 1
    assert out["fn"] == 0
    assert out["map"] == 1.0
    assert out["config"]["score_threshold"] == 0.05


def test_adapter_filters_by_score_and_range(tmp_path):
    box = [10.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]
    far = [80.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]
    pred = {
        "class_names": list(MIT_CLASSES),
        "boxes_3d": [box, far],
        "scores_3d": [0.01, 0.9],
        "labels_3d": [0, 0],
    }
    info = {"gt_boxes": [box], "gt_names": ["car"]}
    pred_path, info_path = _write(tmp_path, pred, info)

    out = evaluate_files(pred_path, info_path)

    assert out["num_predictions_kept"] == 1  # far box passes score, not range
    assert out["tp"] == 0 and out["fn"] == 1
