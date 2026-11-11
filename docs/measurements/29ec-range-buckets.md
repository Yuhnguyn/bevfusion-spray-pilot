# 29e-c — plume sinh vs thật theo dải cự ly

Sinh bằng `scripts/measure_29ec.py`, đúng thứ tự bắt buộc của ticket: **bảng trước khi
sửa code sinh**, rồi mới sửa và đo lại.
3 scene × 30 frame mỗi ô, `wfh_ref = 1 mm`, DBSCAN 0,7°/minPts=3,
real = điểm label 2; gen = detection ray-cast của đường stateful đã nối (`PlumeTransform`).

## Bước 1 — trước khi sửa code sinh

| lớp | km/h | dải (m) | real_pts | gen_pts | real_cl | gen_cl | real_p50 | gen_p50 | gen_raw_det | gen_dropped |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 100 | [0,15) | 78304 | 18822 | 1839 | 1013 | 6 | 5 | 18822 | 3090 |
| Crafter_dynamic | 100 | [15,25) | 9380 | 7986 | 116 | 231 | 7 | 5 | 7986 | 601 |
| Crafter_dynamic | 100 | [25,40) | 445 | 569 | 6 | 14 | 6 | 4 | 569 | 124 |
| Crafter_dynamic | 100 | [40+ | 4 | 12 | 0 | 1 | nan | 3 | 12 | 6 |
| Crafter_dynamic | 130 | [0,15) | 59996 | 13866 | 1271 | 801 | 7 | 6 | 13866 | 1839 |
| Crafter_dynamic | 130 | [15,25) | 6493 | 4945 | 74 | 233 | 6 | 10 | 4945 | 391 |
| Crafter_dynamic | 130 | [25,40) | 417 | 737 | 6 | 41 | 6 | 6 | 737 | 100 |
| Crafter_dynamic | 130 | [40+ | 3 | 113 | 0 | 8 | nan | 4 | 113 | 16 |
| Golf_dynamic | 100 | [0,15) | 35883 | 36378 | 1251 | 2227 | 5 | 5 | 36378 | 6694 |
| Golf_dynamic | 100 | [15,25) | 3781 | 7369 | 62 | 131 | 6 | 6 | 7369 | 345 |
| Golf_dynamic | 100 | [25,40) | 106 | 618 | 0 | 6 | nan | 4 | 618 | 45 |
| Golf_dynamic | 100 | [40+ | 3 | 1 | 0 | 0 | nan | nan | 1 | 1 |
| Golf_dynamic | 130 | [0,15) | 43607 | 48770 | 1271 | 2251 | 6 | 6 | 48770 | 5097 |
| Golf_dynamic | 130 | [15,25) | 6643 | 7081 | 71 | 187 | 5 | 6 | 7081 | 291 |
| Golf_dynamic | 130 | [25,40) | 534 | 848 | 8 | 40 | 12 | 6 | 848 | 86 |
| Golf_dynamic | 130 | [40+ | 4 | 88 | 0 | 1 | nan | 4 | 88 | 16 |

## Bước 3 — sau một vòng sửa

| lớp | km/h | dải (m) | real_pts | gen_pts | real_cl | gen_cl | real_p50 | gen_p50 | gen_raw_det | gen_dropped |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 100 | [0,15) | 78304 | 14069 | 1839 | 937 | 6 | 5 | 14069 | 2817 |
| Crafter_dynamic | 100 | [15,25) | 9380 | 4738 | 116 | 202 | 7 | 6 | 4738 | 525 |
| Crafter_dynamic | 100 | [25,40) | 445 | 332 | 6 | 21 | 6 | 5 | 332 | 87 |
| Crafter_dynamic | 100 | [40+ | 4 | 9 | 0 | 0 | nan | nan | 9 | 2 |
| Crafter_dynamic | 130 | [0,15) | 59996 | 6380 | 1271 | 544 | 7 | 6 | 6380 | 1132 |
| Crafter_dynamic | 130 | [15,25) | 6493 | 2058 | 74 | 180 | 6 | 5 | 2058 | 335 |
| Crafter_dynamic | 130 | [25,40) | 417 | 344 | 6 | 26 | 6 | 6 | 344 | 97 |
| Crafter_dynamic | 130 | [40+ | 3 | 65 | 0 | 4 | nan | 5 | 65 | 22 |
| Golf_dynamic | 100 | [0,15) | 35883 | 19494 | 1251 | 1605 | 5 | 5 | 19494 | 4867 |
| Golf_dynamic | 100 | [15,25) | 3781 | 3818 | 62 | 173 | 6 | 7 | 3818 | 322 |
| Golf_dynamic | 100 | [25,40) | 106 | 391 | 0 | 4 | nan | 5 | 391 | 44 |
| Golf_dynamic | 100 | [40+ | 3 | 1 | 0 | 0 | nan | nan | 1 | 1 |
| Golf_dynamic | 130 | [0,15) | 43607 | 20976 | 1271 | 1200 | 6 | 6 | 20976 | 2426 |
| Golf_dynamic | 130 | [15,25) | 6643 | 3273 | 71 | 146 | 5 | 6 | 3273 | 239 |
| Golf_dynamic | 130 | [25,40) | 534 | 286 | 8 | 24 | 12 | 5 | 286 | 38 |
| Golf_dynamic | 130 | [40+ | 4 | 23 | 0 | 1 | nan | 3 | 23 | 5 |

## Bước 3 — nghiệm thu

### A1 — cụm/frame của mô hình (`visible = round(rate·K)` tại wfh_ref), 9 mốc × 2 lớp

Đại lượng đích của bảng `cal` (PM 29c: 'đo qua `visible_cluster_count_for_speed`').
Số cụm **sống tức thời** là đại lượng khác (cửa sổ 4T), in ở hàng dưới để đối chiếu.

| lớp | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| crafter mô hình | 4 | 11 | 17 | 22 | 21 | 29 | 28 | 18 | 18 |
| crafter bảng | 4.18 | 11.31 | 17.42 | 22.02 | 20.69 | 29.24 | 28.49 | 17.58 | 17.69 |
| crafter sống đo | 11 | 34 | 48 | 60 | 50 | 56 | 55 | 30 | 37 |
| golf mô hình | 4 | 9 | 11 | 13 | 11 | 18 | 17 | 15 | 17 |
| golf bảng | 3.62 | 8.84 | 11.36 | 12.87 | 10.51 | 18.07 | 16.69 | 15.27 | 16.64 |
| golf sống đo | 8 | 16 | 16 | 18 | 16 | 28 | 22 | 14 | 22 |

### A2-A7 — điểm/frame, p50, chiều cao, |y|, latency, capped

| lớp | km/h | điểm/frame | p50/cụm | h p5/med/p95 (m) | p95\|y\| (m) | latency med (ms) | capped |
|---|---:|---:|---:|---|---:|---:|---:|
| Crafter_dynamic | 50 | 21 | 5 | 0.612 / 1.537 / 2.270 | 2.003 | 26.4 | 0 |
| Crafter_dynamic | 60 | 100 | 5 | 0.461 / 1.204 / 1.978 | 2.515 | 43.0 | 0 |
| Crafter_dynamic | 70 | 158 | 5 | 0.430 / 1.090 / 1.815 | 2.246 | 34.2 | 54 |
| Crafter_dynamic | 80 | 156 | 4 | 0.428 / 1.175 / 2.092 | 2.433 | 44.1 | 0 |
| Crafter_dynamic | 90 | 148 | 5 | 0.392 / 0.972 / 1.893 | 2.351 | 34.4 | 0 |
| Crafter_dynamic | 100 | 251 | 5 | 0.437 / 1.028 / 2.064 | 2.140 | 32.8 | 0 |
| Crafter_dynamic | 110 | 194 | 5 | 0.466 / 1.086 / 2.011 | 2.286 | 35.4 | 0 |
| Crafter_dynamic | 120 | 98 | 6 | 0.531 / 1.183 / 2.114 | 2.227 | 26.8 | 0 |
| Crafter_dynamic | 130 | 226 | 6 | 0.430 / 0.789 / 2.030 | 2.331 | 35.0 | 0 |
| Golf_dynamic | 50 | 28 | 4 | 0.392 / 1.239 / 1.843 | 2.138 | 33.1 | 0 |
| Golf_dynamic | 60 | 26 | 4 | 0.319 / 1.138 / 1.848 | 2.518 | 33.4 | 0 |
| Golf_dynamic | 70 | 149 | 5 | 0.443 / 1.089 / 1.752 | 2.301 | 32.9 | 0 |
| Golf_dynamic | 80 | 262 | 5 | 0.384 / 0.797 / 1.565 | 2.269 | 31.5 | 0 |
| Golf_dynamic | 90 | 158 | 5 | 0.336 / 0.756 / 1.522 | 2.053 | 23.6 | 0 |
| Golf_dynamic | 100 | 228 | 5 | 0.313 / 0.654 / 1.451 | 2.406 | 33.0 | 0 |
| Golf_dynamic | 110 | 242 | 5 | 0.276 / 0.678 / 1.508 | 2.158 | 69.6 | 0 |
| Golf_dynamic | 120 | 308 | 6 | 0.399 / 0.747 / 1.552 | 2.128 | 73.2 | 0 |
| Golf_dynamic | 130 | 274 | 6 | 0.408 / 0.784 / 1.538 | 2.742 | 81.1 | 0 |
