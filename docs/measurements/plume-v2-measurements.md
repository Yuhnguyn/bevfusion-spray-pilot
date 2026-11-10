# Plume v2 — số đo 0 GPU (ticket 25)

> **Phạm vi:** 5 section dưới là số đo **0 GPU của ticket 25** (tốc độ, beam, quỹ đạo ego,
> hình học frame, hằng số). Hai file đo **mới hơn** không nằm trong đây:
> `docs/measurements/plume-geometry-measurements.md` (hình học plume thật vs mô phỏng) và
> `docs/reference/paper-qa-notebooklm.md` (paper nói gì). Đọc cả ba trước khi chốt tham số.

File này do 4 script sinh ra; mỗi section nằm giữa cặp marker
`<!-- BEGIN <script> -->` … `<!-- END <script> -->` và được **thay**, không nối thêm.
Chạy lại bất kỳ script nào cũng cho đúng cùng nội dung (idempotent).

```bash
/opt/anaconda3/bin/python scripts/measure_speeds.py
/opt/anaconda3/bin/python scripts/measure_beam_angles.py
/opt/anaconda3/bin/python scripts/measure_ego_motion.py
/opt/anaconda3/bin/python scripts/verify_frame_geometry.py
```

Tag: `[ĐO]` đo trên máy này · `[PAPER]` spec nhà sản xuất · `[CHỌN]` giả định
của dự án, không suy ra từ nguồn · `[tính toán]` số suy ra từ công thức đã dẫn.

<!-- BEGIN measure_speeds.py -->
## 1. Tốc độ, cự ly và mức nước — `measure_speeds.py`

Đọc **toàn bộ 207** `metadata.txt` (mỗi scene 1 dòng dữ liệu). Vận tốc lấy **trực tiếp** từ metadata, không suy từ `poses.txt`.

### Tổng quan dữ liệu `[ĐO measure_speeds.py]`

| Nhóm | Scene | Frame |
|---|---:|---:|
| `Crafter_dynamic` | 108 | 8.930 |
| `Golf_dynamic` | 99 | 8.489 |
| **Tổng** | **207** | **17.419** |

`[ĐO measure_speeds.py]` Số frame = số file `velodyne/*.bin`; mỗi frame có đúng một `labels/*.label` cùng số điểm.

### `object_velocity` — histogram bin 10 km/h `[ĐO measure_speeds.py]`

| Bin (km/h) | Scene | % scene | Frame | % frame |
|---|---:|---:|---:|---:|
| 50–59 | 24 | 11.59 | 2.844 | 16.33 |
| 60–69 | 24 | 11.59 | 2.107 | 12.10 |
| 70–79 | 24 | 11.59 | 1.981 | 11.37 |
| 80–89 | 20 | 9.66 | 1.650 | 9.47 |
| 90–99 | 19 | 9.18 | 1.347 | 7.73 |
| 100–109 | 24 | 11.59 | 1.564 | 8.98 |
| 110–119 | 24 | 11.59 | 2.213 | 12.70 |
| 120–129 | 24 | 11.59 | 1.884 | 10.82 |
| 130–139 | 24 | 11.59 | 1.829 | 10.50 |
| **Tổng** | **207** | **100.00** | **17.419** | **100.00** |

### `ego_velocity` — histogram bin 10 km/h `[ĐO measure_speeds.py]`

| Bin (km/h) | Scene | % scene | Frame | % frame |
|---|---:|---:|---:|---:|
| 50–59 | 24 | 11.59 | 2.844 | 16.33 |
| 60–69 | 24 | 11.59 | 2.107 | 12.10 |
| 70–79 | 24 | 11.59 | 1.981 | 11.37 |
| 80–89 | 20 | 9.66 | 1.650 | 9.47 |
| 90–99 | 19 | 9.18 | 1.347 | 7.73 |
| 100–109 | 24 | 11.59 | 1.564 | 8.98 |
| 110–119 | 24 | 11.59 | 2.213 | 12.70 |
| 120–129 | 24 | 11.59 | 1.884 | 10.82 |
| 130–139 | 24 | 11.59 | 1.829 | 10.50 |
| **Tổng** | **207** | **100.00** | **17.419** | **100.00** |

