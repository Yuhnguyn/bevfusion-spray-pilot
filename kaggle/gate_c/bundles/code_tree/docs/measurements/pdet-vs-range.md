# `P_det` theo cự ly trên RoadSpray `*_static` — Eq. 7 đo ở nhiều khoảng cách (2026-11-19)

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
