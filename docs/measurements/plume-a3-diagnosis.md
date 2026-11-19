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
