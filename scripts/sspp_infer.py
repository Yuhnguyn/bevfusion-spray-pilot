#!/usr/bin/env python3
"""Gate C: does a synthetic plume raise the detector's false positives?

The gate asks one question, on SSPP frames, with **the same frame in every
arm** so the comparison is paired:

* ``clean``  — points with the dataset's spray/noise label (``label == 2``) removed;
* ``plume``  — the clean cloud + a synthetic plume injected by the production
  transform :class:`spray.plume_transform.PlumeTransform` (the path training
  arm B would use: stateful clusters -> beam ray casting -> attenuation and
  occlusion of real returns);
* ``real``   — the raw frame, real spray kept (reference for "what real spray
  does to the detector").

Scenario is the **production following scenario**, not the A3 static one: the
ego moves and the object sits 20-30 m ahead, exactly as ``sspp_infos*.pkl``
describes it. ``PlumeContext`` is built from the info dict. R3 verified that
``PlumeTransform`` is not declared in any config in this repo, so the class is
called directly here and that is recorded as an assumption.

Metrics, per frame and per arm: TP / FP / FN at a fixed score threshold,
recall, and how many real points the plume arm lost (occlusion) or attenuated.
``detections.jsonl`` keeps every detection plus the point counters so the
numbers can be recomputed offline at another threshold.

``--dry-run`` runs on a laptop with **no mmcv / mmdet / mmdet3d**: every heavy
import lives inside a function. It prints the plan (frames, scenes, config,
checkpoint, crop, threshold) and validates one frame end-to-end through the
plume path with numpy only.

Model choice (measured 2026-11-19, see ``.scratch/roadspray-cal/detector-choice.md``):
``data/lidar-only-det.pth`` is the published **LiDAR-only baseline** of
BEVFusion, i.e. the ``voxelnet_0p075`` chain (8.315.898 parameters). It is NOT
compatible with the vendored ``pointpillars`` fragment (head in 384 vs 512,
decoder in 64 vs 256), so a zero-shot gate C must run ``--config model0``.
``--config pointpillars`` exists for the later light detector, applies the
three known config fixes, and refuses to run unless the checkpoint actually
matches that architecture (no silent random weights).

Run with::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/sspp_infer.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from proxy_eval.bootstrap import scene_bootstrap  # noqa: E402
from proxy_eval.matcher import EvalConfig, evaluate_frame  # noqa: E402
from spray.plume import PlumeConfig  # noqa: E402
from spray.plume_context import PlumeContext  # noqa: E402
from spray.plume_state import PlumeState  # noqa: E402
from spray.plume_transform import PlumeTransform  # noqa: E402
from spray.sspp_adapter import load_points  # noqa: E402
from spray.wet_ground import WetGroundConfig  # noqa: E402

NOISE_LABEL = 2
BOX_DIM = 9
POINT_DIM = 5
ARMS = ("clean", "plume", "real")

DEFAULT_DATASET_ROOT = REPO / "data" / "SemanticSprayDataset"
DEFAULT_SPLIT_JSON = REPO / "data" / "sspp_split.json"
DEFAULT_CHECKPOINT = REPO / "data" / "lidar-only-det.pth"

# [ĐO] 2026-11-19 on data/lidar-only-det.pth (the published LiDAR-only baseline).
CHECKPOINT_BYTES = 33362653
CHECKPOINT_SHA256 = (
    "7f3f1f83754752ea2091543d010a87109d724dc48512a6258c31ef6545619a0e"
)

# Config leaves of the pinned vendor tree. ``model0`` is the chain the released
# checkpoint belongs to; ``pointpillars`` is the light detector planned for F2.
CONFIG_LEAVES = {
    "model0": "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/lidar/"
    "voxelnet_0p075.yaml",
    "pointpillars": "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/lidar/"
    "pointpillars.yaml",
}

# Fixes for the three known defects of the vendored pointpillars.yaml fragment
# (detector-choice.md §2.4 + plan.md §"Cảnh báo kỹ thuật F"). Applied only when
# --config pointpillars is requested; the trainer must inherit the same dict.
POINTPILLARS_OVERRIDES = {
    "point_cloud_range": [0.0, -16.0, -5.0, 64.0, 16.0, 3.0],
    "voxel_size": [0.2, 0.2, 8.0],
    "model.encoders.lidar.backbone.pts_middle_encoder.output_shape": [320, 160],
    "model.heads.object.num_classes": 2,
    "model.heads.object.num_proposals": 100,
    "model.heads.object.train_cfg.grid_size": [320, 160, 1],
    "model.heads.object.train_cfg.dataset": "SSPP",
    "model.heads.object.test_cfg.grid_size": [320, 160, 1],
    "model.heads.object.test_cfg.dataset": "SSPP",
    "model.heads.object.bbox_coder.post_center_range": [
        -1.0, -17.0, -5.0, 65.0, 17.0, 3.0,
    ],
    "object_classes": ["Car", "Van"],
    # bug 1 (with_velocity) is a data-section flag: box_dim 9 already carries
    # vx,vy, so it must never be concatenated a second time. The inference
    # harness builds annotations itself; the key is kept here so a future
    # training config derived from this dict inherits the fix.
    "data.train.dataset.with_velocity": False,
    "data.val.with_velocity": False,
    "data.test.with_velocity": False,
}

SPEED_OUT_OF_DOMAIN_KMH = 60.0  # ADR-0006 §5.3: <= 60 km/h is out of domain


# --------------------------------------------------------------------------
# Config resolution. torchpack's ``configs.load(recursive=True)`` merges every
# ancestor ``default.yaml`` (root first) and then evaluates ``${...}``. The
# pinned configs are fragments, so ``mmcv.Config.fromfile`` alone is wrong.
# This is the same resolver the old main-branch Kaggle harness used.
# --------------------------------------------------------------------------
class _DotDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc


def _chain(leaf: Path) -> list[Path]:
    leaf = leaf.resolve()
    candidates = [leaf]
    while leaf.parent != leaf:
        leaf = leaf.parent
        candidates.append(leaf / "default.yaml")
    return [path for path in reversed(candidates) if path.is_file()]


def _merge(destination: dict, source: dict) -> dict:
    for key, value in source.items():
        if isinstance(value, dict):
            if not isinstance(destination.get(key), dict):
                destination[key] = {}
            _merge(destination[key], value)
        else:
            destination[key] = value
    return destination


def _wrap(node):
    if isinstance(node, dict):
        return _DotDict((key, _wrap(value)) for key, value in node.items())
    if isinstance(node, list):
        return [_wrap(value) for value in node]
    return node


def _resolve(node, namespace, depth: int = 0):
    if depth > 32:
        raise RuntimeError("config interpolation nested too deeply")
    if isinstance(node, dict):
        return {key: _resolve(value, namespace, depth + 1) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(value, namespace, depth + 1) for value in node]
    if isinstance(node, str):
        text = node.strip()
        if text.startswith("${") and text.endswith("}"):
            value = eval(text[2:-1], {"__builtins__": {}}, namespace)  # noqa: S307
            return _resolve(value, namespace, depth + 1)
    return node


def _set_dotted(tree: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = tree
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def load_config(config_name: str, overrides: dict | None = None) -> tuple[dict, list[str]]:
    """Resolve the vendored leaf the way torchpack would, then patch it."""
    import yaml

    leaf = REPO / CONFIG_LEAVES[config_name]
    if not leaf.is_file():
        raise SystemExit(
            f"GATE_C_FAILED config leaf missing: {leaf}\n"
            "The pinned vendor tree is required; see docs/adr/0001-mit-bevfusion-pin.md"
        )
    merged: dict = {}
    files = _chain(leaf)
    for name in files:
        with name.open() as handle:
            _merge(merged, yaml.safe_load(handle) or {})
    resolved = _resolve(merged, _wrap(merged))
    if overrides:
        for dotted, value in overrides.items():
            _set_dotted(resolved, dotted, value)
    return resolved, [str(path.relative_to(REPO)) for path in files]


def config_facts(cfg: dict) -> dict:
    """Values the script prints and validates, independent of mmcv."""
    model = cfg["model"]
    lidar = model["encoders"]["lidar"]
    backbone = lidar["backbone"]
    head = model["heads"]["object"]
    pcr = [float(value) for value in cfg["point_cloud_range"]]
    voxel = [float(value) for value in cfg["voxel_size"]]
    facts = {
        "encoder_type": backbone.get("type"),
        "point_cloud_range": pcr,
        "voxel_size": voxel,
        "decoder_in_channels": model["decoder"]["backbone"].get("in_channels"),
        "decoder_type": model["decoder"]["backbone"].get("type"),
        "neck_type": model["decoder"]["neck"].get("type"),
        "head_type": head.get("type"),
        "head_in_channels": head.get("in_channels"),
        "num_classes": int(head.get("num_classes")),
        "num_proposals": int(head.get("num_proposals", 0)),
        "test_grid": [int(value) for value in head["test_cfg"].get("grid_size", [])],
        "train_grid": [int(value) for value in head["train_cfg"].get("grid_size", [])],
        "test_out_size_factor": int(head["test_cfg"].get("out_size_factor")),
        "test_dataset": head["test_cfg"].get("dataset"),
        "fuser": model.get("fuser"),
        "camera_encoder": model["encoders"].get("camera"),
    }
    if facts["encoder_type"] == "PointPillarsEncoder":
        scatter = backbone["pts_middle_encoder"]
        facts["scatter_output_shape"] = [int(v) for v in scatter["output_shape"]]
        facts["grid_xy"] = [
            int(round((pcr[3] - pcr[0]) / voxel[0])),
            int(round((pcr[4] - pcr[1]) / voxel[1])),
        ]
        features = pcr[3] - pcr[0]
        stride = 2 ** len(model["decoder"]["backbone"].get("layer_strides", []))
        facts["neck_stride"] = stride
        facts["expected_heatmap"] = [
            int(round((pcr[3] - pcr[0]) / (voxel[0] * facts["test_out_size_factor"]))),
            int(round((pcr[4] - pcr[1]) / (voxel[1] * facts["test_out_size_factor"]))),
        ]
        facts["_features_span_m"] = features
    return facts


def validate_config_facts(facts: dict) -> list[str]:
    """Static guards for the three known pointpillars defects.

    Returns human-readable checks; raises SystemExit on a fatal mismatch so a
    broken config cannot silently change what gate C measures.
    """
    problems: list[str] = []
    grid = facts["test_grid"]
    checks = [
        f"encoder={facts['encoder_type']}",
        f"fuser={facts['fuser']!r}",
        f"camera={type(facts['camera_encoder']).__name__}",
        f"head={facts['head_type']} in={facts['head_in_channels']} "
        f"classes={facts['num_classes']}",
        f"pcr={facts['point_cloud_range']} voxel={facts['voxel_size']}",
        f"train_grid={facts['train_grid']} test_grid={grid} "
        f"out_size_factor={facts['test_out_size_factor']}",
    ]
    if facts["fuser"] is not None:
        raise SystemExit(
            "GATE_C_FAILED config has a fuser: gate C must be LiDAR-only, got "
            f"{facts['fuser']!r}"
        )
    if facts["camera_encoder"] is not None:
        raise SystemExit("GATE_C_FAILED config has a camera encoder; LiDAR-only required")
    if not grid:
        raise SystemExit("GATE_C_FAILED test_cfg.grid_size is missing")
    if facts["encoder_type"] == "PointPillarsEncoder":
        scatter = facts["scatter_output_shape"]
        grid_xy = facts["grid_xy"]
        if scatter != grid_xy:
            raise SystemExit(
                "GATE_C_FAILED bug 3: PointPillarsScatter.output_shape "
                f"{scatter} != grid_xy {grid_xy} implied by point_cloud_range/voxel_size"
            )
        if facts["test_grid"][:2] != grid_xy:
            raise SystemExit(
                "GATE_C_FAILED bug 3: test_cfg.grid_size "
                f"{facts['test_grid'][:2]} != pillar grid {grid_xy}"
            )
        expected_heatmap = facts["expected_heatmap"]
        test_heatmap = [
            grid_xy[0] // facts["test_out_size_factor"],
            grid_xy[1] // facts["test_out_size_factor"],
        ]
        if expected_heatmap != test_heatmap:
            raise SystemExit(
                "GATE_C_FAILED bug 3: heatmap size from pcr/voxel/out_size_factor "
                f"{expected_heatmap} != grid_size/out_size_factor {test_heatmap}"
            )
        checks.append(
            "pointpillars fixes: output_shape/test_cfg.grid_size consistent; "
            "dataset=" + str(facts["test_dataset"])
        )
        if facts["test_dataset"] == "nuScenes" and facts["num_classes"] != 10:
            raise SystemExit(
                "GATE_C_FAILED bug 2: test_cfg.dataset='nuScenes' with "
                f"num_classes={facts['num_classes']} -> TransFusionHead indexes "
                "class 8/9 in forward_single (IndexError). Set dataset='SSPP'."
            )
    else:
        # The checkpointed model0 chain indexes classes 8/9; 10 classes are
        # required for it to run at all.
        if facts["test_dataset"] == "nuScenes" and facts["num_classes"] != 10:
            raise SystemExit(
                "GATE_C_FAILED bug 2: model0 chain needs num_classes=10 for its "
                f"nuScenes test branch, got {facts['num_classes']}"
            )
        checks.append("model0 chain: native grid, no crop (see runbook)")
    return checks


# --------------------------------------------------------------------------
# Checkpoint
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def checkpoint_facts(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"GATE_C_FAILED checkpoint missing: {path}")
    size = path.stat().st_size
    facts = {
        "path": str(path),
        "bytes": size,
        "sha256": sha256_file(path),
        "expected_bytes": CHECKPOINT_BYTES,
        "expected_sha256": CHECKPOINT_SHA256,
        "matches_expected": size == CHECKPOINT_BYTES,
    }
    if facts["sha256"] != CHECKPOINT_SHA256:
        facts["matches_expected"] = False
    return facts


def _load_state_dict(path: Path) -> dict:
    import torch

    payload = torch.load(str(path), map_location="cpu")
    if isinstance(payload, dict) and "state_dict" in payload:
        payload = payload["state_dict"]
    if isinstance(payload, dict) and payload and all(
        isinstance(key, str) for key in payload
    ):
        return payload
    raise SystemExit(f"GATE_C_FAILED cannot find a state_dict in {path}")


def checkpoint_variant(state: dict) -> str:
    if "encoders.lidar.backbone.conv_out.0.weight" in state:
        return "sparse_voxel"
    if any(key.startswith("encoders.lidar.backbone.pts_voxel_encoder") for key in state):
        return "pointpillars"
    return "unknown"


def check_checkpoint_vs_config(
    config_name: str, facts: dict, state: dict
) -> dict:
    """Refuse to run a checkpoint that does not belong to this architecture."""
    variant = checkpoint_variant(state)
    expected = (
        "pointpillars" if facts["encoder_type"] == "PointPillarsEncoder" else "sparse_voxel"
    )
    report = {"variant": variant, "expected": expected}
    if variant != expected:
        raise SystemExit(
            "GATE_C_FAILED checkpoint/config mismatch: checkpoint is "
            f"'{variant}' but --config {config_name} builds '{expected}'.\n"
            "The released data/lidar-only-det.pth is the LiDAR-only BEVFusion "
            "baseline (voxelnet_0p075). It cannot initialise the pointpillars "
            "fragment: different encoder, decoder in 64 vs 256, head in 384 vs "
            "512. Run gate C with --config model0; use pointpillars only with a "
            "checkpoint trained for it (F2). Refusing to run random weights."
        )

    decoder_in = facts["decoder_in_channels"]
    key = "decoder.backbone.blocks.0.0.weight"
    if key in state:
        actual = int(state[key].shape[1])
        report["decoder_in_checkpoint"] = actual
        if actual != int(decoder_in):
            raise SystemExit(
                f"GATE_C_FAILED {key} in={actual} but config decoder.in_channels="
                f"{decoder_in}"
            )
    head_key = "heads.object.shared_conv.weight"
    if head_key in state:
        actual = int(state[head_key].shape[1])
        report["head_in_checkpoint"] = actual
        if actual != int(facts["head_in_channels"]):
            raise SystemExit(
                f"GATE_C_FAILED {head_key} in={actual} but config head.in_channels="
                f"{facts['head_in_channels']}"
            )
    heat_key = "heads.object.heatmap_head.1.weight"
    if heat_key in state:
        actual = int(state[heat_key].shape[0])
        report["num_classes_checkpoint"] = actual
        if actual != int(facts["num_classes"]):
            raise SystemExit(
                f"GATE_C_FAILED {heat_key} classes={actual} but config "
                f"num_classes={facts['num_classes']}"
            )
    report["ok"] = True
    return report


# --------------------------------------------------------------------------
# Data: frozen split + infos + per-frame label filtering
# --------------------------------------------------------------------------
def read_split(path: Path, split: str) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"GATE_C_FAILED split json missing: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    scenes = document.get("split", {}).get(split)
    if not scenes:
        raise SystemExit(
            f"GATE_C_FAILED split '{split}' not in {path}; "
            f"available={sorted(document.get('split', {}))}"
        )
    return list(scenes)


def read_infos(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"GATE_C_FAILED infos missing: {path}")
    with path.open("rb") as handle:
        infos = pickle.load(handle)
    if not isinstance(infos, list) or not infos:
        raise SystemExit(f"GATE_C_FAILED infos must be a non-empty list: {path}")
    return infos


def label_path_for(dataset_root: Path, info: dict) -> Path:
    bin_path = dataset_root / info["lidar_path"]
    return bin_path.parent.parent / "labels" / f"{bin_path.stem}.label"


def read_labels(dataset_root: Path, info: dict) -> np.ndarray:
    path = label_path_for(dataset_root, info)
    if not path.is_file():
        raise SystemExit(f"GATE_C_FAILED label file missing: {path}")
    labels = np.fromfile(path, dtype=np.int32)
    return labels


def clean_points(dataset_root: Path, info: dict) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (raw_points, clean_points, n_noise_points) for one frame."""
    points = load_points(info, dataset_root)
    labels = read_labels(dataset_root, info)
    if labels.shape[0] != points.shape[0]:
        raise SystemExit(
            f"GATE_C_FAILED {info['token']}: {labels.shape[0]} labels vs "
            f"{points.shape[0]} points"
        )
    noise = labels == NOISE_LABEL
    return points, points[~noise], int(noise.sum())


