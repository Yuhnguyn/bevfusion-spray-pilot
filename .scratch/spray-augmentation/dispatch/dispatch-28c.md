# 28c: sửa hệ quy chiếu của advection — state ở GROUND, render ở EGO

HEAD: df6ca8b  Nhánh: main
Skill: không

Ticket mẹ: `.scratch/spray-augmentation/issues/28-plume-volume-lifetime.md` §PM nghiệm thu 28b (đọc trước).

## Hiện trạng (PM đo, không suy đoán)

Probe của PM (`PYTHONPATH=. python -`, 110 frame, 1 box @23,2 m, `wfh = 1,0 mm`, ego = xe dẫn = 130 km/h):

```
PLUME_STATE scene=probe frame=109 spawned=24 alive=1781 expired=24 capped=6099 assumed=1
vệt dài (span theo x) = 7,3 m      # phải là v·T = 36,1 × 1,8 = 65 m
gap_x p50 = 0,002 m
```

**Nguyên nhân gốc:** `spray/plume_state.py:spawn()` đặt `vel = [v_rel, 0, vz]` với `v_rel = v_abs − ego_speed`.
Trong SemanticSpray/nuScenes eval, ego và xe dẫn thường **cùng tốc độ** ⇒ `v_rel = 0` ⇒ cụm khởi tạo đứng yên
trong hệ ego, drag chỉ tác động lên hiệu với gió 2 m/s ⇒ giọt không bao giờ trôi về phía sau ⇒ toàn bộ plume
dồn vào khối 7 m, trần `max_injected_points = 2000` cắt **6.099/8.099 = 75 %** mỗi frame.

**Sai ở đâu:** `[PAPER]` arXiv 2212.08558 nói rõ "the velocity of the moving object is **set as an initial
cluster velocity**", và code gốc `dee.cpp:397–426` cập nhật vận tốc trong hệ **world**, rồi chỉ **render** sang
hệ cảm biến (`transform_position_from_world_to_sensor_coordinates`, `dee.cpp:250`). Tức:

- cụm mang **vận tốc ground** (không phải vận tốc tương đối với ego);
- drag `drag·|v_air|²·v̂_air·Δt` tác động trong hệ ground, `v_air = v_ground − W`;
- ego chạy `v_ego` nên trong hệ ego cụm trôi ngược ~`v_abs` và vệt dài ~`v·T`.

## Việc phải làm

### 1. `spray/plume_state.py`

- `SprayCluster.vel` đổi nghĩa thành **vận tốc trong hệ ground** (m/s). Ghi rõ trong docstring.
- `spawn()`:
  - `v_ground = object_velocity_ego_mps + [ego_speed_mps, 0, 0]` nếu có vector;
  - nếu `object_velocity_ego_mps is None` ⇒ `v_ground = [object_speed_mps, 0, 0]` (vật chạy theo `+x` trong
    hệ ego tại thời điểm spawn) và đặt `velocity_assumed = True`;
  - cộng `v_z = 5·U(0,1)` như cũ.
- `advance(dt, ego_velocity=None)` — thêm tham số `ego_velocity: np.ndarray | None` (m/s, hệ ego; mặc định
  `[0,0,0]` để test cũ không vỡ):
  - `air = cluster.vel − W` (W = `wind_vector()`), `cluster.vel += drag·|air|²·âir·dt`;
  - **vị trí trong hệ ego**: `cluster.pos += (cluster.vel − ego_velocity)·dt`.
- `PlumeState.advance(dt, ego_velocity=None)` truyền tiếp; `ego_velocity` **không** lưu trong state, do caller
  truyền mỗi frame (28b đã có `context.ego_speed_mps` ⇒ `[ego_speed, 0, 0]`).

### 2. `spray/plume.py`

- Trong `inject_plume_stateful`: gọi `state.advance(dt, ego_velocity=np.array([context.ego_speed_mps, 0, 0]))`.
- Marker giữ nguyên 7 khoá (nếu thêm khoá thì cập nhật test tương ứng).

### 3. Không sửa gì khác

Không đổi `_POINTS_MEDIAN_BY_RANGE`, không đổi công thức `count`/`T`/drag/gió, không đổi trần
`max_injected_points`, không sửa YAML, không sửa `inject_plume()`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` **không giảm so với 213 passed, 4 skipped** (test cũ phải xanh; được thêm test mới).
- [ ] **Đo lại đúng 3 số này và in ra trong báo cáo** (probe 110 frame, 1 box @23,2 m, `wfh = 1,0 mm`):
      130 km/h → `span_x` **≥ 40 m** (kỳ vọng ~50–65 m), `alive` ≤ 600 sau khi lọc tầm, `capped` giảm mạnh
      so với 6.099;
      80 km/h → `span_x` **≥ 25 m** (`v·T = 22,2 × 0,8 = 17,8 m`, cộng đuôi phân bố), `capped` ≤ 2.000.
- [ ] Test mới: cụm vừa spawn ở 130 km/h có `|pos.x|` **giảm dần qua các frame** (trôi ngược trong hệ ego),
      ít nhất 3 frame liên tiếp, mức giảm mỗi frame > 0,5 m.
- [ ] `grep -c "ego_velocity" spray/plume_state.py spray/plume.py` > 0 ở cả hai.
- [ ] Chỉ đổi `spray/plume_state.py`, `spray/plume.py`, + file test. Không file nào khác.

## Cấm

- Không "sửa" bằng cách nới trần điểm, không đổi ngưỡng 50 km/h, không thêm sàn.
- Không đổi `PlumeContext` (đã có đủ `ego_speed_mps` và `object_velocity_ego_mps`).
- Không tự commit; PM nghiệm thu rồi commit.