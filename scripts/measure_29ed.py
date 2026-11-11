#!/usr/bin/env python3
"""Ticket 29e-d: measure the paper's ``r_cl`` and ``P_det`` on the real ``cal``.

Step 1 of the ticket: **measure only**, no generator change. For every real
cluster (DBSCAN in the discretised azimuth/elevation plane, ``eps = 0.7 deg``,
``minPts = 3``) on the label-2 points of ``cal``:

- ``d``     range of the cluster centroid;
- ``n``     number of points in the cluster;
- ``r_cl``  **max** distance from a point to the centre (paper definition);
- ``n_max`` beams intersecting a sphere of radius ``r_cl`` at ``d``, from the
  per-beam solid angle ``omega_tia_sr`` of ``spray/beam_model.py``;
- ``P_det`` ``n / n_max``;
- ``elong`` extent along the range direction over ``r_cl`` (ticket 29d gate G4).

The tables (overall, by class, by speed, by the four range buckets) and the
lognormal fits go to ``docs/measurements/29ed-real-distributions.md``.

    /opt/anaconda3/bin/python scripts/measure_29ed.py
    /opt/anaconda3/bin/python scripts/measure_29ed.py --generated  # A11

Only numpy + stdlib (scipy is used for the fit when present).
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
from pathlib import Path

import numpy as np
import yaml

from spray.beam_model import beams_intersecting_sphere, load_beam_table, omega_tia_sr
from spray.plume import (
    PlumeConfig,
    inject_plume_stateful,
)
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.semantic_stats import cluster_angular

DATASET = Path("data/SemanticSprayDataset")
DOC = Path("docs/measurements/29ed-real-distributions.md")
SPLIT = Path("spray/config/semantic_spray_split.yaml")
ROAD_Z_M = -0.411
WFH_MM = 1.0
DT_S = 0.1
SPEEDS_KMH = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)
GROUPS = {
    "Crafter_dynamic": ("crafter", (6.8268, 2.4183, 2.6206)),
    "Golf_dynamic": ("golf", (4.2468, 2.0167, 1.4981)),
}
BUCKETS = ((0.0, 15.0), (15.0, 25.0), (25.0, 40.0), (40.0, np.inf))
PAPER_RADIUS = (-1.2, 0.8, 0.30)
PAPER_PDET = (-2.3, 1.09, 0.18)
PAPER_ELONG = 1.48
PAPER_NEAR_CLUSTERS = 20.4
FIELDS = ("d", "n", "r_cl", "n_max", "p_det", "elong")


def cal_scenes() -> set[str]:
    """Scene rel paths in the frozen ``cal`` role (ticket 29d)."""
    document = yaml.safe_load(SPLIT.read_text(encoding="utf-8"))
    return {
        str(rel_path)
        for cell in document.get("cells") or []
        for rel_path in ((cell.get("scenes") or {}).get("cal") or [])
    }


def scenes_for(group: str, speed_kmh: float) -> list[Path]:
    measured_on = cal_scenes()
    found: list[Path] = []
    for metadata in sorted((DATASET / group).glob("*/metadata.txt")):
        with metadata.open() as handle:
            rows = list(csv.DictReader(handle))
        if not rows or abs(float(rows[0]["object_velocity"]) - speed_kmh) > 1e-6:
            continue
        rel = metadata.parent.relative_to(DATASET).as_posix()
        if rel not in measured_on:
            continue
        found.append(metadata.parent)
    return found


def evenly(items: list, count: int) -> list:
    if count <= 0 or count >= len(items):
        return list(items)
    picks = np.linspace(0, len(items) - 1, count).round().astype(int)
    return [items[index] for index in sorted(set(picks.tolist()))]


def frame_clusters(points: np.ndarray, omega_sr: float) -> dict[str, np.ndarray]:
    """Paper quantities for every cluster in one frame."""
    labels = cluster_angular(points)
    ranges = np.linalg.norm(points[:, :3].astype(np.float64), axis=1)
    collected: dict[str, list[float]] = {field: [] for field in FIELDS}
    for cluster_id in np.unique(labels):
        if cluster_id < 0:
            continue
        mask = labels == cluster_id
        members = points[mask][:, :3].astype(np.float64)
        count = int(members.shape[0])
        centre = members.mean(axis=0)
        distance = float(np.linalg.norm(centre))
        reach = float(np.max(np.linalg.norm(members - centre, axis=1)))
        if distance <= 0.0:
            n_max = 4.0 * np.pi / omega_sr
        else:
            n_max = beams_intersecting_sphere(reach, distance, omega_sr)
        member_ranges = ranges[mask]
        span = float(member_ranges.max() - member_ranges.min())
        collected["d"].append(distance)
        collected["n"].append(count)
        collected["r_cl"].append(reach)
        collected["n_max"].append(n_max)
        collected["p_det"].append(count / n_max if n_max > 0.0 else np.inf)
        collected["elong"].append(span / reach if reach > 0.0 else np.nan)
    return {
        field: np.asarray(values, dtype=np.float64)
        for field, values in collected.items()
    }


def _empty() -> dict[str, np.ndarray]:
    return {field: np.zeros(0, dtype=np.float64) for field in FIELDS}


def _stack(chunks: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not chunks:
        return _empty()
    return {
        field: np.concatenate([chunk[field] for chunk in chunks])
        for field in FIELDS
    }


def _box_from_labels(scene: Path, frame_stem: str, speed_mps: float):
    path = scene / "object_labels" / "lidar" / f"{frame_stem}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    instances = payload[0]["instances"]
    if not instances:
        return None
    contour = instances[0]["contour"]
    center = contour["center3D"]
    size = contour["size3D"]
    return np.array(
        [
            [
                float(center["x"]),
                float(center["y"]),
                float(center["z"]),
                float(size["y"]),
                float(size["x"]),
                float(size["z"]),
                float(contour["rotation3D"]["z"]),
                speed_mps,
                0.0,
            ]
        ],
        dtype=np.float32,
    )


def scene_distance_m(scene: Path) -> float:
    with (scene / "metadata.txt").open() as handle:
        rows = list(csv.DictReader(handle))
    return float(rows[0]["distance_to_object"])


def fallback_box(
    dims: tuple[float, float, float], speed_mps: float, distance_m: float
) -> np.ndarray:
    width, length, height = dims[1], dims[0], dims[2]
    return np.array(
        [
            [
                distance_m,
                0.0,
                ROAD_Z_M + height / 2.0,
                width,
                length,
                height,
                0.0,
                speed_mps,
                0.0,
            ]
        ],
        dtype=np.float32,
    )


def collect_real(
    group: str, speed_kmh: float, omega_sr: float, *, scene_count: int = 3,
    frames_per_scene: int = 30,
) -> dict:
    speed_mps = speed_kmh / 3.6
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)
    chunks: list[dict[str, np.ndarray]] = []
    near_per_frame: list[int] = []
    for scene in scenes:
        frames = evenly(sorted((scene / "velodyne").glob("*.bin")), frames_per_scene)
        for path in frames:
            points = np.fromfile(path, dtype=np.float32).reshape(-1, 5)
            labels = np.fromfile(scene / "labels" / f"{path.stem}.label", dtype=np.uint32)
            spray = points[labels == 2]
            measured = (
                frame_clusters(spray, omega_sr) if spray.shape[0] else _empty()
            )
            chunks.append(measured)
            near_per_frame.append(int((measured["d"] < 15.0).sum()))
    data = _stack(chunks)
    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "frames": len(near_per_frame),
        "near_per_frame": np.asarray(near_per_frame, dtype=np.float64),
        **data,
    }


def collect_generated(
    group: str, speed_kmh: float, omega_sr: float, *, scene_count: int = 3,
    frames_per_scene: int = 30,
) -> dict:
    """Same quantities on the ray-cast detections (A11)."""
    vehicle_class, dims = GROUPS[group]
    speed_mps = speed_kmh / 3.6
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)
    state = PlumeState()
    table = load_beam_table()
    config = PlumeConfig()
    chunks: list[dict[str, np.ndarray]] = []
    near_per_frame: list[int] = []
    for scene in scenes:
        frames = evenly(sorted((scene / "velodyne").glob("*.bin")), frames_per_scene)
        for frame_index, path in enumerate(frames):
            points = np.fromfile(path, dtype=np.float32).reshape(-1, 5)
            box = _box_from_labels(scene, path.stem, speed_mps)
            if box is None:
                box = fallback_box(dims, speed_mps, scene_distance_m(scene))
            context = PlumeContext(
                scene_token=f"{group}/{speed_kmh:g}/{scene.name}",
                frame_index=frame_index,
                epoch=0,
                sensor_origin=np.zeros(3, dtype=np.float64),
                ego_speed_mps=speed_mps,
                object_speed_mps=speed_mps,
                wfh_mm=WFH_MM,
                road_z_m=ROAD_Z_M,
                object_velocity_ego_mps=np.zeros(3, dtype=np.float64),
            )
            seed = seed_for(context.scene_token, frame_index, 0, 0)
            with contextlib.redirect_stdout(io.StringIO()):
                result = inject_plume_stateful(
                    points,
                    box,
                    context,
                    state,
                    seed=seed,
                    token=context.scene_token,
                    config=config,
                    dt=DT_S,
                    vehicle_class=vehicle_class,
                )
                ray = raycast_frame(
                    result.points_clean,
                    state.all_alive(),
                    table=table,
                    road_z_m=ROAD_Z_M,
                    rng=np.random.default_rng(seed),
                    capped=result.stats.capped,
                    vehicle_class=vehicle_class,
                )
            detections = np.asarray(ray.detections, dtype=np.float32)
            measured = (
                frame_clusters(detections, omega_sr)
                if detections.shape[0]
                else _empty()
            )
            chunks.append(measured)
            near_per_frame.append(int((measured["d"] < 15.0).sum()))
    data = _stack(chunks)
    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "frames": len(near_per_frame),
        "near_per_frame": np.asarray(near_per_frame, dtype=np.float64),
        **data,
    }


def fit_lognormal(values: np.ndarray) -> tuple[float, float]:
    """MLE of a lognormal ``(mu, sigma)``; scipy when available."""
    data = np.asarray(values, dtype=np.float64)
    data = data[np.isfinite(data) & (data > 0.0)]
    if data.size == 0:
        return float("nan"), float("nan")
    try:
        from scipy.stats import lognorm

        sigma, _, scale = lognorm.fit(data, floc=0.0)
        return float(np.log(scale)), float(sigma)
    except Exception:  # noqa: BLE001 - scipy optional
        logged = np.log(data)
        return float(logged.mean()), float(logged.std(ddof=0))


def _stats(values: np.ndarray, quantiles=(50.0, 90.0, 99.0)) -> dict:
    data = np.asarray(values, dtype=np.float64)
    data = data[np.isfinite(data)]
    out = {"n": int(data.size), "mean": float("nan"), "median": float("nan")}
    for q in {10.0, 50.0, 90.0, 99.0} | set(quantiles):
        out[f"p{q:g}"] = float("nan")
    if data.size == 0:
        return out
    out.update(
        {"mean": float(data.mean()), "median": float(np.median(data))}
    )
    for q in quantiles:
        out[f"p{q:g}"] = float(np.percentile(data, q))
    return out


def _fit_row(values: np.ndarray) -> dict:
    stats = _stats(values)
    mu, sigma = fit_lognormal(values)
    stats["mu"] = mu
    stats["sigma"] = sigma
    stats["fit_median"] = float(np.exp(mu)) if np.isfinite(mu) else float("nan")
    stats["fit_mean"] = (
        float(np.exp(mu + 0.5 * sigma * sigma)) if np.isfinite(mu) else float("nan")
    )
    return stats


def _bucket_masks(values: np.ndarray) -> list[np.ndarray]:
    return [
        (values >= lo) & (values < hi) for lo, hi in BUCKETS
    ]


def _bucket_label(index: int) -> str:
    lo, hi = BUCKETS[index]
    return f"[{lo:g},{hi:g})" if np.isfinite(hi) else f"[{lo:g}+"


def _fmt(value: float, digits: int = 3) -> str:
    return "nan" if not np.isfinite(value) else f"{value:.{digits}f}"


def render(cells: list[dict], omega_sr: float, generated: list[dict] | None) -> str:
    lines: list[str] = [
        "# 29e-d — đo `r_cl` và `P_det` trên `cal` theo định nghĩa paper",
        "",
        "Sinh bằng `scripts/measure_29ed.py`. **Chỉ đo**, không sửa generator.",
        f"3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; DBSCAN góc 0,7°/minPts=3, "
        "real = điểm label 2, `wfh_ref = 1 mm`.",
        "",
        f"- `Ω_tia` = `Δaz × Δel` = **{omega_sr:.6e} sr** "
        "(ticket 29e-d ghi 2,003e−5; chênh < 0,1 % do làm tròn góc).",
        "- `d` = range của tâm cụm (centroid điểm); "
        "`r_cl` = **max** khoảng cách điểm → tâm, đúng định nghĩa paper.",
        "- `n_max` = `Ω_cầu(r_cl, d) / Ω_tia`; `P_det = n / n_max`.",
        "- `elong` = `(range max − range min) / r_cl` (G4 của 29d = 1,480).",
        "",
    ]

    all_data = _stack(cells)
    lines += ["## 1. `r_cl`", "", "### Gộp và theo lớp", ""]
    lines.append(
        "| lớp | cụm | median | mean | p90 | p99 | fit µ | fit σ | fit median | paper (−1,2; 0,8; 0,30 m) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for label, data in [("gộp", all_data)] + [
        (group, _stack([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        stats = _fit_row(data["r_cl"])
        lines.append(
            f"| {label} | {stats['n']} | {_fmt(stats['median'])} | "
            f"{_fmt(stats['mean'])} | {_fmt(stats['p90'])} | {_fmt(stats['p99'])} | "
            f"{_fmt(stats['mu'])} | {_fmt(stats['sigma'])} | "
            f"{_fmt(stats['fit_median'])} | −1,2; 0,8; 0,30 |"
        )

    lines += ["", "### Theo lớp × tốc độ", ""]
    lines.append(
        "| lớp | km/h | cụm | median | mean | p90 | p99 | fit µ | fit σ | fit median |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell in cells:
        stats = _fit_row(cell["r_cl"])
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {stats['n']} | "
            f"{_fmt(stats['median'])} | {_fmt(stats['mean'])} | "
            f"{_fmt(stats['p90'])} | {_fmt(stats['p99'])} | "
            f"{_fmt(stats['mu'])} | {_fmt(stats['sigma'])} | "
            f"{_fmt(stats['fit_median'])} |"
        )

    lines += ["", "### Theo lớp × dải cự ly", ""]
    lines.append(
        "| lớp | dải (m) | cụm | median | mean | p90 | p99 | fit µ | fit σ |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for group in GROUPS:
        data = _stack([cell for cell in cells if cell["group"] == group])
        for index, mask in enumerate(_bucket_masks(data["d"])):
            part = data["r_cl"][mask]
            stats = _fit_row(part)
            lines.append(
                f"| {group} | {_bucket_label(index)} | {stats['n']} | "
                f"{_fmt(stats['median'])} | {_fmt(stats['mean'])} | "
                f"{_fmt(stats['p90'])} | {_fmt(stats['p99'])} | "
                f"{_fmt(stats['mu'])} | {_fmt(stats['sigma'])} |"
            )

    lines += ["", "## 2. `P_det`", ""]
    above = float(np.mean(all_data["p_det"] > 1.0)) * 100.0
    lines += [
        f"**Tỉ lệ `P_det > 1` = {above:.2f} % số cụm** "
        "(ngưỡng dừng của ticket: > 5 %).",
        "",
        "### Gộp và theo lớp",
        "",
    ]
    lines.append(
        "| lớp | cụm | median | mean | p10 | p90 | fit µ | fit σ | fit mean | paper (−2,3; 1,09; 0,18) |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for label, data in [("gộp", all_data)] + [
        (group, _stack([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        stats = _fit_row(data["p_det"])
        lines.append(
            f"| {label} | {stats['n']} | {_fmt(stats['median'])} | "
            f"{_fmt(stats['mean'])} | {_fmt(stats.get('p10', float('nan')))} | "
            f"{_fmt(stats['p90'])} | {_fmt(stats['mu'])} | {_fmt(stats['sigma'])} | "
            f"{_fmt(stats['fit_mean'])} | −2,3; 1,09; 0,18 |"
        )

    lines += ["", "### Theo lớp × tốc độ", ""]
    lines.append(
        "| lớp | km/h | cụm | median | mean | p10 | p90 | fit µ | fit σ | fit mean | P_det>1 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell in cells:
        stats = _fit_row(cell["p_det"])
        share = float(np.mean(cell["p_det"] > 1.0)) * 100.0
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {stats['n']} | "
            f"{_fmt(stats['median'])} | {_fmt(stats['mean'])} | "
            f"{_fmt(stats.get('p10', float('nan')))} | {_fmt(stats['p90'])} | "
            f"{_fmt(stats['mu'])} | {_fmt(stats['sigma'])} | "
            f"{_fmt(stats['fit_mean'])} | {share:.1f} % |"
        )

    lines += ["", "### Theo lớp × dải cự ly", ""]
    lines.append(
        "| lớp | dải (m) | cụm | median | mean | p10 | p90 | fit µ | fit σ | P_det>1 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for group in GROUPS:
        data = _stack([cell for cell in cells if cell["group"] == group])
        for index, mask in enumerate(_bucket_masks(data["d"])):
            part = data["p_det"][mask]
            stats = _fit_row(part)
            share = float(np.mean(part > 1.0)) * 100.0 if part.size else float("nan")
            lines.append(
                f"| {group} | {_bucket_label(index)} | {stats['n']} | "
                f"{_fmt(stats['median'])} | {_fmt(stats['mean'])} | "
                f"{_fmt(stats.get('p10', float('nan')))} | {_fmt(stats['p90'])} | "
                f"{_fmt(stats['mu'])} | {_fmt(stats['sigma'])} | {share:.1f} % |"
            )

    lines += ["", "## 3. `elong`", ""]
    lines.append("| lớp | cụm | median | p10 | p90 | G4 29d |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for label, data in [("gộp", all_data)] + [
        (group, _stack([cell for cell in cells if cell["group"] == group]))
        for group in GROUPS
    ]:
        stats = _stats(data["elong"], quantiles=(10.0, 90.0))
        lines.append(
            f"| {label} | {stats['n']} | {_fmt(stats['median'])} | "
            f"{_fmt(stats.get('p10', float('nan')))} | "
            f"{_fmt(stats.get('p90', float('nan')))} | 1,480 |"
        )

    lines += ["", "### `elong` theo lớp × dải cự ly", ""]
    lines.append("| lớp | dải (m) | cụm | median |")
    lines.append("|---|---|---:|---:|")
    for group in GROUPS:
        data = _stack([cell for cell in cells if cell["group"] == group])
        for index, mask in enumerate(_bucket_masks(data["d"])):
            part = data["elong"][mask]
            part = part[np.isfinite(part)]
            lines.append(
                f"| {group} | {_bucket_label(index)} | {part.size} | "
                f"{_fmt(float(np.median(part)) if part.size else float('nan'))} |"
            )

    lines += ["", "## 4. Cụm/frame ở dải gần (< 15 m)", ""]
    lines.append(
        "`d` của tâm cụm < 15 m; trung bình theo frame. Đối chiếu ticket 29e-c: "
        f"Crafter@100 = {PAPER_NEAR_CLUSTERS:g}."
    )
    lines.append("")
    lines.append("| lớp | km/h | scene | frame | cụm/frame <15 m |")
    lines.append("|---|---:|---:|---:|---:|")
    for cell in cells:
        mean = float(np.mean(cell["near_per_frame"]))
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {len(cell['scenes'])} | "
            f"{cell['frames']} | {mean:.2f} |"
        )

    if generated is not None:
        lines += ["", "## 5. A11 — fit trên dữ liệu sinh ra so với `cal`", ""]
        lines.append(
            "Cùng recipe đo trên detection ray-cast của đường stateful đã nối. "
            "Ngưỡng A11: lệch ≤ 25 % ở median và mean của fit."
        )
        lines.append("")
        lines.append(
            "| lớp | đại lượng | cal fit µ | gen fit µ | cal median | gen median | Δmedian | cal mean | gen mean | Δmean |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for group in GROUPS:
            real = _stack([cell for cell in cells if cell["group"] == group])
            gen = _stack([cell for cell in generated if cell["group"] == group])
            for field in ("r_cl", "p_det"):
                r = _fit_row(real[field])
                g = _fit_row(gen[field])
                lines.append(
                    f"| {group} | `{field}` | {_fmt(r['mu'])} | {_fmt(g['mu'])} | "
                    f"{_fmt(r['fit_median'])} | {_fmt(g['fit_median'])} | "
                    f"{_pct(g['fit_median'], r['fit_median'])} | "
                    f"{_fmt(r['fit_mean'])} | {_fmt(g['fit_mean'])} | "
                    f"{_pct(g['fit_mean'], r['fit_mean'])} |"
                )
    return "\n".join(lines)


def _pct(value: float, reference: float) -> str:
    if not np.isfinite(value) or not np.isfinite(reference) or reference == 0.0:
        return "nan"
    return f"{(value - reference) / reference * 100.0:+.1f} %"


def _print_summary(cells: list[dict], omega_sr: float, generated: list[dict] | None) -> None:
    all_data = _stack(cells)
    for group in GROUPS:
        data = _stack([cell for cell in cells if cell["group"] == group])
        radius = _fit_row(data["r_cl"])
        p_det = _fit_row(data["p_det"])
        share = float(np.mean(data["p_det"] > 1.0)) * 100.0
        print(
            f"{group}: r_cl mu={radius['mu']:.3f} sigma={radius['sigma']:.3f} "
            f"median={radius['fit_median']:.3f} m | "
            f"P_det mu={p_det['mu']:.3f} sigma={p_det['sigma']:.3f} "
            f"mean={p_det['fit_mean']:.3f} | P_det>1 {share:.2f} %"
        )
    share_all = float(np.mean(all_data["p_det"] > 1.0)) * 100.0
    print(f"omega_tia = {omega_sr:.6e} sr | P_det>1 (gộp) = {share_all:.2f} %")
    if generated is not None:
        for group in GROUPS:
            real = _stack([cell for cell in cells if cell["group"] == group])
            gen = _stack([cell for cell in generated if cell["group"] == group])
            for field in ("r_cl", "p_det"):
                r = _fit_row(real[field])
                g = _fit_row(gen[field])
                print(
                    f"A11 {group} {field}: median {r['fit_median']:.3f} -> "
                    f"{g['fit_median']:.3f} ({_pct(g['fit_median'], r['fit_median'])}), "
                    f"mean {r['fit_mean']:.3f} -> {g['fit_mean']:.3f} "
                    f"({_pct(g['fit_mean'], r['fit_mean'])})"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generated",
        action="store_true",
        help="also measure the ray-cast detections and print A11",
    )
    args = parser.parse_args()

    table = load_beam_table()
    omega_sr = omega_tia_sr(table)
    cells = [
        collect_real(group, speed, omega_sr) for group in GROUPS for speed in SPEEDS_KMH
    ]
    generated = (
        [
            collect_generated(group, speed, omega_sr)
            for group in GROUPS
            for speed in SPEEDS_KMH
        ]
        if args.generated
        else None
    )
    body = render(cells, omega_sr, generated)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(body, encoding="utf-8")
    _print_summary(cells, omega_sr, generated)
    print(f"Đã ghi {DOC}")


if __name__ == "__main__":
    main()
