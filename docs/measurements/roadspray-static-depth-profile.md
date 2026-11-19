# Plume thật trên RoadSpray `*_static` — depth profile 0–60 m (T4, task-13)

Người đo: `paper-archaeologist` (R2). Ngày: **2026-11-19**. Mục đích: trả lời hộp đo 20 m có cắt mất
phần lớn plume thật không, để định nghĩa lại target A3. Script: `scripts/roadspray_static_depth_profile.py`.
Nguồn: `data/roadspray/{Crafter,Golf}_static.zip` + `meta_data_measurement.xlsx` (549 dòng).

## 0. TL;DR — 4 câu trả lời

1. **Trail thật dài** (mass90, biên phải bin, mask ±5 m/0,15–3,0 m): **6.0 / 44.0 / 52.0 m** ở 50/100/130 km/h (biên trái 4.0/42.0/50.0 m; nội suy 5.5/43.4/51.4 m).
   Bản unmasked (không mask ngang/cao): 54.0 / 48.0 / 54.0 m.
2. **% detections nằm trong 20 m** (theo profile mask): **99.6 / 54.0 / 25.7 %**; nếu tính đúng hộp hẹp cũ 3,4×1,5×20 m: **43.6 / 35.3 / 19.9 %**.
3. **Height p95 / |y| p95** (mask): **2.13 / 2.15 / 2.19 m** (p50 1.58/1.07/1.09 m); **|y| p95 1.04 / 2.74 / 2.40 m**.
4. **Kết luận**: hộp 20 m **KHÔNG đủ** ở 100/130 km/h (chỉ còn 54% và 26% mass tính theo depth); ở 50 km/h thì đủ depth nhưng hộp hẹp về cao/ngang. Target A3 phải dùng tổng 0–60 m (điểm/frame), không dùng lát 20 m. **Target (a) chốt sau khi loại thân xe bằng hình học: 85,1 / 202,6 / 208,9 điểm/frame (xem §5b).**

## 1. Dữ liệu & phương pháp (tái lập được)

| km/h | bag | frame | lớp (frame) | itr_after_water (frame) |
|---:|---:|---:|---|---|
| 50 | 10 | 582 | {'Crafter': 281, 'Golf': 301} | {1: 245, 3: 228, 5: 109} |
| 100 | 10 | 449 | {'Crafter': 241, 'Golf': 208} | {1: 193, 3: 167, 5: 89} |
| 130 | 10 | 457 | {'Crafter': 190, 'Golf': 267} | {1: 176, 3: 187, 5: 94} |

**Mỗi tốc độ 5 bag/lớp (10 bag, gồm cả Crafter + Golf), chọn vòng tròn theo `itr_after_water`; frame = frame lidar có track ibeo còn hiệu lực.**

- Chọn track xe: `/front_ibeo_lux/as_tx/objects`, khớp `object_velocity` metadata, track nhiều mẫu nhất;
  chỉ đo bag xe **đang rời xa** ego (ego thấy đuôi xe ⇒ plume hướng về ego).
- Nội suy tuyến tính vị trí tâm xe tại đúng stamp lidar (bag 50 km/h có ibeo thưa; lấy mẫu gần nhất
  từng trễ tới ~4 m = thân xe lọt vào depth bin 0–4 m).
- Mặt đuôi = tâm track − nửa chiều dài xe (Crafter 3,5 m; Golf 2,15 m).
- Trừ nền bằng **mode** range mỗi `(ring, az_bin 0,4°)` trên cả bag (mode bám nền tĩnh; median bị xe
  chiếm >50 % frame làm nền bị đánh dấu residual). Residual = `|r − mode| > max(0,7 m; 2 %·r)`.
- Mặt đường = RANSAC mặt phẳng (fit trên điểm `z<0`, range ≤120 m, inlier 0,12 m); height = z − mặt phẳng.
- Detection = residual + `intensity <= 2` (Paper A §III-B L724-726: >80 % spray detection intensity 0,
  16 % là 1) để loại thân xe/reflector (intensity p50 17–100).
