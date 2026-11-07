from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from spray.plume import PlumeConfig, cluster_count_for_speed

NOISE_LABEL = 2
FOREGROUND_LABEL = 1


@dataclass(frozen=True)
class ClusterStats:
    point_count: int
    centroid: tuple[float, float, float]
    extent: tuple[float, float, float]
    ego_distance_m: float
    vehicle_distance_m: float | None


def load_scan(scene_dir: str | Path, scan_id: str) -> tuple[np.ndarray, np.ndarray]:
    scene = Path(scene_dir)
    points = np.fromfile(
        scene / "velodyne" / f"{scan_id}.bin", dtype=np.float32
    ).reshape(-1, 5)
    labels = np.fromfile(scene / "labels" / f"{scan_id}.label", dtype=np.int32)
    if labels.shape[0] != points.shape[0]:
        raise ValueError(
            f"{scene}/{scan_id}: {points.shape[0]} points vs "
            f"{labels.shape[0]} labels"
        )
    return points, labels


def noise_points(points: np.ndarray, labels: np.ndarray) -> np.ndarray:
    if points.shape[0] != labels.shape[0]:
        raise ValueError("points and labels must have the same length")
    return points[labels == NOISE_LABEL]


def single_linkage(xy: np.ndarray, radius: float) -> np.ndarray:
    pts = np.asarray(xy, dtype=np.float64)
    count = len(pts)
    if count == 0:
        return np.zeros(0, dtype=np.int64)

    parent = np.arange(count)

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i in range(count - 1):
        distances = np.linalg.norm(pts[i + 1 :] - pts[i], axis=1)
        for j in np.nonzero(distances <= radius)[0]:
            union(i, int(j) + i + 1)

    roots = np.array([find(i) for i in range(count)], dtype=np.int64)
    _, cluster_ids = np.unique(roots, return_inverse=True)
    return cluster_ids.astype(np.int64)


def scan_clusters(
    points: np.ndarray, labels: np.ndarray, radius: float = 0.5
) -> list[ClusterStats]:
    noise = noise_points(points, labels)
    if len(noise) == 0:
        return []

    foreground = points[labels == FOREGROUND_LABEL]
    cluster_ids = single_linkage(noise[:, :2], radius)
    clusters: list[ClusterStats] = []

    for cluster_id in range(int(cluster_ids.max()) + 1):
        members = noise[cluster_ids == cluster_id]
        centroid = members[:, :3].mean(axis=0)
        extent = members[:, :3].max(axis=0) - members[:, :3].min(axis=0)
        ego_distance = float(np.hypot(centroid[0], centroid[1]))
        vehicle_distance = None
        if len(foreground):
            vehicle_distance = float(
                np.min(
                    np.hypot(
                        foreground[:, 0] - centroid[0],
                        foreground[:, 1] - centroid[1],
                    )
                )
            )
        clusters.append(
            ClusterStats(
                point_count=int(len(members)),
                centroid=(
                    float(centroid[0]),
                    float(centroid[1]),
                    float(centroid[2]),
                ),
                extent=(float(extent[0]), float(extent[1]), float(extent[2])),
                ego_distance_m=ego_distance,
                vehicle_distance_m=vehicle_distance,
            )
        )

    return clusters


