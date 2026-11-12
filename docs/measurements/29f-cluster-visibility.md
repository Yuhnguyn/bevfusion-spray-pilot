# 29f — cụm `alive` / `visible` / `dbscan` của generator (đo trên `cal`)

Sinh bằng `scripts/measure_29f.py`. **Chỉ đo**, không sửa generator.
3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful `inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`). DBSCAN góc 0,7° / minPts = 3 (recipe paper, không đổi).

- `alive` = số cụm còn sống trong state ngay trước khi ray-cast (`state.all_alive()`), trung bình theo frame.
- `visible` = số cụm `alive` có ≥ 1 detection nằm trong cầu `|p − tâm| ≤ 1.5·r` của cụm (gán detection cho cầu gần nhất). `visible/real` = `visible` / `real/frame`.
- `h p5/med/p95` = phân vị 5 / 50 / 95 của chiều cao detection sinh ra so với mặt đường, `det_z − ROAD_Z_M` (cùng cách tính `measure_29ec.py`), gộp mọi detection của ô.
- `dbscan` = số cụm DBSCAN dựng lại từ detection của frame (≥ 3 điểm), trung bình theo frame.
- `phủ` = tổng số cụm `alive` khác nhau mà các cụm DBSCAN phủ (mỗi điểm detection gán cho cụm `alive` gần nhất); `phủ max` = cụm DBSCAN phủ nhiều cụm `alive` nhất. `phủ > dbscan` ⇒ DBSCAN **gộp** nhiều cụm thành một.
- `alive_not_dbscan = alive − dbscan` — cụm sinh ra nhưng DBSCAN không thấy.
- `det_per_alive` = số detection / số cụm `alive`.
- `real dbscan` = số cụm DBSCAN trên điểm label 2, lấy từ §2 của `29ed3-gen-overlap.md` (tổng 90 frame); `real/frame` = tổng / 90; `Δ = dbscan − real/frame`. `29ed3` báo **cụm/frame** (12,9 @100), cột `cụm real` của nó là **tổng** — so thẳng hai cột đó là lỗi đơn vị 90×.
- `alive target` = `cluster_count_for_speed_abs(v, 1 mm)` (trạng thái dừng lý thuyết); `alive/target` = `alive` đo / target; `rate` = `cluster_spawn_rate_for_speed_abs(v)`; `rate·T/Δt` = số cụm state sẽ giữ nếu **không** prune; `T` = `lifetime_mean_s(v, 1 mm)`.
- **Cửa chặn:** `alive` ≤ 0.7× real/frame ⇒ lỗi ở khâu **sinh cụm** (3b); `alive` ≈ real/frame mà `dbscan` thấp ⇒ lỗi ở **ray-cast** (3a).
- **Đơn vị của Bảng 1** (`semantic-spray-clusters-by-speed.md`): đếm **cụm DBSCAN** (0,7° / minPts = 3) trên điểm `label == 2` — cùng toán tử với `real/frame` ở đây, không phải cụm `alive` của generator. A1 so `visible_cluster_count_for_speed` (cụm **alive**) với bảng DBSCAN ⇒ A1 đạt là **trùng hợp đơn vị**, không phải bằng chứng generator khớp.
- **Lỗi đơn vị của ticket**: "12,9 cụm gen @100" là **cụm/frame** (`29ed3` §2), còn "21,8 cụm real @100" là **tổng 90 frame** của cùng bảng (§1 `29ed3` ghi `cụm gen` 1160 = 12,9 × 90) ⇒ tỉ lệ đúng là 12,9 / 21,79 = **0,59×**, không phải 12,9 / 1961.

## 1. Theo lớp × tốc độ

