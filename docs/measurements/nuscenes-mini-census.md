# Khám phá nuScenes Mini trên Kaggle — 2026-11-27

Mục đích: trả lời "Mini có dùng được cho train không" **bằng số**, trước khi đốt GPU.
Không chép doc; mọi số dưới đây đọc từ metadata JSON của dataset thật.

## 1. Bản nào dùng được

Có 5 bản "nuscenes-mini" trên Kaggle. **Chỉ một bản có đủ metadata:**

| dataset | size | `v1.0-mini/*.json` | `samples/LIDAR_TOP` | `sweeps/LIDAR_TOP` | verdict |
|---|---|---:|---:|---:|---|
| `babydriver1233/lephyjepa-nuscenes-mini-lidar-dataset-v-1-0` | 4,20 GB | **13 file** ✅ | 404 | 3531 | **dùng được** |
| `aadimator/nuscenes-mini` | 4,20 GB | 13 file ✅ | 404 | 3531 | dùng được (cùng nội dung) |
| `aliabohendy/nuscenes-mini-dataset` | 8,35 GB | ✗ | 195* | — | thiếu metadata |
| `vyomkeshsharma/nuscenes-mini-complete-with-lidarseg` | 4,34 GB | ✗ (chỉ `lidarseg/`) | — | — | thiếu metadata |
| `diamond1234/nuscenes` | 4,31 GB | ✗ (BevFusion `gt_database`) | — | — | prep khác, không phải raw |

\* đếm một trang CSV, không phải toàn bộ.

**Bẫy đã gặp:** `kaggle datasets files` phân trang, mặc định 20 file/trang. Đọc một trang rồi
kết luận "thiếu metadata" là **sai**. Muốn biết đủ phải theo `Next Page Token` tới hết —
helper ở `.scratch/kaggle-mini/kaggle_list_all.py`.

## 2. Nội dung Mini `[ĐO]`

```
scene              10
sample (keyframe)  404
sample_annotation  18.538
sample_data        31.206
calibrated_sensor  120
sweeps/LIDAR_TOP   3.531     = 8,7 sweep/keyframe
keyframe spacing   p50 0,50 s (min 0,40, max 0,60)
sweep spacing      0,050 s   (20 Hz)  ✅
```

⇒ **Sweeps thật, 20 Hz.** Đây là điều bản full keyframe-only trên Kaggle **không** có.
Về mặt mật độ điểm, Mini là bản duy nhất trung thực với paper.

## 3. Số box/frame `[ĐO]` — con số "10 box" cũ là sai

```
vehicle (car/truck/bus): mean 21,5 / frame, p50 16, p95 52, max 57
frame có >= 1 vehicle:   404/404 = 100 %
```

Vẫn chưa phải chi phí, vì `select_lead_box` chỉ lấy **1**. Nhưng nó xác nhận: **không được**
phun cho mọi box.

## 4. Census xe dẫn `[ĐO]` — đây là kết quả quyết định

Điều kiện `select_lead_box`: ô tô, `x > 0`, `x ≤ 50 m`, `|y| ≤ 5 m`, lấy `x` nhỏ nhất.

| scene | frames | có xe dẫn | % | `lead_x` p50 |
|---|---:|---:|---:|---:|
| scene-0061 | 39 | 17 | 44 % | 8,6 m |
| scene-0103 | 40 | 33 | 82 % | 6,6 m |
| scene-0553 | 41 | 41 | 100 % | 2,3 m |
| scene-0655 | 41 | 41 | 100 % | 1,3 m |
| scene-0757 | 41 | 41 | 100 % | 3,6 m |
| scene-0796 | 40 | 30 | 75 % | 8,3 m |
| scene-0916 | 41 | 27 | 66 % | 3,2 m |
| scene-1077 | 41 | **0** | **0 %** | – |
| scene-1094 | 40 | 19 | 48 % | 9,9 m |
| scene-1100 | 40 | 40 | 100 % | 3,0 m |
| **TOTAL** | **404** | **289** | **71,5 %** | **3,4 m** |

`lead_x`: p5 = 0,6 · p50 = **3,4** · p95 = 13,6 m
`lead_cls`: car 231 · truck 54 · bus.rigid 3 · bus.bendy 1

### 71,5 % là con số ẢO

`lead_x p50 = 3,4 m` bất khả thi vật lý: xe dài 4,6 m thì tâm ở 3,4 m nghĩa là ego đang
**xuyên qua** thân xe đó. Nguyên nhân: Mini toàn tắc đường và bãi đỗ — ego đứng, xe xếp hàng
sát nhau. `scene-0553` và `scene-1100` có ego **0 km/h** suốt scene.

