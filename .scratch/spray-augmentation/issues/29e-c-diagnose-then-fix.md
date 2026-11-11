# 29e-c — Chẩn đoán theo dải cự ly rồi mới sửa (thay 29e-b)

Type: task
Status: ready-for-agent
Supersedes: 29e-b (đích `mean det/cụm` trong 29e-b là **sai**, xem mục “Vì sao bỏ”)
Owner: PM dispatch → CommandCode

## Vì sao bỏ đích của 29e-b

29e-b đặt tiêu chí `det/cụm` = mean = 47,3 @100 / 49,6 @130 (±20 %). Số đo lại trên `cal`
(45 frame/ô, cùng toán tử DBSCAN 0,7°) cho thấy mean đó **chỉ là đuôi phân bố**, không phải
đại lượng mô hình cầu độc lập tạo ra được:

| km/h | cụm/frame | điểm/frame | mean | **p50** | p90 | p95 | p99 | max | % điểm trong 5 % cụm to nhất |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 27,3 | 1.183 | 43,3 | **6** | 66 | 188 | 823 | 1.723 | **66,6 %** |
| 130 | 16,0 | 776 | 48,6 | **6** | 80 | 161 | 1.011 | 2.485 | **65,3 %** |

Hai phần ba số điểm nằm trong 5 % cụm — đó là **mảng nước liền** trên mặt đường. Muốn khớp mean
47,3 bằng cầu thì `r` phải ~9 m (`n_max = 1.700/0,18 = 9.400 tia` ⇒ `r/d ≈ 0,30`), phá toàn bộ
hình học. Bỏ A3 cũ; thay bằng **p50 = 6 ± 2** (khớp dữ liệu thật **và** Gate G3 của 29d = 6).

## Paper đã xác nhận (NotebookLM, 2026-11-11, `phk4`)

- `r_cl` ~ lognormal **µ = −1,2, σ = 0,8** ⇒ **median = e^µ = 0,30 m** `[PAPER, Fig. 5]`.
  Đây là hằng số **có sẵn trong code**, không phải thứ cần hiệu chỉnh.
- Cụm là **khối cầu**; detection lấy theo tia cắt cầu; range của điểm ~ **normal quanh tâm cụm**.
- *“With the independent uniform placement of clusters with different radii, overlapping will occur
  in random cases. On one hand, overlapping will reduce the calibrated number of clusters. On the
  other hand, it increases inhomogeneity even further by creating other shapes than spheres.”*
  ⇒ gộp cụm là hiện tượng **nổi lên**, không tune.
- Fig 11a = **tổng điểm/frame**, 500–1.500 ⇒ khớp cửa sổ 570–1.555 của 29c.

## Trạng thái đã biết (không đoán lại)

| Đại lượng | Real (`cal`) | Gen (29c/29e) |
|---|---:|---:|
| cụm/frame @100 / @130 | 27,3 / 16,0 (Bảng 1: 29,24 / 17,69) | khớp ±5 % ✓ |
| điểm/frame @100 / @130 | 1.183 / 776 | **440 / 258** ✗ (2,7–3,0×) |
| p50 điểm/cụm | 6 | 6 ✓ |
| chiều cao p5/med/p95 | 0,111 / 1,197 / 2,264 | 0,66 / 1,47 / 2,37 ✗ |
| p95\|y\| | 2,308 | 3,0 ✗ |
| `RADIUS_MEDIAN_PER_KMH` | — | 0,0055 (đã thêm ở 29e, **sai hướng**) |

Suy đoán có căn cứ về chỗ mất điểm: detection sinh ra ở cự ly xa quá thưa ⇒ DBSCAN `minPts = 3`
loại sạch (điểm `-1`), nên model đếm 1.277 điểm nhưng **đo được chỉ 440**. Phải chứng minh bằng
bảng theo dải cự ly chứ không sửa mò.

## Việc 1 (bắt buộc làm trước) — `scripts/measure_29ec.py`

In bảng so **gen vs real** theo **dải cự ly** `[0–15) [15–25) [25–40) [40+ m`, cho 100 và 130 km/h,
2 lớp, 30 frame × 3 scene, `wfh_ref = 1,0`:

| cột | định nghĩa |
|---|---|
| real_pts / gen_pts | số điểm label-2 (gen: `points_clean` loại ra) trong dải |
| real_cl / gen_cl | số cụm DBSCAN 0,7° **có tâm** trong dải |
| real_p50 / gen_p50 | median điểm/cụm |
| gen_raw_det | số detection generator sinh ra trong dải **trước** DBSCAN |
| gen_dropped | `gen_raw_det −` số điểm lọt vào cụm nào đó (bị DBSCAN bỏ) |

Bảng này quyết định sửa gì (decision tree bên dưới). **Không sửa code sinh trước khi có bảng.**

## Việc 2 — sửa theo bảng

- Nếu `gen_dropped` lớn ở dải xa ⇒ **đừng spawn** cụm ở cự ly > 40 m (plume thật không tạo cụm
  sống được ở đó), hoặc tăng số tia/cụm ở dải xa bằng cách kéo phân bố cự ly vào gần.
- Nếu `gen_pts` thiếu đều ở dải gần ⇒ kiểm `P_det` hiệu dụng và `n_max` (Ω_tia = 2,003e−5 sr).
- Nếu `gen_cl` vượt real ở dải xa ⇒ dồn cụm về gần như trên.
- **Xoá `RADIUS_MEDIAN_PER_KMH`**; trả `r_cl` về lognormal paper µ = −1,2, σ = 0,8, `max 1,0 m`.
- `tail_block_height_frac = (0.05, 0.92)` (ticket chốt; code đang 0,15/1,00).
- Kẹp ngang `|y − y_block| ≤ 2,43 m` mỗi bước.
- Dân số: `WFH_REF_MM = 1.0`; spawn rate đóng vòng theo bảng cụm/frame ở `wfh_ref`.

Cho phép **đúng 1 vòng sửa → đo lại**. Nếu sau 1 vòng vẫn trượt, **dừng và báo số**.

## Tiêu chí nghiệm thu (đóng băng)

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| A1 | cụm/frame, 9 mốc × 2 lớp | ±20 % Bảng 1 |
| A2 | điểm/frame @100 và @130 | 800–1.500 và 600–1.000; 9 mốc trong 570–1.555 |
| A3 | **p50** điểm/cụm | 6 ± 2 |
| A4 | chiều cao p5/med/p95 | 0,111 / 1,197 / 2,264 ± 0,20 m |
| A5 | p95\|y\| | 2,308 ± 15 % |
| A6 | latency | ≤ 100 ms/frame |
| A7 | ngân sách | `capped = 0` ở 4 tốc độ |
| A8 | test | xanh, không xoá/nới test cũ |
| A9 | `points_clean` | byte-equal |
| A10 | thiếu `plume_context` | `RuntimeError` |

## Không được làm

- Không tune trên `held-out`; không đụng `docs/measurements/semantic-spray-*.md` của 29d.
- Không thêm hằng số hiệu chỉnh theo tốc độ nào khác ngoài bảng cụm/frame đã có.
- Không nới ngưỡng. Không commit.