# Cổng chia `cal` / `held-out` cho SemanticSpray

## Luật chia

- rule: `v2-parity-flip-by-cell`
- ngày: 2026-11-11
- lý do đổi luật: trong mỗi ô, `metadata.txt` ghi `itr_after_water`
  1…6 đúng theo thứ tự tên file và bể nước vơi dần sau mỗi lần đo.
  Luật v1 sắp theo tên rồi luôn bắt đầu bằng `cal`, nên `cal` rơi vào
  các lần đo 1/3/5 (nước vừa thay, plume lớn) còn `held-out` vào
  2/4/6 (nước đã vơi); đo 8 frame/scene cho thấy noise/frame chênh
  1,62 lần, khớp với Δ −44,6 % của G1 và kéo theo G6/G7. v2 sắp theo
  `(itr_after_water, tên)` và đảo parity theo ô để hai vai bằng nhau
  ở từng mốc `w_itr`.
- hệ quả: so sánh hai vai **trong cùng một ô** không còn nghĩa vì
  chúng đo ở chu kỳ nước khác nhau; chỉ aggregate theo vai mới dùng được.

> Số liệu của luật v1 (`SPLIT_GATE ok=False failed=[G1,G6,G7]`)
> **không dùng nữa**. Mọi bảng dưới đây sinh lại bằng luật v2.

## Bối cảnh

Tham số generator v2 đang được đo trên toàn bộ 207 scene rồi báo cáo
khớp trên chính 207 scene đó, nên mọi con số là in-sample. Cổng này
chia dataset thành `cal` (được chọn tham số) và `held-out` (chỉ dùng để
kiểm) theo luật v2: 1:1 trong từng ô, sắp theo `itr_after_water`, đảo
parity theo ô, scene dư về `cal`, không RNG. Cổng chỉ PASS khi 7/7
tiêu chí đạt; `held-out` không được dùng để chọn tham số.

## Mẫu

- lệnh: `python scripts/semantic_spray_split.py --measure --frames-per-scene 60`
- `--frames-per-scene`: **60**
- `--limit-scenes`: **0** (0 = không giới hạn)
- clustering cổng: DBSCAN trên mặt phẳng `(azimuth, elevation)`, `eps = 0.7°`, elevation snap lưới `0.333°`, `minPts = 3`, azimuth wrap 360° `[CHỌN]`
- clustering phụ: single-linkage trên `(x, y)` bán kính **0.5 m**, giữ cụm **>= 3 điểm** (chỉ dùng cho bảng phụ)

| vai | scene | frame |
|---|---:|---:|
| cal | 104 | 6074 |
| held-out | 103 | 6006 |
| cal_a | 52 | 3034 |
| cal_b | 52 | 3040 |

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

## Bảng 4 — Cân bằng `itr_after_water`

Số scene mỗi mốc `w_itr` phải bằng nhau giữa `cal` và `held-out`, cho
từng group và toàn cục. Bảng tính trên toàn bộ split, không phụ thuộc
`--limit-scenes`.

| group | vai | w=1 | w=2 | w=3 | w=4 | w=5 | w=6 | tổng |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | cal | 9 | 9 | 9 | 9 | 9 | 9 | 54 |
| Crafter_dynamic | held-out | 9 | 9 | 9 | 9 | 9 | 9 | 54 |
| Golf_dynamic | cal | 9 | 8 | 8 | 8 | 8 | 9 | 50 |
| Golf_dynamic | held-out | 9 | 8 | 8 | 8 | 8 | 8 | 49 |
| toàn cục | cal | 18 | 17 | 17 | 17 | 17 | 18 | 104 |
| toàn cục | held-out | 18 | 17 | 17 | 17 | 17 | 17 | 103 |

- 34 ô đủ 6 scene: `cal` và `held-out` bằng nhau tuyệt đối ở cả 6 mốc
  (mỗi vai 3 scene/mốc/ô).
- Ô `Golf_dynamic` 80 km/h / 30 m chỉ có 2 scene (`w_itr` 1 và 6), ô
  `Golf_dynamic` 90 km/h / 20 m chỉ có 1 scene (`w_itr` 1). Vì tổng
  toàn cục ở mốc `w=6` là **35** (lẻ) nên không thể chia đều: một vai
  buộc phải nhận 18, vai kia 17. Các mốc `w=1…5` bằng nhau (18/18 rồi
  17/17), `w=6` lệch đúng 1 scene — đây là dư lượng của dữ liệu, không
  phải lỗi luật chia.