`[ĐO measure_speeds.py]` `object_velocity == ego_velocity` ở **207/207** scene (0 scene lệch). Hai histogram vì vậy trùng nhau.

### `distance_to_object` `[ĐO measure_speeds.py]`

| Cự ly (m) | Scene | % scene | Frame | % frame |
|---|---:|---:|---:|---:|
| 20.0 | 103 | 49.76 | 8.670 | 49.77 |
| 30.0 | 104 | 50.24 | 8.749 | 50.23 |

### `itr_after_water` `[ĐO measure_speeds.py]`

`itr_after_water` là **biến điều khiển mức nước** của SemanticSpray (số iteration sau khi tưới), không phải `wfh` (paper: **mm**).

| `itr_after_water` | Scene | % scene | Frame | % frame |
|---:|---:|---:|---:|---:|
| 1 | 36 | 17.39 | 2.587 | 14.85 |
| 2 | 34 | 16.43 | 2.966 | 17.03 |
| 3 | 34 | 16.43 | 2.710 | 15.56 |
| 4 | 34 | 16.43 | 2.944 | 16.90 |
| 5 | 34 | 16.43 | 2.945 | 16.91 |
| 6 | 35 | 16.91 | 3.267 | 18.76 |

### `object_name` `[ĐO measure_speeds.py]`

| Xe dẫn | Scene | % scene |
|---|---:|---:|
| Crafter | 108 | 52.17 |
| Golf | 99 | 47.83 |
| Khác | 0 | 0.00 |

### Ngưỡng kích hoạt `[ĐO measure_speeds.py]`

| Ngưỡng | Scene | % trên 207 | Frame | % trên 17.419 |
|---|---:|---:|---:|---:|
| `object_velocity ≥ 40` (kích hoạt) | 207 | 100.00 | 17.419 | 100.00 |
| `object_velocity ≥ 50` (paper) | 207 | 100.00 | 17.419 | 100.00 |
| `object_velocity < 40` | 0 | 0.00 | 0 | 0.00 |

### Frame sẽ không sinh spray `[ĐO measure_speeds.py]`

Công thức số cụm `[CODE] dee.cpp:509–512`: `mean = (0,2·wfh + 0,1)·(v_kmh − 50)`; `count = round(max(0, mean))`.

| Điều kiện | Frame | % frame | Cụm/frame |
|---|---:|---:|---:|
| `v < 50` (dưới ngưỡng paper) | 0 | 0.00 | 0 |
| `v = 50` (đúng offset) | 2.844 | 16.33 | 0 với mọi `wfh > 0` |
| `v > 50` | 14.575 | 83.67 | > 0 |

`[ĐO measure_speeds.py]` **Ràng buộc trần dữ liệu:** **0.00 %** frame có `object_velocity < 50` (0/17.419). Toàn bộ 207 scene nằm trong dải **50–130 km/h**, nên ngưỡng 50 km/h **không** loại frame nào. Nhưng **16.33 %** frame ở **đúng 50 km/h** vẫn cho `mean = (0,2·wfh + 0,1)·(50 − 50) = 0` cụm, tức **0 điểm spray** dù đã vượt ngưỡng kích hoạt 40 km/h.

`[ĐO measure_speeds.py]` Không scene nào có `object_velocity` dưới 40 hoặc trên 130 km/h; không có bin 0–39 km/h.
<!-- END measure_speeds.py -->

<!-- BEGIN measure_beam_angles.py -->
## 2. Góc elevation và ý nghĩa 5 cột `velodyne` — `measure_beam_angles.py`

### Cảm biến của dataset

