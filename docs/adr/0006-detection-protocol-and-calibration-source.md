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

## Liên quan

- ADR-0005: giữ nguyên quyết định domain detection = SSPP; ADR này sửa cách **chia** và cách **chấm**.
- `docs/PROJECT.md` §5: bảng kết quả đã cập nhật theo D3.
- Kế hoạch thi công: `.scratch/roadspray-cal/plan.md`.
