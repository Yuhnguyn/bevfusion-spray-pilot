# ADR-0006: Đơn vị eval, nguồn calibration, và criterion của thí nghiệm detection

Status: Accepted (2026-11-18). Thay phần eval của ADR-0005, **không** thay quyết định dùng SSPP
làm domain detection.

## Context

ADR-0005 chốt detection chạy trên SemanticSpray++ với split theo tốc độ: 16 scene train, 8 val,
12 test. Đo lại ngày 2026-11-18 (`.scratch/roadspray-cal/{power-design,spec}.md`, `[ĐO]`) tìm ra
bốn vấn đề làm kết luận **không đứng được**, kể cả khi augmentation có tác dụng thật:

1. **Test quá ít đơn vị.** Scene-level CV của tín hiệu spray là **0,483** (clusters/frame) và
   **0,761** (noise/frame); ICC 0,14–0,32 nên frame trong cùng scene không phải đơn vị độc lập.
   Với n = 12, **CI95 half-width = 28,4 % / 44,5 %** — cùng cỡ với effect 30 % mà
   `docs/PROJECT.md` §5 đang nhắm. Một effect thật 30 % sẽ có CI **[2 %; 58 %]** (clusters) và
   **[−14 %; 74 %]** (noise): không phân biệt được với "gần như không có tác dụng".
2. **Calibration leak.** Tham số generator chọn trên 104 scene `cal`, trong đó **6/12 test scene
   là `cal`** = **503/954 frame test (52,7 %)**. Và kể cả bỏ scene test khỏi `cal` thì vẫn còn
   **28 scene `cal` ở đúng 3 tốc độ test** — cùng group, cùng cự ly, cùng mẻ nước. Không thể sửa
   bằng cách lọc scene.
3. **Generator chưa đúng.** `docs/measurements/plume-root-cause.md` liệt kê: 3 lỗi quy ước box
   (đã sửa ở `3a971b8`), **lỗi 4× ngân sách cụm chưa sửa**, wet ground đang sửa dở, đuôi phân bố
   điểm/cụm chưa khớp (sinh max ~91 điểm vs thật 982–1 238). Đo plume với detector trước khi sửa
   sẽ trả lời sai: "plume vô hình" có thể chỉ là hệ quả của bug.
4. **Criterion nhị phân có power ~50 %.** `PROJECT.md` §5 đòi "point estimate ≥ 30 % **và** CI95
   loại trừ 0". Vế thứ nhất chặn trần xác suất pass ở **50 %** ngay cả khi effect thật đúng 30 %,
   với **mọi n**. Fail vì vậy không phân biệt được "augment vô dụng" với "xui".

Đồng thời, hai nguồn đã có sẵn cho phép sửa mà **không mua thêm dataset**:

- **RoadSpray `*_static`** (tudatalib/3537, 333 recording, ego đỗ) là đúng chiến dịch calibration
  của Paper A, **không có scene nào trùng SSPP**. Đây là nguồn calibration độc lập duy nhất.
- **Nhãn điểm của SSPP phủ cả 207 scene**, nên box 3D dựng lại được cho 171 scene thiếu box:
  **BEV IoU p50 = 0,931 / p5 = 0,847**, 99,8 % frame ≥ 0,7 trên 36 scene có box `[ĐO]`.

## Decision

Bốn quyết định, áp cùng nhau:

**D1. Đơn vị eval = 3-fold leave-speed-out trên cả 36 scene, pooled out-of-fold n = 36.**
Rule tất định `fold = rank(speed) mod 3 + 1` trên 9 tốc độ 50–130 km/h; mỗi fold 24 scene train /
12 scene test; mỗi scene được test **đúng một lần**, bởi model chưa từng thấy nó. Báo cáo chính là
**pooled**, per-fold là robustness, per-speed (50/130, n = 4) chỉ là **direction check**.

**D2. Calibration lấy từ RoadSpray `*_static`, không từ SSPP.** Generator được hiệu chỉnh trên dữ
liệu kalibre label-free của Paper A (§III-B), tách hoàn toàn khỏi mọi scene SSPP. Assertion cứng
`cal ∩ SSPP = ∅`. **Fallback** nếu D2 chưa xong: eval chỉ trên **18 held-out scene** (pooled n = 18,
CI half-width ≈ 0,18), khai rõ là phương án yếu hơn.

