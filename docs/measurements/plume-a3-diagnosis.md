# A3 — chẩn đoán: vì sao generator thiếu khối lượng và thiếu chuỗi (2026-11-19)

Người đo: lead. Số `[ĐO]` trên máy này. Dụng cụ: `scripts/measure_plume_size_tail.py`.
Nhãn: `[ĐO]` đo được · `[SUY LUẬN]` suy ra · `[CHỌN]` tự chọn.

## 0. Câu hỏi

Sau A1 + bảng calibration mới, generator khớp **cụm/frame** nhưng: 323 điểm/frame ở 100 km/h
(thật 875), `% điểm trong cụm ≥50 điểm` = 50 % (thật 82 %), cụm lớn nhất 190 (thật tới 2 485).
A3 phải sửa. Câu hỏi: sửa **cơ chế nào**?

## 1. Bốn giả thuyết và cách phân biệt

| # | Giả thuyết | Nếu đúng thì |
|---|---|---|
| H1 | Nguồn phun rời rạc (bánh sau) làm plume thật dồn thành cột | phải thêm nguồn cố định |
| H2 | Mật độ góc: thật dày hơn nên percolation nối thành chuỗi | chỉ cần thêm điểm trong cùng vùng |
| H3 | Hình học plume của ta sai (loãng/quá rộng) | phải thu hẹp vùng sinh |
| H4 | Mô hình điểm/cụm sai (không phụ thuộc tốc độ) | phải đổi hàm điểm/cụm |

## 2. Đo 1 — cấu trúc không gian góc, thật vs sinh (100 km/h) `[ĐO]`

| | n điểm | diện tích góc | lấp đầy @0,7° | số mảnh | mảnh lớn nhất | NN p50 |
|---|---:|---:|---:|---:|---:|---:|
| Thật (5 frame) | 653–2 056 | 12 764–21 041 deg² | 0,8–2,0 % | 12–49 | 30–84 % | 0,18–0,23° |
| Sinh (20 frame) | 222–497 | 3 753–19 866 deg² | 0,3–2,0 % | 7–25 | 22–49 % | 0,11–0,32° |

`[SUY LUẬN]` Plume sinh phủ **~1/2 diện tích góc** nhưng chỉ có **~1/4 số điểm** ⇒ mật độ góc thấp hơn
**~2,4×**. H3 không phải nguyên nhân chính (ta *hẹp* hơn, không rộng hơn). H1 và H2 chưa phân biệt được.

## 3. Đo 2 — điểm/cụm theo cự ly, thật vs bảng trong code `[ĐO]`

Code dùng `_POINTS_MEDIAN_BY_RANGE = (30, 20, 14, 10, 10)` như **median**, nhân lognormal `σ = 0,67`.

| cự ly | 50 km/h: số cụm / p50 / mean | 100 km/h: số cụm / p50 / mean | bảng code |
|---|---|---|---|
| 0–5 m | 30 / **7** / 21,5 | 31 / **5** / 25,7 | 30 |
| 5–10 m | 49 / **7** / 38,6 | 50 / **7** / 54,1 | 20 |
| 10–20 m | 25 / **9** / 51,6 | 28 / **10** / 101,7 | 14 |
| 20–30 m | 1 / – / – | 1 / 4 / 4,0 | 10 |

`[SUY LUẬN]` **Hai lỗi cùng lúc:**
1. Bảng code là **~4× quá cao** so với median thật (30 vs 7 ở 0–5 m).
2. Nhưng **mean thật lại cao hơn hẳn** median (21–102) vì phân bố cực lệch. Code dùng median cố định
   `σ = 0,67` ⇒ không bao giờ sinh được đuôi đó.

`[SUY LUẬN]` **Điểm/cụm thật tăng 4,5× theo tốc độ** (8,9 @50 → 40,5 @100), trong khi mô hình hiện tại
gắn điểm/cụm vào **cự ly** — mà kịch bản following luôn đặt xe ở 20 m ⇒ **điểm/cụm gần như không đổi
theo tốc độ**. Đây là **H4**, và nó giải thích cả hai đầu sai: thừa 3× ở 50 km/h, thiếu 2,7–4,2× ở
100–130 km/h.

## 4. Đo 3 — thử sửa bằng "thêm cụm" hoặc "tăng sigma" `[ĐO]`

**Nhân số cụm sinh** (m = 1…6), 100 km/h: `%≥50đ` bão hoà ở **~65 %** (thật 82 %); 130 km/h cũng vậy
(63,9 % ở m=6). Ở 50 km/h nhân càng nhiều càng thừa (m=1 đã 3,1×). ⇒ **H2 không đủ**, thêm điểm không
tạo được chuỗi.

**Quét (scale bảng điểm/cụm) × (sigma)**, 100 km/h:

| scale | σ | điểm/frame | p50 | p95 | %≥50đ |
|---:|---:|---:|---:|---:|---:|
| 0,7 | 0,67 | 236 | 6 | 57 | 34 % |
| 0,7 | 1,30 | 395 | 6 | 140 | 72 % |
| 0,7 | 1,60 | 486 | 6 | **192** | **77 %** |
| 0,5 | 1,60 | 382 | 5 | 132 | 70 % |

`[SUY LUẬN]` Tăng σ tạo được đuôi (p95 và share đạt), nhưng **không có cặp (scale, σ) nào pass cả ba
tiêu chí** ở 100 km/h: muốn đủ khối lượng thì phải nâng scale, mà nâng scale lại làm hỏng 50 km/h
(nơi thật chỉ có 43 điểm/frame). ⇒ cần **thành phần chuỗi có trọng số phụ thuộc tốc độ**, không phải
một σ chung.

## 5. Kết luận → hướng sửa A3

**Giả thuyết "nguồn phun cố định ở bánh sau" (H1) mà tôi nêu trước đó KHÔNG được số liệu xác nhận** —
không cần đến nó để giải thích. Nguyên nhân thật là **H4**: mô hình điểm/cụm không có thành phần phụ
thuộc tốc độ, trong khi dữ liệu thật cho thấy chính thành phần đó tạo ra 4,5× khối lượng và 82 % điểm
nằm trong chuỗi.

**Hướng sửa (chốt cho A3): mô hình **hỗn hợp** điểm/cụm:**

* nhánh "cụm thường": median **5–7 điểm** (khớp p50 thật ở mọi tốc độ), σ nhỏ;
* nhánh "chuỗi": xác suất **p(v)** tăng theo tốc độ, median lớn (~60–100 điểm), σ lớn;
* hiệu chỉnh `p(v)` và median nhánh chuỗi sao cho ba tiêu chí A3 pass: `%điểm trong cụm ≥50đ` lệch
  ≤ 10 điểm %, `p95` trong [0,5×; 2×] thật, `điểm/frame` trong [0,7×; 1,5×] thật ở 50/100/130 km/h.

Giá trị ban đầu để hiệu chỉnh: `p(v)` ≈ share điểm trong chuỗi đo được = **15 % @50 · 82 % @100 ·
83 % @130**; median chuỗi suy từ `p95`/`max` thật (182/2 241 @100).

**Việc KHÔNG làm nữa:** thêm nguồn phun rời rạc; nhân số cụm; tăng σ đồng loạt. Cả ba đều đã đo và
không đủ.