- README của SemanticSpray ghi cảm biến là **Velodyne VLP-32C** (`https://github.com/uulm-mrm/semantic_spray_dataset`), không phải HDL-32E. Ticket 25 ghi HDL-32E; bảng HDL-32E vẫn được liệt kê đầy đủ bên dưới để đối chiếu, nhưng **bảng dùng để kiểm chéo là VLP-32C** vì đó là cảm biến thật của `velodyne/*.bin`.

### Bảng 32 góc danh nghĩa `[PAPER]`

- VLP-32C: Velodyne VLP-32C User Manual 63-9325 Rev. D, **Table 9-2** (`https://data.ouster.io/downloads/velodyne/user-manual/vlp-32c-revd-user-manual.pdf`).
- HDL-32E: Velodyne HDL-32E datasheet 97-0038 Rev. N, FOV `+10,67° … −30,67°`, bước `1,33°` (`https://www.mapix.com/wp-content/uploads/2018/07/97-0038_Rev-M_-HDL-32E_Datasheet_Web.pdf`).

| Laser ID | VLP-32C (°) | Nguồn VLP-32C | HDL-32E (°) | Nguồn HDL-32E |
|---:|---:|---|---:|---|
| 0 | -25.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -30.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 1 | -1.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -29.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 2 | -1.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -28.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 3 | -15.639 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -26.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 4 | -11.310 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -25.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 5 | 0.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -24.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 6 | -0.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -22.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 7 | -8.843 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -21.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 8 | -7.254 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -20.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 9 | 0.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -18.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 10 | -0.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -17.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 11 | -6.148 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -16.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 12 | -5.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -14.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 13 | 1.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -13.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 14 | 0.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -12.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 15 | -4.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -10.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 16 | -4.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -9.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 17 | 1.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -8.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 18 | 1.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -6.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 19 | -3.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -5.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 20 | -3.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -4.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 21 | 3.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -2.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 22 | 2.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | -1.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 23 | -2.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 0.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 24 | -3.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 1.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 25 | 7.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 2.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 26 | 4.667 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 4.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 27 | -2.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 5.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 28 | -2.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 6.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 29 | 15.000 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 8.00 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 30 | 10.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 9.33 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |
| 31 | -1.333 | [PAPER] Velodyne VLP-32C User Manual 63-9325 Rev. D, Table 9-2 | 10.67 | [PAPER] Velodyne HDL-32E datasheet 97-0038 Rev. N (FOV +10,67…−30,67; bước 1,33°) |

### 5 cột của `velodyne/*.bin` `[ĐO measure_beam_angles.py]`

Đo trên **60 frame** thuộc **6 scene** (3 Crafter + 3 Golf, 10 frame/scene, chọn đều theo chỉ số): `Crafter_dynamic/0000_2021-09-08-14-36-56_0`, `Crafter_dynamic/0054_2021-09-08-16-19-50_0`, `Crafter_dynamic/0107_2021-09-08-18-04-20_0`, `Golf_dynamic/0000_2021-09-08-08-27-59_0`, `Golf_dynamic/0058_2021-09-08-10-16-15_0`, `Golf_dynamic/0107_2021-09-08-12-06-10_0`.

| Cột | Nội dung | Bằng chứng số |
|---:|---|---|
| 0, 1, 2 | `x, y, z` (m) | `z` của điểm mặt đường (label 0, `\|x\|,\|y\| < 20 m`) có percentile 1 = `−0,411 m`; box thật cao `2,62 m` (xem `verify_frame_geometry.py`) |
| 3 | **intensity** (0–255) | min `0`, max `249`, p1 `0`, p50 `11`, p99 `74`; 88–113 giá trị phân biệt mỗi frame; 0 giá trị không nguyên |
| 4 | **ring / beam id** `0…31` | union qua mẫu = `0…31` (32 giá trị); mỗi frame có 23–31 ring (median 27); 0 giá trị không nguyên |

`[ĐO measure_beam_angles.py]` Cột 4 là **ring id**, không phải intensity hay cột thời gian: giá trị nguyên `0…31`; các ring chính `0–14` có ~1.300–1.800 điểm/frame và phủ gần đủ 360° azimuth (xem bảng dưới).