def object_speed_mps(boxes: np.ndarray, fallback_mps: float) -> float:
    if boxes.size == 0:
        return float(fallback_mps)
    speeds = np.abs(boxes[:, 7].astype(np.float64))
    finite = speeds[np.isfinite(speeds)]
    return float(finite.max()) if finite.size else float(fallback_mps)


def build_context(args, info: dict, rel_scene: str, frame_index: int, boxes: np.ndarray):
    ego_speed = float(info["ego_speed_kmh"]) / 3.6
    return PlumeContext(
        scene_token=rel_scene,
        frame_index=frame_index,
        epoch=args.epoch,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=ego_speed,
        object_speed_mps=object_speed_mps(boxes, ego_speed),
        wfh_mm=(
            1.0 if args.wfh_mm is None else float(args.wfh_mm)
        ),
        road_z_m=float(args.road_z_m),
        # Following scenario: the object keeps its distance ahead of the ego, so
        # its velocity in the ego frame is ~0 (PROJECT.md §3c measured
        # object_velocity == ego_velocity in all 207 scenes). Passing it
        # explicitly avoids the +x fallback in PlumeState.spawn().
        object_velocity_ego_mps=np.zeros(3, dtype=np.float64),
    )


def select_frames(
    infos: list[dict], scenes: list[str], split: str, limit: int
) -> list[dict]:
    """Frames of ``scenes`` in per-scene timestamp order, capped at ``limit``."""
    by_scene: dict[str, list[dict]] = {scene: [] for scene in scenes}
    known = set(scenes)
    for info in infos:
        token = str(info["token"])
        for scene in known:
            if token.startswith(scene + "/"):
                by_scene[scene].append(info)
                break
    frames: list[dict] = []
    for scene in scenes:
        scene_infos = sorted(by_scene[scene], key=lambda item: item["timestamp"])
        if not scene_infos:
            raise SystemExit(
                f"GATE_C_FAILED split '{split}' scene {scene} has no frame in infos"
            )
        frames.extend(scene_infos)
    if limit and limit > 0:
        frames = frames[: int(limit)]
    return frames


