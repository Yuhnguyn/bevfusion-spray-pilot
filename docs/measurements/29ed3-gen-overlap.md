# 29e-d-iii — các cụm **generator** xếp cạnh nhau (đo trên `cal`)

Sinh bằng `scripts/measure_29ed3.py`. **Chỉ đo**, không sửa generator.
3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; đường stateful `inject_plume_stateful` → `raycast_frame` (đúng đường `PlumeTransform`), đại lượng tính trên **detection sinh ra**.

- `nn` = khoảng cách tâm cụm → tâm cụm gần nhất **trong cùng frame** (m).
- `nn_norm = nn / (r_i + r_j)`, `r` = max khoảng cách điểm → tâm; `nn_norm < 1` nghĩa là hai cầu **chồng nhau**.
- `overlap_frac` = tỉ lệ cụm có `nn_norm < 1`, trên các cụm **có ít nhất một cụm khác trong frame**.
- `pts_in_overlap` = % **tổng điểm** nằm trong cụm có `nn_norm < 1`.
- `n_merged` = số cụm có `elong > 1,5`; `nn_merged` = trung vị `nn_norm` của các cụm đó.
- `Δ overlap_frac` = gen − real (điểm %).
- **Cửa chặn:** `overlap_frac` gen ≥ 40 % ⇒ giả thuyết “vùng đặt quá rộng” sai ⇒ dừng, báo PM, không sửa gì thêm.

## 1. Gộp

| nguồn | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | nn_merged |
|---|---:|---:|---:|---:|---:|---:|---:|
| real | 21623 | 62.7 % | 87.8 % | 0.684 | 0.576 | 10029 | 0.447 |
| gen | 16888 | 84.8 % | 92.0 % | 0.364 | 0.379 | 10641 | 0.320 |
| Δ | | 22.1 | 4.2 | | | | |

## 2. Theo lớp × tốc độ — real vs gen

| lớp | km/h | cụm real | cụm gen | overlap real | overlap gen | Δ overlap_frac | pts real | pts gen | median nn real (m) | median nn gen (m) | median nn_norm real | median nn_norm gen | n_merged real | n_merged gen | nn_merged real | nn_merged gen |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 405 | 264 | 11.1 % | 63.2 % | 52.1 | 9.0 % | 74.2 % | 0.358 | 0.921 | 2.821 | 0.815 | 85 | 72 | 1.479 | 0.663 |
| Crafter_dynamic | 60 | 877 | 525 | 50.1 % | 86.6 % | 36.5 | 78.6 % | 95.8 % | 0.672 | 1.055 | 0.998 | 0.353 | 347 | 247 | 0.523 | 0.330 |
| Crafter_dynamic | 70 | 1480 | 774 | 64.0 % | 89.1 % | 25.1 | 89.5 % | 96.1 % | 0.589 | 0.896 | 0.627 | 0.310 | 730 | 438 | 0.571 | 0.297 |
| Crafter_dynamic | 80 | 1456 | 892 | 65.6 % | 85.1 % | 19.5 | 85.9 % | 93.8 % | 0.700 | 0.537 | 0.560 | 0.375 | 707 | 585 | 0.439 | 0.331 |
| Crafter_dynamic | 90 | 1682 | 1460 | 63.3 % | 88.4 % | 25.1 | 87.9 % | 94.6 % | 0.734 | 0.334 | 0.530 | 0.313 | 798 | 1049 | 0.400 | 0.278 |
| Crafter_dynamic | 100 | 1961 | 1160 | 64.7 % | 85.8 % | 21.1 | 89.5 % | 94.6 % | 0.656 | 0.389 | 0.545 | 0.349 | 957 | 767 | 0.497 | 0.315 |
| Crafter_dynamic | 110 | 1646 | 1516 | 69.9 % | 89.8 % | 19.9 | 91.6 % | 94.7 % | 0.659 | 0.242 | 0.462 | 0.306 | 743 | 1078 | 0.445 | 0.251 |
| Crafter_dynamic | 120 | 1414 | 1127 | 65.1 % | 84.2 % | 19.1 | 83.8 % | 91.1 % | 0.719 | 0.279 | 0.549 | 0.368 | 638 | 739 | 0.462 | 0.282 |
| Crafter_dynamic | 130 | 1351 | 754 | 63.1 % | 77.6 % | 14.5 | 81.1 % | 84.9 % | 0.674 | 0.497 | 0.565 | 0.553 | 571 | 401 | 0.439 | 0.450 |
| Golf_dynamic | 50 | 314 | 180 | 44.3 % | 60.0 % | 15.7 | 54.3 % | 64.7 % | 0.889 | 0.797 | 1.204 | 0.840 | 146 | 55 | 0.808 | 0.684 |
| Golf_dynamic | 60 | 710 | 308 | 58.4 % | 81.7 % | 23.3 | 73.3 % | 88.0 % | 0.638 | 1.207 | 0.645 | 0.419 | 349 | 129 | 0.514 | 0.427 |
| Golf_dynamic | 70 | 956 | 431 | 63.6 % | 78.7 % | 15.1 | 88.9 % | 92.4 % | 0.692 | 1.026 | 0.537 | 0.492 | 478 | 219 | 0.428 | 0.471 |
| Golf_dynamic | 80 | 1141 | 578 | 64.2 % | 71.2 % | 7.0 | 89.5 % | 88.2 % | 0.648 | 0.675 | 0.538 | 0.555 | 578 | 309 | 0.373 | 0.472 |
| Golf_dynamic | 90 | 1053 | 770 | 63.1 % | 83.3 % | 20.2 | 87.7 % | 87.3 % | 0.728 | 0.390 | 0.518 | 0.435 | 506 | 469 | 0.422 | 0.336 |
| Golf_dynamic | 100 | 1313 | 1782 | 65.5 % | 86.8 % | 21.3 | 92.0 % | 92.4 % | 0.667 | 0.172 | 0.452 | 0.368 | 623 | 1198 | 0.361 | 0.311 |
| Golf_dynamic | 110 | 1325 | 1723 | 65.9 % | 87.6 % | 21.7 | 93.0 % | 94.3 % | 0.758 | 0.215 | 0.467 | 0.344 | 616 | 1180 | 0.368 | 0.295 |
| Golf_dynamic | 120 | 1189 | 1273 | 67.5 % | 85.8 % | 18.3 | 91.4 % | 89.9 % | 0.783 | 0.219 | 0.462 | 0.411 | 550 | 833 | 0.354 | 0.342 |
| Golf_dynamic | 130 | 1350 | 1371 | 61.3 % | 84.9 % | 23.6 | 92.0 % | 91.2 % | 0.686 | 0.223 | 0.605 | 0.404 | 607 | 873 | 0.449 | 0.327 |

