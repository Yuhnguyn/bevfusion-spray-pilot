from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EvalConfig:
    class_names: tuple[str, ...]
    iou_threshold: float = 0.5
    score_threshold: float = 0.05
    range_m: float = 54.0
    range_buckets: tuple[float, ...] = (0.0, 10.0, 20.0, 30.0, 40.0, 54.0)


@dataclass
class FrameResult:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    unmatched_predictions: int
    gt_outside_range: int
    recall_by_range: dict[str, float]
    pred_scores: np.ndarray
    pred_labels: np.ndarray
    pred_tp: np.ndarray
    gt_labels: np.ndarray


def evaluate_frame(
    pred_boxes: np.ndarray,
    pred_scores: np.ndarray,
    pred_labels: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
    config: EvalConfig,
) -> FrameResult:
    boxes = _as_boxes(pred_boxes)
    scores = _as_vector(pred_scores)
    labels = _as_labels(pred_labels)
    gt = _as_boxes(gt_boxes)
    gt_lab = _as_labels(gt_labels)
    if len(boxes) != len(scores) or len(boxes) != len(labels):
        raise ValueError("prediction arrays must have the same length")
    if len(gt) != len(gt_lab):
        raise ValueError("GT arrays must have the same length")
    _check_labels(labels, config)
    _check_labels(gt_lab, config)

    gt_keep = np.linalg.norm(gt[:, :2], axis=1) <= config.range_m
    gt_outside = int((~gt_keep).sum())
    gt = gt[gt_keep]
    gt_lab = gt_lab[gt_keep]

    keep = np.linalg.norm(boxes[:, :2], axis=1) <= config.range_m
    boxes = boxes[keep]
    scores = scores[keep]
    labels = labels[keep]

    selected = scores >= config.score_threshold
    selected_tp, matched_gt = _match(
        boxes[selected],
        labels[selected],
        scores[selected],
        gt,
        gt_lab,
        config.iou_threshold,
    )
    tp = int(selected_tp.sum())
    fp = int((~selected_tp).sum())
    fn = int((~matched_gt).sum())

    all_tp, _ = _match(boxes, labels, scores, gt, gt_lab, config.iou_threshold)

    distances = np.linalg.norm(gt[:, :2], axis=1)
    recall_by_range = _recall_by_range(
        distances, matched_gt, config.range_buckets
    )

    return FrameResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=float(tp / (tp + fp)) if tp + fp else 0.0,
        recall=float(tp / (tp + fn)) if tp + fn else 0.0,
        unmatched_predictions=fp,
        gt_outside_range=gt_outside,
        recall_by_range=recall_by_range,
        pred_scores=scores,
        pred_labels=labels,
        pred_tp=all_tp,
        gt_labels=gt_lab,
    )


def average_precision(
    results: list[FrameResult], config: EvalConfig
) -> float:
    aps: list[float] = []
    for class_index in range(len(config.class_names)):
        scores: list[float] = []
        tps: list[float] = []
        gt_count = 0
        for result in results:
            mask = result.pred_labels == class_index
            scores.extend(result.pred_scores[mask].tolist())
            tps.extend(result.pred_tp[mask].astype(np.float64).tolist())
            gt_count += int((result.gt_labels == class_index).sum())
        if gt_count == 0:
            continue
        order = np.argsort(-np.asarray(scores), kind="stable")
        tp = np.asarray(tps, dtype=np.float64)[order]
        cum_tp = np.cumsum(tp)
        cum_fp = np.cumsum(1.0 - tp)
        recall = cum_tp / gt_count
        precision = cum_tp / np.maximum(cum_tp + cum_fp, 1e-12)
        mrec = np.concatenate([[0.0], recall, [1.0]])
        mpre = np.concatenate([[0.0], precision, [0.0]])
        for i in range(len(mpre) - 2, -1, -1):
            mpre[i] = max(mpre[i], mpre[i + 1])
        aps.append(float(np.sum(np.diff(mrec) * mpre[1:])))
    return float(np.mean(aps)) if aps else 0.0


def bev_corners(box: np.ndarray) -> np.ndarray:
    x, y, _, width, length, _, yaw = box
    cos_yaw = np.cos(yaw)
    sin_yaw = np.sin(yaw)
    local = np.array(
        [
            [-width / 2.0, -length / 2.0],
            [width / 2.0, -length / 2.0],
            [width / 2.0, length / 2.0],
            [-width / 2.0, length / 2.0],
        ]
    )
    rotation = np.array([[cos_yaw, -sin_yaw], [sin_yaw, cos_yaw]])
    return local @ rotation.T + np.array([x, y])