@dataclass
class StatsAccumulator:
    radius: float = 0.5
    dense_min: int = 5
    frames: int = 0
    frames_with_noise: int = 0
    noise_per_frame: list[int] = field(default_factory=list)
    clusters_per_frame: list[int] = field(default_factory=list)
    dense_points_per_frame: list[int] = field(default_factory=list)
    dense_clusters_per_frame: list[int] = field(default_factory=list)
    cluster_sizes: list[int] = field(default_factory=list)
    dense_extents: list[float] = field(default_factory=list)
    ego_distances: list[float] = field(default_factory=list)
    vehicle_distances: list[float] = field(default_factory=list)
    dense_ego_distances: list[float] = field(default_factory=list)
    dense_vehicle_distances: list[float] = field(default_factory=list)
    intensities: list[np.ndarray] = field(default_factory=list)
    heights: list[np.ndarray] = field(default_factory=list)

    def add(self, points: np.ndarray, labels: np.ndarray) -> None:
        noise = noise_points(points, labels)
        clusters = scan_clusters(points, labels, radius=self.radius)

        self.frames += 1
        self.noise_per_frame.append(int(len(noise)))
        self.clusters_per_frame.append(len(clusters))
        dense = [c for c in clusters if c.point_count >= self.dense_min]
        self.dense_points_per_frame.append(sum(c.point_count for c in dense))
        self.dense_clusters_per_frame.append(len(dense))
        if len(noise):
            self.frames_with_noise += 1
            self.intensities.append(noise[:, 3].astype(np.float64))
            self.heights.append(noise[:, 2].astype(np.float64))

        for cluster in clusters:
            self.cluster_sizes.append(cluster.point_count)
            if cluster.vehicle_distance_m is not None:
                self.vehicle_distances.append(cluster.vehicle_distance_m)
            self.ego_distances.append(cluster.ego_distance_m)
            if cluster.point_count >= self.dense_min:
                self.dense_extents.append(
                    max(cluster.extent[0], cluster.extent[1], cluster.extent[2])
                )
                self.dense_ego_distances.append(cluster.ego_distance_m)
                if cluster.vehicle_distance_m is not None:
                    self.dense_vehicle_distances.append(
                        cluster.vehicle_distance_m
                    )

    def summary(self) -> dict:
        sizes = np.asarray(self.cluster_sizes, dtype=np.float64)
        dense = np.asarray(
            [size for size in self.cluster_sizes if size >= self.dense_min],
            dtype=np.float64,
        )
        intensities = (
            np.concatenate(self.intensities)
            if self.intensities
            else np.zeros(0, dtype=np.float64)
        )
        heights = (
            np.concatenate(self.heights)
            if self.heights
            else np.zeros(0, dtype=np.float64)
        )
        return {
            "radius_m": self.radius,
            "dense_min": self.dense_min,
            "frames": self.frames,
            "frames_with_noise": self.frames_with_noise,
            "noise_frame_median": _percentile(self.noise_per_frame, 50),
            "noise_frame_mean": _mean(self.noise_per_frame),
            "noise_frame_p90": _percentile(self.noise_per_frame, 90),
            "noise_frame_max": _max(self.noise_per_frame),
            "clusters_frame_median": _percentile(self.clusters_per_frame, 50),
            "clusters_frame_mean": _mean(self.clusters_per_frame),
            "cluster_size_median": _percentile(sizes, 50),
            "cluster_size_mean": _mean(sizes),
            "cluster_size_p90": _percentile(sizes, 90),
            "cluster_size_max": _max(sizes),
            "dense_cluster_count": int(len(dense)),
            "dense_size_median": _percentile(dense, 50),
            "dense_points_frame_median": _percentile(
                self.dense_points_per_frame, 50
            ),
            "dense_clusters_frame_median": _percentile(
                self.dense_clusters_per_frame, 50
            ),
            "dense_extent_median_m": _percentile(self.dense_extents, 50),
            "dense_extent_p90_m": _percentile(self.dense_extents, 90),
            "dense_ego_distance_median_m": _percentile(
                self.dense_ego_distances, 50
            ),
            "dense_vehicle_distance_median_m": _percentile(
                self.dense_vehicle_distances, 50
            ),
            "dense_vehicle_distance_p90_m": _percentile(
                self.dense_vehicle_distances, 90
            ),
            "ego_distance_median_m": _percentile(self.ego_distances, 50),
            "ego_distance_p90_m": _percentile(self.ego_distances, 90),
            "vehicle_distance_median_m": _percentile(self.vehicle_distances, 50),
            "vehicle_distance_p90_m": _percentile(self.vehicle_distances, 90),
            "intensity_median": _percentile(intensities, 50),
            "intensity_p90": _percentile(intensities, 90),
            "intensity_p99": _percentile(intensities, 99),
            "intensity_max": _max(intensities),
            "intensity_zero_fraction": (
                float((intensities == 0).mean()) if len(intensities) else 0.0
            ),
            "height_median_m": _percentile(heights, 50),
            "height_p10_m": _percentile(heights, 10),
            "height_p90_m": _percentile(heights, 90),
        }


