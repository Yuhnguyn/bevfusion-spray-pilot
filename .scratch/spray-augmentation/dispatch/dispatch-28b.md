# 28b: khối sau đuôi + nối state vào generator + marker + gap

HEAD: 43cf130  Nhánh: main
Skill: tdd — `/Users/huynguyen/.agents/skills/tdd` (1 skill duy nhất)

Đây là **nửa sau** của ticket 28 (`issues/28-plume-volume-lifetime.md`). Nửa đầu 28a đã xong (commit `43cf130`):
`spray/plume_state.py` có `SprayCluster`, `PlumeState`, `cluster_count_for_speed_abs`, `lifetime_mean_s`,
`wind_vector`; 7 test xanh. **Đọc file đó trước khi sửa.**

## Hiện trạng (PM đã kiểm)

- `spray/plume.py:187` — `inject_plume(points, boxes, *, seed, token="", config=None)`. Vùng sinh hiện tại
  tính inline trong khoảng dòng 230–270: tâm quanh **tâm box** + lệch ngẫu nhiên, cụm không có tuổi.
  Đo v1: gap dọc quỹ đạo p50 = **3,32 m**.
- `spray/plume.py:397` — `_inside_box(points, box, margin)` unpack `cx, cy, cz, width, length, height, yaw = box[:7]`
  rồi dùng `width/2` cho trục **dọc yaw** ⇒ **lỗi D6**: hộp khử xoay 90° so với xe thật
  (`docs/plume-v1-defects.md` §D6). Quy ước đúng theo dữ liệu thật: `size3D.x` = **chiều dài**, đo trên
  SemanticSpray `x = 6,83 m` vs `y = 2,42 m` (`docs/plume-v2-measurements.md` §4).
- `mit/bevfusion/tools/data_converter/nuscenes_converter.py:250` ghi `dims = b.wlh` ⇒ **9 cột** hiện hành là
  `(x, y, z, w, l, h, yaw, vx, vy)` với `w` = **ngang**, `l` = **dọc yaw**. Cùng file `:507` đổi `wlh → lhw`
  (chỗ khác) — repo không thống nhất; brief này **chốt một quy ước** như trên.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **207 passed, 4 skipped**.

## Số chính xác — chép đúng, cấm tự chỉnh

| Đại lượng | Giá trị | Nguồn |
|---|---|---|
| Khối phun | dài `|v_abs|·Δt` với `Δt = 0,1 s`; **rộng 3,4 m**; **cao 1,5 m**; hằng số, **không** lấy theo kích thước box | `[CODE]` `dee.cpp:571–591` |
| Tâm khối | `pos_box − (L_box/2 + L_khối/2)·[cos yaw, sin yaw]` (ra sau đuôi) | `[CODE]` |
| `z` khối | đáy khối = **đáy box** (`z_box − h_box/2`), nên `z_tâm = z_box − h_box/2 + 1,5/2` | `[CODE]` |
| Thứ tự mỗi chu kỳ | `advance(dt)` → `prune()` → `spawn()` | `[CODE]` |
| Số điểm mỗi cụm mỗi frame | dùng `_POINTS_MEDIAN_BY_RANGE` sẵn có (theo cự ly), **không đổi** | `[ĐO]` ticket 16 |
| Intensity điểm plume | **0** ở ticket này (ticket 30 mới gán ring/intensity) | `[CHỌN]` |

## Quyết định đã chốt

- `[CHỌN]` `wfh` tính **mm** cho `count` và `T` (commit `8c0ef3e`).
- `[CHỌN]` **hai tốc độ**: `count` + `T` dùng `v_abs`; vận tốc đầu + advection dùng **vector vận tốc tương đối**
  (commit `aae6ac1`). 28a đang gán cứng trục `+x` — 28b sửa bằng vector thật.

## Việc phải làm

### 1. `spray/plume_context.py` — thêm vector vận tốc

- Thêm trường optional `object_velocity_ego_mps: np.ndarray (3,) | None = None`: vận tốc của vật **trong hệ ego**
  (m/s). Validate shape + finite như các trường mảng khác.
- `from_sample()`: đọc `object_velocity_ego_mps` nếu có; không có ⇒ `None` (không tự bịa).
- Test cũ của 26 phải vẫn xanh (trường mới có default `None`).

### 2. `spray/plume_state.py` — nhận khối và vector

- `spawn(context, *, object_id, rng, dt, center=None, extents=None)`:
  - `center (3,)` + `extents (3,)` (nửa kích thước) của khối phun; nếu `None` giữ hành vi 28a (jitter quanh
    `sensor_origin`) để test 28a không vỡ.
  - vị trí cụm: `center + rng.uniform(-1, 1, 3) * extents`.
  - vận tốc đầu: nếu `context.object_velocity_ego_mps` có ⇒ `vel_xy = vector đó`; nếu `None` ⇒
    `[object_speed_mps − ego_speed_mps, 0, 0]` và đặt cờ `velocity_assumed = True` (để marker in ra).
  - `v_z = 5·U(0,1)` cộng thêm như cũ.
- `SprayCluster`: thêm `velocity_assumed: bool = False`.
- `probability()`: **clamp `min(1.0, exp(−age/ttl))`** — hiện trả `1,057` ở frame sinh vì `age = −0,1`.

### 3. `spray/plume.py` — đường mới, không phá đường cũ