def frame_indices(frames: list[dict]) -> list[int]:
    """Index of every frame inside its own scene, in the order of ``frames``."""
    counter: dict[str, int] = {}
    indices: list[int] = []
    for frame in frames:
        token = str(frame["token"])
        scene = token.rsplit("/", 1)[0]
        indices.append(counter.get(scene, 0))
        counter[scene] = counter.get(scene, 0) + 1
    return indices


# --------------------------------------------------------------------------
# Plume: call the production transform directly (not declared in any config).
# --------------------------------------------------------------------------
def make_plume_transform(args) -> PlumeTransform:
    wet_ground = WetGroundConfig(enabled=bool(args.wet_ground))
    return PlumeTransform(
        config=PlumeConfig(
            sample_water_film=bool(getattr(args, "sample_water_film", True)),
            water_film_mm=getattr(args, "wfh_mm", None),
        ),
        enabled=True,
        seed=int(args.seed),
        wet_ground=wet_ground,
    )


def inject_plume(
    transform: PlumeTransform,
    state: PlumeState,
    clean: np.ndarray,
    boxes: np.ndarray,
    context: PlumeContext,
    token: str,
    seed: int,
    *,
    sample_water_film: bool = True,
    water_film_mm: float | None = None,
) -> dict:
    """Run PlumeTransform on one frame and report what it changed."""
    transform.config = replace(
        transform.config,
        sample_water_film=bool(sample_water_film),
        water_film_mm=water_film_mm,
    )
    results = {
        "points": clean.copy(),
        "gt_bboxes_3d": boxes,
        "token": token,
        "metadata": {"token": token, "seed": int(seed)},
        "plume_context": context,
        "plume_state": state,
    }
    out = transform(results)
    points = np.asarray(out["points"], dtype=np.float32)
    stats = dict(out["spray_stats"])
    before = int(len(clean))
    # Trước A10 `n_injected` đếm điểm materialise `ring=-1` (vô hiệu với detector);
    # từ A10 nó là số detection plume thật (`raycast.stats.det`).
    after = int(len(points) - int(stats.get("det", 0)))
    clean_after = np.asarray(out["points_clean"], dtype=np.float32)
    return {
        "points": points,
        "stats": stats,
        "n_real_before": before,
        "n_real_after": max(0, after),
        "n_real_removed": max(0, before - max(0, after)),
        "n_real_attenuated": int(stats.get("att_real_points", 0)),
        "n_injected": int(stats.get("det", 0)),
        "clean_unchanged": bool(
            clean_after.shape == clean.shape and np.array_equal(clean_after, clean)
        ),
    }


