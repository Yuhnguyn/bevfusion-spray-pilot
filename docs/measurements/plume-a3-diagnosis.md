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
