#!/usr/bin/env python3
"""Ticket 29e-d-ii: measure how the DBSCAN clusters sit next to each other.

Step 2 of the ticket: **measure only**. On the label-2 points of ``cal``
(3 scenes x 30 frames per cell, 2 classes, 9 speeds) the recipe is the same
DBSCAN as ``spray.semantic_stats`` (``eps = 0.7 deg``, ``minPts = 3``) in the
discretized azimuth/elevation plane. For every frame and every cluster:

- ``nn``          centroid -> nearest other centroid in the same frame (m);
- ``nn_norm``     ``nn / (r_i + r_j)`` with ``r`` the paper radius (max
                  distance from a point to the cluster centre); ``< 1`` means
                  the two spheres overlap;
- ``overlap_frac`` share of clusters (that have a neighbour) with ``nn_norm < 1``;
- ``pts_in_overlap`` share of points that live in an overlapping cluster;
- ``n_merged``    clusters with ``elong > 1.5`` (DBSCAN already fused them);
- ``nn_merged``   median ``nn_norm`` of those merged clusters.

The tables (by class x speed, and by the four range buckets) go to
``docs/measurements/29ed2-overlap.md``.

**Stop gate:** if the pooled ``overlap_frac`` is below 5 % the overlap
hypothesis is wrong -- stop and report to the PM. The generator is never
modified from here.

    /opt/anaconda3/bin/python scripts/measure_29ed2.py

Only numpy + stdlib.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.measure_29ed import (
    BUCKETS,
    GROUPS,
    SPEEDS_KMH,
    _bucket_label,
    _fmt,
    _stats,
    evenly,
    scenes_for,
)
from spray.semantic_stats import cluster_angular

DOC = Path("docs/measurements/29ed2-overlap.md")
OVERLAP_THRESHOLD = 0.05
MERGED_ELONG = 1.5
SHARES = (0.05, 0.10, 0.25)
FIELDS = (
    "d",
    "n",
    "r_cl",
    "elong",
    "nn",
    "nn_norm",
    "nn_merged",
    "merged",
    "overlap",
)


def nearest_neighbours(
    centres: np.ndarray, radii: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Distance and normalised distance to the nearest other centroid.

    ``centres`` is ``(k, 3)`` in metres, ``radii`` is ``(k,)``. A frame with a
    single cluster has no neighbour, so both outputs are ``nan`` there.
    """
    centres = np.atleast_2d(np.asarray(centres, dtype=np.float64))
    radii = np.asarray(radii, dtype=np.float64).reshape(-1)
    count = centres.shape[0]
    distance = np.full(count, np.nan)
    normalised = np.full(count, np.nan)
    if count < 2:
        return distance, normalised
    delta = centres[:, None, :] - centres[None, :, :]
    pairwise = np.linalg.norm(delta, axis=2)
    np.fill_diagonal(pairwise, np.inf)
    nearest = np.argmin(pairwise, axis=1)
    distance = pairwise[np.arange(count), nearest]
    reach = radii + radii[nearest]
    with np.errstate(divide="ignore", invalid="ignore"):
        normalised = np.where(reach > 0.0, distance / reach, np.inf)
    return distance, normalised