**D3. Criterion = effect size + CI95, paired theo scene.** Primary metric = SPF proxy/frame, effect
= chênh tương đối trung bình `log(FP_B/FP_A)` trên từng scene, CI95 = percentile bootstrap **theo
scene** (B = 20 000). Chỉ claim "giảm ≥ X %" khi **cận dưới CI ≥ X**. Không dùng pass/fail nhị phân.
Pre-registration ghi ở `.scratch/roadspray-cal/plan.md` §4.

**D4. Train được mở rộng bằng pseudo-box dựng từ `label == 1`, chỉ dùng cho TRAIN.** Eval/val/metric
**tuyệt đối** dùng human box. Giữ một cặp A/B **human-only** làm đối chứng để kết luận không phụ
thuộc lượng data. Gate: `purity ≥ 0,7` và `n_primary ≥ 50`.

## Thi hành D2 — kết quả đo (2026-11-18)

D2 được thi hành bằng một phép đo mới trên RoadSpray `*_static`, không nhãn, ghi đầy đủ ở
`docs/measurements/roadspray-static-clusters-by-speed.md`. Tóm tắt những gì **quyết định ADR**:

**Cách đo (mỗi thành phần có nguồn, không tự đặt).** Vùng đo = **hộp ngay sau đuôi xe** (Paper A §II
*"The initialization of clusters is restricted to the vehicle trajectory"*; §III-B đếm *"in a spray
filter region behind the vehicle"* rồi chia cho `độ dài vùng / quãng xe đi 1 scan` ⇒ độ dài vùng tự
triệt tiêu). Kích thước lấy từ `define_spray_volumes()` của code tác giả: **rộng 3,4 m, cao 1,5 m**.
Tách spray không cần nhãn bằng **range-image nền** (ego đỗ ⇒ mỗi tia luôn trả về cùng vật thể).
Định vị xe bằng track ibeo `ns == 'Car'`; mặt đuôi xác định từ điểm cao > 1,6 m (plume paper ≤ 1,5 m).
Chỉ đo bag `object_direction = +1` (ego thấy đuôi xe; `−1` là ngược chiều, plume bị che).

**Kết quả `[ĐO]` (9 bag/lớp/tốc độ, CI95 bootstrap ở mức bag, đối chứng âm phía trước xe = 0,0):**

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter cụm/frame | 6,0 | 13,2 | 19,0 | 26,7 | 24,8 | 25,7 | 27,4 | 20,6 | 22,2 |
| Golf cụm/frame | 4,7 | 8,8 | 13,2 | 17,8 | 20,9 | 22,6 | 22,0 | 25,8 | 25,2 |

Hai lớp cùng hình dạng (tăng tới ~22–27 cụm/frame ở 100–130 km/h). 81 bag Crafter và 85 bag Golf được
dùng; bag bị loại vì xe **tiến lại** gần ego (plume bị thân xe che) — xem doc §5.

**Kiểm chứng chéo ba nguồn độc lập:**

| Cặp so sánh | Kết quả |
|---|---|
| static vs bảng SSPP cũ (`cal`, 45 frame/ô) | tỉ lệ **1,13×** (0,91–1,32), Pearson **r = 0,79**, cùng chạm đáy 120 km/h |
| bảng SSPP **per-fold không leak** vs static | r = 0,77 (bảng fold khô hơn vì 10/12 scene `itr` 2–6) |
| bảng cũ vs SSPP ở **đúng điều kiện eval** (`itr = 1`, 2 scene/ô) | lệch 12,2 %, **r = 0,98** |

⇒ Hệ quả cho D2: **bảng cũ không sai số, nó chỉ bị leak.** Đổi nguồn sang static là sửa *protocol*,
không sửa *con số*; độ dịch trung bình ~1,13×, nằm trong dải bất định.

**Độ bất định phải khai kèm (quan trọng cho D3).** Thống kê ±10 % (đã nhỏ sau khi tăng lên 54 bag),
nhưng **định nghĩa vùng** chi phối: bề dày lát cự ly từ 1,0 → 6,0 m làm số cụm đổi **17,9 ↔ 39,8**
(2,2×) tại 100 km/h. Nên bảng chỉ xác định tới **±30–40 %**. **Cổng B (`sinh/thật ∈ [0,7; 1,5]`) và
mọi claim từ bảng phải đọc cùng dải này**; không được coi bảng là số chính xác.

