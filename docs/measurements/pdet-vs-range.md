# `P_det` theo cự ly trên RoadSpray `*_static` — Eq. 7 đo ở nhiều khoảng cách (2026-11-19)

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S5.
> Phần còn đúng: Kết quả b = +0,222 và kết luận near-field không cứu được vẫn đúng.

Người đo: subagent đo lường (R3). Script: `scripts/measure_pdet_vs_range.py`.
Dữ liệu thô: `.scratch/tmp/pdet_vs_range.jsonl` (1 656 cụm) · summary: `.scratch/tmp/pdet_vs_range_summary.json`.
Nguồn: `data/roadspray/{Crafter,Golf}_static.zip` + `meta_data_measurement.xlsx`.
Nhãn: `[ĐO]` · `[SUY RA]` (đại số trên số đo) · `[CHỌN]` (quyết định phương pháp, có lý do).

## 0. TL;DR — 4 câu trả lời

1. **`P_det_obs(R)` có tăng, nhưng luật tăng phụ thuộc định nghĩa `n_max`** — và **không có định nghĩa nào cho b = 2**:
   `b = −0,17` (CI95 `[−0,38; +0,01]`) nếu `n_max` = lưới tia **thật** + `r` của từng cụm;
   `b = +0,34` (CI95 `[0,21; 0,52]`) nếu `r` **cố định 0,31 m** (như generator);
   `b = +1,06` (CI95 `[0,75; 1,27]`) nếu dùng **đúng công thức paper** `n_max = Ω/ω`.
   Giả thuyết quang học mỏng (`b ≈ 2`) **không** được xác nhận trọn vẹn; phần thiếu được `r(R)` hấp thụ (xem §8.1).
2. **`n(R)` gần như phẳng**: `b_n = −0,11` (CI95 `[−0,17; −0,02]`), median `n` = **6 / 5 / 7 / 5 / 4** ở 5–10 / 10–15 / 15–20 / 20–25 / 25–30 m. Cự ly tăng 3,2× mà `n` chỉ giảm 1,5× ⇒ **xác nhận tiền đề "đám hạt mỏng"** ở mức cụm (không phải `n ∝ R⁻²`).
3. **Ở 25 m, `P_det` đo được = 0,181** (bin 20–25 m; fit tại 25 m = 0,193; công thức paper = 0,169–0,204) so với **0,10** của paper ⇒ **lệch 1,7–2×, cùng bậc** ⇒ phép đo đúng phương pháp, sai số chuẩn hoá ~2× phải khai.
4. **Điểm/cụm ở 2 m so với 25 m** (bảng đầy đủ ở §7.4): **157×** với mô hình paper (`P_det` hằng); **240×** với `b` đo được kiểu paper-faithful; **66×** với `r` cố định; **1,3×** nếu `P_det ∝ R^1,89`. Muốn hết bùng nổ phải có `b ≈ 2`, **hoặc** cho `r ∝ R` (đo được `r ∝ R^0,42`).

**Đã áp dụng vào generator (§11, 2026-11-19):** `P_det(R) = P_det0·(R/25 m)^b` với `b` đo
lại bằng chính `load_beam_table()` ⇒ **b = +0,22** (CI95 `[−0,14; +0,55]`). Kết quả: A3 vẫn
**KHÔNG ĐẠT 0/3** (thay đổi ≤ +5 % ở (a)); A3-V **0/6 ô** tập B (median giảm 1,14–1,34×, vẫn
2,0–13,4× quá đậm). ⇒ **P_det(R) không phải chỗ sửa** near-field; xem §11.5.

Ba phát hiện phương pháp (quan trọng ngang 4 câu trả lời):

- **8.1** `r ∝ R^0,42` (CI95 `[0,30; 0,58]`): bán kính cụm **vật lý** lớn dần theo cự ly vì cụm được gom bằng ngưỡng **góc** (0,7°). Đây là chỗ phụ thuộc `R` bị "ẩn" khỏi `P_det`.
- **8.2** `n_max` của cảm biến thật **không** ∝ `R⁻²`: với `r = 0,31 m` cố định nó chỉ giảm như `R⁻0,40` (bin median), vì ring VLP-32C ở elevation thấp (cụm gần: −8,8°) thưa **1,3–4,3°** còn gần 0° (cụm xa: −3,4°) dày **0,33°**. Cụm gần vừa có góc khối lớn hơn vừa rơi vào vùng tia thưa ⇒ hai hiệu ứng gần triệt tiêu.
- **8.3** Bảng tia **production** (`load_beam_table()`, FOV −4,06…+5,88°) cho `n_max = 0` với **40,4 %** cụm thật (669/1 656) vì plume ở cự ly gần nằm dưới −4,06°. RoadSpray dùng VLP-32C trải **−25…+15°** (đo trong bag). Hai bảng tia này **không** phải cùng một cảm biến.

## 1. Câu hỏi

Paper (arXiv 2212.08558, Eq. 7) định nghĩa `P_det = n / n_max(r_cl, p_cl)` và **chỉ đo ở 25 m**
(Fig. 7: µ = −2,3; σ = 1,09 ⇒ median e^−2,3 = 0,100). Repo dùng `P_det` như hằng số, nên
`n = n_max·P_det ∝ (r/R)²` ⇒ cụm càng gần càng nhiều điểm. Đo `P_det(R)` trên dữ liệu thật để biết
mô hình hằng số sai ở dải cự ly ≠ 25 m theo luật nào.

## 2. Dữ liệu & phương pháp `[CHỌN]`

| lớp | bag 50 km/h | bag 100 km/h | bag 130 km/h | frame | cụm |
|---|---:|---:|---:|---:|---:|
| Crafter | 2 | 1 | 2 | 213 | 642 |
| Golf | 2 | 1 | 2 | 253 | 1 014 |
| **tổng** | **4** | **2** | **4** | **466** | **1 656** |