### Phân bố ring và elevation quan sát `[ĐO measure_beam_angles.py]`

`elevation = atan2(z, sqrt(x² + y²))` tính từ chính toạ độ điểm. `obs median` là median của median từng frame (robust với outlier).

| Ring | n_frame | n_điểm | az bin/ frame (median) | obs median (°) | p25 | p75 | VLP-32C cùng ID (°) | Δ cùng ID (°) | Gần nhất (°) | Δ gần nhất (°) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 60 | 98,776 | 35/36 | -4.064 | -4.166 | -3.944 | -25.000 | +20.936 | -4.000 | -0.064 |
| 1 | 60 | 106,957 | 36/36 | -2.593 | -2.702 | -2.516 | -1.000 | -1.593 | -2.667 | +0.074 |
| 2 | 60 | 106,780 | 36/36 | -1.966 | -2.037 | -1.881 | -1.667 | -0.299 | -2.000 | +0.034 |
| 3 | 60 | 106,638 | 36/36 | -1.330 | -1.397 | -1.239 | -15.639 | +14.309 | -1.333 | +0.003 |
| 4 | 60 | 104,985 | 36/36 | -1.054 | -1.141 | -0.941 | -11.310 | +10.256 | -1.000 | -0.054 |
| 5 | 60 | 103,759 | 36/36 | -0.662 | -0.743 | -0.545 | 0.000 | -0.662 | -0.667 | +0.005 |
| 6 | 60 | 97,794 | 36/36 | -0.557 | -0.642 | -0.464 | -0.667 | +0.110 | -0.667 | +0.110 |
| 7 | 60 | 99,637 | 36/36 | -0.424 | -0.529 | -0.347 | -8.843 | +8.419 | -0.333 | -0.091 |
| 8 | 60 | 98,696 | 36/36 | -0.276 | -0.356 | -0.184 | -7.254 | +6.978 | -0.333 | +0.057 |
| 9 | 60 | 96,966 | 36/36 | -0.213 | -0.299 | -0.115 | 0.333 | -0.546 | -0.333 | +0.120 |
| 10 | 60 | 94,938 | 36/36 | -0.195 | -0.260 | -0.107 | -0.333 | +0.138 | -0.333 | +0.138 |
| 11 | 60 | 97,239 | 36/36 | -0.223 | -0.296 | -0.146 | -6.148 | +5.925 | -0.333 | +0.110 |
| 12 | 60 | 99,380 | 36/36 | -0.008 | -0.067 | 0.092 | -5.333 | +5.325 | 0.000 | -0.008 |
| 13 | 60 | 94,006 | 36/36 | -0.025 | -0.075 | 0.067 | 1.333 | -1.358 | 0.000 | -0.025 |
| 14 | 60 | 96,544 | 36/36 | 0.016 | -0.047 | 0.080 | 0.667 | -0.651 | 0.000 | +0.016 |
| 15 | 60 | 80,356 | 36/36 | -0.103 | -0.201 | -0.014 | -4.000 | +3.897 | 0.000 | -0.103 |
| 16 | 60 | 73,960 | 33/36 | 0.069 | -0.011 | 0.183 | -4.667 | +4.736 | 0.000 | +0.069 |
| 17 | 60 | 56,665 | 29/36 | 0.064 | -0.021 | 0.186 | 1.667 | -1.603 | 0.000 | +0.064 |
| 18 | 60 | 45,869 | 25/36 | -0.040 | -0.174 | 0.095 | 1.000 | -1.040 | 0.000 | -0.040 |
| 19 | 60 | 23,488 | 18/36 | -0.146 | -0.215 | 0.009 | -3.667 | +3.521 | 0.000 | -0.146 |
| 20 | 60 | 13,599 | 13/36 | 0.130 | -0.021 | 0.369 | -3.333 | +3.463 | 0.000 | +0.130 |
| 21 | 60 | 5,673 | 8/36 | 0.543 | 0.297 | 1.376 | 3.333 | -2.790 | 0.667 | -0.124 |
| 22 | 60 | 2,159 | 5/36 | 2.037 | 0.694 | 2.985 | 2.333 | -0.296 | 2.333 | -0.296 |
| 23 | 58 | 799 | 2/36 | 3.072 | 2.372 | 3.174 | -2.667 | +5.739 | 3.333 | -0.261 |
| 24 | 52 | 910 | 3/36 | 3.454 | 3.332 | 4.660 | -3.000 | +6.454 | 3.333 | +0.121 |
| 25 | 55 | 1,024 | 3/36 | 3.819 | 3.647 | 5.047 | 7.000 | -3.181 | 3.333 | +0.486 |
| 26 | 45 | 340 | 2/36 | 4.430 | 4.039 | 5.669 | 4.667 | -0.237 | 4.667 | -0.237 |
| 27 ⚠ | 10 | 19 | 1/36 | 5.557 | 4.222 | 15.171 | -2.333 | +7.890 | 4.667 | +0.890 |
| 28 ⚠ | 8 | 12 | 1/36 | 19.815 | 15.633 | 21.039 | -2.000 | +21.815 | 15.000 | +4.815 |
| 29 ⚠ | 13 | 30 | 1/36 | 28.471 | 18.590 | 34.871 | 15.000 | +13.471 | 15.000 | +13.471 |
| 30 ⚠ | 14 | 15 | 1/36 | 12.976 | 12.548 | 20.574 | 10.333 | +2.643 | 15.000 | -2.024 |
| 31 ⚠ | 3 | 3 | 1/36 | 24.049 | 20.282 | 35.041 | -1.333 | +25.382 | 15.000 | +9.049 |

