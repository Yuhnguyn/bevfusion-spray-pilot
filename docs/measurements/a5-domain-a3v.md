# A5 — A3-V với miền hợp lệ "Cách A" (2026-11-19)

Thực hiện theo **ADR-0006 §5.7** (pre-register commit `ecfdb23`). Script:
`.scratch/paper-faithful/a5_a3v_domain.py`. Số thô: `.scratch/tmp/a5_domain_wfh.json`.

**Cấu hình đo:** `diffusion_alpha = 0`, `2,5 ≤ ‖pos‖ ≤ 50 m`, `wfh ~ 0,1 + Exp(mean 1,0)` clip
`[0,1; 1,2] mm` **cố định theo scene**. Tập **B** = 72 scene không có human box (không bao giờ
nằm trong eval). 30 frame cách đều/scene, cùng seed `20261119`, paired.

---

## 1. Kết quả `[ĐO]`

| lớp | band | scene | frame | thật/f | sinh/f | **median sinh/thật [CI95]** | R p05/p50/p95 (m) | `< 3 m` | x p01 | x min |
|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| Crafter | 50–70 | 12 | 360 | 122,3 | 110,1 | **1,04 [0,86; 1,34]** | 16,4 / 18,7 / 19,7 | **0** | +14,9 | −21,0 |
| Golf | 50–70 | 12 | 360 | 119,7 | 42,9 | **0,35 [0,20; 0,78]** | 18,7 / 19,5 / 20,0 | **0** | +18,4 | −21,7 |
| Crafter | 80–110 | 16 | 480 | 812,4 | 254,0 | **0,31 [0,21; 0,42]** | 3,6 / 9,2 / 18,1 | **0** | −8,9 | −49,6 |
| Golf | 80–110 | 16 | 480 | 398,0 | 251,1 | **0,57 [0,39; 0,78]** | 4,6 / 10,6 / 17,9 | **0** | −6,5 | −49,5 |
| Crafter | 120–130 | 8 | 240 | 605,2 | 361,6 | **0,99 [0,55; 1,49]** | 3,9 / 7,4 / 17,7 | **0** | −18,8 | −49,9 |
| Golf | 120–130 | 8 | 240 | 464,8 | 323,6 | **0,72 [0,34; 1,14]** | 4,4 / 9,2 / 17,3 | **0** | −11,8 | −49,8 |

## 2. So với production (A3-V cũ, không miền)

| ô | production | Cách A | giảm |
|---|---:|---:|---:|
| Crafter 50–70 | 1,98× | **1,04×** | 1,9 lần |
| Golf 50–70 | 0,86× | **0,35×** | 2,5 lần |
| Crafter 80–110 | 2,73× | **0,31×** | 8,9 lần |
| Golf 80–110 | 4,63× | **0,57×** | 8,1 lần |
| Crafter 120–130 | **16,92×** | **0,99×** | **17,1 lần** |
| Golf 120–130 | 8,02× | **0,72×** | 11,1 lần |

## 3. Đọc kết quả — điều gì đã đúng, điều gì phải khai

**Đã đúng (ba điều kiện cứng):**

1. **`det < 3 m` = 0 ở cả 6 ô.** Production có 946–1.272 det/frame ở `< 3 m`. Near-field đã bị
   chặn hoàn toàn — đúng mục tiêu chính của Cách A.
2. **`x min` = −49,5…−49,9 m.** Không còn cụm nào trôi tới `−137` / `−294 m` như production. Sát
   biên thật (`x` min = −49,6 m trên 137.821 điểm spray thật).
3. **Tỉ lệ: 5/6 ô giảm 1,9–17,1 lần.** Ca tệ nhất (Crafter 120–130, 16,92×) về **0,99×**.

**Phải khai (không được giấu):**

4. **4/6 ô giờ THƯA hơn thật: 0,31–0,72×.** Chỉ 2 ô nằm trong dải `[0,5; 2,0]` (Crafter 50–70
   = 1,04; Golf 80–110 = 0,57 là sát biên dưới; Crafter 120–130 = 0,99). Theo ngưỡng A3-V
   pre-registered, Cách A **vẫn không đạt** ở 4 ô — nhưng **lệch đổi dấu**: trước là đậm quá, giờ
   là thưa quá. Đó là tiến bộ về **cơ chế**, không phải về **khớp số**.
5. **`R p50` của sinh lệch có hệ thống về phía xa.** 50–70: sinh 18,7–19,5 m so với thật (không in
   được ở đây vì R p50 thật tính trên toàn điểm, xem §4). Ở 80–130: sinh 7,4–10,6 m trong khi
   spray thật có `r` p50 ≈ 14,2 m (toàn tập) và 5,2–8,8 m (per-scene, đo ở lượt trước). Hai thang
   này **chưa so trực tiếp được** — xem §4.
6. **Nguyên nhân 4/6 ô thưa:** tổng lượng spray của RoadSpray `*_static` (dùng hiệu chuẩn) lớn hơn
   following thật (`trail90` static 44 m vs following ~20 m). Đây là **limitation của nguồn hiệu
   chuẩn**, đã ghi ở `plan.md` §3 Cách A. **Không** bù bằng `spawn_scale` (ADR §5.7 cấm).

## 4. Điều kiện còn thiếu để kết luận dứt khoát

`R p50` của hai vế chưa cùng thang: bảng trên tính `R` của **detection** (sinh) nhưng "thật" chỉ
có tổng điểm/frame. Muốn so phân bố cự ly đúng, phải chạy `measure_cdf_over_range.py` (thước KS của
Paper A Fig. 12) cho cấu hình Cách A. **Chưa làm** — đây là việc của bước A5-b.

## 5. Kết luận 1 câu

Cách A **loại bỏ được near-field và "tấm màn trước cảm biến"** (`det < 3 m` = 0, `x min` ≈ −50 m,
ca tệ nhất từ 16,92× về 0,99×), nhưng **không làm plume khớp mật độ**: 4/6 ô giờ thưa hơn thật do
nguồn hiệu chuẩn (static) có tổng lượng spray cao hơn following. Bước tiếp theo phải là **cổng C**
(A7) để biết recall đã về ngang spray thật chưa — đó mới là thứ quyết định augmentation có hợp lệ.
