Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đây là lượt tiếp của ticket 17. Lượt trước bạn đã dừng đúng lúc và hỏi PM chọn A/B/C cho hệ số bẹp.
**PM chốt B.** Ticket đã được cập nhật — đọc lại từ đầu:

  .scratch/spray-augmentation/issues/17-plume-geometry-from-measurement.md

## Chốt của PM (đã ghi trong ticket, mục Comments)

- Làm **phương án B**: hiệu chỉnh `S` bằng thực nghiệm để **median per-cluster** của `r_range/r_extent`
  = **1,28** (kỳ vọng `S ≈ 0,87`). Ghi **cả** 0,64 (giá trị suy ra giải tích) và `S` hiệu dụng vào
  docstring, kèm lý do lệch (điểm rời rạc làm `r_extent` hụt so với `R`).
- Lý do chọn B: ticket 16 đo **median của tỉ lệ từng cụm**, nên generator phải tái lập đúng thống kê đó,
  không phải công thức liên tục.
- **Bỏ** ngưỡng "số điểm/frame phải giảm" — sai hướng. Thay bằng bảng trước → sau theo kịch bản cố định
  3 box ở 12 / 22 / 38 m, 80 km/h, seed 0–4.
- Test (b) dùng **d = 4,0 m**, không dùng 5,0 m.
- Thứ tự thi công: **thay đổi 2 (bẹp) trước, thay đổi 1 (count theo cự ly) sau**, báo số sau mỗi bước.

## Ràng buộc cứng (giữ nguyên)

- **Không đổi** `cluster_radius_median_m` = 0,30. Không đổi ngưỡng 50 km/h, `clusters_at_speed_bounds`,
  vị trí đặt cụm, `max_injected_points`.
- Không thêm beam grid / ray casting / P_det / attenuation.
- Chỉ sửa: `spray/plume.py`, `tests/test_plume.py`, `docs/history/plume-model-provenance.md`.
- 33 test cũ phải còn xanh, không được sửa chúng. Tổng **≥ 35 passed**.
- Không sửa `docs/knowledge-base.html`.

## Commit

`feat(plume): range-dependent cluster density and radial thinning per ticket 16`
(body: `S` hiệu dụng, số điểm/frame trước → sau theo kịch bản cố định, tên 2 test mới)

## Báo lại

1. `S` hiệu dụng tìm được và cách kiểm (số cụm, seed, d)
2. median per-cluster `r_range/r_extent` sau khi sửa
3. median n_points ở d = 4,0 / 15 / 25 m sau khi sửa
4. bảng điểm/frame trước → sau theo 3 box × seed 0–4
5. output pytest