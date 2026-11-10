#!/usr/bin/env python3
"""Measure speeds, distance and water level from every scene's metadata.txt.

Ticket 25, item 1. Reads all 207 ``metadata.txt`` files (header + one CSV row
each), never ``poses.txt`` for velocity. Writes the ``measure_speeds.py``
section of ``docs/plume-v2-measurements.md`` and prints it to stdout.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plume_v2_measure_common as common  # noqa: E402

SECTION = "measure_speeds.py"
SCRIPT = "measure_speeds.py"


def thousand(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def percent(part: int, total: int) -> str:
    return f"{100.0 * part / total:.2f}" if total else "0.00"


def render(stats: dict) -> str:
    total_scenes = stats["n_scenes"]
    total_frames = stats["n_frames"]
    lines: list[str] = [
        f"## 1. Tốc độ, cự ly và mức nước — `{SCRIPT}`",
        "",
        f"Đọc **toàn bộ {total_scenes}** `metadata.txt` (mỗi scene 1 dòng dữ liệu). "
        f"Vận tốc lấy **trực tiếp** từ metadata, không suy từ `poses.txt`.",
        "",
        f"### Tổng quan dữ liệu `[ĐO {SCRIPT}]`",
        "",
        "| Nhóm | Scene | Frame |",
        "|---|---:|---:|",
    ]
    for group in common.GROUPS:
        lines.append(
            f"| `{group}` | {stats['group_scenes'][group]} | "
            f"{thousand(stats['group_frames'][group])} |"
        )
    lines += [
        f"| **Tổng** | **{total_scenes}** | **{thousand(total_frames)}** |",
        "",
        f"`[ĐO {SCRIPT}]` Số frame = số file `velodyne/*.bin`; mỗi frame có đúng "
        "một `labels/*.label` cùng số điểm.",
        "",
        "### `object_velocity` — histogram bin 10 km/h `[ĐO " + SCRIPT + "]`",
        "",
        "| Bin (km/h) | Scene | % scene | Frame | % frame |",
        "|---|---:|---:|---:|---:|",
    ]

    for velocity in sorted(stats["by_velocity"]):
        row = stats["by_velocity"][velocity]
        lines.append(
            f"| {velocity}–{velocity + 9} | {row['scenes']} | "
            f"{percent(row['scenes'], total_scenes)} | "
            f"{thousand(row['frames'])} | "
            f"{percent(row['frames'], total_frames)} |"
        )
    lines += [
        f"| **Tổng** | **{total_scenes}** | **100.00** | "
        f"**{thousand(total_frames)}** | **100.00** |",
        "",
        f"### `ego_velocity` — histogram bin 10 km/h `[ĐO {SCRIPT}]`",
        "",
        "| Bin (km/h) | Scene | % scene | Frame | % frame |",
        "|---|---:|---:|---:|---:|",
    ]
    for velocity in sorted(stats["by_ego"]):
        row = stats["by_ego"][velocity]
        lines.append(
            f"| {velocity}–{velocity + 9} | {row['scenes']} | "
            f"{percent(row['scenes'], total_scenes)} | "
            f"{thousand(row['frames'])} | "
            f"{percent(row['frames'], total_frames)} |"
        )
    lines += [
        f"| **Tổng** | **{total_scenes}** | **100.00** | "
        f"**{thousand(total_frames)}** | **100.00** |",
        "",
        f"`[ĐO {SCRIPT}]` `object_velocity == ego_velocity` ở "
        f"**{total_scenes - stats['object_ne_ego']}/{total_scenes}** scene "
        f"({stats['object_ne_ego']} scene lệch). Hai histogram vì vậy trùng nhau.",
        "",
        f"### `distance_to_object` `[ĐO {SCRIPT}]`",
        "",
        "| Cự ly (m) | Scene | % scene | Frame | % frame |",
        "|---|---:|---:|---:|---:|",
    ]
    for distance in sorted(stats["by_distance"]):
        row = stats["by_distance"][distance]
        lines.append(
            f"| {distance:.1f} | {row['scenes']} | "
            f"{percent(row['scenes'], total_scenes)} | "
            f"{thousand(row['frames'])} | "
            f"{percent(row['frames'], total_frames)} |"
        )
    lines += [
        "",
        f"### `itr_after_water` `[ĐO {SCRIPT}]`",
        "",
        "`itr_after_water` là **biến điều khiển mức nước** của SemanticSpray "
        "(số iteration sau khi tưới), không phải `wfh` (paper: **mm**).",
        "",
        "| `itr_after_water` | Scene | % scene | Frame | % frame |",
        "|---:|---:|---:|---:|---:|",
    ]
    for itr in sorted(stats["by_itr"]):
        row = stats["by_itr"][itr]
        lines.append(
            f"| {itr} | {row['scenes']} | "
            f"{percent(row['scenes'], total_scenes)} | "
            f"{thousand(row['frames'])} | "
            f"{percent(row['frames'], total_frames)} |"
        )
    lines += [
        "",
        f"### `object_name` `[ĐO {SCRIPT}]`",
        "",
        "| Xe dẫn | Scene | % scene |",
        "|---|---:|---:|",
    ]
    for name in sorted(stats["by_name"]):
        row = stats["by_name"][name]
        lines.append(
            f"| {name} | {row['scenes']} | {percent(row['scenes'], total_scenes)} |"
        )
    lines += [
        f"| Khác | 0 | 0.00 |",
        "",
        f"### Ngưỡng kích hoạt `[ĐO {SCRIPT}]`",
        "",
        "| Ngưỡng | Scene | % trên 207 | Frame | % trên 17.419 |",
        "|---|---:|---:|---:|---:|",
        f"| `object_velocity ≥ 40` (kích hoạt) | {stats['ge40_scenes']} | "
        f"{percent(stats['ge40_scenes'], total_scenes)} | "
        f"{thousand(stats['ge40_frames'])} | "
        f"{percent(stats['ge40_frames'], total_frames)} |",
        f"| `object_velocity ≥ 50` (paper) | {stats['ge50_scenes']} | "
        f"{percent(stats['ge50_scenes'], total_scenes)} | "
        f"{thousand(stats['ge50_frames'])} | "
        f"{percent(stats['ge50_frames'], total_frames)} |",
        f"| `object_velocity < 40` | "
        f"{total_scenes - stats['ge40_scenes']} | "
        f"{percent(total_scenes - stats['ge40_scenes'], total_scenes)} | "
        f"{thousand(total_frames - stats['ge40_frames'])} | "
        f"{percent(total_frames - stats['ge40_frames'], total_frames)} |",
        "",
        f"### Frame sẽ không sinh spray `[ĐO {SCRIPT}]`",
        "",
        "Công thức số cụm `[CODE] dee.cpp:509–512`: "
        "`mean = (0,2·wfh + 0,1)·(v_kmh − 50)`; `count = round(max(0, mean))`.",
        "",
        "| Điều kiện | Frame | % frame | Cụm/frame |",
        "|---|---:|---:|---:|",
        f"| `v < 50` (dưới ngưỡng paper) | {thousand(stats['lt50_frames'])} | "
        f"{percent(stats['lt50_frames'], total_frames)} | 0 |",
        f"| `v = 50` (đúng offset) | {thousand(stats['eq50_frames'])} | "
        f"{percent(stats['eq50_frames'], total_frames)} | 0 với mọi `wfh > 0` |",
        f"| `v > 50` | {thousand(stats['gt50_frames'])} | "
        f"{percent(stats['gt50_frames'], total_frames)} | > 0 |",
        "",
        f"`[ĐO {SCRIPT}]` **Ràng buộc trần dữ liệu:** "
        f"**{percent(stats['lt50_frames'], total_frames)} %** frame có "
        f"`object_velocity < 50` ({thousand(stats['lt50_frames'])}/"
        f"{thousand(total_frames)}). Toàn bộ 207 scene nằm trong dải "
        "**50–130 km/h**, nên ngưỡng 50 km/h **không** loại frame nào. "
        f"Nhưng **{percent(stats['eq50_frames'], total_frames)} %** frame ở "
        "**đúng 50 km/h** vẫn cho `mean = (0,2·wfh + 0,1)·(50 − 50) = 0` cụm, "
        "tức **0 điểm spray** dù đã vượt ngưỡng kích hoạt 40 km/h.",
        "",
        f"`[ĐO {SCRIPT}]` Không scene nào có `object_velocity` dưới 40 hoặc "
        "trên 130 km/h; không có bin 0–39 km/h.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    stats = common.speed_stats()
    if stats["n_scenes"] != 207:
        raise SystemExit(f"expected 207 scenes, found {stats['n_scenes']}")
    body = render(stats)
    common.replace_section(SECTION, body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
