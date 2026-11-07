# Walkthrough cho intern — repo này làm gì, từng ticket làm thế nào

Viết cho người mới, không giả định biết BEVFusion. Mỗi mục: việc → dữ liệu vào/ra → công thức →
dựa trên gì → chỗ dễ sai → tự kiểm.

---

## 0. Một sample đi qua repo thế nào

```
nuscenes_infos_train.pkl  (metadata + đường dẫn file)
        │
        ▼  LoadPointsFromFile            → points (N,5): x,y,z,intensity,ring   N≈34.720
        ▼  GlobalRotScaleTrans           → xoay/scale, ghi lidar_aug_matrix
        ▼  RandomFlip3D                  → lật trái/phải
        ▼  PlumeTransform   (ticket 07)  → points (N+K,5) + points_clean (N,5)
        ▼  DefaultFormatBundle3D         → tensor, gom batch
        ▼
   BEVFusion.forward (ticket 08)
        ├── camera branch: 6 ảnh + points_clean → sparse depth → BEV camera
        └── lidar  branch: points → voxel → BEV LiDAR
                        │
                        ▼  fuse (convfuser) → head → boxes_3d (M,9), scores_3d (M,), labels_3d (M,)
                        ▼
   proxy_eval/matcher.py (ticket 05, đã có) → TP/FP/FN → AP từng class → mAP
                        ▼
                    report.md
```

**Điểm mấu chốt phải hiểu:** một sample chỉ có **một** mảng điểm, nhưng hai nhánh cần **hai phiên bản khác
nhau**. Camera cần bản sạch (để chiếu lên ảnh lấy depth), LiDAR cần bản có plume (để học bỏ qua nó). Toàn bộ
ticket 07 và 08 tồn tại chỉ vì chuyện này.

---

## 1. Ticket 04 — sinh `nuscenes_infos_{train,val}.pkl`

**Việc:** biến bộ JSON metadata của nuScenes thành list các dict mà dataloader đọc được.

**Mỗi entry chứa:** `token`, `timestamp`, `lidar_path`, `cams` (6 camera: đường dẫn ảnh + ma trận nội tại/ngoại
tại), `gt_boxes` (M,7), `gt_names` (M,), `num_lidar_pts`.

**Công thức quan trọng nhất — đưa box từ global về LiDAR:**

```
p_ego   = R_ego⁻¹ · (p_global − t_ego)          # global → ego
p_lidar = R_cs⁻¹ · (p_ego − t_cs)               # ego → lidar (calibrated_sensor của LIDAR_TOP)
```

Làm ngược (lidar → ego → global) khi cần. Sai bước này thì box lệch vài mét và mAP sai âm thầm.

**Velocity:** `nusc.box_velocity(token)` trả vận tốc **global** (m/s), tính từ hiệu vị trí 2 keyframe. Phải xoay
về ego/lidar giống box. Đây là dữ liệu plume dùng để biết xe chạy nhanh hay chậm → **nếu quên xoay, plume chĩa
sai hướng** và kết quả vô nghĩa dù không có lỗi nào được báo.

**Còn sinh `nuscenes_dbinfos_train.pkl`:** danh sách box GT + các điểm nằm trong box, dùng cho `ObjectPaste`.

**Dựa trên gì:** `tools/create_data.py` có sẵn của MIT (không tự viết), và định nghĩa format trong
`mmdet3d/datasets/nuscenes_dataset.py`.

**Chỗ dễ sai:** mini split có 6 camera nhưng chỉ 1 số scene có đủ; thiếu ảnh một camera → lỗi lúc collate, không
phải lúc đọc. Log số sample bị skip và lý do.

**Tự kiểm:** in 1 entry, vẽ 1 box lên ảnh bằng phép chiếu `lidar2image` — box phải khớp xe trong ảnh.

---

## 2. Ticket 06 — adapter output model → evaluator

**Việc:** model trả `boxes_3d` kiểu `LiDARInstance3DBoxes` (tensor + thuộc tính), evaluator cần mảng
`(M,7) = [x, y, z, w, l, h, yaw]` cộng `scores`, `labels`.

**Logic:** chỉ là chuyển đổi, nhưng **thứ tự w/l/h phải khớp** với cách evaluator dựng góc box.

**Công thức evaluator dùng (BEV IoU):**

```
4 góc box: (x,y) ± R(yaw) · (±w/2, ±l/2)
IoU = diện tích giao / (diện tích A + diện tích B − diện tích giao)
```

Nếu hoán `w` và `l`, box bị xoay 90°, IoU tụt, mAP tụt — **không có exception nào báo**. Đây là loại bug tệ
nhất: kết quả sai mà mọi thứ vẫn "chạy".

