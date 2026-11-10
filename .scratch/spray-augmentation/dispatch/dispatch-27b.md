# 27b: nối wet ground vào `inject_plume_stateful` (mặc định tắt)

HEAD: 6e7da47  Nhánh: main
Skill: không

## Hiện trạng (PM đã kiểm)

- `spray/wet_ground.py` (ticket 27a) có `apply_wet_ground(points, *, road_z_m, wfh_mm, config)` →
  `(points_out, WetGroundStats)`, in marker `WET_GROUND_STATS points_in=… attenuated=… boosted=… mean_ratio=…`,
  `WetGroundConfig.enabled = False` mặc định.
- `spray/plume.py::inject_plume_stateful(points, boxes, context, state, *, seed, token, config, dt)` trả
  `PlumeResult(points, points_clean, injected, stats)`; hiện **chưa** gọi wet ground.
- `spray/plume_transform.py::PlumeTransform.__init__(config, enabled, seed, **kwargs)` đang giữ `PlumeConfig`;
  `__call__` gọi `inject_plume_stateful` khi có `results["plume_context"]`.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **223 passed, 4 skipped**.

## Quy tắc phải giữ (quan trọng)

1. **`points_clean` KHÔNG bị wet ground sửa.** `points_clean` là đầu vào nhánh camera (đã chốt từ đầu dự án:
   camera branch luôn sạch). Wet ground chỉ sửa bản dùng cho nhánh LiDAR của arm có spray.
2. **Thứ tự:** wet ground trên mây điểm gốc **trước**, rồi mới cộng plume.
3. **Mặc định tắt**, và khi tắt thì hành vi **giống hệt** hiện tại, không in marker `WET_GROUND_STATS`
   (log eval không bị nhiễu).
4. Không đổi `inject_plume()` (đường cũ), không đổi `spray/wet_ground.py`.

## Việc phải làm

### 1. `spray/plume.py`

- `inject_plume_stateful(..., wet_ground=None)` — tham số keyword-only kiểu `WetGroundConfig | None`
  (import từ `spray.wet_ground`; giữ import cục bộ nếu cần tránh vòng lặp import).
- Trong hàm, ngay sau `clean = _as_five_columns(points)`:
  - nếu `wet_ground is not None and wet_ground.enabled` ⇒
    `base, wet_stats = apply_wet_ground(clean, road_z_m=context.road_z_m, wfh_mm=context.wfh_mm, config=wet_ground)`;
  - ngược lại `base = clean`.
- Dùng `base` làm nền để cộng plume (`np.concatenate([base, injected])`), **`points_clean` vẫn là
  `clean.copy()` như cũ**.
- Marker `PLUME_STATE` giữ nguyên 7 khoá; **không** thêm khoá mới (test cũ đang bắt đúng 7 khoá).
- Nếu `wet_ground` bật: cộng số liệu wet ground vào `PlumeStats` bằng 2 field mới
  `wet_points_in: int = 0`, `wet_mean_ratio: float = 0.0` (mặc định 0, không ảnh hưởng đường cũ).

### 2. `spray/plume_transform.py`

- `__init__(..., wet_ground=None)` — nhận `WetGroundConfig | None`, lưu `self.wet_ground`.
- Truyền `wet_ground=self.wet_ground` khi gọi `inject_plume_stateful`. **Không** truyền cho `inject_plume`
  (đường cũ giữ nguyên).

### 3. `tests/test_plume_wet_integration.py` (file mới) — 4 test

1. `wet_ground=None` ⇒ `points`, `points_clean`, `injected`, `stats` **giống hệt** gọi không có tham số
   (`np.array_equal` trên cả ba mảng, `stats.injected` bằng nhau).
2. Bật wet ground với mây điểm **toàn điểm cao** (z = 5 m, không điểm nào trong dải mặt đường) ⇒
   `points` bằng hệt input (`array_equal`), `stats.wet_points_in == 0`.
3. Bật wet ground với mây điểm có điểm mặt đường trong cửa sổ `y ∈ (2,7)`:
   **`points_clean` giữ intensity gốc**, còn `points` (nền) có intensity **giảm** ở đúng điểm đó.
4. Marker: khi bật → stdout có **đúng 1** dòng `WET_GROUND_STATS`; khi tắt → **0** dòng
   (dùng `capsys`).

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 227 passed, 4 skipped**, nêu số thật.
- [ ] `git status` chỉ đổi: `spray/plume.py`, `spray/plume_transform.py`, `tests/test_plume_wet_integration.py` (mới).
- [ ] `git diff spray/wet_ground.py` **rỗng**.
- [ ] Marker `PLUME_STATE` vẫn đúng 7 khoá (test cũ xanh).
- [ ] Báo cáo nêu: `wet_points_in` và `wet_mean_ratio` của test 3.

## Cấm

- Không sửa `points_clean` bằng wet ground; không đổi thứ tự advance→prune→spawn.
- Không bật mặc định; không sửa `wet_ground_default.yaml`, `plume_default.yaml`.
- Không đổi `inject_plume()`, `PlumeContext`, `plume_state.py`.
- Không tự commit; PM nghiệm thu rồi commit.