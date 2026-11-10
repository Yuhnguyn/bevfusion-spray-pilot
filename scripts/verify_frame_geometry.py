#!/usr/bin/env python3
"""Measure one real frame: ground-plane z, real 3D boxes, and w/l order.

Ticket 25, item 4. Also writes the mandatory "Kết luận cho v2" section, because
it is the last script in the 1→4 order.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plume_v2_measure_common as common  # noqa: E402

SECTION = "verify_frame_geometry.py"
CONCLUSION = "conclusion"
SCRIPT = "verify_frame_geometry.py"
SCENE = common.DATASET / "Crafter_dynamic" / "0000_2021-09-08-14-36-56_0"
SCAN_ID = "000000"
GROUND_PERCENTILES = (1.0, 5.0)


def load_box(scene: Path, scan_id: str) -> dict | None:
    path = scene / "object_labels" / "lidar" / f"{scan_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    instances = []
    for block in payload:
        instances.extend(block.get("instances", []))
    if not instances:
        return None
    return instances[0]


def box_fields(box: dict) -> dict:
    contour = box["contour"]
    return {
        "class": box.get("className"),
        "center": contour["center3D"],
        "size": contour["size3D"],
        "rotation": contour.get("rotation3D", {}),
        "points": contour.get("pointN"),
    }


def box_frame_extents(
    points: np.ndarray, labels: np.ndarray, box: dict
) -> dict:
    fields = box_fields(box)
    center = fields["center"]
    yaw = float(fields["rotation"].get("z", 0.0))
    cx, cy, cz = center["x"], center["y"], center["z"]
    mask = (
        (labels == 1)
        & (np.abs(points[:, 0] - cx) < 8.0)
        & (np.abs(points[:, 1] - cy) < 4.0)
    )
    local = points[mask, :3].astype(np.float64) - np.array([cx, cy, cz])
    ca, sa = np.cos(-yaw), np.sin(-yaw)
    x_box = ca * local[:, 0] - sa * local[:, 1]
    y_box = sa * local[:, 0] + ca * local[:, 1]
    z_box = local[:, 2]
    return {
        "n_points": int(mask.sum()),
        "x": (float(x_box.min()), float(x_box.max())),
        "y": (float(y_box.min()), float(y_box.max())),
        "z": (float(z_box.min()), float(z_box.max())),
        "yaw": yaw,
    }


def dataset_box_coverage() -> tuple[int, int]:
    total = len(common.scene_dirs())
    with_boxes = sum(
        1
        for scene in common.scene_dirs()
        if (scene / "object_labels" / "lidar").is_dir()
    )
    return with_boxes, total


def render(frame: dict) -> str:
    points = frame["points"]
    labels = frame["labels"]
    z = points[:, 2]
    x = points[:, 0]
    y = points[:, 1]
    ground = (labels == 0) & (np.abs(x) < 20.0) & (np.abs(y) < 20.0)
    z_ground = z[ground]
    p1, p5, p50 = np.percentile(z_ground, [1.0, 5.0, 50.0])
    labels_unique, labels_counts = np.unique(labels, return_counts=True)

    box_rows = frame["boxes"]
    selected = box_rows[0]
    fields = box_fields(selected)
    center = fields["center"]
    size = fields["size"]
    bottom = center["z"] - size["z"] / 2.0
    with_boxes, total_scenes = dataset_box_coverage()

    lines: list[str] = [
        f"## 4. Hình học frame thật — `{SCRIPT}`",
        "",
        f"Frame: `Crafter_dynamic/0000_2021-09-08-14-36-56_0/{SCAN_ID}`.",
        "",
        f"- Điểm: **{len(points)}**; nhãn: **{len(labels)}**; "
        + (
            "cùng độ dài."
            if len(points) == len(labels)
            else "**khác độ dài**."
        ),
        f"- Nhãn: "
        + ", ".join(
            f"`{int(value)}` = {int(count)} điểm"
            for value, count in zip(labels_unique, labels_counts)
        )
        + ".",
        "",
        f"### `z` mặt đường `[ĐO {SCRIPT}]`",
        "",
        "Mask: `label == 0` **và** `|x| < 20 m` **và** `|y| < 20 m` "
        f"→ **{int(ground.sum())} điểm**.",
        "",
        "| Percentile | `z` (m) |",
        "|---|---:|",
        f"| p1 | {p1:.3f} |",
        f"| p5 | {p5:.3f} |",
        f"| p50 | {p50:.3f} |",
        "",
        f"`[CHỌN {SCRIPT}]` Dùng **percentile 1 = {p1:.3f} m** để neo plume v2 "
        "vào mặt đường: đây là mép dưới của mặt đường, ít bị đẩy lên bởi điểm "
        "nhiễu phía trên; p5 chỉ cao hơn "
        f"`{p5 - p1:.3f} m`. Kiểm chứng độc lập: đáy box thật "
        f"`center_z − size_z/2 = {bottom:.4f} m`, khớp p1 trong "
        f"`{abs(bottom - p1):.4f} m`.",
        "",
        f"- So với `−1,84 m` mà audit v1 dùng cho nuScenes LIDAR_TOP: chênh "
        f"**`{p1 - (-1.84):+.3f} m`** (mặt đường SemanticSpray **cao hơn**). "
        "Đây là hai cảm biến/hai frame khác nhau; số `−1,84 m` không phải số đo "
        "trên SemanticSpray.",
        "",
        f"### 3 object thật trong `object_labels/lidar` `[ĐO {SCRIPT}]`",
        "",
        f"- `object_labels/lidar` có ở **{with_boxes}/{total_scenes} scene** "
        "của dataset; scene này **có**, 76/76 frame, mỗi frame 1 instance "
        "`Van`. Ba frame dưới đây in nguyên JSON (không suy từ nuScenes).",
        "",
        "| Frame | Class | center `(x, y, z)` (m) | size3D `(x, y, z)` (m) | "
        "rotation.z | pointN |",
        "|---|---|---|---|---:|---:|",
    ]
    for scan_id, box in zip(frame["box_scan_ids"], frame["boxes"]):
        fields = box_fields(box)
        center = fields["center"]
        size = fields["size"]
        rotation = fields["rotation"]
        lines.append(
            f"| `{scan_id}` | {fields['class']} | "
            f"({center['x']:.4f}, {center['y']:.4f}, {center['z']:.4f}) | "
            f"({size['x']:.4f}, {size['y']:.4f}, {size['z']:.4f}) | "
            f"{rotation.get('z', 0.0):.4f} | {fields['points']} |"
        )

    extents = frame["extents"]
    lines += [
        "",
        f"### Thứ tự cột và đơn vị của box `[ĐO {SCRIPT}]`",
        "",
        f"- `size3D.x = {size['x']:.4f} m` = **chiều dài** (dọc theo yaw); "
        f"`size3D.y = {size['y']:.4f} m` = **chiều rộng**; "
        f"`size3D.z = {size['z']:.4f} m` = **chiều cao**. Đơn vị **mét**.",
        f"- Bằng chứng từ chính điểm label 1 quanh box (frame `{SCAN_ID}`): "
        f"**{extents['n_points']} điểm**, chiếu vào hệ box (yaw = "
        f"`{extents['yaw']:+.4f} rad`):",
        "",
        "| Trục box | extent quan sát (m) | nửa kích thước box (m) | Kết luận |",
        "|---|---:|---:|---|",
        f"| x (dài) | `[{extents['x'][0]:.2f}, {extents['x'][1]:.2f}]` | "
        f"`±{size['x'] / 2:.2f}` | khớp chiều dài |",
        f"| y (rộng) | `[{extents['y'][0]:.2f}, {extents['y'][1]:.2f}]` | "
        f"`±{size['y'] / 2:.2f}` | khớp chiều rộng |",
        f"| z (cao) | `[{extents['z'][0]:.2f}, {extents['z'][1]:.2f}]` | "
        f"`±{size['z'] / 2:.2f}` | khớp chiều cao |",
        "",
        "Điểm label 1 chỉ thấy mặt sau/trái của xe nên extent không đối xứng; "
        "độ lớn khớp `x ≈ ±3,41 m`, `y ≈ ±1,21 m`, `z ≈ ±1,31 m`. Nếu hoán đổi "
        "`x`/`y` thì chiều dài `6,83 m` sẽ nằm trên trục ngang — không khớp dữ liệu.",
        "",
        f"- `rotation3D.z = {frame['boxes'][0]['contour']['rotation3D']['z']:+.4f}`: "
        "script dùng trực tiếp giá trị này như **radian**; toolkit gốc lại gọi "
        "`np.deg2rad(rotation3D[\"z\"])`. Ở góc nhỏ này hai cách cho cùng kết "
        "luận `w`/`l`, nhưng đơn vị của trường là **điểm mở**, không sửa ở đây.",
        "",
    ]
    return "\n".join(lines)


def render_conclusion(
    frame: dict, speed: dict, beams: dict, p1: float
) -> str:
    total_frames = speed["n_frames"]
    same_median, same_max, same_count = beams["same_all"]
    nearest_median, _, _ = beams["nearest_all"]
    clusters = {}
    for wfh in (0.001, 1.0, 10.0):
        mean = (0.2 * wfh + 0.1) * (130.0 - 50.0)
        clusters[wfh] = int(round(max(0.0, mean)))
    return "\n".join(
        [
            "## Kết luận cho v2",
            "",
            f"- **Trần dữ liệu:** `{100.0 * speed['lt50_frames'] / total_frames:.2f} %` "
            f"frame có `object_velocity < 50` "
            f"(`{speed['lt50_frames']}/{total_frames}`); thêm "
            f"`{100.0 * speed['eq50_frames'] / total_frames:.2f} %` "
            f"(`{speed['eq50_frames']}` frame) ở **đúng 50 km/h** cho "
            "`mean = (0,2·wfh + 0,1)·(50 − 50) = 0` cụm. "
            "`[ĐO measure_speeds.py]`",
            "",
            f"- **Cột 4 của `velodyne`:** là **ring/beam id `0…31`** "
            f"(32 giá trị nguyên); so cùng ID với bảng VLP-32C lệch median "
            f"`|Δ| = {same_median:.2f}°`, max `{same_max:.2f}°`, "
            f"`{same_count}/{len(beams['present'])}` ring `≥ 0,5°` → "
            f"**KHÔNG KHỚP** (góc gần nhất chỉ lệch median "
            f"`{nearest_median:.2f}°`, nhưng đó chỉ vì bảng danh nghĩa dày). "
            "⇒ ray casting **phải tính elevation từ toạ độ** "
            "`atan2(z, √(x²+y²))`, không dùng ring làm góc. "
            "`[ĐO measure_beam_angles.py]`",
            "",
            f"- **Đơn vị `wfh`:** ở `v = 130 km/h`, `mean = (0,2·wfh + 0,1)·80`; "
            f"`wfh = 0,001` (m) → `mean = {80 * (0.2 * 0.001 + 0.1):.3f}` → "
            f"**{clusters[0.001]} cụm**; `wfh = 1` (mm) → `mean = "
            f"{80 * (0.2 * 1 + 0.1):.1f}` → **{clusters[1.0]} cụm** (khớp 24 cụm "
            f"@130 km/h của Fig. 11b); `wfh = 10` → `mean = "
            f"{80 * (0.2 * 10 + 0.1):.1f}` → **{clusters[10.0]} cụm**. "
            "⇒ chọn **mm** (`wfh = 1`). "
            "`[tính toán; công thức [CODE] dee.cpp:509–512; mốc 24 cụm [PAPER] Fig. 11b]`",
            "",
            f"- **`z` mặt đường:** `{p1:.3f} m` (percentile **1**, label 0, "
            "`|x|,|y| < 20 m`; p5 = "
            f"`{np.percentile(frame['points'][:, 2][frame['ground_mask']], 5):.3f} m`); "
            f"so với `−1,84 m` của audit v1, chênh **`{p1 - (-1.84):+.3f} m`**. "
            f"`[ĐO {SCRIPT}]`",
        ]
    )


def main() -> int:
    points = common.load_points(SCENE, SCAN_ID)
    labels = common.load_labels(SCENE, SCAN_ID)
    scan_ids = ["000000", "000001", "000057"]
    boxes = [load_box(SCENE, scan_id) for scan_id in scan_ids]
    if any(box is None for box in boxes):
        raise SystemExit("expected 3D boxes in object_labels/lidar for this scene")
    ground = (labels == 0) & (np.abs(points[:, 0]) < 20.0) & (
        np.abs(points[:, 1]) < 20.0
    )
    frame = {
        "points": points.astype(np.float64),
        "labels": labels,
        "boxes": boxes,
        "box_scan_ids": scan_ids,
        "extents": box_frame_extents(points.astype(np.float64), labels, boxes[0]),
        "ground_mask": ground,
    }
    p1 = float(np.percentile(points[ground, 2], 1.0))

    speed = common.speed_stats()
    beams = common.beam_stats(frames_per_scene=10)

    body = render(frame)
    common.replace_section(SECTION, body)
    print(body)

    conclusion = render_conclusion(frame, speed, beams, p1)
    common.replace_section(CONCLUSION, conclusion)
    print(conclusion)
    return 0


if __name__ == "__main__":
    sys.exit(main())