10 bag (5/lớp; 4 bag bị loại vì xe **đang tiến lại** ⇒ plume bị thân xe che), 466 frame lidar có
track hợp lệ, **114 frame có cụm** (plume chỉ hiện khi xe còn gần: cự ly xe 12–197 m, `car_range`).
Cự ly cụm đo được: **R = 4,05 – 29,96 m** (median 14,5). Baseline máy: ~7 s/bag.

Vùng đo = mặt đuôi xe → sau **0–25 m**, ngang **±5 m**, cao **0,15–1,5 m** trên mặt phẳng mặt đường
(hộp `define_spray_volumes()` của reference: 3,4 × 1,5 × L; nới ngang để không cắt plume).
Cắt **lát sâu 1,0 m** rồi DBSCAN góc (`eps = 0,7°`, `minPts = 3`) trong từng lát.

Bốn quyết định phải khai, kèm số:

1. **Trần 1,5 m** (= chiều cao hộp spray của reference implementation). Lý do: phần "residual"
   cao 1,6–2,1 m ngay sau đuôi xe là **mặt sau thân xe** — `[ĐO]` một cụm 1 159 điểm ở 5 m có độ
   dày theo chiều sâu **sd = 0,04 m** ở cao 1,85 m ⇒ mặt phẳng, không phải spray (cụm này chỉ lọt
   ra ngoài hộp thân xe vì track đặt mặt đuôi danh nghĩa lệch ~0,5 m). Trần 1,5 m cắt **6 018**
   điểm (**28,7 %** so với 20 954 điểm được giữ). **Nhưng trần này KHÔNG phải chỗ tựa của kết luận:**
   chạy lại với `--height-max 3.0` chỉ thêm 174 cụm (+10,5 %) và `b` đổi từ −0,17 sang −0,09
   (§6) ⇒ kết luận bền với lựa chọn này.
2. **Không ngoại suy quỹ đạo.** `roadspray_static_depth_profile.py` cho phép lệch ±0,3 s; ở 50 km/h
   (±4 m) frame đầu bag bị gán sai vị trí xe và "cụm sau đuôi" hoá ra là thân xe
   (`[ĐO]` frame 11 bag `08-56-39`: track nói 12,5 m nhưng mặt phẳng thân xe ở 5,2 m).
   Ở đây **chỉ dùng frame nằm trong khoảng thời gian của track**.
3. **Track chọn theo tốc độ metadata** + chỉ bag xe **rời xa** (tái dùng `car_track()`).
4. **`n_max` = 4 định nghĩa, tính cho cùng một cụm.** Cả 4 đều là "số tia cắt quả cầu `(r, R)`":
   - `n_max_obs` (**chuẩn chính**): lưới tia **đo từ chính bag** — elevation trung vị của từng ring
     thật (29–32 ring, −25…+15°) × 1 825 cột azimuth bước 0,197307° (pha đo được, −0,10…+0,05°).
     Đây là chùm tia **đã tạo ra** `n` detection ⇒ mẫu số đúng nghĩa paper.
   - `n_max_prod`: `load_beam_table()` 30 ring × 1 825 az (−4,06…+5,88°) — thứ generator đang dùng.
   - `n_max_paper`: công thức liên tục của paper `Ω/ω` (chính là `beams_intersecting_sphere()`);
     dùng `r` của cụm ⇒ `n_max ∝ r²/R²` đúng như paper giả định.
   - `n_max_sil`: số ô tia trong hull góc `(az, el)` — **không dùng được** ở quy mô này (§9.2).
   Đếm tia = "khoảng cách từ đường thẳng chứa tia tới tâm cầu ≤ r" + tâm cầu ở phía trước cảm biến;
   cảm biến nằm trong cầu ⇒ mọi tia.

Kiểm tra hợp lệ: `n_max_obs = 0` xảy ra **0/1 656** cụm; `P_det > 1` ở **50/1 656 = 3,0 %**
(do lưới rời rạc + jitter azimuth, không phải lỗi hệ thống).

## 3. Bảng chính `[ĐO]`

| bin cự ly (m) | cụm | bag | median `n` | IQR `n` | median `n_max` | median `r` (m) | median `P_det` | IQR `P_det` | median elevation |
|---|---:|---:|---:|---|---:|---:|---|---|---:|
| 5–10 | 386 | 9 | 6 | 4–13 | 26 | 0,25 | **0,267** | 0,129–0,500 | −8,84° |
| 10–15 | 474 | 9 | 5 | 4–11 | 30 | 0,27 | **0,205** | 0,117–0,465 | −5,82° |
| 15–20 | 423 | 10 | 7 | 4–14 | 41 | 0,35 | **0,182** | 0,111–0,324 | −3,89° |
| 20–25 | 270 | 10 | 5 | 4–10 | 38 | 0,37 | **0,181** | 0,114–0,300 | −3,39° |
| 25–30 | 82 | 9 | 4 | 3–7 | 24,5 | 0,32 | **0,217** | 0,141–0,364 | −3,00° |
| 30–40 | **0** | 0 | — | — | — | — | — | — | — |
| 40–55 | **0** | 0 | — | — | — | — | — | — | — |

`n` toàn bộ: min 3 / median 6 / mean 10,4 / max 137. **Không có cụm nào ở R > 30 m**: plume không
còn tạo residual ở cự ly đó (cùng lý do khiến paper đo ở 25 m). Hai bin cuối vì vậy **không đo được**,
không nội suy.

## 4. Hồi quy `log y = a + b·log R` (bootstrap theo **bag**, 2 000 lần)

| biến | `n` cụm | `b` | CI95 | bag-FE `b` | CI95 | R² |
|---|---:|---:|---|---:|---|---:|
| `P_det` (n_max đo được, `r` từng cụm) | 1 656 | **−0,166** | `[−0,377; +0,005]` | −0,254 | `[−0,421; −0,084]` | 0,006 |
| `n` (số điểm/cụm) | 1 656 | **−0,112** | `[−0,174; −0,025]` | −0,109 | `[−0,166; −0,012]` | 0,004 |
| `r` (bán kính cụm) | 1 656 | **+0,415** | `[+0,298; +0,583]` | +0,467 | `[+0,343; +0,598]` | 0,063 |
| `P_eff` (`n_max` tại **`r` = 0,31 m cố định**) | 1 656 | **+0,344** | `[+0,205; +0,521]` | +0,343 | `[+0,190; +0,554]` | 0,031 |
| `P` theo **công thức paper** `Ω/ω` | 1 656 | **+1,059** | `[+0,753; +1,274]` | — | — | 0,180 |
| bin-median (5 bin) `P_det` / `n` | — | −0,226 / −0,242 | — | — | — | — |

