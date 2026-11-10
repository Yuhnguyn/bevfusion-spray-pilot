# 27: Bước 0 — wet ground (mặt đường ướt mất điểm phản xạ gương)

**Type:** task
**Status:** needs-triage
**Blocked by:** 26
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ

`[PAPER]` §III-A: "road spray does not occur without water on the pavement", dùng mô hình
wet ground của `[9]` = Hahner et al., LiDAR snowfall simulation, CVPR 2022.

**Có 2 nguồn, ưu tiên nguồn thứ 1:**
1. `[CODE]` **cùng file** `DetectionEnvironmentalEffects.cpp:305–380` (`simulate_wet_pavement`) —
   phương trình đầy đủ eq. 12–19: `n_air = 1,0003`, `n_w = 1,33`, `pavement_depth = 0,5 mm`,
   `gamma = clamp(wfh / 0,5 mm, 0, 1)`, `t_p`, `r_wp`, intensity `× 0,3`.
   Đây chính là mô hình paper trích dẫn ⇒ **port từ đây**, không phải suy từ Python.
2. `[ĐO]` repo `SysCV/LiDAR_snow_sim` có `tools/wet_ground/` (Python) — dùng để đối chiếu chéo,
   không phải nguồn chính.

Phạm vi áp dụng trong code gốc: chỉ điểm cách mặt đường **±0,2 m** và có `y` (ngang) trong
khoảng **(2, 7) m** — tức chỉ làm tối điểm đất ở làn bên cạnh, không làm tối toàn bộ mặt đường.
`[CHỌN]` v2 giữ đúng cửa sổ này, ghi config `wet_ground.y_window_m: [2, 7]`.

v1 bỏ bước này (ADR-0002). Đó là một phần lý do ticket 11 null: ta không đổi phân bố điểm
mặt đường, chỉ thêm điểm plume.

## Việc phải làm

1. Ghim commit của `SysCV/LiDAR_snow_sim` (ghi sha vào docstring), **không** vendor cả repo:
   copy 4 file vào `spray/third_party/wet_ground/` kèm LICENSE + ghi chú nguồn.
2. `spray/wet_ground.py` — hàm `apply_wet_ground(points, ctx, cfg)`:
   ước lượng ground plane, làm mất điểm theo phản xạ gương ướt; trả `(points, stats)` với
   `stats.removed`, `stats.ground_points_in`, `stats.pool_remaining`.
3. Config `wet_ground: {enabled: false, ...}` trong `plume_default.yaml`; **mặc định tắt** ở
   ticket này, bật ở ticket 29/31 để A/B tách đóng góp.
4. `tests/test_wet_ground.py` — 3 test: tắt → điểm không đổi; bật trên point cloud tổng hợp
   phẳng → chỉ mất điểm gần `z` mặt đất; điểm cao > 1 m không bị xoá.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` không giảm số test.
- [ ] Log marker `WET_GROUND_STATS removed=<n> ground_in=<n>`.
- [ ] Trên 1 frame thật: `removed > 0` khi bật, `removed == 0` khi tắt.
- [ ] Có LICENSE + sha nguồn trong `spray/third_party/wet_ground/NOTICE.md`.

## Cấm

- Không chỉnh sửa số liệu vật lý trong `phy_equations.py` của tác giả.
- Không bật mặc định trong ticket này.