---

# 6. BẢN 2 — 2026-11-19 (sau audit R2 + QĐ1–QĐ8 của Lead) `[ĐO]`

> Trạng thái: **A3 CHƯA PASS**. Các mục 0–5 ở trên là **lịch sử** — đo bằng dụng cụ đã
> bị chứng minh sai (xem §6.2), nên mọi phán quyết "PASS" trong đó **vô hiệu**
> (`.scratch/roadspray-cal/tasks/A3-team.md` §2). Bản 2 ghi: 4 lần lệch toán tử đã bịt,
> trạng thái QĐ7, và việc **đang chờ T4** (R2 đo depth profile thật 0–60 m).

## 6.1 Bảng trước → sau (2 seed × 60 frame, tầng raycast, default config)

Cột A tái lập đúng số Lead đã báo trước đây (dụng cụ còn bug §1.4): 342 / 1477 / 1541.

| cấu hình | 50 km/h | 100 km/h | 130 km/h |
|---|---|---|---|
| **A. default cũ** (radius Δ=2,5 0,48–0,70; sigma 0,8; streak 1,0) | det 342 · cụm 6,8 | det 1477 · cụm 24,2 | det 1541 · cụm 12,9 |
| **B. fix dụng cụ + streak 0 + bảng Δ=1,0** | det 76 · cụm 4,5 | det 553 · cụm 42,8 | det 432 · cụm 20,1 |
| **C. + QĐ7 (vùng sinh = hộp static)** | det 231 · cụm 12,9 | det 395 · cụm 19,4 | det 288 · cụm 9,4 |

Đích static Δ=1,0: det 236 / 500 / 432 · cụm 9,0 / 35,9 / 33,1 · r50 0,349 / 0,292 / 0,311 m.

## 6.2 Bốn lần lệch toán tử đã bịt (nguyên nhân mọi "PASS" cũ)

| # | Lệch | Hậu quả | Đã bịt bằng | Trạng thái |
|---|---|---|---|---|
| 1 | Đo trên `PlumeResult.injected` (điểm materialised `ring=-1`, bị `raycast.py:117` loại) | đo con số detector không thấy | đo `RaycastResult.detections` | ✅ |
| 2 | Bán kính lấy cột **Δ=2,5 m** (chain-merge dọc tia) | bán kính phồng 1,6–2,1× ⇒ điểm/cụm phồng | cột **Δ=1,0** validated ngược (§roadspray doc §9), sigma 0,72, clip 2,0 (=p99) | ✅ |
| 3 | Cụm của generator = DBSCAN **cả frame**; cụm static = DBSCAN **trong từng lát Δ=1,0** | p95/share hai vế khác đơn vị | thêm cột `*_slice` dùng đúng toán tử static (`static_slice_cluster_sizes`) | ✅ |
| 4 | `det` cả frame vs đích đo **trong hộp 20 m** sau đuôi | "khớp 593 vs 500" là may mắn; trong hộp chỉ 0,08–0,13× | QĐ7: đặt **vùng sinh = hộp static** (W3,4 · H1,5 · L20) | ⚠ **chưa xong** — xem §6.3 |
| 5 | `p95`/`share` phụ thuộc bề dày lát (172 → 242 → 329 qua Δ=1,0→2,5→6,0) | không so được giữa hai nguồn | QĐ8: tiêu chí (b) chuyển sang **r50 / rsig** (định nghĩa paper §III-B) | ✅ (số đã có, xem §6.4) |

## 6.3 QĐ7 — vùng sinh = hộp calibration static, và việc chờ T4

Đã sửa `spray/plume.py` + `spray/plume_state.py`: cụm sinh **phân bố đều** trong hộp
sau đuôi **W = 3,4 m × H = 1,5 m tính từ mặt đường × sâu 20 m**; bỏ `tail_block_height_frac`,
`LATERAL_CLAMP_M`, nguồn 2 bánh và `placement_knots` (tất cả nguồn SSPP — R2 audit PHẢI BỎ).
Field cũ giữ lại (không dùng) để không phá chữ ký `PlumeConfig`/`PlumeStateConfig`.

**Cửa kiểm QĐ7 (≥ 90 % detections trong hộp): FAIL — 42,8 % / 16,3 % / 5,9 %** (50/100/130).

| km/h | trong hộp | ngoài ngang | ngoài cao | ngoài sâu | depth p50/p90/p95 (m) | \|y\| p95 (m) | height p95/max (m) |
|---|---:|---:|---:|---:|---|---|---|
| 50 | 42,8 % | 27,1 % | 42,0 % | 12,3 % | 12,2 / 23,8 / 26,9 | 2,19 | 1,75 / 2,25 |
| 100 | 16,3 % | 44,7 % | 43,8 % | 34,8 % | 16,9 / 38,6 / 45,4 | 2,92 | 1,73 / 2,25 |
| 130 | 5,9 % | 30,2 % | 8,6 % | 94,1 % | 36,8 / 62,7 / **75,3** | 3,07 | 1,37 / 1,88 |

Hai nguyên nhân `[ĐO]`:
1. **Trôi dọc** (chính ở tốc độ cao): sinh trong 0–20 m rồi drag `C = −0,15 m⁻¹` [PAPER] làm
   cụm gần như dừng, xe đi tiếp ⇒ cụm rơi lại; @130 depth p50 = 37 m, p95 = 75 m ⇒ 94 % ra
   ngoài hộp phía sau. Đây là **hệ quả đúng của công thức lifetime paper**
   `T = 0,02·wfh·(v−50) + 0,2`, không phải tham số SSPP.
2. **Bán kính cụm > khoảng cách tới vách hộp**: tâm cụm trong hộp nhưng quả cầu bán kính
   tới 2,0 m làm detection lòi ra ngoài W/2 = 1,7 m và H = 1,5 m.

**Đang chờ T4 (R2):** đo depth profile thật 0–60 m từ bag static (bin 2 m, ngang ±5 m,
cao 0–3 m) để trả lời trail thật dài bao nhiêu (90 % mass) và bao nhiêu % detections thật
nằm trong hộp 20 m. **Chưa kết luận vùng đo/tiêu chí cho tới khi có số T4** — nếu trail
thật cũng dài ~50 m thì đích 236/500/432 chỉ là phần trong hộp và phép so "det cả frame vs
đích trong hộp" sai thêm lần nữa; nếu trail thật ~20 m thì mô hình trôi của generator sai.

## 6.4 QĐ8 — đại lượng bất biến với toán tử cắt lát `[ĐO]`

Trong cùng lát Δ=1,0, mỗi cụm có `radius = max ‖p − centroid‖` (đúng định nghĩa Paper A
§III-B). Đo 2 seed × 60 frame (cấu hình C ở §6.1):

| km/h | r50_slice | đích r50 Δ=1,0 | tỉ lệ | rsig_slice | đích rsig | tỉ lệ |
|---|---:|---:|---:|---:|---:|---:|
| 50 | 0,17 | 0,349 | 0,48× | 0,69 | 0,754 | 0,91× |
| 100 | 0,17 | 0,292 | 0,59× | 0,73 | 0,727 | 1,00× |
| 130 | 0,20 | 0,311 | 0,64× | 0,72 | 0,711 | 1,01× |