`[SUY RA]` Ba hệ thức nối các số trên (dùng để kiểm tra chéo, không phải giả định):

1. `b_paper = b_n + 2 − 2·b_r = −0,11 + 2 − 0,83 = +1,06` — **khớp** số đo `+1,059`.
2. `b_eff = b_n − slope(n_max tại r cố định)`. Đo riêng: `n_max` (r = 0,31 m) giảm như
   `R^−0,46` (CI95 `[−0,60; −0,34]`) ⇒ `−0,11 + 0,46 = +0,34` — **khớp** số đo `+0,344`.
3. Nếu `n_max ∝ R⁻²` (**bảng tia đều** của generator) thì `P_det` phải là `b_n + 2 = +1,89`.
   Chênh lệch 1,55 giữa `+1,89` và `+0,34` **chính là** hiệu ứng §8.2: lưới tia thật không giảm như
   `R⁻²`. Nói cách khác: **P_det chỉ cần ∝ R^1,89 nếu n_max tính bằng bảng tia đều**; với lưới tia
   thật thì chỉ cần `∝ R^0,34` — nhưng đổi lại, chính lưới tia thật cũng làm `n_max` bớt bùng nổ.

## 5. Theo lớp và tốc độ `[ĐO]`

| ô | bag | cụm | median R | median `n` | median `n_max` | median `P_det` | `b` |
|---|---:|---:|---:|---:|---:|---|---:|
| Crafter 50 | 2 | 234 | 15,2 | 5 | 16 | 0,300 | −0,507 |
| Crafter 100 | 1 | 253 | 16,4 | 6 | 41 | 0,190 | −0,384 |
| Crafter 130 | 2 | 155 | 17,2 | 6 | 29 | 0,189 | +0,002 |
| Golf 50 | 2 | 239 | 14,3 | 6 | 36 | 0,217 | −0,180 |
| Golf 100 | 1 | 364 | 11,1 | 6 | 37 | 0,192 | −0,011 |
| Golf 130 | 2 | 411 | 14,1 | 6 | 38 | 0,183 | −0,386 |

Không ô nào có `b` dương đáng kể ⇒ xu hướng "phẳng hoặc giảm nhẹ" **không** do một ô nào chi phối.
Hai lớp cho cùng median `P_det` 0,18–0,30 ⇒ không có khác biệt lớp (paper cũng nói tham số giữ
trong một lớp xe).

## 6. Độ bền của `b` `[ĐO]`

| biến thể | cụm | `b` | CI95 |
|---|---:|---:|---|
| chuẩn (`n_max` đo được, `r` từng cụm) | 1 656 | −0,166 | `[−0,380; +0,006]` |
| chỉ cụm `n ≥ 10` | 495 | −0,315 | `[−0,523; −0,188]` |
| chỉ cụm `n ≥ 20` | 192 | −0,302 | `[−0,583; +0,165]` |
| chỉ spray tươi (depth ≤ 6 m) | 490 | −0,288 | `[−0,505; +0,128]` |
| chỉ depth > 6 m | 1 166 | −0,195 | `[−0,483; +0,027]` |
| `n_max` = hull góc | 423 | −0,191 | `[−0,368; +0,068]` |
| `n_max` = bảng production | 987 | **+0,106** | `[−0,071; +0,231]` |
| `n_max` = công thức paper `Ω/ω` | 1 656 | **+1,059** | `[+0,753; +1,274]` |
| **lát cắt 2,0 m** (thay 1,0 m) — `b` | 1 406 | **−0,281** | `[−0,458; −0,177]` |
| **trần 3,0 m** (thay 1,5 m) — `b` | 1 830 | **−0,086** | `[−0,251; +0,026]` |
| lát 2,0 m — `b` của `P_eff` (`r` cố định) | 1 406 | +0,383 | `[+0,231; +0,589]` |
| trần 3,0 m — `b` của `P_eff` (`r` cố định) | 1 830 | +0,576 | `[+0,394; +0,857]` |

Chiều của `b` **đổi dấu** giữa các định nghĩa `n_max` ⇒ câu "paper đúng hay sai" **không** trả lời
được bằng `P_det` một mình; phải nói rõ `n_max` nào (xem §7.1). Đổi vùng đo (lát 2,0 m; trần 3,0 m)
**không** đổi dấu hay bậc: `b` ∈ `[−0,31; −0,09]`, `b_eff` ∈ `[+0,34; +0,58]` ⇒ kết luận bền.
Mức tuyệt đối của `P_det` thì **đổi theo quy mô cụm** (lát 2,0 m cho `P` ở 20–25 m = 0,111 thay vì
0,181) — đúng như caveat §9.1.

## 7. Trả lời 4 câu hỏi

### 7.1 `P_det_obs(R)` có tăng theo `R` không? `b` = bao nhiêu?

**Có, nhưng ít hơn `R²` rất nhiều, và luật phụ thuộc mẫu số:**

| định nghĩa `n_max` | `b` | CI95 | diễn giải |
|---|---:|---|---|
| lưới tia thật + `r` từng cụm (**chuẩn**) | **−0,17** | `[−0,38; +0,01]` | phẳng, hơi giảm |
| lưới tia thật + `r` = 0,31 m cố định | **+0,34** | `[+0,21; +0,52]` | tăng yếu |
| công thức paper `Ω/ω` + `r` từng cụm | **+1,06** | `[+0,75; +1,27]` | tăng, bằng nửa `R²` |
| (giả thuyết quang học mỏng) | 2 | — | **không** đạt |