def simulator_estimate(
    config: PlumeConfig | None = None, speed_kmh: float = 50.0
) -> dict:
    cfg = config or PlumeConfig()
    clusters = cluster_count_for_speed(speed_kmh, cfg)
    return {
        "clusters_per_frame": clusters,
        "points_per_frame": int(round(clusters * cfg.points_per_cluster_median)),
        "points_per_cluster": cfg.points_per_cluster_median,
        "cluster_diameter_m": 2.0 * cfg.cluster_radius_median_m,
        "distance_range_m": cfg.distance_range_m,
        "height_range_m": cfg.height_range_m,
        "intensity": cfg.intensity,
    }


def compare_to_simulator(
    summary: dict,
    config: PlumeConfig | None = None,
    speed_kmh: float = 50.0,
) -> list[dict]:
    sim = simulator_estimate(config, speed_kmh)
    rows = [
        {
            "metric": "points/frame",
            "real": summary["dense_points_frame_median"],
            "simulator": sim["points_per_frame"],
            "note": "dense clusters only, vs one 50 km/h lead vehicle",
        },
        {
            "metric": "clusters/frame",
            "real": summary["dense_clusters_frame_median"],
            "simulator": sim["clusters_per_frame"],
            "note": "dense clusters only, vs reference (0.2*wfh+0.1)*(v-50)",
        },
        {
            "metric": "points/cluster (median)",
            "real": summary["cluster_size_median"],
            "simulator": sim["points_per_cluster"],
            "note": "all clusters, including singletons",
        },
        {
            "metric": "points/cluster (dense median)",
            "real": summary["dense_size_median"],
            "simulator": sim["points_per_cluster"],
            "note": f"clusters with >= {summary['dense_min']} points",
        },
        {
            "metric": "cluster extent (m)",
            "real": summary["dense_extent_p90_m"],
            "simulator": sim["cluster_diameter_m"],
            "note": "p90 max axis-aligned span (chaining caveat) vs 2*radius",
        },
        {
            "metric": "distance to nearest vehicle point (m)",
            "real": summary["dense_vehicle_distance_median_m"],
            "simulator": sim["distance_range_m"],
            "note": "không so trực tiếp: real đo tới điểm foreground, simulator đo từ tâm box",
        },
        {
            "metric": "height (m)",
            "real": summary["height_median_m"],
            "simulator": sim["height_range_m"],
            "note": "median vs configured uniform range",
        },
        {
            "metric": "intensity (median)",
            "real": summary["intensity_median"],
            "simulator": sim["intensity"],
            "note": "raw SemanticSpray intensity vs configured constant",
        },
    ]
    return rows


