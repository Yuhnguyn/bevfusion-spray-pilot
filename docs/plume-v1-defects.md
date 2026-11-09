# Audit generator plume v1 — 5 lỗi cấu trúc

**Ngày:** 2026-11-10 · **Người làm:** PM (audit, không sửa code) · **Trạng thái:** đầu vào cho planning **ticket 25 (plume simulator v2)**
**Bằng chứng trực quan:** `docs/figs/plume/v1-audit/compare.mp4` (10 s) và `compare_still.png` · script: `render_compare.py`
**Issue GitHub:** xem danh sách ở mục 6.

## 0. Vì sao có audit này

Kết quả A/B của ticket 11 là **null** (`interaction = −0,0031`, CI95 [−0,0140; +0,0017]). Chẩn đoán
`11-i` mô tả *triệu chứng* (hộp dự đoán dịch trung vị 3 mm, 0 hộp mới, 1,9 % hộp sát IoU 0,5) nhưng
chưa trả lời *vì sao can thiệp lại yếu đến thế*. Audit này đọc **code tham chiếu đã publish** và đo
**chính generator của repo**, thay vì suy luận từ thống kê tổng hợp.

## 1. Phương pháp

- **Nguồn tham chiếu:** `openMSL/sl-1-2-reflection-based-lidar-object-model` (MPL-2.0),
  `src/model/strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp`
  (833 dòng), tải 2026-11-10. Số dòng dưới đây trỏ vào file đó.
- **Đo generator:** gọi `spray.plume.inject_plume` với cloud nền tổng hợp (~40.000 điểm trong ±51 m),
  1 box, 60 seed/kịch bản, box dài 4,6 / 10,5 / 13,7 m, tốc độ 50–100 km/h. Không cần dữ liệu nuScenes.
- **Render:** cùng một kịch bản (xe 4,6 m @80 km/h) chạy generator thật (panel 1) và một bản minh hoạ
  cơ chế tham chiếu (panel 2, **không phải code repo**).

## 2. Năm lỗi

### D1 — Toạ độ `z` sai frame: cụm lơ lửng 2,0–3,8 m trên mặt đường · **[P0]**

| | |
|---|---|
| Code | `spray/config/plume_default.yaml:20` → `height_range_m: [0.2, 2.0]`; `spray/plume.py:242` → `z = rng.uniform(*cfg.height_range_m)` gán **tuyệt đối** vào cột `z` của cloud |
| Frame toạ độ | `point_cloud_range` z = `[−5, 3]`; LIDAR_TOP của nuScenes cao ≈ **1,84 m** ⇒ mặt đường ≈ **−1,84 m** trong frame LiDAR |
| Hệ quả | cụm nằm ở **2,0–3,8 m trên mặt đường**, tức **trên nóc xe** (xe cao 1,7 m). Không tia nào của xe phản xạ ở độ cao này và cụm không tương tác với thân xe |
| Tham chiếu | `dee.cpp:568` — `z = z_obj − h_obj/2 + 1,5/2`, tức volume nằm **0…1,5 m trên mặt đường** |
| Cần xác nhận | đo `z` của điểm mặt đường trên **1 frame nuScenes thật** (script audit CPU, mục 5). Nếu đúng → `z = z_ground + U(0; 1,5)` |

Đây là lỗi nặng nhất vì nó làm sai **cả ba** thứ cùng lúc: độ cao, khả năng bị tia chạm, và tương tác với box.

### D2 — Neo cụm từ **tâm box**, không có bề dài `v·Δt` · **[P0]**

