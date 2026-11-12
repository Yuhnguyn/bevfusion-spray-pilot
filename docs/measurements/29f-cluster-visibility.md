# 29f — cụm `alive` / `visible` / `dbscan` của generator (đo trên `cal`)

Sinh bằng `scripts/measure_29f.py`. **Chỉ đo**, không sửa generator.
3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful `inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`). DBSCAN góc 0,7° / minPts = 3 (recipe paper, không đổi).

- `alive` = số cụm còn sống trong state ngay trước khi ray-cast (`state.all_alive()`), trung bình theo frame.
- `visible` = số cụm `alive` có ≥ 1 detection nằm trong cầu `|p − tâm| ≤ 1.5·r` của cụm (gán detection cho cầu gần nhất).
- `dbscan` = số cụm DBSCAN dựng lại từ detection của frame (≥ 3 điểm), trung bình theo frame.
- `alive_not_dbscan = alive − dbscan` — cụm sinh ra nhưng DBSCAN không thấy.
- `det_per_alive` = số detection / số cụm `alive`.
- `real dbscan` = số cụm DBSCAN trên điểm label 2, lấy từ §2 của `29ed3-gen-overlap.md` (tổng 90 frame); `real/frame` = tổng / 90; `Δ = dbscan − real/frame`. `29ed3` báo **cụm/frame** (12,9 @100), cột `cụm real` của nó là **tổng** — so thẳng hai cột đó là lỗi đơn vị 90×.
- `alive target` = `cluster_count_for_speed_abs(v, 1 mm)` (trạng thái dừng lý thuyết); `alive/target` = `alive` đo / target; `T` = `lifetime_mean_s(v, 1 mm)`.
- **Cửa chặn:** `alive` ≤ 0.7× real/frame ⇒ lỗi ở khâu **sinh cụm** (3b); `alive` ≈ real/frame mà `dbscan` thấp ⇒ lỗi ở **ray-cast** (3a).

## 1. Theo lớp × tốc độ

| lớp | km/h | frame | alive | alive/target | visible | dbscan | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real | alive target | T (s) | capped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 90 | 9.37 | 2.34 | 4.56 | 2.93 | 6.43 | 4.01 | 4.50 | -1.57 | 2.08 | 0.65 | 4 | 0.20 | 0 |
| Crafter_dynamic | 60 | 90 | 21.27 | 1.93 | 11.94 | 5.83 | 15.43 | 5.96 | 9.74 | -3.91 | 2.18 | 0.60 | 11 | 0.40 | 0 |
| Crafter_dynamic | 70 | 90 | 26.47 | 1.56 | 12.99 | 8.60 | 17.87 | 6.80 | 16.44 | -7.84 | 1.61 | 0.52 | 17 | 0.60 | 0 |
| Crafter_dynamic | 80 | 90 | 30.71 | 1.40 | 13.68 | 9.91 | 20.80 | 6.02 | 16.18 | -6.27 | 1.90 | 0.61 | 22 | 0.80 | 0 |
| Crafter_dynamic | 90 | 90 | 25.02 | 1.19 | 11.46 | 16.22 | 8.80 | 8.40 | 18.69 | -2.47 | 1.34 | 0.87 | 21 | 1.00 | 0 |
| Crafter_dynamic | 100 | 90 | 28.64 | 0.99 | 13.36 | 12.89 | 15.76 | 7.43 | 21.79 | -8.90 | 1.31 | 0.59 | 29 | 1.20 | 0 |
| Crafter_dynamic | 110 | 90 | 23.80 | 0.85 | 11.16 | 16.84 | 6.96 | 10.02 | 18.29 | -1.44 | 1.30 | 0.92 | 28 | 1.40 | 0 |
| Crafter_dynamic | 120 | 90 | 13.32 | 0.74 | 6.99 | 12.52 | 0.80 | 13.51 | 15.71 | -3.19 | 0.85 | 0.80 | 18 | 1.60 | 0 |
| Crafter_dynamic | 130 | 90 | 12.80 | 0.71 | 6.70 | 8.38 | 4.42 | 7.68 | 15.01 | -6.63 | 0.85 | 0.56 | 18 | 1.80 | 0 |
| Golf_dynamic | 50 | 90 | 7.23 | 1.81 | 3.98 | 2.00 | 5.23 | 3.83 | 3.49 | -1.49 | 2.07 | 0.57 | 4 | 0.20 | 0 |
| Golf_dynamic | 60 | 90 | 12.82 | 1.42 | 7.92 | 3.42 | 9.40 | 4.13 | 7.89 | -4.47 | 1.63 | 0.43 | 9 | 0.40 | 0 |
| Golf_dynamic | 70 | 90 | 11.67 | 1.06 | 8.14 | 4.79 | 6.88 | 8.15 | 10.62 | -5.83 | 1.10 | 0.45 | 11 | 0.60 | 0 |
| Golf_dynamic | 80 | 90 | 11.61 | 0.89 | 8.61 | 6.42 | 5.19 | 10.22 | 12.68 | -6.26 | 0.92 | 0.51 | 13 | 0.80 | 0 |
| Golf_dynamic | 90 | 90 | 8.47 | 0.77 | 5.58 | 8.56 | -0.09 | 12.96 | 11.70 | -3.14 | 0.72 | 0.73 | 11 | 1.00 | 0 |
| Golf_dynamic | 100 | 90 | 14.02 | 0.78 | 10.92 | 19.80 | -5.78 | 18.78 | 14.59 | 5.21 | 0.96 | 1.36 | 18 | 1.20 | 0 |
| Golf_dynamic | 110 | 90 | 11.34 | 0.67 | 8.71 | 19.14 | -7.80 | 24.14 | 14.72 | 4.42 | 0.77 | 1.30 | 17 | 1.40 | 0 |
| Golf_dynamic | 120 | 90 | 8.19 | 0.55 | 6.11 | 14.14 | -5.96 | 23.89 | 13.21 | 0.93 | 0.62 | 1.07 | 15 | 1.60 | 0 |
| Golf_dynamic | 130 | 90 | 9.40 | 0.55 | 7.33 | 15.23 | -5.83 | 29.03 | 15.00 | 0.23 | 0.63 | 1.02 | 17 | 1.80 | 0 |

## 2. Gộp theo lớp (trung bình 9 tốc độ)

| lớp | alive | visible | dbscan | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 21.27 | 10.31 | 10.46 | 10.81 | 7.76 | 15.15 | -4.69 | 1.40 | 0.69 |
| Golf_dynamic | 10.53 | 7.48 | 10.39 | 0.14 | 15.02 | 11.54 | -1.15 | 0.91 | 0.90 |

## 3. Kết luận cửa chặn

**Nhánh 3b (sinh cụm):** 16/18 ô có `alive` ≤ 0.7× real/frame. Cụm không được sinh đủ, ray-cast không phải chỗ mất cụm.
