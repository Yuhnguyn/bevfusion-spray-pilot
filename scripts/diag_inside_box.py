"""Verify lỗi thứ 6: _inside_box dùng quy ước (w,l,h) nuScenes nhưng adapter ghi (l,w,h)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spray.plume import _inside_box

print("=" * 70)
print("_inside_box: box[3]=6.83 (dài), box[4]=2.42 (rộng) theo adapter")
print("nhưng code unpack: width, length = box[3], box[4]\n")

# box thật: dài 6.83 dọc yaw, rộng 2.42 ngang, yaw=0 (dọc trục x)
box = np.array([0.0, 0.0, -0.1, 6.83, 2.42, 2.62, 0.0, 0.0, 0.0], dtype=np.float32)

# điểm ở 2.0 m dọc trục x (TRONG box thật: dài 6.83 → nửa dài 3.4)
p_along = np.array([[2.0, 0.0, 0.5, 0.0, 0.0]], dtype=np.float32)
# điểm ở 2.0 m ngang trục y (NGOÀI box thật: rộng 2.42 → nửa rộng 1.21)
p_across = np.array([[0.0, 2.0, 0.5, 0.0, 0.0]], dtype=np.float32)

for name, p in [("dọc trục x, 2.0 m (TRONG box thật)", p_along),
                ("ngang trục y, 2.0 m (NGOÀI box thật)", p_across)]:
    inside = _inside_box(p, box, margin=0.0)
    print(f" {name}: _inside_box trả về {inside[0]}")

print("\n→ Nếu _inside_box nói điểm DỌC là ngoài và điểm NGANG là trong")
print("  thì nó đang dùng box 2.42 dài × 6.83 rộng — tức xoay 90°.")

print("\n" + "=" * 70)
print("Kiểm với box xoay yaw=90° (dài dọc trục y)")
box90 = np.array([0.0, 0.0, -0.1, 6.83, 2.42, 2.62, np.pi / 2, 0.0, 0.0],
                 dtype=np.float32)
p_along90 = np.array([[0.0, 2.0, 0.5, 0.0, 0.0]], dtype=np.float32)   # dọc yaw=90° → trục y
p_across90 = np.array([[2.0, 0.0, 0.5, 0.0, 0.0]], dtype=np.float32)  # ngang → trục x
for name, p in [("dọc yaw (trục y), 2.0 m — TRONG", p_along90),
                ("ngang yaw (trục x), 2.0 m — NGOÀI", p_across90)]:
    print(f" {name}: {_inside_box(p, box90, margin=0.0)[0]}")

print("\n" + "=" * 70)
print("Tác động thực: bao nhiêu điểm plume bị loại OAN / LỌT?")
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext  # noqa: E402
from spray.plume_state import PlumeState  # noqa: E402

cfg = PlumeConfig()
state = PlumeState()
bxs = np.array([[22.0, 0.0, -0.11, 6.83, 2.42, 2.62, 0.0, 27.8, 0.0]], dtype=np.float32)
pts = np.zeros((500, 5), dtype=np.float32)
for k in range(20):
    ctx = PlumeContext(scene_token="probe", frame_index=k, epoch=0,
                       sensor_origin=np.zeros(3), ego_speed_mps=27.8,
                       object_speed_mps=27.8, wfh_mm=1.0, road_z_m=-0.11)
    res = inject_plume_stateful(pts, bxs, ctx, state, seed=0, token="probe",
                                config=cfg, wet_ground=None)
print(f" sau 20 frame: injected={res.stats.injected} "
      f"rejected_box={res.stats.rejected_box} "
      f"rejected_range={res.stats.rejected_range} capped={res.stats.capped}")
print(f" alive={state.counters.alive}")
print("\n rejected_box cao = nhiều điểm bị loại vì 'nằm trong box' —")
print(" nhưng vùng loại đang là 2.42 dài × 6.83 rộng (xoay 90°).")
