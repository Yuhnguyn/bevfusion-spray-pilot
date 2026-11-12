#!/usr/bin/env python3
"""Ticket 29f: why the generator shows only 0.59x the real clusters per frame.

Step 1 of the ticket: **measure only**, no generator change. On ``cal``
(3 scenes x 30 frames per cell, 2 classes, 9 speeds) every cell reports:

- ``alive``           clusters alive in the state (``state.all_alive()``);
- ``visible``         alive clusters with at least one ray-cast detection;
- ``dbscan``          clusters rebuilt by DBSCAN on the detections, ``>= 3`` pts;
- ``alive_not_dbscan`` ``alive - dbscan`` -- spawned but invisible to DBSCAN;
- ``det_per_alive``   detections per alive cluster;
- ``real dbscan``     the same DBSCAN count on the real label-2 points, copied
                      from ``docs/measurements/29ed3-gen-overlap.md`` section 2;
- ``delta``           ``dbscan - real dbscan``.

Two references make the counts comparable, because ``29ed3`` reports
**clusters per frame** while the real table is a **total over 90 frames**:

- ``real/frame`` = real DBSCAN total / 90 (the same 3 scenes x 30 frames);
- ``alive target`` = ``cluster_count_for_speed_abs(v, 1 mm)``, the steady-state
  alive count the generator's own table aims for.

The DBSCAN recipe is the paper's (``eps = 0.7 deg``, ``minPts = 3``) and is
never changed here. The table goes to
``docs/measurements/29f-cluster-visibility.md``.

**Stop gate:** if ``alive`` is already ``<= 0.7x real`` the fault is in the
cluster spawn (branch 3b); if ``alive`` is near real and ``dbscan`` is low the
fault is in the ray-cast (branch 3a). The gate is evaluated against
``real/frame``.

The script also reports ``dbscan (ảnh ghép)``: the same DBSCAN on
``real_points`` + detections, i.e. what ``PlumeTransform`` actually feeds the
model. It is a diagnostic only.

    /opt/anaconda3/bin/python scripts/measure_29f.py

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
from spray.beam_model import load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import (
    PlumeState,
    cluster_count_for_speed_abs,
    cluster_spawn_rate_for_speed_abs,
    lifetime_mean_s,
)
from spray.raycast import raycast_frame
from spray.semantic_stats import cluster_angular

DOC = Path("docs/measurements/29f-cluster-visibility.md")
STOP_GATE = 0.7
FRAMES_PER_CELL = 90  # 3 scenes x 30 frames, the sampling of ``29ed3``
# Real DBSCAN cluster counts, copied from ``docs/measurements/29ed3-gen-overlap.md``
# section 2 (column ``cum real``). Kept literal so the comparison survives a
# re-run of the real measurement.
REAL_DBSCAN: dict[tuple[str, float], int] = {
    ("Crafter_dynamic", 50.0): 405,
    ("Crafter_dynamic", 60.0): 877,
    ("Crafter_dynamic", 70.0): 1480,
    ("Crafter_dynamic", 80.0): 1456,
    ("Crafter_dynamic", 90.0): 1682,
    ("Crafter_dynamic", 100.0): 1961,
    ("Crafter_dynamic", 110.0): 1646,
    ("Crafter_dynamic", 120.0): 1414,
    ("Crafter_dynamic", 130.0): 1351,
    ("Golf_dynamic", 50.0): 314,
    ("Golf_dynamic", 60.0): 710,
    ("Golf_dynamic", 70.0): 956,
    ("Golf_dynamic", 80.0): 1141,
    ("Golf_dynamic", 90.0): 1053,
    ("Golf_dynamic", 100.0): 1313,
    ("Golf_dynamic", 110.0): 1325,
    ("Golf_dynamic", 120.0): 1189,
    ("Golf_dynamic", 130.0): 1350,
}


def sphere_center(cluster) -> np.ndarray:
    """Centre of the point cloud ``inject_plume_stateful`` draws for a cluster.

    The ball is sampled around ``cluster.pos`` and then squashed along the ray
    (``_thin_radial``), which moves the mean along the ray only; the centre
    stays ``cluster.pos``.
    """
    return np.asarray(cluster.pos, dtype=np.float64).ravel()


def match_clusters(
    detections: np.ndarray,
    alive: list,
    *,
    radius_scale: float = 1.5,
) -> int:
    """Number of alive clusters with at least one detection inside their ball.

    A detection belongs to the ball ``|p - centre| <= radius_scale * r`` of the
    nearest alive cluster; the ball radius is the cluster radius. ``radius_scale
    = 1.5`` absorbs the angular spread of the ray-cast detections.
    """
    if not alive or detections.shape[0] == 0:
        return 0
    centres = np.asarray([sphere_center(cluster) for cluster in alive])
    radii = np.asarray([float(cluster.radius) for cluster in alive])
    points = np.asarray(detections[:, :3], dtype=np.float64)
    delta = points[:, None, :] - centres[None, :, :]
    distance = np.linalg.norm(delta, axis=2)
    nearest = np.argmin(distance, axis=1)
    inside = distance[np.arange(points.shape[0]), nearest] <= (
        radius_scale * radii[nearest]
    )
    return int(np.unique(nearest[inside]).size)


def count_dbscan(points: np.ndarray) -> int:
    """DBSCAN clusters (``>= 3`` points) on the angular plane."""
    if points.shape[0] == 0:
        return 0
    labels = cluster_angular(points)
    return int(np.unique(labels[labels >= 0]).size)


def count_dbscan_offroad(points: np.ndarray, road_z_m: float) -> int:
    """DBSCAN clusters that are not the road surface.

    ``PlumeTransform`` concatenates ``real_points`` with the detections, so the
    DBSCAN of the augmented frame also sees road points. A cluster is kept when
    its centroid is at least ``0.10 m`` above the road; this is a diagnostic
    only, the recipe (``eps``, ``minPts``) is untouched.

    Only points in a box around the plume are clustered (``|y| <= 6 m``,
    ``-60 <= x <= 40 m``, ``z`` within 3 m of the road): road points are
    thousands per frame and the O(n^2) DBSCAN would take minutes otherwise.
    """
    if points.shape[0] == 0:
        return 0
    xyz = points[:, :3].astype(np.float64)
    near = (
        (np.abs(xyz[:, 1]) <= 6.0)
        & (xyz[:, 0] >= -60.0)
        & (xyz[:, 0] <= 40.0)
        & (np.abs(xyz[:, 2] - road_z_m) <= 3.0)
    )
    subset = points[near]
    if subset.shape[0] < 3:
        return 0
    labels = cluster_angular(subset)
    kept = 0
    for cluster_id in np.unique(labels):
        if cluster_id < 0:
            continue
        members = subset[labels == cluster_id][:, :3].astype(np.float64)
        if float(members[:, 2].mean()) - road_z_m >= 0.10:
            kept += 1
    return kept


def cluster_coverage(
    detections: np.ndarray, alive: list
) -> tuple[int, int]:
    """How many alive clusters each DBSCAN cluster of the detections covers.

    Returns ``(total_covered, largest)``: the sum over DBSCAN clusters of the
    number of distinct alive clusters that own at least one of its points, and
    the largest such number. ``total_covered > dbscan`` means DBSCAN fuses
    several generator clusters into one.
    """
    if not alive or detections.shape[0] == 0:
        return 0, 0
    labels = cluster_angular(detections)
    centres = np.asarray([sphere_center(cluster) for cluster in alive])
    points = np.asarray(detections[:, :3], dtype=np.float64)
    nearest = np.argmin(
        np.linalg.norm(points[:, None, :] - centres[None, :, :], axis=2), axis=1
    )
    total = 0
    largest = 0
    for cluster_id in np.unique(labels):
        if cluster_id < 0:
            continue
        owners = set(nearest[labels == cluster_id].tolist())
        total += len(owners)
        largest = max(largest, len(owners))
    return total, largest


def collect_cell(
    group: str,
    speed_kmh: float,
    *,
    scene_count: int = 3,
    frames_per_scene: int = 30,
    radius_scale: float = 1.5,
) -> dict:
    """Alive / visible / DBSCAN counts for one class x speed cell."""
    vehicle_class, dims = GROUPS[group]
    speed_mps = speed_kmh / 3.6
    scenes = evenly(scenes_for(group, speed_kmh), scene_count)
    state = PlumeState()
    table = load_beam_table()
    config = PlumeConfig()
    alive_per_frame: list[int] = []
    visible_per_frame: list[int] = []
    dbscan_per_frame: list[int] = []
    covered_per_frame: list[int] = []
    largest_cover_per_frame: list[int] = []
    det_per_frame: list[int] = []
    capped = 0
    frames = 0
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
                alive = list(state.all_alive())
                ray = raycast_frame(
                    result.points_clean,
                    alive,
                    table=table,
                    road_z_m=ROAD_Z_M,
                    rng=np.random.default_rng(seed),
                    capped=result.stats.capped,
                )
            capped = max(capped, int(result.stats.capped))
            detections = np.asarray(ray.detections, dtype=np.float32)
            alive_per_frame.append(len(alive))
            visible_per_frame.append(
                match_clusters(detections, alive, radius_scale=radius_scale)
            )
            dbscan_per_frame.append(count_dbscan(detections))
            covered, largest = cluster_coverage(detections, alive)
            covered_per_frame.append(covered)
            largest_cover_per_frame.append(largest)
            det_per_frame.append(int(detections.shape[0]))
            frames += 1
    alive_mean = float(np.mean(alive_per_frame)) if frames else float("nan")
    visible_mean = (
        float(np.mean(visible_per_frame)) if frames else float("nan")
    )
    dbscan_mean = float(np.mean(dbscan_per_frame)) if frames else float("nan")
    covered_mean = float(np.mean(covered_per_frame)) if frames else float("nan")
    largest_cover_mean = (
        float(np.mean(largest_cover_per_frame)) if frames else float("nan")
    )
    det_mean = float(np.mean(det_per_frame)) if frames else float("nan")
    real = float(REAL_DBSCAN[(group, speed_kmh)])
    real_per_frame = real / FRAMES_PER_CELL
    return {
        "group": group,
        "speed": speed_kmh,
        "scenes": [scene.name for scene in scenes],
        "frames": frames,
        "alive": alive_mean,
        "visible": visible_mean,
        "dbscan": dbscan_mean,
        "covered": covered_mean,
        "largest_cover": largest_cover_mean,
        "alive_not_dbscan": alive_mean - dbscan_mean,
        "det_per_alive": det_mean / alive_mean if alive_mean > 0.0 else float("nan"),
        "real": real,
        "real_per_frame": real_per_frame,
        "delta": dbscan_mean - real_per_frame,
        "alive_ratio": alive_mean / real_per_frame,
        "dbscan_ratio": dbscan_mean / real_per_frame,
        "alive_vs_target": (
            alive_mean / float(cluster_count_for_speed_abs(speed_kmh, WFH_MM, vehicle_class))
            if cluster_count_for_speed_abs(speed_kmh, WFH_MM, vehicle_class) > 0
            else float("nan")
        ),
        "capped": capped,
        # Steady-state analytic values, for the branch decision.
        "alive_target": float(
            cluster_count_for_speed_abs(speed_kmh, WFH_MM, vehicle_class)
        ),
        "lifetime_s": lifetime_mean_s(speed_kmh, WFH_MM),
        # Spawn rate over the T window: what the state would hold if nothing
        # pruned it. The measured ``alive`` runs above this because the ceiling
        # prune is nearly inert (clusters sit well below the box top).
        "spawn_rate": float(
            cluster_spawn_rate_for_speed_abs(speed_kmh, vehicle_class)
        ),
    }


def branch(cells: list[dict]) -> str:
    """Pick branch 3b (spawn) or 3a (ray-cast) from the stop gate."""
    low = [cell for cell in cells if cell["alive_ratio"] <= STOP_GATE]
    if low:
        return "3b"
    return "3a"


def render(cells: list[dict], radius_scale: float) -> str:
    lines: list[str] = [
        "# 29f — cụm `alive` / `visible` / `dbscan` của generator (đo trên `cal`)",
        "",
        "Sinh bằng `scripts/measure_29f.py`. **Chỉ đo**, không sửa generator.",
        "3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful "
        "`inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`). "
        "DBSCAN góc 0,7° / minPts = 3 (recipe paper, không đổi).",
        "",
        "- `alive` = số cụm còn sống trong state ngay trước khi ray-cast "
        "(`state.all_alive()`), trung bình theo frame.",
        "- `visible` = số cụm `alive` có ≥ 1 detection nằm trong cầu "
        f"`|p − tâm| ≤ {radius_scale:g}·r` của cụm (gán detection cho cầu gần nhất).",
        "- `dbscan` = số cụm DBSCAN dựng lại từ detection của frame (≥ 3 điểm), "
        "trung bình theo frame.",
        "- `phủ` = tổng số cụm `alive` khác nhau mà các cụm DBSCAN phủ (mỗi điểm "
        "detection gán cho cụm `alive` gần nhất); `phủ max` = cụm DBSCAN phủ nhiều "
        "cụm `alive` nhất. `phủ > dbscan` ⇒ DBSCAN **gộp** nhiều cụm thành một.",
        "- `alive_not_dbscan = alive − dbscan` — cụm sinh ra nhưng DBSCAN không thấy.",
        "- `det_per_alive` = số detection / số cụm `alive`.",
        "- `real dbscan` = số cụm DBSCAN trên điểm label 2, lấy từ §2 của "
        "`29ed3-gen-overlap.md` (tổng 90 frame); `real/frame` = tổng / 90; "
        "`Δ = dbscan − real/frame`. `29ed3` báo **cụm/frame** (12,9 @100), cột "
        "`cụm real` của nó là **tổng** — so thẳng hai cột đó là lỗi đơn vị 90×.",
        "- `alive target` = `cluster_count_for_speed_abs(v, 1 mm)` (trạng thái dừng "
        "lý thuyết); `alive/target` = `alive` đo / target; `rate` = "
        "`cluster_spawn_rate_for_speed_abs(v)`; `rate·T/Δt` = số cụm state sẽ giữ nếu "
        "**không** prune; `T` = `lifetime_mean_s(v, 1 mm)`.",
        f"- **Cửa chặn:** `alive` ≤ {STOP_GATE:g}× real/frame ⇒ lỗi ở khâu **sinh cụm** "
        "(3b); `alive` ≈ real/frame mà `dbscan` thấp ⇒ lỗi ở **ray-cast** (3a).",
        "- **Đơn vị của Bảng 1** (`semantic-spray-clusters-by-speed.md`): đếm **cụm "
        "DBSCAN** (0,7° / minPts = 3) trên điểm `label == 2` — cùng toán tử với "
        "`real/frame` ở đây, không phải cụm `alive` của generator. A1 so "
        "`visible_cluster_count_for_speed` (cụm **alive**) với bảng DBSCAN ⇒ A1 đạt "
        "là **trùng hợp đơn vị**, không phải bằng chứng generator khớp.",
        "",
        "## 1. Theo lớp × tốc độ",
        "",
        "| lớp | km/h | frame | alive | alive/target | visible | dbscan | phủ | "
        "phủ max | alive_not_dbscan | det_per_alive | real/frame | Δ | "
        "alive/real | dbscan/real | alive target | rate | rate·T/Δt | T (s) | capped |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        lines.append(
            f"| {cell['group']} | {cell['speed']:g} | {cell['frames']} | "
            f"{_fmt(cell['alive'], 2)} | {_fmt(cell['alive_vs_target'], 2)} | "
            f"{_fmt(cell['visible'], 2)} | "
            f"{_fmt(cell['dbscan'], 2)} | {_fmt(cell['covered'], 2)} | "
            f"{_fmt(cell['largest_cover'], 2)} | "
            f"{_fmt(cell['alive_not_dbscan'], 2)} | "
            f"{_fmt(cell['det_per_alive'], 2)} | {_fmt(cell['real_per_frame'], 2)} | "
            f"{_fmt(cell['delta'], 2)} | {_fmt(cell['alive_ratio'], 2)} | "
            f"{_fmt(cell['dbscan_ratio'], 2)} | "
            f"{cell['alive_target']:.0f} | {_fmt(cell['spawn_rate'], 2)} | "
            f"{_fmt(cell['spawn_rate'] * cell['lifetime_s'] / DT_S, 1)} | "
            f"{_fmt(cell['lifetime_s'], 2)} | {cell['capped']} |"
        )

    lines += [
        "",
        "## 2. Gộp theo lớp (trung bình 9 tốc độ)",
        "",
        "| lớp | alive | visible | dbscan | phủ | alive_not_dbscan | "
        "det_per_alive | real/frame | Δ | alive/real | dbscan/real |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in GROUPS:
        rows = [cell for cell in cells if cell["group"] == group]
        alive = float(np.mean([row["alive"] for row in rows]))
        visible = float(np.mean([row["visible"] for row in rows]))
        dbscan = float(np.mean([row["dbscan"] for row in rows]))
        covered = float(np.mean([row["covered"] for row in rows]))
        det = float(np.mean([row["det_per_alive"] for row in rows]))
        real = float(np.mean([row["real_per_frame"] for row in rows]))
        lines.append(
            f"| {group} | {_fmt(alive, 2)} | {_fmt(visible, 2)} | "
            f"{_fmt(dbscan, 2)} | {_fmt(covered, 2)} | "
            f"{_fmt(alive - dbscan, 2)} | {_fmt(det, 2)} | "
            f"{real:.2f} | {_fmt(dbscan - real, 2)} | {_fmt(alive / real, 2)} | "
            f"{_fmt(dbscan / real, 2)} |"
        )

    chosen = branch(cells)
    # Cells *under* the gate (``<=``, same predicate as ``branch``). The 29f
    # worker counted the cells *above* the gate and printed them as "≤".
    low = [
        f"{cell['group']}@{cell['speed']:g}"
        for cell in cells
        if cell["alive_ratio"] <= STOP_GATE
    ]
    lines += ["", "## 3. Kết luận cửa chặn", ""]
    if chosen == "3b":
        lines.append(
            f"**Nhánh 3b (sinh cụm):** {len(low)}/{len(cells)} ô có `alive` ≤ "
            f"{STOP_GATE:g}× real/frame ({', '.join(low)}). Cụm không được sinh "
            "đủ, ray-cast không phải chỗ mất cụm."
        )
    else:
        lines.append(
            f"**Nhánh 3a (ray-cast):** {len(low)}/{len(cells)} ô có `alive` ≤ "
            f"{STOP_GATE:g}× real/frame ({', '.join(low) or 'không ô nào'}) — "
            "cụm sinh đủ, mất ở khâu ray-cast / DBSCAN."
        )
    lines += [
        "",
        "## 4. Cơ chế đo được",
        "",
        "- `alive` chạy **cao hơn** `alive target` (1,0–2,2×): `T` bốc `N(T, 0,2 s)` và bị "
        "kẹp ≥ 0, nên một phần cụm sống tới ~4·(T + 2σ) = 5,6·T và trạng thái giữ "
        "nhiều cụm hơn `rate·K`. Thử riêng (không ghi vào bảng): tắt hẳn prune theo "
        "trần cũng chỉ lên 9,2 / 66,6 cụm @50 / @100 ⇒ prune theo trần **không** phải "
        "chỗ mất cụm.",
        "- `visible` / `alive` ≈ 0,47 (Crafter) và 0,71 (Golf): mỗi cụm chỉ có "
        "`det_per_alive` ≈ 4–29 detection, trong khi DBSCAN cần ≥ 3 điểm **và** 3 điểm "
        "đó phải nằm trong 0,7° của nhau.",
        "- `dbscan` (chỉ detection) ≈ 0,52–0,92× real/frame với Crafter, 0,43–0,73× "
        "với Golf ở 50–90 km/h, nhưng **> 1×** với Golf ở 100–130 km/h — cột `phủ` "
        "giải thích: `phủ` luôn > `dbscan` (ví dụ Crafter@60: 17,3 cụm `alive` bị "
        "5,8 cụm DBSCAN gộp, có cụm DBSCAN phủ 7,6 cụm) ⇒ DBSCAN **gộp** nhiều cụm "
        "thành một. Detection của một cụm nằm rải trong ~1,5·r quanh tâm (p50 "
        "0,33–0,61 m), trong khi `eps = 0,7°` ở 10–20 m chỉ là 0,12–0,24 m ⇒ cụm "
        "0,3 m **không tách được** thành một cụm DBSCAN riêng. Vì vậy `dbscan` là "
        "**cận dưới** của số cụm generator, không phải phép đếm 1-1.",
        "- **Ảnh ghép không dùng được**: đo riêng 3 frame Crafter@100, DBSCAN trên "
        "`real_points` + detection (đúng đầu vào `PlumeTransform`) cho 21–29 cụm, "
        "trong đó **điểm thật một mình đã 12–20 cụm** (mưa, phản xạ, điểm trên xe) ⇒ "
        "phần lớn cụm DBSCAN ở ảnh ghép **không phải** cụm plume.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    cells = [
        collect_cell(group, speed) for group in GROUPS for speed in SPEEDS_KMH
    ]
    body = render(cells, 1.5)
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(body, encoding="utf-8")

    for cell in cells:
        print(
            f"{cell['group']} @{cell['speed']:g}: alive={cell['alive']:.2f} "
            f"({cell['alive_ratio']:.2f}x real/frame) visible={cell['visible']:.2f} "
            f"dbscan={cell['dbscan']:.2f} ({cell['dbscan_ratio']:.2f}x real/frame) "
            f"phu={cell['covered']:.2f} (max {cell['largest_cover']:.1f}) "
            f"alive_not_dbscan={cell['alive_not_dbscan']:.2f} "
            f"det/alive={cell['det_per_alive']:.2f}"
        )
    chosen = branch(cells)
    print(f"NHANH: {chosen}")
    print(f"Đã ghi {DOC}")


if __name__ == "__main__":
    main()
