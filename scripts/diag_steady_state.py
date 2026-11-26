"""Chẩn đoán 7: plume có đạt trạng thái dừng trong độ dài scene SSPP không?

So: 4T (tuổi thọ tối đa) vs độ dài scene (số frame × 0,1 s).
Chạy dài tới 120 frame để xem alive hội tụ về đâu.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.plume import (
    PlumeConfig,
    cluster_rate_for_speed,
    cluster_visible_target_for_speed,
    lifetime_time_constant,
    steady_state_cluster_factor,
)
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState

print("=== (a) Tuổi thọ tối đa 4T vs độ dài scene ===")
print("scene SSPP: 53-67 frame = 5.3-6.7 s\n")
print(" v(km/h) |  T(s) | 4T(s) | 4T/dt | scene 53f | scene 67f | đạt dừng?")
for v in (50, 60, 80, 100, 120, 130):
    T = lifetime_time_constant(v, PlumeConfig())
    max_age = 4 * T
    need = int(max_age / 0.1)
    ok53 = "CÓ" if need <= 53 else f"KHÔNG (cần {need})"
    ok67 = "CÓ" if need <= 67 else f"KHÔNG (cần {need})"
    print(f" {v:7d} | {T:5.2f} | {max_age:5.2f} | {need:6d} | {ok53:>9} | {ok67:>9} |")

print("\n=== (b) alive hội tụ về đâu (chạy 120 frame) ===")
cfg = PlumeConfig()
for v_kmh in (60, 100, 120):
    v = v_kmh / 3.6
    state = PlumeState()
    boxes = np.array([[22.0, 0.0, -0.2, 6.83, 2.42, 2.62, 0.0, v, 0.0]], dtype=np.float32)
    pts = np.zeros((500, 5), dtype=np.float32)
    marks = {}
    for k in range(120):
        ctx = PlumeContext(
            scene_token="probe", frame_index=k, epoch=0,
            sensor_origin=np.zeros(3), ego_speed_mps=v,
            object_speed_mps=v, wfh_mm=1.0, road_z_m=-1.6,
        )
        from spray.plume import inject_plume_stateful
        inject_plume_stateful(
            pts, boxes, ctx, state, seed=97 + k, token=f"probe/{k}",
            config=cfg, wet_ground=None, vehicle_class="crafter",
        )
        if k in (24, 32, 52, 66, 119):
            marks[k] = (state.counters.alive, state.counters.expired)
    target = cluster_visible_target_for_speed(v_kmh, "crafter")
    rate = cluster_rate_for_speed(v_kmh, cfg, "crafter")
    K = steady_state_cluster_factor(v_kmh, cfg)
    print(f"\n v={v_kmh} km/h: bảng đích visible={target:.1f}, rate={rate:.2f}, K={K:.2f}")
    print(f"   rate×K = {rate*K:.1f} (phải ≈ visible)")
    for k, (alive, exp) in marks.items():
        print(f"   frame {k:3d}: alive={alive:3d} expired={exp}")