| lớp | km/h | frame | alive | alive/target | visible | visible/real | h p5/med/p95 (m) | dbscan | phủ | phủ max | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real | alive target | rate | rate·T/Δt | T (s) | capped |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 90 | 11.98 | 2.99 | 6.28 | 1.40 | 0.396 / 1.334 / 2.261 | 3.64 | 6.51 | 2.44 | 8.33 | 3.96 | 4.50 | -0.86 | 2.66 | 0.81 | 4 | 1.66 | 3.3 | 0.20 | 0 |
| Crafter_dynamic | 60 | 90 | 29.69 | 2.70 | 17.22 | 1.77 | 0.297 / 1.010 / 2.069 | 7.63 | 24.88 | 9.80 | 22.06 | 5.51 | 9.74 | -2.11 | 3.05 | 0.78 | 11 | 2.54 | 10.2 | 0.40 | 0 |
| Crafter_dynamic | 70 | 90 | 38.69 | 2.28 | 20.92 | 1.27 | 0.244 / 0.777 / 1.783 | 12.84 | 34.92 | 10.04 | 25.84 | 7.05 | 16.44 | -3.60 | 2.35 | 0.78 | 17 | 2.72 | 16.3 | 0.60 | 458 |
| Crafter_dynamic | 80 | 90 | 39.77 | 1.81 | 20.82 | 1.29 | 0.351 / 0.759 / 1.891 | 19.99 | 43.97 | 9.36 | 19.78 | 8.59 | 16.18 | 3.81 | 2.46 | 1.24 | 22 | 2.63 | 21.0 | 0.80 | 170 |
| Crafter_dynamic | 90 | 90 | 30.91 | 1.47 | 16.69 | 0.89 | 0.327 / 0.645 / 1.671 | 26.93 | 44.98 | 5.76 | 3.98 | 11.77 | 18.69 | 8.24 | 1.65 | 1.44 | 21 | 2.00 | 20.0 | 1.00 | 0 |
| Crafter_dynamic | 100 | 90 | 36.43 | 1.26 | 20.29 | 0.93 | 0.335 / 0.652 / 1.715 | 32.99 | 56.79 | 8.90 | 3.44 | 13.47 | 21.79 | 11.20 | 1.67 | 1.51 | 29 | 2.38 | 28.6 | 1.20 | 51 |
| Crafter_dynamic | 110 | 90 | 31.00 | 1.11 | 15.40 | 0.84 | 0.353 / 0.607 / 1.780 | 25.53 | 39.06 | 6.30 | 5.47 | 11.86 | 18.29 | 7.24 | 1.70 | 1.40 | 28 | 2.00 | 28.0 | 1.40 | 0 |
| Crafter_dynamic | 120 | 90 | 16.37 | 0.91 | 9.23 | 0.59 | 0.335 / 0.603 / 1.652 | 21.10 | 27.03 | 3.39 | -4.73 | 18.15 | 15.71 | 5.39 | 1.04 | 1.34 | 18 | 1.08 | 17.3 | 1.60 | 0 |
| Crafter_dynamic | 130 | 90 | 14.50 | 0.81 | 8.53 | 0.57 | 0.379 / 0.674 / 1.855 | 14.19 | 18.41 | 2.84 | 0.31 | 12.48 | 15.01 | -0.82 | 0.97 | 0.95 | 18 | 0.97 | 17.5 | 1.80 | 0 |
| Golf_dynamic | 50 | 90 | 11.82 | 2.96 | 5.52 | 1.58 | 0.391 / 1.172 / 1.744 | 2.27 | 4.22 | 2.01 | 9.56 | 2.56 | 3.49 | -1.22 | 3.39 | 0.65 | 4 | 1.44 | 2.9 | 0.20 | 0 |
| Golf_dynamic | 60 | 90 | 22.70 | 2.52 | 11.63 | 1.47 | 0.243 / 1.054 / 1.701 | 3.91 | 10.50 | 4.31 | 18.79 | 2.77 | 7.89 | -3.98 | 2.88 | 0.50 | 9 | 1.98 | 7.9 | 0.40 | 0 |
| Golf_dynamic | 70 | 90 | 25.20 | 2.29 | 16.88 | 1.59 | 0.309 / 0.801 / 1.591 | 8.92 | 25.06 | 8.69 | 16.28 | 7.45 | 10.62 | -1.70 | 2.37 | 0.84 | 11 | 1.77 | 10.6 | 0.60 | 0 |
| Golf_dynamic | 80 | 90 | 22.84 | 1.76 | 16.18 | 1.28 | 0.318 / 0.677 / 1.436 | 17.66 | 34.70 | 7.03 | 5.19 | 12.70 | 12.68 | 4.98 | 1.80 | 1.39 | 13 | 1.54 | 12.3 | 0.80 | 0 |
| Golf_dynamic | 90 | 90 | 15.50 | 1.41 | 10.04 | 0.86 | 0.276 / 0.631 / 1.333 | 19.27 | 27.26 | 3.59 | -3.77 | 15.35 | 11.70 | 7.57 | 1.32 | 1.65 | 11 | 1.02 | 10.2 | 1.00 | 0 |
| Golf_dynamic | 100 | 90 | 22.30 | 1.24 | 16.16 | 1.11 | 0.242 / 0.542 / 1.304 | 34.84 | 50.00 | 6.34 | -12.54 | 21.85 | 14.59 | 20.26 | 1.53 | 2.39 | 18 | 1.47 | 17.7 | 1.20 | 0 |
| Golf_dynamic | 110 | 90 | 17.67 | 1.04 | 13.09 | 0.89 | 0.261 / 0.555 / 1.212 | 34.28 | 45.87 | 4.61 | -16.61 | 29.14 | 14.72 | 19.56 | 1.20 | 2.33 | 17 | 1.17 | 16.4 | 1.40 | 0 |
| Golf_dynamic | 120 | 90 | 14.07 | 0.94 | 10.32 | 0.78 | 0.237 / 0.566 / 1.280 | 26.10 | 33.26 | 3.76 | -12.03 | 26.76 | 13.21 | 12.89 | 1.06 | 1.98 | 15 | 0.94 | 15.1 | 1.60 | 0 |
| Golf_dynamic | 130 | 90 | 13.63 | 0.80 | 10.79 | 0.72 | 0.269 / 0.557 / 1.293 | 31.08 | 39.20 | 4.81 | -17.44 | 39.86 | 15.00 | 16.08 | 0.91 | 2.07 | 17 | 0.92 | 16.5 | 1.80 | 0 |

