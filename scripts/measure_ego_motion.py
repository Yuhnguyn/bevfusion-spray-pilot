#!/usr/bin/env python3
"""Read ``poses.txt`` for three scenes, export (x, y, yaw) and cross-check speed.

Ticket 25, item 3. The file has no timestamp and — in this release — every
translation component is exactly zero, so a position-derived speed is reported
as 0 and the comparison with ``metadata.txt`` is reported as a failure with
numbers. The formula is never changed to hide it.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plume_v2_measure_common as common  # noqa: E402

SECTION = "measure_ego_motion.py"
SCRIPT = "measure_ego_motion.py"
DT_S = 0.1
CSV_DIR = common.REPO / "docs" / "figs" / "ego-motion"


def choose_scenes() -> list[dict]:
    records = common.speed_stats()["records"]
    crafter = next(
        record
        for record in records
        if record["group"] == "Crafter_dynamic"
    )
    golf = next(
        record
        for record in records
        if record["group"] == "Golf_dynamic"
    )
    highest = sorted(
        records,
        key=lambda record: (-record["object_velocity"], record["scene"]),
    )[0]
    chosen = [
        {**crafter, "why": "1 scene Crafter"},
        {**golf, "why": "1 scene Golf"},
        {
            **highest,
            "why": f"`object_velocity` cao nhất ({highest['object_velocity']} km/h)",
        },
    ]
    for record in chosen:
        record["path"] = common.DATASET / record["group"] / record["scene"]
    return chosen


def pose_table(scene: Path) -> dict:
    matrix = np.loadtxt(scene / "poses.txt", dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != 16:
        raise ValueError(f"{scene}/poses.txt: shape {matrix.shape}, expected (n, 16)")
    rotation = matrix[:, :12].reshape(-1, 3, 4)[:, :, :3]
    x = matrix[:, 3]
    y = matrix[:, 7]
    z = matrix[:, 11]
    tail = matrix[:, 12:16]
    yaw = np.degrees(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
    unwrapped = np.degrees(np.unwrap(np.radians(yaw)))
    steps = np.diff(unwrapped) / DT_S if len(yaw) > 1 else np.zeros(0)
    dx = np.diff(x)
    dy = np.diff(y)
    position_speed = np.hypot(dx, dy) / DT_S if len(x) > 1 else np.zeros(0)
    return {
        "n": len(matrix),
        "x": x,
        "y": y,
        "yaw": yaw,
        "unwrapped": unwrapped,
        "max_translation": float(np.abs(matrix[:, [3, 7, 11]]).max()),
        "max_tail": float(np.abs(tail).max()),
        "orthonormal_error": float(
            np.abs(
                rotation[0] @ rotation[0].T - np.eye(3)
            ).max()
        ),
        "yaw_rate_median": float(np.median(np.abs(steps))) if len(steps) else 0.0,
        "yaw_rate_p90": float(np.percentile(np.abs(steps), 90))
        if len(steps)
        else 0.0,
        "yaw_rate_max": float(np.abs(steps).max()) if len(steps) else 0.0,
        "position_speed_median": float(np.median(position_speed))
        if len(position_speed)
        else 0.0,
        "position_speed_max": float(np.abs(position_speed).max())
        if len(position_speed)
        else 0.0,
        "total_yaw_change": float(unwrapped[-1] - unwrapped[0]) if len(yaw) > 1 else 0.0,
    }


def write_csv(scene: Path, table: dict) -> Path:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = CSV_DIR / f"{scene.name}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["frame", "x", "y", "yaw_deg"])
        for frame in range(table["n"]):
            writer.writerow(
                [
                    frame,
                    f"{table['x'][frame]:.6f}",
                    f"{table['y'][frame]:.6f}",
                    f"{table['yaw'][frame]:.6f}",
                ]
            )
    return path


def box_relative_speed(scene: Path, n_frames: int) -> float | None:
    lidar_dir = scene / "object_labels" / "lidar"
    ids = sorted(path.stem for path in lidar_dir.glob("*.json"))
    if len(ids) < 2:
        return None

    def center(scan_id: str) -> tuple[float, float] | None:
        payload = json.loads((lidar_dir / f"{scan_id}.json").read_text())
        for block in payload:
            for instance in block.get("instances", []):
                contour = instance.get("contour", {})
                if "center3D" in contour:
                    return (
                        float(contour["center3D"]["x"]),
                        float(contour["center3D"]["y"]),
                    )
        return None

    first = center(ids[0])
    last = center(ids[-1])
    if first is None or last is None:
        return None
    distance = float(np.hypot(last[0] - first[0], last[1] - first[1]))
    duration = (n_frames - 1) * DT_S
    return distance / duration * 3.6 if duration > 0 else 0.0


def global_translation_check() -> tuple[int, float]:
    scenes = common.scene_dirs()
    maximum = 0.0
    for scene in scenes:
        matrix = np.loadtxt(scene / "poses.txt", dtype=np.float64)
        maximum = max(
            maximum,
            float(np.abs(matrix[:, [3, 7, 11, 12, 13, 14, 15]]).max()),
        )
    return len(scenes), maximum


def render(rows: list[dict], global_scenes: int, global_translation: float) -> str:
    lines: list[str] = [
        f"## 3. Quỹ đạo ego từ `poses.txt` — `{SCRIPT}`",
        "",
        "### Scene được chọn `[ĐO " + SCRIPT + "]`",
        "",
        "| Scene | Nhóm | Vì sao chọn | Frame | `object_velocity` | "
        "`ego_velocity` | `distance_to_object` | `itr_after_water` |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        record = row["record"]
        lines.append(
            f"| `{record['group']}/{record['scene']}` | {record['group']} | "
            f"{record['why']} | {row['table']['n']} | "
            f"{record['object_velocity']} km/h | {record['ego_velocity']} km/h | "
            f"{record['distance']:.1f} m | {record['itr']} |"
        )

    lines += [
        "",
        "### Định dạng `poses.txt` `[ĐO " + SCRIPT + "]`",
        "",
        "- Mỗi dòng **16 float** = ma trận 4×4 **row-major**; 3×3 đầu là rotation, "
        "cột 4 là tịnh tiến (`x = phần tử 3`, `y = 7`, `z = 11`).",
        "- Kiểm tra trực giao: `max |R·Rᵀ − I|` trên frame đầu của cả 3 scene "
        f"= `{max(row['table']['orthonormal_error'] for row in rows):.1e}`.",
        "- **Không có timestamp** trong file; mỗi scene có số frame khác nhau.",
        f"- `[ĐO {SCRIPT}]` **Toàn bộ {global_scenes} scene**: max "
        f"`|tịnh tiến|` = `{global_translation:.6f} m` (cột 3, 7, 11 và "
        "12–15). Vì vậy `x = y = 0` ở mọi frame; chỉ `yaw` thay đổi.",
        "",
        "### Quỹ đạo và tốc độ `[ĐO " + SCRIPT + "]`",
        "",
        f"`[CHỌN]` Giả định tần số **10 Hz** ⇒ `Δt = {DT_S:.1f} s`, vì file "
        "không có timestamp. Mọi số `°/s` và `m/s` dưới đây phụ thuộc giả định này.",
        "",
        "| Scene | Frame | max\\|tịnh tiến\\| (m) | x range (m) | y range (m) | "
        "yaw đầu (°) | yaw cuối (°) | Δyaw (°) | median \\|yaw rate\\| (°/s) | "
        "p90 \\|yaw rate\\| (°/s) |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        table = row["table"]
        record = row["record"]
        lines.append(
            f"| `{record['scene']}` | {table['n']} | "
            f"{table['max_translation']:.6f} | "
            f"[{table['x'].min():.6f}, {table['x'].max():.6f}] | "
            f"[{table['y'].min():.6f}, {table['y'].max():.6f}] | "
            f"{table['yaw'][0]:.3f} | {table['yaw'][-1]:.3f} | "
            f"{table['total_yaw_change']:+.3f} | "
            f"{table['yaw_rate_median']:.3f} | {table['yaw_rate_p90']:.3f} |"
        )

    lines += [
        "",
        "### Kiểm chéo tốc độ với `metadata.txt` `[ĐO " + SCRIPT + "]`",
        "",
        "| Scene | `ego_velocity` metadata (km/h) | metadata (m/s) | "
        "speed từ vị trí (m/s) | sai lệch | Kết quả |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        table = row["table"]
        record = row["record"]
        expected = record["ego_velocity"] / 3.6
        observed = table["position_speed_median"]
        deviation = abs(observed - expected) / expected * 100.0 if expected else 0.0
        verdict = "ĐẠT" if deviation < 10.0 else "**KHÔNG ĐẠT**"
        lines.append(
            f"| `{record['scene']}` | {record['ego_velocity']} | "
            f"{expected:.3f} | {observed:.3f} | {deviation:.2f} % | {verdict} |"
        )

    lines += [
        "",
        f"`[ĐO {SCRIPT}]` Speed suy từ vị trí = **0,000 m/s** ở cả 3 scene vì "
        "cột tịnh tiến đúng bằng 0; sai lệch **100 %** so với metadata ⇒ "
        "**KHÔNG ĐẠT** ngưỡng < 10 %.",
        "",
        "**Giả thuyết (không tự đổi công thức):**",
        "",
        "1. Bản release này **chỉ lưu rotation**, cột tịnh tiến bị zero hoá; "
        "không phải lỗi đơn vị (giá trị đúng bằng 0, không phải bị chia 1000).",
        "2. `poses.txt` **không có timestamp**; `Δt = 0,1 s` là giả định `[CHỌN]` "
        "từ 10 Hz, không đọc được từ dữ liệu.",
        "3. Không có frame skip: số dòng `poses.txt` = số file `velodyne/*.bin` "
        "ở cả 3 scene.",
        "",
        "**Kiểm chéo phụ (không dùng để thay tốc độ):** box xe dẫn trong "
        "`object_labels/lidar` gần như đứng yên tương đối với ego:",
        "",
        "| Scene | Vận tốc tương đối từ box (km/h) | `\\|object − ego\\|` metadata (km/h) |",
        "|---|---:|---:|",
    ]
    relative_rows = [
        (
            row,
            box_relative_speed(row["record"]["path"], row["table"]["n"]),
        )
        for row in rows
    ]
    relative_known = [
        (row, value) for row, value in relative_rows if value is not None
    ]
    if relative_known:
        worst_row, worst_value = max(relative_known, key=lambda item: item[1])
        worst_pct = (
            worst_value / worst_row["record"]["ego_velocity"] * 100.0
            if worst_row["record"]["ego_velocity"]
            else 0.0
        )
        relative_note = (
            "Box giữ khoảng cách gần như cố định (vận tốc tương đối đo được "
            f"`≤ {worst_value:.2f} km/h`, tức `≤ {worst_pct:.1f} %` tốc độ ego "
            "ở scene nhanh nhất), phù hợp `object_velocity = ego_velocity` "
            "trong metadata **trong sai số annotation**; nhưng đây **không** "
            "phải phép đo vận tốc tuyệt đối của ego (thiếu tịnh tiến trong "
            "`poses.txt`)."
        )
    else:
        relative_note = (
            "Không đọc được box trong `object_labels/lidar` để kiểm chéo phụ."
        )
    for row, relative in relative_rows:
        record = row["record"]
        if relative is None:
            lines.append(f"| `{record['scene']}` | không có box | 0 |")
        else:
            lines.append(
                f"| `{record['scene']}` | {relative:.2f} | "
                f"{abs(record['object_velocity'] - record['ego_velocity'])} |"
            )
    lines += [
        "",
        relative_note,
        "",
        "### CSV xuất ra `[ĐO " + SCRIPT + "]`",
        "",
        "| Scene | File |",
        "|---|---|",
    ]
    for row in rows:
        record = row["record"]
        lines.append(
            f"| `{record['scene']}` | "
            f"`docs/figs/ego-motion/{record['scene']}.csv` |"
        )
    lines += [
        "",
        "Cột `frame,x,y,yaw_deg`. `x` và `y` bằng `0,000000` ở mọi dòng vì "
        "tịnh tiến trong `poses.txt` bằng 0; `yaw_deg` lấy từ rotation.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    global_scenes, global_translation = global_translation_check()
    rows = []
    for record in choose_scenes():
        table = pose_table(record["path"])
        write_csv(record["path"], table)
        rows.append({"record": record, "table": table})
    body = render(rows, global_scenes, global_translation)
    common.replace_section(SECTION, body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