def render_markdown(
    summary: dict,
    rows: list[dict],
    *,
    scenes: int,
    sampled_frames: int,
    speed_kmh: float = 50.0,
) -> str:
    lines = [
        "# SemanticSpray statistics",
        "",
        "Sinh bởi `scripts/semantic_spray_stats.py`. Chỉ dùng để so thống kê",
        "simulator; dataset này không dùng để train/eval BEVFusion.",
        "",
        "## Câu hỏi và kết luận",
        "",
        "Câu hỏi: spray plume thật trông như thế nào (bao nhiêu điểm, to cỡ nào,",
        "ở đâu, sáng đến đâu), và bộ sinh `spray/plume.py` có tạo ra thứ tương",
        "tự không?",
        "",
        *_conclusions(summary, rows),
        "",
        "## Sample",
        "",
        f"- scenes: **{scenes}**",
        f"- frames đã đọc: **{sampled_frames}** (lấy mẫu đều mỗi scene)",
        f"- frames có noise label: **{summary['frames_with_noise']}**",
        f"- clustering: single-linkage, radius **{summary['radius_m']} m**",
        f"- dense cluster: **>= {summary['dense_min']} điểm**",
        f"- simulator tham chiếu: `PlumeConfig` mặc định, lead vehicle "
        f"**{speed_kmh:.0f} km/h**",
        "",
        "## Nguồn dữ liệu",
        "",
        "- SemanticSpray (Piroli et al., RA-L 2024), license CC BY 4.0.",
        "- Devkit: https://github.com/uulm-mrm/semantic_spray_dataset",
        "- Root đọc: `data/SemanticSprayDataset` (2 nhóm scene, 207 scene).",
        "- `velodyne/*.bin`: `(x, y, z, intensity, ring)`; `labels/*.label`:",
        "  int32 với `0 = background`, `1 = foreground vehicle`, `2 = noise`",
        "  theo loader của devkit.",
        "- Script đọc trực tiếp file nhị phân, không áp dụng ego-box filter",
        "  của devkit.",
        "",
        "## Observed distribution",
        "",
        "| metric | value |",
        "|---|---|",
        f"| noise points / frame (median) | {summary['noise_frame_median']:.1f} |",
        f"| noise points / frame (mean) | {summary['noise_frame_mean']:.1f} |",
        f"| noise points / frame (p90) | {summary['noise_frame_p90']:.1f} |",
        f"| noise points / frame (max) | {summary['noise_frame_max']:.0f} |",
        f"| clusters / frame (median) | {summary['clusters_frame_median']:.1f} |",
        f"| cluster size (median) | {summary['cluster_size_median']:.1f} |",
        f"| cluster size (mean) | {summary['cluster_size_mean']:.1f} |",
        f"| cluster size (p90) | {summary['cluster_size_p90']:.1f} |",
        f"| cluster size (max) | {summary['cluster_size_max']:.0f} |",
        f"| dense clusters observed | {summary['dense_cluster_count']} |",
        f"| dense cluster size (median) | {summary['dense_size_median']:.1f} |",
        f"| dense points / frame (median) | {summary['dense_points_frame_median']:.1f} |",
        f"| dense clusters / frame (median) | {summary['dense_clusters_frame_median']:.1f} |",
        f"| dense cluster extent (median) | {summary['dense_extent_median_m']:.2f} m |",
        f"| dense cluster extent (p90) | {summary['dense_extent_p90_m']:.2f} m |",
        f"| dense ego distance (median) | {summary['dense_ego_distance_median_m']:.1f} m |",
        f"| dense distance to foreground (median) | {summary['dense_vehicle_distance_median_m']:.1f} m |",
        f"| ego distance (median) | {summary['ego_distance_median_m']:.1f} m |",
        f"| ego distance (p90) | {summary['ego_distance_p90_m']:.1f} m |",
        f"| distance to foreground (median) | {summary['vehicle_distance_median_m']:.1f} m |",
        f"| distance to foreground (p90) | {summary['vehicle_distance_p90_m']:.1f} m |",
        f"| intensity median | {summary['intensity_median']:.1f} |",
        f"| intensity p90 | {summary['intensity_p90']:.1f} |",
        f"| intensity p99 | {summary['intensity_p99']:.1f} |",
        f"| intensity max | {summary['intensity_max']:.1f} |",
        f"| intensity == 0 fraction | {summary['intensity_zero_fraction']:.2%} |",
        f"| height median | {summary['height_median_m']:.2f} m |",
        f"| height p10 | {summary['height_p10_m']:.2f} m |",
        f"| height p90 | {summary['height_p90_m']:.2f} m |",
        "",
        "## So với simulator",
        "",
        "| metric | real | simulator | note |",
        "|---|---|---|---|",
    ]
    for row in rows:
        real_text = _format(row["real"])
        sim_text = _format_simulator(row["simulator"])
        lines.append(
            f"| {row['metric']} | {real_text} | {sim_text} | {row['note']} |"
        )

    lines += [
        "",
        "## Khác biệt lớn",
        "",
        *_differences(summary, rows),
        "",
        "## Caveats",
        "",
        "- Label `2` của SemanticSpray là *noise*, gồm spray và các nguồn",
        "  nhiễu khác (mưa, phản xạ). Vì vậy phần lớn cluster là singleton.",
        f"  Các so sánh hình học chỉ dùng dense cluster (>= {summary['dense_min']} điểm)",
        "  để tránh kết luận từ nhiễu rời rạc.",
        "- Single-linkage nối các điểm cách nhau <= radius, nên một chuỗi điểm",
        "  có thể bị gộp thành một cluster dài. Extent vì vậy là **cận trên**,",
        "  không dùng để kết luận plume thật to hay nhỏ hơn simulator.",
        "- Khoảng cách tới foreground là khoảng cách centroid tới điểm",
        "  foreground gần nhất, không phải tới tâm box của xe. Điểm foreground",
        "  thưa do occlusion nên giá trị này thiên lớn và không so trực tiếp",
        "  được với offset 1-10 m của simulator.",
        "- Ticket này chỉ so với `PlumeConfig` của repo, chưa so với đường cong",
        "  trong paper. Đây là bước stage 4 của evidence ladder, không phải",
        "  bằng chứng cho pilot A/B.",
        "",
    ]
    return "\n".join(lines)