- Thêm hàm **mới** `inject_plume_stateful(points, boxes, context, state, *, seed, token="", config=None, dt=0.1)`:
  - với mỗi box: `object_id = i`, tính khối phun theo bảng trên (dùng `l` cho chiều dài box, `yaw` cho hướng),
    rồi `state.spawn(...)`.
  - mỗi lần gọi: `advance(dt)` → `prune()` → `spawn()` (đúng thứ tự) — **một** lần cho cả frame, không lặp theo box.
  - materialize điểm: mỗi cụm còn sống phát `points_per_cluster` mẫu trong mặt cầu bán kính `cluster.radius`
    (dùng lại `_ball` + `_thin_radial`, `radial_squash` như cũ), mật độ theo cự ly `_POINTS_MEDIAN_BY_RANGE`,
    `intensity = 0`, cột ring = `-1` (chưa gán).
  - loại điểm nằm trong thân box bằng `_inside_box` (đã sửa quy ước), cộng vào `stats.rejected_box`.
  - trần `max_injected_points` giữ nguyên nhưng **đếm** `stats.capped` (v1 đã có trường này).
  - in **một** dòng marker mỗi lần gọi:
    `PLUME_STATE scene=<token> frame=<frame_index> spawned=<n> alive=<n> expired=<n> capped=<n> assumed=<0|1>`
- `inject_plume()` **giữ nguyên** (đường cũ, dùng cho test + lịch sử v1). Không đổi chữ ký.
- `_inside_box`: sửa quy ước — nửa trục **dọc yaw** = `length/2`, **ngang** = `width/2`, và ghi chú
  `# 9 cột: (x, y, z, w, l, h, yaw, vx, vy), w = ngang, l = dọc yaw — nuscenes_converter.py:250`.
- `PlumeTransform.__call__`: nếu có `plume_context` **và** `results` có `plume_state` (hoặc transform tự giữ
  một `PlumeState`) ⇒ gọi `inject_plume_stateful`; ngược lại đường cũ. Test cũ của 26 (so `np.array_equal`
  với `inject_plume`) phải vẫn xanh — đường không-context không được đổi.

### 4. `spray/plume.py` — config

- Thêm `water_film_height_mm: float = 1.0` (chỉ đường mới dùng), `tail_block_width_m: float = 3.4`,
  `tail_block_height_m: float = 1.5`.
- **Không** đổi `water_film_height_m` của đường cũ, không đổi các hằng 0,2/0,1/50/0,02/0,2/4/K/drag/gió.
- Không sửa `spray/config/plume_default.yaml` ở ticket này.

### 5. `tests/test_plume_tail_block.py` (file mới) — 6 test, viết **trước**

1. **Khối sau đuôi**: box `(x=23,2, y=0, z=0,899, w=2,42, l=6,83, h=2,62, yaw=0)`, `v_abs = 80 km/h`
   ⇒ khối dài `2,22 m`, rộng `3,4`, cao `1,5`; mọi cụm spawn nằm trong
   `x ∈ [23,2 − 3,415 − 2,22 ; 23,2 − 3,415]`, `|y| ≤ 1,7`, `z ∈ [0,899 − 1,31 ; 0,899 − 1,31 + 1,5]`.
2. **Vệt liên tục**: chạy 10 frame cùng scene, `alive` > 0 từ frame 2 trở đi (không có frame rỗng).
3. **Gap dọc quỹ đạo**: 10 frame @80 km/h, chiếu vị trí cụm lên trục chuyển động, gap giữa các cụm liên tiếp
   p50 **< 1,0 m** (v1: 3,32 m). In số p50 thật vào báo cáo.
4. **Không điểm nào trong thân box**: sau khi gọi, mọi điểm injected phải `_inside_box(...) == False`
   (tính lại bằng chính hàm đó), và `stats.rejected_box ≥ 0`.
5. **`P_t` ≤ 1**: cụm vừa spawn có `age = −dt` ⇒ `probability() ≤ 1.0`.
6. **Marker**: bắt stdout, đúng **1** dòng `PLUME_STATE`, có đủ 7 khoá `scene/frame/spawned/alive/expired/
   capped/assumed`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 213 passed, 4 skipped** (207 + 6), không skip mới. Nêu số thật.
- [ ] `git status` chỉ đổi 4 file: `spray/plume_context.py`, `spray/plume_state.py`, `spray/plume.py`,
      `tests/test_plume_tail_block.py` (mới). Không thêm file khác.
- [ ] `inject_plume()` không đổi chữ ký; test `test_without_context_matches_direct_inject_plume` vẫn xanh.
- [ ] Báo cáo nêu **đúng 4 số**: `alive` ở frame 10 @80 km/h, `expired` cộng dồn, `capped`, `gap p50`.
- [ ] `grep -c "PLUME_STATE" spray/plume.py` ≥ 1.
- [ ] Nếu sửa `_inside_box` làm test cũ fail: **báo tên test + số cũ/mới**, tuyệt đối không sửa số kỳ vọng.

## Cấm

- Không đổi `inject_plume()` (đường cũ), `PlumeConfig.water_film_height_m`, `_POINTS_MEDIAN_BY_RANGE`,
  `steady_state_cluster_factor`, các hằng của reference.
- Không sửa `spray/config/*.yaml`, `kaggle/`, `proxy_eval/`, `mit/`, `docs/`.
- Không dùng `time.time()`; không `os.environ`; không thêm dependency.
- Không tự commit; PM nghiệm thu rồi commit.