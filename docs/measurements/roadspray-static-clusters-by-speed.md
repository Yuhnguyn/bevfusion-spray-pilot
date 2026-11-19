# Cụm spray trên RoadSpray `*_static` — đo không dùng nhãn (2026-11-18)

Người đo: lead. Nguồn: `data/roadspray/{Crafter,Golf}_static.zip` + `meta_data_measurement.xlsx`.
Mục đích: nguồn **không leak** cho `_CLUSTER_VISIBLE_BY_SPEED` (ADR-0006 **D2**, chẩn đoán **V2**).
Nguồn phương pháp: Paper A §II/§III-B + reference implementation `openMSL/sl-1-2`.
Nhãn: `[ĐO]` trên máy này · `[PAPER]` paper nói · `[CHỌN]` tự chọn.

---

## 1. Vì sao phải đo lại

`_CLUSTER_VISIBLE_BY_SPEED` cũ đo trên SSPP `cal`, mà `cal` chứa **6/12 scene test** (V2). Đo lại trên
RoadSpray `*_static` — chiến dịch **calibration của Paper A**, không nằm trong tập đánh giá.

## 2. Dữ liệu đã kiểm `[ĐO]`

| Kiểm | Kết quả |
|---|---|
| Zip khớp release | `Crafter_static` 7 924 255 130 B (163 bag), `Golf_static` 5 460 144 118 B (171 bag) |
| Metadata | `meta_data_measurement.xlsx` 26 774 B, 549 dòng; static **333** (Crafter 162 + Golf 171) |
| Sensor | VLP-32C, **9,95 Hz**, fields `x,y,z,intensity,ring` — cùng layout điểm SSPP |
| Ego | `/adma/twist` mean **0,005 km/h** ⇒ đỗ thật |
| Mặt đường | `z ≈ −2,01 m` trong khung `velodyne` (RANSAC 14 509 inlier) — **không** phải `z = 0` |

## 3. Phương pháp

**Vùng đo = hộp ngay sau đuôi xe.** Paper A §II: *"The initialization of clusters is restricted to the
vehicle trajectory and no clusters are spawned randomly in the scene."* §III-B: số cụm đếm *"in a spray
filter region behind the vehicle"* rồi chia cho *"the length ratio of the spray region to the distance
the object traveled during one scan"* ⇒ **độ dài vùng tự triệt tiêu**. Kích thước lấy từ
`define_spray_volumes()` của tác giả: **rộng 3,4 m, cao 1,5 m**; mặt đuôi = tâm track − nửa chiều dài xe
(Crafter **3,5 m** đo từ dữ liệu, Golf **2,15 m**).

**Tách spray không cần nhãn.** Ego đỗ ⇒ mỗi tia `(ring, az_bin 0,4°)` luôn trả về cùng vật thể ở cùng
range. Nền = median range mỗi bin trên cả bag; residual = `|r − median| > max(0,7 m; 2 %·r)`, bỏ thêm
điểm dưới mặt đường +0,15 m.

**Định vị xe.** Không dùng nhãn phân loại của ibeo (xem §5-b); chọn track có **nhiều mẫu nhất** trong
số các track mà `|d(range)/dt|` khớp `object_velocity` của metadata (sai số ≤ 40 %). Ego đỗ nên
`|d(range)/dt|` = tốc độ xe đối tượng.

