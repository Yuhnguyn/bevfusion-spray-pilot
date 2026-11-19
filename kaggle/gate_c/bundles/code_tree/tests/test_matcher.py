import numpy as np
import pytest

from proxy_eval.matcher import EvalConfig, average_precision, bev_iou, evaluate_frame

CONFIG = EvalConfig(class_names=("car", "truck"))


def _box(x=0.0, y=0.0, w=2.0, l=4.0, yaw=0.0):
    return np.array([x, y, 0.0, w, l, 1.5, yaw], dtype=np.float64)


def test_bev_iou_identical_disjoint_and_partial():
    base = _box()

    assert bev_iou(base, base) == pytest.approx(1.0)
    assert bev_iou(base, _box(x=10.0)) == 0.0
    assert bev_iou(base, _box(x=1.0)) == pytest.approx(1.0 / 3.0)


def test_rotated_square_has_same_area():
    base = _box(w=2.0, l=2.0)

    assert bev_iou(base, _box(w=2.0, l=2.0, yaw=np.pi / 2.0)) == pytest.approx(
        1.0
    )


def test_perfect_match():
    box = _box()

    result = evaluate_frame([box], [0.9], [0], [box], [0], CONFIG)

    assert (result.tp, result.fp, result.fn) == (1, 0, 0)
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.unmatched_predictions == 0


def test_duplicate_prediction_counts_as_false_positive():
    box = _box()

    result = evaluate_frame([box, box], [0.9, 0.8], [0, 0], [box], [0], CONFIG)

    assert (result.tp, result.fp, result.fn) == (1, 1, 0)
    assert result.precision == 0.5


def test_wrong_class_is_false_positive_and_false_negative():
    box = _box()

    result = evaluate_frame([box], [0.9], [1], [box], [0], CONFIG)

    assert (result.tp, result.fp, result.fn) == (0, 1, 1)


def test_range_filter_excludes_outside_gt():
    inside = _box(x=10.0)
    outside = _box(x=60.0)

    result = evaluate_frame(
        [inside], [0.9], [0], [inside, outside], [0, 0], CONFIG
    )

    assert result.gt_outside_range == 1
    assert result.tp == 1
    assert result.fn == 0


def test_recall_by_range_bucket():
    near = _box(x=5.0)
    far = _box(x=25.0)

    result = evaluate_frame([near], [0.9], [0], [near, far], [0, 0], CONFIG)

    assert result.recall_by_range["0-10"] == 1.0
    assert result.recall_by_range["20-30"] == 0.0


def test_average_precision_perfect_and_partial():
    box = _box()
    perfect = evaluate_frame([box], [0.9], [0], [box], [0], CONFIG)
    miss = evaluate_frame([], [], [], [box], [0], CONFIG)

    assert average_precision([perfect], CONFIG) == pytest.approx(1.0)
    assert average_precision([perfect, miss], CONFIG) == pytest.approx(0.5)