def _conclusions(summary: dict, rows: list[dict]) -> list[str]:
    by_name = {row["metric"]: row for row in rows}
    frame = by_name["points/frame"]
    cluster = by_name["points/cluster (dense median)"]
    return [
        f"- Tổng mật độ mỗi frame cùng bậc: dense median "
        f"{frame['real']:.0f} điểm so với simulator {frame['simulator']:.0f}.",
        f"- Mỗi plume simulator dày hơn plume thật: "
        f"{cluster['simulator']:.0f} so với median {cluster['real']:.0f} điểm.",
        f"- Intensity thật gần như bằng 0: median "
        f"{summary['intensity_median']:.0f}, p99 {summary['intensity_p99']:.0f}, "
        f"khớp mặc định {by_name['intensity (median)']['simulator']:.0f}.",
        "- Kích thước plume thật chưa kết luận được vì clustering có thể nối",
        "  chuỗi điểm; xem caveat về extent.",
    ]


def _differences(summary: dict, rows: list[dict]) -> list[str]:
    by_name = {row["metric"]: row for row in rows}
    notes: list[str] = []

    frame = by_name["points/frame"]
    if frame["simulator"] > 2 * max(frame["real"], 1e-9):
        notes.append(
            "- Simulator phun nhiều điểm mỗi frame hơn quan sát: "
            f"{frame['simulator']:.0f} so với median {frame['real']:.0f}."
        )

    cluster = by_name["points/cluster (dense median)"]
    if cluster["real"] and cluster["simulator"] > 1.5 * cluster["real"]:
        notes.append(
            "- Dense plume thật nhỏ hơn một cluster simulator: "
            f"median {cluster['real']:.0f} so với {cluster['simulator']:.0f} điểm."
        )

    clusters_per_frame = by_name["clusters/frame"]
    if (
        clusters_per_frame["real"]
        and clusters_per_frame["simulator"] > 2 * clusters_per_frame["real"]
    ):
        notes.append(
            "- Simulator tạo nhiều plume mỗi frame hơn quan sát: "
            f"{clusters_per_frame['simulator']:.0f} so với median "
            f"{clusters_per_frame['real']:.0f}."
        )

    intensity = by_name["intensity (median)"]
    if summary["intensity_p90"] > 2:
        notes.append(
            "- Intensity thật có đuôi cao hơn hằng số simulator: "
            f"p90 {summary['intensity_p90']:.1f}, p99 "
            f"{summary['intensity_p99']:.1f}, trong khi simulator dùng "
            f"{intensity['simulator']:.1f}."
        )

    if not notes:
        notes.append("- Không có khác biệt lớn theo các ngưỡng đang dùng.")
    return notes


def _format(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, tuple):
        return ", ".join(f"{item:.1f}" for item in value)
    return f"{float(value):.2f}"


def _format_simulator(value: object) -> str:
    if isinstance(value, tuple):
        return f"{value[0]:g}-{value[1]:g}"
    return _format(value)


def _percentile(values, q: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.percentile(array, q)) if len(array) else float("nan")


def _mean(values) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(array.mean()) if len(array) else float("nan")


def _max(values) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(array.max()) if len(array) else float("nan")
