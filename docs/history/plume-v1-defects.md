# Audit generator plume v1 — 5 lỗi cấu trúc

**Ngày:** 2026-11-10 · **Người làm:** PM (audit, không sửa code) · **Trạng thái:** đầu vào cho planning **ticket 25 (plume simulator v2)**
**Kiểm chứng độc lập:** 2026-11-10, PM đo lại toàn bộ trên generator thật — 3 chỗ phải sửa số (§7). Script: `~/.hermes/drafts/spray-pilot/validate_v2.py`, `validate_gap.py`, `density.py`.
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
| Đo lại | điểm cách mặt đường **1,35 / 2,93 / 4,53 m** (min/p50/max, 60 seed). Dải 2,0–3,8 m là **tâm cụm**; điểm rời rạc rộng hơn vì bán kính cụm tới 1,0 m |
| Tham chiếu | `dee.cpp:568` — `z = z_obj − h_obj/2 + 1,5/2`, tức volume nằm **0…1,5 m trên mặt đường** |
| Cần xác nhận | đo `z` của điểm mặt đường trên **1 frame nuScenes thật** (script audit CPU, mục 5). Nếu đúng → `z = z_ground + U(0; 1,5)` |

Đây là lỗi nặng nhất vì nó làm sai **cả ba** thứ cùng lúc: độ cao, khả năng bị tia chạm, và tương tác với box.

### D2 — Neo cụm từ **tâm box**, không có bề dài `v·Δt` · **[P0]**

| | |
|---|---|
| Code | `plume.py:240–247`: `distance ~ U(1; 10)`, `center = box_centre + direction·distance`, `direction = −v̂` |
| Đo (audit) | trung vị điểm cách **mặt đuôi** **4,01 m** (p90 **6,93 m**) — xe 4,6 m @100 km/h, 120 seed |
| Đo lại (PM) | neo đúng mặt đuôi `cx − L/2`, xe 4,6 m **@80 km/h, 60 seed**: p50 **3,32 m**, p90 **7,02 m**, xa nhất **8,23 m**. p90 khớp, **p50 lệch 0,7 m** ⇒ số 4,01 m không tái lập được, kết luận định tính không đổi |
| Tham chiếu | volume dài `|v|·Δt` = **1,39 m @50 / 2,22 @80 / 2,78 @100 km/h**, neo tại `obj.pos − (L/2 + L_vol/2)` ⇒ **bắt đầu đúng mặt đuôi** (`dee.cpp:559–567`); tâm cụm uniform **trong volume đó** (`:516–518`) |
| Mật độ (đo lại) | so theo **mét dài vệt** thay vì m³: v1 rải ~140 điểm trên **9 m** = **15,5 điểm/m**; tham chiếu dồn 159 điểm vào `v·Δt` ⇒ **16,9× loãng hơn @60 km/h · 4,7× @80 · 2,3× @100 · 1,4× @120**. Con số 3,6-vs-14,0 (2,3×) chỉ đúng ở 100 km/h |
| Provenance | `docs/history/plume-model-provenance.md:22` dán nhãn `[PAPER]` cho "cách 1–10 m", nhưng paper chỉ nói **định tính** ⇒ phải đổi thành `[CHỌN]` khi v2 chốt |

### D3 — Tự triệt tiêu liều: **14–63 %** điểm rơi vào thân xe · **[P1, tiềm ẩn — phụ thuộc D1 + D6]**

| | |
|---|---|
| Code | `plume.py:287–294` xoá mọi điểm nằm trong box (margin `0,2 m`) |
| Đo (audit) | xe 4,6 m: 134,6 điểm sinh → **18,7 (13,9 %)** bị xoá · truck 10,5 m: **45,7 %** · trailer 13,7 m: **63,1 %** |
| Nguyên nhân | `distance` tính từ **tâm** nên `d < L/2` là nằm trong thân xe |
| Hệ quả | liều thực tế phụ thuộc **loại xe**, không phải tham số thiết kế; với trailer gần **2/3** công sinh bị vứt bỏ |

**Sửa lại sau kiểm chứng (2026-11-10).** Ba đại lượng khác nhau đã bị gộp làm một trong bản đầu.
Đo trên **cùng một tập điểm ứng viên** (60 seed × ~142 điểm, box `z = mặt đường + h/2`), script `d3_convention.py`:

| Cỡ xe | A. Code hiện tại | B. Chỉ sửa thứ tự `w`/`l` (D6) | C. Chỉ nâng box lên dải 0,2–2,0 m |
|---|---|---|---|
| xe con 4,6 × 1,9 × 1,7 | **0,00 %** | 0,40 % | 1,66 % |
| truck 10,5 m | **1,50 %** | 30,2 % | 1,67 % |
| trailer 13,7 m | **1,66 %** | **63,6 %** | 1,67 % |