⚠ = ring có mặt ở **< 30/60 frame** (mẫu thưa; median kém tin cậy).

### Kết luận kiểm chéo `[ĐO measure_beam_angles.py]`

- **Theo cùng ring ID** (kiểm tra ring id có đúng là Laser ID của manual): median `|Δ| = 3.49°`, max `25.38°`, **27/32** ring lệch `≥ 0,5°` → **KHÔNG KHỚP**. Chỉ xét 27 ring có mặt ở ≥ 30/60 frame: median `|Δ| = 3.18°`, max `20.94°`, 22/27 ring lệch `≥ 0,5°`.
- Không phải lệch hằng số do nghiêng frame: `Δ cùng ID` trải từ `-3.18°` đến `+25.38°`.
- **Theo tiêu chí "góc danh nghĩa gần nhất"** (đúng chữ của ticket): median `|Δ| = 0.11°` `< 0,5°` ⇒ *khớp về độ lớn*, max `13.47°` (các ring 27–31 thưa điểm). Nhưng con số nhỏ này **chỉ vì bảng VLP-32C dày** quanh đường chân trời (bước ~0,33°), không chứng minh ring id trùng Laser ID: ring `0` quan sát `-4.06°` nhưng Laser ID `0` danh nghĩa `−25,00°`; ring `3` quan sát `-1.33°` nhưng Laser ID `3` danh nghĩa `−15,64°`.
- **Nếu dùng bảng HDL-32E** (ticket ghi tên cảm biến này): median `|Δ| = 13.23°`, max `26.74°`, 30/32 ring lệch `≥ 0,5°` → cũng **KHÔNG KHỚP**; dataset là VLP-32C theo README.
- **Không sửa bảng góc, không suy ra cảm biến khác.** Kết luận cho bước ray casting: **không dùng ring id làm góc elevation**; phải tính `atan2(z, sqrt(x² + y²))` từ toạ độ điểm của chính frame đó.
<!-- END measure_beam_angles.py -->

<!-- BEGIN measure_ego_motion.py -->
## 3. Quỹ đạo ego từ `poses.txt` — `measure_ego_motion.py`

### Scene được chọn `[ĐO measure_ego_motion.py]`

