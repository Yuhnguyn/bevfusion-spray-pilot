# Spike: đo spray trên RoadSpray `*_static` không dùng nhãn (2026-11-18)

Người làm: lead. Mục đích: thay `_CLUSTER_VISIBLE_BY_SPEED` (đang đo trên SSPP `cal`, leak — V2)
bằng nguồn **RoadSpray `*_static`** đúng như ADR-0006 **D2**. Nhãn số: `[ĐO]` trên máy này.

**Kết luận ngắn: dữ liệu và hạ tầng đã sẵn sàng và đọc được, nhưng phép đếm cụm không nhãn
chưa tách được spray khỏi nhiễu cảnh — nhiễu nền cùng bậc với tín hiệu. Cần chốt hướng trước
khi tiêu thêm thời gian.**

---

## 1. Dữ liệu đã có, khớp release `[ĐO]`

| File | Byte | Khớp tudatalib |
|---|---:|---|
| `data/roadspray/Crafter_static.zip` | 7 924 255 130 | ✅ (163 bag, `163 vs 162` dòng xlsx — 1 bag không có trong metadata) |
| `data/roadspray/Crafter_dynamic.zip` | 6 127 018 713 | ✅ (108 bag) |
| `data/roadspray/meta_data_measurement.xlsx` | 26 774 | ✅ **mới tải 2026-11-18** qua DSpace REST |
| `data/roadspray/meta_data_dataset.json` | 2 517 | ✅ |
| `~/Downloads/Golf_dynamic.zip` | 6 009 340 245 | ✅ chưa copy vào `data/` |
| `Golf_static.zip` | 5 460 144 118 | ❌ **chưa tải** (link REST đã có) |

`meta_data_measurement.xlsx` = 549 dòng, header verbatim
`file_name, object_name, object_velocity, object_direction, ego_velocity, distance_to_object,
amb_tmp, unimog_direction, measurement_itr, itr_after_water, comment`.
- **static = 333 dòng** (Crafter 162 + Golf 171), `ego_velocity = 0`, 9 tốc độ 50–130,
  `itr_after_water` 1–6 (+2 dòng 7/8 của Golf), `measurement_itr` 1–3 (Golf có 4).
- dynamic = 108 + 108 dòng, `ego_velocity = object_velocity`, `distance_to_object ∈ {20, 30}`.

Nghĩa là **tốc độ + mức nước của từng bag có sẵn, không cần decode ADMA**.

## 2. Bag thật sự đọc được `[ĐO]`

- `/velodyne_points`: **VLP-32C**, 9,95 Hz (Δt ≈ 100 ms, khớp paper), fields
  `x, y, z, intensity (float32), ring (uint16)` — **cùng layout với điểm SSPP**.
- Ego **đỗ thật**: `/adma/twist` mean 0,005 km/h, max 0,057 km/h trên bag 12-40-53.
- Sensor cao hơn mặt đường: mặt đường nằm ở `z ≈ −2,0 m` trong khung `velodyne`
  (metadata ghi 1,686 m tới móc sau — RANSAC ra 14 509 inlier ở `z = −2,01`).
  ⇒ **cảnh báo**: mọi code giả định "mặt đường ở z=0" đều sai ở dataset này.

## 3. Nguyên lý tách spray không nhãn (và tại sao nó chưa đủ)

Vì ego đỗ, mỗi tia `(ring, az_bin)` luôn trả về cùng một vật thể ở cùng range ⇒ dựng
**range-image nền** = median range mỗi bin trên cả bag; điểm có `|r − median| > tol` là residual.
Sau đó bỏ điểm dưới mặt đường (RANSAC) và bỏ điểm thuộc thân xe, còn lại là spray.

Đo trên bag 12-40-53 (Crafter 120 km/h, `itr_after_water=2`):

| Frame | residual | > mặt đường | cụm | ghi chú |
|---|---:|---:|---:|---|
| 0 (chưa có xe) | 4 197 | **0** | 0 | nền sạch |
| 30 (chưa tới) | 4 930 | 151 | 1 | nền sạch |
| 46 (đang qua) | 8 702 | **951** | 38 | tín hiệu rõ |
| 56 (xe đã qua) | 6 972 | 732 | 50 | plume còn tan dần |

