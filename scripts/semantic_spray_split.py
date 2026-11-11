#!/usr/bin/env python3
"""Build, verify, and measure the frozen SemanticSpray cal/held-out split.

Commands (ticket 29d):

    CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/semantic_spray_split.py --build
    ... --verify
    ... --measure --frames-per-scene 60

``--build`` writes ``spray/config/semantic_spray_split.yaml``; ``--verify``
rebuilds the split from the dataset and compares it with the file on disk;
``--measure`` reads sampled frames of each role, evaluates the 7 frozen
criteria, writes ``docs/measurements/semantic-spray-cal-vs-heldout.md`` and
exits 1 when the gate fails.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from spray.semantic_split import (  # noqa: E402
    GROUPS,
    ROLE_CAL,
    ROLE_HELD_OUT,
    RULE_VERSION,
    build_split,
    dump_split,
    evaluate_criteria,
    itr_balance,
    load_split,
    read_dataset,
    role_scenes,
    verify_split,
)
from spray.semantic_stats import (  # noqa: E402
    ANGULAR_EPS_DEG,
    ELEVATION_STEP_DEG,
    MIN_PTS,
    RADIUS_M,
    StatsAccumulator,
    frame_stats_pair,
    metrics,
)

BOX_HEIGHT_M = 2.6206  # [ĐO] docs/measurements/plume-v2-measurements.md, van box
BOX_HEIGHT_SOURCE = (
    "chiều cao box van `Crafter_dynamic`, "
    "`docs/measurements/plume-v2-measurements.md`"
)


def sample_scan_ids(scene: Path, limit: int) -> list[str]:
    ids = sorted(path.stem for path in (scene / "velodyne").glob("*.bin"))
    if limit <= 0 or limit >= len(ids):
        return ids
    picks = np.linspace(0, len(ids) - 1, limit).round().astype(int)
    return [ids[index] for index in sorted(set(picks.tolist()))]


def _load_frame(scene: Path, scan_id: str):
    points_path = scene / "velodyne" / f"{scan_id}.bin"
    labels_path = scene / "labels" / f"{scan_id}.label"
    if not points_path.is_file() or not labels_path.is_file():
        return None
    raw = np.fromfile(points_path, dtype=np.float32)
    if raw.size == 0 or raw.size % 5:
        return None
    points = raw.reshape(-1, 5)
    labels = np.fromfile(labels_path, dtype=np.uint32)
    if labels.size != points.shape[0]:
        return None
    return points, labels


def _display_command() -> str:
    parts = [os.path.basename(sys.executable)]
    for argument in sys.argv:
        try:
            resolved = Path(argument).resolve()
        except OSError:
            parts.append(argument)
            continue
        if resolved == REPO or REPO in resolved.parents:
            parts.append(str(resolved.relative_to(REPO)))
        else:
            parts.append(argument)
    return " ".join(parts)


def measure_roles(
    cal_paths: list[Path],
    held_paths: list[Path],
    frames_per_scene: int,
) -> dict:
    role_keys = (ROLE_CAL, ROLE_HELD_OUT, "cal_a", "cal_b")
    paper = {role: StatsAccumulator() for role in role_keys}
    legacy = {role: StatsAccumulator() for role in role_keys}
    frames = {role: 0 for role in role_keys}
    skipped = {ROLE_CAL: 0, ROLE_HELD_OUT: 0}
    started = time.monotonic()

    def announce_start(role: str, paths: list[Path]) -> None:
        print(
            f"MEASURE_START role={role} scenes={len(paths)} "
            f"frames_per_scene={frames_per_scene}",
            flush=True,
        )

    def announce_progress(role: str, position: int, total: int) -> None:
        if position % 10 == 0 or position == total:
            print(
                f"MEASURE_PROGRESS role={role} scene={position}/{total} "
                f"frames={frames[role]}",
                flush=True,
            )

    def run(
        scene: Path,
        paper_roles: tuple[str, ...],
        legacy_roles: tuple[str, ...],
        role: str,
    ):
        for scan_id in sample_scan_ids(scene, frames_per_scene):
            loaded = _load_frame(scene, scan_id)
            if loaded is None:
                skipped[role] += 1
                continue
            points, labels = loaded
            frames_for_recipe = frame_stats_pair(points, labels)
            for name in paper_roles:
                paper[name].add(frames_for_recipe["paper"])
                frames[name] += 1
            for name in legacy_roles:
                legacy[name].add(frames_for_recipe["legacy"])

    announce_start(ROLE_CAL, cal_paths)
    for index, scene in enumerate(cal_paths):
        half = "cal_a" if index % 2 == 0 else "cal_b"
        run(scene, (ROLE_CAL, half), (ROLE_CAL,), ROLE_CAL)
        announce_progress(ROLE_CAL, index + 1, len(cal_paths))
    announce_start(ROLE_HELD_OUT, held_paths)
    for index, scene in enumerate(held_paths):
        run(scene, (ROLE_HELD_OUT,), (ROLE_HELD_OUT,), ROLE_HELD_OUT)
        announce_progress(ROLE_HELD_OUT, index + 1, len(held_paths))

    print(
        f"MEASURE_DONE elapsed={time.monotonic() - started:.1f} "
        f"frames={frames[ROLE_CAL] + frames[ROLE_HELD_OUT]} "
        f"skipped={sum(skipped.values())}",
        flush=True,
    )

    summaries = {
        role: paper[role].summary() for role in role_keys
    }
    legacy_summaries = {
        role: legacy[role].summary() for role in role_keys
    }
    return {
        "summaries": summaries,
        "legacy_summaries": legacy_summaries,
        "metrics": {
            role: metrics(summaries[role], legacy_summaries[role])
            for role in role_keys
        },
        "frames": frames,
        "skipped": skipped,
    }


def _number(value, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def _signed_percent(delta, base, digits: int = 1) -> str:
    try:
        delta_value = float(delta)
        base_value = float(base)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(delta_value) or not math.isfinite(base_value):
        return "n/a"
    if base_value == 0.0:
        return "n/a"
    return f"{100.0 * delta_value / abs(base_value):+.{digits}f}%"


def _percent(value, digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return f"{100.0 * number:.{digits}f}%"


def _percentile(values, q: float) -> str:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return "n/a"
    return f"{float(np.percentile(array, q)):.2f}"


def _table1(split: dict) -> list[str]:
    lines = [
        "| group | km/h | distance (m) | #scene | cal | held-out | unpaired |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for cell in split["cells"]:
        key = cell["key"]
        cal = cell["scenes"][ROLE_CAL]
        held = cell["scenes"][ROLE_HELD_OUT]
        lines.append(
            f"| {key['group']} | {key['velocity_kmh']:.0f} | "
            f"{key['distance_m']:.1f} | {len(cal) + len(held)} | "
            f"{len(cal)} | {len(held)} | "
            f"{'yes' if cell['unpaired'] else 'no'} |"
        )
    return lines


def _table4(balance: dict) -> list[str]:
    levels = sorted(
        {
            level
            for per_group in balance.values()
            for per_role in per_group.values()
            for level in per_role
        }
    )
    lines = [
        "| group | vai | "
        + " | ".join(f"w={level}" for level in levels)
        + " | tổng |",
        "|---|---|" + "---:|" * len(levels) + "---:|",
    ]

    totals = {
        ROLE_CAL: {level: 0 for level in levels},
        ROLE_HELD_OUT: {level: 0 for level in levels},
    }
    for group in (group for group in GROUPS if group in balance):
        for role in (ROLE_CAL, ROLE_HELD_OUT):
            counts = balance[group][role]
            for level in levels:
                totals[role][level] += counts.get(level, 0)
            cells = " | ".join(
                str(counts.get(level, 0)) for level in levels
            )
            lines.append(
                f"| {group} | {role} | {cells} | "
                f"{sum(counts.values())} |"
            )

    for role in (ROLE_CAL, ROLE_HELD_OUT):
        cells = " | ".join(str(totals[role][level]) for level in levels)
        lines.append(
            f"| toàn cục | {role} | {cells} | "
            f"{sum(totals[role].values())} |"
        )
    return lines


def _table2(results: list, metrics_by_role: dict) -> list[str]:
    lines = [
        "| id | đại lượng | cal | held-out | Δ | Δ_halfsplit | ngưỡng | verdict |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        quantity = f"{result.quantity} ({result.estimator})"
        if result.id == "G6":
            keys = ("G6_p5", "G6_med", "G6_p95")
            cal_metrics = metrics_by_role.get(ROLE_CAL) or {}
            held_metrics = metrics_by_role.get(ROLE_HELD_OUT) or {}
            cal_cell = " / ".join(
                _number(cal_metrics.get(key), 3) for key in keys
            )
            held_cell = " / ".join(
                _number(held_metrics.get(key), 3) for key in keys
            )
            delta_cell = " / ".join(
                _signed_delta(held_metrics.get(key), cal_metrics.get(key))
                for key in keys
            )
            half_cell = _number(result.half_split_delta, 3)
            threshold_cell = _number(result.threshold, 3)
        elif result.relative:
            cal_cell = _number(result.cal, 3)
            held_cell = _number(result.held_out, 3)
            delta_cell = _signed_percent(result.delta, result.cal)
            half_cell = _percent(result.half_split_delta)
            threshold_cell = _percent(result.threshold)
        else:
            cal_cell = _number(result.cal, 3)
            held_cell = _number(result.held_out, 3)
            delta_cell = (
                f"{result.delta:+.3f}"
                if math.isfinite(result.delta)
                else "n/a"
            )
            half_cell = _number(result.half_split_delta, 3)
            threshold_cell = _number(result.threshold, 3)

        verdict = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| {result.id} | {quantity} | {cal_cell} | {held_cell} | "
            f"{delta_cell} | {half_cell} | {threshold_cell} | {verdict} |"
        )
    return lines


def _signed_delta(held, cal) -> str:
    try:
        held_value = float(held)
        cal_value = float(cal)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(held_value) or not math.isfinite(cal_value):
        return "n/a"
    return f"{held_value - cal_value:+.3f}"


def _table3(summary: dict) -> list[str]:
    noise = summary["noise_per_frame"]
    clusters = summary["clusters_per_frame"]
    sizes = summary["cluster_sizes"]
    heights = np.asarray(summary["height_above_road"], dtype=np.float64)
    abs_y = summary["abs_y"]
    intensity = summary["intensity"]
    ring = summary["ring"]

    if heights.size:
        fraction = heights / BOX_HEIGHT_M
        tail_p5 = _percentile(fraction, 5)
        tail_p95 = _percentile(fraction, 95)
    else:
        tail_p5 = tail_p95 = "n/a"

    if ring.size:
        ring_cell = (
            f"{int(np.rint(ring.min()))}–{int(np.rint(ring.max()))}, "
            f"median {float(np.median(ring)):.0f}"
        )
    else:
        ring_cell = "n/a"

    clusters_mean = (
        f"{float(clusters.mean()):.2f}" if clusters.size else "n/a"
    )

    return [
        "| đại lượng (trên cal) | giá trị |",
        "|---|---|",
        f"| điểm noise/frame (p5 / med / p95) | "
        f"{_percentile(noise, 5)} / {_percentile(noise, 50)} / "
        f"{_percentile(noise, 95)} |",
        f"| cụm/frame (mean) | {clusters_mean} |",
        f"| điểm/cụm (p5 / med / p95) | "
        f"{_percentile(sizes, 5)} / {_percentile(sizes, 50)} / "
        f"{_percentile(sizes, 95)} |",
        f"| `tail_block_height_frac` (p5 / p95) | "
        f"{tail_p5} / {tail_p95} |",
        f"| p95(\\|y\\|) (m) | {_percentile(abs_y, 95)} |",
        f"| intensity (p50 / p90 / p99) | "
        f"{_percentile(intensity, 50)} / {_percentile(intensity, 90)} / "
        f"{_percentile(intensity, 99)} |",
        f"| ring (khoảng, median) | {ring_cell} |",
    ]


def _table_legacy(metrics_by_role: dict) -> list[str]:
    lines = [
        "| vai | cụm/frame (mean) | điểm/cụm (median) | median r_range/r_extent |",
        "|---|---:|---:|---:|",
    ]
    for role in (ROLE_CAL, ROLE_HELD_OUT):
        data = metrics_by_role.get(role) or {}
        lines.append(
            f"| {role} | {_number(data.get('legacy_G2'))} | "
            f"{_number(data.get('legacy_G3'))} | "
            f"{_number(data.get('legacy_G4'), 3)} |"
        )
    return lines


def render_report(
    split: dict,
    measured: dict,
    results: list,
    sample: dict,
    balance: dict,
) -> str:
    summaries = measured["summaries"]
    metrics_by_role = measured["metrics"]
    failed = [result.id for result in results if not result.passed]
    lines = [
        "# Cổng chia `cal` / `held-out` cho SemanticSpray",
        "",
        "## Luật chia",
        "",
        f"- rule: `{RULE_VERSION}`",
        "- ngày: 2026-11-11",
        "- lý do đổi luật: trong mỗi ô, `metadata.txt` ghi `itr_after_water`",
        "  1…6 đúng theo thứ tự tên file và bể nước vơi dần sau mỗi lần đo.",
        "  Luật v1 sắp theo tên rồi luôn bắt đầu bằng `cal`, nên `cal` rơi vào",
        "  các lần đo 1/3/5 (nước vừa thay, plume lớn) còn `held-out` vào",
        "  2/4/6 (nước đã vơi); đo 8 frame/scene cho thấy noise/frame chênh",
        "  1,62 lần, khớp với Δ −44,6 % của G1 và kéo theo G6/G7. v2 sắp theo",
        "  `(itr_after_water, tên)` và đảo parity theo ô để hai vai bằng nhau",
        "  ở từng mốc `w_itr`.",
        "- hệ quả: so sánh hai vai **trong cùng một ô** không còn nghĩa vì",
        "  chúng đo ở chu kỳ nước khác nhau; chỉ aggregate theo vai mới dùng được.",
        "",
        "> Số liệu của luật v1 (`SPLIT_GATE ok=False failed=[G1,G6,G7]`)",
        "> **không dùng nữa**. Mọi bảng dưới đây sinh lại bằng luật v2.",
        "",
        "## Bối cảnh",
        "",
        "Tham số generator v2 đang được đo trên toàn bộ 207 scene rồi báo cáo",
        "khớp trên chính 207 scene đó, nên mọi con số là in-sample. Cổng này",
        "chia dataset thành `cal` (được chọn tham số) và `held-out` (chỉ dùng để",
        "kiểm) theo luật v2: 1:1 trong từng ô, sắp theo `itr_after_water`, đảo",
        "parity theo ô, scene dư về `cal`, không RNG. Cổng chỉ PASS khi 7/7",
        "tiêu chí đạt; `held-out` không được dùng để chọn tham số.",
        "",
        "## Mẫu",
        "",
        f"- lệnh: `{sample['command']}`",
        f"- `--frames-per-scene`: **{sample['frames_per_scene']}**",
        f"- `--limit-scenes`: **{sample['limit_scenes']}** "
        "(0 = không giới hạn)",
        "- clustering cổng: DBSCAN trên mặt phẳng `(azimuth, elevation)`, "
        f"`eps = {ANGULAR_EPS_DEG}°`, elevation snap lưới "
        f"`{ELEVATION_STEP_DEG}°`, `minPts = {MIN_PTS}`, azimuth wrap 360° "
        "`[CHỌN]`",
        "- clustering phụ: single-linkage trên `(x, y)` bán kính "
        f"**{RADIUS_M} m**, giữ cụm **>= {MIN_PTS} điểm** "
        "(chỉ dùng cho bảng phụ)",
        "",
        "| vai | scene | frame |",
        "|---|---:|---:|",
        f"| cal | {sample['scenes'][ROLE_CAL]} | "
        f"{measured['frames'][ROLE_CAL]} |",
        f"| held-out | {sample['scenes'][ROLE_HELD_OUT]} | "
        f"{measured['frames'][ROLE_HELD_OUT]} |",
        f"| cal_a | {sample['scenes']['cal_a']} | "
        f"{measured['frames']['cal_a']} |",
        f"| cal_b | {sample['scenes']['cal_b']} | "
        f"{measured['frames']['cal_b']} |",
        "",
        f"- frame bị bỏ (thiếu file hoặc `labels.size != points.shape[0]`): "
        f"**{sample['skipped']}** "
        f"(cal {measured['skipped'][ROLE_CAL]}, "
        f"held-out {measured['skipped'][ROLE_HELD_OUT]})",
        "",
        "## Bảng 1 — Split theo ô",
        "",
        *_table1(split),
        "",
        "## Bảng 4 — Cân bằng `itr_after_water`",
        "",
        "Số scene mỗi mốc `w_itr` phải bằng nhau giữa `cal` và `held-out`, cho",
        "từng group và toàn cục. Bảng tính trên toàn bộ split, không phụ thuộc",
        "`--limit-scenes`.",
        "",
        *_table4(balance),
        "",
        "- 34 ô đủ 6 scene: `cal` và `held-out` bằng nhau tuyệt đối ở cả 6 mốc",
        "  (mỗi vai 3 scene/mốc/ô).",
        "- Ô `Golf_dynamic` 80 km/h / 30 m chỉ có 2 scene (`w_itr` 1 và 6), ô",
        "  `Golf_dynamic` 90 km/h / 20 m chỉ có 1 scene (`w_itr` 1). Vì tổng",
        "  toàn cục ở mốc `w=6` là **35** (lẻ) nên không thể chia đều: một vai",
        "  buộc phải nhận 18, vai kia 17. Các mốc `w=1…5` bằng nhau (18/18 rồi",
        "  17/17), `w=6` lệch đúng 1 scene — đây là dư lượng của dữ liệu, không",
        "  phải lỗi luật chia.",
        "",
        "## Bảng 2 — 7 tiêu chí đóng băng `[ĐO]`",
        "",
        "Ngưỡng hiệu dụng = `max(sàn, 2 × Δ_halfsplit)`; `Δ_halfsplit` là",
        "chênh giữa hai nửa xen kẽ của `cal` và chỉ là **sàn nhiễu nội tại**",
        "`[CHỌN]`. G6 PASS khi cả p5, p50, p95 đạt. G2/G3/G4 dùng DBSCAN góc",
        "theo recipe paper.",
        "",
        *_table2(results, metrics_by_role),
        "",
        "### Bảng phụ — recipe legacy Euclid 0,5 m (chỉ để đối chiếu ticket 16) `[ĐO]`",
        "",
        "Recipe này không tham gia cổng; chỉ để so thang số. `17,06` "
        "cụm/frame của ticket 16 sinh bởi toán tử `0,5 m` + `dense_min = 5` "
        "nên **đếm thiếu** so với paper (33 cụm/frame ở 100 km/h, Fig. 1); "
        "không được lấy `17,06` làm mốc.",
        "",
        *_table_legacy(metrics_by_role),
    ]

    notes = [
        f"- {result.id}: {result.note}"
        for result in results
        if not result.passed and result.note
    ]
    if notes:
        lines += ["", "Ghi chú các dòng FAIL:", "", *notes]

    lines += [
        "",
        "## Bảng 3 — Số bàn giao cho 29c `[ĐO]`",
        "",
        f"`tail_block_height_frac` chia độ cao trên mặt đường cho "
        f"**{BOX_HEIGHT_M} m** ({BOX_HEIGHT_SOURCE}).",
        "",
        *_table3(summaries[ROLE_CAL]),
        "",
        "## Kết luận",
        "",
    ]

    if not failed:
        lines.append(
            "7/7 PASS — split đại diện được cho các tham số dùng ở 29c."
        )
    else:
        lines.append(
            f"{len(failed)}/7 FAIL ({', '.join(failed)}) — split không đại "
            "diện được cho (các) tham số tương ứng."
        )
        lines.append("Không đổi ngưỡng, không trộn vai.")

    lines += [
        "",
        "## Caveats",
        "",
        "- `Δ_halfsplit` chỉ là sàn nhiễu nội tại của `cal`, không phải "
        "khoảng tin cậy hình thức `[CHỌN]`.",
        "- Cổng dùng DBSCAN góc `minPts = 3`, `eps = 0,7°`, elevation snap "
        "`0,333°`; paper không nói rõ lân cận là hộp hay tròn trong mặt "
        "phẳng góc nên dùng đĩa Euclid `[CHỌN]`. Single-linkage 0,5 m chỉ "
        "còn là bảng phụ.",
        "- Paper **không chia scene**: paper giữ điều kiện chưa dùng khi "
        "hiệu chỉnh trên cùng bộ dữ liệu (§IV-1) và có bộ spray test riêng "
        "1.463 frame. Split 1:1 theo scene ở đây là `[CHỌN]` của mình, "
        "không phải protocol paper.",
        "- Label `2` của SemanticSpray gồm cả nhiễu không phải spray (mưa, "
        "phản xạ), nên mọi đại lượng đều là thống kê của *noise*, không "
        "riêng plume.",
        "- `amb_tmp` không đưa vào ô chia: nó lệch theo lô và sẽ làm ô mất "
        "cân bằng mà không thêm thông tin.",
        "",
    ]
    return "\n".join(lines)


def _build(args: argparse.Namespace) -> int:
    metas = read_dataset(args.data)
    split = build_split(metas)
    dump_split(split, args.split)
    unpaired = sum(1 for cell in split["cells"] if cell["unpaired"])
    print(
        f"SPLIT_BUILT cal={split['counts'][ROLE_CAL]} "
        f"heldout={split['counts'][ROLE_HELD_OUT]} "
        f"cells={len(split['cells'])} unpaired={unpaired}"
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    split_path = Path(args.split)
    if not split_path.is_file():
        print("SPLIT_VERIFY_MISMATCH n=1")
        print(f"missing split file: {split_path}")
        return 1
    built = build_split(read_dataset(args.data))
    problems = verify_split(built, split_path)
    if problems:
        print(f"SPLIT_VERIFY_MISMATCH n={len(problems)}")
        for problem in problems:
            print(problem)
        return 1
    print("SPLIT_VERIFY_OK")
    return 0


def _measure(args: argparse.Namespace) -> int:
    split = load_split(args.split)
    balance = itr_balance(read_dataset(args.data), split)
    cal_paths = role_scenes(split, ROLE_CAL, args.data)
    held_paths = role_scenes(split, ROLE_HELD_OUT, args.data)
    if args.limit_scenes:
        cal_paths = cal_paths[: args.limit_scenes]
        held_paths = held_paths[: args.limit_scenes]

    measured = measure_roles(cal_paths, held_paths, args.frames_per_scene)
    results = evaluate_criteria(measured["metrics"])

    command = _display_command()
    sample = {
        "command": command,
        "frames_per_scene": args.frames_per_scene,
        "limit_scenes": args.limit_scenes,
        "scenes": {
            ROLE_CAL: len(cal_paths),
            ROLE_HELD_OUT: len(held_paths),
            "cal_a": len(cal_paths[::2]),
            "cal_b": len(cal_paths[1::2]),
        },
        "skipped": sum(measured["skipped"].values()),
    }

    report = render_report(split, measured, results, sample, balance)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    frames = measured["frames"]
    failed = [result.id for result in results if not result.passed]
    ok = not failed
    print(
        f"SPLIT_GATE ok={ok} failed=[{','.join(failed)}] "
        f"frames_cal={frames[ROLE_CAL]} "
        f"frames_heldout={frames[ROLE_HELD_OUT]}"
    )
    print(f"wrote {args.out}")
    if measured["skipped"]:
        print(f"skipped frames: {sample['skipped']}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        default=str(REPO / "data" / "SemanticSprayDataset"),
    )
    parser.add_argument(
        "--split",
        default=str(REPO / "spray" / "config" / "semantic_spray_split.yaml"),
    )
    parser.add_argument(
        "--out",
        default=str(
            REPO
            / "docs"
            / "measurements"
            / "semantic-spray-cal-vs-heldout.md"
        ),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--measure", action="store_true")
    parser.add_argument("--frames-per-scene", type=int, default=60)
    parser.add_argument(
        "--limit-scenes",
        type=int,
        default=0,
        help="keep only the first N scenes of each role (0 = all)",
    )
    args = parser.parse_args()

    if args.build:
        return _build(args)
    if args.verify:
        return _verify(args)
    return _measure(args)


if __name__ == "__main__":
    sys.exit(main())