| Scene | Nhóm | Vì sao chọn | Frame | `object_velocity` | `ego_velocity` | `distance_to_object` | `itr_after_water` |
|---|---|---|---:|---:|---:|---:|---:|
| `Crafter_dynamic/0000_2021-09-08-14-36-56_0` | Crafter_dynamic | 1 scene Crafter | 76 | 50 km/h | 50 km/h | 20.0 m | 1 |
| `Golf_dynamic/0000_2021-09-08-08-27-59_0` | Golf_dynamic | 1 scene Golf | 128 | 50 km/h | 50 km/h | 20.0 m | 1 |
| `Golf_dynamic/0096_2021-09-08-11-51-15_0` | Golf_dynamic | `object_velocity` cao nhất (130 km/h) | 53 | 130 km/h | 130 km/h | 20.0 m | 1 |

### Định dạng `poses.txt` `[ĐO measure_ego_motion.py]`

- Mỗi dòng **16 float** = ma trận 4×4 **row-major**; 3×3 đầu là rotation, cột 4 là tịnh tiến (`x = phần tử 3`, `y = 7`, `z = 11`).
- Kiểm tra trực giao: `max |R·Rᵀ − I|` trên frame đầu của cả 3 scene = `2.2e-16`.
- **Không có timestamp** trong file; mỗi scene có số frame khác nhau.
- `[ĐO measure_ego_motion.py]` **Toàn bộ 207 scene**: max `|tịnh tiến|` = `0.000000 m` (cột 3, 7, 11 và 12–15). Vì vậy `x = y = 0` ở mọi frame; chỉ `yaw` thay đổi.

### Quỹ đạo và tốc độ `[ĐO measure_ego_motion.py]`

`[CHỌN]` Giả định tần số **10 Hz** ⇒ `Δt = 0.1 s`, vì file không có timestamp. Mọi số `°/s` và `m/s` dưới đây phụ thuộc giả định này.

| Scene | Frame | max\|tịnh tiến\| (m) | x range (m) | y range (m) | yaw đầu (°) | yaw cuối (°) | Δyaw (°) | median \|yaw rate\| (°/s) | p90 \|yaw rate\| (°/s) |
|---|---:|---:|---|---|---:|---:|---:|---:|---:|
| `0000_2021-09-08-14-36-56_0` | 76 | 0.000000 | [0.000000, 0.000000] | [0.000000, 0.000000] | 108.370 | 107.900 | -0.470 | 0.100 | 0.200 |
| `0000_2021-09-08-08-27-59_0` | 128 | 0.000000 | [0.000000, 0.000000] | [0.000000, 0.000000] | 108.150 | 107.850 | -0.300 | 0.100 | 0.300 |
| `0096_2021-09-08-11-51-15_0` | 53 | 0.000000 | [0.000000, 0.000000] | [0.000000, 0.000000] | 108.140 | 107.360 | -0.780 | 0.400 | 0.900 |

### Kiểm chéo tốc độ với `metadata.txt` `[ĐO measure_ego_motion.py]`

| Scene | `ego_velocity` metadata (km/h) | metadata (m/s) | speed từ vị trí (m/s) | sai lệch | Kết quả |
|---|---:|---:|---:|---:|---|
| `0000_2021-09-08-14-36-56_0` | 50 | 13.889 | 0.000 | 100.00 % | **KHÔNG ĐẠT** |
| `0000_2021-09-08-08-27-59_0` | 50 | 13.889 | 0.000 | 100.00 % | **KHÔNG ĐẠT** |
| `0096_2021-09-08-11-51-15_0` | 130 | 36.111 | 0.000 | 100.00 % | **KHÔNG ĐẠT** |

`[ĐO measure_ego_motion.py]` Speed suy từ vị trí = **0,000 m/s** ở cả 3 scene vì cột tịnh tiến đúng bằng 0; sai lệch **100 %** so với metadata ⇒ **KHÔNG ĐẠT** ngưỡng < 10 %.

**Giả thuyết (không tự đổi công thức):**