⇒ **Tín hiệu có thật và bám đúng động học plume** (tăng khi xe qua, tắt dần sau đó).

**Nhưng** đo trên 8 bag (2 bag × 4 tốc độ, `itr_after_water=1`) thì nhiễu nền quá lớn:

| Tốc độ | cụm/frame (frame vắng) | cụm/frame (frame có xe) | cụm trong dải 20–30 m |
|---:|---:|---:|---:|
| 50 | 98,2 | 111,0 | 24,7 → 22,4 |
| 100 | 89,8 | 108,6 | 23,0 → 19,6 |
| 120 | 94,6 | 106,2 | 23,8 → 20,2 |
| 130 | 92,1 | 111,8 | 24,1 → 20,3 |

Hai điều đáng chú ý:
1. **Nhiễu nền ~90–100 cụm/frame** (cây cối/quanh test track): trong không gian
   `(azimuth, elevation)`, **mọi mặt liền nhau đều chain thành cụm**, nên bụi cây cho rất nhiều cụm.
2. Dải 20–30 m **không** tăng khi có xe (24,7 → 22,4) ⇒ spray không nằm cố định ở 25 m như
   cách paper mô tả; nó **đi theo xe**. Muốn đếm đúng phải neo ROI vào xe, không neo vào cự ly.

Tách thân xe thì làm được: Crafter hiện ra thành cụm **cao 2,5–2,7 m** (đúng chiều cao van),
extent ≈ `2,2 × 5,0 m`, range lùi đều 36,7 → 48,3 m qua các frame — nhưng chỉ nhận được
**35 frame / 480 frame** của 8 bag, và số cụm trong ±20°/±15 m quanh xe chỉ 0–7 (thấp hơn
nhiều so với ~20–30 cụm/frame mà bảng hiện tại nói). Tức là plume **bị merge vào chính cụm thân xe**
hoặc bị lọc mất — chưa kiểm chứng được.

## 4. Ba hướng, cần chốt

| | Hướng | Chi phí | Rủi ro |
|---|---|---|---|
| **D-a** | Đẩy tiếp phép tách không nhãn: ROI neo theo xe + `intensity < 10` + dải độ cao + kiểm tra bền theo thời gian | 1–2 ngày, kết quả chưa chắc | Cao: nhiễu nền cùng bậc tín hiệu |
| **D-b** | Đọc số **Fig. 4** của Paper A (đúng bộ giá trị calibration của paper) | 2–3 giờ | Sai số đọc hình ~5–10 %; không độc lập với paper |
| **D-c** | Đo lại trên SSPP nhưng **tách scene tuyệt đối** + tăng mẫu 10× (450 frame/ô thay vì 45) | 3–4 giờ, 0 GPU | Không dùng RoadSpray static ⇒ lệch D2, phải ghi ADR |

Điểm quan trọng cho cả ba: **bảng hiện tại chỉ có 45 frame/ô**, nên CI95 của mỗi ô ước cỡ
±20–30 % — đủ để giải thích đường cong không đơn điệu (`29,24 @100 → 17,58 @120`). Nghĩa là
kể cả khi giữ nguyên nguồn dữ liệu, **tăng mẫu** vẫn là việc đáng làm trước khi dùng bảng
làm đích cho cổng B (`sinh/thật ∈ [0,7; 1,5]`).

## 5. Hạ tầng để lại

- `scripts/roadspray_static_clusters.py` — đọc bag trong zip, dựng range-image nền,
  RANSAC mặt đường, DBSCAN góc bằng cKDTree (không sklearn/O(n²)), ghi JSONL descriptor
  từng cụm (`n, cx, cy, cz, range, rmin, rmax, ex, ey, ez, h, intensity`), resumable,
  `--bags/--limit/--only-water`. ~24 s/bag ⇒ cả 163 bag ≈ 65 phút.
- Đã kiểm: `python scripts/roadspray_static_clusters.py --limit 2`.
