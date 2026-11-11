# Cổng chia `cal` / `held-out` cho SemanticSpray

## Bối cảnh

Tham số generator v2 đang được đo trên toàn bộ 207 scene rồi báo cáo
khớp trên chính 207 scene đó, nên mọi con số là in-sample. Cổng này
chia dataset thành `cal` (được chọn tham số) và `held-out` (chỉ dùng để
kiểm) theo luật đóng băng `[CHỌN 2026-11-11]`: 1:1 trong từng ô, sắp
theo tên, xen kẽ, scene dư về `cal`, không RNG. Cổng chỉ PASS khi 7/7
tiêu chí đạt; `held-out` không được dùng để chọn tham số.

## Mẫu

- lệnh: `python scripts/semantic_spray_split.py --measure --frames-per-scene 60`
- `--frames-per-scene`: **60**
- `--limit-scenes`: **0** (0 = không giới hạn)
- clustering cổng: DBSCAN trên mặt phẳng `(azimuth, elevation)`, `eps = 0.7°`, elevation snap lưới `0.333°`, `minPts = 3`, azimuth wrap 360° `[CHỌN]`
- clustering phụ: single-linkage trên `(x, y)` bán kính **0.5 m**, giữ cụm **>= 3 điểm** (chỉ dùng cho bảng phụ)

| vai | scene | frame |
|---|---:|---:|
| cal | 104 | 6015 |
| held-out | 103 | 6065 |
| cal_a | 52 | 3045 |
| cal_b | 52 | 2970 |

- frame bị bỏ (thiếu file hoặc `labels.size != points.shape[0]`): **0** (cal 0, held-out 0)

## Bảng 1 — Split theo ô

| group | km/h | distance (m) | #scene | cal | held-out | unpaired |
|---|---:|---:|---:|---:|---:|---|
| Crafter_dynamic | 50 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 50 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 60 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 60 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 70 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 70 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 80 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 80 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 90 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 90 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 100 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 100 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 110 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 110 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 120 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 120 | 30.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 130 | 20.0 | 6 | 3 | 3 | no |
| Crafter_dynamic | 130 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 50 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 50 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 60 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 60 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 70 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 70 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 80 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 80 | 30.0 | 2 | 1 | 1 | no |
| Golf_dynamic | 90 | 20.0 | 1 | 1 | 0 | yes |
| Golf_dynamic | 90 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 100 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 100 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 110 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 110 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 120 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 120 | 30.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 130 | 20.0 | 6 | 3 | 3 | no |
| Golf_dynamic | 130 | 30.0 | 6 | 3 | 3 | no |

## Bảng 2 — 7 tiêu chí đóng băng `[ĐO]`

Ngưỡng hiệu dụng = `max(sàn, 2 × Δ_halfsplit)`; `Δ_halfsplit` là
chênh giữa hai nửa xen kẽ của `cal` và chỉ là **sàn nhiễu nội tại**
`[CHỌN]`. G6 PASS khi cả p5, p50, p95 đạt. G2/G3/G4 dùng DBSCAN góc
theo recipe paper.

| id | đại lượng | cal | held-out | Δ | Δ_halfsplit | ngưỡng | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| G1 | noise_points_per_frame (median) | 260.000 | 144.000 | -44.6% | 5.4% | 15.0% | FAIL |
| G2 | clusters_per_frame (mean) | 14.796 | 11.937 | -19.3% | 3.0% | 20.0% | PASS |
| G3 | points_per_cluster (median) | 6.000 | 6.000 | +0.0% | 0.0% | 20.0% | PASS |
| G4 | range_over_extent (median) | 1.481 | 1.481 | -0.000 | 0.002 | 0.100 | PASS |
| G5 | abs_y_p95_m (p95) | 2.488 | 2.157 | -13.3% | 0.9% | 15.0% | PASS |
| G6 | height_above_road_m (p5, p50, p95) | 0.128 / 1.335 / 2.307 | 0.067 / 0.964 / 2.153 | -0.062 / -0.371 / -0.155 | 0.079 | 0.200 | FAIL |
| G7 | elevation_deg (median) | 7.678 | 6.861 | -0.817 | 0.283 | 0.565 | FAIL |

### Bảng phụ — recipe legacy Euclid 0,5 m (chỉ để đối chiếu ticket 16) `[ĐO]`

Recipe này không tham gia cổng; chỉ để so thang số. `17,06` cụm/frame của ticket 16 sinh bởi toán tử `0,5 m` + `dense_min = 5` nên **đếm thiếu** so với paper (33 cụm/frame ở 100 km/h, Fig. 1); không được lấy `17,06` làm mốc.

| vai | cụm/frame (mean) | điểm/cụm (median) | median r_range/r_extent |
|---|---:|---:|---:|
| cal | 8.38 | 10.00 | 1.270 |
| held-out | 7.32 | 10.00 | 1.265 |

Ghi chú các dòng FAIL:

- G6: G6_p5: Δ=-0.062; G6_med: Δ=-0.371; G6_p95: Δ=-0.155 — có phân vị vượt ngưỡng

## Bảng 3 — Số bàn giao cho 29c `[ĐO]`

`tail_block_height_frac` chia độ cao trên mặt đường cho **2.6206 m** (chiều cao box van `Crafter_dynamic`, `docs/measurements/plume-v2-measurements.md`).

| đại lượng (trên cal) | giá trị |
|---|---|
| điểm noise/frame (p5 / med / p95) | 5.00 / 260.00 / 1995.60 |
| cụm/frame (mean) | 14.80 |
| điểm/cụm (p5 / med / p95) | 3.00 / 6.00 / 140.00 |
| `tail_block_height_frac` (p5 / p95) | 0.05 / 0.88 |
| p95(\|y\|) (m) | 2.49 |
| intensity (p50 / p90 / p99) | 0.00 / 1.00 / 3.00 |
| ring (khoảng, median) | 0–31, median 9 |

## Kết luận

3/7 FAIL (G1, G6, G7) — split không đại diện được cho (các) tham số tương ứng.
Không đổi ngưỡng, không trộn vai.

## Caveats

- `Δ_halfsplit` chỉ là sàn nhiễu nội tại của `cal`, không phải khoảng tin cậy hình thức `[CHỌN]`.
- Cổng dùng DBSCAN góc `minPts = 3`, `eps = 0,7°`, elevation snap `0,333°`; paper không nói rõ lân cận là hộp hay tròn trong mặt phẳng góc nên dùng đĩa Euclid `[CHỌN]`. Single-linkage 0,5 m chỉ còn là bảng phụ.
- Paper **không chia scene**: paper giữ điều kiện chưa dùng khi hiệu chỉnh trên cùng bộ dữ liệu (§IV-1) và có bộ spray test riêng 1.463 frame. Split 1:1 theo scene ở đây là `[CHỌN]` của mình, không phải protocol paper.
- Label `2` của SemanticSpray gồm cả nhiễu không phải spray (mưa, phản xạ), nên mọi đại lượng đều là thống kê của *noise*, không riêng plume.
- `amb_tmp` không đưa vào ô chia: nó lệch theo lô và sẽ làm ô mất cân bằng mà không thêm thông tin.
