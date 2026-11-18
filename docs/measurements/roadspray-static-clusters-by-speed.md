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

Tham số chốt trước `[CHỌN]`: `L = 20 m`, `Δ = 2,5 m`, `W = 3,4 m`, `H = 1,5 m`, xe ở 18–38 m.

## 4. Kết quả `[ĐO]`

**54 bag, 1 558 frame, 8 tốc độ** (tất cả mức nước; `direction = +1`; CI95 bootstrap ở mức **bag**):

| Tốc độ | bag | frame | **cụm/frame** | CI95 | điểm/frame | Δ=1,0 | Δ=6,0 |
|---:|---:|---:|---:|---|---:|---:|---:|
| 60 | 1 | 20 | **11,5** | – (1 bag) | 272 | 15,9 | 7,7 |
| 70 | 8 | 116 | **19,0** | [15,7; 22,3] | 348 | 27,7 | 10,8 |
| 80 | 8 | 86 | **25,8** | [23,2; 28,5] | 389 | 34,9 | 16,7 |
| 90 | 7 | 60 | **27,3** | [21,9; 32,6] | 435 | 38,4 | 16,3 |
| 100 | 8 | 56 | **28,5** | [25,5; 31,6] | 502 | 39,8 | 17,9 |
| 110 | 5 | 22 | **25,9** | [14,7; 37,0] | 432 | 34,2 | 14,6 |
| 120 | 7 | 30 | **20,5** | [16,2; 24,9] | 324 | 26,1 | 12,5 |
| 130 | 8 | 42 | **22,0** | [18,4; 25,6] | 374 | 32,8 | 14,8 |

Đối chứng âm (hộp cùng kích thước **phía trước** xe) = **0,5–1,0 cụm/frame** ở mọi tốc độ. Nhiễu lá
cây — vốn cho **98 cụm/frame** khi đếm cả khung — đã bị loại hoàn toàn bằng ràng buộc hình học.

### Bảng ở đúng điều kiện eval (`itr_after_water = 1`) `[ĐO]`

Cả 36 scene eval của SSPP đều `itr_after_water = 1`, và Paper A calibrate ở
*"fully covered pavement"* (1 mm). Nên bảng lý thuyết đúng phải là tập `itr = 1`:

| Tốc độ | bag | frame | cụm/frame | CI95 (bag) | lệch vs bảng gộp |
|---:|---:|---:|---:|---|---:|
| 70 | 3 | 38 | 20,4 | [11,6; 29,2] | +7,6 % |
| 80 | 3 | 30 | 28,7 | [26,6; 30,8] | +11,2 % |
| 90 | 2 | 22 | 30,9 | [25,6; 36,3] | +13,5 % |
| 100 | 2 | 16 | 28,4 | [19,3; 37,4] | −0,6 % |
| 110 | 2 | 8 | 35,8 | [12,0; 59,7] | +38,5 % |
| 120 | 3 | 16 | 15,4 | [9,4; 21,5] | −24,8 % |
| 130 | 3 | 12 | 22,1 | [14,1; 30,0] | +0,2 % |

**Quyết định `[CHỌN]`: dùng bảng GỘP (54 bag) làm bảng chính, báo cáo bảng `itr = 1` kèm theo.**
Lý do: tập `itr = 1` chỉ có 2–3 bag và 8–38 frame/tốc độ ⇒ CI95 rộng tới ±50 %
(`110 km/h: [12,0; 59,7]`), không đủ để làm bảng tra cứu. Chênh lệch giữa hai
biến thể (−25 % … +38 %) **nằm gọn trong dải bất định định nghĩa vùng ±30–40 %**
đã nêu ở §5, nên không thể kết luận ảnh hưởng của mực nước từ mẫu hiện có.
Cần thêm bag (`Golf_static` chưa tải) mới tách được hiệu ứng này.

**Đường cong không đơn điệu là thật, không phải nhiễu mẫu:** đỉnh **28,5 @100 km/h** rơi còn
**20,5 @120 km/h** (−28 %), và hai CI95 **không chồng nhau** ([25,5; 31,6] vs [16,2; 24,9]).