**Trạng thái thi hành:** **XONG** — `_CLUSTER_VISIBLE_BY_SPEED` trong `spray/plume.py` đã thay bằng
bảng RoadSpray static cho **cả hai lớp** (2026-11-18 23:40), 203 test xanh. Bảng SSPP `cal` cũ giữ lại
trong `docs/measurements/semantic-spray-clusters-by-speed.md` để đối chiếu, không dùng trong code.
Fallback của D2 (eval trên 18 held-out scene) **không cần dùng**.

Ba bug phương pháp đã trả giá, ghi ở doc §5 để không lặp lại: (a) `object_direction` không cùng ngữ
nghĩa giữa hai chiến dịch ⇒ phải quyết định chiều bằng **hình học**; (b) ibeo đổi nhãn phân loại theo
tốc độ (`Car` ↔ `Truck`) ⇒ không dùng nhãn để chọn track; (c) track rác 4–6 mẫu của ibeo ⇒ chọn track
**nhiều mẫu nhất**, nếu không số cụm bị đẩy lên ~1,4×.

## Consequences

**Được:**

- Kết luận có thể đứng trước reviewer: n = 36, CI half-width 15,7 %, và **không** scene nào dùng để
  chọn tham số lại được dùng để chấm.
- Train từ 16 scene/1 124 frame lên **92 scene/~7 180 frame (6,4×)** mà không cần dataset mới.
- Không phụ thuộc vào một lần bốc xấu: test hiện tại có spray bằng **0,79×** trung bình 36 scene và
  65 % frame nằm ở tốc độ ngoại suy.
- Criterion đo được **độ lớn** của tác dụng, không chỉ "có/không".

**Mất / phải khai:**

- Train gấp **3 lần** số run (3 fold) ⇒ ngân sách GPU ~10–27 h, phải dùng detector nhẹ
  (`pointpillars.yaml` có sẵn + crop `[0,64]×[−16,16] m`) làm pilot.
- Pseudo scene là `itr_after_water` 2–6 trong khi eval là 1; lượng spray khác 1,2–5,4× tuỳ tốc độ.
  Đo trên input train (đã bỏ `label == 2`) cho thấy khác **< 1,1 %** số điểm `[ĐO]` — nhưng vẫn
  phải khai vì nó ảnh hưởng cách viết claim, và **cấm** trộn itr nếu có arm train giữ spray.
- Pseudo-box **không** dùng được để đo yaw/độ cong: 120 km/h (cua) chỉ 88,8 % frame đạt 3D IoU ≥ 0,7.
- Không so số tuyệt đối với nhánh `main` hay Model 0 cũ; chỉ đọc delta ghép cặp.

## Điều gì sẽ khiến mở lại ADR này

- **P2**: kết quả P1 dương nhưng muốn kiểm generalization ngoài domain → train trên STF
  (`.scratch/roadspray-cal/spec.md` Phụ lục A). Khi đó D1 vẫn giữ, chỉ đổi tập train.
- Bộ test 1.463 frame của Paper A (G-Class/CLA/Smart) được công bố → thay SSPP làm test, mở lại D1.
- Generator được chứng minh không thể khớp spray thật (chốt chặn B hoặc C thất bại) → câu hỏi
  nghiên cứu phải đổi, không chỉ đổi protocol.
- Box 3D được công bố cho cả 207 scene → bỏ D4, dùng human box toàn bộ.
- `Golf_static` lấy được → đo nốt dòng Golf và đưa bảng static vào `_CLUSTER_VISIBLE_BY_SPEED`.
- Bảng static lệch bảng per-fold > 1,5× sau khi có Golf → kiểm lại phương pháp đo.

## Liên quan

- ADR-0005: giữ nguyên quyết định domain detection = SSPP; ADR này sửa cách **chia** và cách **chấm**.
- `docs/PROJECT.md` §5: bảng kết quả đã cập nhật theo D3.
- Kế hoạch thi công: `.scratch/roadspray-cal/plan.md`.
