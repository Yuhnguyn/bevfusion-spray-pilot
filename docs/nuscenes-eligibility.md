# Eligibility nuScenes — số đo đầy đủ

Sinh bởi kernel `nguynhuy9669/nuscenes-eligibility-scan`, chạy `2026-11-07T03:18:36Z` (12.4 s), `velocity_source=devkit`, `val_split_available=True`. JSON thô: `kaggle/smoke_test/evidence/eligibility.json`.

## 0. Định nghĩa

- **split**: all keyframes; val = nuscenes.utils.splits.val; train = all scenes not in val (only for cross-check, never eval)
- **d**: min BEV distance from the LIDAR_TOP origin of the current keyframe to the 4 footprint corners, in LiDAR frame; only boxes whose center has x > 0 in LiDAR frame
- **d_legacy**: BEV distance of the box center to the LIDAR origin, only boxes with x > 0 in LiDAR frame (old table definition)
- **v_box_kmh**: ||velocity_global|| * 3.6
- **v_velocity_global**: devkit box_velocity when importable; otherwise (p_next - p_prev) / ((t_next - t_prev)/1e6) with max_time_diff 0.5 s and 2x allowance for the centered difference
- **v_ego_kmh**: ||ego_pose(t)[:2] - ego_pose(t-1)[:2]|| / 0.5 s inside the same scene; first keyframe of a scene has null and is excluded from ego filters
- **vehicle_classes**: ['bicycle', 'bus', 'car', 'construction_vehicle', 'motorcycle', 'trailer', 'truck']
- **vehicle_categories**: ['vehicle.bicycle', 'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.car', 'vehicle.construction', 'vehicle.motorcycle', 'vehicle.trailer', 'vehicle.truck']
- **car_only**: vehicle.car
- **box_speed_threshold_kmh**: 50.0
- **distance_ladder_m**: [10.0, 15.0, 20.0, 30.0, 40.0, 50.0]
- **ego_thresholds_kmh**: [None, 30.0, 50.0, 60.0]
- **legacy_expected**: {'boxes': 952, 'frames': 697}

## 1. Kích thước dữ liệu [ĐO]

| tập | scene | keyframe |
|---|---|---|
| all | 850 | 34149 |
| val | 150 | 6019 |
| train | 700 | 28130 |

## 2. Hàng đối chứng — tái lập bảng cũ [ĐO]

Điều kiện: `d_legacy ≤ 30 m`, box ≥50 km/h, `x>0`, không lọc ego, toàn bộ keyframe. Bảng cũ (2026-11-05): 952 box / 697 frame.

| tập class | box | frame | scene | lệch box | lệch frame |
|---|---|---|---|---|---|
| vehicle_ish | 957 | 698 | 75 | +0.53% | +0.14% |
| car_only | 831 | 625 | 68 | -12.71% | -10.33% |

Kết luận: tập `vehicle_ish` (8 category của `NameMapping`) tái lập đúng → **các bảng cũ quét toàn bộ trainval**, không phải val split.

## 3. Bảng 1 — ngưỡng khoảng cách, không lọc ego

**split=all · vehicle_ish** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 195 | 187 | 34 | 5.50 |
| 15 | 385 | 342 | 47 | 7.28 |
| 20 | 609 | 488 | 58 | 8.41 |
| 30 | 1055 | 753 | 78 | 9.65 |
| 40 | 1408 | 937 | 91 | 10.30 |
| 50 | 1690 | 1091 | 107 | 10.20 |

**split=all · car_only** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 161 | 155 | 29 | 5.34 |
| 15 | 330 | 295 | 42 | 7.02 |
| 20 | 522 | 425 | 51 | 8.33 |
| 30 | 924 | 677 | 70 | 9.67 |
| 40 | 1241 | 841 | 81 | 10.38 |
| 50 | 1488 | 982 | 95 | 10.34 |

**split=val · vehicle_ish** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 49 | 47 | 9 | 5.22 |
| 15 | 79 | 70 | 12 | 5.83 |
| 20 | 112 | 90 | 13 | 6.92 |
| 30 | 169 | 117 | 13 | 9.00 |
| 40 | 234 | 158 | 14 | 11.29 |
| 50 | 298 | 196 | 16 | 12.25 |

**split=val · car_only** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 33 | 32 | 7 | 4.57 |
| 15 | 58 | 51 | 11 | 4.64 |
| 20 | 79 | 66 | 12 | 5.50 |
| 30 | 123 | 92 | 12 | 7.67 |
| 40 | 181 | 131 | 13 | 10.08 |
| 50 | 238 | 168 | 15 | 11.20 |