`[CHỌN]` Chuẩn = lưới tia thật + `r` từng cụm, vì đó là mẫu số **đúng cảm biến đã tạo ra `n`**.
Nhưng khi báo cáo phải kèm hai số kia — chênh lệch giữa chúng chính là nội dung khoa học (§8.1–8.2).

### 7.2 `n(R)` có phụ thuộc `R` không?

**Gần như không.** `b_n = −0,112` (CI95 `[−0,174; −0,025]`, bag-FE −0,109); bin median 6 / 5 / 7 / 5 / 4
⇒ trên 5–30 m (3,2×) số điểm mỗi cụm chỉ giảm ~1,5×, trong khi `n_max` của **một quả cầu bán kính
cố định** sẽ giảm ~8×. **Xác nhận tiền đề quang học mỏng ở mức cụm**: số detection/cụm không co giãn
theo `R⁻²`.

### 7.3 Ở 25 m, `P_det` có xấp xỉ 0,10 không?

| cách đọc | giá trị ở 25 m |
|---|---:|
| bin 20–25 m, `n_max` đo được | **0,181** |
| fit `exp(a + b·ln 25)` | **0,193** |
| bin 20–25 m, công thức paper `Ω/ω` | **0,169** |
| bin 25–30 m, công thức paper `Ω/ω` | **0,204** |
| paper (median lognormal µ=−2,3) | **0,100** |

**Kết luận: khớp trong 1,1–2,0×.** Đây là kiểm chứng chéo quan trọng — phép đo cho **cùng bậc** với
paper, không lệch 10×. Đáng chú ý: với lát cắt **2,0 m** (cụm to hơn) thì bin 20–25 m cho
**0,111** — gần như trùng 0,10 của paper; còn với lát 1,0 m thì 0,181. Chênh lệch này đúng là
hiệu ứng "P_det phụ thuộc quy mô cụm" (§9.1), không phải sai số đo. Phần lệch 2× có nguồn gốc rõ: (i) `r` trung vị ở 20–30 m = **0,36 m** so với
0,31 m của paper; (ii) paper fit lognormal trên **phân bố giữa các cụm**, còn đây là median của phân
bố đó đo trên một mẫu khác (2 lớp xe, 3 tốc độ); (iii) `P_det` phụ thuộc **quy mô cụm** (§9.1) nên
không có một con số duy nhất. Vì vậy 0,18 được coi là **xác nhận phương pháp**, không phải mâu thuẫn.

### 7.4 Nếu thay `P_det` hằng bằng `P_det(R)` đo được thì số điểm/cụm ở 2 m và 25 m chênh bao nhiêu?

`n = P_det(R) · n_max(R)` và `n_max(r, R) ∝ r²/R²` (kiểm tra số: slope log-log của `Ω/ω` trên 5–40 m
= **−2,001**). Với `r` = 0,36 m (giá trị ở 20–30 m): `n_max(2 m) = 5 128`, `n_max(25 m) = 33`
⇒ **tỉ lệ hình học 157×**.

| `P_det` dùng | `P(2)/P(25)` | điểm/cụm **2 m : 25 m** |
|---|---:|---:|
| hằng số 0,10 (**hiện tại**) | 1 | **157×** |
| `b = −0,17` (chuẩn, `r` từng cụm) | 1,71 | **240×** (tệ hơn) |
| `b = +0,34` (`r` cố định 0,31 m) | 0,40 | **66×** |
| `b = +1,89` (đo: `b_n + 2`) | 0,0076 | **1,3×** |
| `b = 2` (quang học mỏng) | 0,0064 | **1,0×** |

`[SUY RA]` Vì `b_n ≈ −0,11`, muốn `n(R)` phẳng thì `P_det` **phải** ∝ `R^1,89` (CI95 `[1,83; 1,98]`)
khi `r` giữ cố định — tức **gần đúng `b = 2`**. Đổi knob khác cũng tương đương: cho `r ∝ R` (đo được
`r ∝ R^0,42`) với `P_det` hằng cũng làm `n` phẳng. Hai cách sửa **không** độc lập.

Số tuyệt đối cho thấy quy mô lỗi: mô hình paper đặt **513 điểm** vào một cụm ở 2 m
(`0,10 × 5 128`), trong khi dữ liệu thật ở 5–10 m có median **6 điểm/cụm**.

## 8. Ba phát hiện phương pháp

### 8.1 `r(R)`: bán kính vật lý của cụm lớn dần theo cự ly `[ĐO]`

`r = 0,094 · R^0,415` (CI95 `[0,30; 0,58]`); median `r` = 0,25 → 0,37 m từ bin 5–10 lên 20–25 m.
Nguyên nhân: cụm được gom bằng ngưỡng **góc** `eps = 0,7°` (đúng paper) ⇒ ở 8 m cụm rộng ~0,1 m,
ở 25 m rộng ~0,3 m. Vì `n_max ∝ (r/R)²`, `r ∝ R^0,42` làm `n_max` giảm chậm hơn `R⁻²` **rất nhiều**
(`n_max_obs` bin median: 26 → 30 → 41 → 38 → 25, gần như phẳng).

**Hệ quả:** phân bố `r` mà paper đo ở 25 m (median 0,31 m) **không** dùng được như hằng số vật lý cho
mọi cự ly. Generator đang làm đúng điều đó (`RADIUS_MEDIAN_M = 0,31`, `radius0` độc lập với `R`) —
đây là một nguyên nhân độc lập với `P_det` gây bùng nổ điểm ở cự ly gần.

### 8.2 `n_max` của cảm biến thật không theo `R⁻²`, vì ring VLP-32C không đều `[ĐO]`