**Dựa trên gì:** format của `proxy_eval/matcher.py::bev_corners` (đã có, đọc dòng 128–155).

**Tự kiểm:** tạo 1 box, đổi qua adapter rồi đổi ngược, phải ra đúng ban đầu. Và 1 frame thật: vẽ box dự đoán
lên BEV, so bằng mắt với GT.

---

## 3. Ticket 07 — `PlumeTransform`

**Việc:** gọi `inject_plume(points, boxes, seed=..., token=...)` và đặt kết quả vào dict.

**Vào/ra:** `points (N,5)` → `points (N+K,5)`, `points_clean (N,5)` (bản sao trước khi chèn), `spray_stats`.

### Công thức, từng bước, và vì sao

**(a) Tốc độ từ velocity**

```
speed_ms  = hypot(vx, vy)
speed_kmh = speed_ms × 3.6
```

`3.6` chỉ là đổi m/s → km/h. Ví dụ `vx=13,9 m/s` → 50 km/h.

**(b) Ngưỡng 50 km/h**

Spray chỉ hình thành khi nước bị bắn lên khỏi mặt đường, và paper đo được hiện tượng bắt đầu khoảng 50 km/h
(Linnhoff §III-A). Dưới ngưỡng → 0 cụm, không chèn gì.

Có một bug thật đã gặp: `float32(30/3.6)*3.6 = 29,999999` < 30 → box đúng ngưỡng bị loại oan. Vì vậy có
`speed_epsilon_kmh = 1e-3`: so sánh `speed_kmh < 50 − ε`.

**(c) Số cụm theo tốc độ**

```
t = (speed_kmh − 50) / (130 − 50)        # kẹp về [0,1]
n = round(2 + t × (8 − 2))
```

Ví dụ: 50 → 2; 72 → `t=0,275` → 3,65 → **4**; 90 → 5; 130 → 8.

**Dựa trên gì:** paper **có** cho dạng hàm — §III *Cluster Generation*: số cụm mỗi timestep là hàm tuyến tính
của tốc độ, lớp xe và độ dày màng nước; Fig. 4 vẽ mean clusters/timestep + đường tuyến tính xấp xỉ (đo cho
VW Crafter, tới ~30 cụm/scan). Repo dùng đúng **dạng hàm** đó nhưng hằng số 2 và 8 là lựa chọn của repo, neo
sao cho ở dải giữa khớp **median 5 cụm dày mỗi frame** đo trên SemanticSpray. Nói cách khác: dạng hàm theo
paper, hằng số theo dữ liệu mình có. (Xem `docs/plume-model-provenance.md`.)

**(d) Số điểm mỗi cụm và bán kính — phân bố lognormal**

```
μ = ln(median)
x = exp(μ + σ·z)      với z ~ N(0,1), sau đó kẹp vào [min, max]
```

Vì sao lognormal: đại lượng dương, lệch phải (nhiều cụm nhỏ, ít cụm rất to) — đúng hình dạng đo được. Tham số
hoá bằng **median** để dễ đọc: `median=17` nghĩa là một nửa số cụm có ≤17 điểm.

Ví dụ với `median=17, σ=0,67`: `z=0` → 17 điểm; `z=1,28` (p90) → `exp(2,83+0,86)=40`; `z=−1,28` → 7.
Bán kính `median=0,30 m, σ=0,8`: p90 = `0,30·exp(1,03)=0,84 m`.

**Dựa trên gì:** median 17 điểm đo trên SemanticSpray; bán kính lấy từ Linnhoff Fig. 5 (μ=−1,2, σ=0,8 →
median 0,30 m).

**(e) Đặt cụm**

```
direction = −[vx, vy] / |v|        # ngược chiều xe chạy: nước bắn ra sau
perp      = [−direction_y, direction_x]
tâm_cụm   = box_xy + direction × distance + perp × lateral,   distance ~ U(1,10) m, lateral ~ N(0; 0,5) m
z_cụm     = U(0,2; 2,0) m
```

Vì sao ngược chiều velocity: plume là nước bị bánh xe hất **ra sau**. Nếu đặt trước xe thì đó là hiện tượng khác
(không có thật).

**(f) Sinh điểm trong hình cầu bán kính R**

```
u = rng.random()^(1/3)          # phân bố đều theo bán kính
hướng = vector ngẫu nhiên chuẩn hoá
điểm = tâm + u · R · hướng
```

