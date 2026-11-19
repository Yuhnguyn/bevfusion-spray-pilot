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

import numpy as np

from spray.beam_model import BeamTable, load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState, PlumeStateConfig
from spray.raycast import raycast_frame
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
BOX_HALF_LENGTH_M = 3.5
H_ABOVE_M = 0.15
ROAD_Z_M = -1.6
BOX_CENTRE_X_M = 20.0


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


def measure_speed(speed_kmh: float, seed: int, table: BeamTable,
                  spawn_scale: float = 1.0,
                  radius_sigma: float = 0.8,
                  streak_scale: float = 1.0) -> dict:
    """Chạy tới trạng thái dừng; đo **tầng raycast** trên các frame đo.

    Chỉ raycast ở cửa sổ đo (state không phụ thuộc raycast) — 54 750 tia/frame
    nên đỡ được phần lớn thời gian ở 260 frame warming.
    """
    config = PlumeConfig()
    from spray.plume_state import PlumeState, PlumeStateConfig
    state = PlumeState(PlumeStateConfig(spawn_scale=spawn_scale,
                                        radius_sigma=radius_sigma,
                                        streak_scale=streak_scale))
    speed_mps = speed_kmh / 3.6
    # Box theo quy ước adapter: box[2] = ĐÁY hộp, box[3] = dài, box[4] = rộng,
    # box[5] = cao. Kích thước ĐÚNG của VW Crafter (6.8 × 2.4 × 2.6 m) như dữ
    # liệu thật — bản trước hard-code 4.5 × 1.9 × 1.5, làm khối plume thấp hơn
    # thực tế 1.1 m nên phần lớn rơi dưới mép dưới FOV `[DO] 2026-11-19`.
    box = np.array([[20.0, 0.0, -1.6, 6.8, 2.4, 2.6, 0.0, speed_mps, 0.0]],
                   dtype=np.float64)
    rng_background = np.random.default_rng(seed)
    background = np.zeros((BACKGROUND_POINTS, 5), dtype=np.float32)
    background[:, 0] = rng_background.uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 1] = rng_background.uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 2] = -1.6

    frames: list[np.ndarray] = []
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        for index in range(WARMUP_FRAMES + MEASURE_FRAMES):
            result = inject_plume_stateful(
                background,
                box,
                _context(speed_kmh, index),
                state,
                seed=seed * 100_000 + index,
                token=f"tail/{index}",
                config=config,
            )
            if index < WARMUP_FRAMES:
                continue
            ray = raycast_frame(
                result.points,
                state.all_alive(),
                table=table,
                road_z_m=-1.6,
                rng=np.random.default_rng(seed * 777 + index),
            )
            frames.append(ray.detections)

    flat_sizes: list[int] = []
    flat_sizes_slice: list[int] = []
    flat_radii_slice: list[float] = []
    totals: list[int] = []
    for detections in frames:
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
    big_s = array_s[array_s >= BIG_CLUSTER_POINTS]
    radii_s = np.asarray(flat_radii_slice, dtype=np.float64)
    radii_s = radii_s[radii_s > 0.0]
    r50_slice = float(np.median(radii_s)) if radii_s.size else 0.0
    rsig_slice = (
        float(np.log(radii_s).std(ddof=0)) if radii_s.size > 1 else 0.0
    )
    return {
        "detections_frame": float(np.mean(totals)),
        "n_cluster": float(array.size) / max(len(frames), 1),
        "p50": float(np.median(array)) if array.size else 0.0,
        "mean": float(array.mean()) if array.size else 0.0,
        "p95": float(np.percentile(array, 95)) if array.size else 0.0,
        "max": int(array.max()) if array.size else 0,
        "share_big": 100.0 * float(big.sum()) / max(float(array.sum()), 1e-9),
        "big_count": int(big.size),
        # --- cột cùng toán tử với đích static (cắt lát Δ=1,0 m) ---
        "det_slice_frame": float(array_s.sum()) / max(len(frames), 1),
        "n_cluster_slice": float(array_s.size) / max(len(frames), 1),
        "p50_slice": float(np.median(array_s)) if array_s.size else 0.0,
        "mean_slice": float(array_s.mean()) if array_s.size else 0.0,
        "p95_slice": float(np.percentile(array_s, 95)) if array_s.size else 0.0,
        "max_slice": int(array_s.max()) if array_s.size else 0,
        "share_big_slice": 100.0 * float(big_s.sum()) / max(float(array_s.sum()), 1e-9),
        "big_count_slice": int(big_s.size),
        # QĐ8: hai đại lượng BẤT BIẾN với toán tử cắt lát/vùng cắt (định nghĩa paper)
        "r50_slice": r50_slice,
        "rsig_slice": rsig_slice,
        "n_radius_slice": int(radii_s.size),
    }


