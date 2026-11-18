# Cụm spray trên RoadSpray `*_static` — đo không dùng nhãn (2026-11-18)

Người đo: lead. Nguồn: `data/roadspray/Crafter_static.zip` (163 bag) + `meta_data_measurement.xlsx`.
Mục đích: có nguồn **không leak** cho bảng `_CLUSTER_VISIBLE_BY_SPEED` (ADR-0006 **D2**, chẩn đoán **V2**).
Nguồn phương pháp: Paper A §II/§III-B + reference implementation `openMSL/sl-1-2`.
Nhãn: `[ĐO]` trên máy này · `[PAPER]` paper nói · `[CHỌN]` tự chọn.

---

## 1. Vì sao phải đo lại

`_CLUSTER_VISIBLE_BY_SPEED` hiện tại đo trên SSPP `cal`, mà `cal` chứa **6/12 scene test** (V2).
Đo lại trên RoadSpray `*_static` — chiến dịch **calibration của Paper A**, không nằm trong tập đánh giá.

## 2. Dữ liệu đã kiểm `[ĐO]`

| Kiểm | Kết quả |
|---|---|
| Zip khớp release | `Crafter_static` 7 924 255 130 B, `Crafter_dynamic` 6 127 018 713 B |
| Metadata | `meta_data_measurement.xlsx` 26 774 B, 549 dòng; static **333** (Crafter 162 + Golf 171) |
| Sensor | VLP-32C, **9,95 Hz**, fields `x,y,z,intensity,ring` — cùng layout điểm SSPP |
| Ego | `/adma/twist` mean **0,005 km/h** ⇒ đỗ thật (đúng định nghĩa "static") |
| Mặt đường | `z ≈ −2,01 m` trong khung `velodyne` (RANSAC 14 509 inlier) — **không** phải `z = 0` |

## 3. Phương pháp

Bốn thành phần, mỗi thành phần lấy từ nguồn chứ không tự đặt:

1. **Vùng đo = hộp sau đuôi xe.** Paper A §II: *"The initialization of clusters is restricted to
   the vehicle trajectory and no clusters are spawned randomly in the scene."* §III-B: số cụm được
   đếm *"in a spray filter region behind the vehicle"*, rồi chia cho *"the length ratio of the spray
   region to the distance the object traveled during one scan"* ⇒ **độ dài vùng tự triệt tiêu** khi
   chuẩn hoá. Kích thước hộp lấy từ `define_spray_volumes()` của code tác giả:
   **rộng 3,4 m, cao 1,5 m** trên mặt đường.
2. **Tách spray không cần nhãn.** Ego đỗ ⇒ mỗi tia `(ring, az_bin 0,4°)` luôn trả về cùng một vật
   thể ở cùng range. Dựng **range-image nền** = median range mỗi bin trên cả bag; residual =
   `|r − median| > max(0,7 m; 2 %·r)`. Bỏ thêm điểm dưới mặt đường +0,15 m (RANSAC).
3. **Định vị xe.** Track `ns == 'Car'` từ `/front_ibeo_lux/as_tx/objects`, đổi về khung `velodyne`
   bằng transform trong `meta_data_dataset.json` (bag không có `/tf`; `tf2_msgs` không có trong typestore).
   `[ĐO]` track cho 127,7 → 8,1 m, tốc độ **123 km/h** với bag metadata 120 km/h.
4. **Mặt đuôi xe.** Van cao ~2,6 m còn plume theo paper cao ≤ 1,5 m ⇒ điểm cao **> 1,6 m** chỉ có
   thể thuộc thân xe; điểm xa nhất về phía sau = mặt đuôi. `[ĐO]` `rear = car_range − 3,5 m`, ổn định.

**Chiều xe `[ĐO]`:** `object_direction = +1` ⇒ xe chạy cùng chiều ego (y 29,5 → 139,1 m; ego thấy
**đuôi**, plume hướng về ego). `direction = −1` ⇒ ngược chiều (y 130,2 → 20,3 m; ego thấy **mặt
trước**, plume bị che). **Chỉ đo trên `direction = +1`.**

**Cắt lát cự ly `[CHỌN]`.** DBSCAN của paper chạy trên `(azimuth, elevation)`, **không có chiều cự
ly**, nên hai điểm cùng tia cách nhau 5 m và 20 m vẫn là hàng xóm. Ở kịch bản static ego nhìn **dọc**
ống plume (3 → 23 m) nên toàn bộ plume chain thành **một** cụm (632/942 điểm). Cắt plume thành các
lát dày `Δ` rồi gom cụm trong từng lát phá được hiện tượng này, và đúng tinh thần paper —
*"object distance of 25 m … distinct and stable clusters are observed"*.

## 4. Kết quả `[ĐO]`

Crafter, `itr_after_water = 1`, frame có xe ở **18–38 m**, hộp dài 20 m, 18 bag / 295 frame:

