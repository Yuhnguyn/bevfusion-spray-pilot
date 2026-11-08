"""End-to-end test of the three arms through the real mmdet3d pipeline.

Skipped on a laptop (no mmcv/mmdet3d); runs inside the pinned MIT kernel clone.
"""

import copy
import os

import numpy as np
import pytest

try:  # pragma: no cover - only importable inside the pinned MIT kernel
    import mmcv
    from mmdet.datasets.builder import PIPELINES
    from mmdet3d.core import LiDARInstance3DBoxes
    from mmdet3d.core.points import LiDARPoints
except ImportError:  # laptop: no mmcv/mmdet3d, every test skips
    mmcv = PIPELINES = LiDARInstance3DBoxes = LiDARPoints = None

pytestmark = pytest.mark.skipif(
    mmcv is None,
    reason="mmcv/mmdet3d not installed; this test runs in the pinned MIT kernel",
)

from spray.denoise import dror_filter  # noqa: E402
from spray.pipeline import install  # noqa: E402
from spray.plume_transform import PlumeTransform  # noqa: E402

CONFIG_PATH = "mit/bevfusion/configs/nuscenes/default.yaml"
AUGMENT_STEPS = (
    "GlobalRotScaleTrans",
    "RandomFlip3D",
    "PointsRangeFilter",
    "ObjectRangeFilter",
    "PointShuffle",
)
POINT_CLOUD_RANGE = (-54.0, -54.0, -5.0, 54.0, 54.0, 3.0)
COLLECT_KEYS = [
    "points",
    "points_clean",
    "lidar_aug_matrix",
    "spray_stats",
    "sample_idx",
]
# 20 m/s = 72 km/h. The reference cluster count is (0.2*wfh + 0.1) * (v_kmh - 50)
# and 13.9 m/s (50.04 km/h) rounds to zero clusters, i.e. nothing injected.
BOX_VELOCITY = (0.0, 20.0, 0.0)


class _Denoise:
    """Arm B0: drop DROR outliers from the augmented stream only."""

    def __call__(self, results):
        points = results["points"]
        keep_mask, stats = dror_filter(points.tensor, k=8, alpha=0.03)
        results["points"] = LiDARPoints(
            points.tensor[keep_mask], points_dim=points.points_dim
        )
        results["denoise_stats"] = stats
        return results


def _array(value):
    if hasattr(value, "tensor"):
        value = value.tensor
    elif hasattr(value, "data"):
        value = value.data
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _load_config():
    if not os.path.exists(CONFIG_PATH):
        pytest.skip(f"kernel clone not present: {CONFIG_PATH}")
    return mmcv.Config.fromfile(CONFIG_PATH)


def _sample():
    rng = np.random.default_rng(0)
    xyz = rng.uniform(POINT_CLOUD_RANGE[:3], POINT_CLOUD_RANGE[3:], size=(40000, 3))
    extra = rng.uniform(0.0, 1.0, size=(40000, 2))
    points = np.concatenate([xyz, extra], axis=1).astype(np.float32)
    box = np.array(
        [
            [
                10.0,
                0.0,
                0.8,
                4.5,
                1.9,
                1.6,
                0.0,
                BOX_VELOCITY[0],
                BOX_VELOCITY[1],
            ]
        ],
        dtype=np.float32,
    )
    return {
        "points": LiDARPoints(points, points_dim=5),
        "gt_bboxes_3d": LiDARInstance3DBoxes(box, box_dim=9),
        "gt_labels_3d": np.array([0], dtype=np.int64),
        "sample_idx": 0,
        "metadata": {"token": "e2e", "seed": 0},
    }


def _build(cfg, plume_enabled=True, denoise=False):
    install()
    transforms = [
        PIPELINES.build(copy.deepcopy(dict(step)))
        for step in cfg.train_pipeline
        if step["type"] in AUGMENT_STEPS
    ]
    transforms.append(PlumeTransform(enabled=plume_enabled, seed=0))
    if denoise:
        transforms.append(_Denoise())
    transforms.append(
        PIPELINES.build(
            dict(
                type="CleanPointsFormatBundle3D",
                classes=list(cfg.object_classes),
            )
        )
    )
    transforms.append(
        PIPELINES.build(dict(type="CleanPointsCollect3D", keys=COLLECT_KEYS))
    )
    return transforms


def _run(cfg, plume_enabled=True, denoise=False):
    results = _sample()
    for transform in _build(cfg, plume_enabled=plume_enabled, denoise=denoise):
        results = transform(results)
    return results


def test_three_arms_run_end_to_end():
    cfg = _load_config()
    batches = {
        "A": _run(cfg, plume_enabled=False),
        "B": _run(cfg, plume_enabled=True),
        "B0": _run(cfg, plume_enabled=True, denoise=True),
    }

    for name, batch in batches.items():
        if "points_clean" not in batch:
            print(f"arm {name}: batch keys = {sorted(batch)}")
            pytest.fail(
                f"arm {name}: points_clean missing from batch output "
                "(plumbing bug, report to PM)"
            )
        clean = _array(batch["points_clean"])
        augmented = _array(batch["points"])
        assert np.isfinite(clean).all(), f"arm {name}: NaN/inf in points_clean"
        assert np.isfinite(augmented).all(), f"arm {name}: NaN/inf in points"

    assert batches["A"]["spray_stats"]["injected"] == 0
    assert batches["B"]["spray_stats"]["injected"] > 0
    assert batches["B0"]["spray_stats"]["injected"] > 0


def test_disabled_spray_leaves_points_unchanged():
    cfg = _load_config()
    batch = _run(cfg, plume_enabled=False)

    points = _array(batch["points"])
    clean = _array(batch["points_clean"])

    assert points.tobytes() == clean.tobytes()


def test_streams_share_frame_and_aug_matrix():
    cfg = _load_config()
    results = _sample()
    expected_idx = results["sample_idx"]
    aug_matrix = None
    snapshot = None

    for transform in _build(cfg, plume_enabled=True):
        if isinstance(transform, PlumeTransform):
            aug_matrix = np.array(_array(results["lidar_aug_matrix"]), copy=True)
            snapshot = np.array(_array(results["points"]), copy=True)
        results = transform(results)

    assert aug_matrix is not None
    assert snapshot is not None
    assert _array(results["points_clean"]).tobytes() == snapshot.tobytes()
    assert len(_array(results["points"])) == len(snapshot) + int(
        results["spray_stats"]["injected"]
    )
    assert np.array_equal(_array(results["lidar_aug_matrix"]), aug_matrix)
    assert results["sample_idx"] == expected_idx


def test_inverse_aug_matrix_roundtrip():
    cfg = _load_config()
    results = _sample()
    transform = PIPELINES.build(
        dict(
            type="GlobalRotScaleTrans",
            resize_lim=(0.95, 1.05),
            rot_lim=(-0.3, 0.3),
            trans_lim=0.5,
            is_train=True,
        )
    )
    results = transform(results)

    matrix = _array(results["lidar_aug_matrix"]).astype(np.float64)
    assert matrix.shape == (4, 4)
    assert not np.allclose(matrix, np.eye(4))

    points = np.random.default_rng(0).uniform(
        POINT_CLOUD_RANGE[:3], POINT_CLOUD_RANGE[3:], size=(100, 3)
    )
    homogeneous = np.concatenate([points, np.ones((len(points), 1))], axis=1)
    augmented = homogeneous @ matrix.T
    restored = augmented @ np.linalg.inv(matrix).T

    assert np.allclose(restored[:, :3], points, atol=1e-4)