`[SUY LUẬN]` **rsig khớp**, **r50 của generator nhỏ hơn ~0,5–0,65×** so với static đo cùng
toán tử. Lưu ý: cắt lát cũng làm giảm `r50` của một quả cầu (phần bị cắt mất), nên r50_slice
chưa hoàn toàn "bất biến"; nhưng đây là đại lượng duy nhất **hai vế đo cùng một định nghĩa**.
Kết luận này cũng đang chờ T4 trước khi dùng để sửa tham số.

## 6.5 Tham số đang dùng + nguồn

| Tham số | Giá trị hiện tại | Nguồn | Ghi chú |
|---|---|---|---|
| `RADIUS_MU` | −1,2 | `[PAPER]` Linnhoff Fig. 5 | một lognormal duy nhất |
| `RADIUS_SIGMA` | **0,72** | `[ĐO]` static Δ=1,0: rsig median 0,720 (9 tốc độ, 0,701–0,771) | thay 0,97 (Δ=2,5) |
| `RADIUS_MAX_M` | **2,0** | `[PAPER]` không đặt clip; p99 = exp(−1,2+2,326·0,72) = **1,94 m** | bỏ clip 1,0 (dee.cpp:528, code tham chiếu) |
| Trung vị bán kính theo tốc độ | hằng **0,31 m** (tạm) | `[ĐO]` 3 mốc Δ=1,0: 0,349/0,292/0,311; paper 0,301 | **D5 chờ Mốc 4** — sẽ dùng bảng 9 tốc độ |
| `_CLUSTER_VISIBLE_BY_SPEED` Crafter | 9,04 / 14,40 / 19,77 / 25,13 / 30,50 / 35,86 / 34,93 / 34,01 / 33,08 | `[ĐO]` static Δ=1,0 `cpf` (9,04/35,86/33,08 @50/100/130 + nội suy tuyến tính) | bảng Δ=2,5 cũ đã bỏ |
| `_CLUSTER_VISIBLE_BY_SPEED` Golf | 4,73 … 25,18 | static Δ=2,5 cũ | **CHƯA ĐO Δ=1,0 — chưa validate; A3 không dùng tới** |
| `streak_scale` | **0,0** (tắt) | R2 audit: KHÔNG có trong paper | trước 0,5 → gây `max` điểm/cụm ~3.500 |
| Vùng sinh | W3,4 · H1,5 · L20 sau đuôi | `[CHỌN]` D2-hợp lệ: paper chỉ nói "uniform ... behind every moving object", không cho kích thước ⇒ dùng vùng do phép đo calibration định nghĩa | QĐ7, đang chờ T4 |
| `source_count` | 0 (tắt) | R2 audit: hai bánh xe là tham số tự thêm, không có trong paper | field `source_*` giữ nhưng không dùng |
| `points_per_cluster_median` | 17 (dead-path) | `[ĐO]` chỉ mô tả tầng **materialised**; `PlumeTransform` bỏ các điểm này | **không ảnh hưởng det/frame** |
| Lifetime `T` | `0,02·wfh·(v−50)+0,2` | `[PAPER]` | **không sửa để số đẹp** |
| `wfh_mm` | 1,0 | `[CHỌN]` dataset không khai báo độ ướt | giữ làm mức chuẩn |
| Drag `C` | −0,15 m⁻¹ | `[PAPER]` | |

## 6.6 Tiêu chí A3 hiện hành (Lead ký 2026-11-19)

- Nghiệm thu: **8 seed × 120 frame**; sweep nhanh 2 seed × 60 frame (không dùng để kết luận).
- **(a)** `mean(det)/mean(real)` ∈ [0,7; 1,5].
- **(b)** QĐ8: `r50_slice` và `rsig_slice` trong **±20 %** đích static Δ=1,0
  (0,349/0,292/0,311; rsig 0,754/0,727/0,711). `p95_slice`/`share_slice` **chỉ in chẩn đoán**.
- **(c)** CI95 half-width của `det/frame` ≤ **25 %** của mean (bootstrap theo seed, B=2000);
  không đạt ⇒ in `NHIỄU`, **không** được ghi PASS.
- `cụm_slice` = **cờ cảnh báo** (ngoài [0,5×; 2,0×] thì in ⚠), không phải tiêu chí.
- `[ĐO]` R3: block CV cửa sổ đo 60–120 frame = **21,7 % @50 · 22,2 % @100 · 12,1 % @130**
  ⇒ mọi chênh lệch < 25 % giữa hai cấu hình là **nhiễu**, không tinh chỉnh theo.

## 6.7 Tái lập

```bash
# sweep nhanh (2 seed × 60 frame, ~50-110 s tuỳ tải)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_plume_size_tail.py --seeds 2 --frames 60
# nghiệm thu (8 seed × 120 frame, ~7 phút)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_plume_size_tail.py
# tests
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -m pytest tests -q
```

`[ĐO]` 2026-11-19: `208 passed` (207 cũ + 1 test bất biến mới thay cho test clamp bị bỏ).

---

# 7. QĐ9 + QĐ10 — bỏ tiêu chí "hình dạng cụm", thay bằng profile độ sâu `[ĐO]`

Cập nhật 2026-11-19 sau phép đo **hàm truyền của toán tử đo**. Script:
`.scratch/tmp/operator_transfer.py` (chỉ dùng `.scratch/tmp/`, không sửa `spray/tests/dụng cụ`).

## 7.1 Bằng chứng: toán tử ĐO bóp méo bán kính 0,57–0,88× `[ĐO]`

Nạp vào đúng toán tử (raycast `load_beam_table` → cắt lát Δ=1,0 m → `cluster_angular`
0,7°/minPts 3) các **quả cầu bán kính biết trước**, rồi đo lại `r50_slice`:

**1 cụm/frame, thưa (range ~16 m) — hàm truyền:**

| r_in (m) | 0,20 | 0,31 | 0,50 | 0,80 |
|---|---:|---:|---:|---:|
| r50 đo được (m) | 0,176 | 0,242 | 0,360 | 0,459 |
| tỉ lệ đo/nạp | 0,88 | 0,78 | 0,72 | 0,57 |

**Cùng r = 0,31 m, tăng mật độ (cụm rải đều trong hộp):**

| số cụm | 1 | 5 | 20 | 60 | 120 |
|---|---:|---:|---:|---:|---:|
| r50 đo được (m) | 0,179 | 0,174 | 0,196 | 0,219 | 0,232 |
| tỉ lệ | 0,58 | 0,56 | 0,63 | 0,71 | 0,75 |
| cụm_slice | 0,9 | 2,9 | 8,8 | 19,3 | 30,9 |
| det_slice | 5,9 | 19,6 | 72,2 | 180,9 | 292,9 |

**Cùng mật độ 60 cụm, tách biến bán kính:** r_in 0,20 → r50 0,162; r_in 0,50 → r50 0,269
(×1,66). Ở mật độ ~ generator @100 (36 cụm): r_in 0,31 → r50 **0,202**; r_in 0,50 → 0,214.
Ảnh hưởng **range** nhỏ: dịch xe +10 m (static 18–38 m) chỉ đổi 0,202→0,189 (n=36),
0,232→0,244 (n=120).