Với `r = 0,31 m` cố định, `n_max` đo được giảm như `R^−0,46` (CI95 `[−0,60; −0,34]`;
bin median 38 → 33,5 → 36 → 28 → 22), **không** phải `R^−2` của công thức liên tục. Lý do: cụm **gần** nằm ở elevation **−8,8°**, nơi ring
VLP-32C thưa **1,3–4,3°** (ring ở −8,99°, −7,33°, −5,99°); cụm **xa** ở **−3,4°**, nơi ring dày
**0,33–0,66°**. Hai hiệu ứng (góc khối ∝ `1/R²` vs mật độ tia tăng theo elevation) gần triệt tiêu.
`[SUY RA]` Đây là lý do `b_eff` theo lưới thật (+0,34) nhỏ hơn `b` theo công thức paper (+1,06)
rất nhiều: công thức `Ω/ω` giả định mật độ tia **đều**, nên nó gán cho cụm gần quá nhiều tia
(vùng elevation thấp thưa) và cho cụm xa quá ít.

### 8.3 Bảng tia production không phủ nổi plume ở cự ly gần `[ĐO]`

`n_max_prod = 0` với **669/1 656 = 40,4 %** cụm. `[ĐO]` Toàn bộ 1 656 cụm nằm ở elevation
**−15,65…−0,33°** (median −4,67°), còn sàn FOV của bảng production là **−4,06°**: 669 cụm đó có
elevation −15,65…−4,67° (median −7,25°) tức **hoàn toàn dưới sàn**. Nơi cả hai > 0,
tỉ lệ `n_max_prod / n_max_obs` = **0,93** (p10 0,33; p90 1,07) — tức không chỉ khác FOV mà còn khác
mật độ ring (30 ring đều 0,333° trong 9,94° so với 29–32 ring không đều trong 40°).
`[SUY RA]` Hai bảng tia **không** mô tả cùng một cảm biến: bảng production hợp với dải −4…+6° (có thể
là SSPP), còn RoadSpray là VLP-32C đầy đủ. Muốn đối chiếu generator với RoadSpray phải dùng **lưới
ring đo được**, nếu không thì 40 % cụm gần như "vô hình" với generator.

## 9. Caveat — những gì **không** đo được / không nên đọc quá

1. **`P_det` phụ thuộc quy mô cụm.** `n/n_max` là "tỉ lệ lấp đầy" của quả cầu: cụm 3–5 điểm (dense core)
   cho `P` cao, cụm lớn cho `P` thấp. Vì vậy **không** có một `P_det` duy nhất; bảng §3 là phân bố
   theo bin, và mọi so sánh phải cùng quy mô cụm. Đây là hạn chế **của định nghĩa paper**, không
   phải của phép đo.
2. **Hull góc không dùng được**: `P_sil` median ≈ 1,0–4,7 (vượt 1 ở **4/5 bin** — vô lý về mặt
   xác suất) vì cụm 3–8 điểm chỉ chiếm
   ~1 điểm/ô tia; hull suy biến thành đoạn thẳng ⇒ số ô "trong hull" ≤ `n`. Chỉ 423/1 656 cụm
   (≥ 8 điểm, ≥ 2 ring) tính được, và giá trị vẫn vô nghĩa. **Không** dùng làm chuẩn.
3. **Cự ly chỉ 4–30 m.** Bin 30–40 và 40–55 m **rỗng** — plume không tạo residual ở đó. Không ngoại
   suy ra 2 m: con số 2 m trong §7.4 là **đại số** trên luật `r²/R²`, không phải đo.
4. **`R` và elevation bị chặn (confound).** Cụm gần luôn ở elevation thấp (§8.2). Phép đo **không**
   tách được "hiệu ứng cự ly" khỏi "hiệu ứng mật độ tia theo elevation". Đây là hạn chế vật lý của
   cảm biến, không sửa được bằng thống kê — chỉ có thể khai.
5. **Kịch bản không phải following.** RoadSpray static = ego **đỗ**, xe chạy ngang qua rồi ra xa;
   generator mô phỏng ego **chạy theo** xe. Cùng hiện tượng spray, khác hình học nhìn.
6. **Không đo `P_det` của SSPP** (D2-chặt: SSPP chỉ để kiểm chứng).
7. **3 % cụm có `P_det > 1`** do lưới rời rạc/pha azimuth; giữ nguyên, không clip.

## 10. Tái lập

```bash
# đo (10 bag, ~90 s; bag tạm giải nén vào .scratch/tmp/bags rồi xoá)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
  scripts/measure_pdet_vs_range.py --plan 50:2,100:1,130:2

# tổng hợp: bảng bin + 4 hồi quy + bootstrap theo bag + bảng câu hỏi
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
  scripts/measure_pdet_vs_range.py --mode aggregate
```

Đổi `--slice` (0,5 / 2,0 m), `--height-max` (3,0 m) hoặc `--lateral-half` để chạy độ bền; đổi
`--plan` để đổi số bag. Mọi tham số của một lần chạy được ghi ở dòng `_kind: params` trong JSONL.

```bash
# §11 — đo lại với n_max CỦA GENERATOR (load_beam_table() + r = 0,31 m), ~91 s
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
  scripts/measure_pdet_vs_range.py --plan 50:2,100:1,130:2 \
  --out .scratch/tmp/pdet_gen.jsonl --summary .scratch/tmp/pdet_gen_summary.json
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
  scripts/measure_pdet_vs_range.py --mode aggregate \
  --out .scratch/tmp/pdet_gen.jsonl --summary .scratch/tmp/pdet_gen_summary.json

# §11 — hai nghiệm thu ở chế độ b = +0,22 (bỏ biến = b = 0,0 = P_det hằng)
PLUME_PDET_RANGE_EXPONENT=0.22195 CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python scripts/measure_plume_size_tail.py --seeds 8 --frames 120
PLUME_PDET_RANGE_EXPONENT=0.22195 CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python scripts/measure_following_scenario.py --frames-per-scene 30
```

---

## 11. Áp dụng vào generator — `P_det(R) = P_det0 · (R / 25 m)^b` (2026-11-19)

Người cài: subagent kỹ thuật. Code: `spray/raycast.py::RaycastConfig.pdet_range_exponent`
+ `_range_factor()` trong `raycast_frame()`. Đo lại bằng `scripts/measure_pdet_vs_range.py`
với **`n_max` do chính `load_beam_table()` sinh ra**: `.scratch/tmp/pdet_gen.jsonl`
(1 656 cụm / 10 bag), `.scratch/tmp/pdet_gen_summary.json`.