**split=train · vehicle_ish** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 146 | 140 | 25 | 5.60 |
| 15 | 306 | 272 | 35 | 7.77 |
| 20 | 497 | 398 | 45 | 8.84 |
| 30 | 886 | 636 | 65 | 9.78 |
| 40 | 1174 | 779 | 77 | 10.12 |
| 50 | 1392 | 895 | 91 | 9.84 |

**split=train · car_only** · box ≥50 km/h, x>0

| d_max (m) | box | frame | scene | frame/scene |
|---|---|---|---|---|
| 10 | 128 | 123 | 22 | 5.59 |
| 15 | 272 | 244 | 31 | 7.87 |
| 20 | 443 | 359 | 39 | 9.21 |
| 30 | 801 | 585 | 58 | 10.09 |
| 40 | 1060 | 710 | 68 | 10.44 |
| 50 | 1250 | 814 | 80 | 10.18 |

## 4. Bảng 2 — thêm lọc vận tốc ego

**all · no_ego_filter**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 195 | 187 | 34 |
| 15 | 385 | 342 | 47 |
| 20 | 609 | 488 | 58 |
| 30 | 1055 | 753 | 78 |
| 40 | 1408 | 937 | 91 |
| 50 | 1690 | 1091 | 107 |

**all · ego_ge_30**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 116 | 112 | 26 |
| 15 | 257 | 232 | 35 |
| 20 | 404 | 322 | 37 |
| 30 | 701 | 484 | 40 |
| 40 | 901 | 575 | 44 |
| 50 | 1052 | 647 | 50 |

**all · ego_ge_50**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 11 | 10 | 5 |
| 15 | 63 | 57 | 9 |
| 20 | 121 | 86 | 10 |
| 30 | 257 | 163 | 12 |
| 40 | 294 | 170 | 14 |
| 50 | 330 | 175 | 15 |

**all · ego_ge_60**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 0 | 0 | 0 |
| 15 | 35 | 32 | 4 |
| 20 | 71 | 46 | 4 |
| 30 | 108 | 54 | 6 |
| 40 | 128 | 55 | 6 |
| 50 | 144 | 56 | 6 |

**val · no_ego_filter**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 49 | 47 | 9 |
| 15 | 79 | 70 | 12 |
| 20 | 112 | 90 | 13 |
| 30 | 169 | 117 | 13 |
| 40 | 234 | 158 | 14 |
| 50 | 298 | 196 | 16 |

**val · ego_ge_30**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 44 | 42 | 8 |
| 15 | 72 | 63 | 10 |
| 20 | 103 | 81 | 10 |
| 30 | 152 | 103 | 11 |
| 40 | 204 | 137 | 11 |
| 50 | 256 | 167 | 13 |

**val · ego_ge_50**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 0 | 0 | 0 |
| 15 | 0 | 0 | 0 |
| 20 | 0 | 0 | 0 |
| 30 | 0 | 0 | 0 |
| 40 | 1 | 1 | 1 |
| 50 | 2 | 2 | 2 |

**val · ego_ge_60**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 0 | 0 | 0 |
| 15 | 0 | 0 | 0 |
| 20 | 0 | 0 | 0 |
| 30 | 0 | 0 | 0 |
| 40 | 0 | 0 | 0 |
| 50 | 0 | 0 | 0 |

**train · no_ego_filter**

| d_max (m) | box | frame | scene |
|---|---|---|---|
| 10 | 146 | 140 | 25 |
| 15 | 306 | 272 | 35 |
| 20 | 497 | 398 | 45 |
| 30 | 886 | 636 | 65 |
| 40 | 1174 | 779 | 77 |
| 50 | 1392 | 895 | 91 |

## 5. Highway [ĐO]

- Scene highway trên toàn dataset: **2**, frame: **81**
- Scene highway trong val: **0 / 150** → hướng 'chỉ dùng highway' không khả thi với val split.

## 6. Kết luận

1. Bảng cũ 34.029 frame là **toàn bộ trainval** (850 scene / 34.149 keyframe), không phải val (150 / 6.019).
2. Trần của val ở 50 km/h: **196 frame / 16 scene** (d≤50 m, không lọc ego); 117 frame / 13 scene ở d≤30 m.
3. Thêm lọc ego ≥50 km/h → **0 frame** trên val. Highway → **0 scene** trong val.
4. Eval set chốt: phương án A — val, d≤50 m, không lọc ego, báo per-range 0–30 / 30–50 m.