- Bin depth **2 m**, 0–60 m sau mặt đuôi; masked: ngang ±5 m, cao 0,15–3,0 m; unmasked: không mask
  ngang/cao. `trail90` = biên phải bin nơi cumulative đạt 90 %; biên trái và nội suy xuất kèm.
- Control: bag xe **đang tiến lại** (plume bị thân xe che) ở 100 km/h, cùng pipeline ⇒ nền clutter.

## 2. Bảng tổng hợp (gộp 2 lớp; masked là chuẩn chính)

| km/h | bag | frame | det/frame masked | det/frame unmasked | cụm/frame masked | trail90 masked (right) | trail90 unmasked | %depth≤20 masked | %hộp hẹp 3,4×1,5×20 | h p95 | \|y\| p95 | điểm/m masked | %mass 10 m đầu |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 10 | 582 | 99.0 | 144.2 | 3.1 | 6.0 m | 54.0 m | 99.6 % | 43.6 % | 2.13 m | 1.04 m | 16.5 | 98.5 % |
| 100 | 10 | 449 | 203.2 | 240.7 | 14.1 | 44.0 m | 48.0 m | 54.0 % | 35.3 % | 2.15 m | 2.74 m | 4.6 | 17.1 % |
| 130 | 10 | 457 | 208.6 | 234.3 | 14.4 | 52.0 m | 54.0 m | 25.7 % | 19.9 % | 2.19 m | 2.40 m | 4.0 | 5.1 % |

`điểm/m = det_per_frame / trail90_m` (mật độ tuyến tính): **16.5 / 4.6 / 4.0** ⇒ giảm **4.1×** từ 50→130 km/h.

## 3. Bảng theo lớp (masked)

| lớp | km/h | bag | frame | det/frame | cụm/frame | trail90 | %depth≤20 | %hộp hẹp | h p95 | \|y\| p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter | 50 | 5 | 281 | 148.5 | 3.6 | 6.0 m | 99.6 % | 22.7 % | 2.16 m | 1.07 m |
| Crafter | 100 | 5 | 241 | 272.8 | 18.1 | 46.0 m | 45.9 % | 21.3 % | 2.20 m | 2.97 m |
| Crafter | 130 | 5 | 190 | 338.5 | 21.6 | 54.0 m | 19.0 % | 11.5 % | 2.25 m | 2.59 m |
| Golf | 50 | 5 | 301 | 52.8 | 2.7 | 8.0 m | 99.6 % | 98.6 % | 1.44 m | 0.94 m |
| Golf | 100 | 5 | 208 | 122.6 | 9.4 | 30.0 m | 74.9 % | 71.6 % | 1.40 m | 1.70 m |
| Golf | 130 | 5 | 267 | 116.1 | 9.3 | 46.0 m | 39.6 % | 37.5 % | 1.95 m | 1.77 m |

## 4. Depth profile đầy đủ (2 m/bin) — hai biến thể

### 50 km/h — 10 bag, 582 frame, trail90 masked=6.0 m / unmasked=54.0 m