## 3. Gen theo lớp (gộp 9 tốc độ) — đối chiếu §1 của `29ed2-overlap.md`

| lớp | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 8472 | 85.6 % | 93.2 % | 0.459 | 0.355 | 5376 | 63.5 % | 0.305 |
| Golf_dynamic | 8416 | 84.0 % | 90.8 % | 0.289 | 0.405 | 5265 | 62.6 % | 0.333 |

## 4. `capped` và độ phủ

| lớp | km/h | frame | capped |
|---|---:|---:|---:|
| Crafter_dynamic | 50 | 90 | 0 |
| Crafter_dynamic | 60 | 90 | 0 |
| Crafter_dynamic | 70 | 90 | 0 |
| Crafter_dynamic | 80 | 90 | 0 |
| Crafter_dynamic | 90 | 90 | 0 |
| Crafter_dynamic | 100 | 90 | 0 |
| Crafter_dynamic | 110 | 90 | 0 |
| Crafter_dynamic | 120 | 90 | 0 |
| Crafter_dynamic | 130 | 90 | 0 |
| Golf_dynamic | 50 | 90 | 0 |
| Golf_dynamic | 60 | 90 | 0 |
| Golf_dynamic | 70 | 90 | 0 |
| Golf_dynamic | 80 | 90 | 0 |
| Golf_dynamic | 90 | 90 | 0 |
| Golf_dynamic | 100 | 90 | 0 |
| Golf_dynamic | 110 | 90 | 0 |
| Golf_dynamic | 120 | 90 | 0 |
| Golf_dynamic | 130 | 90 | 0 |

## 5. Kết luận cửa chặn

`overlap_frac` gen gộp = **84.8 %**.

**DỪNG:** 18/18 ô đã ≥ 40 % (Crafter_dynamic@50, Crafter_dynamic@60, Crafter_dynamic@70, Crafter_dynamic@80, Crafter_dynamic@90, Crafter_dynamic@100, Crafter_dynamic@110, Crafter_dynamic@120, Crafter_dynamic@130, Golf_dynamic@50, Golf_dynamic@60, Golf_dynamic@70, Golf_dynamic@80, Golf_dynamic@90, Golf_dynamic@100, Golf_dynamic@110, Golf_dynamic@120, Golf_dynamic@130). Giả thuyết “vùng đặt quá rộng” **sai**; báo PM, không sửa gì thêm.
