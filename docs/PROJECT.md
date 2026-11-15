# Dự án: BEVFusion LiDAR-only trên SemanticSpray++

Cập nhật: 2026-11-15 · nhánh `sspp` · tách từ `main` @ `f3fb7d2`.

---

## 1. Câu hỏi

Khi train BEVFusion LiDAR-only trên frame **đã bỏ điểm spray**, việc chèn thêm spray tổng hợp
lúc train có giảm **số hộp dương tính giả trên spray thật** không, và có **mất recall xe thật**
không?

Ba điều kiện để câu hỏi có nghĩa:

1. Nền train của hai arm phải giống hệt nhau, chỉ khác một biến là có/không có plume.
2. Tập test phải là **tốc độ chưa thấy** trong train, nếu không model chỉ nhớ scene.
3. Phải có **nhóm đối chứng không train** (Model 0), nếu không không biết mức hỏng gốc.

---

## 2. Phạm vi

**Có:** nhánh điểm tin cậy (heatmap) của detector LiDAR-only.

**Không:** hình học hộp, lớp, vận tốc, nhánh camera/fusion (dataset không có calib 6 view).

**Domain:** highway, 1 xe dẫn/frame, 2 lớp (Car, Van). Số tuyệt đối không chuyển sang nuScenes
đô thị; chỉ **delta ghép cặp** là chuyển được.

---

## 3. Dữ liệu — số đo trên `data/SemanticSprayDataset`

| Hạng mục | Giá trị |
|---|---|
| Scene tổng | 207 |
| Scene có box 3D | **36** |
| Frame trong 36 scene đó | **2.587** |
| Box | **2.595** (1 box/frame, tối đa 2) |
| Lớp | Car 1.362 · Van 1.225 · Other Vehicle 8 (bỏ) |
| Point format | `x, y, z, intensity, ring` — 5 chiều, ring 0…28 |
| Calibration camera | **không có** → chỉ LiDAR-only |
| Mặt đường | `z = −0,411 m` |

### Split theo tốc độ

36 scene = lưới 9 tốc độ × 2 cự ly (20 m / 30 m) × 2 group (Crafter / Golf), **mỗi ô 2 scene**.
Chia theo tốc độ để test là tốc độ chưa thấy.

| Split | Tốc độ (km/h) | Scene | Frame | Box | Spray p50/frame |
|---|---|---|---|---|---|
| train | 60, 80, 100, 120 | 16 | 1.124 | 1.124 | 378 |
| val | 70, 110 | 8 | 509 | 509 | 499 |
| **test** | **50, 90, 130** | **12** | **954** | **962** | **142** |

Spray p50 theo từng tốc độ (pooled frame): 50 → 73 · 60 → 208 · 70 → 374 · 80 → 493 ·
90 → 503 · 100 → 887 · 110 → 1.025 · 120 → 728 · 130 → 630.

### Ba sự thật phải nhớ khi đọc code

**a) `z` đáy box, không phải tâm.** Box JSON cho `center3D` ở tâm hình học. Công thức convert:

```python
dims  = (w, l, h) = (size3D.y, size3D.x, size3D.z)
yaw'  = -rotation3D.z - pi/2
z'    = center3D.z - size3D.z / 2        # đáy hộp
```

Kiểm bằng box đầu của `Crafter_dynamic/0000`: `0,899 − 2,6206/2 = −0,4113`, đúng mặt đường.
Trung bình toàn bộ 2.595 box: −0,362 (train) / −0,375 (val) / −0,376 (test). Dùng công thức
cho **từng box**, đừng dùng hằng số.

**b) `poses.txt` không có tịnh tiến.** 3 cột đầu là ma trận xoay, cột 4 toàn `0.0` → **không
lấy được ego displacement** từ pose. Tốc độ ego phải đọc từ `metadata.txt` cột `ego_velocity`.
Đây là lý do `PlumeContext.from_sample` có tham số `ego_speed_mps` tường minh.

**c) `object_velocity == ego_velocity` ở 207/207 scene**, cự ly chỉ 20,0 / 30,0 m. Ma trận thí
nghiệm có kiểm soát, không phải giao thông thật.

---

## 4. Ba nhánh thí nghiệm

| | Model 0 | Arm A | Arm B |
|---|---|---|---|
| Init | `lidar-only-det.pth` | giống | giống |
| Train | không | 16 scene | 16 scene |
| Nền point cloud | – | `points[labels != 2]` | `points[labels != 2]` |
| Spray tổng hợp | – | không | **p = 0,5, tại chỗ** |
| Steps / lr / batch / seed | – | 2000 / 1e-4 / 2 / 0 | giống Arm A |

**Model 0** không cập nhật trọng số nào — chỉ chạy inference. Nó là trạng thái ban đầu của cả
hai arm, và là mốc để biết mức hỏng gốc.

**Arm A** là nhóm đối chứng của Arm B. Nếu chỉ so B với Model 0, không tách được "học thêm
1.124 frame" khỏi "augment".

**Ba điều bắt buộc khi train:**

1. Bỏ `labels == 2` trước khi vào pipeline — **cả hai** arm.
2. Augment **tại chỗ**, không nhân đôi sample (nếu không, biến thay đổi là training exposure).
3. Log `n_points` mỗi 50 bước — arm B phải lớn hơn arm A khi augmentation bật.

---

## 5. Đo cái gì

Hai điều kiện eval, cả hai **không augment**:

| Điều kiện | Dữ liệu | Trả lời |
|---|---|---|
| Test | 12 scene real spray | Có giảm FP trên spray thật không |
| Clean control | nuScenes val 196 frame | Có mất gì trên domain gốc không |