| Tốc độ | cụm/frame (Δ=2,5) | điểm/frame | đối chứng phía trước xe |
|---:|---:|---:|---:|
| 70 | 19,8 | 356 | 0,7 |
| 80 | 29,3 | 366 | 0,6 |
| 90 | 31,4 | 425 | 0,5 |
| 100 | 28,1 | 510 | 0,8 |
| 110 | 30,2 | 474 | 0,5 |
| 120 | 15,0 | 266 | 0,5 |
| 130 | 24,2 | 423 | 0,5 |

Đối chứng âm (hộp cùng kích thước **phía trước** xe) = **0–0,8 cụm/frame**. Nhiễu lá cây — vốn cho
**98 cụm/frame** khi đếm cả khung — đã bị loại hoàn toàn bằng ràng buộc hình học.

**Hai phép đo độc lập khớp nhau:**

| Tốc độ | static (bảng trên) | SSPP `cal` (bảng hiện tại) | tỉ lệ |
|---:|---:|---:|---:|
| 70 | 19,8 | 17,42 | 1,14 |
| 80 | 29,3 | 22,02 | 1,33 |
| 90 | 31,4 | 20,69 | 1,52 |
| 100 | 28,1 | 29,24 | 0,96 |
| 110 | 30,2 | 28,49 | 1,06 |
| 120 | 15,0 | 17,58 | 0,85 |
| 130 | 24,2 | 17,69 | 1,37 |

Tỉ lệ trung bình **1,18** (0,85–1,52), Pearson `r = 0,64`, Spearman `ρ = 0,64`. Cả hai **cùng không
đơn điệu và cùng chạm đáy ở 120 km/h**.

**Plume xa dần theo tốc độ** — điểm/frame theo độ sâu sau đuôi:

| Tốc độ | 0–4 m | 4–8 m | 8–12 m | 12–16 m | 16–20 m |
|---:|---:|---:|---:|---:|---:|
| 70 | 158 | 69 | 72 | 37 | 19 |
| 100 | 75 | 20 | 113 | 103 | 200 |
| 130 | 70 | 29 | 82 | 123 | 120 |

Đúng chiều với mô hình cản của paper (eq. 5, `C = −0,15 m⁻¹`): quãng trôi trước khi tan tính ra
**2,0 / 6,9 / 8,6 / 11,1 m** ở 50 / 80 / 100 / 130 km/h.

## 5. Độ bất định — phải ghi kèm mọi con số

| Nguồn | Độ lớn |
|---|---|
| Bề dày lát `Δ` (1,0 → 6,0 m), tại 100 km/h | **19,5 – 37,8 cụm** (1,94×) |
| Độ dài hộp `L` (2,8 → 20 m) | 1,0 → 28,9 cụm (không bất biến) |
| Mẫu (6–19 frame/tốc độ) | CI95 cỡ **±35 %** |

⇒ Bảng chỉ xác định được tới **±30–40 %**. Không được dùng nó như một con số chính xác, và cổng B
(`sinh/thật ∈ [0,7; 1,5]`) phải được đọc cùng độ bất định này.

## 6. Hệ quả cho dự án

1. **V2 giải được mà không cần tin một con số duy nhất:** chọn bảng **static** làm bảng calibration
   (đúng D2, không leak) và dùng bảng **SSPP tính lại trên scene không thuộc tập test** làm **kiểm
   chứng chéo**; hai bên lệch ≤ 1,5× ở mọi tốc độ đo được.
2. Vì sai số chủ yếu là **định nghĩa vùng** chứ không phải nguồn dữ liệu, việc đổi nguồn từ SSPP
   sang RoadSpray **không làm thay đổi kết luận khoa học** — nó chỉ làm protocol sạch leak.
3. `[CHỌN]` chốt trước khi dùng: `L = 20 m`, `Δ = 2,5 m`, `W = 3,4 m`, `H = 1,5 m`, chỉ
   `direction = +1`, chỉ `itr_after_water` tách riêng. Mọi báo cáo phải in kèm dải `Δ` và số frame.

## 7. Còn thiếu

- **50 và 60 km/h** chưa có bag `direction = +1`, `water = 1` (18 bag chọn ra không phủ hai mốc này).
- **Golf** chưa đo (`Golf_static.zip` 5 460 144 118 B chưa tải; link REST đã có).
- Chưa chạy đủ 3 mức nước ⇒ chưa kiểm được giả thuyết "nhiều nước → nhiều cụm".

## 8. Hạ tầng

- `scripts/roadspray_static_clusters.py` — range-image nền + RANSAC mặt đường + DBSCAN góc bằng
  cKDTree/union-find (không sklearn, không O(n²)), ghi JSONL descriptor từng cụm.
- `scripts/roadspray_static_plume_box.py` — định vị xe từ ibeo, cắt hộp sau đuôi, cắt lát cự ly,
  hộp đối chứng phía trước; `--speed/--water/--bags/--limit`.