Kiểm bằng tốc độ ego `[ĐO]`:

```
ego speed    p50 18,4 km/h · p95 46,9 · max 54,6
  > 20 km/h   47,5 % frame
  > 40 km/h   19,5 %
  > 50 km/h    4,3 %
```

### Hình học generator biến sai số vị trí thành lỗi câm

Plume spawn trong slab dài `|v_aug|·dt` ngay sau **mặt đuôi** xe, rồi `select_alive` lọc theo
**mặt cầu** cụm (`‖pos‖ − radius ≥ 2,5 m`). Điều kiện để cụm còn sống:

```
lead_x − λ/2 − |v_aug|·dt/2 − r  ≥  2,5 m
```

Giải theo `lead_x` với `λ = 4,6 m` (car), `v_aug = 100 km/h` (`dt = 0,1` ⇒ slab 2,78 m), và
`r` lấy từ lognormal của generator (`μ = −1,2`, `σ = 0,8` sau bản sửa 2026-11-27):

```
lead_x ≥ 6,49 m (khi r = p50 = 0,30 m)
lead_x ≥ 7,31 m (khi r = p95 = 1,12 m)
```

| `lead_x` | mặt đuôi | slab@100 | tâm slab − r(p50) | sống? |
|---:|---:|---:|---:|:--|
| 3,4 | 1,1 | 2,78 | **−1,84** | **KHÔNG** |
| 6,5 | 4,2 | 2,78 | 1,26 | vừa đủ |
| 12,0 | 9,7 | 2,78 | 6,76 | có |
| 20,0 | 17,7 | 2,78 | 14,76 | có |

Khi slab rơi vào vùng `‖pos‖ − r < 2,5`, `select_alive` **lọc sạch cụm** — transform vẫn
`return` bình thường, không warn. Đây đúng bẫy "lỗi câm" đã ghi trong `spray-pilot-ops`.

### Bao nhiêu frame thật sự dùng được

```
lead_x >=  5,00 m: 101/404 = 25,0 %
lead_x >=  6,49 m:  87/404 = 21,5 %   ← ngưỡng sinh được, r = p50
lead_x >=  7,31 m:  82/404 = 20,3 %   ← ngưỡng sinh được, r = p95
lead_x >= 10,00 m:  37/404 =  9,2 %
lead_x >= 20,00 m:   6/404 =  1,5 %   ← khoảng cách campaign của paper
```

**Không dùng `lead_x >= 9 m`** (một bản nháp trước của tài liệu này đã ghi 12,8 % theo ngưỡng
đó): ngưỡng phải giải từ hình học generator, không chọn tròn số.

## 5. Kết luận

| câu hỏi | trả lời |
|---|---|
| Mini có metadata đủ để dựng infos? | **Có** (dùng `babydriver1233` hoặc `aadimator`) |
| Mini có sweeps 20 Hz như paper? | **Có**, 8,7 sweep/keyframe |
| Mini có đủ frame để train? | **Không.** 404 keyframe; 2.000 bước × batch 2 = 4.000 sample = **~10 epoch** ⇒ overfit |
| Mini có frame "bám đuôi" như paper? | **Gần như không.** p50 khoảng cách xe dẫn **3,4 m**; paper đo ở **20 m**; chỉ **1,5 %** frame đạt ≥ 20 m |
| Mini dùng được để làm gì? | **Thông luồng** (dây chạy, cache có điểm, `points_clean` xuống model, loss giảm) — đúng như user đã chốt |

**Không được** trích dẫn bất kỳ so sánh A/B nào trên Mini như bằng chứng về tác dụng của
augmentation. Hai lý do độc lập: (a) n = 10 scene; (b) vị trí plume sai miền so với paper.

## 6. Việc phải làm trước khi train full

1. Train (hoặc ít nhất census) trên **full `v1.0-trainval`** — nơi có đường trường tốc độ cao.
2. Ngưỡng census phải là **`spawnable`**: `lead_x − λ/2 − slab/2 − r ≥ 2,5 m`, tức
   `lead_x ≥ 6,49 m` ở p50. Ngưỡng "có xe dẫn" cho 71,5 % trong khi thực dùng được **21,5 %**;
   ngưỡng "≥ 20 m" (đúng khoảng cách paper) chỉ còn **1,5 %**.
3. Cân nhắc `road_z_m` phải là **hằng số đo được**, không phải −1,84 lấy từ doc: Mini có nhiều
   cao độ khác nhau (bãi đỗ, cầu).
