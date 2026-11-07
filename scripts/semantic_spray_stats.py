#!/usr/bin/env python3
"""Measure SemanticSpray plume geometry versus range.

The script reads the extracted SemanticSpray dataset, clusters label-2 (noise)
points with the same single-linkage rule used for the simulator comparison
(radius 0.5 m, dense cluster >= 5 points), and reports per-range geometry.

Two reports can be produced:

* geometry report (default): ``docs/plume-geometry-vs-real.md`` with
  ``n_points``, ``r_extent``, ``r_range``, ``r_range / r_extent``, ``n_rings``
  and ``ring_span`` per distance bucket;
* legacy summary report (opt-in via ``--basic-out``): the older
  ``docs/semantic-spray-stats.md`` content rendered by
  ``spray.spray_stats.render_markdown``.

One-command reproduction of the committed geometry report (2,070 frames):
    CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python \
        scripts/semantic_spray_stats.py

To widen the sample when a distance bucket has fewer than 30 clusters:
    ... scripts/semantic_spray_stats.py \
        --frames-per-scene 20 --label "expanded-20-fps" \
        --geometry-out docs/plume-geometry-vs-real-expanded.md

Sample flags are recorded verbatim in the generated report, so a table can
always be traced back to the frames that produced it.
"""
import argparse
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from spray.plume import PlumeConfig  # noqa: E402
from spray.spray_stats import (  # noqa: E402
    NOISE_LABEL,
    StatsAccumulator,
    compare_to_simulator,
    load_scan,
    render_markdown,
    single_linkage,
)

# (low, high, label); low inclusive, high exclusive. The last bucket is open.
RANGE_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 5.0, "0–5"),
    (5.0, 10.0, "5–10"),
    (10.0, 20.0, "10–20"),
    (20.0, 30.0, "20–30"),
    (30.0, 50.0, "30–50"),
    (50.0, math.inf, ">50"),
)


def bucket_index(distance: float) -> int:
    for index, (low, high, _) in enumerate(RANGE_BUCKETS):
        if low <= distance < high:
            return index
    return len(RANGE_BUCKETS) - 1


@dataclass(frozen=True)
class ClusterRecord:
    """Geometry of one noise cluster (single-linkage on xy, radius 0.5 m)."""

    point_count: int
    d_sensor_m: float
    r_extent_m: float
    r_range_m: float
    n_rings: int
    ring_span: int


def scene_dirs(root: str, groups: list[str] | None = None) -> list[str]:
    scenes = []
    for group in sorted(os.listdir(root)):
        group_dir = os.path.join(root, group)
        if not os.path.isdir(group_dir):
            continue
        if groups and group not in groups:
            continue
        for scene in sorted(os.listdir(group_dir)):
            scene_dir = os.path.join(group_dir, scene)
            if os.path.isdir(os.path.join(scene_dir, "velodyne")):
                scenes.append(scene_dir)
    return scenes


def sample_scan_ids(scene: str, limit: int) -> list[str]:
    ids = sorted(
        name[:-4] for name in os.listdir(os.path.join(scene, "velodyne"))
        if name.endswith(".bin")
    )
    if limit <= 0 or limit >= len(ids):
        return ids
    picks = np.linspace(0, len(ids) - 1, limit).round().astype(int)
    return [ids[index] for index in sorted(set(picks.tolist()))]


