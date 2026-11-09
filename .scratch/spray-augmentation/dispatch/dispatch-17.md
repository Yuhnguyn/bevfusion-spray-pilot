Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. .scratch/spray-augmentation/STATUS.md
2. .scratch/spray-augmentation/issues/17-plume-geometry-from-measurement.md  ← ticket, nguồn đúng
3. docs/plume-geometry-vs-real.md  ← số đo mà ticket dựa vào

## Nhiệm vụ

Làm trọn ticket 17: sửa `spray/plume.py` theo đúng **3 thay đổi** trong ticket (count phụ thuộc cự ly;
bẹp 0,64 theo phương bán kính; KHÔNG đổi bán kính 0,30). Thêm ≥2 test. Cập nhật provenance doc.

## Ràng buộc cứng — sai là trả lại bài

- **Không đổi** `cluster_radius_median_m` (giữ 0,30). Số đo 0,755 m là cận trên do single-linkage
  chaining; paper Fig. 5 = 0,30. Ghi lý do vào docstring.
- **Không đổi** ngưỡng 50 km/h, `clusters_at_speed_bounds`, vị trí đặt cụm, `max_injected_points`.
- **Không** thêm beam grid / ray casting / P_det / attenuation. Chỉ 3 thay đổi trong ticket.
- Số điểm/frame **sẽ giảm** — đây là thay đổi có chủ ý. KHÔNG áp ngưỡng "lệch ≤10%". Nhưng phải ghi
  số trước/sau (cùng frame, cùng seed) vào commit message.
- Nếu bạn cho rằng spec sai hoặc phải đổi thêm tham số khác: **DỪNG**, báo PM kèm số.
- Không sửa `docs/knowledge-base.html` (PM sẽ cho sửa sau).

## Test

- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥ 35 passed**
  (baseline hiện tại **33**; 33 test cũ phải vẫn xanh, không được sửa chúng để dễ qua).
- Hai test mới phải kiểm đúng thứ ticket ghi: (a) `r_range/r_extent` ∈ [1,15; 1,40];
  (b) median n_points ở ~5/15/25 m khớp bảng trong ±20%.

## Commit

`feat(plume): range-dependent cluster density and radial thinning per ticket 16`
(kèm 2 dòng trong commit body: số điểm/frame trước → sau, và 2 tên test mới)

## Báo lại (ngắn)

1. số điểm/frame trước → sau (cùng frame, cùng seed), và giải thích giảm vì đâu
2. `r_range/r_extent` đo được sau khi sửa (tự tính từ điểm sinh ra, đưa số)
3. median n_points ở ~5/15/25 m sau khi sửa
4. danh sách test mới + output pytest
5. chỗ nào trong ticket bạn thấy mơ hồ