## 2. Gộp theo lớp (trung bình 9 tốc độ)

| lớp | alive | visible | dbscan | phủ | alive_not_dbscan | det_per_alive | real/frame | Δ | alive/real | dbscan/real |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 27.70 | 15.04 | 18.32 | 32.95 | 9.39 | 10.32 | 15.15 | 3.17 | 1.83 | 1.21 |
| Golf_dynamic | 18.41 | 12.29 | 19.81 | 30.01 | -1.40 | 17.61 | 11.54 | 8.27 | 1.60 | 1.72 |

## 3. Kết luận cửa chặn

**Nhánh 3a (ray-cast):** 0/18 ô có `alive` ≤ 0.7× real/frame (không ô nào) — cụm sinh đủ, mất ở khâu ray-cast / DBSCAN.

## 4. Cơ chế đo được

- **29h:** bỏ `vz` + bỏ trần làm `alive` **tăng** ở mọi ô (vd Crafter@70: 26,5 → 38,7), tức trần cũ đã xoá một phần cụm thật. Nhưng `alive` vượt `target` xa hơn (2,3–3,0× ở 50–70 km/h) vì `T ~ N(T, 0,2 s)` kẹp ≥ 0 cho đuôi sống tới ~5,6·T, và `visible/real` > 1,25 ở 50–80 km/h ⇒ số cụm **nhìn thấy** vượt nhãn thật.
- `visible` / `alive` ≈ 0,47 (Crafter) và 0,71 (Golf): mỗi cụm chỉ có `det_per_alive` ≈ 4–29 detection, trong khi DBSCAN cần ≥ 3 điểm **và** 3 điểm đó phải nằm trong 0,7° của nhau.
- `dbscan` (chỉ detection) ≈ 0,52–0,92× real/frame với Crafter, 0,43–0,73× với Golf ở 50–90 km/h, nhưng **> 1×** với Golf ở 100–130 km/h — cột `phủ` giải thích: `phủ` luôn > `dbscan` (ví dụ Crafter@60: 17,3 cụm `alive` bị 5,8 cụm DBSCAN gộp, có cụm DBSCAN phủ 7,6 cụm) ⇒ DBSCAN **gộp** nhiều cụm thành một. Detection của một cụm nằm rải trong ~1,5·r quanh tâm (p50 0,33–0,61 m), trong khi `eps = 0,7°` ở 10–20 m chỉ là 0,12–0,24 m ⇒ cụm 0,3 m **không tách được** thành một cụm DBSCAN riêng. Vì vậy `dbscan` là **cận dưới** của số cụm generator, không phải phép đếm 1-1.
- **Ảnh ghép không dùng được**: đo riêng 3 frame Crafter@100, DBSCAN trên `real_points` + detection (đúng đầu vào `PlumeTransform`) cho 21–29 cụm, trong đó **điểm thật một mình đã 12–20 cụm** (mưa, phản xạ, điểm trên xe) ⇒ phần lớn cụm DBSCAN ở ảnh ghép **không phải** cụm plume.