| bin (m) | masked det/frame | unmasked det/frame | % luỹ kế masked | % luỹ kế unmasked | frame quan sát |
|---|---:|---:|---:|---:|---:|
| 0–2 | 48.019 | 49.612 | 47.60 | 25.74 | 582 |
| 2–4 | 30.608 | 32.686 | 77.94 | 42.71 | 582 |
| 4–6 | 16.566 | 18.383 | 94.36 | 52.24 | 551 |
| 6–8 | 3.132 | 4.639 | 97.47 | 54.65 | 529 |
| 8–10 | 1.057 | 2.367 | 98.52 | 55.88 | 512 |
| 10–12 | 0.303 | 1.605 | 98.82 | 56.71 | 499 |
| 12–14 | 0.139 | 1.633 | 98.95 | 57.56 | 482 |
| 14–16 | 0.079 | 1.598 | 99.03 | 58.39 | 470 |
| 16–18 | 0.044 | 1.673 | 99.08 | 59.26 | 452 |
| 18–20 | 0.039 | 1.735 | 99.11 | 60.16 | 438 |
| 20–22 | 0.038 | 1.990 | 99.15 | 61.19 | 420 |
| 22–24 | 0.032 | 2.252 | 99.18 | 62.36 | 405 |
| 24–26 | 0.018 | 2.286 | 99.20 | 63.55 | 388 |
| 26–28 | 0.043 | 2.597 | 99.24 | 64.89 | 372 |
| 28–30 | 0.036 | 2.641 | 99.28 | 66.26 | 359 |
| 30–32 | 0.038 | 2.938 | 99.32 | 67.79 | 341 |
| 32–34 | 0.028 | 2.827 | 99.34 | 69.25 | 324 |
| 34–36 | 0.036 | 3.071 | 99.38 | 70.85 | 309 |
| 36–38 | 0.048 | 3.215 | 99.43 | 72.52 | 293 |
| 38–40 | 0.040 | 3.392 | 99.47 | 74.28 | 278 |
| 40–42 | 0.053 | 3.450 | 99.52 | 76.07 | 262 |
| 42–44 | 0.045 | 3.623 | 99.56 | 77.95 | 247 |
| 44–46 | 0.030 | 3.987 | 99.59 | 80.02 | 232 |
| 46–48 | 0.065 | 4.526 | 99.66 | 82.36 | 215 |
| 48–50 | 0.045 | 4.731 | 99.70 | 84.82 | 201 |
| 50–52 | 0.043 | 4.674 | 99.75 | 87.25 | 184 |
| 52–54 | 0.071 | 5.494 | 99.82 | 90.10 | 170 |
| 54–56 | 0.071 | 5.753 | 99.89 | 93.08 | 154 |
| 56–58 | 0.065 | 6.217 | 99.95 | 96.31 | 138 |
| 58–60 | 0.049 | 7.115 | 100.00 | 100.00 | 122 |

### 100 km/h — 10 bag, 449 frame, trail90 masked=44.0 m / unmasked=48.0 m

| bin (m) | masked det/frame | unmasked det/frame | % luỹ kế masked | % luỹ kế unmasked | frame quan sát |
|---|---:|---:|---:|---:|---:|
| 0–2 | 5.653 | 6.009 | 2.45 | 2.16 | 449 |
| 2–4 | 5.287 | 5.844 | 4.74 | 4.25 | 449 |
| 4–6 | 6.931 | 7.724 | 7.75 | 7.03 | 449 |
| 6–8 | 10.871 | 11.811 | 12.46 | 11.27 | 449 |
| 8–10 | 10.624 | 11.612 | 17.07 | 15.43 | 449 |
| 10–12 | 13.077 | 14.309 | 22.74 | 20.57 | 443 |
| 12–14 | 13.975 | 15.376 | 28.80 | 26.09 | 433 |
| 14–16 | 12.895 | 14.383 | 34.39 | 31.25 | 428 |
| 16–18 | 13.844 | 15.272 | 40.39 | 36.73 | 423 |
| 18–20 | 20.031 | 21.495 | 49.07 | 44.45 | 418 |
| 20–22 | 13.416 | 14.929 | 54.89 | 49.81 | 411 |
| 22–24 | 11.514 | 12.992 | 59.88 | 54.47 | 395 |
| 24–26 | 10.659 | 12.240 | 64.50 | 58.87 | 387 |
| 26–28 | 10.097 | 11.475 | 68.88 | 62.99 | 381 |
| 28–30 | 8.879 | 10.458 | 72.73 | 66.74 | 373 |
| 30–32 | 7.725 | 9.267 | 76.08 | 70.07 | 367 |
| 32–34 | 6.730 | 8.331 | 79.00 | 73.06 | 359 |
| 34–36 | 6.405 | 8.026 | 81.77 | 75.94 | 351 |
| 36–38 | 5.715 | 7.512 | 84.25 | 78.63 | 344 |
| 38–40 | 4.890 | 6.625 | 86.37 | 81.01 | 336 |
| 40–42 | 5.036 | 7.058 | 88.56 | 83.54 | 329 |
| 42–44 | 4.682 | 6.526 | 90.59 | 85.89 | 321 |
| 44–46 | 3.958 | 6.080 | 92.30 | 88.07 | 313 |
| 46–48 | 3.526 | 5.581 | 93.83 | 90.07 | 308 |
| 48–50 | 2.967 | 5.191 | 95.12 | 91.94 | 299 |
| 50–52 | 2.945 | 5.065 | 96.39 | 93.75 | 293 |
| 52–54 | 2.673 | 4.919 | 97.55 | 95.52 | 284 |
| 54–56 | 2.353 | 4.665 | 98.57 | 97.19 | 278 |
| 56–58 | 1.756 | 4.011 | 99.33 | 98.63 | 270 |
| 58–60 | 1.536 | 3.806 | 100.00 | 100.00 | 263 |