def bev_iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
    poly_a = bev_corners(box_a)
    poly_b = bev_corners(box_b)
    intersection = _clip_polygon(poly_a, poly_b)
    if len(intersection) < 3:
        return 0.0
    inter_area = _polygon_area(intersection)
    union = _polygon_area(poly_a) + _polygon_area(poly_b) - inter_area
    return float(inter_area / union) if union > 0 else 0.0


def _match(
    boxes: np.ndarray,
    labels: np.ndarray,
    scores: np.ndarray,
    gt_boxes: np.ndarray,
    gt_labels: np.ndarray,
    iou_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    pred_tp = np.zeros(len(boxes), dtype=bool)
    matched_gt = np.zeros(len(gt_boxes), dtype=bool)
    if len(boxes) == 0 or len(gt_boxes) == 0:
        return pred_tp, matched_gt

    order = np.argsort(-scores, kind="stable")
    for index in order:
        best_iou = -1.0
        best_gt = -1
        for gt_index in range(len(gt_boxes)):
            if matched_gt[gt_index] or gt_labels[gt_index] != labels[index]:
                continue
            iou = bev_iou(boxes[index], gt_boxes[gt_index])
            if iou > best_iou:
                best_iou = iou
                best_gt = gt_index
        if best_gt >= 0 and best_iou >= iou_threshold:
            matched_gt[best_gt] = True
            pred_tp[index] = True
    return pred_tp, matched_gt


def _recall_by_range(
    distances: np.ndarray,
    matched_gt: np.ndarray,
    buckets: tuple[float, ...],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for index in range(len(buckets) - 1):
        low = buckets[index]
        high = buckets[index + 1]
        if index == len(buckets) - 2:
            mask = (distances >= low) & (distances <= high)
        else:
            mask = (distances >= low) & (distances < high)
        total = int(mask.sum())
        key = f"{low:g}-{high:g}"
        result[key] = float(matched_gt[mask].sum() / total) if total else 0.0
    return result


def _as_boxes(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return np.empty((0, 7), dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 7:
        raise ValueError("boxes must have shape (N, 7)")
    return arr


def _as_vector(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return np.empty((0,), dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("scores must be one-dimensional")
    return arr


def _as_labels(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values)
    if arr.size == 0:
        return np.empty((0,), dtype=np.int64)
    if arr.ndim != 1:
        raise ValueError("labels must be one-dimensional")
    return arr.astype(np.int64)


def _check_labels(labels: np.ndarray, config: EvalConfig) -> None:
    if len(labels) and (
        labels.min() < 0 or labels.max() >= len(config.class_names)
    ):
        raise ValueError("label outside configured class_names")


def _polygon_area(polygon: np.ndarray) -> float:
    if len(polygon) < 3:
        return 0.0
    x = polygon[:, 0]
    y = polygon[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _clip_polygon(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    output = [tuple(point) for point in subject]
    for index in range(len(clip)):
        if not output:
            break
        start = clip[index]
        end = clip[(index + 1) % len(clip)]
        current = output
        output = []
        for point_index in range(len(current)):
            point = current[point_index]
            next_point = current[(point_index + 1) % len(current)]
            point_inside = _inside(point, start, end)
            next_inside = _inside(next_point, start, end)
            if point_inside:
                output.append(point)
            if point_inside != next_inside:
                output.append(_intersection(point, next_point, start, end))
    return np.asarray(output, dtype=np.float64)


def _inside(point, start, end) -> bool:
    return (
        (end[0] - start[0]) * (point[1] - start[1])
        - (end[1] - start[1]) * (point[0] - start[0])
    ) >= 0.0


def _intersection(point, next_point, start, end):
    d1 = (end[0] - start[0]) * (point[1] - start[1]) - (
        end[1] - start[1]
    ) * (point[0] - start[0])
    d2 = (end[0] - start[0]) * (next_point[1] - start[1]) - (
        end[1] - start[1]
    ) * (next_point[0] - start[0])
    if d1 == d2:
        return point
    t = d1 / (d1 - d2)
    return (
        point[0] + t * (next_point[0] - point[0]),
        point[1] + t * (next_point[1] - point[1]),
    )