| | |
|---|---|
| Code | `plume.py:240–247`: `distance ~ U(1; 10)`, `center = box_centre + direction·distance`, `direction = −v̂` |
| Đo | trung vị điểm cách **mặt đuôi** **4,01 m** (p90 **6,93 m**) — xe 4,6 m @100 km/h, 120 seed |
| Tham chiếu | volume dài `|v|·Δt` = **1,39 m @50 / 2,22 @80 / 2,78 @100 km/h**, neo tại `obj.pos − (L/2 + L_vol/2)` ⇒ **bắt đầu đúng mặt đuôi** (`dee.cpp:559–567`); tâm cụm uniform **trong volume đó** (`:516–518`) |
| Mật độ | **3,6 điểm/m³** (v1) vs **14,0 điểm/m³** (volume tham chiếu) ⇒ **2,3× loãng hơn** ngay sau đuôi xe |
| Provenance | `docs/plume-model-provenance.md:22` dán nhãn `[PAPER]` cho "cách 1–10 m", nhưng paper chỉ nói **định tính** ⇒ phải đổi thành `[CHỌN]` khi v2 chốt |

### D3 — Tự triệt tiêu liều: **14–63 %** điểm bị `rejected_box` xoá · **[P1]**

| | |
|---|---|
| Code | `plume.py:287–294` xoá mọi điểm nằm trong box (margin `0,2 m`) |
| Đo (60 seed) | xe 4,6 m: 134,6 điểm sinh → **18,7 (13,9 %)** bị xoá · truck 10,5 m: **45,7 %** · trailer 13,7 m: **63,1 %** |
| Nguyên nhân | `distance` tính từ **tâm** nên `d < L/2` là nằm trong thân xe |
| Hệ quả | liều thực tế phụ thuộc **loại xe**, không phải tham số thiết kế; với trailer gần **2/3** công sinh bị vứt bỏ |

### D4 — Stateless mỗi frame ⇒ **không có vệt** · **[P1]**

| | |
|---|---|
| Code | generator không có state; `K = 2,51` chỉ là **hệ số nhân số cụm**, không tạo cấu trúc không–thời gian |
| Đo | trong clip, trung vị khoảng cách sau đuôi **dao động 1,57 → 7,33 m** giữa các frame của **cùng một kịch bản** |
| Tham chiếu | cụm sống tới `4T`, tồn tại `exp(−age/T)` (`dee.cpp:262`, `:446`), vận tốc = vận tốc vật + drag `N(−0,12; 0,04)` (`:537–538`) ⇒ sinh ra **vệt** bám đuôi xe |
| Hệ quả | detector chỉ thấy đám bụi rời rạc, không thấy một khối nước liên tục — khác hẳn hiện tượng thật |

### D5 — Không mô phỏng **tương tác với phép đo** · **[P1]**

Thiếu cả 5 cơ chế mà code tham chiếu có:

| Cơ chế | Tham chiếu | v1 | Hệ quả |
|---|---|---|---|
| visibility (điểm trong vùng bóng của xe) | ray–sphere `:456–485` | không | xe đi ngược chiều ⇒ cụm nằm **sau thân xe**, LiDAR thật không thể trả về → sinh điểm **bất khả** |
| occlusion (tia bị chặn → return của xe mất) | `add_max_detection` `:781` | không | không bao giờ **lấy mất** tín hiệu của xe |
| attenuation | `exp(−2·0,04·d)` `:271–272` | không | intensity không đổi |
| thay return yếu theo `power = intensity/d²` | `:290` | không | — |
| `P_det` per-tia | `min(1, lognormal(−2,3; 1,1))` `:250–300` | không | thống kê per-tia không tái lập được |

Đây là khác biệt **bản chất**: v1 *rắc thêm rác*; mô phỏng thật *làm hỏng phép đo*.

## 3. Vì sao 5 lỗi này giải thích kết quả null

- Plume chỉ thêm **147 điểm = 0,42 %** cloud (34.700 điểm, keyframe-only).
- Đường kính cụm **0,6 m** = **đúng 1 cell** của detection head (180×180 ô trên 108 m ⇒ 0,6 m/ô).
  8 cụm ⇒ 8 ô heatmap trên 32.400 ô.