### 130 km/h — 10 bag, 457 frame, trail90 masked=52.0 m / unmasked=54.0 m

| bin (m) | masked det/frame | unmasked det/frame | % luỹ kế masked | % luỹ kế unmasked | frame quan sát |
|---|---:|---:|---:|---:|---:|
| 0–2 | 0.873 | 0.982 | 0.38 | 0.38 | 457 |
| 2–4 | 1.681 | 1.884 | 1.10 | 1.09 | 457 |
| 4–6 | 1.328 | 1.652 | 1.67 | 1.73 | 457 |
| 6–8 | 3.549 | 3.958 | 3.20 | 3.24 | 457 |
| 8–10 | 4.457 | 4.991 | 5.12 | 5.14 | 457 |
| 10–12 | 5.683 | 6.298 | 7.57 | 7.55 | 457 |
| 12–14 | 7.193 | 7.917 | 10.66 | 10.57 | 457 |
| 14–16 | 8.387 | 9.180 | 14.28 | 14.08 | 455 |
| 16–18 | 10.195 | 11.137 | 18.67 | 18.33 | 452 |
| 18–20 | 10.621 | 11.563 | 23.24 | 22.75 | 449 |
| 20–22 | 9.707 | 10.716 | 27.42 | 26.85 | 444 |
| 22–24 | 11.918 | 12.925 | 32.55 | 31.78 | 441 |
| 24–26 | 15.588 | 16.680 | 39.26 | 38.15 | 434 |
| 26–28 | 16.516 | 17.688 | 46.38 | 44.91 | 426 |
| 28–30 | 10.950 | 12.139 | 51.09 | 49.55 | 418 |
| 30–32 | 11.027 | 12.114 | 55.84 | 54.17 | 414 |
| 32–34 | 10.810 | 11.901 | 60.50 | 58.72 | 405 |
| 34–36 | 9.652 | 11.028 | 64.65 | 62.93 | 400 |
| 36–38 | 9.967 | 10.975 | 68.94 | 67.12 | 394 |
| 38–40 | 7.530 | 8.654 | 72.19 | 70.43 | 387 |
| 40–42 | 8.462 | 9.666 | 75.83 | 74.12 | 383 |
| 42–44 | 6.460 | 7.628 | 78.61 | 77.03 | 376 |
| 44–46 | 8.299 | 9.728 | 82.19 | 80.75 | 371 |
| 46–48 | 6.712 | 7.896 | 85.08 | 83.77 | 365 |
| 48–50 | 6.898 | 8.183 | 88.05 | 86.89 | 361 |
| 50–52 | 6.297 | 7.517 | 90.76 | 89.76 | 354 |
| 52–54 | 6.352 | 7.642 | 93.49 | 92.68 | 349 |
| 54–56 | 5.052 | 6.317 | 95.67 | 95.10 | 344 |
| 56–58 | 5.497 | 6.935 | 98.04 | 97.74 | 336 |
| 58–60 | 4.559 | 5.906 | 100.00 | 100.00 | 331 |

## 5. Kiểm tra chéo & ảnh hưởng của mask