# --------------------------------------------------------------------------
# Detector (all heavy imports inside)
# --------------------------------------------------------------------------
def load_model(config_name: str, checkpoint: Path, device: str, overrides: dict):
    import torch
    from mmcv import ConfigDict
    from mmdet3d.models import build_model

    cfg, chain = load_config(config_name, overrides)
    facts = config_facts(cfg)
    checks = validate_config_facts(facts)

    def to_config_dict(node):
        if isinstance(node, dict):
            return ConfigDict(
                (key, to_config_dict(value)) for key, value in node.items()
            )
        if isinstance(node, list):
            return [to_config_dict(value) for value in node]
        return node

    model = build_model(to_config_dict(cfg["model"]))
    state = _load_state_dict(checkpoint)
    load_report = check_checkpoint_vs_config(config_name, facts, state)
    result = model.load_state_dict(state, strict=False)

    def parameter_like(key: str) -> bool:
        return not (
            key.endswith("num_batches_tracked") or key.startswith("_")
        )

    missing = sorted(key for key in result.missing_keys if parameter_like(key))
    unexpected = sorted(key for key in result.unexpected_keys if parameter_like(key))
    load_report["missing"] = missing
    load_report["unexpected"] = unexpected
    if missing or unexpected:
        raise SystemExit(
            "GATE_C_FAILED checkpoint does not match the config exactly: "
            f"missing={missing[:8]} unexpected={unexpected[:8]} (full list in "
            "the kernel log). Refusing a partial/random model for gate C."
        )
    model.to(device)
    model.eval()
    return model, facts, {
        "chain": chain,
        "checks": checks,
        "checkpoint_load": load_report,
        "missing_keys": missing,
        "unexpected_keys": unexpected,
    }


def _to_numpy(value) -> np.ndarray:
    if hasattr(value, "tensor"):
        value = value.tensor
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def _as_box_array(value, columns: int = 9) -> np.ndarray:
    array = _to_numpy(value)
    if array.size == 0:
        return np.empty((0, columns), dtype=np.float32)
    return np.asarray(array, dtype=np.float32).reshape(-1, columns)


def detect(
    model,
    facts: dict,
    points: np.ndarray,
    device: str,
    legacy_channel4: bool = False,
    z_shift_m: float = 0.0,
) -> dict:
    import torch
    from mmdet3d.core.bbox import LiDARInstance3DBoxes

    # SỬA LỖI 2026-11-19 (chẩn đoán: docs/measurements/model0-blindness-diagnosis.md)
    # nuScenes/BEVFusion dùng cột 4 = **time-lag** trong [-0.5; 0]
    # (`mmdet3d/datasets/pipelines/loading.py:182` đặt 0 cho keyframe, `:223` đặt
    # `ts - sweep_ts` cho sweep). File .bin của SSPP có cột 4 = **ring** (0..31).
    # Nạp thẳng ring vào chỗ time-lag phá lớp conv đầu (trọng số kênh 4 của
    # checkpoint có RMS 0,874 / max|w| 15,15, gấp 7,4x / 16,6x các kênh khác):
    # activation bị đẩy 5-17 sigma và biến thiên theo không gian ⇒ model bắn box
    # quanh ego (98,5 % trong 5 m), TP = 0/954 frame, chỉ 4/954 frame score >= 0,2.
    # Với frame không có sweep, pipeline chuẩn đặt time-lag = 0 cho mọi điểm.
    cloud = np.array(points[:, :POINT_DIM], dtype=np.float32, copy=True)
    if cloud.ndim == 2 and cloud.shape[1] > 4 and not legacy_channel4:
        cloud[:, 4] = 0.0
        assert float(np.abs(cloud[:, 4]).max(initial=0.0)) < 1e-6
    if z_shift_m:
        # Covariate của phép đo này, không phải fix: mặt đường SSPP z=-0,38 so
        # với nuScenes z=-1,84 (docs/measurements/model0-blindness-diagnosis.md §4.1).
        cloud[:, 2] += np.float32(z_shift_m)
    tensor = torch.as_tensor(
        np.ascontiguousarray(cloud),
        dtype=torch.float32,
        device=device,
    )
    metas = [{"box_type_3d": LiDARInstance3DBoxes}]
    with torch.no_grad():
        outputs = model(
            points=[tensor],
            img=None,
            camera2ego=None,
            lidar2ego=None,
            lidar2camera=None,
            lidar2image=None,
            camera_intrinsics=None,
            img_aug_matrix=None,
            lidar_aug_matrix=None,
            metas=metas,
        )
    first = outputs[0]
    boxes = _as_box_array(first["boxes_3d"], 9)
    scores = _to_numpy(first["scores_3d"]).reshape(-1)
    labels = _to_numpy(first["labels_3d"]).reshape(-1).astype(np.int64)
    return {"boxes": boxes, "scores": scores, "labels": labels}


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def make_eval_config(args) -> EvalConfig:
    # Label-agnostic matching: SSPP has 2 classes (Car, Van) while the
    # checkpoint predicts its 10 nuScenes classes; gate C asks whether a
    # detection matches ANY ground-truth vehicle at BEV IoU >= 0.5.
    return EvalConfig(
        class_names=("object",),
        iou_threshold=float(args.iou_thresh),
        score_threshold=float(args.score_thresh),
        range_m=float(args.range_m),
    )


