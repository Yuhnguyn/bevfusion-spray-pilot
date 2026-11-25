# A5 — A3-V với miền hợp lệ "Cách A" (2026-11-19, **bản v2 sau khi sửa lỗi mặt cầu**)

> ⚠️ **SỐ NÀY KHÔNG CÒN LÀ SỐ HIỆN HÀNH** (từ QĐ14 + QĐ15, 2026-11-25).
> Bảng dưới đo trên code trước QĐ14. Đo lại trên `HEAD 5e4da9b` (cùng script, cùng
> tập B, cùng seed) cho tỉ lệ thấp hơn −2 % … −35,4 %, đảo 2 ô từ ĐẠT sang TRƯỢT.
> Nguyên nhân chính là **QĐ14** (P_det0 thành hằng số theo cụm ⇒ tổng det giảm), không
> phải QĐ15. Thước near-field `R p05` và `x min` **không đổi** — tác dụng của miền giữ nguyên.
> Số hiện hành: `docs/measurements/a5-domain-a3v-post-qd15.md`.

Thực hiện theo **ADR-0006 §5.7** (pre-register commit `ecfdb23`). Script:
`.scratch/paper-faithful/a5_a3v_domain.py`. Số thô: `.scratch/tmp/a5_domain_v2.json`.

> **Đính chính so với bản v1 (`83eaee9`):** v1 báo `det < 3 m = 0` ở cả 6 ô. **Sai.** Hai lỗi
> cùng lúc, cả hai ở phía **thước đo của tôi**, không phải ở generator:
>
> 1. **Lọc theo tâm cụm thay vì mặt cầu.** Tâm ở 3 m với bán kính 2 m thì mặt cầu đã ở 1 m.
>    Đo 40 frame (α = 0): **7,3 %** cụm (136/1864) có mặt cầu dưới 2,5 m lọt qua bộ lọc, và **3**
>    cụm có mặt cầu **xuyên qua** cảm biến. Đã sửa `select_alive` lọc theo `‖pos‖ − radius`
>    (commit `a35edd6`), thêm 2 test, đã chứng minh test đỏ khi revert logic.
> 2. **In `median` của `det<3m` thay vì mean/max.** Median bằng 0 che mất các frame có det gần
>    (đo được: median 0 nhưng **max 127** trong một frame). Đúng loại lỗi "đếm bằng median" mà
>    skill `spray-pilot-ops` bẫy 8 đã ghi. Đã in thêm `mean / max / số frame`.

---

## 1. Kết quả `[ĐO]` — bản v2

Tập **B** = 72 scene không human box, 30 frame cách đều/scene, cùng seed `20261119`, paired.
Cấu hình: `diffusion_alpha = 0`, `‖pos‖ − radius ≥ 2,5 m`, `‖pos‖ ≤ 50 m`,
`wfh ~ 0,1 + Exp(mean 1,0)` clip `[0,1; 1,2] mm` cố định theo scene.

| lớp | band | scene | frame | thật/f | sinh/f | **median sinh/thật [CI95]** | R p05/p50/p95 (m) | `<3m` mean | `<3m` max | frame có `<3m` | x p01 | x min |
|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|
| Crafter | 50–70 | 12 | 360 | 122,3 | 107,5 | **1,02 [0,85; 1,26]** | 16,4 / 18,7 / 19,7 | 0,1 | 18 | 6/360 | +14,9 | −21,0 |
| Golf | 50–70 | 12 | 360 | 119,7 | 41,7 | **0,34 [0,20; 0,78]** | 18,7 / 19,5 / 20,0 | 0,1 | 12 | 6/360 | +18,4 | −21,7 |
| Crafter | 80–110 | 16 | 480 | 812,4 | 212,7 | **0,25 [0,20; 0,36]** | 4,5 / 10,0 / 18,2 | 3,1 | **127** | 97/480 | −9,2 | −49,2 |
| Golf | 80–110 | 16 | 480 | 398,0 | 223,4 | **0,50 [0,36; 0,71]** | 5,3 / 11,4 / 18,0 | 2,0 | 113 | 60/480 | −6,7 | −49,6 |
| Crafter | 120–130 | 8 | 240 | 605,2 | 279,2 | **0,85 [0,45; 1,31]** | 4,6 / 8,3 / 18,3 | 3,2 | 115 | 39/240 | −20,4 | −49,9 |
| Golf | 120–130 | 8 | 240 | 464,8 | 274,8 | **0,65 [0,30; 0,98]** | 5,1 / 10,1 / 17,5 | 2,4 | 74 | 37/240 | −12,0 | −49,8 |