## 5. Tiêu chí 29h (F1–F3)

- **F1** `alive/target` ∈ [0.95, 1.05] ở 9 mốc × 2 lớp.
- **F2** `visible/real` ∈ [0.75, 1.25] ở 9 mốc × 2 lớp.
- **F3** `h p5/med/p95` = 0,111 / 1,197 / 2,264 ± 0.2 m (A4 của 29e-d), tính **gộp** mọi detection của cả 18 ô (mỗi ô 90 frame) để cùng đơn vị với A4.

| tiêu chí | đạt | trượt |
|---|---|---|
| F1 alive/target | 1/18 | Crafter_dynamic@50 (2.99), Crafter_dynamic@60 (2.70), Crafter_dynamic@70 (2.28), Crafter_dynamic@80 (1.81), Crafter_dynamic@90 (1.47), Crafter_dynamic@100 (1.26), Crafter_dynamic@110 (1.11), Crafter_dynamic@120 (0.91), Crafter_dynamic@130 (0.81), Golf_dynamic@50 (2.96), Golf_dynamic@60 (2.52), Golf_dynamic@70 (2.29), Golf_dynamic@80 (1.76), Golf_dynamic@90 (1.41), Golf_dynamic@100 (1.24), Golf_dynamic@120 (0.94), Golf_dynamic@130 (0.80) |
| F2 visible/real | 7/18 | Crafter_dynamic@50 (1.40), Crafter_dynamic@60 (1.77), Crafter_dynamic@70 (1.27), Crafter_dynamic@80 (1.29), Crafter_dynamic@120 (0.59), Crafter_dynamic@130 (0.57), Golf_dynamic@50 (1.58), Golf_dynamic@60 (1.47), Golf_dynamic@70 (1.59), Golf_dynamic@80 (1.28), Golf_dynamic@130 (0.72) |

`h` gộp 18 ô (median của phân vị từng ô): **0.314 / 0.663 / 1.686** vs 0.111 / 1.197 / 2.264.

| F3 p5 | F3 med | F3 p95 | lệch p95 lớn nhất một ô | cửa chặn (>0.35 m) |
|---|---|---|---|---|
| 0.203 | -0.534 | -0.578 | 1.052 | DỪNG |