def main() -> None:
    global SEEDS, MEASURE_FRAMES
    import argparse as _argparse
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--spawn-scale", type=float,
                     default=PlumeStateConfig().spawn_scale)
    # SỬA LỖI DỤNG CỤ 2026-11-19 (Lead): hai default dưới đây từng hard-code
    # 0,8 và 1,0 trong khi `PlumeStateConfig` dùng 0,73 / 0,5 ⇒ "chạy default"
    # KHÔNG đo đúng config, và mọi phán quyết "PASS/FAIL mặc định" đều lệch.
    # Bây giờ default đọc thẳng từ config.
    _cfg = PlumeStateConfig()
    _ap.add_argument("--radius-sigma", type=float, default=_cfg.radius_sigma)
    _ap.add_argument("--streak-scale", type=float, default=_cfg.streak_scale)
    _ap.add_argument("--seeds", type=int, default=SEEDS,
                     help="số seed (nghiệm thu = 8; sweep nhanh = 2)")
    _ap.add_argument("--frames", type=int, default=MEASURE_FRAMES,
                     help="số frame đo mỗi seed (nghiệm thu = 120; sweep = 60)")
    _args = _ap.parse_args()
    SEEDS = int(_args.seeds)
    MEASURE_FRAMES = int(_args.frames)
    table = production_table()
    header = (f"{'km/h':>5} {'det':>6} {'cụm_f':>6} {'cụm_sl':>6} "
              f"{'det_sl':>6} {'r50s':>5} {'rsigs':>5} "
              f"{'p95s':>5} {'%≥50s':>7} {'CI95':>8} "
              f"| thật (det, cụm, r50, rsig) | A3")
    print(header)
    verdicts = []
    for speed_kmh in sorted(REAL):
        runs = [measure_speed(speed_kmh, seed, table, _args.spawn_scale,
                              _args.radius_sigma, _args.streak_scale)
                for seed in range(SEEDS)]
        got = {key: float(np.mean([run[key] for run in runs]))
               for key in runs[0]}
        real = REAL[speed_kmh]

        # CI95 half-width của det/frame **theo seed** (bootstrap percentile, B=2000).
        det_seeds = np.asarray([run["detections_frame"] for run in runs],
                               dtype=np.float64)
        _rng_ci = np.random.default_rng(12345)
        _boot = _rng_ci.choice(det_seeds, size=(2000, det_seeds.size),
                               replace=True).mean(axis=1)
        ci95 = 0.5 * float(np.percentile(_boot, 97.5) - np.percentile(_boot, 2.5))
        rel_ci = ci95 / max(float(det_seeds.mean()), 1e-9)
        stable = rel_ci <= 0.25

        def inside(value, band):
            low, high = band
            return low * 0.85 <= value <= high * 1.15

        det_ratio = got["detections_frame"] / np.mean(real["det"])
        # (b) đọc trên cột **slice** — cùng toán tử cắt lát Δ=1,0 m với đích
        # static (QĐ1 2026-11-19). Cột full-frame chỉ in để đối chiếu.
        r50_rel = (got["r50_slice"] - real["r50"]) / real["r50"]
        rsig_rel = (got["rsig_slice"] - real["rsig"]) / real["rsig"]
        criteria = [
            abs(r50_rel) <= 0.20,      # (b) QĐ8: bán kính ±20 %
            abs(rsig_rel) <= 0.20,     # (b) QĐ8: sigma ±20 %
            0.7 <= det_ratio <= 1.5,   # (a)
            stable,                    # (c)
        ]
        verdicts.append(all(criteria))
        if not stable:
            mark = "NHIỄU"
        else:
            mark = "PASS" if all(criteria) else "FAIL"
        which = ("đúng" if 0.7 <= det_ratio <= 1.5
                 else "thiếu" if det_ratio < 0.7 else "thừa")
        cpf_ratio = got["n_cluster_slice"] / real["cpf"]
        warn = "" if 0.5 <= cpf_ratio <= 2.0 else f"  ⚠cụm×{cpf_ratio:.1f}"
        print(f"{speed_kmh:>5.0f} {got['detections_frame']:>6.0f} "
              f"{got['n_cluster']:>6.1f} {got['n_cluster_slice']:>6.1f} "
              f"{got['det_slice_frame']:>6.0f} {got['r50_slice']:>5.2f} "
              f"{got['rsig_slice']:>5.2f} {got['p95_slice']:>5.0f} "
              f"{got['share_big_slice']:>6.1f}% CI95±{rel_ci * 100:>4.1f}% "
              f"| thật: det {np.mean(real['det']):>4.0f}, cụm {real['cpf']:>4.1f}, "
              f"r50 {real['r50']:.3f}, rsig {real['rsig']:.3f} "
              f"-> {mark} (det {det_ratio:.2f}×, r50 {(r50_rel+1):.2f}×, "
              f"rsig {(rsig_rel+1):.2f}×){warn}")
    print()
    print(f"TIÊU CHÍ A3 — đo ở tầng raycast (= tầng detector thật sự thấy), "
          f"cần ĐỦ 5 điều, {SEEDS} seed × {MEASURE_FRAMES} frame:")
    print("  (a) det/frame ∈ [0,7×; 1,5×] mức thật (det = cả frame, cột `det`)")
    print("  (b) QĐ8 2026-11-19: r50_slice và rsig_slice (định nghĩa paper §III-B,")
    print("      bất biến với toán tử cắt lát) nằm trong ±20 % đích Δ=1,0 (0,349/0,292/0,311;")
    print("      rsig 0,754/0,727/0,711). p95_slice/share_slice CHỈ in chẩn đoán, không")
    print("      dùng kết luận (đã chứng minh phụ thuộc toán tử: 172→242→329 qua Δ)")
    print("  (c) CI95 half-width của det/frame ≤ 25 % của mean — nếu không: NHIỄU")
    print("  cụm_slice = CỜ CẢNH BÁO (chỉ báo khi ngoài [0,5×; 2,0×]), KHÔNG phải tiêu chí")
    print(f"KẾT QUẢ A3: {'PASS' if all(verdicts) else 'FAIL'}")


if __name__ == "__main__":
    main()