Vì sao mũ `1/3`: thể tích hình cầu tỉ lệ `R³`. Nếu lấy `u` tuyến tính thì điểm dồn vào tâm — sai hình dạng
plume (thực tế là vỏ mỏng, phân tán).

**(g) Loại điểm không hợp lệ**

- Ngoài `point_cloud_range = [−54, −54, −5, 54, 54, 3]` (range của config MIT).
- Nằm trong GT box đã nới `0,2 m`: đưa điểm về hệ toạ độ box bằng cách xoay `−yaw`, rồi so
  `|dx| ≤ w/2 + margin`, `|dy| ≤ l/2 + margin`, `|dz| ≤ h/2 + margin`. Nới 0,2 m để plume không dính sát box
  (sát quá thì bị tính là điểm của xe → nhiễu nhãn).

**(h) Chặn số điểm**

`max_injected_points = 2000` mỗi frame. Lý do: model voxelize với `max_voxels` giới hạn; nhồi quá nhiều điểm
giả sẽ **đẩy điểm thật ra khỏi voxel** và làm hỏng cả frame. Vượt cap → subsample không hoàn lại.

**(i) Tính tất định**

`rng` dựng từ `seed` + hash(`token`) → cùng sample, cùng seed, cùng kết quả. Không có bước này thì arm A và B
nhìn hai bản nhiễu khác nhau, phép so sánh mất nghĩa.

### Chỗ dễ sai
1. Quên epsilon ở ngưỡng 50 → mất các frame đúng 50 km/h.
2. Dùng `points` sau khi chèn để tính `points_clean` → hai bản giống nhau, augmentation vô hiệu.
3. Sinh plume trước `GlobalRotScaleTrans`/`RandomFlip3D` → plume trôi khỏi vị trí.
4. Không seed theo token → không tái lập được.

### Tự kiểm
`points_clean` phải **byte-equal** với input. `len(points) − len(points_clean) == stats.injected`.
Cùng seed chạy 2 lần → mảng giống hệt. 49,9 km/h → 0 điểm; 50 km/h → 2 cụm ≈ 76 điểm.

---

## 4. Ticket 08 — routing hai nhánh

**Việc:** sửa `BEVFusion.forward` để camera branch dùng `points_clean`, LiDAR branch dùng `points`.

Hiện tại code gọi `extract_camera_features(img, points, ...)` và `extract_lidar_features(points)` — **cùng một
biến `points`**. Patch: thêm kwarg `points_clean` và truyền nó cho camera.

**Vì sao camera phải sạch:** camera branch chiếu từng điểm 3D lên ảnh (`lidar2image`) để lấy depth thưa. Điểm
plume nằm sau xe, chiếu vào vùng ảnh không tương ứng → depth sai → BEV camera sai. Mà camera là nửa còn lại của
fusion, nên sai ở đây làm hỏng luôn kết quả fusion.

**Vì sao LiDAR phải có plume:** đó chính là thứ model cần học để bỏ qua. Nếu đưa bản sạch cho cả hai nhánh thì
không còn gì để augment.

**Dựa trên gì:** kiến trúc BEVFusion — depth branch lấy điểm LiDAR chiếu lên ảnh; đọc
`extract_camera_features` để thấy `points` được dùng cho depth.

**Tự kiểm:** đặt một giá trị marker vào `points` và `points_clean` (ví dụ 9999), chạy forward, assert nhánh nào
nhận giá trị nào. Không so hash float.

---

## 5. Ticket 09 — test end-to-end

**Việc:** chạy 1 sample thật qua cả 3 arm (A/B/B0) tới lúc format bundle, dùng model giả ghi lại input.

**Assert:**
1. Arm A: `points_clean` == `points` (không chèn gì).
2. Arm B: `len(points) > len(points_clean)`, chênh lệch == `stats.injected`.
3. Không điểm plume nào nằm trong GT box.
4. Tắt spray (`enabled: false`) → `points_clean` không tồn tại hoặc bằng `points`.
5. Arm B0: `points` đã qua lọc có ít điểm hơn arm A cùng frame.

**Dựa trên gì:** nguyên tắc "test hành vi ngoài, không test nội bộ" — kiểm cái model nhìn thấy.

---

## 6. Ticket 10 — 3 config

3 file YAML, khác nhau **đúng một chỗ**: `spray.enabled` (A: false, B: true) và bước lọc (B0).

Cách kiểm tự động: load 3 config, xoá key `spray` và `filter`, phần còn lại phải **giống hệt nhau**. Nếu khác
(seed, LR, batch size, freeze list) thì phép so A/B không còn là so một biến.

---

## 7. Ticket 11 — chạy và đọc kết quả