### 11.1 Số mũ `b` — đo với ĐÚNG bảng tia của generator `[ĐO]`

Số mũ phải đo bằng **cùng** mẫu số mà generator dùng, nếu không phép chia `n / n_max`
không còn là "số tia cắt quả cầu": `n_max` = số tia của `load_beam_table()`
(30 ring đều 0,333° trong FOV −4,06…+5,88° × 1 825 cột az) cắt quả cầu bán kính
**cố định 0,31 m** (`RADIUS_MEDIAN_M`, `spray/plume_state.py`) đặt tại tâm cụm thật.
Tiêu chí đếm y hệt `_collect_hits` (khoảng cách từ đường thẳng chứa tia tới tâm ≤ r,
tâm ở phía trước cảm biến).

| biến thể `n_max` | cụm dùng được | loại vì `n_max=0` | `b` | CI95 (bag) | bag-FE `b` | CI95 | R² |
|---|---:|---:|---:|---|---:|---|---:|
| **generator: production + `r` = 0,31 m** (chuẩn) | **980** | **676 (40,8 %)** | **+0,222** | `[−0,135; +0,547]` | +0,212 | `[−0,143; +0,555]` | 0,005 |
| generator, `E[n_max]` theo lognormal paper (5 lượng vị trí) | 1 408 | 248 (15,0 %) | −0,327 | `[−0,895; +0,075]` | −0,385 | `[−0,948; +0,098]` | 0,011 |
| (tham chiếu §4) lưới tia thật + `r` từng cụm | 1 656 | 0 | −0,166 | `[−0,377; +0,005]` | −0,254 | `[−0,421; −0,084]` | 0,006 |
| (tham chiếu §4) lưới tia thật + `r` = 0,31 m | 1 656 | 0 | +0,344 | `[+0,206; +0,529]` | +0,343 | `[+0,188; +0,566]` | 0,031 |
| (tham chiếu §4) công thức paper `Ω/ω` | 1 656 | 0 | +1,059 | `[+0,753; +1,270]` | — | — | 0,180 |
| (tham chiếu §7.4) `b_n + 2`, bảng tia ĐỀU | 1 656 | 0 | +1,89 | `[+1,83; +1,98]` | — | — | — |

Ba số `[ĐO]` giải thích vì sao `+1,89` **không** phải số đúng cho generator:

1. `n_max` của bảng production **không** giảm như `R⁻²`: đo được `n_max_gen ∝ R^−0,679`
   (CI95 `[−1,068; −0,408]`) trên 980 cụm dùng được. Hai lý do: (i) FOV chỉ 9,94° nên quả
   cầu 0,31 m ở gần bị **cắt cụt** bởi sàn −4,06° (nó "được" ít tia hơn góc khối hình học);
   (ii) cụm gần nằm ở elevation thấp (median −5,0° ở bin 5–10 m) tức đúng vùng sàn, còn cụm
   xa ở −3,0…−3,6° tức nằm trọn trong FOV. Hai hiệu ứng bù nhau.
2. Vì `n` đo được gần như phẳng (`b_n = −0,112`) nên `P_det` **chỉ cần** tăng `R^0,22`,
   không phải `R^1,89` — chênh **1,67** đơn vị số mũ, đúng bằng phần "bảng tia thật + FOV
   hẹp" đã hấp thụ (so §8.2–8.3).
3. `676` cụm bị loại **không phải nhiễu**: elevation −15,65…−5,11° (median −7,25°) tức
   **nằm dưới sàn FOV** của bảng production (§8.3; 676 = 669 cụm của §8.3 + 7 cụm mà bán kính
   0,31 m cố định không với tới FOV trong khi bán kính đo được thì vừa). Hệ quả: **không cụm nào
   ở `R < 6 m` dùng được** (cụm gần nhất còn `n_max > 0` ở 6,02 m) ⇒ với bảng tia này 40,8 % cụm
   thật "vô hình", và đó đúng là vùng near-field mà A3-V lệch 8–17×.
   **Số mũ vì vậy chỉ được đo trên 6–30 m** (median 18,0 m).

Hai kiểm tra chéo:

- **Hằng đẳng thức `b = b_n − slope(n_max)`** chỉ đúng khi hai vế dùng **cùng mẫu**. Trên 980
  cụm dùng được: `b_n`(mẫu) = −0,457, `slope(n_max)` = −0,679 ⇒ **+0,222**, khớp tuyệt đối với
  fit trực tiếp (OLS trên cùng mẫu là đại số). Trên cả 1 656 cụm: `b_n = −0,112` ⇒ +0,567;
  số đó **sai cho generator** vì trộn các cụm mà generator không thể nhìn thấy (nó cho `n = 0`,
  không phải `n` nhỏ).
- **bin-median** (5 bin) cho `b = +0,135`, cùng dấu và cùng bậc với +0,222 ⇒ không do vài cụm
  lớn chi phối.

`[CHỌN]` Dùng **b = +0,22** (chuẩn, `r` cố định 0,31 m). Lý do không dùng biến thể `E[r]`
(−0,327): (i) nó đặt vào mẫu số những bán kính 0,50–1,94 m trong khi bán kính **đo được** của
chính các cụm đó là 0,25–0,37 m — một phản thực tế bị phóng 6×; (ii) CI95 `[−0,895; +0,075]`
vắt qua 0 **và** +0,1, tức không phân biệt được `P_det` hằng với `P_det ∝ R^0,1`; (iii) dấu âm
sẽ **tăng** mật độ near-field, ngược chiều sai lệch đã đo ở A3-V. Cả hai biến thể thống nhất ở
điểm quan trọng: **|b| ≤ 0,5 — dữ liệu static KHÔNG phân biệt được `P_det` hằng với `P_det(R)`
dốc nhẹ.**

### 11.2 Cài đặt `[CODE]`

```
P_det(R) = P_det0 · (R / R0)^b,  R0 = 25 m (cự ly paper đo, Fig. 7),  b = pdet_range_exponent
```