def scan_cluster_records(
    points: np.ndarray, labels: np.ndarray, radius: float = 0.5
) -> list[ClusterRecord]:
    """Cluster label-2 points and return per-cluster radial geometry."""
    noise = points[labels == NOISE_LABEL]
    if len(noise) == 0:
        return []

    cluster_ids = single_linkage(noise[:, :2], radius)
    point_ranges = np.linalg.norm(noise[:, :3], axis=1)
    point_rings = np.rint(noise[:, 4]).astype(np.int64)

    records: list[ClusterRecord] = []
    for cluster_id in range(int(cluster_ids.max()) + 1):
        member_mask = cluster_ids == cluster_id
        members = noise[member_mask][:, :3].astype(np.float64)
        centroid = members.mean(axis=0)
        member_ranges = point_ranges[member_mask]
        member_rings = np.unique(point_rings[member_mask])
        records.append(
            ClusterRecord(
                point_count=int(member_mask.sum()),
                d_sensor_m=float(np.linalg.norm(centroid)),
                r_extent_m=float(
                    np.max(np.linalg.norm(members - centroid, axis=1))
                ),
                r_range_m=float(member_ranges.max() - member_ranges.min()),
                n_rings=int(len(member_rings)),
                ring_span=int(member_rings.max() - member_rings.min()),
            )
        )
    return records


@dataclass
class BucketStats:
    n_clusters: int = 0
    point_counts: list[int] = field(default_factory=list)
    r_extents: list[float] = field(default_factory=list)
    r_ranges: list[float] = field(default_factory=list)
    range_extent_ratios: list[float] = field(default_factory=list)
    n_rings: list[int] = field(default_factory=list)
    ring_spans: list[int] = field(default_factory=list)


@dataclass
class GeometryAccumulator:
    radius: float = 0.5
    dense_min: int = 5
    frames: int = 0
    frames_with_noise: int = 0
    noise_points: int = 0
    all_clusters: int = 0
    dense_clusters: int = 0
    buckets: dict[int, BucketStats] = field(
        default_factory=lambda: {
            index: BucketStats() for index in range(len(RANGE_BUCKETS))
        }
    )

    def add(
        self,
        labels: np.ndarray,
        records: list[ClusterRecord],
    ) -> None:
        noise_count = int(np.count_nonzero(labels == NOISE_LABEL))
        self.frames += 1
        self.noise_points += noise_count
        self.all_clusters += len(records)
        if noise_count:
            self.frames_with_noise += 1
        for record in records:
            if record.point_count < self.dense_min:
                continue
            self.dense_clusters += 1
            bucket = self.buckets[bucket_index(record.d_sensor_m)]
            bucket.n_clusters += 1
            bucket.point_counts.append(record.point_count)
            bucket.r_extents.append(record.r_extent_m)
            bucket.r_ranges.append(record.r_range_m)
            if record.r_extent_m > 0.0:
                bucket.range_extent_ratios.append(
                    record.r_range_m / record.r_extent_m
                )
            bucket.n_rings.append(record.n_rings)
            bucket.ring_spans.append(record.ring_span)

    def summary(self) -> dict:
        rows = []
        for index, (low, high, label) in enumerate(RANGE_BUCKETS):
            bucket = self.buckets[index]
            rows.append(
                {
                    "label": label,
                    "low": low,
                    "high": high,
                    "n_clusters": bucket.n_clusters,
                    "n_points_median": _percentile(bucket.point_counts, 50),
                    "n_points_p25": _percentile(bucket.point_counts, 25),
                    "n_points_p75": _percentile(bucket.point_counts, 75),
                    "r_extent_median": _percentile(bucket.r_extents, 50),
                    "r_range_median": _percentile(bucket.r_ranges, 50),
                    "ratio_median": _percentile(bucket.range_extent_ratios, 50),
                    "ratio_n": len(bucket.range_extent_ratios),
                    "n_rings_median": _percentile(bucket.n_rings, 50),
                    "n_rings_p25": _percentile(bucket.n_rings, 25),
                    "n_rings_p75": _percentile(bucket.n_rings, 75),
                    "ring_span_median": _percentile(bucket.ring_spans, 50),
                }
            )
        all_points = [v for b in self.buckets.values() for v in b.point_counts]
        all_extents = [v for b in self.buckets.values() for v in b.r_extents]
        all_ranges = [v for b in self.buckets.values() for v in b.r_ranges]
        all_ratios = [v for b in self.buckets.values() for v in b.range_extent_ratios]
        all_rings = [v for b in self.buckets.values() for v in b.n_rings]
        all_spans = [v for b in self.buckets.values() for v in b.ring_spans]
        return {
            "radius_m": self.radius,
            "dense_min": self.dense_min,
            "frames": self.frames,
            "frames_with_noise": self.frames_with_noise,
            "noise_points": self.noise_points,
            "all_clusters": self.all_clusters,
            "dense_clusters": self.dense_clusters,
            "buckets": rows,
            "all": {
                "n_clusters": self.dense_clusters,
                "n_points_median": _percentile(all_points, 50),
                "r_extent_median": _percentile(all_extents, 50),
                "r_range_median": _percentile(all_ranges, 50),
                "ratio_median": _percentile(all_ratios, 50),
                "ratio_n": len(all_ratios),
                "n_rings_median": _percentile(all_rings, 50),
                "ring_span_median": _percentile(all_spans, 50),
            },
        }


