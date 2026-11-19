#!/usr/bin/env python3
"""Debug một frame: GT vs detection, nhãn và IoU thô."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path("/Users/huynguyen/projects/bevfusion-spray-pilot")
sys.path.insert(0, str(REPO))

from proxy_eval.matcher import bev_iou  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays, read_frame_boxes, read_metadata,
)

SCENE = "Crafter_dynamic/0000_2021-09-08-14-36-56_0"
FRAME = 0
ROOT = REPO / "data/SemanticSprayDataset"
JSONL = REPO / ".scratch/diag/a7/gate_c_out/gate_c_detections.jsonl"


def main() -> None:
    path = ROOT / SCENE
    scan = sorted(p.stem for p in (path / "velodyne").glob("*.bin"))[FRAME]
    meta = read_metadata(path / "metadata.txt")
    obj_v = float(meta["object_velocity"]) / 3.6
    raw = read_frame_boxes(path / "object_labels" / "lidar" / f"{scan}.json")
    print(f"scan={scan}  raw type={type(raw)}  n={len(raw)}")
    print(f"raw[0] = {json.dumps(raw[0] if isinstance(raw, list) else raw, default=str)[:600]}")

    boxes, labels, extra = _boxes_to_arrays(raw, obj_v)
    print(f"\nGT boxes shape={boxes.shape}")
    for index in range(len(boxes)):
        print(f"  gt[{index}] {np.round(boxes[index], 3)}  label={labels[index]!r}")
    if extra is not None:
        print(f"  extra keys: {list(extra)[:5] if hasattr(extra, 'keys') else type(extra)}")

    record = None
    with JSONL.open() as handle:
        for line in handle:
            row = json.loads(line)
            if (row["scene_token"] == SCENE and row["frame_idx"] == FRAME
                    and row["arm"] == "clean"):
                record = row
                break
    assert record is not None
    print(f"\ndetections (clean) n={len(record['boxes'])}")
    for box in record["boxes"][:6]:
        print(f"  det {box['label']!r:>8} x={box['x']:7.2f} y={box['y']:7.2f} z={box['z']:6.2f} "
              f"dx={box['dx']:5.2f} dy={box['dy']:5.2f} dz={box['dz']:5.2f} "
              f"yaw={box['yaw']:+.2f} score={box['score']:.3f}")

    print("\nIoU GT x moi detection cung nhan:")
    for index in range(len(boxes)):
        target = str(labels[index])
        arr = np.array([box_ for box_ in boxes[index]], dtype=float)
        for box in record["boxes"]:
            if str(box["label"]) != target:
                continue
            det = np.array([box["x"], box["y"], box["z"], box["dx"], box["dy"],
                            box["dz"], box["yaw"]], dtype=float)
            iou = bev_iou(det, arr)
            if iou > 0.05:
                print(f"  gt{index}({target}) vs det: IoU={iou:.3f}  "
                      f"gt=[{arr[0]:.2f},{arr[1]:.2f}] det=[{det[0]:.2f},{det[1]:.2f}]")


if __name__ == "__main__":
    main()