1. Bản release này **chỉ lưu rotation**, cột tịnh tiến bị zero hoá; không phải lỗi đơn vị (giá trị đúng bằng 0, không phải bị chia 1000).
2. `poses.txt` **không có timestamp**; `Δt = 0,1 s` là giả định `[CHỌN]` từ 10 Hz, không đọc được từ dữ liệu.
3. Không có frame skip: số dòng `poses.txt` = số file `velodyne/*.bin` ở cả 3 scene.

**Kiểm chéo phụ (không dùng để thay tốc độ):** box xe dẫn trong `object_labels/lidar` gần như đứng yên tương đối với ego:

| Scene | Vận tốc tương đối từ box (km/h) | `\|object − ego\|` metadata (km/h) |
|---|---:|---:|
| `0000_2021-09-08-14-36-56_0` | 1.18 | 0 |
| `0000_2021-09-08-08-27-59_0` | 0.27 | 0 |
| `0096_2021-09-08-11-51-15_0` | 6.26 | 0 |

Box giữ khoảng cách gần như cố định (vận tốc tương đối đo được `≤ 6.26 km/h`, tức `≤ 4.8 %` tốc độ ego ở scene nhanh nhất), phù hợp `object_velocity = ego_velocity` trong metadata **trong sai số annotation**; nhưng đây **không** phải phép đo vận tốc tuyệt đối của ego (thiếu tịnh tiến trong `poses.txt`).

### CSV xuất ra `[ĐO measure_ego_motion.py]`

| Scene | File |
|---|---|
| `0000_2021-09-08-14-36-56_0` | `docs/figs/ego-motion/0000_2021-09-08-14-36-56_0.csv` |
| `0000_2021-09-08-08-27-59_0` | `docs/figs/ego-motion/0000_2021-09-08-08-27-59_0.csv` |
| `0096_2021-09-08-11-51-15_0` | `docs/figs/ego-motion/0096_2021-09-08-11-51-15_0.csv` |

Cột `frame,x,y,yaw_deg`. `x` và `y` bằng `0,000000` ở mọi dòng vì tịnh tiến trong `poses.txt` bằng 0; `yaw_deg` lấy từ rotation.
<!-- END measure_ego_motion.py -->

<!-- BEGIN verify_frame_geometry.py -->
## 4. Hình học frame thật — `verify_frame_geometry.py`

Frame: `Crafter_dynamic/0000_2021-09-08-14-36-56_0/000000`.

- Điểm: **29178**; nhãn: **29178**; cùng độ dài.
- Nhãn: `0` = 28832 điểm, `1` = 299 điểm, `2` = 47 điểm.

### `z` mặt đường `[ĐO verify_frame_geometry.py]`

Mask: `label == 0` **và** `|x| < 20 m` **và** `|y| < 20 m` → **13324 điểm**.

| Percentile | `z` (m) |
|---|---:|
| p1 | -0.411 |
| p5 | -0.372 |
| p50 | -0.276 |

`[CHỌN verify_frame_geometry.py]` Dùng **percentile 1 = -0.411 m** để neo plume v2 vào mặt đường: đây là mép dưới của mặt đường, ít bị đẩy lên bởi điểm nhiễu phía trên; p5 chỉ cao hơn `0.039 m`. Kiểm chứng độc lập: đáy box thật `center_z − size_z/2 = -0.4113 m`, khớp p1 trong `0.0003 m`.

- So với `−1,84 m` mà audit v1 dùng cho nuScenes LIDAR_TOP: chênh **`+1.429 m`** (mặt đường SemanticSpray **cao hơn**). Đây là hai cảm biến/hai frame khác nhau; số `−1,84 m` không phải số đo trên SemanticSpray.

### 3 object thật trong `object_labels/lidar` `[ĐO verify_frame_geometry.py]`

- `object_labels/lidar` có ở **36/207 scene** của dataset; scene này **có**, 76/76 frame, mỗi frame 1 instance `Van`. Ba frame dưới đây in nguyên JSON (không suy từ nuScenes).

