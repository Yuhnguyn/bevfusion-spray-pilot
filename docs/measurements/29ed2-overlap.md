# 29e-d-ii — các cụm DBSCAN xếp cạnh nhau (đo trên `cal`)

Sinh bằng `scripts/measure_29ed2.py`. **Chỉ đo**, không sửa generator.
3 scene × 30 frame mỗi ô, 9 tốc độ × 2 lớp; DBSCAN góc 0,7°/minPts=3 trên điểm label 2.

- `nn` = khoảng cách tâm cụm → tâm cụm gần nhất **trong cùng frame** (m).
- `nn_norm = nn / (r_i + r_j)`, `r` = bán kính paper (max khoảng cách điểm → tâm); `nn_norm < 1` nghĩa là hai cầu **chồng nhau**.
- `overlap_frac` = tỉ lệ cụm có `nn_norm < 1`, tính trên các cụm **có ít nhất một cụm khác trong frame** (cụm lẻ không có `nn` nên không tính vào mẫu số).
- `pts_in_overlap` = % **tổng điểm** nằm trong cụm có `nn_norm < 1`.
- `n_merged` = số cụm có `elong > 1,5` (dấu hiệu DBSCAN đã gộp), kèm % trên tổng số cụm; `nn_merged` = trung vị `nn_norm` của các cụm đó.
- **Cửa chặn:** `overlap_frac` gộp < 5 % ⇒ giả thuyết chồng cụm sai, dừng và báo PM.

## 1. Gộp và theo lớp

| lớp | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gộp | 21623 | 62.7 % | 87.8 % | 0.684 | 0.576 | 10029 | 46.4 % | 0.447 |
| Crafter_dynamic | 12272 | 62.3 % | 86.4 % | 0.666 | 0.605 | 5576 | 45.4 % | 0.474 |
| Golf_dynamic | 9351 | 63.4 % | 90.3 % | 0.708 | 0.537 | 4453 | 47.6 % | 0.413 |

## 2. Theo lớp × tốc độ

| lớp | km/h | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 405 | 11.1 % | 9.0 % | 0.358 | 2.821 | 85 | 21.0 % | 1.479 |
| Crafter_dynamic | 60 | 877 | 50.1 % | 78.6 % | 0.672 | 0.998 | 347 | 39.6 % | 0.523 |
| Crafter_dynamic | 70 | 1480 | 64.0 % | 89.5 % | 0.589 | 0.627 | 730 | 49.3 % | 0.571 |
| Crafter_dynamic | 80 | 1456 | 65.6 % | 85.9 % | 0.700 | 0.560 | 707 | 48.6 % | 0.439 |
| Crafter_dynamic | 90 | 1682 | 63.3 % | 87.9 % | 0.734 | 0.530 | 798 | 47.4 % | 0.400 |
| Crafter_dynamic | 100 | 1961 | 64.7 % | 89.5 % | 0.656 | 0.545 | 957 | 48.8 % | 0.497 |
| Crafter_dynamic | 110 | 1646 | 69.9 % | 91.6 % | 0.659 | 0.462 | 743 | 45.1 % | 0.445 |
| Crafter_dynamic | 120 | 1414 | 65.1 % | 83.8 % | 0.719 | 0.549 | 638 | 45.1 % | 0.462 |
| Crafter_dynamic | 130 | 1351 | 63.1 % | 81.1 % | 0.674 | 0.565 | 571 | 42.3 % | 0.439 |
| Golf_dynamic | 50 | 314 | 44.3 % | 54.3 % | 0.889 | 1.204 | 146 | 46.5 % | 0.808 |
| Golf_dynamic | 60 | 710 | 58.4 % | 73.3 % | 0.638 | 0.645 | 349 | 49.2 % | 0.514 |
| Golf_dynamic | 70 | 956 | 63.6 % | 88.9 % | 0.692 | 0.537 | 478 | 50.0 % | 0.428 |
| Golf_dynamic | 80 | 1141 | 64.2 % | 89.5 % | 0.648 | 0.538 | 578 | 50.7 % | 0.373 |
| Golf_dynamic | 90 | 1053 | 63.1 % | 87.7 % | 0.728 | 0.518 | 506 | 48.1 % | 0.422 |
| Golf_dynamic | 100 | 1313 | 65.5 % | 92.0 % | 0.667 | 0.452 | 623 | 47.4 % | 0.361 |
| Golf_dynamic | 110 | 1325 | 65.9 % | 93.0 % | 0.758 | 0.467 | 616 | 46.5 % | 0.368 |
| Golf_dynamic | 120 | 1189 | 67.5 % | 91.4 % | 0.783 | 0.462 | 550 | 46.3 % | 0.354 |
| Golf_dynamic | 130 | 1350 | 61.3 % | 92.0 % | 0.686 | 0.605 | 607 | 45.0 % | 0.449 |

