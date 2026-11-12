# 29f — cụm `alive` / `visible` / `dbscan` của generator (đo trên `cal`)

Sinh bằng `scripts/measure_29f.py`. **Chỉ đo**, không sửa generator.
3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful `inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`). DBSCAN góc 0,7° / minPts = 3 (recipe paper, không đổi).

- `alive` = số cụm còn sống trong state ngay trước khi ray-cast (`state.all_alive()`), trung bình theo frame.
- `visible` = số cụm `alive` có ≥ 1 detection nằm trong cầu `|p − tâm| ≤ 1.5·r` của cụm (gán detection cho cầu gần nhất).
- `dbscan` = số cụm DBSCAN dựng lại từ detection của frame (≥ 3 điểm), trung bình theo frame.
- `phủ` = tổng số cụm `alive` khác nhau mà các cụm DBSCAN phủ (mỗi điểm detection gán cho cụm `alive` gần nhất); `phủ max` = cụm DBSCAN phủ nhiều cụm `alive` nhất. `phủ > dbscan` ⇒ DBSCAN **gộp** nhiều cụm thành một.
- `alive_not_dbscan = alive − dbscan` — cụm sinh ra nhưng DBSCAN không thấy.
- `det_per_alive` = số detection / số cụm `alive`.
- `real dbscan` = số cụm DBSCAN trên điểm label 2, lấy từ §2 của `29ed3-gen-overlap.md` (tổng 90 frame); `real/frame` = tổng / 90; `Δ = dbscan − real/frame`. `29ed3` báo **cụm/frame** (12,9 @100), cột `cụm real` của nó là **tổng** — so thẳng hai cột đó là lỗi đơn vị 90×.
- `alive target` = `cluster_count_for_speed_abs(v, 1 mm)` (trạng thái dừng lý thuyết); `alive/target` = `alive` đo / target; `rate` = `cluster_spawn_rate_for_speed_abs(v)`; `rate·T/Δt` = số cụm state sẽ giữ nếu **không** prune; `T` = `lifetime_mean_s(v, 1 mm)`.
- **Cửa chặn:** `alive` ≤ 0.7× real/frame ⇒ lỗi ở khâu **sinh cụm** (3b); `alive` ≈ real/frame mà `dbscan` thấp ⇒ lỗi ở **ray-cast** (3a).
- **Đơn vị của Bảng 1** (`semantic-spray-clusters-by-speed.md`): đếm **cụm DBSCAN** (0,7° / minPts = 3) trên điểm `label == 2` — cùng toán tử với `real/frame` ở đây, không phải cụm `alive` của generator. A1 so `visible_cluster_count_for_speed` (cụm **alive**) với bảng DBSCAN ⇒ A1 đạt là **trùng hợp đơn vị**, không phải bằng chứng generator khớp.

## 1. Theo lớp × tốc độ