def overlap_frac(normalised: np.ndarray) -> float:
    """Share of neighbour-having clusters with ``nn_norm < 1``."""
    values = np.asarray(normalised, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    return float(np.mean(values < 1.0))


def pts_in_overlap(
    normalised: np.ndarray, sizes: np.ndarray
) -> float:
    """Share of points living in a cluster with ``nn_norm < 1``."""
    values = np.asarray(normalised, dtype=np.float64)
    weights = np.asarray(sizes, dtype=np.float64)
    total = float(weights.sum())
    if total <= 0.0:
        return float("nan")
    inside = np.isfinite(values) & (values < 1.0)
    return float(weights[inside].sum() / total)


def n_merged(elong: np.ndarray) -> int:
    """Number of clusters already fused by DBSCAN (``elong > 1.5``)."""
    return int(np.sum(np.asarray(elong, dtype=np.float64) > MERGED_ELONG))


def nn_merged(elong: np.ndarray, normalised: np.ndarray) -> float:
    """Median ``nn_norm`` over the merged clusters."""
    values = np.asarray(normalised, dtype=np.float64)
    mask = np.asarray(elong, dtype=np.float64) > MERGED_ELONG
    values = values[mask & np.isfinite(values)]
    return float(np.median(values)) if values.size else float("nan")


def frame_clusters(points: np.ndarray) -> dict[str, np.ndarray]:
    """Per-cluster quantities plus the within-frame nearest neighbour."""
    labels = cluster_angular(points)
    ranges = np.linalg.norm(points[:, :3].astype(np.float64), axis=1)
    centres: list[np.ndarray] = []
    radii: list[float] = []
    spans: list[float] = []
    sizes: list[int] = []
    ranges_out: list[float] = []
    for cluster_id in np.unique(labels):
        if cluster_id < 0:
            continue
        mask = labels == cluster_id
        members = points[mask][:, :3].astype(np.float64)
        centre = members.mean(axis=0)
        reach = float(np.max(np.linalg.norm(members - centre, axis=1)))
        member_ranges = ranges[mask]
        centres.append(centre)
        radii.append(reach)
        spans.append(float(member_ranges.max() - member_ranges.min()))
        sizes.append(int(members.shape[0]))
        ranges_out.append(float(np.linalg.norm(centre)))
    if not centres:
        return {field: np.zeros(0) for field in FIELDS}
    radius_array = np.asarray(radii, dtype=np.float64)
    distance, normalised = nearest_neighbours(
        np.asarray(centres, dtype=np.float64), radius_array
    )
    elong = np.asarray(spans) / np.where(radius_array > 0.0, radius_array, np.nan)
    merged = elong > MERGED_ELONG
    return {
        "d": np.asarray(ranges_out, dtype=np.float64),
        "n": np.asarray(sizes, dtype=np.float64),
        "r_cl": radius_array,
        "elong": elong,
        "nn": distance,
        "nn_norm": normalised,
        "nn_merged": np.where(merged, normalised, np.nan),
        "merged": merged.astype(np.float64),
        "overlap": (np.isfinite(normalised) & (normalised < 1.0)).astype(
            np.float64
        ),
    }


def _empty() -> dict[str, np.ndarray]:
    return {field: np.zeros(0) for field in FIELDS}


def _merge(chunks: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not chunks:
        return _empty()
    return {
        field: np.concatenate([chunk[field] for chunk in chunks])
        for field in FIELDS
    }


def collect_real(
    group: str,
    speed_kmh: float,
    *,
    scene_count: int = 3,
    frames_per_scene: int = 30,
) -> dict:
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)
    chunks: list[dict[str, np.ndarray]] = []
    frames = 0
    for scene in scenes:
        paths = evenly(
            sorted((scene / "velodyne").glob("*.bin")), frames_per_scene
        )
        for path in paths:
            points = np.fromfile(path, dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(
                scene / "labels" / f"{path.stem}.label", dtype=np.uint32
            )
            spray = points[labels == 2]
            chunks.append(frame_clusters(spray) if spray.shape[0] else _empty())
            frames += 1
    data = _merge(chunks)
    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "frames": frames,
        **data,
    }


def _pool(cells: list[dict]) -> dict[str, np.ndarray]:
    return _merge([{field: cell[field] for field in FIELDS} for cell in cells])


def _bucket_masks(values: np.ndarray) -> list[np.ndarray]:
    return [(values >= lo) & (values < hi) for lo, hi in BUCKETS]


def _median_finite(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=np.float64)
    data = data[np.isfinite(data)]
    return float(np.median(data)) if data.size else float("nan")


def _share_row(label: str, data: dict[str, np.ndarray]) -> str:
    normalised = data["nn_norm"]
    overlap = overlap_frac(normalised)
    points = pts_in_overlap(normalised, data["n"])
    merged = n_merged(data["elong"])
    return (
        f"| {label} | {data['d'].size} | {_fmt(overlap * 100.0, 1)} % | "
        f"{_fmt(points * 100.0, 1)} % | "
        f"{_fmt(_median_finite(data['nn']))} | "
        f"{_fmt(_median_finite(normalised))} | "
        f"{merged} | {_fmt(merged / max(data['d'].size, 1) * 100.0, 1)} % | "
        f"{_fmt(nn_merged(data['elong'], normalised))} |"
    )


def _largest_share(data: dict[str, np.ndarray], quantile: float) -> float:
    """Share of points held by the top ``quantile`` largest clusters."""
    sizes = np.sort(np.asarray(data["n"], dtype=np.float64))[::-1]
    if sizes.size == 0 or sizes.sum() <= 0.0:
        return float("nan")
    keep = max(1, int(round(quantile * sizes.size)))
    return float(sizes[:keep].sum() / sizes.sum())


def render(cells: list[dict], pooled: dict[str, np.ndarray]) -> str:
    overlap = overlap_frac(pooled["nn_norm"])
    points = pts_in_overlap(pooled["nn_norm"], pooled["n"])
    lines: list[str] = [
        "# 29e-d-ii — các cụm DBSCAN xếp cạnh nhau (đo trên `cal`)",
        "",
        "Sinh bằng `scripts/measure_29ed2.py`. **Chỉ đo**, không sửa generator.",
        "3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; DBSCAN góc 0,7°/minPts=3 trên "
        "điểm label 2.",
        "",
        "- `nn` = khoảng cách tâm cụm → tâm cụm gần nhất **trong cùng frame** (m).",
        "- `nn_norm = nn / (r_i + r_j)`, `r` = bán kính paper (max khoảng cách "
        "điểm → tâm); `nn_norm < 1` nghĩa là hai cầu **chồng nhau**.",
        "- `overlap_frac` = tỉ lệ cụm có `nn_norm < 1`, tính trên các cụm **có ít "
        "nhất một cụm khác trong frame** (cụm lẻ không có `nn` nên không tính vào "
        "mẫu số).",
        "- `pts_in_overlap` = % **tổng điểm** nằm trong cụm có `nn_norm < 1`.",
        "- `n_merged` = số cụm có `elong > 1,5` (dấu hiệu DBSCAN đã gộp), kèm % "
        "trên tổng số cụm; `nn_merged` = trung vị `nn_norm` của các cụm đó.",
        f"- **Cửa chặn:** `overlap_frac` gộp < {OVERLAP_THRESHOLD * 100.0:g} % ⇒ "
        "giả thuyết chồng cụm sai, dừng và báo PM.",
        "",
        "## 1. Gộp và theo lớp",
        "",
        "| lớp | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.append(_share_row("gộp", pooled))
    for group in GROUPS:
        data = _pool([cell for cell in cells if cell["group"] == group])
        lines.append(_share_row(group, data))

    lines += ["", "## 2. Theo lớp × tốc độ", ""]
    lines.append(
        "| lớp | km/h | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell in cells:
        lines.append(_share_row(f"{cell['group']} | {cell['speed']:g}", cell))

    lines += ["", "## 3. Theo 4 dải cự ly", ""]
    lines.append(
        "Dải theo range của tâm cụm. `overlap_frac` tính lại trên các cụm trong dải."
    )
    lines += [
        "",
        "| lớp | dải (m) | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, data in [("gộp", pooled)] + [
        (group, _pool([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        for index, mask in enumerate(_bucket_masks(data["d"])):
            part = {field: values[mask] for field, values in data.items()}
            lines.append(_share_row(f"{label} | {_bucket_label(index)}", part))

    lines += [
        "",
        "## 4. Đối chiếu `pts_in_overlap` với mức tập trung điểm đã đo",
        "",
        "B2 của ticket: đối chiếu với con số **66 %** của 5 % cụm to nhất. Cùng dữ "
        "liệu, cùng cụm, chỉ khác cách chia nhóm.",
        "",
        "| lớp | pts_in_overlap | % điểm trong 5 % cụm to nhất | 10 % | 25 % |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, data in [("gộp", pooled)] + [
        (group, _pool([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        lines.append(
            f"| {label} | {_fmt(pts_in_overlap(data['nn_norm'], data['n']) * 100.0, 1)} % | "
            + " | ".join(
                f"{_fmt(_largest_share(data, share) * 100.0, 1)} %" for share in SHARES
            )
            + " |"
        )

    lines += [
        "",
        "## 5. `nn` theo lớp",
        "",
        "| lớp | cụm | p10 | median | p90 | mean |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, data in [("gộp", pooled)] + [
        (group, _pool([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        stats = _stats(data["nn"])
        lines.append(
            f"| {label} | {stats['n']} | {_fmt(stats['p10'])} | "
            f"{_fmt(stats['median'])} | {_fmt(stats['p90'])} | "
            f"{_fmt(stats['mean'])} |"
        )

    lines += [
        "",
        "## 6. Kết luận cửa chặn",
        "",
        f"`overlap_frac` gộp = **{_fmt(overlap * 100.0, 1)} %** "
        f"(ngưỡng {OVERLAP_THRESHOLD * 100.0:g} %). "
        + (
            "Giả thuyết chồng cụm **sống**; báo PM trước khi sửa generator."
            if np.isfinite(overlap) and overlap >= OVERLAP_THRESHOLD
            else "Giả thuyết chồng cụm **sai**; dừng, báo PM, không sửa generator."
        ),
        "",
        f"`pts_in_overlap` gộp = **{_fmt(points * 100.0, 1)} %** tổng điểm.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    cells = [
        collect_real(group, speed) for group in GROUPS for speed in SPEEDS_KMH
    ]
    pooled = _pool(cells)
    body = render(cells, pooled)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(body, encoding="utf-8")

    overlap = overlap_frac(pooled["nn_norm"])
    points = pts_in_overlap(pooled["nn_norm"], pooled["n"])
    for group in GROUPS:
        data = _pool([cell for cell in cells if cell["group"] == group])
        print(
            f"{group}: overlap_frac={overlap_frac(data['nn_norm']) * 100.0:.1f} % "
            f"pts_in_overlap={pts_in_overlap(data['nn_norm'], data['n']) * 100.0:.1f} % "
            f"n_merged={n_merged(data['elong'])}/{data['d'].size} "
            f"nn_merged={_fmt(nn_merged(data['elong'], data['nn_norm']))}"
        )
    print(f"gộp: overlap_frac={overlap * 100.0:.1f} % pts_in_overlap={points * 100.0:.1f} %")
    if np.isfinite(overlap) and overlap < OVERLAP_THRESHOLD:
        print(
            f"DUNG: overlap_frac < {OVERLAP_THRESHOLD * 100.0:g} % — "
            "giả thuyết chồng cụm sai, báo PM, không sửa generator."
        )
    print(f"Đã ghi {DOC}")


if __name__ == "__main__":
    main()