## 3. Theo 4 dải cự ly

Dải theo range của tâm cụm. `overlap_frac` tính lại trên các cụm trong dải.

| lớp | dải (m) | cụm | overlap_frac | pts_in_overlap | median nn (m) | median nn_norm | n_merged | % cụm gộp | nn_merged |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gộp | [0,15) | 20038 | 63.7 % | 88.1 % | 0.632 | 0.556 | 9405 | 46.9 % | 0.448 |
| gộp | [15,25) | 1410 | 51.4 % | 84.6 % | 2.783 | 0.911 | 569 | 40.4 % | 0.422 |
| gộp | [25,40) | 175 | 34.0 % | 45.7 % | 9.159 | 3.037 | 55 | 31.4 % | 1.170 |
| gộp | [40+ | 0 | nan % | nan % | nan | nan | 0 | 0.0 % | nan |
| Crafter_dynamic | [0,15) | 11398 | 63.8 % | 86.5 % | 0.617 | 0.570 | 5289 | 46.4 % | 0.479 |
| Crafter_dynamic | [15,25) | 785 | 44.8 % | 85.2 % | 2.747 | 1.382 | 268 | 34.1 % | 0.399 |
| Crafter_dynamic | [25,40) | 89 | 24.7 % | 43.8 % | 10.411 | 7.893 | 19 | 21.3 % | 0.954 |
| Crafter_dynamic | [40+ | 0 | nan % | nan % | nan | nan | 0 | 0.0 % | nan |
| Golf_dynamic | [0,15) | 8640 | 63.7 % | 91.0 % | 0.653 | 0.525 | 4116 | 47.6 % | 0.409 |
| Golf_dynamic | [15,25) | 625 | 60.2 % | 83.8 % | 2.877 | 0.599 | 301 | 48.2 % | 0.447 |
| Golf_dynamic | [25,40) | 86 | 44.6 % | 47.0 % | 6.242 | 1.207 | 36 | 41.9 % | 1.484 |
| Golf_dynamic | [40+ | 0 | nan % | nan % | nan | nan | 0 | 0.0 % | nan |

## 4. Đối chiếu `pts_in_overlap` với mức tập trung điểm đã đo

B2 của ticket: đối chiếu với con số **66 %** của 5 % cụm to nhất. Cùng dữ liệu, cùng cụm, chỉ khác cách chia nhóm.

| lớp | pts_in_overlap | % điểm trong 5 % cụm to nhất | 10 % | 25 % |
|---|---:|---:|---:|---:|
| gộp | 87.8 % | 65.9 % | 78.0 % | 87.7 % |
| Crafter_dynamic | 86.4 % | 64.7 % | 78.4 % | 88.9 % |
| Golf_dynamic | 90.3 % | 66.6 % | 75.6 % | 85.4 % |

## 5. `nn` theo lớp

| lớp | cụm | p10 | median | p90 | mean |
|---|---:|---:|---:|---:|---:|
| gộp | 21434 | 0.211 | 0.684 | 2.230 | 1.348 |
| Crafter_dynamic | 12195 | 0.216 | 0.666 | 2.181 | 1.308 |
| Golf_dynamic | 9239 | 0.204 | 0.708 | 2.278 | 1.401 |

## 6. Kết luận cửa chặn

`overlap_frac` gộp = **62.7 %** (ngưỡng 5 %). Giả thuyết chồng cụm **sống**; báo PM trước khi sửa generator.

`pts_in_overlap` gộp = **87.8 %** tổng điểm.
