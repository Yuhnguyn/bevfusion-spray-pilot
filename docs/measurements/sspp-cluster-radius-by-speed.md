# Bán kính cụm theo tốc độ trên SSPP — kiểm định bước 2 của A3 (2026-11-19)

Người đo: lead. Script: `scripts/sspp_cluster_radius_by_speed.py`. JSON: `.scratch/roadspray-cal/tmp/radii.json`.
Nhãn: `[ĐO]` · `[DỰ ĐOÁN]` (ghi **trước** khi đo) · `[SUY LUẬN]`.

## 0. Câu hỏi kiểm định

Sau bước 1 (số điểm/cụm ∝ tiết diện quả cầu, `∝ r²`), mô hình khớp ở 100 km/h nhưng:
50 km/h **thừa 5,6×** và đuôi quá nặng; 130 km/h **thiếu 2,5×**. Giả thuyết bước 2: độ nặng
đuôi do **σ của phân bố bán kính** thay đổi theo tốc độ (paper Fig. 5 là phân bố bán kính
*theo từng tốc độ*, repo đang dùng số trung bình `σ = 0,8` cho mọi tốc độ).

**Dự đoán ghi trước khi đo** `[DỰ ĐOÁN]` — suy từ `σ_meas = sqrt(2 ln(mean/p50))`, `σ_count = 2σ_r`,
hệ số truyền pipeline ~1,05:

| km/h | σ_r dự đoán |
|---:|---:|
| 50 | **0,42** |
| 70 | 0,72 |
| 100 | 0,93 |
| 130 | 0,96 |

Điều kiện bác bỏ: nếu đo ra `σ_r(50) ≈ 0,8` (số paper) thì giả thuyết **sai**.

## 1. Kết quả `[ĐO]`

Định nghĩa bán kính đúng Paper A §III-B: *"the radii r_cl are set to the maximum distance of
detections to the respective cluster center"*. Recipe gom cụm y nguyên bảng cụm/frame
(`label == 2`, DBSCAN `eps = 0,7°`, `minPts = 3`). 207 scene × 15 frame, gộp theo fold (không leak).

**Crafter:**

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **σ_ln (đo)** | **1,37** | 1,69 | 1,67 | 1,69 | 1,72 | 1,67 | 1,71 | 1,69 | 1,68 |
| **median r (m)** | **0,079** | 0,152 | 0,242 | 0,350 | 0,333 | 0,311 | 0,337 | 0,369 | 0,310 |
| p90 r (m) | 0,71 | 3,68 | 4,56 | 5,73 | 5,83 | 5,36 | 5,76 | 5,80 | 5,43 |
| số cụm | 823 | 1 412 | 2 139 | 2 796 | 3 196 | 3 688 | 3 053 | 2 179 | 2 227 |

**Golf:** median 0,186 / 0,301 / 0,289 / 0,255 m; σ_ln 1,52 / 1,80 / 1,87 / 1,84 ở 50/70/100/130.

## 2. Kết luận: dự đoán **SAI**

| km/h | σ_r dự đoán | **σ_r đo được** | |
|---:|---:|---:|---|
| 50 | 0,42 | **1,37** | ✗ |
| 70 | 0,72 | **1,67** | ✗ |
| 100 | 0,93 | **1,67** | ✗ |
| 130 | 0,96 | **1,68** | ✗ |

`σ_r` **gần như không đổi** theo tốc độ (1,67–1,72 từ 60 tới 130 km/h), không tăng 0,42 → 0,96 như
dự đoán. **Giả thuyết "σ_bán_kính thay đổi theo tốc độ" bị bác bỏ.** Hướng đó dừng ở đây.

## 3. Nhưng phép đo tìm ra đại lượng thật sự phụ thuộc tốc độ

`[SUY LUẬN]` **Trung vị bán kính** — không phải σ — tăng **4,4×** từ 50 → 80 km/h rồi bão hoà:

| km/h | 50 | 60 | 70 | 80 | ≥90 |
|---|---:|---:|---:|---:|---:|
| median r | **0,079 m** | 0,152 | 0,242 | 0,350 | 0,31–0,37 |

Hai hệ quả quan trọng:

1. **Số paper (`µ = −1,2` ⇒ median 0,30 m) khớp với giá trị ≥ 80 km/h** của phép đo này
   (0,31–0,37 m) — tức số paper là số **tốc độ cao**, không phải hằng số cho mọi tốc độ. Repo đang
   dùng nó cho mọi tốc độ ⇒ ở 50 km/h bán kính bị **phóng 3,8×**, mà số điểm lại ∝ `r²`
   ⇒ **thừa ~14×** đúng ở chỗ ta đang thừa 5,6×. Đây là lời giải thích định lượng cho sai số 50 km/h.
2. `σ_r` đo được (1,67) **không so trực tiếp được với số paper (0,8)**: bán kính của cụm DBSCAN
   thật bao gồm cả các **chuỗi đã gộp** (p90 tới 5,7 m, max ~29 m), trong khi paper fit trên phân bố
   cụm "sạch". Chỉ **median** là so được, và nó khớp ở tốc độ cao.

## 4. Việc tiếp theo (đề xuất)

1. Thay hằng số `cluster_radius_median_m = 0,30` bằng **bảng median bán kính theo tốc độ** (số ở §1).
   Đây là số đo, và đúng đại lượng paper công bố (Fig. 5 theo từng tốc độ).
2. **Hiệu chỉnh lại luật số điểm**: `count ∝ r²` chỉ đúng khi quả cầu trải trên nhiều tia; ở bán kính
   nhỏ (0,08 m ở 10 m ⇒ 0,9° ⇒ ~2×4 tia) luật này không còn đúng và sẽ **co quá mức**. Nên dùng luật
   theo **số tia cắt qua** với sàn, thay vì `r²` trần.
3. Bảng `_POINTS_MEDIAN_BY_RANGE` (30/20/14/10) được hiệu chỉnh ở bán kính 0,30 m cố định ⇒ sau khi
   đổi bán kính phải **hiệu chỉnh lại** để tránh đếm hai lần cùng một hiệu ứng.
4. Đo lại bằng `scripts/measure_plume_size_tail.py`; tiêu chí A3 giữ nguyên
   (`share` ±10 điểm %, p95 trong [0,5×; 2×], `điểm/frame` trong [0,7×; 1,5×] ở 50/100/130).