| km/h | %depth≤20 masked | %depth≤20 unmasked | %hộp hẹp (3,4×1,5×20) | %unmasked ngoài mask | trong đó: dưới mặt đường | trên 3 m | ngang >5 m | road_z mean |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 99.6 | 78.1 | 43.6 | 31.3 | 5.8 | 0.1 | 28.0 | -1.91 m |
| 100 | 54.0 | 49.9 | 35.3 | 15.6 | 4.5 | 0.7 | 11.8 | -1.85 m |
| 130 | 25.7 | 25.3 | 19.9 | 11.0 | 3.8 | 0.5 | 8.0 | -1.85 m |

Diễn giải: `%depth≤20 masked` lấy theo đúng mask ±5 m/3 m, nên khác `%hộp hẹp` (hộp 3,4×1,5×20 cũ).
Phần unmasked nằm ngoài mask chủ yếu là **ngang >5 m** (28 % ở 50 km/h, 12–8 % ở 100–130), không phải
theo chiều cao (≤0,7 % trên 3 m); phần dưới mặt đường 3,8–5,8 %. Vì vậy unmasked ở 50 km/h bị nhiễu
residual hai bên đường, không dùng làm thước plume; masked là thước chính.

## 5b. Loại thân xe bằng HÌNH HỌC — và cái kết luận "68 % thân xe" bị bác

`h_p50 = 1,58 m` ở 50 km/h từng bị nghi là thân xe, và mask cao `h ≤ 1,2 m` làm det/frame rơi 68 %.
Để phân xử, tôi loại detection nằm **bên trong hộp 3D của xe đối tượng** (không đụng tới cao độ):
hộp dài `2 × OBJECT_HALF_LENGTH` (Crafter **7,0 m**, Golf **4,3 m**), rộng **2,4 / 1,8 m**, cao
**2,6 / 1,5 m**, đặt theo track pose + hướng chạy, đáy = mặt đường, biên đệm 0,2 m (`--body-box`).

| km/h | biến thể | det/frame | trail90 | %mass≤20 m | h p95 | body-removed/frame | % det nằm trong hộp xe |
|---:|---|---:|---:|---:|---:|---:|---:|
| 50 | base (h≤3,0) | 99,0 | 6,0 m | 99,6 % | 2,13 m | — | — |
| 50 | **tight (h≤1,2)** | 31,6 | 8,0 m | 99,9 % | 1,18 m | 0 | 0 |
| 50 | **geom (bỏ hộp xe)** | **85,1** | 6,0 m | 99,5 % | 2,11 m | 28,0 | **14,0 %** |
| 100 | base (h≤3,0) | 203,2 | 44,0 m | 54,0 % | 2,15 m | — | — |
| 100 | **tight (h≤1,2)** | 115,7 | 38,0 m | 64,5 % | 1,14 m | 0 | 0 |
| 100 | **geom (bỏ hộp xe)** | **202,6** | 44,0 m | 53,8 % | 2,15 m | 2,9 | **0,3 %** |
| 130 | base (h≤3,0) | 208,6 | 52,0 m | 25,7 % | 2,19 m | — | — |
| 130 | **tight (h≤1,2)** | 115,4 | 48,0 m | 36,2 % | 1,15 m | 0 | 0 |
| 130 | **geom (bỏ hộp xe)** | **208,9** | 52,0 m | 25,7 % | 2,19 m | 0,4 | **0,1 %** |

**Kết luận (quan trọng, ngược giả thuyết ban đầu):**
- Chỉ **14,0 %** detections @50 km/h, **0,3 %** @100 và **0,1 %** @130 nằm trong hộp xe ⇒ **thân xe không
  phải nguồn nhiễm 68 %**. Mask cao 1,2 m cắt **spray thật** ở tầng cao (h p95 ≈ 2,1 m) — số `31,6` là
  **cận dưới**, `99,0` gần hơn với thực nhưng vẫn có ~14 % thân xe @50.