- D1+D2+D3 làm liều thực tế **vừa loãng 2,3×, vừa mất 14–63 %, vừa nằm sai độ cao**.
- D5 bỏ đi cơ chế duy nhất khiến detector **mất** tín hiệu ⇒ mAP chỉ có thể nhúc nhích qua re-ranking.

## 4. Chương trình v2 (đầu vào planning)

### 4.1 Bốn tầng, làm theo thứ tự

| Tầng | Nội dung | Nguồn |
|---|---|---|
| **L1 Hình học** | neo **mặt đuôi** +`0,2 m`; dài `v·Δt`; rộng **3,4 m** đều; cao **0–1,5 m trên mặt đường**; rải theo **tuổi**: `distance = v·age`, `age ~ exp(−age/T)` cắt `[0,4T]` | `dee.cpp:559–567`, `:516–518`, `:530` |
| **L2 Khả kiến** | chỉ sinh điểm ở nơi tia tới được: bin `(azimuth, elevation)` của cloud hiện có, so cự ly; điểm thật **gần hơn** ⇒ **không sinh** (vùng bóng) | suy ra từ ray–sphere `:456–485` |
| **L3 Tương tác** | tia cắt cụm ⇒ return thành điểm spray ở cự ly ngẫu nhiên **trong** cụm, **thay thế** return của xe nếu `power` thắng; attenuation `exp(−2·0,04·d)` cộng dồn dọc tia | `:250–300`, `:781`, `:271` |
| **L4 Thời gian** | cụm sống `4T`, trôi theo vận tốc + drag, mờ `exp(−age/T)` | `:262`, `:446`, `:537` |

L4 chỉ có nghĩa khi có **sweeps** hoặc chuỗi 10 Hz; với keyframe-only (2 Hz) thì L4 ≈ L1.

### 4.2 Ba regime liều — chọn theo phân bố thật, đăng ký trước

| Regime | điểm/frame | Nguồn |
|---|---|---|
| light (hiện tại) | ~150 | p50 SemanticSpray = 159 |
| **medium (đề xuất)** | **~1.100** | **p90 = 1.138,6** |
| heavy | ~4.000 | max = 4.088 |

### 4.3 Tiêu chí nghiệm thu (không phải "mAP giảm")

Khớp thống kê SemanticSpray: điểm/frame (p50/p90/max), cụm/frame, điểm/cụm, extent (p50/p90),
khoảng cách tới foreground, chiều cao (p10/50/90), `r_range/r_extent` — mỗi chỉ số ±20–25 %.
Cộng **property test**: (a) **0 %** điểm nằm trong vùng bóng, (b) **0 %** điểm nằm trong box,
(c) mật độ giảm đơn điệu theo tuổi.

## 5. Việc phải làm trước khi sửa code (0 GPU)

1. **Audit CPU trên mini split** (chỉ cần annotation, không cần `.bin`): % frame có ≥1 cụm, phân bố
   liều/frame, % điểm bị `rejected_box`, % frame có xe đi ngược chiều. → chốt tham số liều L1.
2. **Đo `z` mặt đường** trên 1 frame nuScenes thật → xác nhận/ bác bỏ D1.
3. Chỉ sau đó mới viết spec ticket 25 và code.

## 6. Issue GitHub

| # | Lỗi | Nhãn |
|---|---|---|
| 1 | D1 — toạ độ z sai frame | `priority:P0` `bug` `area:plume-sim` |
| 2 | D2 — neo từ tâm box, thiếu `v·Δt` | `priority:P0` `bug` `area:plume-sim` |
| 3 | D3 — 14–63 % điểm bị `rejected_box` xoá | `priority:P1` `bug` `area:plume-sim` |
| 4 | D4 — stateless, không có vệt | `priority:P1` `enhancement` `area:plume-sim` |
| 5 | D5 — thiếu visibility/occlusion/attenuation | `priority:P1` `enhancement` `area:plume-sim` |
| 6 | Umbrella: Ticket 25 — spec v2 + acceptance | `enhancement` `area:plume-sim` |