- `R` = khoảng cách từ cảm biến tới **tâm cụm** (`np.linalg.norm(cluster.pos)`), đúng như
  `_collect_hits` dùng; `P_det0` vẫn là mẫu lognormal paper (`mu = −2,3`, `sigma = 1,1`) —
  chỉ **luật theo cự ly** là mới, giá trị tại 25 m không đổi.
- `RaycastConfig.pdet_range_exponent: float = 0.0` ⇒ **mặc định là hành vi cũ** (`P_det` hằng);
  nhánh `!= 0.0` là nhánh duy nhất bị thêm, nên mọi kết quả cũ tái lập **bit-for-bit**
  (test `test_pdet_at_paper_distance_does_not_depend_on_the_exponent`: ở đúng 25 m hệ số = 1,0
  nên mảng detection trùng tuyệt đối). Đã kiểm chứng ở mức nghiệm thu: chạy lại A3 8 seed và
  A3-V 30 frame/scene với `b = 0` cho **đúng từng số** của ADR-0006 §5/A3-V (13,0/144,0/283,4;
  1,98/0,86/2,73/4,63/16,92/8,02) ⇒ không có thay đổi ẩn.
- Hai script nghiệm thu không nhận config từ CLI (và không được sửa), nên chế độ chọn bằng biến
  môi trường `PLUME_PDET_RANGE_EXPONENT`; nó chỉ cấp **giá trị mặc định** cho dataclass, config
  truyền tường minh luôn thắng. Production (`PlumeTransform` → `raycast_frame()` không truyền
  config) vì vậy **vẫn chạy b = 0,0** trừ khi ai đó set biến này — bật cho production là quyết
  định của ADR, không phải của code.
- **Không** đụng `diffusion_alpha`, `RADIUS_*`, lifetime, drag, `spawn_scale`, bảng
  `_CLUSTER_VISIBLE_BY_SPEED`, `p_det_scale`.
- Test: `tests/test_raycast.py` +5 test; toàn bộ **213 passed** (trước: 208).

### 11.3 A3 (static) trước/sau `[ĐO]`

Nghiệm thu đủ: 8 seed × 120 frame (thực 120/66/51), `.scratch/tmp/a3_full_b0.txt` /
`a3_full_b0222.txt` + profile JSON cùng tên hậu tố `_profiles.json`. Bản nhanh
(`--seeds 2 --frames 60`) cho cùng kết luận.

| km/h | điểm/frame ± CI95 | (a) | trail90 | (b') trail | %mass≤20 | (b') profile | (c) | verdict |
|---|---:|---:|---:|---|---:|---|---:|:---:|
| **b = 0** | | | | | | | | |
| 50 | 13,0 ±11,1 % | 0,15× ✗ | 2,2 m | 0,37× ✗ | 100,0 % | 94 % (0–2 m) ✗ | ✓ | FAIL |
| 100 | 144,0 ±5,8 % | 0,71× ✓ | 40,2 m | 0,91× ✓ | 60,8 % | 268 % (2–4 m) ✗ | ✓ | FAIL |
| 130 | 283,4 ±9,0 % | 1,36× ✓ | 49,8 m | 0,96× ✓ | 44,1 % | 995 % (0–2 m) ✗ | ✓ | FAIL |
| **b = +0,22** | | | | | | | | |
| 50 | 13,4 ±10,5 % | 0,16× ✗ | 2,2 m | 0,37× ✗ | 100,0 % | 93 % (0–2 m) ✗ | ✓ | FAIL |
| 100 | 150,6 ±5,6 % | 0,74× ✓ | 40,8 m | 0,93× ✓ | 59,5 % | 255 % (2–4 m) ✗ | ✓ | FAIL |
| 130 | 294,8 ±8,6 % | 1,41× ✓ | 50,0 m | 0,96× ✓ | 43,1 % | 959 % (0–2 m) ✗ | ✓ | FAIL |

**A3: 0/3 tốc độ PASS ở cả hai chế độ** ⇒ `P_det(R)` **không** đổi phán quyết. Chi tiết:

- (a) xấu đi nhẹ **+4,6 %** ở 100/130 km/h (144,0 → 150,6; 283,4 → 294,8) vì cụm ở kịch bản
  static phần lớn ở **> 25 m**, nơi `(R/25)^0,22 > 1` làm `P_det` **tăng**. `b = +0,22` đẩy
  (a)@130 lên **1,41×**, sát trần 1,5× ⇒ **không thể tăng b thêm** mà không phá A3 (a).
