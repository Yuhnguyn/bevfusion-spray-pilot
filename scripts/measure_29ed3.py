#!/usr/bin/env python3
"""Ticket 29e-d-iii: measure how the **generated** clusters sit next to each other.

Step 2 of the ticket: **measure only**, no generator change. The real side is
the ``cal`` measurement of ``scripts/measure_29ed2.py`` (label-2 points,
``docs/measurements/29ed2-overlap.md``). The generated side runs the same
stateful path as ``PlumeTransform`` (``inject_plume_stateful`` ->
``raycast_frame``) on the same 3 scenes x 30 frames per cell, 2 classes and 9
speeds, and computes the **same** quantities on the ray-cast detections:

- ``nn``          centroid -> nearest other centroid in the same frame (m);
- ``nn_norm``     ``nn / (r_i + r_j)``; ``< 1`` means the two spheres overlap;
- ``overlap_frac`` share of clusters (that have a neighbour) with ``nn_norm < 1``;
- ``pts_in_overlap`` share of points that live in an overlapping cluster;
- ``n_merged``    clusters with ``elong > 1.5``;
- ``nn_merged``   median ``nn_norm`` of those merged clusters.

The table (real vs generated, by class x speed, with a ``delta overlap_frac``
column) goes to ``docs/measurements/29ed3-gen-overlap.md``.

**Stop gate:** if the generated ``overlap_frac`` is already >= 40 % the
"placement region too wide" hypothesis is wrong -- stop and report to the PM.

    /opt/anaconda3/bin/python scripts/measure_29ed3.py

Only numpy + stdlib.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import numpy as np

from scripts.measure_29ed import (
    DT_S,
    GROUPS,
    ROAD_Z_M,
    SPEEDS_KMH,
    WFH_MM,
    _box_from_labels,
    _fmt,
    evenly,
    fallback_box,
    scene_distance_m,
    scenes_for,
)
from scripts.measure_29ed2 import (
    FIELDS,
    _empty,
    _merge,
    _median_finite,
    _pool,
    _share_row,
    frame_clusters,
    n_merged,
    nn_merged,
    overlap_frac,
    pts_in_overlap,
)
from spray.beam_model import load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame

DOC = Path("docs/measurements/29ed3-gen-overlap.md")
STOP_GATE = 0.40
# Real cells, copied from ``docs/measurements/29ed2-overlap.md`` (section 2).
# Kept literal so the comparison survives a re-run of the real measurement.
REAL_CELLS: dict[tuple[str, float], dict[str, float]] = {
    ("Crafter_dynamic", 50.0): {"clusters": 405, "overlap": 11.1, "pts": 9.0,
                                "nn": 0.358, "nn_norm": 2.821, "merged": 85,
                                "nn_merged": 1.479},
    ("Crafter_dynamic", 60.0): {"clusters": 877, "overlap": 50.1, "pts": 78.6,
                                "nn": 0.672, "nn_norm": 0.998, "merged": 347,
                                "nn_merged": 0.523},
    ("Crafter_dynamic", 70.0): {"clusters": 1480, "overlap": 64.0, "pts": 89.5,
                                "nn": 0.589, "nn_norm": 0.627, "merged": 730,
                                "nn_merged": 0.571},
    ("Crafter_dynamic", 80.0): {"clusters": 1456, "overlap": 65.6, "pts": 85.9,
                                "nn": 0.700, "nn_norm": 0.560, "merged": 707,
                                "nn_merged": 0.439},
    ("Crafter_dynamic", 90.0): {"clusters": 1682, "overlap": 63.3, "pts": 87.9,
                                "nn": 0.734, "nn_norm": 0.530, "merged": 798,
                                "nn_merged": 0.400},
    ("Crafter_dynamic", 100.0): {"clusters": 1961, "overlap": 64.7, "pts": 89.5,
                                 "nn": 0.656, "nn_norm": 0.545, "merged": 957,
                                 "nn_merged": 0.497},
    ("Crafter_dynamic", 110.0): {"clusters": 1646, "overlap": 69.9, "pts": 91.6,
                                 "nn": 0.659, "nn_norm": 0.462, "merged": 743,
                                 "nn_merged": 0.445},
    ("Crafter_dynamic", 120.0): {"clusters": 1414, "overlap": 65.1, "pts": 83.8,
                                 "nn": 0.719, "nn_norm": 0.549, "merged": 638,
                                 "nn_merged": 0.462},
    ("Crafter_dynamic", 130.0): {"clusters": 1351, "overlap": 63.1, "pts": 81.1,
                                 "nn": 0.674, "nn_norm": 0.565, "merged": 571,
                                 "nn_merged": 0.439},
    ("Golf_dynamic", 50.0): {"clusters": 314, "overlap": 44.3, "pts": 54.3,
                             "nn": 0.889, "nn_norm": 1.204, "merged": 146,
                             "nn_merged": 0.808},
    ("Golf_dynamic", 60.0): {"clusters": 710, "overlap": 58.4, "pts": 73.3,
                             "nn": 0.638, "nn_norm": 0.645, "merged": 349,
                             "nn_merged": 0.514},
    ("Golf_dynamic", 70.0): {"clusters": 956, "overlap": 63.6, "pts": 88.9,
                             "nn": 0.692, "nn_norm": 0.537, "merged": 478,
                             "nn_merged": 0.428},
    ("Golf_dynamic", 80.0): {"clusters": 1141, "overlap": 64.2, "pts": 89.5,
                             "nn": 0.648, "nn_norm": 0.538, "merged": 578,
                             "nn_merged": 0.373},
    ("Golf_dynamic", 90.0): {"clusters": 1053, "overlap": 63.1, "pts": 87.7,
                             "nn": 0.728, "nn_norm": 0.518, "merged": 506,
                             "nn_merged": 0.422},
    ("Golf_dynamic", 100.0): {"clusters": 1313, "overlap": 65.5, "pts": 92.0,
                              "nn": 0.667, "nn_norm": 0.452, "merged": 623,
                              "nn_merged": 0.361},
    ("Golf_dynamic", 110.0): {"clusters": 1325, "overlap": 65.9, "pts": 93.0,
                              "nn": 0.758, "nn_norm": 0.467, "merged": 616,
                              "nn_merged": 0.368},
    ("Golf_dynamic", 120.0): {"clusters": 1189, "overlap": 67.5, "pts": 91.4,
                              "nn": 0.783, "nn_norm": 0.462, "merged": 550,
                              "nn_merged": 0.354},
    ("Golf_dynamic", 130.0): {"clusters": 1350, "overlap": 61.3, "pts": 92.0,
                              "nn": 0.686, "nn_norm": 0.605, "merged": 607,
                              "nn_merged": 0.449},
}
# Pooled real row (same document, section 1).
REAL_POOLED = {"clusters": 21623, "overlap": 62.7, "pts": 87.8, "nn": 0.684,
               "nn_norm": 0.576, "merged": 10029, "nn_merged": 0.447}


def collect_generated(
    group: str,
    speed_kmh: float,
    *,
    scene_count: int = 3,
    frames_per_scene: int = 30,
) -> dict:
    """Overlap quantities on the ray-cast detections of one cell."""
    vehicle_class, dims = GROUPS[group]
    speed_mps = speed_kmh / 3.6
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)
    state = PlumeState()
    table = load_beam_table()
    config = PlumeConfig()
    chunks: list[dict[str, np.ndarray]] = []
    frames = 0
    capped = 0
    for scene in scenes:
        paths = evenly(
            sorted((scene / "velodyne").glob("*.bin")), frames_per_scene
        )
        for frame_index, path in enumerate(paths):
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
                )
            capped = max(capped, int(result.stats.capped))
            detections = np.asarray(ray.detections, dtype=np.float32)
            chunks.append(
                frame_clusters(detections) if detections.shape[0] else _empty()
            )
            frames += 1
    data = _merge(chunks)
    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "frames": frames,
        "capped": capped,
        **data,
    }


def _gen_share(cell: dict) -> dict[str, float]:
    normalised = cell["nn_norm"]
    return {
        "clusters": float(cell["d"].size),
        "overlap": overlap_frac(normalised) * 100.0,
        "pts": pts_in_overlap(normalised, cell["n"]) * 100.0,
        "nn": _median_finite(cell["nn"]),
        "nn_norm": _median_finite(normalised),
        "merged": float(n_merged(cell["elong"])),
        "nn_merged": nn_merged(cell["elong"], normalised),
    }


def _delta(gen: dict[str, float], real: dict[str, float]) -> float:
    return gen["overlap"] - real["overlap"]


def render(cells: list[dict], pooled: dict[str, np.ndarray]) -> str:
    gen_pooled = _gen_share({"d": pooled["d"], **pooled})
    lines: list[str] = [
        "# 29e-d-iii — các cụm **generator** xếp cạnh nhau (đo trên `cal`)",
        "",
        "Sinh bằng `scripts/measure_29ed3.py`. **Chỉ đo**, không sửa generator.",
        "3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful "
        "`inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`), "
        "đại lượng tính trên **detection sinh ra**.",
        "",
        "- `nn` = khoảng cách tâm cụm → tâm cụm gần nhất **trong cùng frame** (m).",
        "- `nn_norm = nn / (r_i + r_j)`, `r` = max khoảng cách điểm → tâm; "
        "`nn_norm < 1` nghĩa là hai cầu **chồng nhau**.",
        "- `overlap_frac` = tỉ lệ cụm có `nn_norm < 1`, trên các cụm **có ít nhất "
        "một cụm khác trong frame**.",
        "- `pts_in_overlap` = % **tổng điểm** nằm trong cụm có `nn_norm < 1`.",
        "- `n_merged` = số cụm có `elong > 1,5`; `nn_merged` = trung vị `nn_norm` "
        "của các cụm đó.",
        "- `Δ overlap_frac` = gen − real (điểm %).",
        f"- **Cửa chặn:** `overlap_frac` gen ≥ {STOP_GATE * 100.0:g} % ⇒ giả thuyết "
        "“vùng đặt quá rộng” sai ⇒ dừng, báo PM, không sửa gì thêm.",
        "",
        "## 1. Gộp",
        "",
        "| nguồn | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | nn_merged |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| real | {REAL_POOLED['clusters']} | {REAL_POOLED['overlap']:.1f} % | "
        f"{REAL_POOLED['pts']:.1f} % | {REAL_POOLED['nn']:.3f} | "
        f"{REAL_POOLED['nn_norm']:.3f} | {REAL_POOLED['merged']} | "
        f"{REAL_POOLED['nn_merged']:.3f} |",
        f"| gen | {gen_pooled['clusters']:.0f} | {_fmt(gen_pooled['overlap'], 1)} % | "
        f"{_fmt(gen_pooled['pts'], 1)} % | {_fmt(gen_pooled['nn'])} | "
        f"{_fmt(gen_pooled['nn_norm'])} | {gen_pooled['merged']:.0f} | "
        f"{_fmt(gen_pooled['nn_merged'])} |",
        f"| Δ | | {_fmt(_delta(gen_pooled, REAL_POOLED), 1)} | "
        f"{_fmt(gen_pooled['pts'] - REAL_POOLED['pts'], 1)} | | | | |",
        "",
        "## 2. Theo lớp × tốc độ — real vs gen",
        "",
        "| lớp | km/h | cụm real | cụm gen | overlap real | overlap gen | "
        "Δ overlap_frac | pts real | pts gen | median nn real (m) | median nn gen (m) | "
        "median nn_norm real | median nn_norm gen | n_merged real | n_merged gen | "
        "nn_merged real | nn_merged gen |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        real = REAL_CELLS[(cell["group"], cell["speed"])]
        gen = _gen_share(cell)
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {real['clusters']} | "
            f"{gen['clusters']:.0f} | {real['overlap']:.1f} % | "
            f"{_fmt(gen['overlap'], 1)} % | "
            f"{_fmt(_delta(gen, real), 1)} | {real['pts']:.1f} % | "
            f"{_fmt(gen['pts'], 1)} % | {real['nn']:.3f} | {_fmt(gen['nn'])} | "
            f"{real['nn_norm']:.3f} | {_fmt(gen['nn_norm'])} | "
            f"{real['merged']} | {gen['merged']:.0f} | "
            f"{real['nn_merged']:.3f} | {_fmt(gen['nn_merged'])} |"
        )

    lines += [
        "",
        "## 3. Gen theo lớp (gộp 9 tốc độ) — đối chiếu §1 của `29ed2-overlap.md`",
        "",
        "| lớp | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in GROUPS:
        data = _pool([cell for cell in cells if cell["group"] == group])
        lines.append(_share_row(group, data))

    lines += [
        "",
        "## 4. `capped` và độ phủ",
        "",
        "| lớp | km/h | frame | capped |",
        "|---|---:|---:|---:|",
    ]
    for cell in cells:
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {cell['frames']} | "
            f"{cell['capped']} |"
        )

    high = [
        cell
        for cell in cells
        if _gen_share(cell)["overlap"] >= STOP_GATE * 100.0
    ]
    lines += [
        "",
        "## 5. Kết luận cửa chặn",
        "",
        f"`overlap_frac` gen gộp = **{_fmt(gen_pooled['overlap'], 1)} %**.",
        "",
    ]
    if high:
        lines.append(
            f"**DỪNG:** {len(high)}/18 ô đã ≥ {STOP_GATE * 100.0:g} % "
            f"({', '.join('{}@{:g}'.format(c['group'], c['speed']) for c in high)}). "
            "Giả thuyết “vùng đặt quá rộng” **sai**; báo PM, không sửa gì thêm."
        )
    else:
        lines.append(
            f"Không ô nào ≥ {STOP_GATE * 100.0:g} %. So sánh Δ theo ô ở §2 để "
            "quyết định có thu hẹp vùng đặt hay không."
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    cells = [
        collect_generated(group, speed) for group in GROUPS for speed in SPEEDS_KMH
    ]
    pooled = _pool(cells)
    body = render(cells, pooled)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(body, encoding="utf-8")

    for cell in cells:
        gen = _gen_share(cell)
        real = REAL_CELLS[(cell["group"], cell["speed"])]
        print(
            f"{cell['group']} @{cell['speed']:g}: "
            f"overlap gen={gen['overlap']:.1f} % real={real['overlap']:.1f} % "
            f"Δ={_delta(gen, real):+.1f} pts gen={gen['pts']:.1f} % "
            f"clusters gen={gen['clusters']:.0f} real={real['clusters']}"
        )
    gen_pooled = _gen_share(pooled)
    print(
        f"gộp: overlap gen={gen_pooled['overlap']:.1f} % "
        f"real={REAL_POOLED['overlap']:.1f} % "
        f"pts gen={gen_pooled['pts']:.1f} % real={REAL_POOLED['pts']:.1f} %"
    )
    high = [cell for cell in cells if _gen_share(cell)["overlap"] >= STOP_GATE * 100.0]
    if high:
        print(
            f"DUNG: {len(high)}/18 ô có overlap_frac >= {STOP_GATE * 100.0:g} % — "
            "giả thuyết vùng đặt quá rộng sai, báo PM, không sửa generator."
        )
    print(f"Đã ghi {DOC}")


if __name__ == "__main__":
    main()
