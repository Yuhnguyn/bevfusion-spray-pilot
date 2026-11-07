"""Ticket 06: evaluator adapter evidence - real MIT output on real frames.

Runs `step_eval_frame.py` in the pinned Python 3.8 venv. It reuses the model
and checkpoint from the cells above and the val infos written by cell 17.
The raw tensors are consumed by proxy_eval/mit_adapter.py locally.

Primary frame: most in-range GT under the MIT loader filter (num_lidar_pts>0).
Secondary frame: index 0 of the timestamp-sorted val infos (ticket 04 sample).
"""

import json
import os
import sys

WORK = os.environ.get("SMOKE_WORK", "/kaggle/working/smoke_test")
sys.path.insert(0, WORK)
import smoke_common as sc  # noqa: E402

STEP = r'''
"""Ticket 06: run the pinned model on real val frames and save its raw output.

The adapter and the evaluator stay on the local machine; this step only proves
the model really runs on a real frame and records the exact tensors it returns.

Primary frame: the val frame with the most in-range GT under the MIT loader
filter (num_lidar_pts > 0), tie-broken by token. Secondary frame: index 0 of the
timestamp-sorted val infos, i.e. the frame ticket 04 loaded.
"""

import json
import os
import sys

os.chdir("/kaggle/working")
sys.path.insert(0, os.environ["WORK"])
sys.path.insert(0, os.path.join(os.environ["WORK"], "scripts"))

import numpy as np
import torch
from mmcv import ConfigDict
from mmcv.parallel import DataContainer, collate, scatter

# numba 0.58 removed ``numba.errors``; the pinned dataset pipeline imports it.
try:
    import numba.errors  # noqa: F401
except Exception:
    try:
        from numba.core import errors as _numba_core_errors
        import types as _types

        _shim = _types.ModuleType("numba.errors")
        _shim.NumbaPerformanceWarning = _numba_core_errors.NumbaPerformanceWarning
        sys.modules["numba.errors"] = _shim
    except Exception:
        pass

from mmdet3d.datasets import build_dataset  # noqa: E402

import smoke_cfg  # noqa: E402
import smoke_model  # noqa: E402

PRIMARY_TOKEN = "f56a544064a548a39a81f18cc8f633c5"
SECONDARY_INDEX = 0
ART = os.environ["ART"]
PROVENANCE = {
    "source": "kaggle kernel nguynhuy9669/bevfusion-smoke-test",
    "pin": "da93b27",
    "checkpoint_sha256": "ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122",
}

# mmdet3d/datasets/nuscenes_dataset.py:112-123 at da93b27.
MIT_CLASSES = [
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
]

cfg, files = smoke_cfg.load(os.environ["CONFIG_PATH"])
dataset_cfg = ConfigDict(cfg["data"]["val"])
dropped = []
if not dataset_cfg.get("modality", {}).get("use_map", False):
    kept = []
    for transform in dataset_cfg["pipeline"]:
        if transform.get("type") == "LoadBEVSegmentation":
            dropped.append(transform["type"])
        else:
            kept.append(transform)
    dataset_cfg["pipeline"] = kept
    for transform in dataset_cfg["pipeline"]:
        if transform.get("type") == "Collect3D" and "keys" in transform:
            cleaned = [key for key in transform["keys"] if key != "gt_masks_bev"]
            if len(cleaned) != len(transform["keys"]):
                dropped.append("Collect3D.gt_masks_bev")
            transform["keys"] = cleaned

dataset = build_dataset(dataset_cfg)
infos = dataset.data_infos
tokens = [str(info["token"]) for info in infos]
assert PRIMARY_TOKEN in tokens, "primary token missing from val infos"
primary_index = tokens.index(PRIMARY_TOKEN)
assert SECONDARY_INDEX < len(infos)

model, build_info = smoke_model.build(cfg["model"], device="cuda")
ckpt = smoke_model.load_checkpoint(model, os.environ["CKPT_PATH"], device="cuda")
assert ckpt["ok"], "checkpoint did not load cleanly: %r" % (ckpt,)


def info_record(info):
    return {
        "_provenance": dict(PROVENANCE, selection="val infos record used for this frame"),
        "token": str(info["token"]),
        "timestamp": int(info["timestamp"]),
        "lidar_path": str(info["lidar_path"]),
        "gt_boxes": np.asarray(info["gt_boxes"], dtype=float).tolist(),
        "gt_names": [str(name) for name in info["gt_names"]],
        "valid_flag": np.asarray(info["valid_flag"]).astype(bool).tolist(),
        "num_lidar_pts": np.asarray(info["num_lidar_pts"]).astype(int).tolist(),
    }


def run_frame(index):
    data = dataset[index]
    points = data["points"].data if hasattr(data["points"], "data") else data["points"]
    image = data["img"].data if hasattr(data["img"], "data") else data["img"]
    num_points = int(points.shape[0])

    batch = collate([data], samples_per_gpu=1)
    scattered = scatter(batch, [torch.cuda.current_device()], dim=0)
    # mmcv.parallel.scatter returns one entry per target GPU.
    if isinstance(scattered, (list, tuple)) and len(scattered) == 1:
        batch = scattered[0]
    else:
        batch = scattered
    batch = {
        key: (value.data if isinstance(value, DataContainer) else value)
        for key, value in batch.items()
    }
    with torch.no_grad():
        result = model(**batch)

    detection = result[0]
    boxes = detection["boxes_3d"].tensor.detach().cpu().numpy()
    scores = detection["scores_3d"].detach().cpu().numpy()
    labels = detection["labels_3d"].detach().cpu().numpy().astype(np.int64)
    assert len(boxes) == len(scores) == len(labels), "detection lengths differ"
    assert np.isfinite(boxes).all(), "non-finite box coordinate"
    assert np.isfinite(scores).all(), "non-finite score"
    assert labels.min(initial=0) >= 0, "negative class index"
    assert labels.max(initial=0) < len(MIT_CLASSES), "class index outside MIT list"

    raw = {
        "_provenance": dict(
            PROVENANCE,
            frame_token=str(infos[index]["token"]),
            note="raw boxes_3d/scores_3d/labels_3d returned by BEVFusion.forward",
        ),
        "token": str(infos[index]["token"]),
        "class_names": MIT_CLASSES,
        "boxes_3d": boxes[:, :7].astype(float).tolist(),
        "scores_3d": scores.astype(float).tolist(),
        "labels_3d": labels.tolist(),
    }
    summary = {
        "index": index,
        "token": str(infos[index]["token"]),
        "num_gt_raw": int(len(infos[index]["gt_boxes"])),
        "num_sweeps": int(len(infos[index].get("sweeps", []))),
        "num_points": num_points,
        "img_shape": list(image.shape),
        "predictions": int(len(boxes)),
        "score_max": float(scores.max()) if len(scores) else None,
        "predictions_ge_0_05": int((scores >= 0.05).sum()),
        "label_histogram": {
            MIT_CLASSES[label]: int((labels == label).sum())
            for label in sorted(set(labels.tolist()))
        },
    }
    return raw, summary


primary_raw, primary_summary = run_frame(primary_index)
secondary_raw, secondary_summary = run_frame(SECONDARY_INDEX)


def dump(name, payload):
    path = os.path.join(ART, name)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1)
    print("wrote " + path)
    return path


dump("real_frame_detections.json", primary_raw)
dump("real_frame_eval_info.json", info_record(infos[primary_index]))
dump("real_frame_range_detections.json", secondary_raw)
dump("real_frame_range_info.json", info_record(infos[SECONDARY_INDEX]))

summary = {
    "status": "ok",
    "primary": primary_summary,
    "secondary": secondary_summary,
    "class_names": MIT_CLASSES,
    "num_infos": len(infos),
    "use_valid_flag": bool(dataset.use_valid_flag),
    "dropped_transforms": dropped,
    "config_files": files,
    "checkpoint": {"ok": bool(ckpt["ok"]), "sha256": ckpt["sha256"]},
    "build": {"init_cfg_disabled": bool(build_info["init_cfg_disabled"])},
    "torch": torch.__version__,
}
dump("eval_frame.json", summary)
print(json.dumps(summary, indent=1))
print("TICKET06_OK")

'''

sc.write_script("step_eval_frame.py", STEP)
rc, text = sc.run_script("step_eval_frame.py", log_name="step_eval_frame.log", timeout=3600)
report = sc.load_json("eval_frame.json")
print()
print("rc = %d" % rc)
for key in ("primary", "secondary"):
    entry = report.get(key, {})
    print("%-9s token=%s gt=%s preds=%s max_score=%s ge0.05=%s"
          % (key, entry.get("token"), entry.get("num_gt_raw"),
             entry.get("predictions"), entry.get("score_max"),
             entry.get("predictions_ge_0_05")))
print("class_names: %s" % json.dumps(report.get("class_names")))
print("TICKET06_OK" if "TICKET06_OK" in text else "TICKET06_FAILED (see logs/step_eval_frame.log)")