- Kiểm tra nới hộp xe thêm 1,2 m và 3,0 m về phía sau (vượt xa mặt đuôi xe 7 m) chỉ làm giảm thêm
  (48 % / 71 % @50) — các điểm đó nằm **ngoài** mọi hộp xe hợp lý ⇒ là spray/mist thật, không phải thân xe.
- **Target (a) chốt = bộ `geom`**: **85,1 / 202,6 / 208,9 điểm/frame**; trail90 **6,0 / 44,0 / 52,0 m**;
  %mass≤20 m **99,5 / 53,8 / 25,7 %**. Đây là một bộ số duy nhất cho cả 3 tốc độ, chỉ loại phần thật
  sự nằm trong thân xe. Sai số còn lại của det/frame: @50 khoảng ±14 % (khác base↔geom), @100/130 < 1 %.
- **Bài học phương pháp:** đừng suy "thân xe" từ cao độ. `det/frame @50` từng bị nghi nhiễm 68 % thân xe;
  kiểm tra hình học cho thấy chỉ ~14 % nằm trong hộp xe, phần còn lại là spray thật ở cao độ 1,2–3,0 m.
  Muốn loại thân xe phải dùng hộp 3D theo track, không dùng ngưỡng cao độ.

## 6. Control âm (bag xe tiến lại, 100 km/h — plume bị thân xe che)

| tập | bag | frame | det/frame masked | trail90 masked | %depth≤20 | h p95 | \|y\| p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| control 100 km/h | 8 | 199 | 26.6 | 10.0 m | 100.0 % | 1.75 m | 1.77 m |
| signal 100 km/h | 10 | 449 | 203.2 | 44.0 m | 54.0 % | 2.15 m | 2.74 m |

Control **không có đuôi sâu**: 100 % mass trong 20 m, trail90 = 10 m, det/frame chỉ 26,6 so với 203,2 của
signal ⇒ các bin sâu 20–60 m của signal là spray thật nhìn thấy được, không phải clutter nền.

## 7. Cảnh báo phương pháp

1. **`clusters_per_frame` phụ thuộc vùng đo** (DBSCAN góc merge mạnh hơn khi vùng rộng): 50 km/h có
   9,0 cụm/frame trong hộp hẹp cũ nhưng chỉ 3,1 cụm/frame trong vùng ±5 m/3 m/60 m ⇒ **không dùng cụm/frame
   làm tiêu chí A3**, chỉ dùng đại lượng điểm (det/frame) là bền với định nghĩa vùng.
2. **Đếm điểm thấp hơn số cũ**: bản này dùng background **mode** + lọc `intensity<=2` + nội suy track.
   Số cũ (`roadspray-static-clusters-by-speed.md`, và target A3 236/500/432) dùng median background +
   không lọc intensity + track gần nhất ⇒ có thể lẫn thân xe/nền; **phải re-baseline target A3 bằng
   pipeline này** trước khi so tuyệt đối.
3. **Nhiễm thân xe ở 50 km/h — đã kiểm tra riêng (2026-11-19).** `h_p50 = 1,58 m` ở 50 km/h là bất
   thường, nên tôi chạy lại **đúng 5 bag/lớp, cùng pipeline** với mask cao chặt `0,15 ≤ h ≤ 1,2 m`
   (`--height-max 1.2`). Kết quả:

   | 50 km/h | det/frame (h≤3,0) | det/frame (h≤1,2) | Δ | trail90 base→tight | h p95 base→tight |
   |---|---:|---:|---:|---:|---:|
   | Crafter | 148,5 | 28,2 | **−81,0 %** | 6,0 → 8,0 m | 2,16 → 0,85 m |
   | Golf | 52,8 | 34,7 | **−34,3 %** | 8,0 → 8,0 m | 1,44 → 1,21 m |
   | gộp 2 lớp | 99,0 | 31,6 | **−68,1 %** | 6,0 → 8,0 m | 2,13 → 1,18 m |

   ⇒ Ở 50 km/h phần lớn "detection" trong vùng ±5 m/3 m nằm ở **dải cao 1,2–3,0 m = thân xe**
   (Crafter cao 2,6 m; Golf thấp hơn nên chỉ −34 %). Vì giảm **>20 %**, **det/frame @50 km/h KHÔNG dùng
   được làm tiêu chí tuyệt đối**; với 50 km/h chỉ dùng **trail90 (6–8 m, ổn định) và %mass theo depth**
   — cả hai không đổi về kết luận. Ở 100/130 km/h chưa lặp phép thử này (xe rời ego nhanh, `h_p50` chỉ
   1,07–1,09 m) — nếu cần chắc chắn, chạy lại `--height-max 1.2` cho 2 tốc độ đó (~3 phút).