`[SUY LUẬN]` Vì (i) cùng input 0,31 m chỉ đo ra 0,17–0,24; (ii) tăng mật độ 120× chỉ
kéo r50 +30 % (0,179→0,232), không thể đạt 0,349; (iii) muốn đo ra 0,349 phải nạp cầu
0,7–0,8 m = **2,5× paper 0,30** — nên **không được dùng 0,349/0,292/0,311 làm bán kính
đầu vào**. Chúng là **đại lượng ĐO ĐƯỢC** (đầu ra của toán tử trên plume thật dạng
**chuỗi điểm dày** — 26 điểm/cụm), không phải bán kính quả cầu. Nạp đầu ra làm đầu vào là
đếm trùng đúng hệ số bóp méo ~0,75×.

## 7.2 QĐ9 — huỷ D5 vĩnh viễn `[CHỌN]`

- Bán kính mô hình **giữ 0,30–0,31 m** (paper Linnhoff Fig. 5; static Δ=1,0 3 mốc
  0,349/0,292/0,311 là số đo đầu ra, chỉ dùng để kiểm chứng, không dùng làm input).
- D5 ("dựng bảng bán kính 9 tốc độ từ Δ=1,0") **huỷ**. Mốc 4 (D5) không làm nữa.
- `RADIUS_SIGMA = 0,72` và clip 2,0 m (=p99 1,94 m) giữ nguyên.

## 7.3 QĐ10 — tiêu chí (b') mới: profile theo độ sâu, KHÔNG clustering `[CHỌN]`

Bỏ mọi tiêu chí dựa trên cluster statistics (r50, rsig, p95, share, cụm/frame) khỏi
**điều kiện PASS** — lý do: cả hai vế đều đi qua `cluster_angular`, mà toán tử bóp méo
**khác nhau** với quả cầu rời (generator) và chuỗi thật (dữ liệu) — §7.1. Chúng chỉ còn là
**chẩn đoán in ra**.

