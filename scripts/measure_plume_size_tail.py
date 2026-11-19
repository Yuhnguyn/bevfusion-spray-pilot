"""Đo **đuôi phân bố điểm/cụm của plume sinh ra** và so với spray thật.

Đây là dụng cụ **chấp nhận A3**: chạy generator ở trạng thái dừng, lấy các điểm
spray được chèn (`PlumeResult.injected`), gom cụm bằng **đúng toán tử đã dùng
cho dữ liệu thật** (`spray.semantic_stats.cluster_angular`: DBSCAN trên
`(azimuth, elevation)`, `eps = 0,7°`, `minPts = 3`), rồi so bốn đại lượng với
bảng thật trong `docs/measurements/sspp-cluster-size-distribution.md`:

* `điểm/frame`
* `điểm/cụm` p50 (thật: 5–7 ở mọi tốc độ)
* `điểm/cụm` p95 (thật: 17 / 182 / 158 ở 50 / 100 / 130 km/h)
* **`% điểm nằm trong cụm ≥ 50 điểm`** (thật: 15 % / 82 % / 83 %) ← tiêu chí chính

Vì sao `% điểm trong cụm ≥50` là tiêu chí chính: phân bố thật **hai đỉnh** —
rất nhiều cụm nhỏ (p50 = 5–7 điểm, generator đã khớp) + một ít chuỗi khổng lồ giữ
phần lớn khối lượng điểm. Nếu chỉ nhìn `điểm/frame` thì không phân biệt được
"thiếu chuỗi" với "mọi cụm nhỏ đi".

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/measure_plume_size_tail.py
"""

from __future__ import annotations

import contextlib
import io

import numpy as np

from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.semantic_stats import ANGULAR_EPS_DEG, MIN_PTS, cluster_angular

DT = 0.1
# Cloud nền ~30k điểm như frame SSPP thật: `_injected_budget` = 5 % số điểm
# thật (tối thiểu 500), nên truyền cloud rỗng sẽ cap plume ở 500 điểm và đo sai.
BACKGROUND_POINTS = 30_000
WARMUP_FRAMES = 260
MEASURE_FRAMES = 60
SEEDS = 2
BIG_CLUSTER_POINTS = 50

# docs/measurements/sspp-cluster-size-distribution.md (Crafter, gộp 3 fold).
REAL = {
    50.0: {"points": 43, "p50": 6, "mean": 8.8, "p95": 17, "max": 144,
           "share_big": 15.0},
    100.0: {"points": 875, "p50": 6, "mean": 40.4, "p95": 182, "max": 2241,
            "share_big": 82.0},
    130.0: {"points": 592, "p50": 6, "mean": 45.3, "p95": 158, "max": 2485,
            "share_big": 83.0},
}


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


def measure_speed(speed_kmh: float, seed: int) -> dict:
    """Chạy tới trạng thái dừng rồi đo đuôi phân bố của các frame đo."""
    config = PlumeConfig()
    state = PlumeState()
    speed_mps = speed_kmh / 3.6
    # Box theo quy ước adapter: box[2] = ĐÁY hộp, box[3] = dài, box[4] = rộng.
    box = np.array([[20.0, 0.0, -1.6, 4.5, 1.9, 1.5, 0.0, speed_mps, 0.0]],
                   dtype=np.float64)
    background = np.zeros((BACKGROUND_POINTS, 5), dtype=np.float32)
    background[:, 0] = np.random.default_rng(seed).uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 1] = np.random.default_rng(seed + 1).uniform(-27, 27, BACKGROUND_POINTS)
    background[:, 2] = -1.6
    frames: list[dict] = []
    capped = 0
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
            capped += result.stats.capped
            if index < WARMUP_FRAMES:
                continue
            spray = result.injected[:, :3].astype(np.float64)
            if spray.shape[0] < MIN_PTS:
                frames.append({"points": int(spray.shape[0]), "sizes": [],
                               "unclustered": int(spray.shape[0])})
                continue
            labels = cluster_angular(spray, eps_deg=ANGULAR_EPS_DEG,
                                     min_pts=MIN_PTS)
            valid = labels[labels >= 0]
            sizes = [int(value) for value in np.bincount(valid)] \
                if valid.size else []
            frames.append({"points": int(spray.shape[0]), "sizes": sizes,
                           "unclustered": int((labels < 0).sum())})
    flat = np.array([size for frame in frames for size in frame["sizes"]],
                    dtype=np.int64)
    totals = np.array([frame["points"] for frame in frames], dtype=np.int64)
    if flat.size == 0:
        return {"capped": float(capped), "points": float(totals.mean()), "n_cluster": 0.0,
                "p50": 0.0, "mean": 0.0, "p95": 0.0, "max": 0,
                "share_big": 0.0, "clusters_per_frame": 0.0,
                "unclustered_share": 100.0}
    big = flat[flat >= BIG_CLUSTER_POINTS]
    unclustered = float(np.mean([frame["unclustered"] for frame in frames]))
    return {
        "capped": float(capped),
        "points": float(totals.mean()),
        "n_cluster": float(flat.size) / len(frames),
        "p50": float(np.median(flat)),
        "mean": float(flat.mean()),
        "p95": float(np.percentile(flat, 95)),
        "max": int(flat.max()),
        "share_big": 100.0 * float(big.sum()) / float(flat.sum()),
        "clusters_per_frame": float(flat.size) / len(frames),
        "unclustered_share": 100.0 * unclustered / max(float(totals.mean()), 1e-9),
    }


def main() -> None:
    print(f"{'km/h':>5} {'điểm/frame':>11} {'cụm/frame':>10} {'p50':>5} {'mean':>6} "
          f"{'p95':>5} {'max':>5} {'%điểm≥50đ':>10} {'%lẻ':>6} | so với thật")
    verdicts = []
    for speed_kmh in sorted(REAL):
        runs = [measure_speed(speed_kmh, seed) for seed in range(SEEDS)]
        merged = {key: float(np.mean([run[key] for run in runs]))
                  for key in ("points", "p50", "mean", "p95", "max",
                              "share_big", "clusters_per_frame", "capped",
                              "unclustered_share")}
        real = REAL[speed_kmh]
        share_gap = merged["share_big"] - real["share_big"]
        criteria = [
            abs(share_gap) <= 10.0,
            real["p95"] * 0.5 <= merged["p95"] <= real["p95"] * 2.0,
        ]
        verdicts.append(all(criteria))
        status = "PASS" if all(criteria) else "FAIL"
        print(f"{speed_kmh:>5.0f} {merged['points']:>11.0f} "
              f"{merged['clusters_per_frame']:>10.1f} {merged['p50']:>5.0f} "
              f"{merged['mean']:>6.1f} {merged['p95']:>5.0f} {merged['max']:>5.0f} "
              f"{merged['share_big']:>9.1f}% {merged['unclustered_share']:>5.1f}% | thật {real['points']:>4} điểm, "
              f"p95 {real['p95']:>3}, ≥50đ {real['share_big']:>4.0f}% -> {status} "
              f"(capped {merged['capped']:.0f})")
    print()
    print("TIÊU CHÍ A3: |%điểm trong cụm ≥50đ − thật| ≤ 10 điểm % VÀ p95 trong "
          "[0,5×; 2×] thật, với cụm/frame không đổi.")
    print(f"KẾT QUẢ A3: {'PASS' if all(verdicts) else 'FAIL'}")


if __name__ == "__main__":
    main()
