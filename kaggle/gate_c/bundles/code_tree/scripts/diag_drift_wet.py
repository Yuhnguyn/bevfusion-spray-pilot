"""Chẩn đoán 5: (a) cụm sinh có trôi ngược không? (b) wet ground có tác dụng không?"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.wet_ground import WetGroundConfig, apply_wet_ground

print("=== (a) Cụm sinh có trôi ngược trong hệ ego? ===")
print("Kỳ vọng vật lý: cụm mất vận tốc do drag ⇒ tụt lùi ~1-2 m mỗi chu kỳ")
print("THẬT (đo được): spray tụt lùi 0.5-1.4 m/frame\n")

state = PlumeState()
cfg = PlumeConfig()
boxes = np.array([[22.0, 0.0, -0.2, 6.83, 2.42, 2.62, 0.0, 27.8, 0.0]], dtype=np.float32)
pts = np.zeros((500, 5), dtype=np.float32)

for k in range(20):
    ctx = PlumeContext(
        scene_token="probe", frame_index=k, epoch=0,
        sensor_origin=np.zeros(3), ego_speed_mps=27.8,
        object_speed_mps=27.8, wfh_mm=1.0, road_z_m=-1.6,
    )
    inject_plume_stateful(
        pts, boxes, ctx, state, seed=0, token="probe",
        config=cfg, wet_ground=None, vehicle_class="crafter",
    )
    alive = state.all_alive()
    if not alive:
        continue
    xs = np.array([c.pos[0] for c in alive])
    ages = np.array([c.age for c in alive])
    vels = np.array([np.linalg.norm(c.vel) for c in alive])
    print(
        f" frame={k:2d} alive={len(alive):3d} "
        f"x_min={xs.min():7.2f} x_p50={np.median(xs):7.2f} x_max={xs.max():7.2f} "
        f"|v|_p50={np.median(vels):5.2f} age_p50={np.median(ages):5.2f}"
    )

print("\n=== (b) Wet ground: attenuate hay boost? ===")
# mặt đường: điểm z thấp, xa ego
n = 2000
road = np.zeros((n, 5), dtype=np.float32)
road[:, 0] = np.linspace(5, 40, n)
road[:, 1] = np.random.default_rng(0).uniform(-8, 8, n)
road[:, 2] = -1.6
road[:, 3] = 40.0  # intensity trung bình

for enabled in (False, True):
    wg = WetGroundConfig(enabled=enabled)
    out, st = apply_wet_ground(road, road_z_m=-1.6, wfh_mm=1.0, config=wg)
    print(
        f" enabled={enabled}: points_in={st.points_in} "
        f"attenuated={st.attenuated} boosted={st.boosted} "
        f"mean_ratio={st.mean_ratio:.3f} "
        f"| intensity_p50={np.median(out[:,3]):.1f} (vào: 40.0)"
    )