**Ngưỡng score `τ`:** quét trên frame sạch, lấy τ nhỏ nhất mà precision ≥ 0,5. Đóng băng, dùng
cho cả ba checkpoint.

**SPF proxy/frame** — hộp phải thoả cả ba: `score ≥ τ`, không khớp GT nào ở IoU ≥ 0,5, tâm hộp
cách tâm cụm noise ≤ 1,5 m. Cụm noise dùng `spray.semantic_stats.cluster_angular`
(eps 0,7°, minPts 3 — công thức paper).

### Bảng kết quả

| Metric | Model 0 | Arm A | Arm B | Điều kiện đạt |
|---|---|---|---|---|
| AP@0,5 — test real spray | | | | B ≥ A |
| Recall — test real spray | | | | B ≥ A − 0,02 |
| Total FP/frame — test | | | | B < A |
| **SPF proxy/frame — test** | | | | **B < A ≥ 30 % tương đối, CI95 loại trừ 0** |
| AP@0,5 — clean control | | | | B ≥ A − 0,5 điểm |
| SPF proxy/frame — 50 và 130 km/h | | | | B < A ở **cả hai** |

Hàng 4 là hàng quyết định. Còn lại là chốt chặn.

**Phép đo thêm (miễn phí):** chạy cùng checkpoint hai lần trên cùng frame — bản gốc và bản
`points[labels != 2]`. Delta là tác động thuần của noise, không phụ thuộc generator.

---

## 6. Sổ quyết định

| Ngày | Quyết định | Lý do |
|---|---|---|
| 11-04 | pin MIT `da93b27` | tái lập được (ADR-0001) |
| 11-15 | **detection chuyển sang SemanticSpray++** | có spray thật + box thật; đổi lại mất frame sạch, mất camera, 1 box/frame (ADR-0005) |
| 11-15 | bỏ điểm `label == 2` khỏi nền train **cả hai** arm | để nền A và B giống hệt, chỉ khác plume tự sinh |
| 11-15 | chia split theo **tốc độ**, test = 50/90/130 | test phải là tốc độ chưa thấy, nếu không model nhớ scene |
| 11-15 | Arm A là nhóm đối chứng, không so trực tiếp B với Model 0 | tách "học thêm" khỏi "augment" |
| 11-15 | giữ `wet_ground.py`, `proxy_eval/matcher.py`, `inject_plume` dù chưa dùng | đóng import; trạng thái ghi ở §9 |

---

## 7. Chốt chặn trước khi chạy

| Kiểm | Giá trị đúng | Nếu sai |
|---|---|---|
| Checkpoint | `lidar-only-det.pth` = **33.362.653 byte** | trỏ nhầm bản fusion (163.715.701 byte) → `strict=False` che lỗi, đo model nửa khởi tạo |
| `box_dim` | **9** (7 hình học + 2 vận tốc) | head `code_size: 9` mismatch |
| `n_points` arm B | > arm A | plume không chèn được gì → dừng |
| `τ` | < 1,0 | `τ = 1,0` = model không đạt precision 0,5 trên domain này → báo cáo, không hạ mục tiêu |

**Nguồn checkpoint:** link `bevfusion.mit.edu` đã chết (trả HTML 16.478 byte). Mirror còn sống
là Dropbox mà README upstream đang liệt kê; đã tải thử, đúng **33.362.653 byte**, zip archive.

---

## 8. Bản đồ tài liệu

| File | Nội dung |
|---|---|
| `README.md` | cửa vào, 1 phút |
| `docs/PROJECT.md` | file này — câu hỏi, phạm vi, số đo, sổ quyết định |
| `docs/adr/0001-mit-bevfusion-pin.md` | pin `da93b27` |
| `docs/adr/0005-sspp-as-detection-domain.md` | vì sao đổi domain, đánh đổi gì |
| `docs/measurements/semantic-spray-stats.md` | thống kê spray thật |
| `docs/measurements/semantic-spray-cal-vs-heldout.md` | cổng 7 tiêu chí của split cal/held-out |
| `docs/measurements/semantic-spray-clusters-by-speed.md` | cụm/frame theo tốc độ |
| `docs/reference/paper-qa-notebooklm.md` | hỏi đáp nguyên văn với paper — `[PAPER]` vs `[CODE]` |
| `.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md` | 5 bước thi công |

Nhãn số: `[ĐO]` đo trên máy này · `[PAPER]` paper nói · `[CODE]` code tham chiếu · `[CHỌN]` tự chọn.

---

## 9. Giữ lại nhưng chưa dùng

| File | Vì sao vẫn ở đây | Trạng thái thật |
|---|---|---|
| `spray/wet_ground.py` | `plume_transform` import | mặc định **tắt** (`wet_ground=None`) |
| `proxy_eval/matcher.py` | `evaluate_frame` + `average_precision` | `class_names` là tham số → truyền `("car","van")` là chạy |
| `spray/plume.py` hàm `inject_plume` | `spray/__init__.py` export | v1, đã bị `inject_plume_stateful` thay; chỉ `test_plume.py` gọi |

---

## 10. Điều dự án này không chứng minh

Không chứng minh plume tổng hợp giống spray thật về mặt vật lý — chỉ chứng minh **thêm plume đó
lúc train thì giảm báo nhầm trên spray thật**. Nếu kết quả âm, kết luận đúng là "generator hiện
tại không chuyển được", không phải "augment vô dụng".

Không chứng minh được gì về nhánh camera hay fusion, vì dataset không có calibration.