- **A = hôm nay: 0,0–1,7 %** (script thứ hai, box cao 3,4/3,9 m, cho 0,03–2,1 %; cả hai đều ≤ 2 %).
  Hai lỗi cùng che cho `rejected_box`: D1 đẩy plume ra khỏi dải `z` của box, và D6 làm hộp khử mỏng đi 5 lần
  theo trục vệt (§7). Vậy D3 **chưa gây hại**.
- **B** cho thấy sửa **D6 một mình** là đủ để con số 30–64 % xuất hiện ngay ⇒ D6 là lỗi thật, không phải chi tiết vô hại.
- Khi sửa **cả D1 và D6** (plume nằm 0–1,5 m trên mặt đường, hộp đúng quy ước), tỉ lệ thành **≈14 % / 45 % / 63 %**
  — đúng bằng con số bản đầu. Nói cách khác **13,9–63,1 % là tỉ lệ *sau khi* sửa D1 + D6**, không phải tỉ lệ hôm nay.
- ⇒ **D1 và D6 phải sửa trong cùng một thay đổi.** Nếu chỉ sửa D6 trước, liều tụt 30–64 % ngay và rất dễ đọc sai
  là "v2 kém hơn v1".

### D4 — Stateless mỗi frame ⇒ **không có vệt** · **[P1]**

| | |
|---|---|
| Code | generator không có state; `K = 2,51` chỉ là **hệ số nhân số cụm**, không tạo cấu trúc không–thời gian |
| Đo | trong clip, trung vị khoảng cách sau đuôi **dao động 1,57 → 7,33 m** giữa các frame của **cùng một kịch bản** |
| Đo lại (PM) | 20 seed cùng box 4,6 m @80 km/h: trung vị sau đuôi (neo đúng mặt đuôi) **1,16 → 5,84 m**, **std 1,33 m** ⇒ xác nhận: vị trí bị rút lại mỗi frame, không có vệt bám đuôi |
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

**Đo lại (PM) — xác nhận định lượng:** điểm gốc giữ nguyên tuyệt đối (40.000 → 40.105, không điểm nào bị lấy đi);
100 % điểm plume có `intensity = 0` và `ring = 0`. Với **xe đi ngược chiều**, **100 %** điểm plume nằm **xa ego hơn**
tâm box (trung vị 26,97 m so với 20,0 m) ⇒ vùng bóng của thân xe ⇒ LiDAR thật không thể trả về.
Với xe cùng chiều, trung vị 17,62 m < 25 m ⇒ khả kiến bình thường. Đây là tiêu chí đo được cho L2 của v2.

## 3. Vì sao 5 lỗi này giải thích kết quả null

- Plume chỉ thêm **147 điểm = 0,42 %** cloud (34.700 điểm, keyframe-only).
- Đường kính cụm **0,6 m** = **đúng 1 cell** của detection head (180×180 ô trên 108 m ⇒ 0,6 m/ô).
  8 cụm ⇒ 8 ô heatmap trên 32.400 ô.
- D1+D2+D3 làm liều thực tế **vừa loãng 4,7× (ở 80 km/h; 16,9× ở 60 km/h), vừa nằm sai độ cao**;
  phần "mất 14–63 %" hiện **chưa xảy ra** nhưng sẽ xảy ra ngay khi sửa D1 nếu không sửa D3 cùng lúc.
- Plume **đông cứng qua các epoch** (D8): hình học so với xe giống hệt ở mọi epoch ⇒ mạng có 14 epoch để học thuộc,
  đây không phải augmentation ngẫu nhiên.
- Toàn bộ điểm plume có `intensity = 0` (D8) — giá trị hiếm trong nuScenes thật ⇒ thêm một tín hiệu tầm thường để tách plume.
- Trần 2000 điểm (D7) khiến regime "nặng" không thể đạt đúng liều.
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
2. **Đo `z` mặt đường** trên 1 frame nuScenes thật → xác nhận/bác bỏ D1. Cùng frame đó chốt luôn
   thứ tự `w`/`l` của box production (D6) bằng cách so footprint box với chính điểm của xe.
3. Chỉ sau đó mới viết spec ticket 25 và code.

## 6. Issue GitHub

| # | Lỗi | Nhãn |
|---|---|---|
| 1 | D1 — toạ độ z sai frame | `priority:P0` `bug` `area:plume-sim` |
| 2 | D2 — neo từ tâm box, thiếu `v·Δt` | `priority:P0` `bug` `area:plume-sim` |
| 3 | D3 — 14–63 % điểm rơi vào thân xe (hiện chưa xoá vì D1 che; phải sửa cùng D1) | `priority:P1` `bug` `area:plume-sim` |
| 4 | D4 — stateless, không có vệt | `priority:P1` `enhancement` `area:plume-sim` |
| 5 | D5 — thiếu visibility/occlusion/attenuation | `priority:P1` `enhancement` `area:plume-sim` |
| 6 | Umbrella: Ticket 25 — spec v2 + acceptance | `enhancement` `area:plume-sim` |
| — | D6 (w/l box), D7 (trần 2000), D8 (đông cứng seed + intensity) | **chưa mở issue** — chờ chốt spec v2 |