| Frame | Class | center `(x, y, z)` (m) | size3D `(x, y, z)` (m) | rotation.z | pointN |
|---|---|---|---|---:|---:|
| `000000` | Van | (23.2387, -0.1798, 0.8990) | (6.8268, 2.4183, 2.6206) | -0.0440 | 303 |
| `000001` | Van | (23.2583, -0.1737, 0.8915) | (6.8268, 2.4183, 2.6206) | -0.0411 | 334 |
| `000057` | Van | (24.9441, -0.0410, 0.8374) | (6.8268, 2.4183, 2.6206) | -0.0207 | 292 |

### Thứ tự cột và đơn vị của box `[ĐO verify_frame_geometry.py]`

- `size3D.x = 6.8268 m` = **chiều dài** (dọc theo yaw); `size3D.y = 2.4183 m` = **chiều rộng**; `size3D.z = 2.6206 m` = **chiều cao**. Đơn vị **mét**.
- Bằng chứng từ chính điểm label 1 quanh box (frame `000000`): **298 điểm**, chiếu vào hệ box (yaw = `-0.0440 rad`):

| Trục box | extent quan sát (m) | nửa kích thước box (m) | Kết luận |
|---|---:|---:|---|
| x (dài) | `[-3.44, 1.39]` | `±3.41` | khớp chiều dài |
| y (rộng) | `[-0.97, 1.36]` | `±1.21` | khớp chiều rộng |
| z (cao) | `[-0.90, 1.58]` | `±1.31` | khớp chiều cao |

Điểm label 1 chỉ thấy mặt sau/trái của xe nên extent không đối xứng; độ lớn khớp `x ≈ ±3,41 m`, `y ≈ ±1,21 m`, `z ≈ ±1,31 m`. Nếu hoán đổi `x`/`y` thì chiều dài `6,83 m` sẽ nằm trên trục ngang — không khớp dữ liệu.

- `rotation3D.z = -0.0440`: script dùng trực tiếp giá trị này như **radian**; toolkit gốc lại gọi `np.deg2rad(rotation3D["z"])`. Ở góc nhỏ này hai cách cho cùng kết luận `w`/`l`, nhưng đơn vị của trường là **điểm mở**, không sửa ở đây.
<!-- END verify_frame_geometry.py -->

<!-- BEGIN conclusion -->
## Kết luận cho v2

- **Trần dữ liệu:** `0.00 %` frame có `object_velocity < 50` (`0/17419`); thêm `16.33 %` (`2844` frame) ở **đúng 50 km/h** cho `mean = (0,2·wfh + 0,1)·(50 − 50) = 0` cụm. `[ĐO measure_speeds.py]`

- **Cột 4 của `velodyne`:** là **ring/beam id `0…31`** (32 giá trị nguyên); so cùng ID với bảng VLP-32C lệch median `|Δ| = 3.49°`, max `25.38°`, `27/32` ring `≥ 0,5°` → **KHÔNG KHỚP** (góc gần nhất chỉ lệch median `0.11°`, nhưng đó chỉ vì bảng danh nghĩa dày). ⇒ ray casting **phải tính elevation từ toạ độ** `atan2(z, √(x²+y²))`, không dùng ring làm góc. `[ĐO measure_beam_angles.py]`

- **Đơn vị `wfh`:** ở `v = 130 km/h`, `mean = (0,2·wfh + 0,1)·80`; `wfh = 0,001` (m) → `mean = 8.016` → **8 cụm**; `wfh = 1` (mm) → `mean = 24.0` → **24 cụm** (khớp 24 cụm @130 km/h của Fig. 11b); `wfh = 10` → `mean = 168.0` → **168 cụm**. ⇒ chọn **mm** (`wfh = 1`). `[tính toán; công thức [CODE] dee.cpp:509–512; mốc 24 cụm [PAPER] Fig. 11b]`

- **`z` mặt đường:** `-0.411 m` (percentile **1**, label 0, `|x|,|y| < 20 m`; p5 = `-0.372 m`); so với `−1,84 m` của audit v1, chênh **`+1.429 m`**. `[ĐO verify_frame_geometry.py]`
<!-- END conclusion -->
