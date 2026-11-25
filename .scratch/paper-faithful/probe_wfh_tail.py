"""Probe: wfh (mức nước) có điều khiển độ dài đuôi plume không?

Nếu có, thì hiệu chuẩn phải nhắm vào `wfh`/`T`, không phải `spawn_scale` —
vì hai đại lượng đó điều khiển hai thuộc tính khác nhau (số cụm vs độ dài đuôi).

Kịch bản: static, ego đứng yên, xe ở ~25 m, chạy ra xa. Đo quantile của depth
sau mặt đuôi. So với RoadSpray thật cùng dải car_range.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import raycast_frame  # noqa: E402

ROAD_Z = -1.6
VEH_LEN = 6.829
DT = 0.1


def context(speed_kmh: float, frame: int, wfh_mm: float) -> PlumeContext:
    v = speed_kmh / 3.6
    return PlumeContext(
        scene_token="probe", frame_index=frame, epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=0.0, object_speed_mps=v,
        object_velocity_ego_mps=np.array([v, 0.0, 0.0]),
        wfh_mm=wfh_mm, road_z_m=ROAD_Z,
    )


def box_at(x: float) -> np.ndarray:
    return np.array([[x, 0.0, ROAD_Z + 2.621 / 2, VEH_LEN, 2.419, 2.621, 0, 0, 0]],
                    dtype=np.float32)


def run(speed_kmh: float, wfh_mm: float, seed: int = 7,
        frames: int = 45) -> np.ndarray:
    rng = np.random.default_rng(seed)
    background = np.zeros((4000, 5), dtype=np.float32)
    background[:, 0] = rng.uniform(-27, 27, 4000)
    background[:, 1] = rng.uniform(-27, 27, 4000)
    background[:, 2] = ROAD_Z
    table = load_beam_table()
    state = PlumeState(PlumeStateConfig())
    depths: list[np.ndarray] = []
    start_x = 24.0
    step = speed_kmh / 3.6 * DT
    for i in range(frames):
        car_x = start_x + step * i
        res = inject_plume_stateful(
            background, box_at(car_x), context(speed_kmh, i, wfh_mm), state,
            seed=seed * 100_000 + i, token=f"probe/{i}")
        ray = raycast_frame(res.points, state.all_alive(), table=table,
                            road_z_m=ROAD_Z,
                            rng=np.random.default_rng(seed * 777 + i))
        det = ray.detections
        if len(det):
            rear = car_x - VEH_LEN / 2.0
            depths.append(rear - det[:, 0].astype(np.float64))
    if not depths:
        return np.zeros(0)
    return np.concatenate(depths)


def quant(v: np.ndarray, q: float) -> float:
    return float(np.percentile(v, q)) if v.size else float("nan")


def main() -> None:
    print("Đuôi plume (depth sau mặt đuôi, m) — p50/p90/p95/p99 + n_det/frame\n")
    print(f"{'km/h':>5} {'wfh':>6} {'n/fr':>7} {'p50':>7} {'p90':>7} "
          f"{'p95':>7} {'p99':>7}")
    print("-" * 52)
    for speed in (100, 130):
        for wfh in (0.3, 0.7, 1.0, 1.2):
            d = run(speed, wfh)
            print(f"{speed:>5} {wfh:>6.1f} {d.size / 45:>7.0f} "
                  f"{quant(d, 50):>7.1f} {quant(d, 90):>7.1f} "
                  f"{quant(d, 95):>7.1f} {quant(d, 99):>7.1f}")
        print()
    print("Đích RoadSpray thật (dải car [20,40)): "
          "100 km/h p50 17,5 p95 26,5 | 130 km/h p50 20,5 p95 29,5")


if __name__ == "__main__":
    main()