4. ego ĐỖ, xe chạy qua: plume nhìn từ phía sau/bên. Trail sâu (40–60 m) tương ứng đám spray còn lơ lửng
   gần ego sau khi xe đã đi xa — đúng cơ chế drag `C=−0,15 m⁻¹`; không phải plume trong kịch bản following
   ở cùng khoảng cách, nhưng là thước car-relative tốt nhất hiện có.
5. `%hộp hẹp` thấp hơn `%depth≤20` vì hộp cũ hẹp hơn mask (1,7 m nửa ngang, 1,5 m cao so với 5 m/3 m).

## 8. Tái lập

```bash
# đo (2 lớp × 3 tốc độ; 5 bag hợp lệ/tốc độ/lớp, tối đa 14 ứng viên)
for z in Crafter Golf; do
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/roadspray_static_depth_profile.py --zip data/roadspray/${z}_static.zip \
    --speeds 50,100,130 --target-valid-bags 5 --max-candidates 14 --direction signal \
    --out .scratch/roadspray-cal/tmp/depth_signal_${z,,}_v2.jsonl
done
cat .scratch/roadspray-cal/tmp/depth_signal_{crafter,golf}_v2.jsonl > .scratch/roadspray-cal/tmp/depth_signal_v2.jsonl
# biến thể tight (cận dưới): thêm --height-max 1.2 --speeds 50 / 100,130
# (kết quả: depth_50_h12*.jsonl, depth_h12_100_130*.jsonl)
# biến thể geom (target chốt): thêm --body-box (hộp xe 3D theo track)
# (kết quả: depth_50_geom*.jsonl, depth_geom100_130*.jsonl)
# tổng hợp
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
  scripts/roadspray_static_depth_profile.py --mode aggregate \
  --out .scratch/roadspray-cal/tmp/depth_signal_v2.jsonl \
  --summary .scratch/roadspray-cal/tmp/depth_signal_v2_summary.json
```

## 9. File

- `scripts/roadspray_static_depth_profile.py` — script đo + aggregate.
- `.scratch/roadspray-cal/tmp/depth_signal_v2.jsonl` — 1.488 frame (712 Crafter + 776 Golf).
- `.scratch/roadspray-cal/tmp/depth_signal_v2_summary.json` — summary đầy đủ (mọi bin, 2 biến thể).
- `.scratch/roadspray-cal/tmp/depth_control_v2.jsonl` / `..._summary.json` — control 100 km/h (8 bag).
- `.scratch/roadspray-cal/tmp/depth_50_h12.jsonl` / `depth_50_h12_summary.json` — biến thể tight
  50 km/h (`--height-max 1.2`, 10 bag, 582 frame).
- `.scratch/roadspray-cal/tmp/depth_geom50.jsonl`, `depth_geom100_130.jsonl` — biến thể geom
  (`--body-box`, 10 bag/tốc độ; bảng target ở §5b).
- `meta_data_measurement.xlsx`: 549 dòng; static 333 (Crafter 162 + Golf 171).

**Số cũ trong `.scratch/roadspray-cal/tmp/depth_signal_summary.json` (Lead đã đọc) là bản trước khi lọc
intensity/nội suy track**; bảng trong doc này là bản cuối. Xu hướng không đổi, nhưng con số tuyệt đối
(đặc biệt det/frame và điểm/m ở 50 km/h) khác — dùng bảng này khi viết báo cáo.