Tiêu chí mới (chờ T4 chốt số đích):
- **(a)** tổng điểm/frame trong **0–60 m sau đuôi**: tỉ lệ sinh/thật ∈ **[0,7; 1,5]**;
- **(b')** **hình dạng profile** chuẩn hoá theo độ sâu (bin 2 m): lệch chuẩn hoá
  ≤ **30 %** ở mỗi bin có ≥ 10 % mass; độ sâu chứa **90 % mass** lệch ≤ **25 %**;
- **(c)** CI95 half-width của tổng điểm/frame ≤ **25 %** của mean (bootstrap theo seed,
  B = 2000; không đạt ⇒ `NHIỄU`, không được ghi PASS).

Dụng cụ đã có khả năng xuất profile phía generator: `scripts/measure_plume_size_tail.py`
in khối `QĐ10 — PROFILE ĐỘ SÂU` và ghi JSON `--profile-out` (mặc định
`.scratch/tmp/a3_generator_profiles.json`) gồm: `depth_profile_points_per_frame` (30 bin
2 m), `depth_total_points_per_frame`, `depth_p50_m`, `depth_p90_m`, `depth_mass90_m`,
`depth_frac_beyond_60`. Cách chia bin tái dùng đúng phép cắt lát Δ=1,0 của toán tử static
nhưng **chỉ đếm điểm, không clustering**.

`[ĐO]` Ví dụ smoke 1 seed × 10 frame (chưa phải nghiệm thu): generator đang dồn mass ở
**bin 16–18 m** (sát vách xa của hộp) ở cả 3 tốc độ; mass90 = 16 / 40 / 30 m; ngoài 60 m
= 0,0 / 1,3 / 4,4 %. Đây là profile **tạm**, chờ T4 để so với thật.

## 7.4 QĐ11 + 4 sửa lỗi R3 — tách vùng SINH khỏi vùng ĐO `[ĐO]`

**QĐ11 (2026-11-19):** QĐ7 đã gộp nhầm **vùng sinh** với **vùng đo**. Sửa lại:
- **Vùng SINH** = slab dài **`|v|·Δt`** (1,4 m @50 · 2,8 @100 · 3,6 @130), rộng 3,4 m,
  cao 1,5 m tính từ mặt đường, ngay sau đuôi xe. Nguồn: implementation reference của
  tác giả (`openMSL/sl-1-2`, `define_spray_volumes()`) + bề ngang/cao của hộp đo calibration.
- **Vùng ĐO** = profile bin 2 m trên **0–60 m** sau đuôi (chỉ đếm điểm, không clustering).

**4 sửa lỗi R3 audit (trước freeze):**
1. **Mask hai vế giống nhau** (lần lệch toán tử thứ 6): generator mask `|y| ≤ 5,0 m` và
   `0,15 m ≤ z − road_z ≤ 3,0 m` — đúng mask vế thật T4. JSON xuất cả
   `depth_profile_masked` (**dùng cho tiêu chí**) và `depth_profile_unmasked` (chẩn đoán).
2. **`depth_at_mass` trả BIÊN PHẢI** của bin (trước trả biên trái ⇒ lệch 0–2 m, đủ làm
   tiêu chí (b')(ii) ≤25 % trượt oan). JSON có cả `*_masked_bin_m: [trái, phải]`.
3. **`measure_speed` bỏ default hard-code**: `spawn_scale`/`radius_sigma`/`streak_scale`
   giờ `None` → đọc từ `PlumeStateConfig` (streak mặc định 0,0; ai gọi trực tiếp không
   bật lại streak).
4. **Một nguồn `rear_x`**: `VEHICLE_BOX_LENGTH_M = 6,8` ⇒ rear = 20 − 3,4 = **16,6 m**
   (trước hộp sinh dùng 6,8 còn box đo dùng half = 3,5 ⇒ lệch 0,1 m).

Ghi chú R3 #4 (test `points_per_cluster`): đổi cận dưới **14 → 12** là **chủ đích**, không
phải nới ngưỡng — đổi nguồn từ SSPP sang static Δ=1,0 (`ppf/cpf` = 25,4/13,3/12,3 ⇒ dải
12–26), và đại lượng `points_per_cluster_median` chỉ mô tả **tầng materialised**
(`PlumeTransform` bỏ các điểm `ring=-1`), **không ảnh hưởng `det/frame`**.

**Smoke 1 seed × 10 frame sau QĐ11 `[ĐO]`** (chưa phải nghiệm thu):

| km/h | masked đ/frame | p50 (biên phải) | p90 | ngoài 60 m | bin đỉnh (masked) | unmasked đ/frame |
|---|---:|---:|---:|---:|---|---:|
| 50 | 77,4 | 4 m | 16 m | 0,0 % | **0–2 m: 31,7** · 14–16: 12,9 · 2–4: 12,4 | 77,4 |
| 100 | 176,0 | 16 m | 38 m | 0,2 % | **2–4 m: 17,7** · 14–16: 14,2 · 4–6: 13,1 | 177,7 |
| 130 | 199,2 | 16 m | 34 m | 2,5 % | **12–14 m: 27,7** · 14–16: 23,8 · 16–18: 16,4 | 201,8 |

`[SUY LUẬN]` Ở 50 km/h mass bám sát đuôi (bin 0–2 m) như kỳ vọng của slab `|v|·Δt`. Ở
100/130 km/h profile **hai đỉnh**: gần đuôi và dồn thêm ở 12–16 m — đúng hệ quả vật lý của
drag (cụm giảm tốc ⇒ mật độ không gian ∝ 1/v ⇒ tích tụ về cuối đời), không phải bug.
**Trọng tài cuối cùng là profile thật của T4**: nếu thật cũng dồn về xa thì generator đúng;
nếu thật dồn gần đuôi thì mô hình drag/lifetime paper không khớp dữ liệu này — ghi phát hiện,
không sửa công thức paper.

## 7.5 QĐ12 — khôi phục paper Eq. 1: tan xác suất, T tất định `[ĐO]`

Sau khi chứng minh trail @50 km/h dài 16 m là do **chuỗi artifact code** (ttl ~
`N(0,2; 0,2)` × cắt cứng `4·ttl` — cả hai `[CODE]`, xem §7.4), Lead chốt QĐ12:

1. **Bỏ cắt cứng** `age > 4·ttl`: mỗi bước cụm sống với xác suất `P = exp(−Δt/T)`
   (paper Eq. 1: *P(còn tồn tại sau t) = exp(−t/T)*). Giữ trần **số học** `12·T`
   (`exp(−12) = 6e−6`, ảnh hưởng < 1 cụm/10^5) — ghi rõ "trần số học, không phải mô hình".
2. **`LIFETIME_SIGMA_S = 0,0`**: paper cho T là hàm **tất định** của tốc độ + màng nước;
   σ = 0,2 s là `[CODE] std_time_constant` của reference impl.
3. Hệ số tích luỹ đổi thành `K = 1/(1−exp(−Δt/T))` (tổng cấp số nhân vô hạn);
   `steady_state_alive_factor` giờ **bằng** `K`; `rate = visible/K`.
   `_CLUSTER_VISIBLE_BY_SPEED` **không đổi** — nó định nghĩa số cụm sống, và
   alive đo lại = 9,4 / 32,2 / 29,6 vs bảng 9,04 / 35,86 / 33,08 (lệch 10–11 %,
   là nhiễu 120 frame của K lớn; **không** phải lỗi 4×).

**Smoke sau QĐ12 (1 seed × 10 frame, bin 2 m — đúng cách T4):**

| km/h | điểm/frame gen | đích T4-final (a) | trail90 gen | trail90 thật | %mass≤20 gen | %mass≤20 thật |
|---|---:|---:|---:|---:|---:|---:|
| 50 | 145,4 | 99,0 (⚠ nhiễm thân xe, xem §7.7) | 2 m | 6,0 m | 100,0 % | 99,6 % |
| 100 | 483,4 | 203,2 | 20 m | 44,0 m | 92,9 % | 54,0 % |
| 130 | 461,6 | 208,6 | 30 m | 52,0 m | 58,3 % | 25,7 % |

⇒ QĐ12 đúng hướng về **cơ chế** (trail @50 16 → 2 m, hết artifact), nhưng trail vẫn **ngắn
hơn thật ~2×** ở 100/130 ⇒ **chưa** hiệu chỉnh `p_det_scale` (sẽ đóng băng trail sai).

## 7.6 Lưới độ nhạy `(wfh_mm, |C|)` → trail90 `[ĐO]`

Lead giao kiểm tra: có tổ hợp **có nguồn vật lý** nào khớp trail90 thật **6,0 / 44,0 / 52,0 m**
không. `wfh_mm` = điều kiện đo thật (R2: `itr_after_water ∈ {1,3,5}` ⇒ 1–5 mm);
`|C|` quét 0,15 (paper) / 0,30 / 0,50 (**phân tích độ nhạy**, chưa đổi default).
Script tạm: `.scratch/tmp/trail_grid.py`; 1 seed × 10 frame/ô, warmup 260 frame.

**Lưu ý API `[ĐO]`:** `PlumeContext` hiện **chặn cứng `wfh_mm ≤ 1,2`**. Để chạy lưới
wfh 2/3/5 như yêu cầu, script tạm **bỏ validation trong tiến trình phân tích** (không sửa
`spray/`). Nếu kết luận cần wfh > 1,2 thật thì phải mở lại API/ADR.

| wfh (mm) | \|C\| | trail90 50 km/h | trail90 100 km/h | trail90 130 km/h |
|---:|---:|---:|---:|---:|
| 1 | 0,15 | 2,0 | 20,0 | 26,0 |
| 1 | 0,30 | 4,0 | 20,0 | 24,0 |
| 1 | 0,50 | 4,0 | 22,0 | 22,0 |
| 2 | 0,15 | 2,0 | 22,0 | 34,0 |
| 2 | 0,30 | 2,0 | 24,0 | 28,0 |
| **2** | **0,50** | **6,0** | 28,0 | 26,0 |
| 3 | 0,15 | 4,0 | 26,0 | **38,0** |
| 3 | 0,30 | 4,0 | 26,0 | 38,0 |
| 3 | 0,50 | 4,0 | 30,0 | 24,0 |
| 5 | 0,15 | 2,0 | 28,0 | 28,0 |
| 5 | 0,30 | 2,0 | 30,0 | 28,0 |
| 5 | 0,50 | 4,0 | **34,0** | 28,0 |
| **THẬT** | — | **6,0** | **44,0** | **52,0** |

`[SUY LUẬN]` **Không ô nào khớp cả 3** (kết cục **iii** của Lead):
- @50: hai ô khớp (wfh 2/|C|0,5 cho đúng 6,0 m; wfh1/0,3–0,5 cho 4 m — trong 1 bin).
- @100: tốt nhất **34 m** (wfh5/0,5) vs 44 m = 0,77×; @130: tốt nhất **38 m**
  (wfh3/0,15–0,30) vs 52 m = 0,73×. Ngay cả **wfh = 5 mm = 4,2× trần API** cũng không tới.
- Tăng |C| (0,15 → 0,50) **không kéo dài** trail (thậm chí ngắn hơn ở 130 vì cụm dừng nhanh
  hơn ⇒ ít điểm ở xa); tăng wfh kéo dài nhưng **bão hoà ~30–38 m**.

**Vì sao bão hoà — đo trực tiếp (wfh=2, |C|=0,15, 130 km/h):** tâm cụm alive có depth
p50/p90/max = **35,5 / 142,4 / 378 m** (mô hình paper tạo trail cụm RẤT dài), nhưng
**detection-visible** depth p90 chỉ **12,3 m**, p99 47,7 m. Nguyên nhân: cụm ở xa (range
30–100 m) là quả cầu bán kính 0,31 m ⇒ chỉ vài tia cắt × `P_det ~0,1` ⇒ **<1 detection/cụm**;
profile đếm điểm nên mass xa gần như biến mất. Dữ liệu thật ở cùng độ sâu có **26 điểm/cụm**
(dạng chuỗi) nên vẫn hiện. ⇒ Giới hạn trail-visible của ta nằm ở **số điểm/cụm** (đại lượng
`p_det_scale` sẽ chỉnh), **không** ở lifetime/drag ⇒ đổi (wfh, C) là thuốc sai.

## 7.7 Bài học phương pháp

1. **Nhiễm thân xe `[ĐO]`:** ở 50 km/h, **68,1 %** detection trong vùng ±5 m / 0–3,0 m nằm ở
   dải cao 1,2–3,0 m = **thân xe Crafter (cao 2,6 m)**; cắt cao độ 1,2 m làm det/frame
   99,0 → **31,6**. ⇒ target (a) @50 của vùng đo rộng là **số rác**; phải **loại hộp 3D thân xe
   bằng hình học** (không chỉ cắt độ cao, vì plume thật cao tới 2,1 m). Trail90 ổn định
   (6,0 → 8,0 m khi cắt chặt) nên trail/profile vẫn dùng được.
2. **Bất đối xứng bộ lọc đã biết và chấp nhận:** pipeline T4 lọc `intensity ≤ 2`; generator
   **không có intensity** (mọi điểm là spray) nên không mô phỏng filter này — tương đương
   về ý nghĩa, **không** thêm filter giả.
3. **Kiểm tra công thức drag `[ĐO]`:** `PlumeState.advance` áp `v += C·v̂_air·|v_air|²·dt` trong
   **hệ ground** (v_air = v − wind, wind 2 m/s); với C = −0,15 ⇒ `dv/dt = −0,15·|v_air|·v_air`,
   đúng dấu và đúng hệ quy chiếu paper; drag **không** trừ ego (đúng: ego chỉ trừ khi tích phân
   vị trí). Không có bug dấu/hệ.
4. **Giới hạn API:** `wfh_mm` bị chặn `0 < wfh ≤ 1,2` — nếu R2 chốt wfh điều kiện đo > 1,2 thì
   phải mở lại validation (hiện chỉ phân tích bằng bypass tạm).

## 7.8 `p_det_scale` — quét sau QĐ12, trên target (a) MỚI `[ĐO]`

Target (a) mới (T4 §5b, bộ `geom` — loại hộp 3D thân xe bằng hình học):
**85,1 / 202,6 / 208,9 điểm/frame**; trail90 **6,0 / 44,0 / 52,0 m**; %mass≤20
**99,5 / 53,8 / 25,7 %** (50/100/130). `p_det_scale` = hệ số nhân P_det (mặc định 1,0).

Quét 2 seed × 60 frame, config QĐ12 + QĐ11 + bán kính 0,31/σ0,72/clip 2,0, streak 0:

| `p_det_scale` | 50 km/h | 100 km/h | 130 km/h | trail90 50/100/130 |
|---:|---:|---:|---:|---|
| 1,00 | 122,7 | 861,2 | 826,1 | 3 / 22 / 26 m |
| 0,44 | 58,3 | 406,2 | 386,7 | 3 / 22 / 26 m |
| 0,20 | 27,6 | 189,8 | 179,6 | 3 / 22 / 26 m |
| **0,22** | **30,2** | **208,6** | **197,0** | 3 / 22 / 26 m |
| 0,10 | 13,6 | 95,5 | 89,8 | 3 / 22 / 26 m |

`[SUY LUẬN]`
1. Quan hệ **không tuyến tính** (P_det bị clamp `min(1, lognormal·scale)`): 1,00 → 0,44 chỉ
   giảm det ~2,1× ở 100/130 (không phải 2,3×), còn 0,44 → 0,22 giảm đúng ~2×.
2. **Không một `p_det_scale` nào khớp cả 3**: để khớp target cần ~0,6–0,7 @50 nhưng
   ~0,22 @100/130. Ở `s = 0,22`: det/đích = **0,35 / 1,03 / 0,94**.
3. **trail90 KHÔNG đổi** (3 / 22 / 26 m) suốt dải `s` = 0,10–1,00 ⇒ `p_det_scale` **không**
   sửa được hình dạng profile; (b') không thể pass bằng núm này — xác nhận kết luận (iii) ở §7.6:
   giới hạn nằm ở cấu trúc cụm (quả cầu rời, ít điểm ở xa), không ở lifetime/drag/P_det.

**Đề xuất (chờ Lead chốt):** ưu tiên 100/130 như Lead đã nói ⇒ `p_det_scale ≈ 0,22`; @50 sẽ
là 0,35× target (trượt (a)) và **không thể** sửa bằng một số chung. Chưa bake vào default
(`RaycastConfig.p_det_scale` vẫn 1,0; chỉ có qua CLI) để chờ quyết định.

## 7.9 QĐ13 — cơ chế TÁN XẠ (mở rộng NGOÀI paper, user duyệt) `[ĐO]` / `[CHỌN]`

**Mô hình (Lead chốt, user duyệt):** bán kính cụm nở theo độ sâu đã rơi lại phía sau mặt đuôi:
`r(t) = r₀ + α·d_rel(t)`, `r₀` = lognormal paper (median 0,31 / σ 0,72),
`d_rel` = độ sâu cụm sau mặt đuôi (ego frame). Một α dùng chung cho 3 tốc độ.
`RADIUS_MAX_M` nâng **2,0 → 4,0 m** (clip **số học theo max quan sát**, không phải paper).
Căn cứ khai báo: paper §III-B định nghĩa `r_cl` = *khoảng cách xa nhất từ tâm cụm tới detection* —
đại lượng **đo được ở nhiều tuổi plume**; mô hình hoá tường minh sự nở theo tuổi là nhất quán với
định nghĩa đó, và khuếch tán rối làm đám sương nở theo quãng đường. **Đây là mở rộng ngoài paper**
(ADR sẽ ghi rõ), mặc định `diffusion_alpha = 0,0` (tắt) cho tới khi chốt α.

Cài đặt: `PlumeStateConfig.diffusion_alpha`, `SprayCluster.radius0/rear_point/forward`,
cập nhật trong `advance()`; CLI `--diffusion-alpha`. `pytest` 208 passed.

**Quét α (2 seed × 60 frame, `p_det_scale = 1,0`, các tham số khác giữ nguyên):**

| α | det 50 | det 100 | det 130 | trail90 50 | trail90 100 | trail90 130 |
|---:|---:|---:|---:|---:|---:|---:|
| 0,00 | 128,5 | 855,8 | 826,0 | 3 m | 23 m | 26 m |
| 0,03 | 136,4 | 2517,7 | 2383,4 | 3 m | 26 m | 31 m |
| 0,06 | **144,4** | **4775,9** | **4552,0** | 3 m | **26 m** | **30 m** |
| 0,10 | — | — | — | — | — | — |

α = 0,10 **không chạy xong** (>10 phút, phải dừng): sphere bán kính 1,5–4 m làm số giao tia bùng nổ
(chi phí raycast tăng hàng chục lần) — bản thân điều đó đã là dấu hiệu mô hình không dùng được.

`[SUY LUẬN]` **α không kéo trail90 tới đích, nhưng làm det bùng nổ** (α=0,06: det 4776 vs đích 203
= **23×**; trail90 vẫn 26 m vs đích 44 m). Chẩn đoán trực tiếp ở 100 km/h, α=0,06:
- Cụm alive: 39,4; depth p90 = **66,9 m**; **34,5 %** cụm ở depth > 26 m với radius p50 = **3,0 m**
  ⇒ population xa **có tồn tại** và đã được làm to.
- Nhưng **44 % tổng detections** nằm ở depth 16–20 m (sát/cạnh cảm biến, range 0–3 m) vì cụm
  radius ~1,3–1,5 m ở range ~1–3 m phủ **hàng trăm tia**; mass xa chỉ ~10 %.
- Nguyên nhân gốc: raycast đếm **giao tia × mặt cầu**, nên một quả cầu lớn ở gần sensor cho số điểm
  **không vật lý** (real plume bị giới hạn bởi mật độ hạt, không phải bởi số tia). Nở bán kính làm
  số điểm near-field tăng theo **góc khối** (∝ r²/R²) nhanh hơn far-field ⇒ **ngược** tác dụng cần.
- Vì vậy **không tồn tại cặp (α, s) khớp cả 3** trong dải α đã thử; theo luật Lead: **DỪNG, báo bảng,
  không thêm bậc tự do thứ ba**. α mặc định vẫn 0,0 (QĐ13 core đã cài, chưa bật).

## 7.10 QĐ14 — instrument phải mô phỏng ĐÚNG kịch bản static `[ĐO]`

**Lần lệch toán tử thứ 7 (và là lần thứ hai ở "bối cảnh"):** instrument cũ cho ego và xe
chạy **cùng tốc độ, cách nhau 20 m** ⇒ plume trôi ngược **xuyên qua sensor**: 44 % detections
ở depth 16–20 m = range 0–3 m, mass dồn near-field giả, nở bán kính làm det bùng nổ, và mọi
so sánh profile với static đều lệch.

**QĐ14:** ego **ĐỨNG YÊN**, xe đối tượng chạy **ra xa**; slab `|v|·Δt` sau **mặt đuôi hiện
tại**; đo trong ego frame; profile bin 2 m 0–60 m; mask ±5 m / 0,15–3,0 m; loại điểm trong
**hộp 3D thân xe** (Crafter 7,0×2,4×2,6 + margin 0,2, đúng `--body-box` của T4); loại điểm
range ≤ 4 m (NEAR_FIELD của T4). Đường chạy bắt đầu đủ xa để slab nằm ngoài 15 m, chạy tới
**200 m**.

**Tiền đề "dải 18–38 m" của QĐ14 bị bác bởi chính dữ liệu T4** `[ĐO]`: `roadspray_static_depth_profile.py`
không có cửa sổ `car_range` 18–38; nó dùng **mọi frame track-valid**, và `car_range` thực trong
`depth_signal_v2.jsonl` là p5/p50/max = 13/45/97 m @50 · 23/77/166 @100 · 33/103/207 @130.
Cửa sổ 18–38 là của **phép đo hộp cũ**; nếu chỉ mô phỏng 18→38 thì trail 44/52 m **mâu thuẫn
hình học** (quãng xe đi trong cửa sổ ≈ 20 m). Phát hiện này do R1, Lead xác nhận.

**Cửa kiểm QĐ14 đạt:** `range<15m` = **0,0 %** cả 3 tốc độ (trước 26,9 % ở 100 km/h);
cụm alive @100: depth p50/p90 = 10,4/42,9 m, chỉ **6,5 %** ở bin depth 16–20 m.

**Baseline α = 0 (2 seed):**

| km/h | điểm/frame | trail90 | %mass≤20 | CI95 | đích T4 geom |
|---|---:|---:|---:|---:|---|
| 50 | 10,3 | 2 m | 100,0 % | ±18,5 % | 85,1 / 6 m / 99,5 % |
| 100 | 34,3 | 24 m | 86,6 % | ±19,6 % | 202,6 / 44 m / 53,8 % |
| 130 | 45,4 | 40 m | 70,2 % | ±15,8 % | 208,9 / 52 m / 25,7 % |

`body-removed`: 15,8 / 11,9 / 4,5 % (T4: 14,0 / 0,3 / 0,1 %) — cùng bậc @50; cao hơn ở
100/130, ghi nhận, chưa sửa.

## 7.11 QĐ13 thử lại trong bối cảnh đúng — và kết luận A3 `[ĐO]`

Sửa thêm một lỗi cài đặt QĐ13: mặt đuôi trong kịch bản static **dời theo xe**; `d_rel` phải
tính `(rear_birth − pos)·forward + v_rel·elapsed` (trước chỉ dùng rear_birth ⇒ depth âm ⇒
α vô tác dụng). Sau khi sửa, quét α (2 seed, `p_det_scale = 1,0`):

| α | det 50 | det 100 | det 130 | trail90 50 | trail90 100 | trail90 130 | %mass≤20 (50/100/130) |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0,00 | 10,3 | 34,3 | 45,4 | 2 | 24 | 40 | 100,0 / 86,6 / 70,2 |
| 0,03 | 10,9 | 85,3 | 158,9 | 2 | 41 | 49 | 100,0 / 65,3 / 49,7 |
| **0,06** | 11,2 | **148,3** | **249,4** | 2 | **43** | **49** | 100,0 / 59,3 / 46,9 |
| 0,08 | 11,8 | 183,1 | 287,4 | 2 | 41 | 49 | 100,0 / 59,8 / 47,3 |
| **ĐÍCH** | 85,1 | 202,6 | 208,9 | 6 | 44 | 52 | 99,5 / 53,8 / 25,7 |
| **tỉ lệ @α=0,06** | **0,13×** | **0,73×** | **1,19×** | **0,33×** | **0,98×** | **0,94×** | — |

`body-removed` không tăng theo α (50: 15,8→16,2 %; 100: 11,9→7,0 %; 130: 4,5→4,4 %) — không
phải hộp thân xe sai vị trí.

**Áp quy tắc quyết định của Lead:**
1. Không có α nào cho trail90 vào [0,7; 1,5]× đích **ở cả 3 tốc độ**: @50 kẹt **2 m = 0,33×**
   đích 6 m với mọi α ≤ 0,08 (α chỉ tác động qua `d_rel`, mà @50 `d_rel ≤ ~2 m`).
2. Tỉ lệ det span **0,13× → 1,19×** (9×) nên **không tồn tại một `p_det_scale`** đưa cả 3
   vào [0,7; 1,5]×.
3. ⇒ Theo luật Lead: **A3 không đạt**; không thêm bậc tự do.

**Nguyên nhân gốc @50 km/h `[SUY LUẬN]`:** `T = 0,02·wfh·(v−50)+0,2` là `[CODE]` dee.cpp:530;
tại **đúng 50 km/h** số hạng `(v−50)=0` ⇒ `T = 0,2 s` **bất kể wfh**, trail mô hình ≤ ~2 m.
Đích 6 m đòi `T_eff ≈ 0,5 s`. Paper chỉ định nghĩa T qua **Fig. 6** (provenance R2), không cho
công thức ⇒ **công thức [CODE] có thể sai ở tốc độ thấp** — đây là phát hiện cho cổng B,
không phải chỗ để thêm cơ chế. 100/130 km/h với α = 0,06 đã khớp cả det lẫn trail (0,73/1,19×;
0,98/0,94×); chỉ còn %mass≤20 @130 lệch (46,9 vs 25,7) và @50 hỏng.

---

# 8. VERDICT A3 — nghiệm thu 8 seed (2026-11-19) `[ĐO]`

**Cấu hình nghiệm thu:** `scripts/measure_plume_size_tail.py` kịch bản static QĐ14
(ego đứng yên, xe chạy ra xa), `diffusion_alpha = 0,06` (**đã bake default**, user duyệt),
`RADIUS_MAX_M = 4,0` (clip số học), bán kính lognormal paper 0,30/0,31 & σ 0,72,
`p_det_scale = 1,0` (**không hiệu chỉnh**), streak tắt.
8 seed / tốc độ; frame mỗi seed: **120 / 66 / 51** (50/100/130 — giới hạn bởi đường chạy
tới 200 m và cap 120); CI95 = bootstrap **theo seed** B=2000. Script:
`.scratch/tmp/a3_acceptance.py`; số liệu thô `.scratch/tmp/a3_acceptance.json`.

**Đích T4-final (bộ `geom`)**: điểm/frame **85,1 / 202,6 / 208,9**; trail90 **6 / 44 / 52 m**;
%mass≤20 **99,5 / 53,8 / 25,7 %**.

| km/h | điểm/frame ± CI95 | tỉ lệ (a) | trail90 | tỉ lệ | %mass≤20 | (a) | (b') trail | (b') profile | (c) | **verdict** |
|---|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---|
| 50 | **13,0 ±11,3 %** | **0,15×** | **2,2 m** | **0,38×** | 100,0 | ✗ | ✗ | ✗ (98,2 %) | ✓ | **FAIL** |
| 100 | **144,0 ±5,8 %** | 0,71× | **40,2 m** | 0,91× | 60,8 | ✓ | ✓ | ✗ (268 %) | ✓ | **FAIL** |
| 130 | **283,4 ±9,1 %** | 1,36× | **49,8 m** | 0,96× | 44,1 | ✓ | ✓ | ✗ (995 %) | ✓ | **FAIL** |

## 8.1 Kết luận: **A3 KHÔNG ĐẠT** theo pre-registration — đạt một phần

- **(a) điểm/frame**: đạt ở **100 và 130 km/h** (0,71× và 1,36× — trong [0,7; 1,5]);
  **trượt nặng @50** (0,15×).
- **trail90**: đạt ở 100/130 (0,91× / 0,96×); **trượt @50** (0,38×).
- **(c) CI95**: đạt cả 3 (5,8–11,3 % ≤ 25 %) ⇒ phép đo đủ ổn định, kết luận không do nhiễu.
- **(b') profile-shape**: **trượt cả 3**. Generator cho profile quá **phẳng** so với thật
  (mỗi bin ~4–6 %) trong khi thật dồn ở 18–20 m @100 và 24–30 m @130; near-field 0–8 m của
  ta cao hơn thật nhiều (4–5 % vs 0,4–2,5 % @130). Max lệch bin: 98 % / 268 % / 995 %.
  ⇒ Dù tổng điểm và trail90 khớp ở 100/130, **hình dạng phân bố vẫn sai** — đúng thứ (b')
  được tạo ra để bắt.

**Vấn đề định nghĩa (b') cần Lead chốt khi viết luận văn:** luật QĐ10 nói "so các bin có
**≥10 % mass thật**". Với 100/130 km/h **không bin nào đạt 10 %** (bin lớn nhất 9,86 % / 9,64 %)
⇒ đọc nguyên văn thì tiêu chí **rỗng/vacuous** (tự đạt). Bảng trên dùng fallback hợp lý: so
các bin chứa tới **90 % mass thật** (tức vùng profile có ý nghĩa). Nếu dùng nghĩa vacuous thì
100/130 sẽ "PASS" (b') một cách giả tạo — không nên. **Kiến nghị**: định nghĩa lại (b') =
"|gen_norm − real_norm|/real_norm ≤ 30 % cho các bin đến 90 % mass", giữ nguyên tinh thần.

## 8.2 Miền tin cậy

- **Dùng được: 100–130 km/h** cho (a)+(trail90)+(c). Trail @130 49,8/52 m và det 1,36× nằm
  trong dải; @100 det 0,71× (sát biên dưới) và trail 40,2/44 m.
- **Ngoài miền: ≤ 60 km/h.** Định lượng @50: trail mô hình **2,2 m vs thật 6,0 m (0,38×)**,
  det **0,15×**, profile lệch gần 100 % ở bin 2–6 m.
- **Nguyên nhân gốc `[SUY LUẬN]`:** `T = 0,02·wfh·(v−50)+0,2` là `[CODE]` dee.cpp:530; tại
  `v = 50` số hạng `(v−50) = 0` ⇒ `T = 0,2 s` **bất kể wfh**, trong khi dữ liệu đòi
  `T_eff ≈ 1,0 s` (trail 6 m). Paper chỉ định nghĩa `T` qua **Fig. 6**, **không** cho công
  thức ⇒ đây là **limitation của reference impl**, không phải bug của repo; **không** sửa T
  (đã chốt phương án B).

## 8.3 Hai mở rộng ngoài paper đã dùng (phải khai)

1. **Bỏ `streak`** (`streak_scale = 0,0`): cơ chế nối cụm thành vệt không có trong paper
   (R2 audit 49 tham số: PHẢI BỎ).
2. **Thêm tán xạ** `r(t) = r₀ + α·d_rel(t)`, **α = 0,06** — mở rộng ngoài paper,
   **user-approved 2026-11-19**; căn cứ: paper định nghĩa `r_cl` là đại lượng đo được ở
   nhiều tuổi plume (phân bố lognormal của paper là phân bố biên theo tuổi), khuếch tán rối
   làm đám sương nở theo quãng đường. α hiệu chỉnh từ trail90 static (6/44/52 m).

## 8.4 Ảnh hưởng downstream (cổng B)

- Cổng B **phải báo riêng theo nhóm tốc độ**. Ở **≤ 60 km/h**, augmentation sẽ **yếu hơn
  thực tế** (thiếu đuôi plume) ⇒ nếu Arm B không cải thiện ở nhóm tốc độ thấp, đó là
  **kỳ vọng từ limitation này**, không phải bằng chứng phản bác augmentation.
- Ở 100–130 km/h, generator khớp (a)+trail nhưng profile-shape còn phẳng hơn thật ⇒
  plume tổng hợp phân bố đều hơn thật; khi diễn giải FP theo độ sâu cần lưu ý.
- Kết luận A3 **không chứng minh** augmentation vô dụng — đó là việc của cổng C.

## 8.5 Tái lập

```bash
# nghiệm thu 8 seed (≈2,3 phút, kịch bản static QĐ14, α=0,06 default)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    .scratch/tmp/a3_acceptance.py
# hoặc chạy dụng cụ trực tiếp
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_plume_size_tail.py --seeds 8
# tests
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -m pytest tests -q
```

`[ĐO]` md5 (2026-11-19): `scripts/measure_plume_size_tail.py` = `134f723361cc12af74035859a24ef3be` ·
`spray/plume_state.py` = `8c3ae8cac572490c663b9aa8aab8af05` · `spray/plume.py` =
`086353341bfdf6e9840388bcba3af01e` · `spray/raycast.py` = `8c58faf81903f0369f12220ebf90f098` ·
`.scratch/tmp/a3_acceptance.py` = `83f249b8abc0c2ac201c7a536925ccff` · target T4
`.scratch/roadspray-cal/tmp/depth_signal_v2_summary.json` = `f1a187ab010746a33dea6879ab5cb774`.