**Mức nước (itr_after_water 1/3/5) không cho xu hướng rõ:** ví dụ 100 km/h → 28,4 / 30,0 / 27,1;
120 km/h → 15,0 / 24,0 / 25,0 (mẫu 1–3 bag/ô). **Chưa kết luận được** giả thuyết "nhiều nước → nhiều cụm".

### Kiểm chứng chéo với bảng SSPP hiện tại `[ĐO]`

| Tốc độ | static (bảng trên) | SSPP `cal` (bảng hiện tại) | tỉ lệ | SSPP nằm trong CI95 của static? |
|---:|---:|---:|---:|---|
| 70 | 19,0 | 17,42 | 1,09 | có |
| 80 | 25,8 | 22,02 | 1,17 | không |
| 90 | 27,3 | 20,69 | 1,32 | không |
| 100 | 28,5 | 29,24 | 0,97 | có |
| 110 | 25,9 | 28,49 | 0,91 | có |
| 120 | 20,5 | 17,58 | 1,17 | có |
| 130 | 22,0 | 17,69 | 1,24 | không |

Tỉ lệ trung bình **1,13** (0,91–1,32), Pearson **r = 0,792**. Hai bộ dữ liệu khác nhau (ego đỗ vs
ego bám sau), hai cách tách điểm khác nhau (range-image vs nhãn ngữ nghĩa), vẫn cho **cùng hình dạng
đường cong, kể cả cùng chạm đáy ở 120 km/h**.

### Plume xa dần theo tốc độ `[ĐO]`

Điểm/frame theo độ sâu sau đuôi (Δ=2,5):

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
| **Bề dày lát `Δ`** (1,0 → 6,0 m), tại 100 km/h | **17,9 – 39,8 cụm** (2,2×) ← **chi phối** |
| Mẫu (bag-level bootstrap) | CI95 ≈ **±10 %** ở hầu hết tốc độ; ±40 % ở 110 km/h (chỉ 5 bag) |
| Độ dài hộp `L` (2,8 → 20 m) | 1,0 → 28,9 cụm (không bất biến) |

⇒ Sau khi tăng mẫu, **sai số thống kê đã nhỏ (±10 %) nhưng sai số định nghĩa vùng vẫn ~2×**. Bảng chỉ
xác định được tới **±30–40 %**, và cổng B (`sinh/thật ∈ [0,7; 1,5]`) phải được đọc cùng độ bất định này.

## 6. Hệ quả cho dự án

1. **V2 giải được mà không cần tin một con số duy nhất:** chọn bảng **static** làm bảng calibration
   (đúng D2, không leak) và dùng bảng **SSPP tính lại trên scene không thuộc tập test** làm **kiểm
   chứng chéo**; hai bên lệch ≤ 1,32× ở mọi tốc độ đo được.
2. Vì sai số chủ yếu là **định nghĩa vùng** chứ không phải nguồn dữ liệu, việc đổi nguồn từ SSPP
   sang RoadSpray **không làm thay đổi kết luận khoa học** — nó chỉ làm protocol sạch leak.
3. Hình dạng đường cong (tăng tới ~100 km/h rồi giảm) **được xác nhận độc lập hai lần**, nên bảng
   tra cứu không-tham-số hoá (như code hiện tại) là lựa chọn đúng; **không** fit `a·(v−50)`.

## 7. Còn thiếu

- **60 km/h** chỉ có 1 bag (20 frame) ⇒ dòng đó chưa dùng được.
- **Golf** chưa đo (`Golf_static.zip` 5 460 144 118 B chưa tải; link REST đã có).
- Mức nước: mẫu 1–3 bag/ô, chưa kết luận.
- 81 bag được chọn nhưng chỉ 54 bag cho dữ liệu (số còn lại track ibeo < 5 mẫu hoặc 0 frame khớp).

## 8. Hạ tầng

- `scripts/roadspray_static_clusters.py` — range-image nền + RANSAC mặt đường + DBSCAN góc bằng
  cKDTree/union-find (không sklearn, không O(n²)), ghi JSONL descriptor từng cụm.
- `scripts/roadspray_static_plume_box.py` — định vị xe từ ibeo, cắt hộp sau đuôi, cắt lát cự ly,
  hộp đối chứng phía trước; `--speed/--water/--bags/--limit`.
- Chạy lại toàn bộ: `python scripts/roadspray_static_plume_box.py --out <file>.jsonl` (~11 phút cho 81 bag).
