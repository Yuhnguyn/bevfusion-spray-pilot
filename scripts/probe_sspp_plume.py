#!/usr/bin/env python3
"""Measure the plume generator against real SSPP frames with one cluster operator.

Both sides are measured on the **same frame** and with the same
:func:`spray.semantic_stats.cluster_angular` (paper recipe: DBSCAN in the
``(azimuth, elevation)`` plane, ``eps = 0.7°``, ``minPts = 3``):

* **real** -- points whose label is ``labels & 0xFFFF == 2`` (spray/noise),
  straight from ``labels/*.label``;
* **generator** -- ``points[labels != 2]`` fed to
  :func:`spray.plume.inject_plume` with the frame's 9-column ``gt_boxes``; the
  clusters are counted on ``result.injected``, **not** from ``PlumeStats``.

The generator is not modified. This is a measurement, not a fix ticket.

Run the smoke subset with::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
        scripts/probe_sspp_plume.py --limit-scenes 4

The report goes to ``docs/measurements/sspp-plume-probe.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# CẢNH BÁO (brief A8): `inject_plume` stateless đã bị xoá khỏi spray/plume.py.
# Script này ĐANG HỎNG — các hàm dưới đây gọi thẳng `inject_plume(...)` và sẽ NameError.
# Số nó từng in (docs/measurements/sspp-plume-probe.md) đo bằng đường ĐÃ CHẾT, KHÔNG dùng
# làm target calibration. Muốn dựng lại: viết trên `inject_plume_stateful`.
inject_plume = None  # gọi vào sẽ TypeError — xem cảnh báo trên

from spray.plume import PlumeConfig  # noqa: E402
from spray.semantic_stats import cluster_angular  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    build_info,
    load_points,
    read_frame_boxes,
    read_metadata,
    object_speed_kmh,
)

NOISE_LABEL = 2
LABEL_MASK = 0xFFFF
DEFAULT_FRAMES_PER_SCENE = 10
DEFAULT_DATASET_ROOT = REPO / "data" / "SemanticSprayDataset"
DEFAULT_SPLIT_JSON = REPO / "data" / "sspp_split.json"
DEFAULT_REPORT = REPO / "docs" / "measurements" / "sspp-plume-probe.md"

# [PAPER-graph] Fig. 4 at 25 m, read off the plotted curve (clusters/frame).
# Comparison only: never fit the generator to these values.
PAPER_FIG4_25M = (
    (70.0, 4.5),
    (80.0, 9.0),
    (90.0, 11.0),
    (100.0, 12.3),
    (110.0, 16.4),
    (120.0, 20.4),
    (130.0, 26.0),
)

SIDE_REAL = "real"
SIDE_GEN = "gen"


def count_clusters(points: np.ndarray) -> tuple[int, np.ndarray]:
    """Paper-recipe cluster count and per-cluster point counts.

    The one operator used for both sides. ``cluster_angular`` returns ``-1``
    for points in no cluster; only non-negative labels are counted.
    """

    arr = np.asarray(points)
    if arr.shape[0] == 0:
        return 0, np.zeros(0, dtype=np.int64)
    labels = cluster_angular(arr[:, :3])
    ids, sizes = np.unique(labels[labels >= 0], return_counts=True)
    return int(ids.size), sizes.astype(np.int64)


def frame_scan_ids(scene_dir: Path) -> list[str]:
    """Frame stems holding at least one Car/Van ``3D_BOX`` (split builder rule)."""

    labels_dir = scene_dir / "object_labels" / "lidar"
    return [
        path.stem
        for path in sorted(labels_dir.glob("*.json"), key=lambda p: p.name)
        if read_frame_boxes(path)
    ]


def evenly_spaced(count: int, sample: int) -> list[int]:
    """``sample`` indices spread evenly over ``range(count)``."""

    if count <= sample:
        return list(range(count))
    indices = np.linspace(0, count - 1, sample)
    return sorted({int(round(value)) for value in indices})


def measure_frame(
    dataset_root: Path,
    rel_scene: str,
    scan_id: str,
    metadata_row: dict[str, str],
) -> dict:
    """Measure real and generated plume clusters on one frame."""

    scene_dir = dataset_root / rel_scene
    info = build_info(dataset_root, rel_scene, scan_id, metadata_row)
    points = load_points(info, dataset_root)

    labels_path = scene_dir / "labels" / f"{scan_id}.label"
    labels = np.fromfile(labels_path, dtype=np.int32)
    if labels.shape[0] != points.shape[0]:
        raise ValueError(
            f"{labels_path}: {labels.shape[0]} labels vs "
            f"{points.shape[0]} points"
        )

    noise_mask = (labels & LABEL_MASK) == NOISE_LABEL
    noise = points[noise_mask]
    real_clusters, real_sizes = count_clusters(noise)

    clean = points[~noise_mask]
    result = inject_plume(
        clean,
        info["gt_boxes"],
        seed=0,
        token=info["token"],
        config=PlumeConfig(),
    )
    gen_clusters, gen_sizes = count_clusters(result.injected)

    boxes = info["gt_boxes"]
    road_z = float(np.median(boxes[:, 2])) if boxes.shape[0] else None
    real_heights = noise[:, 2] - road_z if road_z is not None else noise[:0, 2]
    gen_heights = (
        result.injected[:, 2] - road_z
        if road_z is not None
        else result.injected[:0, 2]
    )

    stats = result.stats
    return {
        "token": info["token"],
        "group": info["group"],
        "speed_kmh": object_speed_kmh(metadata_row),
        "real": {
            "clusters": real_clusters,
            "points": int(noise.shape[0]),
            "sizes": real_sizes,
            "heights": np.asarray(real_heights, dtype=np.float64),
            "capped": 0,
            "skipped_no_velocity": 0,
            "skipped_low_speed": 0,
            "eligible_boxes": int(boxes.shape[0]),
        },
        "gen": {
            "clusters": gen_clusters,
            "points": int(stats.injected),
            "sizes": gen_sizes,
            "heights": np.asarray(gen_heights, dtype=np.float64),
            "capped": int(stats.capped),
            "skipped_no_velocity": int(stats.skipped_no_velocity),
            "skipped_low_speed": int(stats.skipped_low_speed),
            "eligible_boxes": int(stats.eligible_boxes),
        },
    }


def _empty_side() -> dict:
    return {
        "frames": 0,
        "clusters_total": 0,
        "points_total": 0,
        "sizes": [],
        "heights": [],
        "capped": 0,
        "skipped_no_velocity": 0,
        "skipped_low_speed": 0,
        "eligible_boxes": 0,
    }


def _accumulate(side: dict, frame_side: dict) -> None:
    side["frames"] += 1
    side["clusters_total"] += frame_side["clusters"]
    side["points_total"] += frame_side["points"]
    side["sizes"].append(frame_side["sizes"])
    side["heights"].append(frame_side["heights"])
    side["capped"] += frame_side["capped"]
    side["skipped_no_velocity"] += frame_side["skipped_no_velocity"]
    side["skipped_low_speed"] += frame_side["skipped_low_speed"]
    side["eligible_boxes"] += frame_side["eligible_boxes"]


def summarize_side(side: dict) -> dict:
    frames = side["frames"]
    sizes = (
        np.concatenate(side["sizes"])
        if side["sizes"]
        else np.zeros(0, dtype=np.int64)
    )
    heights = (
        np.concatenate(side["heights"])
        if side["heights"]
        else np.zeros(0, dtype=np.float64)
    )
    return {
        "frames": frames,
        "clusters_total": side["clusters_total"],
        "points_total": side["points_total"],
        "clusters_per_frame": (
            side["clusters_total"] / frames if frames else float("nan")
        ),
        "points_per_frame": (
            side["points_total"] / frames if frames else float("nan")
        ),
        "det_per_cluster_p50": (
            float(np.percentile(sizes, 50)) if sizes.size else float("nan")
        ),
        "det_per_cluster_mean": (
            float(sizes.mean()) if sizes.size else float("nan")
        ),
        "height_p5": (
            float(np.percentile(heights, 5)) if heights.size else float("nan")
        ),
        "capped": side["capped"],
        "skipped_no_velocity": side["skipped_no_velocity"],
        "skipped_low_speed": side["skipped_low_speed"],
        "eligible_boxes": side["eligible_boxes"],
    }


def _fmt(value: float, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "nan"
    return f"{value:.{digits}f}"


def _fmt_comma(value: float, digits: int = 2) -> str:
    text = _fmt(value, digits)
    return text.replace(".", ",") if text != "nan" else text


def print_rows(rows: dict) -> None:
    for (group, speed), sides in sorted(rows.items()):
        for side_name in (SIDE_REAL, SIDE_GEN):
            side = sides[side_name]
            print(
                "SSPP_PLUME_PROBE "
                f"group={group} "
                f"speed={speed:.0f} "
                f"side={side_name} "
                f"frames={side['frames']} "
                f"clusters_per_frame={_fmt(side['clusters_per_frame'])} "
                f"points_per_frame={_fmt(side['points_per_frame'], 1)} "
                f"det_per_cluster_p50={_fmt(side['det_per_cluster_p50'])} "
                f"det_per_cluster_mean={_fmt(side['det_per_cluster_mean'])} "
                f"height_p5={_fmt(side['height_p5'])} "
                f"capped={side['capped']}"
            )


def _mismatch_rows(rows: dict) -> list[tuple[str, str]]:
    """Up to five ``(what is wrong, measured evidence)`` rows."""

    ratios: list[float] = []
    p50_real: list[float] = []
    p50_gen: list[float] = []
    height_real: list[float] = []
    height_gen: list[float] = []
    capped_total = 0
    injected_total = 0
    golf_speeds: dict[float, float] = {}
    crafter_speeds: dict[float, float] = {}

    for (group, speed), sides in rows.items():
        real = sides[SIDE_REAL]
        gen = sides[SIDE_GEN]
        if np.isfinite(real["clusters_per_frame"]) and real["clusters_per_frame"] > 0:
            ratios.append(gen["clusters_per_frame"] / real["clusters_per_frame"])
        if np.isfinite(real["det_per_cluster_p50"]):
            p50_real.append(real["det_per_cluster_p50"])
        if np.isfinite(gen["det_per_cluster_p50"]):
            p50_gen.append(gen["det_per_cluster_p50"])
        if np.isfinite(real["height_p5"]):
            height_real.append(real["height_p5"])
        if np.isfinite(gen["height_p5"]):
            height_gen.append(gen["height_p5"])
        capped_total += gen["capped"]
        injected_total += gen["points_total"]
        if group.startswith("Golf"):
            golf_speeds[speed] = gen["clusters_per_frame"]
        elif group.startswith("Crafter"):
            crafter_speeds[speed] = gen["clusters_per_frame"]

    out: list[tuple[str, str]] = []
    if ratios:
        out.append(
            (
                "Số cụm/frame của generator lệch so với frame thật",
                f"gen/thật = {_fmt_comma(min(ratios))}–{_fmt_comma(max(ratios))}× "
                f"trên {len(ratios)} ô (group, tốc độ)",
            )
        )
    if p50_real and p50_gen:
        out.append(
            (
                "Số điểm mỗi cụm khác giữa hai phía",
                f"p50 điểm/cụm: thật {_fmt_comma(float(np.mean(p50_real)))} "
                f"so với gen {_fmt_comma(float(np.mean(p50_gen)))}",
            )
        )
    if height_real and height_gen:
        out.append(
            (
                "Độ cao p5 của điểm trên mặt đường khác nhau",
                f"p5 cao: thật {_fmt_comma(min(height_real))}–"
                f"{_fmt_comma(max(height_real))} m, gen "
                f"{_fmt_comma(min(height_gen))}–{_fmt_comma(max(height_gen))} m",
            )
        )
    if capped_total:
        share = (
            100.0 * capped_total / (capped_total + injected_total)
            if (capped_total + injected_total)
            else 0.0
        )
        out.append(
            (
                "Ngân sách điểm cắt bớt điểm vừa sinh",
                f"capped {capped_total} điểm, {_fmt_comma(share, 1)} % tổng điểm gen",
            )
        )
    shared = sorted(set(golf_speeds) & set(crafter_speeds))
    if shared:
        same = all(
            abs(golf_speeds[speed] - crafter_speeds[speed]) < 0.05
            for speed in shared
        )
        out.append(
            (
                "Golf dùng chung bảng cụm của Crafter",
                "inject_plume không nhận vehicle_class; cụm/frame gen "
                + ("bằng nhau" if same else "khác nhau")
                + " ở cùng tốc độ",
            )
        )
    return out[:5]


def build_markdown(
    rows: dict,
    *,
    dataset_root: Path,
    split: str,
    scenes: int,
    frames: int,
    frames_per_scene: int,
) -> str:
    """Render the measurement report."""

    lines: list[str] = []
    lines.append("# Probe generator plume trên SemanticSpray++ — đo thật vs sinh")
    lines.append("")
    lines.append(
        "Báo cáo do `scripts/probe_sspp_plume.py` sinh. **Không sửa generator**; "
        "đây là phép đo hiện trạng."
    )
    lines.append("")
    lines.append("## Phạm vi mẫu")
    lines.append("")
    lines.append("| Mục | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Dataset | `{dataset_root}` |")
    lines.append(f"| Split | `{split}` |")
    lines.append(f"| Scene | {scenes} |")
    lines.append(f"| Frame | {frames} |")
    lines.append(f"| Frame/scene | tối đa {frames_per_scene}, cách đều |")
    lines.append(
        "| Toán tử cụm | `spray.semantic_stats.cluster_angular` "
        "(DBSCAN góc, eps = 0,7°, minPts = 3) |"
    )
    lines.append(
        "| Điểm thật | `labels & 0xFFFF == 2` |"
    )
    lines.append(
        "| Điểm gen | `inject_plume(points[labels != 2], gt_boxes, "
        "seed=0, token=<scene/scan>)`, đếm trên `result.injected` |"
    )
    lines.append(
        "| Mặt đường | `road_z` = trung vị z-đáy của box GT trong frame |"
    )
    lines.append("")

    lines.append("## Bảng thật-vs-generator theo (group, tốc độ) `[ĐO]`")
    lines.append("")
    lines.append(
        "`real` = điểm noise thật; `gen` = điểm `inject_plume` chèn vào cùng "
        "frame. `points` = số điểm mỗi frame. `det/cụm` = số điểm mỗi cụm. "
        "`height p5` = percentile 5 chiều cao trên mặt đường. Mọi số trong bảng "
        "này là `[ĐO]` trên máy này."
    )
    lines.append("")
    lines.append(
        "| group | km/h | frame | cụm/frame real `[ĐO]` | cụm/frame gen `[ĐO]` | "
        "điểm/frame real `[ĐO]` | điểm/frame gen `[ĐO]` | "
        "det/cụm p50 real `[ĐO]` | det/cụm p50 gen `[ĐO]` | "
        "det/cụm mean real `[ĐO]` | det/cụm mean gen `[ĐO]` | "
        "height p5 real `[ĐO]` | height p5 gen `[ĐO]` | capped gen `[ĐO]` |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for (group, speed), sides in sorted(rows.items()):
        real = sides[SIDE_REAL]
        gen = sides[SIDE_GEN]
        lines.append(
            f"| {group} | {speed:.0f} | {real['frames']} | "
            f"{_fmt_comma(real['clusters_per_frame'])} | "
            f"{_fmt_comma(gen['clusters_per_frame'])} | "
            f"{_fmt_comma(real['points_per_frame'], 1)} | "
            f"{_fmt_comma(gen['points_per_frame'], 1)} | "
            f"{_fmt_comma(real['det_per_cluster_p50'])} | "
            f"{_fmt_comma(gen['det_per_cluster_p50'])} | "
            f"{_fmt_comma(real['det_per_cluster_mean'])} | "
            f"{_fmt_comma(gen['det_per_cluster_mean'])} | "
            f"{_fmt_comma(real['height_p5'])} | "
            f"{_fmt_comma(gen['height_p5'])} | "
            f"{gen['capped']} |"
        )
    lines.append("")

    lines.append("## Thống kê `PlumeStats` phía generator `[ĐO]`")
    lines.append("")
    lines.append(
        "`injected` = `stats.injected`; `eligible box·frame` = số box đủ điều "
        "kiện cộng dồn qua các frame. `skipped_*` lấy nguyên từ `PlumeStats`."
    )
    lines.append("")
    lines.append(
        "| group | km/h | frame | eligible box·frame `[ĐO]` | injected `[ĐO]` | "
        "capped `[ĐO]` | skipped_no_velocity `[ĐO]` | "
        "skipped_low_speed `[ĐO]` |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for (group, speed), sides in sorted(rows.items()):
        gen = sides[SIDE_GEN]
        lines.append(
            f"| {group} | {speed:.0f} | {gen['frames']} | "
            f"{gen['eligible_boxes']} | {gen['points_total']} | "
            f"{gen['capped']} | {gen['skipped_no_velocity']} | "
            f"{gen['skipped_low_speed']} |"
        )
    lines.append("")
    lines.append("## Cái còn sai")
    lines.append("")
    lines.append("| Hiện tượng | Bằng chứng |")
    lines.append("|---|---|")
    mismatches = _mismatch_rows(rows)
    if mismatches:
        for what, evidence in mismatches:
            lines.append(f"| {what} | {evidence} |")
    else:
        lines.append("| — | chưa đủ dữ liệu |")
    lines.append("")

    lines.append("## Đối chiếu Fig. 4 @25 m `[PAPER-graph]`")
    lines.append("")
    lines.append(
        "Các số 4,5 / 9 / 11 / 12,3 / 16,4 / 20,4 / 26 cụm/frame ở "
        "70→130 km/h là **đọc từ đồ thị** Fig. 4 của paper tại cự ly 25 m, "
        "`[PAPER-graph]`. Chỉ dùng để đối chiếu, **không dùng để fit** generator. "
        "Paper chỉ định lượng Crafter, nên Golf để tham khảo."
    )
    lines.append("")
    lines.append(
        "| km/h | Fig. 4 @25 m `[PAPER-graph]` | Crafter thật `[ĐO]` | "
        "Crafter gen `[ĐO]` | Golf thật `[ĐO]` | Golf gen `[ĐO]` |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|")
    by_group_speed: dict[tuple[str, float], dict] = {}
    for (group, speed), sides in rows.items():
        by_group_speed[(group, speed)] = sides

    def _cell(group_prefix: str, speed: float, side: str, field: str) -> str:
        for (group, row_speed), sides in by_group_speed.items():
            if group.startswith(group_prefix) and abs(row_speed - speed) < 0.5:
                return _fmt_comma(sides[side][field])
        return "—"

    for speed, target in PAPER_FIG4_25M:
        lines.append(
            f"| {speed:.0f} | {_fmt_comma(target, 1)} | "
            f"{_cell('Crafter', speed, SIDE_REAL, 'clusters_per_frame')} | "
            f"{_cell('Crafter', speed, SIDE_GEN, 'clusters_per_frame')} | "
            f"{_cell('Golf', speed, SIDE_REAL, 'clusters_per_frame')} | "
            f"{_cell('Golf', speed, SIDE_GEN, 'clusters_per_frame')} |"
        )
    lines.append("")
    lines.append(
        "Split train chỉ chứa tốc độ 60/80/100/120 km/h, nên các mốc "
        "70/90/110/130 để trống (`—`). Đây là giới hạn của split, không phải lỗi "
        "của phép đo."
    )
    lines.append("")

    lines.append("## Cách chạy lại")
    lines.append("")
    lines.append("```bash")
    lines.append(
        "CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python "
        "scripts/probe_sspp_plume.py"
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help="SemanticSpray++ root holding Crafter_dynamic/Golf_dynamic",
    )
    parser.add_argument(
        "--split-json",
        type=Path,
        default=DEFAULT_SPLIT_JSON,
        help="split file written by scripts/build_sspp_split.py",
    )
    parser.add_argument("--split", default="train", help="split name to measure")
    parser.add_argument(
        "--frames-per-scene",
        type=int,
        default=DEFAULT_FRAMES_PER_SCENE,
        help="evenly spaced frames sampled per scene",
    )
    parser.add_argument(
        "--limit-scenes",
        type=int,
        default=None,
        help="measure only the first N scenes of the split (smoke run)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="markdown report path",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="do not write the markdown report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_root = args.dataset_root.resolve()
    split_doc = json.loads(args.split_json.read_text(encoding="utf-8"))
    scenes = list(split_doc["split"][args.split])
    if args.limit_scenes is not None:
        scenes = scenes[: args.limit_scenes]

    rows: dict[tuple[str, float], dict] = {}
    measured_frames = 0
    measured_scenes = 0
    for rel_scene in scenes:
        scene_dir = dataset_root / rel_scene
        metadata_row = read_metadata(scene_dir / "metadata.txt")
        scan_ids = frame_scan_ids(scene_dir)
        if not scan_ids:
            continue
        chosen = [
            scan_ids[index]
            for index in evenly_spaced(len(scan_ids), args.frames_per_scene)
        ]
        measured_scenes += 1
        for scan_id in chosen:
            frame = measure_frame(
                dataset_root, rel_scene, scan_id, metadata_row
            )
            key = (frame["group"], float(round(frame["speed_kmh"])))
            if key not in rows:
                rows[key] = {SIDE_REAL: _empty_side(), SIDE_GEN: _empty_side()}
            _accumulate(rows[key][SIDE_REAL], frame[SIDE_REAL])
            _accumulate(rows[key][SIDE_GEN], frame[SIDE_GEN])
            measured_frames += 1

    summary_rows = {
        key: {
            SIDE_REAL: summarize_side(sides[SIDE_REAL]),
            SIDE_GEN: summarize_side(sides[SIDE_GEN]),
        }
        for key, sides in rows.items()
    }
    print_rows(summary_rows)

    gen_clusters = sum(
        sides[SIDE_GEN]["clusters_total"] for sides in summary_rows.values()
    )
    markdown = build_markdown(
        summary_rows,
        dataset_root=dataset_root,
        split=args.split,
        scenes=measured_scenes,
        frames=measured_frames,
        frames_per_scene=args.frames_per_scene,
    )
    if not args.no_report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown + "\n", encoding="utf-8")
        print(f"SSPP_PLUME_PROBE_REPORT path={args.report}")

    if gen_clusters == 0:
        print("SSPP_PLUME_PROBE_BLOCKED all_gen_frames_have_zero_clusters")
        for (group, speed), sides in sorted(summary_rows.items()):
            gen = sides[SIDE_GEN]
            print(
                "SSPP_PLUME_PROBE_STATS "
                f"group={group} speed={speed:.0f} frames={gen['frames']} "
                f"eligible_boxes={gen['eligible_boxes']} "
                f"skipped_no_velocity={gen['skipped_no_velocity']} "
                f"skipped_low_speed={gen['skipped_low_speed']} "
                f"injected={gen['points_total']} capped={gen['capped']}"
            )
        return 2

    print(
        f"SSPP_PLUME_PROBE_DONE frames={measured_frames} "
        f"scenes={measured_scenes}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