def _sample_description(args: argparse.Namespace, scenes: list[str]) -> dict:
    group_counts: dict[str, int] = {}
    for scene in scenes:
        group = os.path.basename(os.path.dirname(scene))
        group_counts[group] = group_counts.get(group, 0) + 1
    return {
        "label": args.label or "(none)",
        "groups_arg": args.groups,
        "group_counts": group_counts,
        "scenes": len(scenes),
        "frames_per_scene": args.frames_per_scene,
        "scene_limit": args.scenes,
        "scene_stride": args.scene_stride,
        "scene_offset": args.scene_offset,
        "radius_m": args.radius,
        "dense_min": args.dense_min,
        "min_clusters": args.min_clusters,
        "command": " ".join(
            [
                os.path.basename(sys.executable),
                os.path.relpath(__file__, REPO),
                *sys.argv[1:],
            ]
        ),
    }


def render_geometry_markdown(
    summary: dict,
    sample: dict,
    config: PlumeConfig,
) -> str:
    buckets = summary["buckets"]
    min_clusters = sample["min_clusters"]
    enough = {
        row["label"]: row["n_clusters"] >= min_clusters for row in buckets
    }

    lines = [
        "# Plume geometry vs range on SemanticSpray",
        "",
        "Sinh bởi `scripts/semantic_spray_stats.py` (ticket 16). Chỉ đo hình học",
        "plume thật; **không sửa generator**. Số đo gắn nhãn `[ĐO]`; tham chiếu",
        "generator gắn nhãn `[CODE]`.",
        "",
        "## Sample",
        "",
        f"- label: `{sample['label']}`",
        f"- lệnh: `{sample['command']}`",
        "- cờ: "
        f"`--groups={sample['groups_arg']} "
        f"--scene-offset={sample['scene_offset']} "
        f"--scene-stride={sample['scene_stride']} "
        f"--scenes={sample['scene_limit']} "
        f"--frames-per-scene={sample['frames_per_scene']} "
        f"--radius={sample['radius_m']} --dense-min={sample['dense_min']}`",
        f"- scenes: **{sample['scenes']}** "
        f"({', '.join(f'{k}={v}' for k, v in sample['group_counts'].items())})",
        f"- frames đã đọc: **{summary['frames']}**",
        f"- frames có noise label: **{summary['frames_with_noise']}**",
        f"- noise points: **{summary['noise_points']}**",
        f"- clusters: **{summary['all_clusters']}** (mọi kích thước), "
        f"**{summary['dense_clusters']}** dense (>= {summary['dense_min']} điểm)",
        "- clustering: single-linkage trên `(x, y)`, radius "
        f"**{summary['radius_m']} m** (giữ nguyên như `docs/semantic-spray-stats.md`)",
        "",
        "## Định nghĩa đo",
        "",
        "- `d_sensor`: `‖centroid‖` (norm 3D trong LiDAR frame).",
        "- `n_points`: số điểm trong cluster.",
        "- `r_extent`: `max ‖p − centroid‖` — bán kính ngoài của cluster.",
        "- `r_range`: `max ‖p‖ − min ‖p‖` — độ dày theo phương bán kính.",
        "- `n_rings`: số giá trị `ring` khác nhau trong cluster.",
        "- `ring_span`: `max(ring) − min(ring)`.",
        "- Bucket: `[low, high)`, bucket cuối là `>50 m`.",
        "- Ngưỡng kết luận: bucket có **< "
        f"{min_clusters} dense clusters** thì ghi `quá ít, không kết luận`.",
        "",
        "## Bảng 1 — Số điểm mỗi cluster theo cự ly `[ĐO]`",
        "",
        "| bucket (m) | n_clusters | median n_points | p25 | p75 |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += _density_rows(buckets, min_clusters)

    lines += [
        "",
        "## Bảng 2 — Hình học bán kính theo cự ly `[ĐO]`",
        "",
        "Tham chiếu generator `[CODE]`: "
        f"`cluster_radius_median_m = {config.cluster_radius_median_m:.2f} m`.",
        "",
        "| bucket (m) | n_clusters | median r_extent (m) | median r_range (m) | median r_range/r_extent | n (ratio) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines += _radial_rows(buckets, min_clusters)

    lines += [
        "",
        "## Bảng 3 — Cấu trúc vòng quét theo cự ly `[ĐO]`",
        "",
        "| bucket (m) | n_clusters | median n_rings | p25 | p75 | median ring_span |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines += _ring_rows(buckets, min_clusters)

    overall = summary["all"]
    lines += [
        "",
        f"Toàn bộ **{overall['n_clusters']}** dense clusters (mọi cự ly): "
        f"median `n_points` = {overall['n_points_median']:.1f}, "
        f"median `r_extent` = {overall['r_extent_median']:.3f} m, "
        f"median `r_range` = {overall['r_range_median']:.3f} m, "
        f"median `r_range/r_extent` = {overall['ratio_median']:.3f} "
        f"(n={overall['ratio_n']}), "
        f"median `n_rings` = {overall['n_rings_median']:.1f}, "
        f"median `ring_span` = {overall['ring_span_median']:.0f} `[ĐO]`.",
        "",
        "## Kết luận bằng số",
        "",
        *_geometry_conclusions(buckets, enough, min_clusters, config),
        "",
        "## Caveats",
        "",
        "- Label `2` của SemanticSpray là *noise*, gồm spray và các nguồn nhiễu",
        "  khác. Chỉ dense cluster (>= "
        f"{summary['dense_min']} điểm) được đo hình học.",
        "- Single-linkage trên `(x, y)` nối các điểm cách nhau <= radius, nên một",
        "  cluster có thể bị nối chuỗi. `r_extent` và `r_range` vì vậy là cận trên",
        "  của hình học plume đơn lẻ; `n_rings` cũng bị ảnh hưởng cùng chiều.",
        "- `d_sensor` là norm 3D của centroid, không phải khoảng cách ngang",
        "  (`hypot(x, y)`) đã dùng trong `docs/semantic-spray-stats.md`.",
        "- Script chỉ đo, không đề xuất hay sửa tham số generator (ticket 17).",
        "",
    ]
    return "\n".join(lines)


def _density_rows(buckets: list[dict], min_clusters: int) -> list[str]:
    rows = []
    for row in buckets:
        if row["n_clusters"] < min_clusters:
            rows.append(
                f"| {row['label']} | {row['n_clusters']} | "
                "quá ít, không kết luận | quá ít, không kết luận | "
                "quá ít, không kết luận |"
            )
            continue
        rows.append(
            f"| {row['label']} | {row['n_clusters']} | "
            f"{row['n_points_median']:.1f} | {row['n_points_p25']:.1f} | "
            f"{row['n_points_p75']:.1f} |"
        )
    return rows


def _radial_rows(buckets: list[dict], min_clusters: int) -> list[str]:
    rows = []
    for row in buckets:
        if row["n_clusters"] < min_clusters:
            rows.append(
                f"| {row['label']} | {row['n_clusters']} | "
                "quá ít, không kết luận | quá ít, không kết luận | "
                "quá ít, không kết luận | quá ít, không kết luận |"
            )
            continue
        rows.append(
            f"| {row['label']} | {row['n_clusters']} | "
            f"{row['r_extent_median']:.3f} | {row['r_range_median']:.3f} | "
            f"{row['ratio_median']:.3f} | {row['ratio_n']} |"
        )
    return rows


def _ring_rows(buckets: list[dict], min_clusters: int) -> list[str]:
    rows = []
    for row in buckets:
        if row["n_clusters"] < min_clusters:
            rows.append(
                f"| {row['label']} | {row['n_clusters']} | "
                "quá ít, không kết luận | quá ít, không kết luận | "
                "quá ít, không kết luận | quá ít, không kết luận |"
            )
            continue
        rows.append(
            f"| {row['label']} | {row['n_clusters']} | "
            f"{row['n_rings_median']:.1f} | {row['n_rings_p25']:.1f} | "
            f"{row['n_rings_p75']:.1f} | {row['ring_span_median']:.0f} |"
        )
    return rows


def _bucket_by_label(buckets: list[dict], label: str) -> dict | None:
    for row in buckets:
        if row["label"] == label:
            return row
    return None


def _geometry_conclusions(
    buckets: list[dict],
    enough: dict[str, bool],
    min_clusters: int,
    config: PlumeConfig,
) -> list[str]:
    near = _bucket_by_label(buckets, "0–5")
    mid = _bucket_by_label(buckets, "20–30")
    lines: list[str] = []

    if near and mid and enough["0–5"] and enough["20–30"]:
        ratio = (
            near["n_points_median"] / mid["n_points_median"]
            if mid["n_points_median"] > 0
            else float("nan")
        )
        lines.append(
            f"- `median n_points` giảm từ {near['n_points_median']:.1f} "
            f"(0–5 m, n={near['n_clusters']}) xuống "
            f"{mid['n_points_median']:.1f} (20–30 m, n={mid['n_clusters']}), "
            f"tỉ lệ {ratio:.1f}× `[ĐO]`."
        )
    else:
        lines.append(
            "- `median n_points` 0–5 m → 20–30 m: **quá ít, không kết luận** "
            f"(cần >= {min_clusters} dense clusters mỗi bucket)."
        )

    for row in buckets:
        if not enough[row["label"]]:
            continue
        lines.append(
            f"- `median r_range/r_extent` ở {row['label']} m là "
            f"{row['ratio_median']:.3f} (n={row['ratio_n']}): độ dày bán kính "
            f"là {row['ratio_median']:.3f} lần bán kính ngoài `[ĐO]`."
        )

    near_extent = near["r_extent_median"] if near and enough["0–5"] else None
    if near_extent is not None:
        lines.append(
            f"- `median r_extent` ở 0–5 m là {near_extent:.3f} m "
            f"(n={near['n_clusters']}) `[ĐO]`, tức "
            f"{near_extent / config.cluster_radius_median_m:.2f}× giá trị cấu "
            "hình "
            f"`cluster_radius_median_m = {config.cluster_radius_median_m:.2f} m` "
            "`[CODE]`."
        )

    for row in buckets:
        if not enough[row["label"]]:
            continue
        lines.append(
            f"- `median n_rings` ở {row['label']} m là "
            f"{row['n_rings_median']:.1f} (p25 "
            f"{row['n_rings_p25']:.1f}, p75 {row['n_rings_p75']:.1f}, "
            f"n={row['n_clusters']}), `median ring_span` "
            f"{row['ring_span_median']:.0f} `[ĐO]`."
        )

    return lines


def _percentile(values, q: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.percentile(array, q)) if len(array) else float("nan")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        default=os.path.join(REPO, "data", "SemanticSprayDataset"),
    )
    parser.add_argument("--frames-per-scene", type=int, default=10)
    parser.add_argument("--scenes", type=int, default=0, help="0 = all")
    parser.add_argument(
        "--scene-stride", type=int, default=1,
        help="keep every Nth scene after offset (1 = all)",
    )
    parser.add_argument(
        "--scene-offset", type=int, default=0,
        help="start at this scene index before applying stride",
    )
    parser.add_argument(
        "--groups", default="",
        help="comma-separated group names (default: all groups)",
    )
    parser.add_argument("--radius", type=float, default=0.5)
    parser.add_argument("--dense-min", type=int, default=5)
    parser.add_argument(
        "--min-clusters", type=int, default=30,
        help="minimum dense clusters per bucket before reporting numbers",
    )
    parser.add_argument(
        "--label", default="",
        help="free-form sample label recorded in the report",
    )
    parser.add_argument(
        "--geometry-out",
        default=os.path.join(REPO, "docs", "plume-geometry-vs-real.md"),
    )
    parser.add_argument(
        "--basic-out",
        default="",
        help="optional path for the legacy summary report (opt-in)",
    )
    parser.add_argument("--speed-kmh", type=float, default=50.0)
    args = parser.parse_args()

    groups = [name.strip() for name in args.groups.split(",") if name.strip()]
    scenes = scene_dirs(args.data, groups)
    scenes = scenes[args.scene_offset :: max(args.scene_stride, 1)]
    if args.scenes:
        scenes = scenes[: args.scenes]
    if not scenes:
        raise SystemExit(f"no scenes found under {args.data}")

    accumulator = GeometryAccumulator(radius=args.radius, dense_min=args.dense_min)
    basic = (
        StatsAccumulator(radius=args.radius, dense_min=args.dense_min)
        if args.basic_out
        else None
    )
    sampled_frames = 0
    for number, scene in enumerate(scenes, start=1):
        for scan_id in sample_scan_ids(scene, args.frames_per_scene):
            points, labels = load_scan(scene, scan_id)
            records = scan_cluster_records(points, labels, radius=args.radius)
            accumulator.add(labels, records)
            if basic is not None:
                basic.add(points, labels)
            sampled_frames += 1
        print(
            f"\rscene {number}/{len(scenes)}  frames {sampled_frames}",
            end="",
            flush=True,
        )
    print()

    sample = _sample_description(args, scenes)
    summary = accumulator.summary()
    report = render_geometry_markdown(summary, sample, PlumeConfig())

    os.makedirs(os.path.dirname(os.path.abspath(args.geometry_out)), exist_ok=True)
    with open(args.geometry_out, "w", encoding="utf-8") as handle:
        handle.write(report)
    print(f"wrote {args.geometry_out}")

    if basic is not None:
        basic_summary = basic.summary()
        rows = compare_to_simulator(basic_summary, speed_kmh=args.speed_kmh)
        basic_report = render_markdown(
            basic_summary,
            rows,
            scenes=len(scenes),
            sampled_frames=sampled_frames,
            speed_kmh=args.speed_kmh,
        )
        os.makedirs(
            os.path.dirname(os.path.abspath(args.basic_out)), exist_ok=True
        )
        with open(args.basic_out, "w", encoding="utf-8") as handle:
            handle.write(basic_report)
        print(f"wrote {args.basic_out}")

    for row in summary["buckets"]:
        print(
            f"  {row['label']:>6} m  n={row['n_clusters']:>5}  "
            f"n_points={row['n_points_median']:.1f}  "
            f"r_extent={row['r_extent_median']:.3f}  "
            f"r_range={row['r_range_median']:.3f}  "
            f"ratio={row['ratio_median']:.3f}  "
            f"n_rings={row['n_rings_median']:.1f}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