def score_detection(
    detection: dict, gt_boxes: np.ndarray, eval_config: EvalConfig
) -> dict:
    gt = np.asarray(gt_boxes, dtype=np.float64).reshape(-1, BOX_DIM)[:, :7]
    pred = np.asarray(detection["boxes"], dtype=np.float64).reshape(-1, 9)[:, :7]
    scores = np.asarray(detection["scores"], dtype=np.float64).reshape(-1)
    result = evaluate_frame(
        pred,
        scores,
        np.zeros(len(scores), dtype=np.int64),
        gt,
        np.zeros(len(gt), dtype=np.int64),
        eval_config,
    )
    return {
        "tp": int(result.tp),
        "fp": int(result.fp),
        "fn": int(result.fn),
        "recall": float(result.recall),
        "precision": float(result.precision),
        "n_pred": int(len(pred)),
    }


def summarize(records: list[dict], args, eval_config: EvalConfig) -> dict:
    thresholds = sorted({float(args.score_thresh), 0.1, 0.3, 0.5})
    speed_values = sorted({int(round(record["speed_kmh"])) for record in records})
    per_arm: dict[str, dict] = {}
    per_speed: dict[str, dict] = {}
    for arm in args.arms:
        arm_records = [record for record in records if record["arm"] == arm]
        if not arm_records:
            continue
        per_arm[arm] = _aggregate(arm_records, eval_config)
        per_speed[arm] = {}
        for speed in speed_values:
            group = [
                record
                for record in arm_records
                if int(round(record["speed_kmh"])) == speed
            ]
            if group:
                per_speed[arm][str(speed)] = _aggregate(group, eval_config)

    paired = {}
    if "plume" in per_arm and "clean" in per_arm:
        paired["plume_minus_clean"] = _paired(records, eval_config, seed=int(args.seed))

    threshold_sweep = {}
    for threshold in thresholds:
        config = EvalConfig(
            class_names=("object",),
            iou_threshold=float(args.iou_thresh),
            score_threshold=threshold,
            range_m=float(args.range_m),
        )
        sweep = {}
        for arm in args.arms:
            arm_records = [record for record in records if record["arm"] == arm]
            if arm_records:
                aggregate = _aggregate(arm_records, config)
                sweep[arm] = {
                    "fp_per_frame": aggregate["fp_per_frame"],
                    "recall": aggregate["recall"],
                    "n_frames": aggregate["n_frames"],
                }
        threshold_sweep[f"{threshold:.2f}"] = sweep

    return {
        "per_arm": per_arm,
        "per_speed_kmh": per_speed,
        "paired": paired,
        "threshold_sweep": threshold_sweep,
        "speed_groups": {
            str(speed): {
                "n_frames": sum(
                    1 for record in records
                    if int(round(record["speed_kmh"])) == speed
                    and record["arm"] == args.arms[0]
                ),
                "in_domain": speed > SPEED_OUT_OF_DOMAIN_KMH,
            }
            for speed in speed_values
        },
    }


def _aggregate(records: list[dict], eval_config: EvalConfig) -> dict:
    rows = [score_detection(record["detections"], record["gt_boxes"], eval_config)
            for record in records]
    n = len(rows)
    plume_rows = [row for row in rows]
    return {
        "n_frames": n,
        "tp_per_frame": float(np.mean([row["tp"] for row in rows])) if n else 0.0,
        "fp_per_frame": float(np.mean([row["fp"] for row in plume_rows])) if n else 0.0,
        "fn_per_frame": float(np.mean([row["fn"] for row in rows])) if n else 0.0,
        "recall": float(np.mean([row["recall"] for row in rows])) if n else 0.0,
        "precision": float(np.mean([row["precision"] for row in rows])) if n else 0.0,
        "n_real_before": int(sum(record["n_real_before"] for record in records)),
        "n_real_after": int(sum(record["n_real_after"] for record in records)),
        "n_real_removed": int(sum(record["n_real_removed"] for record in records)),
        "n_real_attenuated": int(
            sum(record["n_real_attenuated"] for record in records)
        ),
        "n_injected": int(sum(record["n_injected"] for record in records)),
        "n_noise_points": int(sum(record["n_noise_points"] for record in records)),
    }


def _paired(
    records: list[dict], eval_config: EvalConfig, seed: int = 0, n_boot: int = 2000
) -> dict:
    by_arm: dict[str, list[dict]] = {"clean": [], "plume": []}
    for record in records:
        if record["arm"] in by_arm:
            by_arm[record["arm"]].append(record)
    clean_rows = {
        (record["scene_token"], record["frame_idx"]): record
        for record in by_arm["clean"]
    }
    plume_rows = {
        (record["scene_token"], record["frame_idx"]): record
        for record in by_arm["plume"]
    }
    common = sorted(set(clean_rows) & set(plume_rows))
    if not common:
        return {"error": "no paired frames"}
    scene_fp_clean: dict[str, list[float]] = {}
    scene_fp_plume: dict[str, list[float]] = {}
    scene_recall_clean: dict[str, list[float]] = {}
    scene_recall_plume: dict[str, list[float]] = {}
    for key in common:
        clean = clean_rows[key]
        plume = plume_rows[key]
        scene = clean["scene_token"]
        clean_score = score_detection(clean["detections"], clean["gt_boxes"], eval_config)
        plume_score = score_detection(plume["detections"], plume["gt_boxes"], eval_config)
        scene_fp_clean.setdefault(scene, []).append(float(clean_score["fp"]))
        scene_fp_plume.setdefault(scene, []).append(float(plume_score["fp"]))
        scene_recall_clean.setdefault(scene, []).append(float(clean_score["recall"]))
        scene_recall_plume.setdefault(scene, []).append(float(plume_score["recall"]))

    def scene_mean(values: dict[str, list[float]]) -> dict[str, float]:
        return {scene: float(np.mean(items)) for scene, items in values.items()}

    fp_clean = scene_mean(scene_fp_clean)
    fp_plume = scene_mean(scene_fp_plume)
    recall_clean = scene_mean(scene_recall_clean)
    recall_plume = scene_mean(scene_recall_plume)
    scenes = sorted(fp_clean)
    if len(scenes) < 2:
        return {"error": f"paired delta needs >=2 scenes, got {len(scenes)}"}
    fp_delta = {scene: fp_plume[scene] - fp_clean[scene] for scene in scenes}
    recall_delta = {scene: recall_plume[scene] - recall_clean[scene] for scene in scenes}
    return {
        "n_paired_frames": len(common),
        "n_scenes": len(scenes),
        "fp_per_scene": {
            "clean": fp_clean,
            "plume": fp_plume,
            "delta_plume_minus_clean": fp_delta,
        },
        "fp_delta_bootstrap": scene_bootstrap(fp_delta, n=n_boot, seed=seed),
        "recall_per_scene": {
            "clean": recall_clean,
            "plume": recall_plume,
            "delta_plume_minus_clean": recall_delta,
        },
        "recall_delta_bootstrap": scene_bootstrap(
            recall_delta, n=n_boot, seed=seed
        ),
        "n_real_removed": int(
            sum(
                plume_rows[key]["n_real_removed"]
                for key in common
            )
        ),
        "n_real_before": int(
            sum(plume_rows[key]["n_real_before"] for key in common)
        ),
        "n_real_removed_fraction": float(
            sum(plume_rows[key]["n_real_removed"] for key in common)
            / max(1, sum(plume_rows[key]["n_real_before"] for key in common))
        ),
    }