## Bảng 2 — 7 tiêu chí đóng băng `[ĐO]`

Ngưỡng = sàn đóng băng của từng tiêu chí, không bao giờ nới.
`Δ_halfsplit` là chênh giữa hai nửa stratify theo
`(group, itr_after_water)` của `cal`, chỉ để **chẩn đoán** và không
tham gia verdict `[CHỌN]`. G6 PASS khi cả p5, p50, p95 đạt.
G2/G3/G4 dùng DBSCAN góc theo recipe paper.

| id | đại lượng | cal | held-out | Δ | Δ_halfsplit (chẩn đoán) | ngưỡng | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| G1 | noise_points_per_frame (median) | 188.000 | 184.000 | -2.1% | 14.9% | 15.0% | PASS |
| G2 | clusters_per_frame (mean) | 13.414 | 13.307 | -0.8% | 3.4% | 20.0% | PASS |
| G3 | points_per_cluster (median) | 6.000 | 6.000 | +0.0% | 0.0% | 20.0% | PASS |
| G4 | range_over_extent (median) | 1.480 | 1.482 | +0.002 | 0.007 | 0.100 | PASS |
| G5 | abs_y_p95_m (p95) | 2.308 | 2.401 | +4.0% | 5.5% | 15.0% | PASS |
| G6 | height_above_road_m (p5, p50, p95) | 0.111 / 1.197 / 2.264 | 0.093 / 1.183 / 2.248 | -0.018 / -0.014 / -0.016 | 0.013 | 0.200 | PASS |
| G7 | elevation_deg (median) | 7.494 | 7.334 | -0.160 | 0.264 | 0.500 | PASS |

### Bảng phụ — recipe legacy Euclid 0,5 m (chỉ để đối chiếu ticket 16) `[ĐO]`

Recipe này không tham gia cổng; chỉ để so thang số. `17,06` cụm/frame của ticket 16 sinh bởi toán tử `0,5 m` + `dense_min = 5` nên **đếm thiếu** so với paper (33 cụm/frame ở 100 km/h, Fig. 1); không được lấy `17,06` làm mốc.

| vai | cụm/frame (mean) | điểm/cụm (median) | median r_range/r_extent |
|---|---:|---:|---:|
| cal | 7.85 | 10.00 | 1.267 |
| held-out | 7.85 | 10.00 | 1.268 |

## Bảng 3 — Số bàn giao cho 29c `[ĐO]`

`tail_block_height_frac` chia độ cao trên mặt đường cho **2.6206 m** (chiều cao box van `Crafter_dynamic`, `docs/measurements/plume-v2-measurements.md`).

| đại lượng (trên cal) | giá trị |
|---|---|
| điểm noise/frame (p5 / med / p95) | 4.00 / 188.00 / 1671.35 |
| cụm/frame (mean) | 13.41 |
| điểm/cụm (p5 / med / p95) | 3.00 / 6.00 / 135.00 |
| `tail_block_height_frac` (p5 / p95) | 0.04 / 0.86 |
| p95(\|y\|) (m) | 2.31 |
| intensity (p50 / p90 / p99) | 0.00 / 1.00 / 3.00 |
| ring (khoảng, median) | 0–31, median 8 |

## Kết luận

7/7 PASS — split đại diện được cho các tham số dùng ở 29c.

## Caveats

- `Δ_halfsplit` chỉ là chẩn đoán nhiễu nội tại của `cal` (hai nửa
  stratify theo `(group, itr_after_water)`), không phải khoảng tin
  cậy hình thức và không dùng để nới ngưỡng `[CHỌN]`.
- Cổng dùng DBSCAN góc `minPts = 3`, `eps = 0,7°`, elevation snap `0,333°`; paper không nói rõ lân cận là hộp hay tròn trong mặt phẳng góc nên dùng đĩa Euclid `[CHỌN]`. Single-linkage 0,5 m chỉ còn là bảng phụ.
- Paper **không chia scene**: paper giữ điều kiện chưa dùng khi hiệu chỉnh trên cùng bộ dữ liệu (§IV-1) và có bộ spray test riêng 1.463 frame. Split 1:1 theo scene ở đây là `[CHỌN]` của mình, không phải protocol paper.
- Label `2` của SemanticSpray gồm cả nhiễu không phải spray (mưa, phản xạ), nên mọi đại lượng đều là thống kê của *noise*, không riêng plume.
- `amb_tmp` không đưa vào ô chia: nó lệch theo lô và sẽ làm ô mất cân bằng mà không thêm thông tin.
