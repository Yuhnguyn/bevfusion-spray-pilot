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

from spray.beam_model import BeamTable, ELEVATION_MAX_DEG, ELEVATION_MIN_DEG
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.semantic_stats import ANGULAR_EPS_DEG, MIN_PTS, cluster_angular

WARMUP_FRAMES = 260
MEASURE_FRAMES = 60
SEEDS = 2
BIG_CLUSTER_POINTS = 50
BACKGROUND_POINTS = 30_000

# docs/measurements/sspp-cluster-size-distribution.md (Crafter, gộp 3 fold) —
# các số THẬT đều là detections của cảm biến nên so ở tầng raycast mới công bằng.
REAL = {
    50.0: {"points": 43, "clusters": 4.8, "p50": 6, "mean": 8.8, "p95": 17,
           "max": 144, "share_big": 15.0},
    100.0: {"points": 875, "clusters": 21.6, "p50": 6, "mean": 40.4, "p95": 182,
            "max": 2241, "share_big": 82.0},
    130.0: {"points": 592, "clusters": 13.1, "p50": 6, "mean": 45.3, "p95": 158,
            "max": 2485, "share_big": 83.0},
}


def vlp32c_table() -> BeamTable:
    """Bộ tia VLP-32C — copy y từ scripts/visualize_sspp_plume.py (nhánh smoke)."""
    elevation = np.linspace(ELEVATION_MIN_DEG, ELEVATION_MAX_DEG, 32,
                            dtype=np.float64)
    return BeamTable(elevation_deg=tuple(float(v) for v in elevation),
                     azimuth_step_deg=0.2)


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
                  radius_sigma: float = 0.8) -> dict:
    """Chạy tới trạng thái dừng; đo **tầng raycast** trên các frame đo.

    Chỉ raycast ở cửa sổ đo (state không phụ thuộc raycast) — 54 750 tia/frame
    nên đỡ được phần lớn thời gian ở 260 frame warming.
    """
    config = PlumeConfig()
    from spray.plume_state import PlumeStateConfig
    state = PlumeState(PlumeStateConfig(spawn_scale=spawn_scale,
                                        radius_sigma=radius_sigma))
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
    totals: list[int] = []
    for detections in frames:
        totals.append(int(detections.shape[0]))
        pos = detections[:, :3].astype(np.float64)
        if pos.shape[0] < MIN_PTS:
            continue
        labels = cluster_angular(pos, eps_deg=ANGULAR_EPS_DEG, min_pts=MIN_PTS)
        valid = labels[labels >= 0]
        if valid.size:
            flat_sizes.extend(int(v) for v in np.bincount(valid))
    array = np.asarray(flat_sizes, dtype=np.int64)
    big = array[array >= BIG_CLUSTER_POINTS]
    return {
        "detections_frame": float(np.mean(totals)),
        "n_cluster": float(array.size) / max(len(frames), 1),
        "p50": float(np.median(array)) if array.size else 0.0,
        "mean": float(array.mean()) if array.size else 0.0,
        "p95": float(np.percentile(array, 95)) if array.size else 0.0,
        "max": int(array.max()) if array.size else 0,
        "share_big": 100.0 * float(big.sum()) / max(float(array.sum()), 1e-9),
        "big_count": int(big.size),
    }


def main() -> None:
    import argparse as _argparse
    _ap = _argparse.ArgumentParser()
    _ap.add_argument("--spawn-scale", type=float, default=1.0)
    _ap.add_argument("--radius-sigma", type=float, default=0.8)
    _args = _ap.parse_args()
    table = vlp32c_table()
    header = (f"{'km/h':>5} {'det/frame':>10} {'cụm':>6} {'p50':>4} {'mean':>6} "
              f"{'p95':>5} {'max':>5} {'%≥50đ':>7} | thật (det, cụm, p50, p95, "
              "max, %≥50đ) | A3")
    print(header)
    verdicts = []
    for speed_kmh in sorted(REAL):
        runs = [measure_speed(speed_kmh, seed, table, _args.spawn_scale,
                              _args.radius_sigma)
                for seed in range(SEEDS)]
        got = {key: float(np.mean([run[key] for run in runs]))
               for key in runs[0]}
        real = REAL[speed_kmh]
        criteria = [
            abs(got["share_big"] - real["share_big"]) <= 10.0,
            0.5 * real["p95"] <= got["p95"] <= 2.0 * real["p95"],
            0.7 <= got["detections_frame"] / real["points"] <= 1.5,
        ]
        verdicts.append(all(criteria))
        mark = "PASS" if all(criteria) else "FAIL"
        which = ("đúng" if all(criteria) else "thiếu" if
                 got["detections_frame"] < real["points"] else "thừa")
        print(f"{speed_kmh:>5.0f} {got['detections_frame']:>10.0f} "
              f"{got['n_cluster']:>6.1f} {got['p50']:>4.0f} {got['mean']:>6.1f} "
              f"{got['p95']:>5.0f} {got['max']:>5.0f} {got['share_big']:>6.1f}% "
              f"| {real['points']:>4} đ, {real['clusters']:>5.1f}, {real['p50']}, "
              f"{real['p95']:>3}, {real['max']:>4}, {real['share_big']:>4.0f}% "
              f"-> {mark} ({which} det/frame)")
    print()
    print("TIÊU CHÍ A3 (đo ở tầng raycast = tầng detector thật sự thấy): "
          "|%điểm ≥50đ − thật| ≤ 10 điểm % · p95 ∈ [0,5×; 2×] · "
          "det/frame ∈ [0,7×; 1,5×] · cụm/frame không đổi.")
    print(f"KẾT QUẢ A3: {'PASS' if all(verdicts) else 'FAIL'}")


if __name__ == "__main__":
    main()