# --------------------------------------------------------------------------
# Dry run (must work without mmcv / mmdet / mmdet3d)
# --------------------------------------------------------------------------
def dry_run(args) -> int:
    started = time.time()
    dataset_root = Path(args.dataset_root).resolve()
    infos_path = Path(args.infos).resolve()
    split_json = Path(args.split_json).resolve()
    checkpoint = Path(args.checkpoint).resolve()

    scenes = read_split(split_json, args.split)
    infos = read_infos(infos_path)
    frames = select_frames(infos, scenes, args.split, args.limit)
    indices = frame_indices(frames)
    print(
        f"GATE_C_DRY_RUN split={args.split} scenes={len(scenes)} "
        f"frames={len(frames)} arms={','.join(args.arms)} "
        f"per_arm={len(frames) * len(args.arms)}"
    )

    overrides = POINTPILLARS_OVERRIDES if args.config == "pointpillars" else None
    cfg, chain = load_config(args.config, overrides)
    facts = config_facts(cfg)
    checks = validate_config_facts(facts)
    print(f"GATE_C_CONFIG leaf={CONFIG_LEAVES[args.config]}")
    print("GATE_C_CONFIG_CHAIN " + " -> ".join(chain))
    print(
        "GATE_C_MODEL "
        f"encoder={facts['encoder_type']} fuser={facts['fuser']!r} "
        f"decoder={facts['decoder_type']}(in {facts['decoder_in_channels']}) "
        f"neck={facts['neck_type']} head={facts['head_type']} "
        f"head_in={facts['head_in_channels']} classes={facts['num_classes']} "
        f"proposals={facts['num_proposals']} test_grid={facts['test_grid']} "
        f"out_size_factor={facts['test_out_size_factor']}"
    )
    print(
        "GATE_C_RANGE "
        f"pcr={facts['point_cloud_range']} voxel={facts['voxel_size']} "
        f"crop={'none (native pcr of the checkpoint)' if args.config == 'model0' else '[0,64]x[-16,16] (pointpillars override)'}"
    )
    for check in checks:
        print("GATE_C_CHECK " + check)

    checkpoint_report = checkpoint_facts(checkpoint)
    print(
        "GATE_C_CHECKPOINT "
        f"path={checkpoint_report['path']} bytes={checkpoint_report['bytes']} "
        f"sha256={checkpoint_report['sha256']} "
        f"matches_expected={int(checkpoint_report['matches_expected'])}"
    )
    try:
        state = _load_state_dict(checkpoint)
        load_report = check_checkpoint_vs_config(args.config, facts, state)
        print(
            "GATE_C_CHECKPOINT_CONFIG "
            f"variant={load_report['variant']} decoder_in="
            f"{load_report.get('decoder_in_checkpoint')} head_in="
            f"{load_report.get('head_in_checkpoint')} classes="
            f"{load_report.get('num_classes_checkpoint')} ok=1"
        )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - torch may be absent on a laptop
        print(f"GATE_C_CHECKPOINT_CONFIG skipped ({type(exc).__name__}: {exc})")

    print(
        "GATE_C_SCORING "
        f"score_thresh={args.score_thresh} iou_thresh={args.iou_thresh} "
        f"range_m={args.range_m} min_score={args.min_score} "
        f"sweep=[0.10,{args.score_thresh:.2f},0.30,0.50]"
    )
    print(
        "GATE_C_PLUME "
        f"transform=spray.plume_transform.PlumeTransform seed={args.seed} "
        f"epoch={args.epoch} wfh_mm={args.wfh_mm} road_z_m={args.road_z_m} "
        f"wet_ground={int(args.wet_ground)} scenario=following "
        f"wfh_sampling={int(bool(args.sample_water_film))}"
    )

    speeds: dict[int, int] = {}
    for frame in frames:
        speeds[int(round(frame["ego_speed_kmh"]))] = (
            speeds.get(int(round(frame["ego_speed_kmh"])), 0) + 1
        )
    for speed in sorted(speeds):
        in_domain = "yes" if speed > SPEED_OUT_OF_DOMAIN_KMH else "NO (<=60 km/h, out of domain)"
        print(
            f"GATE_C_SPEED {speed}km/h frames={speeds[speed]} "
            f"in_domain={in_domain}"
        )

    # One-frame end-to-end plumbing check through the production plume path.
    sample = frames[0]
    rel_scene = str(sample["token"]).rsplit("/", 1)[0]
    points, clean, n_noise = clean_points(dataset_root, sample)
    if clean.shape[1] != POINT_DIM:
        raise SystemExit(f"GATE_C_FAILED point cloud has {clean.shape[1]} columns")
    boxes = np.asarray(sample["gt_boxes"], dtype=np.float32).reshape(-1, BOX_DIM)
    sample_index = indices[0]
    context = build_context(args, sample, rel_scene, sample_index, boxes)
    transform = make_plume_transform(args)
    state = PlumeState()
    seed = _frame_seed(rel_scene, sample_index, args.epoch, args.seed)
    injected = inject_plume(
        transform, state, clean, boxes, context, sample["token"], seed,
        sample_water_film=args.sample_water_film,
        water_film_mm=args.wfh_mm,
    )
    if not injected["clean_unchanged"]:
        raise SystemExit(
            "GATE_C_FAILED plume transform changed points_clean; pairing between "
            "arms would be broken"
        )
    if injected["n_real_before"] <= 0:
        raise SystemExit("GATE_C_FAILED clean cloud is empty")
    runtime = time.time() - started
    print(
        "GATE_C_PLUMB_OK "
        f"scene={rel_scene} frame={sample_index} "
        f"points={len(points)} noise={n_noise} clean={len(clean)} "
        f"injected={injected['n_injected']} "
        f"real_before={injected['n_real_before']} "
        f"real_after={injected['n_real_after']} "
        f"removed={injected['n_real_removed']} "
        f"attenuated={injected['n_real_attenuated']} "
        f"boxes={len(boxes)} live_clusters={len(state.all_alive())} "
        f"clean_unchanged=1"
    )
    print(
        "GATE_C_DRY_RUN_OK "
        f"runtime_s={runtime:.1f} "
        f"expected_inference_s={_expected_minutes(len(frames), len(args.arms)):.1f}min"
    )
    return 0


