# Plume geometry vs range on SemanticSpray

Sinh bởi `scripts/semantic_spray_stats.py` (ticket 16). Chỉ đo hình học
plume thật; **không sửa generator**. Số đo gắn nhãn `[ĐO]`; tham chiếu
generator gắn nhãn `[CODE]`.

## Sample

- label: `base-207x10`
- lệnh: `python scripts/semantic_spray_stats.py --label base-207x10`
- cờ: `--groups= --scene-offset=0 --scene-stride=1 --scenes=0 --frames-per-scene=10 --radius=0.5 --dense-min=5`
- scenes: **207** (Crafter_dynamic=108, Golf_dynamic=99)
- frames đã đọc: **2070**
- frames có noise label: **2034**
- noise points: **873457**
- clusters: **35305** (mọi kích thước), **11607** dense (>= 5 điểm)
- clustering: single-linkage trên `(x, y)`, radius **0.5 m** (giữ nguyên như `docs/measurements/semantic-spray-stats.md`)

## Định nghĩa đo

- `d_sensor`: `‖centroid‖` (norm 3D trong LiDAR frame).
- `n_points`: số điểm trong cluster.
- `r_extent`: `max ‖p − centroid‖` — bán kính ngoài của cluster.
- `r_range`: `max ‖p‖ − min ‖p‖` — độ dày theo phương bán kính.
- `n_rings`: số giá trị `ring` khác nhau trong cluster.
- `ring_span`: `max(ring) − min(ring)`.
- Bucket: `[low, high)`, bucket cuối là `>50 m`.
- Ngưỡng kết luận: bucket có **< 30 dense clusters** thì ghi `quá ít, không kết luận`.

## Bảng 1 — Số điểm mỗi cluster theo cự ly `[ĐO]`

| bucket (m) | n_clusters | median n_points | p25 | p75 |
|---|---:|---:|---:|---:|
| 0–5 | 2342 | 30.0 | 13.0 | 129.0 |
| 5–10 | 2964 | 20.0 | 9.0 | 87.0 |
| 10–20 | 5045 | 14.0 | 7.0 | 43.0 |
| 20–30 | 1170 | 10.0 | 6.0 | 19.0 |
| 30–50 | 86 | 10.0 | 6.0 | 15.8 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

## Bảng 2 — Hình học bán kính theo cự ly `[ĐO]`

Tham chiếu generator `[CODE]`: `cluster_radius_median_m = 0.30 m`.

| bucket (m) | n_clusters | median r_extent (m) | median r_range (m) | median r_range/r_extent | n (ratio) |
|---|---:|---:|---:|---:|---:|
| 0–5 | 2342 | 0.594 | 0.445 | 1.106 | 2342 |
| 5–10 | 2964 | 0.887 | 1.002 | 1.346 | 2964 |
| 10–20 | 5045 | 0.813 | 0.966 | 1.306 | 5045 |
| 20–30 | 1170 | 0.660 | 0.795 | 1.226 | 1170 |
| 30–50 | 86 | 0.712 | 0.525 | 0.724 | 86 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

## Bảng 3 — Cấu trúc vòng quét theo cự ly `[ĐO]`

| bucket (m) | n_clusters | median n_rings | p25 | p75 | median ring_span |
|---|---:|---:|---:|---:|---:|
| 0–5 | 2342 | 1.0 | 1.0 | 2.0 | 0 |
| 5–10 | 2964 | 4.0 | 2.0 | 11.0 | 5 |
| 10–20 | 5045 | 4.0 | 2.0 | 8.0 | 5 |
| 20–30 | 1170 | 4.0 | 2.0 | 5.0 | 3 |
| 30–50 | 86 | 2.0 | 1.0 | 4.0 | 1 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

Toàn bộ **11607** dense clusters (mọi cự ly): median `n_points` = 17.0, median `r_extent` = 0.755 m, median `r_range` = 0.862 m, median `r_range/r_extent` = 1.280 (n=11607), median `n_rings` = 3.0, median `ring_span` = 3 `[ĐO]`.

## Kết luận bằng số

- `median n_points` giảm từ 30.0 (0–5 m, n=2342) xuống 10.0 (20–30 m, n=1170), tỉ lệ 3.0× `[ĐO]`.
- `median r_range/r_extent` ở 0–5 m là 1.106 (n=2342): độ dày bán kính là 1.106 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 5–10 m là 1.346 (n=2964): độ dày bán kính là 1.346 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 10–20 m là 1.306 (n=5045): độ dày bán kính là 1.306 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 20–30 m là 1.226 (n=1170): độ dày bán kính là 1.226 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 30–50 m là 0.724 (n=86): độ dày bán kính là 0.724 lần bán kính ngoài `[ĐO]`.
- `median r_extent` ở 0–5 m là 0.594 m (n=2342) `[ĐO]`, tức 1.98× giá trị cấu hình `cluster_radius_median_m = 0.30 m` `[CODE]`.
- `median n_rings` ở 0–5 m là 1.0 (p25 1.0, p75 2.0, n=2342), `median ring_span` 0 `[ĐO]`.
- `median n_rings` ở 5–10 m là 4.0 (p25 2.0, p75 11.0, n=2964), `median ring_span` 5 `[ĐO]`.
- `median n_rings` ở 10–20 m là 4.0 (p25 2.0, p75 8.0, n=5045), `median ring_span` 5 `[ĐO]`.
- `median n_rings` ở 20–30 m là 4.0 (p25 2.0, p75 5.0, n=1170), `median ring_span` 3 `[ĐO]`.
- `median n_rings` ở 30–50 m là 2.0 (p25 1.0, p75 4.0, n=86), `median ring_span` 1 `[ĐO]`.

## Caveats

- Label `2` của SemanticSpray là *noise*, gồm spray và các nguồn nhiễu
  khác. Chỉ dense cluster (>= 5 điểm) được đo hình học.
- Single-linkage trên `(x, y)` nối các điểm cách nhau <= radius, nên một
  cluster có thể bị nối chuỗi. `r_extent` và `r_range` vì vậy là cận trên
  của hình học plume đơn lẻ; `n_rings` cũng bị ảnh hưởng cùng chiều.
- `d_sensor` là norm 3D của centroid, không phải khoảng cách ngang
  (`hypot(x, y)`) đã dùng trong `docs/measurements/semantic-spray-stats.md`.
- Script chỉ đo, không đề xuất hay sửa tham số generator (ticket 17).