## 7. Bổ sung sau kiểm chứng độc lập — 2026-11-10 (PM)

PM chạy lại generator thật (20–60 seed/kịch bản) và tải `dee.cpp` bản gốc để đối chiếu. Kết quả:
**D1, D4, D5 đúng**; **D2 đúng hướng nhưng p50 sai 0,7 m**; **D3 sai bản chất** (đã sửa ở trên).
Số dòng trích trong `dee.cpp` (`:568`, `:559–567`, `:516–518`, `:530`, `:446`, `:509–512`, `:537`, `:781`, `:271`) **khớp từng dòng**.
Riêng các *giá trị* `−2,3/1,1`, `0,04 m⁻¹`, ngưỡng 40 km/h nằm trong file **profile YAML**, không nằm trong `dee.cpp`
⇒ nhãn đúng là `[CHỌN]`/profile, không phải `[CODE]`.

Ba vấn đề mới, chưa có issue:

> Script tái lập (ngoài repo, `~/.hermes/drafts/spray-pilot/`): `validate_gap.py` (khoảng cách neo đúng mặt đuôi
> `cx − L/2`, `z` so với mặt đường), `d3_convention.py` (cùng tập điểm ứng viên, 3 quy ước hộp), `d3_check.py`,
> `validate_v2.py` (trần điểm + khả kiến + thuộc tính điểm).

### D6 — Box test bị **xoay 90°**: `width` dùng làm nửa trục dọc theo yaw · **[P0 khi sửa D1]**

`spray/plume.py:397–410` (`_inside_box`) đặt `width/2` lên `local_x` và `length/2` lên `local_y`. Trong frame LiDAR
nuScenes, `local_x` là **trục dọc theo hướng xe** ⇒ nửa trục dọc bị lấy bằng nửa **chiều rộng** (0,95 m cho xe con,
thay vì 2,3 m). Ba nguồn trong repo không khớp nhau: `nuscenes_converter.py:250,276` ghi `dims = b.wlh`
(slot 3 = rộng ≈1,9 m); cùng file `:507` lại đổi `wlh → lhw`; `tests/test_plume.py` dùng `[4,5; 1,9]` (slot 3 = dài).
Test của repo vì thế **không** bắt được lỗi này: nó đi theo quy ước ngược với dữ liệu production.

Tác động đo được (`d3_convention.py`, cùng tập điểm): hộp khử chỉ còn 1,50 % (truck) và 1,66 % (trailer);
**đổi đúng quy ước thì thành 30,2 % và 63,6 %**. Hiện chưa lộ ra ngoài vì D1 đã đẩy plume ra khỏi dải `z` của box.
**Chốt quy ước trên 1 frame thật**, cùng lần đo `z` mặt đường; sửa D6 cùng D1.

### D7 — Trần `max_injected_points = 2000` là **global**, chặn regime nặng · **[P1]**

Đo: 1 xe @80 km/h = 138 điểm/frame ⇒ **14,5 xe là chạm trần**. 16 xe → 2.340 điểm/frame, cắt **14,2 %**;
24 xe → cắt **24,4 %** và liều bão hoà đúng 2.000. Regime "heavy ~4.000 điểm/frame" (§4.2) **bất khả thi**
nếu không nâng trần; regime medium ~1.100 vẫn lọt. Trần cắt **ngẫu nhiên trên toàn bộ điểm**, nên liều mỗi xe
cũng thành không đồng đều.

### D8 — Can thiệp **đông cứng** qua các epoch + `intensity = 0` · **[P1]**

`PlumeTransform` đọc `seed` từ `metadata`/`results`; pipeline không đặt khoá này ⇒ luôn `seed = 0`,
RNG chỉ phụ thuộc token frame. Hệ quả: **hình học plume so với xe giống hệt nhau ở mọi epoch** —
đây là một nhiễu **cố định** gắn vào dataset, không phải augmentation ngẫu nhiên; với ~14 epoch, mạng
đủ thời gian học thuộc. Cộng thêm 100 % điểm plume có `intensity = 0` (hiếm trong nuScenes thật)
⇒ hai tín hiệu tầm thường để tách plume khỏi mưa thật. Cần quyết trong spec v2: lấy seed theo
`(token, epoch)` và lấy `intensity` từ phân bố đo trên SemanticSpray thật.

### Còn phải xác minh (cần 1 frame thật, 0 GPU)

| Việc | Trạng thái |
|---|---|
| `z` mặt đường = −1,84 m (D1) | chưa đo, doc tự nhận |
| thứ tự `w`/`l` production (D6) | chưa chốt |
| 159 điểm/frame của SemanticSpray | lấy từ ticket 12/16, chưa đo lại |