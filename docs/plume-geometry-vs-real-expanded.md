# Plume geometry vs range on SemanticSpray

Sinh bởi `scripts/semantic_spray_stats.py` (ticket 16). Chỉ đo hình học
plume thật; **không sửa generator**. Số đo gắn nhãn `[ĐO]`; tham chiếu
generator gắn nhãn `[CODE]`.

## Sample

- label: `expanded-207x20`
- lệnh: `python scripts/semantic_spray_stats.py --frames-per-scene 20 --label expanded-207x20 --geometry-out docs/plume-geometry-vs-real-expanded.md`
- cờ: `--groups= --scene-offset=0 --scene-stride=1 --scenes=0 --frames-per-scene=20 --radius=0.5 --dense-min=5`
- scenes: **207** (Crafter_dynamic=108, Golf_dynamic=99)
- frames đã đọc: **4140**
- frames có noise label: **4072**
- noise points: **1845175**
- clusters: **73048** (mọi kích thước), **23989** dense (>= 5 điểm)
- clustering: single-linkage trên `(x, y)`, radius **0.5 m** (giữ nguyên như `docs/semantic-spray-stats.md`)

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
| 0–5 | 4740 | 32.0 | 13.0 | 130.0 |
| 5–10 | 6254 | 19.0 | 8.0 | 90.0 |
| 10–20 | 10416 | 15.0 | 7.0 | 42.0 |
| 20–30 | 2412 | 10.0 | 6.0 | 19.0 |
| 30–50 | 167 | 10.0 | 6.0 | 16.5 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

## Bảng 2 — Hình học bán kính theo cự ly `[ĐO]`

Tham chiếu generator `[CODE]`: `cluster_radius_median_m = 0.30 m`.

| bucket (m) | n_clusters | median r_extent (m) | median r_range (m) | median r_range/r_extent | n (ratio) |
|---|---:|---:|---:|---:|---:|
| 0–5 | 4740 | 0.596 | 0.462 | 1.128 | 4740 |
| 5–10 | 6254 | 0.921 | 0.983 | 1.353 | 6254 |
| 10–20 | 10416 | 0.829 | 0.975 | 1.316 | 10416 |
| 20–30 | 2412 | 0.680 | 0.833 | 1.270 | 2412 |
| 30–50 | 167 | 0.643 | 0.429 | 0.637 | 167 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

## Bảng 3 — Cấu trúc vòng quét theo cự ly `[ĐO]`

| bucket (m) | n_clusters | median n_rings | p25 | p75 | median ring_span |
|---|---:|---:|---:|---:|---:|
| 0–5 | 4740 | 1.0 | 1.0 | 2.0 | 0 |
| 5–10 | 6254 | 4.0 | 2.0 | 11.0 | 6 |
| 10–20 | 10416 | 4.0 | 2.0 | 8.0 | 5 |
| 20–30 | 2412 | 4.0 | 2.0 | 6.0 | 3 |
| 30–50 | 167 | 2.0 | 1.0 | 3.0 | 1 |
| >50 | 0 | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận | quá ít, không kết luận |

Toàn bộ **23989** dense clusters (mọi cự ly): median `n_points` = 17.0, median `r_extent` = 0.768 m, median `r_range` = 0.877 m, median `r_range/r_extent` = 1.294 (n=23989), median `n_rings` = 3.0, median `ring_span` = 3 `[ĐO]`.

## Kết luận bằng số

- `median n_points` giảm từ 32.0 (0–5 m, n=4740) xuống 10.0 (20–30 m, n=2412), tỉ lệ 3.2× `[ĐO]`.
- `median r_range/r_extent` ở 0–5 m là 1.128 (n=4740): độ dày bán kính là 1.128 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 5–10 m là 1.353 (n=6254): độ dày bán kính là 1.353 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 10–20 m là 1.316 (n=10416): độ dày bán kính là 1.316 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 20–30 m là 1.270 (n=2412): độ dày bán kính là 1.270 lần bán kính ngoài `[ĐO]`.
- `median r_range/r_extent` ở 30–50 m là 0.637 (n=167): độ dày bán kính là 0.637 lần bán kính ngoài `[ĐO]`.
- `median r_extent` ở 0–5 m là 0.596 m (n=4740) `[ĐO]`, tức 1.99× giá trị cấu hình `cluster_radius_median_m = 0.30 m` `[CODE]`.
- `median n_rings` ở 0–5 m là 1.0 (p25 1.0, p75 2.0, n=4740), `median ring_span` 0 `[ĐO]`.
- `median n_rings` ở 5–10 m là 4.0 (p25 2.0, p75 11.0, n=6254), `median ring_span` 6 `[ĐO]`.
- `median n_rings` ở 10–20 m là 4.0 (p25 2.0, p75 8.0, n=10416), `median ring_span` 5 `[ĐO]`.
- `median n_rings` ở 20–30 m là 4.0 (p25 2.0, p75 6.0, n=2412), `median ring_span` 3 `[ĐO]`.
- `median n_rings` ở 30–50 m là 2.0 (p25 1.0, p75 3.0, n=167), `median ring_span` 1 `[ĐO]`.

## Caveats

- Label `2` của SemanticSpray là *noise*, gồm spray và các nguồn nhiễu
  khác. Chỉ dense cluster (>= 5 điểm) được đo hình học.
- Single-linkage trên `(x, y)` nối các điểm cách nhau <= radius, nên một
  cluster có thể bị nối chuỗi. `r_extent` và `r_range` vì vậy là cận trên
  của hình học plume đơn lẻ; `n_rings` cũng bị ảnh hưởng cùng chiều.
- `d_sensor` là norm 3D của centroid, không phải khoảng cách ngang
  (`hypot(x, y)`) đã dùng trong `docs/semantic-spray-stats.md`.
- Script chỉ đo, không đề xuất hay sửa tham số generator (ticket 17).
