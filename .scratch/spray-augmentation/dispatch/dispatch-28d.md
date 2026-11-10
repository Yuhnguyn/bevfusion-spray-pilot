# 28d: hằng cản `C = −0,15 m⁻¹` theo paper (bỏ phân bố N(−0,12; 0,04))

HEAD: 0b4b5b3  Nhánh: main
Skill: không

## Hiện trạng (PM đã kiểm)

- `spray/plume_state.py` dùng `DRAG_MEAN = -0.12`, `DRAG_STD = 0.04`, mỗi cụm bốc một giá trị
  `drag = N(−0,12; 0,04)`.
- Paper (arXiv 2212.08558, `[PAPER]`): hệ số cản là **hằng số `C = −0,15 m⁻¹`** trong phương trình
  `v_cl,k = C·(v_w + v_cl,k−1)²·Δt + v_cl,k−1`, `Δt = 100 ms`.
- Code gốc `dee.cpp:542` dùng `N(−0,12; 0,04)` — phân bố này không có trong paper.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **217 passed, 4 skipped**.

## Quyết định

`[CHỌN 2026-11-10 — user]` **Theo paper**: `C = −0,15 m⁻¹`, **hằng số**, không lấy mẫu.

## Việc phải làm

### 1. `spray/plume_state.py`

- `DRAG_MEAN = -0.15`, `DRAG_STD = 0.0`.
- Docstring: ghi `[PAPER]` arXiv 2212.08558 — `C = −0,15 m⁻¹`, đơn vị 1/m; nêu rõ code gốc dùng
  `N(−0,12; 0,04)` và ta **cố ý** theo paper.
- Giữ nguyên cấu trúc `PlumeStateConfig.drag_mean / drag_std` để sau này còn đổi được, nhưng mặc định là
  hằng số. Giữ nguyên công thức cập nhật `v += drag·|air|²·âir·Δt` và guard `drag > 0` (đã có).
- Không đổi gì khác: `count`, `T`, bán kính, gió 208°/2 m/s, `Δt = 0,1 s`, `age`, xoá `4T`.

### 2. Test

- Thêm 1 test: 20 cụm spawn liên tiếp có `cluster.drag == pytest.approx(-0.15)` **tất cả** (chứng minh hằng số,
  không lấy mẫu).
- Sửa test cũ nếu nó hard-code `−0,12`; nếu test cũ fail vì hằng số mới thì **báo tên test + số cũ/mới**,
  không tự đổi kỳ vọng ở chỗ khác.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 218 passed, 4 skipped**, nêu số thật.
- [ ] `grep -n "0.15" spray/plume_state.py` có kết quả; `grep -c "0.12" spray/plume_state.py` = 0
      (trừ khi còn trong comment ghi nguồn cũ — nếu vậy phải ghi rõ "code gốc dùng 0,12").
- [ ] Báo cáo nêu: `drag` của 5 cụm đầu tiên (phải đều −0,15) và `span_x` của probe 110 frame @130 km/h
      (`wfh = 1,0 mm`) — kỳ vọng **≤ 73,7 m** một chút vì cản mạnh hơn (PM đã đo 73,7 m với −0,12).
- [ ] Chỉ đổi `spray/plume_state.py` + file test.

## Cấm

- Không đổi `count`, `T`, bán kính, gió, `Δt`, `age`, `4T`, `max_injected_points`.
- Không đổi `PlumeContext`, `inject_plume*`, YAML.
- Không tự commit; PM nghiệm thu rồi commit.