## 2. So với production (A3-V cũ, không miền)

| ô | production | Cách A v2 | giảm |
|---|---:|---:|---:|
| Crafter 50–70 | 1,98× | **1,02×** | 1,9 |
| Golf 50–70 | 0,86× | **0,34×** | 2,5 |
| Crafter 80–110 | 2,73× | **0,25×** | 10,9 |
| Golf 80–110 | 4,63× | **0,50×** | 9,3 |
| Crafter 120–130 | **16,92×** | **0,85×** | **19,9** |
| Golf 120–130 | 8,02× | **0,65×** | 12,3 |

## 3. Điều đã đúng — và điều KHÔNG đúng

**Đúng:**

1. **Tỉ lệ giảm 1,9–19,9 lần.** Ca tệ nhất (Crafter 120–130, 16,92×) về **0,85×**.
2. **`x min` = −49,2…−49,9 m**, không còn −137/−294 m. Sát biên thật (thật: −49,6 m).
3. **`R p50` của 50–70 km/h** = 18,7–19,5 m — khớp thang của vùng đuôi xe (cụm ngay sau đuôi xe ở
   20–30 m ⇒ `R ≈ 18–20 m` là hợp lý).
4. **`R p05` ở 80–130 km/h = 4,5–5,3 m**, thay vì 1,42–1,58 m của production.

**KHÔNG đúng — phải rút lại claim "near-field về 0":**

5. **`det < 3 m` KHÔNG bằng 0.** Mean 0,1–3,2 det/frame, **max tới 127** trong một frame, xuất hiện
   ở 6–97 trong mỗi 240–480 frame. Lý do: lọc `‖pos‖ − radius ≥ 2,5 m` chặn **tâm và mặt cầu**,
   nhưng `raycast_frame` sinh detection dọc theo **tia**, không theo mặt cầu — một tia đi qua phần
   rìa của quả cầu có thể cho điểm rất gần gốc. Đây là **hệ quả của mô hình quả cầu**, đúng loại
   paper §V tự cảnh báo. Muốn về đúng 0 phải cắt ở tầng **detection** (sau raycast) — **chưa làm**,
   và nếu làm phải pre-register riêng.
6. **4/6 ô vẫn thưa hơn thật**: 0,25–0,65×. Chỉ 2/6 nằm trong `[0,5; 2,0]` (Crafter 50–70 = 1,02;
   Golf 80–110 = 0,50 sát biên). Nguyên nhân: nguồn hiệu chuẩn `*_static` có tổng spray cao hơn
   following (`trail90` 44 m vs ~20 m) — limitation của **nguồn hiệu chuẩn**. **Không** bù bằng
   `spawn_scale` (§5.7 cấm).

## 4. Điều kiện còn thiếu để kết luận dứt khoát

`R p50` của hai vế chưa cùng thang: bảng trên tính `R` của **detection** (sinh), còn "thật" chỉ có
tổng điểm/frame. Muốn so phân bố cự ly đúng phải chạy `measure_cdf_over_range.py` (thước KS của
Paper A Fig. 12) cho cấu hình Cách A. **Chưa làm** — việc của A5-b.

## 5. Hệ quả cho cổng C

Cổng C đo **recall**, không đo số điểm. Hai điều kiện để nó còn có nghĩa:

- plume **không còn** là "tấm màn dày sát cảm biến" — **đạt** (`R p05` 4,5–5,3 m so với 1,42–1,58;
  ca tệ nhất về 0,85×);
- plume **không quá thưa đến mức vô hình** — hiện 0,25–0,65× ở 4/6 ô, tức một phần ba đến hai phần
  ba lượng spray thật. Vẫn nhìn thấy, nhưng **phải khai** khi đọc kết quả.

Nếu `Δrecall(plume−clean)` về ngang `Δrecall(real−clean) = −0,049` thì kết luận là **cơ chế
near-field** mới là nguyên nhân, độ thưa không phá kết luận đó. Nếu vẫn `< −0,15` thì §5.7 mục 3
buộc **DỪNG**.

## 6. Kết luận 1 câu

Cách A **cắt được phần lớn bệnh** (tỉ lệ giảm tới 19,9 lần, `x` không còn trôi tới −294 m, `R p05`
về 4,5–5,3 m), nhưng **không** làm `det < 3 m` về 0 — cái đó cần cắt ở tầng detection và **chưa**
làm; và 4/6 ô giờ thưa hơn thật do nguồn hiệu chuẩn.