**Cắt lát cự ly `[CHỌN]`.** DBSCAN của paper chạy trên `(azimuth, elevation)`, **không có chiều cự ly**,
nên hai điểm cùng tia cách nhau 5 m và 20 m vẫn là hàng xóm; ở kịch bản static ego nhìn **dọc** ống
plume (3 → 23 m) nên cả plume chain thành **một** cụm (632/942 điểm). Cắt plume thành lát dày `Δ` rồi
gom cụm trong từng lát, đúng tinh thần paper (*"object distance of 25 m … distinct and stable clusters
are observed"*).

**Tham số chốt trước `[CHỌN]`:** `L = 20 m`, `Δ = 2,5 m`, `W = 3,4 m`, `H = 1,5 m`, xe ở 18–38 m.

## 4. Kết quả `[ĐO]`

Track của xe phải **đang rời xa** ego (ego thấy đuôi xe, plume hướng về ego); bag xe **tiến lại** bị
loại vì plume bị chính thân xe che — xem §5-a. CI95 = bootstrap ở mức **bag**.

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Crafter — cụm/frame** | 6,0 | 13,2 | 19,0 | 26,7 | 24,8 | 25,7 | 27,4 | 20,6 | 22,2 |
| CI95 half-width | 1,3 | 3,1 | 2,5 | 1,8 | 3,7 | 1,9 | 5,2 | 4,7 | 2,8 |
| điểm/frame | 239 | 306 | 381 | 443 | 431 | 506 | 566 | 435 | 440 |
| bag / frame | 9/141 | 9/113 | 9/87 | 9/70 | 9/66 | 9/58 | 9/55 | 9/45 | 8/38 |
| **Golf — cụm/frame** | 4,7 | 8,8 | 13,2 | 17,8 | 20,9 | 22,6 | 22,0 | 25,8 | 25,2 |
| CI95 half-width | 0,6 | 1,1 | 1,3 | 1,5 | 2,0 | 3,2 | 2,4 | 1,6 | 2,4 |
| điểm/frame | 190 | 231 | 278 | 336 | 381 | 472 | 468 | 526 | 563 |
| bag / frame | 9/139 | 13/163 | 9/95 | 9/83 | 9/81 | 9/71 | 9/67 | 10/63 | 7/33 |

**Đối chứng âm** (cùng hộp, **phía trước** xe) = **0,0 cụm/frame** ở **mọi** ô của cả hai lớp.

Hai lớp cùng hình dạng: tăng tới ~22–27 cụm/frame quanh 100–130 km/h. Crafter nhỉnh hơn Golf
~1,1–1,6× ở tốc độ thấp, gần bằng nhau ở tốc độ cao.

### Kiểm chứng chéo với bảng SSPP `cal` cũ `[ĐO]`

| | tỉ lệ trung bình (min–max) | Pearson r |
|---|---|---|
| Crafter | **1,15** (0,88–1,43) | **0,94** |
| Golf | 1,40 (0,99–1,99) | 0,89 |

Crafter khớp rất chặt. Golf lệch hệ thống ~1,4×: bảng SSPP cũ của Golf đo 45 frame/ô và trộn mức nước,
nên có dip bất thường ở 90 km/h (10,51) mà phép đo static (9 bag, 81 frame) không thấy — số static
tăng đơn điệu và mượt hơn, nên **tin bảng static hơn**.

### Bảng SSPP per-fold (kiểm chứng chéo thứ hai)

`docs/measurements/sspp-cluster-table-folds.md`: bảng per-fold không leak khớp bảng static với
r = 0,77 (bảng fold khô hơn vì 10/12 scene `itr` 2–6, trong khi eval là `itr = 1`).

## 5. Ba bug đã trả giá — đừng lặp lại

**(a) `object_direction` không cùng ngữ nghĩa giữa hai chiến dịch.** `[ĐO]`: bag Crafter dir `+1` chạy
**cùng chiều** ego (y 29,5 → 139,1 m); bag Golf dir `+1` lại **tiến lại gần** (y 45,4 → 11,2 m). Dùng
cột này làm filter cho ra **0 frame** trên cả 171 bag Golf. Sửa: quyết định bằng **hình học** —
`median d(range)/dt > 0` (xe đang rời xa). Tỉ lệ: Crafter 81 rời / 81 tiến; Golf 85 rời / 86 tiến.

**(b) ibeo đổi nhãn phân loại theo tốc độ.** Cùng một chiếc VW Crafter được gọi `Car` ở 100 km/h nhưng
`Truck` ở 50 km/h; bag Crafter 50 km/h **không có mẫu `Car` nào** (9 bag ⇒ 0 frame). Sửa: bỏ phụ thuộc
nhãn, chọn track theo tốc độ metadata.

**(c) Track rác của ibeo.** Chọn track có rate khớp nhất từng vớ phải track **6 mẫu** (`Unknown Big`,
range 17 → 28 m, rate 100,3 km/h) thay vì track thật **51 mẫu** (range 29,8 → 139,2 m, rate 104,6).
Hệ quả: số cụm bị đẩy lên **~1,4×** trên cả hai lớp. Sửa: sau khi lọc theo tolerance, chọn track
**nhiều mẫu nhất** và bỏ track < 10 mẫu.

## 6. Độ bất định — phải ghi kèm mọi con số

| Nguồn | Độ lớn |
|---|---|
| **Bề dày lát `Δ`** (1,0 → 6,0 m), Crafter @100 km/h | **17,2 – 35,9 cụm** (2,1×) ← chi phối |
| Mẫu (bootstrap mức bag) | CI95 half-width **1–5 cụm** (≈ ±5–20 %) |
| Độ dài hộp `L` (2,8 → 20 m) | không bất biến, vì mật độ plume giảm theo độ sâu |

⇒ Bảng xác định tới **±30–40 %** do sai số **định nghĩa vùng**, dù sai số thống kê đã nhỏ. Cổng B
(`sinh/thật ∈ [0,7; 1,5]`) và mọi claim từ bảng phải đọc cùng dải này.

## 7. Còn thiếu

- Hộp dài `L = 20 m` là chốt theo paper + quãng trôi; **chưa quét độ nhạy L** ở đây (mới quét `Δ`).
- Mức nước: gộp cả `itr_after_water` 1–6 (mỗi ô 9–13 bag) vì tách ra thì mỗi ô chỉ 1–2 bag. Bảng
  `itr = 1` (đúng điều kiện eval) có CI95 rộng ±50 % với mẫu hiện có.
- Chỉ đo bag có track ibeo dài ≥ 10 mẫu và xe **rời xa** ego; số còn lại bị loại (xem §5).

## 8. Hạ tầng

- `scripts/roadspray_static_clusters.py` — range-image nền + RANSAC mặt đường + DBSCAN góc bằng
  cKDTree/union-find (không sklearn, không O(n²)).
- `scripts/roadspray_static_plume_box.py` — định vị xe từ ibeo (chọn theo tốc độ metadata), cắt hộp
  sau đuôi, cắt lát cự ly, hộp đối chứng phía trước; `--zip/--speed/--water/--bags/--limit`.
- Chạy lại: `python scripts/roadspray_static_plume_box.py --zip <zip> --out <file>.jsonl`
  (~13 phút cho 163 bag Crafter, ~17 phút cho 171 bag Golf).

---

# 9. CẬP NHẬT 2026-11-19 — cột **Δ = 1,0 m** là cột chuẩn thức `[ĐO]`

Quyết định của Lead (A3, 2026-11-19): bảng cụm/frame dùng cho calibration phải lấy từ
**bề dày lát Δ = 1,0 m**, không phải Δ = 2,5 m. Lý do: DBSCAN của paper chạy trên
`(azimuth, elevation)` **không có chiều cự ly**, nên trong một lát cắt dày, nhiều đám thật
nằm dọc tia bị nối thành một chuỗi (chain-merging) ⇒ số cụm bị **thổi phồng 1,6–2,1×**
khi tăng Δ. Đo được trên cùng dữ liệu (Crafter, `.scratch/roadspray-cal/tmp/a3_targets_static.json`):

| km/h | cpf Δ=1,0 | cpf Δ=2,5 | cpf Δ=6,0 | share Δ=1,0 | share Δ=2,5 | share Δ=6,0 |
|---|---:|---:|---:|---:|---:|---:|
| 50 | **9,04** | 5,96 | 3,61 | 77,9 % | 82,4 % | 92,3 % |
| 100 | **35,86** | 26,07 | 17,21 | 39,2 % | 51,8 % | 71,2 % |
| 130 | **33,08** | 22,63 | 13,74 | 34,7 % | 53,2 % | 75,1 % |

## 9.1 Recipe đo lại từ raw `[ĐO]`

Nguồn raw: `.scratch/roadspray-cal/tmp/plume_crafter_v5.jsonl` — output của
`scripts/roadspray_static_plume_box.py` (81 bag Crafter, `itr_after_water` 1/3/5).
Recipe dựng lại (đã **validate ngược**, xem §9.2):

1. Chỉ giữ frame có xe ở **18 m ≤ `car_range` ≤ 38 m** (đúng cửa sổ cự ly của phép đo static).
2. Với mỗi frame, lấy danh sách cụm ở cột `rear_by_width["1.0"]` (lát Δ = 1,0 m; vùng sau
   đuôi W = 3,4 m, H = 1,5 m tính từ mặt đường, sâu 20 m — xem §3).
3. `r50` = **median** của `radius` trên mọi cụm của tốc độ đó; `rsig` = **std của `log(radius)`**
   (`ddof = 0`), tức sigma của lognormal bán kính.
4. `radius` của một cụm = *"maximum distance of detections to the respective cluster center"*
   — đúng định nghĩa Paper A §III-B, tính trong `static_slice_cluster_sizes()`.

## 9.2 Validate ngược `[ĐO]`

Recipe trên tái tạo **chính xác** (sai số làm tròn < 0,001) mọi số công bố trong
`a3_targets_static.json`:

| key | r50 tính lại | r50 trong file | rsig tính lại | rsig trong file |
|---|---:|---:|---:|---:|
| `50_1.0` | 0,349 | 0,349 | 0,754 | 0,7539 |
| `100_1.0` | 0,292 | 0,292 | 0,727 | 0,7274 |
| `130_1.0` | 0,311 | 0,311 | 0,714 | 0,7140 |

Và tái tạo **đúng toàn bộ bảng Δ = 2,5 cũ** đang nằm trong `spray/plume_state.py` trước
2026-11-19 (0,70 / 0,60 / 0,60 / 0,45 / 0,53 / 0,48 / 0,49 / 0,56 / 0,66 → khi tính đủ
9 tốc độ: khớp từng mốc sau khi làm tròn 2 chữ số). Hai phép validate ngược này là lý do
protocol D2-chặt đứng được: số dẫn từ static **tái lập được từ raw**, không phải số bịa.

## 9.3 Hệ quả

- Bảng calibration `_CLUSTER_VISIBLE_BY_SPEED` (Crafter) được dựng từ cột Δ = 1,0:
  9,04 @50 · 35,86 @100 · 33,08 @130, nội suy tuyến tính 6 mốc còn lại.
- Bảng Golf **chưa có phép đo static Δ = 1,0 tương ứng**; các giá trị Golf trong code vẫn
  là Δ = 2,5 cũ ⇒ **chưa validate, A3 không dùng tới**; nếu sau này dùng Golf phải đo lại.
- Cột Δ = 2,5/6,0 chỉ còn dùng làm **dải bất định định nghĩa vùng** (±30–40 %), không dùng
  để chọn tham số.