def _expected_minutes(n_frames: int, n_arms: int) -> float:
    # [ƯT] one forward of the 0.075 sparse model is ~0.10-0.20 s on a T4.
    return n_frames * n_arms * 0.15 / 60.0


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------
def _frame_seed(scene_token: str, frame_index: int, epoch: int, base_seed: int) -> int:
    """Same seed PlumeTransform would derive, so the dry run matches inference."""
    from spray.plume_context import seed_for

    return seed_for(scene_token, frame_index, epoch, base_seed)


def _device(requested: str) -> str:
    if requested != "auto":
        return requested
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def run(args) -> int:
    started = time.time()
    dataset_root = Path(args.dataset_root).resolve()
    infos_path = Path(args.infos).resolve()
    split_json = Path(args.split_json).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scenes = read_split(split_json, args.split)
    infos = read_infos(infos_path)
    frames = select_frames(infos, scenes, args.split, args.limit)
    if getattr(args, "tokens", None):
        # Ghim đúng frame cần đo (verify kênh 4 trên Kaggle): thay
        # cho --limit, để hai chế độ chạy trên cùng frame. Thứ tự giữ nguyên.
        wanted = [str(token) for token in args.tokens]
        by_token = {str(info["token"]): info for info in infos}
        missing = [token for token in wanted if token not in by_token]
        if missing:
            raise SystemExit(f"GATE_C_FAILED --tokens not in {infos_path}: {missing}")
        scene_set = set(scenes)
        unknown_scene = [
            token for token in wanted
            if str(token).rsplit("/", 1)[0] not in scene_set
        ]
        if unknown_scene:
            raise SystemExit(
                f"GATE_C_FAILED --tokens outside split {args.split!r}: {unknown_scene}"
            )
        frames = [by_token[token] for token in wanted]
    indices = frame_indices(frames)
    device = _device(args.device)
    if device == "cpu":
        raise SystemExit(
            "GATE_C_FAILED inference needs the compiled CUDA ops (Voxelization / "
            "spconv); run on a GPU machine (Kaggle T4), or pass --dry-run locally."
        )
    overrides = POINTPILLARS_OVERRIDES if args.config == "pointpillars" else None
    model, facts, model_report = load_model(args.config, checkpoint, device, overrides)
    print(
        "GATE_C_MODEL_OK "
        f"config={args.config} device={device} chain={len(model_report['chain'])} "
        f"checkpoint_variant={model_report['checkpoint_load']['variant']} "
        f"missing={len(model_report['missing_keys'])} "
        f"unexpected={len(model_report['unexpected_keys'])}"
    )
    eval_config = make_eval_config(args)
    transform = make_plume_transform(args)
    state = PlumeState()
    records: list[dict] = []
    print(
        "GATE_C_INPUT_MODE "
        f"legacy_channel4={int(bool(getattr(args, 'legacy_channel4', False)))} "
        f"z_shift_m={float(getattr(args, 'z_shift_m', 0.0)):.3f} "
        f"tokens={len(args.tokens) if getattr(args, 'tokens', None) else 0}"
    )
    order = sorted(range(len(frames)), key=lambda index: (
        str(frames[index]["token"]).rsplit("/", 1)[0], indices[index]
    ))
    started_inference = time.time()
    for position, index in enumerate(order):
        info = frames[index]
        rel_scene = str(info["token"]).rsplit("/", 1)[0]
        frame_idx = indices[index]
        points, clean, n_noise = clean_points(dataset_root, info)
        boxes = np.asarray(info["gt_boxes"], dtype=np.float32).reshape(-1, BOX_DIM)
        context = build_context(args, info, rel_scene, frame_idx, boxes)
        seed = _frame_seed(rel_scene, frame_idx, args.epoch, args.seed)
        common = {
            "scene_token": rel_scene,
            "frame_idx": frame_idx,
            "token": info["token"],
            "speed_kmh": float(info["ego_speed_kmh"]),
            "gt_boxes": boxes,
            "n_noise_points": int(n_noise),
        }
        for arm in args.arms:
            if arm == "clean":
                input_points = clean
                point_stats = {
                    "n_real_before": int(len(clean)),
                    "n_real_after": int(len(clean)),
                    "n_real_removed": 0,
                    "n_real_attenuated": 0,
                    "n_injected": 0,
                }
            elif arm == "plume":
                injected = inject_plume(
                    transform, state, clean, boxes, context, info["token"], seed,
                    sample_water_film=args.sample_water_film,
                    water_film_mm=args.wfh_mm,
                )
                input_points = injected["points"]
                point_stats = {
                    "n_real_before": injected["n_real_before"],
                    "n_real_after": injected["n_real_after"],
                    "n_real_removed": injected["n_real_removed"],
                    "n_real_attenuated": injected["n_real_attenuated"],
                    "n_injected": injected["n_injected"],
                }
            elif arm == "real":
                input_points = points
                point_stats = {
                    "n_real_before": int(len(points)),
                    "n_real_after": int(len(points)),
                    "n_real_removed": 0,
                    "n_real_attenuated": 0,
                    "n_injected": 0,
                }
            else:  # pragma: no cover - argparse restricts choices
                raise SystemExit(f"unknown arm {arm!r}")
            detection = detect(
                model,
                facts,
                input_points,
                device,
                legacy_channel4=bool(getattr(args, "legacy_channel4", False)),
                z_shift_m=float(getattr(args, "z_shift_m", 0.0)),
            )
            record = dict(common)
            record.update(point_stats)
            record["arm"] = arm
            record["detections"] = detection
            records.append(record)
        if args.log_every and (position + 1) % args.log_every == 0:
            elapsed = time.time() - started_inference
            print(
                "GATE_C_STEP "
                f"{position + 1}/{len(order)} scene={rel_scene} frame={frame_idx} "
                f"elapsed_s={elapsed:.1f}",
                flush=True,
            )
    summary = summarize(records, args, eval_config)

    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            detection = record["detections"]
            boxes = detection["boxes"]
            line = {
                "scene_token": record["scene_token"],
                "frame_idx": record["frame_idx"],
                "arm": record["arm"],
                "token": record["token"],
                "speed_kmh": record["speed_kmh"],
                "n_real_points_before": record["n_real_before"],
                "n_real_points_after": record["n_real_after"],
                "n_real_points_removed": record["n_real_removed"],
                "n_real_points_attenuated": record["n_real_attenuated"],
                "n_injected": record["n_injected"],
                "n_noise_points": record["n_noise_points"],
                "score_thresh": float(args.score_thresh),
                "boxes": [
                    {
                        "x": float(box[0]),
                        "y": float(box[1]),
                        "z": float(box[2]),
                        "dx": float(box[3]),
                        "dy": float(box[4]),
                        "dz": float(box[5]),
                        "yaw": float(box[6]),
                        "score": float(score),
                        "label": int(label),
                    }
                    for box, score, label in zip(
                        boxes, detection["scores"], detection["labels"]
                    )
                    if float(score) >= float(args.min_score)
                ],
            }
            handle.write(json.dumps(line) + "\n")

    summary_path = out_path.with_name(out_path.stem + "_summary.json")
    payload = {
        "generated_by": "scripts/sspp_infer.py",
        "argv": sys.argv,
        "config": args.config,
        "config_chain": model_report["chain"],
        "config_checks": model_report["checks"],
        "checkpoint": checkpoint_facts(checkpoint),
        "checkpoint_load": model_report["checkpoint_load"],
        "split": args.split,
        "scenes": len(scenes),
        "frames": len(frames),
        "arms": list(args.arms),
        "score_thresh": float(args.score_thresh),
        "score_thresh_is_primary": True,
        "iou_thresh": float(args.iou_thresh),
        "range_m": float(args.range_m),
        "seed": int(args.seed),
        "legacy_channel4": bool(getattr(args, "legacy_channel4", False)),
        "z_shift_m": float(getattr(args, "z_shift_m", 0.0)),
        "epoch": int(args.epoch),
        "wfh_mm": None if args.wfh_mm is None else float(args.wfh_mm),
        "road_z_m": float(args.road_z_m),
        "wet_ground": bool(args.wet_ground),
        "scenario": "following",
        "speed_out_of_domain_kmh": SPEED_OUT_OF_DOMAIN_KMH,
        "elapsed_s": round(time.time() - started, 1),
        "inference_s": round(time.time() - started_inference, 1),
        "summary": summary,
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"GATE_C_OUTPUT {out_path} lines={len(records)}")
    print(f"GATE_C_SUMMARY {summary_path}")
    for arm in args.arms:
        aggregate = summary["per_arm"].get(arm)
        if aggregate:
            print(
                f"GATE_C_ARM {arm} frames={aggregate['n_frames']} "
                f"fp_per_frame={aggregate['fp_per_frame']:.4f} "
                f"recall={aggregate['recall']:.4f} "
                f"tp_per_frame={aggregate['tp_per_frame']:.4f} "
                f"injected={aggregate['n_injected']} "
                f"real_removed={aggregate['n_real_removed']} "
                f"real_attenuated={aggregate['n_real_attenuated']}"
            )
    paired = summary["paired"].get("plume_minus_clean") if summary["paired"] else None
    if paired and "fp_delta_bootstrap" in paired:
        fp_boot = paired["fp_delta_bootstrap"]
        recall_boot = paired["recall_delta_bootstrap"]
        print(
            "GATE_C_PAIRED "
            f"scenes={paired['n_scenes']} frames={paired['n_paired_frames']} "
            f"fp_delta_mean={fp_boot['mean']:.4f} "
            f"fp_delta_ci95=[{fp_boot['lo']:.4f},{fp_boot['hi']:.4f}] "
            f"recall_delta_mean={recall_boot['mean']:.4f} "
            f"recall_delta_ci95=[{recall_boot['lo']:.4f},{recall_boot['hi']:.4f}] "
            f"real_removed_fraction={paired['n_real_removed_fraction']:.4f}"
        )
    print(
        "GATE_C_OK "
        f"frames={len(frames)} arms={len(args.arms)} elapsed_s={time.time() - started:.1f}"
    )
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate C: paired clean/plume/real inference of the LiDAR-only "
        "BEVFusion baseline on SemanticSpray++.",
    )
    parser.add_argument("--config", choices=sorted(CONFIG_LEAVES), default="model0")
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    parser.add_argument("--infos", default=None,
                        help="defaults to data/sspp_infos_<split>.pkl")
    parser.add_argument("--split-json", default=str(DEFAULT_SPLIT_JSON))
    parser.add_argument("--split", default="test")
    parser.add_argument("--arms", nargs="+", choices=list(ARMS),
                        default=["clean", "plume", "real"])
    parser.add_argument("--limit", type=int, default=0,
                        help="max frames total; 0 = whole split")
    parser.add_argument("--out", default="gate_c_detections.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--score-thresh", type=float, default=0.20,
                        help="primary tau; pre-registered before the run")
    parser.add_argument("--min-score", type=float, default=0.05,
                        help="write detections down to this score (offline sweep)")
    parser.add_argument("--iou-thresh", type=float, default=0.5)
    parser.add_argument("--range-m", type=float, default=54.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--wfh-mm", dest="wfh_mm", default=None,
                        type=lambda s: None if s.lower() in ("none", "") else float(s),
                        help="[CHỌN] water film height (mm); 'none'/bỏ trống ⇒ lấy "
                             "mẫu theo scene [PAPER §V]")
    parser.add_argument("--no-wfh-sampling", dest="sample_water_film",
                        action="store_false", default=True,
                        help="tắt lấy mẫu mức ẩm, giữ wfh_mm của caller")
    parser.add_argument("--road-z-m", type=float, default=-0.411,
                        help="ground plane z in the LiDAR frame (PROJECT.md §3)")
    parser.add_argument("--wet-ground", dest="wet_ground", action="store_true",
                        default=True,
                        help="run the Hahner wet-ground stage (arm B uses it)")
    parser.add_argument("--no-wet-ground", dest="wet_ground", action="store_false",
                        help="disable the wet-ground stage (sensitivity only)")
    parser.add_argument("--paper-domain", dest="paper_domain", action="store_true",
                        default=False,
                        help="[DEPRECATED, no-op] miền paper giờ là default của "
                             "PlumeStateConfig; cờ chỉ giữ để kernel cũ chạy được")
    parser.add_argument("--legacy-channel4", dest="legacy_channel4",
                        action="store_true",
                        help="tái hiện lỗi cũ: nạp thẳng cột 4 của file .bin "
                             "(ring 0..31) vào chỗ time-lag của nuScenes; mặc "
                             "định là zero hoá cột 4 như pipeline chuẩn")
    parser.add_argument("--z-shift-m", type=float, default=0.0,
                        help="chẩn đoán covariate độ cao: cộng giá trị này vào "
                             "z trước khi vào detector (thử -1.45)")
    parser.add_argument("--tokens", nargs="+", default=None,
                        help="chỉ chạy đúng các frame token này (thay --limit)")
    parser.add_argument("--log-every", type=int, default=50)
    args = parser.parse_args(argv)
    if getattr(args, "paper_domain", False):
        print(
            "WARN --paper-domain is deprecated and has no effect; the paper "
            "domain is now the PlumeStateConfig default",
            file=sys.stderr,
        )
    if args.infos is None:
        args.infos = str(REPO / "data" / f"sspp_infos_{args.split}.pkl")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.dry_run:
            return dry_run(args)
        return run(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - one clear failure line for the log
        import traceback

        traceback.print_exc()
        print(f"GATE_C_FAILED {type(exc).__name__}: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