| lớp | km/h | frame | alive | alive/target | visible | dbscan | phủ | phủ max | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real | alive target | rate | rate·T/Δt | T (s) | capped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 90 | 9.37 | 2.34 | 4.56 | 2.93 | 4.79 | 2.10 | 6.43 | 4.01 | 4.50 | -1.57 | 2.08 | 0.65 | 4 | 1.66 | 3.3 | 0.20 | 0 |
| Crafter_dynamic | 60 | 90 | 21.27 | 1.93 | 11.94 | 5.83 | 17.26 | 7.59 | 15.43 | 5.96 | 9.74 | -3.91 | 2.18 | 0.60 | 11 | 2.54 | 10.2 | 0.40 | 0 |
| Crafter_dynamic | 70 | 90 | 26.47 | 1.56 | 12.99 | 8.60 | 21.38 | 6.80 | 17.87 | 6.80 | 16.44 | -7.84 | 1.61 | 0.52 | 17 | 2.72 | 16.3 | 0.60 | 0 |
| Crafter_dynamic | 80 | 90 | 30.71 | 1.40 | 13.68 | 9.91 | 21.47 | 7.29 | 20.80 | 6.02 | 16.18 | -6.27 | 1.90 | 0.61 | 22 | 2.63 | 21.0 | 0.80 | 0 |
| Crafter_dynamic | 90 | 90 | 25.02 | 1.19 | 11.46 | 16.22 | 25.50 | 4.51 | 8.80 | 8.40 | 18.69 | -2.47 | 1.34 | 0.87 | 21 | 2.00 | 20.0 | 1.00 | 0 |
| Crafter_dynamic | 100 | 90 | 28.64 | 0.99 | 13.36 | 12.89 | 23.56 | 6.19 | 15.76 | 7.43 | 21.79 | -8.90 | 1.31 | 0.59 | 29 | 2.38 | 28.6 | 1.20 | 0 |
| Crafter_dynamic | 110 | 90 | 23.80 | 0.85 | 11.16 | 16.84 | 25.07 | 4.77 | 6.96 | 10.02 | 18.29 | -1.44 | 1.30 | 0.92 | 28 | 2.00 | 28.0 | 1.40 | 0 |
| Crafter_dynamic | 120 | 90 | 13.32 | 0.74 | 6.99 | 12.52 | 16.23 | 3.01 | 0.80 | 13.51 | 15.71 | -3.19 | 0.85 | 0.80 | 18 | 1.08 | 17.3 | 1.60 | 0 |
| Crafter_dynamic | 130 | 90 | 12.80 | 0.71 | 6.70 | 8.38 | 10.93 | 2.22 | 4.42 | 7.68 | 15.01 | -6.63 | 0.85 | 0.56 | 18 | 0.97 | 17.5 | 1.80 | 0 |
| Golf_dynamic | 50 | 90 | 7.23 | 1.81 | 3.98 | 2.00 | 3.52 | 1.88 | 5.23 | 3.83 | 3.49 | -1.49 | 2.07 | 0.57 | 4 | 1.44 | 2.9 | 0.20 | 0 |
| Golf_dynamic | 60 | 90 | 12.82 | 1.42 | 7.92 | 3.42 | 7.96 | 3.44 | 9.40 | 4.13 | 7.89 | -4.47 | 1.63 | 0.43 | 9 | 1.98 | 7.9 | 0.40 | 0 |
| Golf_dynamic | 70 | 90 | 11.67 | 1.06 | 8.14 | 4.79 | 11.02 | 5.06 | 6.88 | 8.15 | 10.62 | -5.83 | 1.10 | 0.45 | 11 | 1.77 | 10.6 | 0.60 | 0 |
| Golf_dynamic | 80 | 90 | 11.61 | 0.89 | 8.61 | 6.42 | 11.57 | 4.12 | 5.19 | 10.22 | 12.68 | -6.26 | 0.92 | 0.51 | 13 | 1.54 | 12.3 | 0.80 | 0 |
| Golf_dynamic | 90 | 90 | 8.47 | 0.77 | 5.58 | 8.56 | 11.81 | 2.48 | -0.09 | 12.96 | 11.70 | -3.14 | 0.72 | 0.73 | 11 | 1.02 | 10.2 | 1.00 | 0 |
| Golf_dynamic | 100 | 90 | 14.02 | 0.78 | 10.92 | 19.80 | 28.01 | 4.71 | -5.78 | 18.78 | 14.59 | 5.21 | 0.96 | 1.36 | 18 | 1.47 | 17.7 | 1.20 | 0 |
| Golf_dynamic | 110 | 90 | 11.34 | 0.67 | 8.71 | 19.14 | 25.39 | 3.70 | -7.80 | 24.14 | 14.72 | 4.42 | 0.77 | 1.30 | 17 | 1.17 | 16.4 | 1.40 | 0 |
| Golf_dynamic | 120 | 90 | 8.19 | 0.55 | 6.11 | 14.14 | 17.63 | 2.87 | -5.96 | 23.89 | 13.21 | 0.93 | 0.62 | 1.07 | 15 | 0.94 | 15.1 | 1.60 | 0 |
| Golf_dynamic | 130 | 90 | 9.40 | 0.55 | 7.33 | 15.23 | 19.23 | 3.10 | -5.83 | 29.03 | 15.00 | 0.23 | 0.63 | 1.02 | 17 | 0.92 | 16.5 | 1.80 | 0 |

## 2. Gộp theo lớp (trung bình 9 tốc độ)

| lớp | alive | visible | dbscan | phủ | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 21.27 | 10.31 | 10.46 | 18.46 | 10.81 | 7.76 | 15.15 | -4.69 | 1.40 | 0.69 |
| Golf_dynamic | 10.53 | 7.48 | 10.39 | 15.13 | 0.14 | 15.02 | 11.54 | -1.15 | 0.91 | 0.90 |

## 3. Kết luận cửa chặn

**Nhánh 3b (sinh cụm):** 2/18 ô có `alive` ≤ 0.7× real/frame (Golf_dynamic@120, Golf_dynamic@130). Cụm không được sinh đủ, ray-cast không phải chỗ mất cụm.

## 4. Cơ chế đo được

- `alive` chạy **cao hơn** `alive target` (1,0–2,2×): `T` bốc `N(T, 0,2 s)` và bị kẹp ≥ 0, nên một phần cụm sống tới ~4·(T + 2σ) = 5,6·T và trạng thái giữ nhiều cụm hơn `rate·K`. Thử riêng (không ghi vào bảng): tắt hẳn prune theo trần cũng chỉ lên 9,2 / 66,6 cụm @50 / @100 ⇒ prune theo trần **không** phải chỗ mất cụm.
- `visible` / `alive` ≈ 0,47 (Crafter) và 0,71 (Golf): mỗi cụm chỉ có `det_per_alive` ≈ 4–29 detection, trong khi DBSCAN cần ≥ 3 điểm **và** 3 điểm đó phải nằm trong 0,7° của nhau.
- `dbscan` (chỉ detection) ≈ 0,43–0,92× real/frame với Crafter, 0,43–0,73× với Golf ở 50–90 km/h, nhưng **> 1×** với Golf ở 100–130 km/h — cột `phủ` giải thích: DBSCAN **gộp** nhiều cụm `alive` thành một cụm. Detection của một cụm nằm rải trong ~1,5·r quanh tâm (p50 0,33–0,61 m), trong khi `eps = 0,7°` ở 10–20 m chỉ là 0,12–0,24 m ⇒ cụm 0,3 m **không tách được** thành một cụm DBSCAN riêng. Vì vậy `dbscan` là **cận dưới** của số cụm generator, không phải phép đếm 1-1.
- **Ảnh ghép không dùng được**: đo riêng 3 frame Crafter@100, DBSCAN trên `real_points` + detection (đúng đầu vào `PlumeTransform`) cho 21–29 cụm, trong đó **điểm thật một mình đã 12–20 cụm** (mưa, phản xạ, điểm trên xe) ⇒ phần lớn cụm DBSCAN ở ảnh ghép **không phải** cụm plume.
