#!/usr/bin/env python3
"""Đo đuôi phân bố điểm/cụm của plume **ở tầng detector thật sự thấy**.

**Bài học sửa dụng cụ (2026-11-19, do user phát hiện):** bản cũ đo trên
``PlumeResult.injected`` — các điểm *vật chất hoá* bên trong quả cầu cụm với
``ring = -1``. Nhưng ``spray/raycast.py:117`` nói rõ: điểm ``ring`` ngoài
``0..M-1`` *"take no part in intersection or occlusion"* ⇒ tầng vật chất hoá
**vô hiệu** với detector; detection thật sự sinh từ giao của **bộ tia
(VLP-32C: 32 ring × 1800 az) với mặt cầu cụm** (``_collect_hits``), một lượt rút
thăm ``P_det`` mỗi đoạn, giữ mạnh nhất mỗi tia (``_keep_strongest_per_beam``).
Đo trên tầng vô hiệu tức đo một con số không tồn tại với detector ⇒ các phán
quyết A3 trước đây (50/100 PASS, 130 FAIL) **vô hiệu**, phải đo lại ở tầng
``RaycastResult.detections`` — cùng tầng với ``label == 2`` của dữ liệu thật
(đều là *detections của cảm biến*).

Đường đo (đúng như PlumeTransform dùng khi train):

    inject_plume_stateful  ->  state.all_alive()  ->  raycast_frame  ->  detections
    (chỉ cần để giữ state)     cụm sống                54 750 tia          cái detector thấy

Đo bằng **đúng toán tử** dữ liệu thật: DBSCAN trên ``(azimuth, elevation)``,
``eps = 0,7°``, ``minPts = 3``.

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \\
        scripts/measure_plume_size_tail.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import numpy as np

from spray.beam_model import BeamTable, load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState, PlumeStateConfig
from spray.raycast import RaycastConfig, raycast_frame
from spray.semantic_stats import ANGULAR_EPS_DEG, MIN_PTS, cluster_angular

WARMUP_FRAMES = 260
# NGHIÊM THU (Lead chốt 2026-11-19, sau khi R3 chứng minh 2 seed là quá ít):
# 50 km/h giữa các seed cho det/frame 294–513 (1,75×) ⇒ sai số đo LỚN HƠN dải đích.
# Vì vậy kết luận PASS/FAIL chỉ được đọc từ cấu hình nghiệm thu: 8 seed × 120 frame.
# Muốn sweep nhanh thì truyền `--seeds 2 --frames 60`, nhưng KHÔNG được kết luận từ đó.
MEASURE_FRAMES = 120
SEEDS = 8
BIG_CLUSTER_POINTS = 50
BACKGROUND_POINTS = 30_000

# --- Toán tử của phép đo STATIC (QĐ1 2026-11-19) ---------------------------
# Static đo cụm của plume THẬT bằng cách cắt vùng sau đuôi xe thành các lát
# dày Δ = 1,0 m rồi DBSCAN góc trong TỪNG lát (lát phá chain dọc tia). DBSCAN
# trên CẢ frame (cột `cụm`/`p95`/`share` cũ) là toán tử khác ⇒ p95/share không
# so trực tiếp với đích static được. Cột `*_slice` dưới đây mới cùng đơn vị đo.
# Hằng số copy từ scripts/roadspray_static_plume_box.py.
SLICE_WIDTH_M = 1.0
BOX_WIDTH_M = 3.4
BOX_HEIGHT_M = 1.5
BOX_LENGTH_M = 20.0
# R3 #4: MỘT nguồn duy nhất cho rear_x. Hộp generator dài 6,8 m (VW Crafter),
# trước đây box đo dùng half = 3,5 ⇒ rear lệch 0,1 m so với 16,6 của hộp sinh.
VEHICLE_BOX_LENGTH_M = 6.8
BOX_HALF_LENGTH_M = VEHICLE_BOX_LENGTH_M / 2.0
H_ABOVE_M = 0.15
# R3 #1: mask cho profile độ sâu phải GIỐNG HỆT vế thật (T4 của R2):
# ngang ±5 m, cao 0,15–3,0 m tính từ mặt đường. Nếu không mask thì (a)/(b')
# là hai cái thước khác nhau — lần lệch toán tử thứ 6.
PROFILE_HALF_WIDTH_M = 5.0
PROFILE_HEIGHT_MIN_M = 0.15
PROFILE_HEIGHT_MAX_M = 3.0
# QĐ14 2026-11-19 — instrument phải mô phỏng ĐÚNG kịch bản static của T4:
# ego ĐỨNG YÊN, xe đối tượng chạy RA XA (xe đi qua ego rồi rời đi). T4 đo trên
# các frame track-valid có car_range p50 77/103 m, max 97/166/207 m (KHÔNG có
# cửa sổ 18–38 m — cửa sổ đó là của phép đo hộp cũ). Vì vậy đường chạy mô phỏng
# từ sau ego tới 200 m, đo từ car_range ≥ 12 m.
STATIC_DT_S = 0.1
STATIC_MIN_TAIL_RANGE_M = 18.5
STATIC_END_X_M = 200.0
STATIC_NEAR_FIELD_M = 4.0   # T4 loại điểm sát ego (range <= 4 m)
STATIC_BODY_DIMS_M = {      # T4 §5b --body-box
    "crafter": (7.0, 2.4, 2.6),
    "golf": (4.3, 1.8, 1.5),
}
STATIC_BODY_MARGIN_M = 0.2

# Target T4-final (biến thể `geom`): điểm/frame masked, trail90, %mass<=20 m.
TARGET_DET = {50.0: 85.1, 100.0: 202.6, 130.0: 208.9}
TARGET_TRAIL90 = {50.0: 6.0, 100.0: 44.0, 130.0: 52.0}
TARGET_MASS20 = {50.0: 99.5, 100.0: 53.8, 130.0: 25.7}
ROAD_Z_M = -1.6
BOX_CENTRE_X_M = 20.0

# QĐ10 2026-11-19 — profile theo **độ sâu**, KHÔNG qua clustering.
# Lý do: cả hai vế (generator và static) đều đi qua `cluster_angular`, mà toán
# tử đó bóp méo bán kính khác nhau với quả cầu rời (generator) và chuỗi điểm
# dày (dữ liệu thật) — đo được trong `.scratch/tmp/operator_transfer.py`:
# input 0,31 m -> đo lại 0,17–0,24; input 0,8 m -> 0,46. Vì vậy mọi tiêu chí
# cluster (r50/p95/share/cụm) chỉ còn là CHẨN ĐOÁN, không phải điều kiện PASS.
# Đại lượng so sánh mới = **đếm điểm theo bin độ sâu** sau đuôi xe, hai vế dùng
# cùng một phép binning.
DEPTH_BIN_M = 2.0
DEPTH_MAX_M = 60.0
DEPTH_BIN_EDGES_M = tuple(
    float(index) * DEPTH_BIN_M
    for index in range(int(DEPTH_MAX_M / DEPTH_BIN_M) + 1)
)


def static_slice_cluster_sizes(
    detections: np.ndarray,
) -> tuple[list[int], list[float]]:
    """Kích thước cụm theo ĐÚNG toán tử của `roadspray_static_plume_box.py`.

    Vùng sau đuôi xe: dài 20 m sau mặt đuôi (rear = 20 − 3,5 m), ngang 3,4 m,
    cao (0,15; 1,5] m trên mặt đường. Cắt lát dày Δ = 1,0 m theo **độ sâu sau
    đuôi**, rồi DBSCAN `(azimuth, elevation)` eps 0,7° / minPts 3 trong từng
    lát. Trả về kích thước từng cụm (chỉ cụm ≥ minPts, giống static).
    """
    if detections.shape[0] == 0:
        return [], []
    pos = detections[:, :3].astype(np.float64)
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
    depth = (BOX_CENTRE_X_M - BOX_HALF_LENGTH_M) - x
    height = z - ROAD_Z_M
    base = (
        (np.abs(y) <= BOX_WIDTH_M / 2.0)
        & (height > H_ABOVE_M)
        & (height <= BOX_HEIGHT_M)
    )
    behind = base & (depth >= 0.0) & (depth <= BOX_LENGTH_M)
    if int(behind.sum()) < MIN_PTS:
        return [], []
    points = pos[behind]
    capsules = np.floor(depth[behind] / SLICE_WIDTH_M).astype(np.int64)
    sizes: list[int] = []
    radii: list[float] = []
    for capsule in np.unique(capsules):
        members = points[capsules == capsule]
        if members.shape[0] < MIN_PTS:
            continue
        labels = cluster_angular(members, eps_deg=ANGULAR_EPS_DEG,
                                 min_pts=MIN_PTS)
        for label in np.unique(labels[labels >= 0]):
            cluster = members[labels == label]
            centroid = cluster.mean(axis=0)
            # QĐ8 — định nghĩa bán kính của chính paper §III-B:
            # "the radii r_cl are set to the maximum distance of detections to
            # the respective cluster center".
            radii.append(float(np.linalg.norm(cluster - centroid, axis=1).max()))
            sizes.append(int(cluster.shape[0]))
    return sizes, radii

# docs/measurements/sspp-cluster-size-distribution.md (Crafter, gộp 3 fold) —
# các số THẬT đều là detections của cảm biến nên so ở tầng raycast mới công bằng.
# `[ĐO] 2026-11-19` ĐÍCH TỪ **ROADSPRAY `*_static`** (ADR-0006 D2), không từ SSPP.
# Số liệu: .scratch/roadspray-cal/tmp/a3_targets_static.json, đo bằng
# scripts/roadspray_static_plume_box.py (Δ = 1,0 / 2,5 / 6,0 m, L = 20 m).
# Vì phép đo static phải CẮT LÁT để phá chain dọc tia, các đại lượng phụ thuộc
# bề dày lát; dải dưới đây được lấy là **min..max qua ba bề dày lát** — tức biên
# độ bất định định nghĩa vùng, đúng như doc đã khai (±30-40 %).
# Điểm chuẩn để so `det/frame` là điểm/frame ở Δ = 2,5 m.
REAL = {
    # r50 Δ=1,0 [ĐO] a3_targets_static.json: 0,349 / 0,292 / 0,311 m;
    # rsig Δ=1,0 = 0,754 / 0,727 / 0,711 (median 9 tốc độ = 0,720).
    50.0: {"det": (229, 242), "share": (77.9, 92.3), "p95": (172, 329),
           "p50": (5, 7), "mean": (25.4, 67.1), "cpf": 9.04,
           "r50": 0.349, "rsig": 0.754},
    100.0: {"det": (476, 523), "share": (39.2, 71.2), "p95": (43, 156),
            "p50": (6, 8), "mean": (13.3, 30.4), "cpf": 35.86,
            "r50": 0.292, "rsig": 0.727},
    130.0: {"det": (408, 456), "share": (34.7, 75.1), "p95": (36, 181),
            "p50": (5, 7), "mean": (12.3, 33.2), "cpf": 33.08,
            "r50": 0.311, "rsig": 0.711},
}


def production_table() -> BeamTable:
    """Bộ tia **production** — đúng cái ``PlumeTransform`` dùng khi train.

    SỬA LỖI DỤNG CỤ 2026-11-19 (R2 audit): bản cũ dựng tay 32 ring × 1800 az
    (0,2°) trong khi production dùng `load_beam_table()` = **30 ring × 1825 az
    (0,197307°)**. Hai lưới khác nhau ⇒ mọi con số A3 trước đây đo trên một
    dụng cụ không tồn tại trong production. Số cụm/det phụ thuộc trực tiếp vào
    số tia và cách chúng cắt quả cầu, nên phải dùng đúng lưới production.
    """
    return load_beam_table()


def _context(speed_kmh: float, frame_index: int) -> PlumeContext:
    speed_mps = speed_kmh / 3.6
    return PlumeContext(
        scene_token="tail",
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=speed_mps,
        object_speed_mps=speed_mps,
        wfh_mm=1.0,
        road_z_m=-1.6,
    )


def _static_context(speed_kmh: float, frame_index: int) -> PlumeContext:
    """QĐ14: ego ĐỨNG YÊN; xe chạy ra xa với vận tốc mặt đường ``speed``.

    ``object_velocity_ego_mps = [v, 0, 0]`` và ``ego_speed_mps = 0`` để vận tốc
    ground lúc sinh = vận tốc xe (đúng "initial velocity = object velocity").
    """
    speed_mps = speed_kmh / 3.6
    return PlumeContext(
        scene_token="tail",
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=0.0,
        object_speed_mps=speed_mps,
        object_velocity_ego_mps=np.array(
            [speed_mps, 0.0, 0.0], dtype=np.float64
        ),
        wfh_mm=1.0,
        road_z_m=ROAD_Z_M,
    )


def _static_box(car_x_m: float, speed_mps: float) -> np.ndarray:
    return np.array(
        [[car_x_m, 0.0, ROAD_Z_M, VEHICLE_BOX_LENGTH_M, 2.4, 2.6,
          0.0, speed_mps, 0.0]],
        dtype=np.float64,
    )


def _static_profile(
    measured: list[tuple[float, np.ndarray]], class_name: str
) -> dict:
    """Profile độ sâu 0–60 m đúng định nghĩa T4 (QĐ14)."""
    body_length, body_width, body_height = STATIC_BODY_DIMS_M[class_name]
    n_bins = len(DEPTH_BIN_EDGES_M) - 1
    profile_masked = np.zeros(n_bins, dtype=np.float64)
    profile_unmasked = np.zeros(n_bins, dtype=np.float64)
    total_masked = 0
    total_unmasked = 0
    beyond_masked = 0
    beyond_unmasked = 0
    n_near_field = 0
    n_range_lt_15 = 0
    n_all = 0
    n_body_removed = 0
    for car_x, detections in measured:
        if detections.shape[0] == 0:
            continue
        xyz = detections[:, :3].astype(np.float64)
        ranges = np.linalg.norm(xyz, axis=1)
        near_ok = ranges > STATIC_NEAR_FIELD_M
        n_all += int(xyz.shape[0])
        n_near_field += int((~near_ok).sum())
        n_range_lt_15 += int((ranges < 15.0).sum())
        rear = car_x - VEHICLE_BOX_LENGTH_M / 2.0
        depth = rear - xyz[:, 0]
        height = xyz[:, 2] - ROAD_Z_M
        inside_body = (
            (np.abs(xyz[:, 0] - car_x) <= body_length / 2.0
             + STATIC_BODY_MARGIN_M)
            & (np.abs(xyz[:, 1]) <= body_width / 2.0 + STATIC_BODY_MARGIN_M)
            & (height >= 0.0)
            & (height <= body_height + STATIC_BODY_MARGIN_M)
        )
        body_ok = ~inside_body
        n_body_removed += int((inside_body & near_ok).sum())
        behind = near_ok & body_ok & (depth >= 0.0)
        masked = (
            behind
            & (np.abs(xyz[:, 1]) <= PROFILE_HALF_WIDTH_M)
            & (height >= PROFILE_HEIGHT_MIN_M)
            & (height <= PROFILE_HEIGHT_MAX_M)
        )
        for mask, profile in (
            (masked, profile_masked),
            (behind, profile_unmasked),
        ):
            inside = mask & (depth < DEPTH_MAX_M)
            index = np.floor(depth[inside] / DEPTH_BIN_M).astype(np.int64)
            if index.size:
                profile += np.bincount(index, minlength=profile.size)
        total_masked += int(masked.sum())
        total_unmasked += int(behind.sum())
        beyond_masked += int((masked & (depth >= DEPTH_MAX_M)).sum())
        beyond_unmasked += int((behind & (depth >= DEPTH_MAX_M)).sum())
    n_frames = max(len(measured), 1)
    masked_per_frame = profile_masked / n_frames
    unmasked_per_frame = profile_unmasked / n_frames
    edges = np.asarray(DEPTH_BIN_EDGES_M, dtype=np.float64)

    def _depth_at(profile: np.ndarray, fraction: float) -> tuple[float, float]:
        cumulative = np.cumsum(profile)
        total = float(cumulative[-1]) if cumulative.size else 0.0
        if total <= 0.0:
            return float("nan"), float("nan")
        position = int(np.searchsorted(cumulative, fraction * total))
        position = min(position, len(edges) - 2)
        return float(edges[position]), float(edges[position + 1])

    def _mass_upto(profile: np.ndarray, limit_m: float) -> float:
        total = float(profile.sum())
        if total <= 0.0:
            return float("nan")
        return float(
            100.0 * profile[edges[1:] <= limit_m].sum() / total
        )

    return {
        "det_masked_frame": total_masked / n_frames,
        "det_unmasked_frame": total_unmasked / n_frames,
        "depth_profile_masked": masked_per_frame.tolist(),
        "depth_profile_unmasked": unmasked_per_frame.tolist(),
        "depth_bin_edges_m": list(edges),
        "depth_total_masked": total_masked / n_frames,
        "depth_total_unmasked": total_unmasked / n_frames,
        "depth_trail90_masked_m": _depth_at(masked_per_frame, 0.90)[1],
        "depth_trail90_unmasked_m": _depth_at(unmasked_per_frame, 0.90)[1],
        "depth_mass20_masked_pct": _mass_upto(masked_per_frame, 20.0),
        "depth_frac_beyond_60_masked": (
            beyond_masked / total_masked if total_masked else 0.0
        ),
        "depth_frac_beyond_60_unmasked": (
            beyond_unmasked / total_unmasked if total_unmasked else 0.0
        ),
        "near_field_frac": (n_near_field / n_all if n_all else 0.0),
        "range_lt_15_frac": (n_range_lt_15 / n_all if n_all else 0.0),
        "body_removed_frac": (
            n_body_removed / (n_body_removed + total_masked)
            if (n_body_removed + total_masked) else 0.0
        ),
        "measured_frames": n_frames,
    }


def measure_speed(
    speed_kmh: float,
    seed: int,
    table: BeamTable,
    spawn_scale: float | None = None,
    radius_sigma: float | None = None,
    streak_scale: float | None = None,
    p_det_scale: float = 1.0,
    diffusion_alpha: float | None = None,
    class_name: str = "crafter",
) -> dict:
    """Một seed của kịch bản **static** QĐ14 (ego đứng yên, xe chạy ra xa)."""
    defaults = PlumeStateConfig()
    if spawn_scale is None:
        spawn_scale = defaults.spawn_scale
    if radius_sigma is None:
        radius_sigma = defaults.radius_sigma
    if streak_scale is None:
        streak_scale = defaults.streak_scale
    if diffusion_alpha is None:
        diffusion_alpha = defaults.diffusion_alpha
    config = PlumeConfig(
        point_cloud_range=(-60.0, -20.0, -6.0, 220.0, 20.0, 6.0)
    )
    state = PlumeState(
        PlumeStateConfig(
            spawn_scale=spawn_scale,
            radius_sigma=radius_sigma,
            streak_scale=streak_scale,
            diffusion_alpha=diffusion_alpha,
        )
    )
    speed_mps = speed_kmh / 3.6
    step_m = speed_mps * STATIC_DT_S
    # Bắt đầu đủ xa để **vùng sinh** (slab |v|·Δt ngay sau đuôi) nằm trọn
    # ngoài range 15 m — cửa kiểm QĐ14 (không còn detection range < 15 m).
    start_x = STATIC_MIN_TAIL_RANGE_M + step_m + 0.5
    n_steps = int(np.ceil((STATIC_END_X_M - start_x) / step_m)) + 1
    rng_background = np.random.default_rng(seed)
    background = np.zeros((BACKGROUND_POINTS, 5), dtype=np.float32)
    background[:, 0] = rng_background.uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 1] = rng_background.uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 2] = ROAD_Z_M

    measured: list[tuple[float, np.ndarray]] = []
    detections_all: list[np.ndarray] = []
    if n_steps <= 0:
        n_steps = 1
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        for index in range(n_steps):
            car_x = start_x + step_m * index
            result = inject_plume_stateful(
                background,
                _static_box(car_x, speed_mps),
                _static_context(speed_kmh, index),
                state,
                seed=seed * 100_000 + index,
                token=f"tail/{index}",
                config=config,
            )
            # đo mọi frame sinh ra sau khi đã đủ xa (xem start_x)

            ray = raycast_frame(
                result.points,
                state.all_alive(),
                table=table,
                road_z_m=ROAD_Z_M,
                rng=np.random.default_rng(seed * 777 + index),
                config=RaycastConfig(p_det_scale=p_det_scale),
            )
            measured.append((car_x, ray.detections))
            detections_all.append(ray.detections)

    if MEASURE_FRAMES > 0:
        measured = measured[:MEASURE_FRAMES]
        detections_all = detections_all[:MEASURE_FRAMES]

    # --- chẩn đoán cluster (giữ từ dụng cụ cũ) ---
    flat_sizes: list[int] = []
    flat_sizes_slice: list[int] = []
    flat_radii_slice: list[float] = []
    totals: list[int] = []
    for detections in detections_all:
        totals.append(int(detections.shape[0]))
        pos = detections[:, :3].astype(np.float64)
        if pos.shape[0] >= MIN_PTS:
            labels = cluster_angular(pos, eps_deg=ANGULAR_EPS_DEG,
                                     min_pts=MIN_PTS)
            valid = labels[labels >= 0]
            if valid.size:
                flat_sizes.extend(int(v) for v in np.bincount(valid))
        slice_sizes, slice_radii = static_slice_cluster_sizes(detections)
        flat_sizes_slice.extend(slice_sizes)
        flat_radii_slice.extend(slice_radii)
    array = np.asarray(flat_sizes, dtype=np.int64)
    big = array[array >= BIG_CLUSTER_POINTS]
    array_s = np.asarray(flat_sizes_slice, dtype=np.int64)
    radii_s = np.asarray(flat_radii_slice, dtype=np.float64)
    radii_s = radii_s[radii_s > 0.0]

    # --- profile độ sâu QĐ14 ---
    profile = _static_profile(measured, class_name)
    return {
        "detections_frame": float(np.mean(totals)),
        "n_cluster": float(array.size) / max(len(detections_all), 1),
        "p50": float(np.median(array)) if array.size else 0.0,
        "mean": float(array.mean()) if array.size else 0.0,
        "p95": float(np.percentile(array, 95)) if array.size else 0.0,
        "max": int(array.max()) if array.size else 0,
        "share_big": 100.0 * float(big.sum()) / max(float(array.sum()), 1e-9),
        "big_count": int(big.size),
        "det_slice_frame": float(array_s.sum()) / max(len(detections_all), 1),
        "n_cluster_slice": float(array_s.size) / max(len(detections_all), 1),
        "r50_slice": float(np.median(radii_s)) if radii_s.size else 0.0,
        "rsig_slice": (
            float(np.log(radii_s).std(ddof=0)) if radii_s.size > 1 else 0.0
        ),
        **profile,
    }


def main() -> None:
    global SEEDS, MEASURE_FRAMES
    import argparse as _argparse
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--spawn-scale", type=float,
                     default=PlumeStateConfig().spawn_scale)
    _cfg = PlumeStateConfig()
    _ap.add_argument("--radius-sigma", type=float, default=_cfg.radius_sigma)
    _ap.add_argument("--streak-scale", type=float, default=_cfg.streak_scale)
    _ap.add_argument("--diffusion-alpha", type=float,
                     default=_cfg.diffusion_alpha,
                     help="QĐ13: hệ số tán xạ bán kính theo độ sâu (0,0 = tắt)")
    _ap.add_argument("--p-det-scale", type=float, default=1.0,
                     help="hệ số nhân P_det [CHỌN] hiệu chỉnh theo static")
    _ap.add_argument("--seeds", type=int, default=SEEDS,
                     help="số seed (nghiệm thu = 8; sweep nhanh = 2)")
    _ap.add_argument("--frames", type=int, default=MEASURE_FRAMES,
                     help="cap số frame đo mỗi seed (mỗi lượt chạy static có "
                          "131/66/51 frame ứng 50/100/130 km/h)")
    _ap.add_argument(
        "--profile-out",
        default=str(
            Path(__file__).resolve().parents[1]
            / ".scratch/tmp/a3_generator_profiles.json"
        ),
        help="ghi profile độ sâu QĐ14 (JSON); '' để tắt",
    )
    _args = _ap.parse_args()
    SEEDS = int(_args.seeds)
    MEASURE_FRAMES = int(_args.frames)
    table = production_table()
    print(
        "QĐ14 — KỊCH BẢN STATIC: ego ĐỨNG YÊN, xe chạy ra xa tới "
        f"{STATIC_END_X_M:.0f} m; vùng sinh bắt đầu đủ xa để không có "
        f"detection range < {STATIC_MIN_TAIL_RANGE_M:.0f} m"
    )
    print(
        f"THAM SỐ: spawn_scale={_args.spawn_scale:.3f} "
        f"radius_sigma={_args.radius_sigma:.3f} "
        f"streak_scale={_args.streak_scale:.3f} "
        f"diffusion_alpha={_args.diffusion_alpha:.3f} "
        f"p_det_scale={_args.p_det_scale:.3f} | seeds={SEEDS}"
    )
    header = (
        f"{'km/h':>5} {'điểm/f':>8} {'trail90':>8} {'%≤20m':>7} "
        f"{'n_frame':>7} {'range<15m':>9} {'body_rm':>7} "
        f"{'CI95':>8} | đích T4 geom (điểm, trail90, %≤20)"
    )
    print(header)
    verdicts = []
    results: dict[float, dict] = {}
    for speed_kmh in sorted(TARGET_DET):
        runs = [
            measure_speed(
                speed_kmh, seed, table, _args.spawn_scale,
                _args.radius_sigma, _args.streak_scale,
                p_det_scale=_args.p_det_scale,
                diffusion_alpha=_args.diffusion_alpha,
            )
            for seed in range(SEEDS)
        ]
        got = {
            key: float(np.mean([run[key] for run in runs]))
            for key in runs[0]
            if np.isscalar(runs[0][key])
        }
        for key in ("depth_profile_masked", "depth_profile_unmasked"):
            got[key] = np.mean(
                np.asarray([run[key] for run in runs], dtype=np.float64),
                axis=0,
            ).tolist()
        got["depth_bin_edges_m"] = list(runs[0]["depth_bin_edges_m"])
        results[speed_kmh] = got

        det_seeds = np.asarray([run["det_masked_frame"] for run in runs],
                               dtype=np.float64)
        rng_ci = np.random.default_rng(12345)
        boot = rng_ci.choice(
            det_seeds, size=(2000, det_seeds.size), replace=True
        ).mean(axis=1)
        ci95 = 0.5 * float(
            np.percentile(boot, 97.5) - np.percentile(boot, 2.5)
        )
        rel_ci = ci95 / max(float(det_seeds.mean()), 1e-9)
        ratio = got["depth_total_masked"] / TARGET_DET[speed_kmh]
        trail_ratio = (
            got["depth_trail90_masked_m"] / TARGET_TRAIL90[speed_kmh]
        )
        criteria = [
            0.7 <= ratio <= 1.5,
            abs(trail_ratio - 1.0) <= 0.25,
            rel_ci <= 0.25,
        ]
        verdicts.append(all(criteria))
        mark = "PASS" if all(criteria) else "FAIL"
        if rel_ci > 0.25:
            mark = "NHIỄU"
        print(
            f"{speed_kmh:>5.0f} {got['depth_total_masked']:>8.1f} "
            f"{got['depth_trail90_masked_m']:>7.1f}m "
            f"{got['depth_mass20_masked_pct']:>6.1f}% "
            f"{got['measured_frames']:>7.0f} "
            f"{got['range_lt_15_frac'] * 100:>8.1f}% "
            f"{got['body_removed_frac'] * 100:>6.1f}% "
            f"±{rel_ci * 100:>5.1f}% | "
            f"đích {TARGET_DET[speed_kmh]:>5.1f} / "
            f"{TARGET_TRAIL90[speed_kmh]:>4.0f} m / "
            f"{TARGET_MASS20[speed_kmh]:>4.1f}% -> {mark} "
            f"(det {ratio:.2f}×, trail {trail_ratio:.2f}×)"
        )
    print()
    print(
        "TIÊU CHÍ (a) điểm/frame masked ∈ [0,7; 1,5]× đích T4 geom; "
        "(b') trail90 trong ±25 % (proxy; profile-shape đầy đủ in ở JSON); "
        "(c) CI95 ≤ 25 %. `range<15m` = tỉ lệ detection bị loại bởi NEAR_FIELD "
        "(T4 dùng 4 m)."
    )
    print(f"KẾT QUẢ A3: {'PASS' if all(verdicts) else 'FAIL'}")

    if _args.profile_out:
        out = Path(_args.profile_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "generated_by": "scripts/measure_plume_size_tail.py",
                    "scenario": "static_QD14",
                    "note": (
                        "QĐ14: ego đứng yên, xe chạy 12–200 m; profile 0–60 m "
                        "bin 2 m, mask ±5 m / 0,15–3,0 m, bỏ hộp 3D thân xe"
                    ),
                    "seeds": SEEDS,
                    "params": {
                        "spawn_scale": _args.spawn_scale,
                        "radius_sigma": _args.radius_sigma,
                        "streak_scale": _args.streak_scale,
                        "diffusion_alpha": _args.diffusion_alpha,
                        "p_det_scale": _args.p_det_scale,
                    },
                    "targets": {
                        f"{speed:.0f}": {
                            "det": TARGET_DET[speed],
                            "trail90_m": TARGET_TRAIL90[speed],
                            "mass20_pct": TARGET_MASS20[speed],
                        }
                        for speed in sorted(TARGET_DET)
                    },
                    "profiles": {
                        f"{speed:.0f}": {
                            key: value
                            for key, value in results[speed].items()
                            if key.startswith("depth_")
                            or key in (
                                "det_masked_frame",
                                "det_unmasked_frame",
                                "near_field_frac",
                                "range_lt_15_frac",
                                "body_removed_frac",
                                "measured_frames",
                            )
                        }
                        for speed in sorted(TARGET_DET)
                    },
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"DEPTH_PROFILE_WRITTEN path={out}")


if __name__ == "__main__":
    main()