- (b') profile-shape **giảm nhẹ** (268 → 255 %; 995 → 959 %) nhưng vẫn trượt xa ngưỡng 30 %;
  %mass≤20 đổi ≤ 1 pp. Kết luận (b') không đổi.
- (b')@50 ở bảng trên dùng profile thật của `roadspray-static-depth-profile.md`; toán tử đã kiểm
  chứng: nó cho **268,0 % / 994,9 %** ở 100/130, đúng số ADR đã công bố. @50 nó cho 93,9 % cho
  cấu hình ADR (ADR ghi 98,2 %) ⇒ riêng @50 sai khác ~4 pp do profile thật @50 trong doc thuộc
  một biến thể khác; không đổi verdict.

### 11.4 A3-V (following) trước/sau `[ĐO]`

`scripts/measure_following_scenario.py --frames-per-scene 30`, cùng seed, cùng 108 scene
(A 36 boxed + B 72 unboxed). Số thô: `.scratch/tmp/following_b0.json` / `following_b0222.json`.
**Verdict đọc trên tập B** (pre-registered, 171 scene không box). Tập A là eval set, chỉ để đối
chiếu.

| lớp | nhóm | median trước | CI95 | median sau | CI95 | đổi | <10 m sau | <4 m sau | verdict sau |
|---|---|---:|---|---:|---|---:|---:|---:|:---:|
| Crafter | 50–70 | 1,98 | `[1,58; 2,60]` | **1,74** | `[1,49; 2,25]` | 0,88× | 33,7 % | 11,9 % | FAIL |
| Golf | 50–70 | **0,86** | `[0,51; 1,68]` | **0,76** | `[0,48; 1,36]` | 0,88× | 43,4 % | 17,7 % | FAIL (CI dưới 0,48) |
| Crafter | 80–110 | 2,73 | `[2,30; 3,14]` | **2,04** | `[1,71; 2,33]` | 0,75× | 75,9 % | 41,0 % | FAIL |
| Golf | 80–110 | 4,63 | `[3,97; 5,73]` | **3,53** | `[2,88; 4,29]` | 0,76× | 72,3 % | 35,6 % | FAIL |
| Crafter | 120–130 | **16,92** | `[13,88; 20,88]` | **13,43** | `[11,13; 15,51]` | 0,79× | 74,4 % | 41,1 % | FAIL |
| Golf | 120–130 | 8,02 | `[6,07; 11,64]` | **5,99** | `[4,66; 8,65]` | 0,75× | 73,4 % | 38,1 % | FAIL |

Trước: **1/6 ô PASS** (Golf 50–70). Sau: **0/6 ô PASS**. Tập A (không phải verdict):
Crafter 50–70 0,80 → 0,79 PASS; Golf 50–70 0,36 → 0,32 FAIL; Crafter 80–110 1,30 → **0,98 PASS**;
Golf 80–110 3,50 → 2,72 FAIL; 120–130 4,61 → 3,75 và 4,51 → 3,44 FAIL (2/6 PASS cả trước và sau).

Ba điều phải khai:

1. **Mức giảm đúng bằng cận trên của số mũ.** `(R/25)^0,22` = **0,57** ở 2 m, 0,66 ở 4 m, 0,85 ở
   10 m, 0,94 ở 16 m, **1,00 ở ≥ 25 m** ⇒ tối đa chỉ giảm được 1,75× ở near-field, và **không
   giảm gì** ở far-field. Đo được 1,14–1,34× ⇒ đúng cận trên, không phải "chưa tune đủ".
2. **Ô duy nhất từng PASS nay FAIL** (Golf 50–70: 0,86 → 0,76, CI dưới 0,51 → 0,48). Ô này vốn
   **thiếu** điểm (0,86×) nên `b > 0` làm tệ thêm. Đây là hệ quả tất yếu của một luật đơn điệu.
3. **Near-field chỉ giảm vài pp**: `range < 10 m` 81,1 → 74,4 %, `range < 4 m` 49,2 → 41,1 %
   (Crafter 120–130). Trong khi đó 40–80 % detection vẫn nằm sát cảm biến ⇒ nguyên nhân không
   phải `P_det`.

### 11.5 Kết luận — `P_det(R)` sửa được gì, còn lệch bao nhiêu `[SUY RA]`

**Sửa được:** đúng phần hình học mà nó đại diện — 1,14–1,34× ở A3-V (cận trên lý thuyết 1,75×
ở 2 m), và không đổi phán quyết nào. **Không sửa được** near-field, vì hai lý do định lượng:

1. **Hai kịch bản đòi hai dấu ngược nhau.** Static (12–200 m) đã **quá đậm** ở 130 km/h
   ((a) = 1,36× trước, 1,41× sau) nên nó chỉ chịu được `b ≤ ~0,25`; following (1–25 m) cần
   `P_det` **tăng mạnh** ở gần. Một luật luỹ thừa neo ở 25 m **không thể** làm cả hai.
2. **Số mũ mà near-field cần lớn hơn số đo 7×.** Với bảng production, `n_max(2 m, r = 0,31)`
   = **2 566** tia ⇒ ở `P_det0 = 0,10` generator đặt **257 điểm** vào một cụm ở 2 m, trong khi
   dữ liệu thật cho **~5 điểm/cụm** (phẳng từ 4 đến 30 m). Muốn ~5 điểm ở 2 m thì
   `P_det(2 m) ≈ 0,002` ⇒ **b ≈ +1,56**. Nhưng cùng `b` đó cho `P_det(50 m) = 0,30` (3× hiện
   tại) và `P_det(100 m) ≈ 0,87` ⇒ (a)@130 của A3 sẽ bùng nổ, và nó **vượt xa** số đo +0,22.
   Không có giá trị `b` nào thoả cả hai; đây là bằng chứng định lượng cho câu "định luật tỉ lệ
   theo cự ly SAI" ở ADR-0006 §"Nguyên nhân sâu hơn" — nhưng **sửa bằng `P_det` là sai chỗ**.
3. **Calibration không có chỗ tựa ở near-field.** 40,8 % cụm thật (toàn bộ `R < 6 m`) có
   `n_max = 0` với bảng production vì plume thật nằm dưới sàn FOV −4,06° (§8.3). Không có dữ
   liệu nào trong phép đo này ràng buộc `P_det` dưới 6 m ⇒ mọi giá trị `b` dưới 6 m là **ngoại
   suy**, và ngoại suy theo luật sai (bảng tia 9,94° thay vì 40° của VLP-32C) thì không thể đúng.

**Đề xuất bước tiếp (chưa làm, cần mở ADR):**

- `pdet_range_exponent` **giữ 0,0** trong production: +0,22 làm A3 (a)@130 xấu thêm mà không
  cứu được A3-V ⇒ bật là net-negative cho tới khi có quyết định khác.
- Sửa **hình học**, không sửa `P_det`: (i) cho `r` phụ thuộc cự ly theo số đo `r ∝ R^0,42`
  (§8.1) — đây là nguyên nhân **độc lập** gây bùng nổ; (ii) dùng lưới ring **đo được** của
  VLP-32C (−25…+15°, §8.3) thay lưới 9,94° — nhưng đổi bảng tia là đổi toàn bộ nghiệm thu cũ.
- Phần **mức tuyệt đối** còn lại (5–13× ở 80–130 km/h) là việc của `following_density_scale`
  (D2-v2, một số vô hướng) — và dải 0,76 → 13,43× vẫn vượt khả năng của một số vô hướng, đúng
  như dự đoán đã ghi trong ADR-0006.