### Công thức đánh giá (đã có trong `proxy_eval/matcher.py`)

**Bước 1 — mỗi frame:** lọc box theo bán kính `‖(x,y)‖ ≤ range`; lọc theo `score ≥ 0,05`; ghép dự đoán với GT
theo BEV IoU ≥ 0,5, ưu tiên điểm cao trước (greedy); đếm TP/FP/FN.

**Bước 2 — mỗi class, toàn bộ frame:**

```
sắp xếp mọi dự đoán của class theo score giảm dần
cum_tp, cum_fp  → recall = cum_tp / số GT, precision = cum_tp / (cum_tp + cum_fp)
precision envelope: p[i] = max(p[i], p[i+1])       (làm phẳng về bên phải)
AP = Σ (recall[i] − recall[i−1]) × p[i]            (all-point interpolation)
```

**Bước 3 — mAP** = trung bình AP trên các class có GT.

**Bước 4 — khoảng tin cậy theo scene:**

```
lặp 1000 lần: lấy ngẫu nhiên các scene (có hoàn lại), tính lại mAP
CI 95% = percentile 2,5 và 97,5 của phân bố đó
```

Vì sao theo scene chứ không theo frame: các frame trong cùng một scene rất giống nhau (cùng đường, cùng xe).
Bootstrap theo frame sẽ cho CI hẹp giả tạo, khiến kết quả nhiễu trông như có ý nghĩa.

### Các đại lượng báo cáo

```
G_X = mAP_clean(X) − mAP_plume(X)          # X ∈ {A, B, B0}
noise_floor_A = nửa độ rộng CI của G_A
```

Ví dụ: A sạch 0,300; A có plume 0,240 → `G_A = 0,060`. B sạch 0,285; B có plume 0,270 → `G_B = 0,015`.
Kết luận "augment giúp" chỉ đứng nếu: `G_A` > noise floor, `mAP_clean(B) ≥ 0,9·mAP_clean(A)` (0,285 ≥ 0,270 ✓),
và `G_B ≤ 0,5·G_A` (0,015 ≤ 0,030 ✓).

---

## 8. Ticket 14 — arm B0 (lọc rồi detect)

**Việc:** trước khi đưa điểm vào model, bỏ các điểm "cô lập" — plume thường là cụm nhỏ rời rạc, điểm thật của xe
thì dày.

**Công thức ROR (Radius Outlier Removal):**

```
với mỗi điểm p: đếm số điểm khác trong bán kính r = 0,5 m
nếu count < k = 8  →  bỏ p
```

Cài bằng KD-tree (`scipy.spatial.cKDTree`), không thêm dependency nặng.

**Dựa trên gì:** paper dùng DROR (bán kính thích nghi theo khoảng cách) và đo được **AP −5,5** vì DROR xoá cả
điểm xa thật. ROR là bản rẻ hơn, yếu hơn, chọn trước khi xem kết quả (pre-registered) để không bị cáo buộc tune.

**Chỗ dễ sai:** ở xa, mật độ điểm tự nhiên đã thấp → ROR xoá cả điểm thật. Phải log **% điểm giữ lại theo
range bucket** để thấy thiệt hại này, và báo thời gian ms/frame.

---

## 9. Ticket 13 — cổng quyết định

Đọc bảng ở ticket 11, kiểm 5 điều kiện (gap trên noise floor; mAP sạch của B ≥ 90% của A; gap B ≤ nửa gap A;
FP giảm với CI không chứa 0; B > B0). Không đạt → viết kết quả âm. Không tune để đạt.

---

## 10. Bảng "mỗi con số dựa trên gì"

| Con số | Giá trị | Nguồn |
|---|---|---|
| Ngưỡng bắt đầu spray | 50 km/h | Linnhoff §III-A (đo thực nghiệm) |
| Bán kính cụm | median 0,30 m, σ=0,8 | Linnhoff Fig. 5 |
| Số điểm/cụm | median 17 | đo trên SemanticSpray |
| Số cụm theo tốc độ | 2 → 8 | chọn, để khớp median 5 cụm/frame đo được |
| Intensity điểm plume | 0 | 81,95% điểm spray thật có intensity 0 |
| Cap điểm/frame | 2000 | chọn, theo giới hạn `max_voxels` |
| IoU threshold | 0,5 | chuẩn ngành cho xe |
| Score threshold | 0,05 | chọn, để không bỏ sót dự đoán yếu |
| Bootstrap | 1000 lần theo scene | chọn, vì frame trong scene tương quan |
| ROR | k=8, r=0,5 m | chọn trước, pre-registered |