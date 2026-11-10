# Hình học plume: nhãn thật vs mô phỏng — đo theo thang 50–130 km/h

Hai script, đều tất định, chạy lại cho cùng số:

| Script | Đo gì |
|---|---|
| `scripts/measure_plume_geometry.py` | vị trí 3D của cum mô phỏng vs điểm spray thật, theo từng mức tốc độ |
| `scripts/measure_spray_height.py` | độ cao điểm spray trên **mặt đường đã fit** (khử pitch/roll), quy ra % chiều cao box |

Nhãn spray = giá trị `2` trong `labels/*.label`. Mô phỏng: `PlumeState` + `PlumeContext`,
`wfh = 1,0 mm`, xe dẫn ở 20 m, `dt = 0,1 s`, `ego_speed = object_speed` (đúng metadata:
hai giá trị bằng nhau ở 207/207 scene).

## A. Nhãn thật — spray nằm ở đâu `[ĐO]`

2 scene mỗi mức tốc độ, tối đa 60 frame/scene:

| km/h | điểm/frame | range p5 / **med** / p95 (m) | elevation med | x p5 / **med** / p95 (m) | % điểm **sau** cảm biến |
|---:|---:|---|---:|---|---:|
| 50 | 65 | 3,39 / **3,84** / 20,57 | 7,14° | −7,8 / **+3,7** / 20,5 | 34,9 % |
| 60 | 162 | 3,38 / **7,45** / 16,43 | 7,34° | −10,5 / **−4,8** / 17,0 | 69,5 % |
| 70 | 471 | 3,41 / **8,16** / 14,79 | 9,54° | −13,5 / **−7,1** / 8,5 | 93,1 % |
| 80 | 878 | 3,72 / **9,09** / 17,45 | 8,16° | −12,2 / **+3,7** / 17,1 | 41,2 % |
| 90 | 1.059 | 3,69 / **8,33** / 15,92 | 8,08° | −14,3 / **−5,5** / 14,0 | 62,9 % |
| 100 | 1.555 | 3,68 / **7,98** / 16,28 | 8,94° | −15,5 / **−5,7** / 12,2 | 68,6 % |
| 110 | 1.399 | 3,66 / **8,17** / 17,45 | 8,24° | −15,4 / **−5,1** / 14,2 | 62,6 % |
| 120 | 950 | 3,52 / **7,99** / 16,52 | 8,61° | −14,0 / **−4,9** / 14,0 | 62,2 % |
| 130 | 807 | 3,38 / **7,35** / 15,73 | 9,18° | −14,2 / **−4,9** / 12,2 | 68,6 % |

Bốn tính chất, đều **không** phụ thuộc tốc độ:

1. **Range median 7,3–9,1 m** ở mọi tốc độ ≥60; p95 14,8–20,6 m. Plume luôn nằm trong
   20 m quanh cảm biến, không phải vệt dài hàng trăm mét.
2. **62–93 % điểm spray nằm SAU cảm biến** (`x < 0`), median `x ≈ −5 m`. Nước bắn ra từ
   bánh xe dẫn, rồi xe mang cảm biến **vượt qua** đám nước đó. Plume thật trải từ
   `x ≈ −14 m` (p5) tới `x ≈ +14 m` (p95), tức cả hai phía cảm biến.
3. **Độ cao trên mặt đường**: p5 **0,16 m** / med **1,51 m** / p95 **2,36 m**
   (n = 939.803 điểm, gộp 9 mức tốc độ) = **6,1 % / 57,8 % / 90,2 %** chiều cao box
   (2,6206 m). Nước bắn lên tới gần nóc xe, không nằm sát mặt đường.
4. **Bề ngang**: `|y|` p5 **0,06** / med **0,63** / p95 **2,31 m** — hẹp ở giữa, tản ra
   ±2,3 m.

Nhiệt độ nghiêng xe (pitch fit từ mặt đường) chỉ **+0,05…+0,12°** ⇒ phép đo elevation
không bị nhiễu pitch; hai khung "độ cao trên mặt đường" và "range" cho cùng kết luận.

## B. Mô phỏng hiện tại — sai ở tốc độ cao `[ĐO]`

90 frame, lấy trung vị 30 frame cuối. Cấu hình hiện tại: khối sau đuôi 0–1,5 m trên mặt
đường, chỉ xoá theo `age > 4T`.

| km/h | cụm sống | range med | p95 | elevation med | x med | % sau cảm biến |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | **0** | — | — | — | — | — |
| 60 | 51 | 9,83 | 16,2 | 7,60° | +8,1 | 21,8 % |
| 70 | 155 | 10,65 | 28,3 | 6,29° | +0,6 | 48,6 % |
| 80 | 302 | 13,99 | 50,3 | 4,51° | −9,5 | 65,5 % |
| 90 | 497 | 22,27 | 75,1 | 2,96° | −22,0 | 75,5 % |
| 100 | 738 | 37,43 | 104,0 | 1,98° | −37,2 | 82,1 % |
| 110 | 1.030 | 54,62 | 136,4 | 1,41° | −54,5 | 86,2 % |
| 120 | 1.354 | 73,03 | 170,0 | 1,07° | −72,9 | 88,7 % |
| 130 | 1.700 | **91,01** | **204,3** | **0,85°** | **−90,8** | 90,7 % |

**Lỗi 1 — vệt kéo dài vô hạn.** Ở 130 km/h range median **91 m** (thật 7,35 m, lệch
**12×**), p95 **204 m** (thật 15,7 m). Nguyên nhân: `advance()` chỉ rút vận tốc cụm về
**vận tốc gió 1,77 m/s**, nên trong hệ ego cụm rơi lại với tốc độ ≈ `v_ego` suốt
`4T` = 7,2 s ⇒ 36,1 × 7,2 ≈ 260 m. Luật xoá duy nhất hiện có là `age > 4T`.

**Lỗi 2 — plume nằm quá thấp.** Khối phủ 0–1,5 m (0–57 % chiều cao box), trung vị 28,6 %,
trong khi nhãn thật có trung vị **57,8 %**; elevation median mô phỏng **0,85–7,60°** so
với thật **7,1–9,5°**, và càng sai khi tốc độ tăng.

## C. Sửa bằng hình học, không bằng hằng số mới `[ĐO]`

Ba luật, mỗi luật lấy từ một số đo ở mục A. Không đổi `T`, không đổi `P_det`, không đổi `C`.

**(1) KHÔNG cắt cụm theo mét — để `n_max` tự dập đuôi.**

Bản đầu của mục này đề xuất cắt cụm khi `x < −15 m`. **Đề xuất đó đã bị bác bỏ** bằng phép đo
sau: tách scene chẵn/lẻ (hai tập không giao nhau), cùng mức tốc độ, đo lại p5 của `x`.

| km/h | p5 nửa A (m) | p5 nửa B (m) | lệch |
|---:|---:|---:|---:|
| 50 | +2,76 | −40,58 | 43,4 |
| 70 | −4,73 | −9,79 | 5,1 |
| 100 | −6,45 | −10,02 | 3,6 |
| 130 | −11,61 | −4,79 | 6,8 |

p5 dao động **−40,6 … +3,7 m** ⇒ không phải hằng số, không được dùng làm ngưỡng. Đo trên
**toàn bộ 24 scene mỗi mức** thì đuôi rất nhọn (130 km/h, n = 95.453 điểm): `[−20,−15)` có 693 điểm,
quá `−20 m` chỉ còn **62 điểm = 0,065 %**, xa nhất **−35 m**.

Cơ chế đúng để đuôi tự tắt: `n_max ∝ 1/d²`. Cụm bán kính 0,3 m có `n_max = 28` ô góc ở 20 m,
`n_max = 3` ở **~61 m**, `< 1` ở 200 m ⇒ dưới `minPts = 3` thì không thành cluster spray. Đây là
lý do **không** cần luật cắt, và cũng là lý do con số "cụm ở 91 m" không phải lỗi mô hình: nó là
số đo trên **vị trí cụm**, không phải trên **detection**.

Bảng dưới đây là kết quả **khi thử** cắt ở `−15 m` — giữ lại làm bằng chứng, **không dùng** làm
thông số:

| km/h | cụm sống | range med | p95 | elevation med | x p5 / med / p95 | % sau cảm biến | `\|y\|` p95 |
|---:|---:|---:|---:|---:|---|---:|---:|
| 60 | 50 | 9,63 | 15,8 | 5,96° | −7,8 / +8,5 / 15,7 | 19,5 % | 3,1 |
| 70 | 126 | 8,93 | 15,4 | 5,34° | −12,6 / +4,4 / 15,4 | 36,6 % | 3,3 |
| 80 | 177 | 8,68 | 15,2 | 5,09° | −13,0 / +2,9 / 15,1 | 41,1 % | 3,1 |
| 90 | 210 | 8,56 | 15,1 | 4,57° | −13,3 / +2,5 / 15,0 | 41,8 % | 2,9 |
| 100 | 231 | 8,51 | 15,0 | 4,33° | −13,2 / +2,4 / 14,9 | 42,9 % | 2,8 |
| 110 | 248 | 8,48 | 15,0 | 4,22° | −12,9 / +2,4 / 14,8 | 42,9 % | 2,6 |
| 120 | 264 | 8,26 | 14,8 | 4,18° | −13,3 / +2,4 / 14,6 | 42,7 % | 2,5 |
| 130 | 274 | 8,24 | 14,8 | 3,96° | −13,4 / +1,8 / 14,6 | 43,7 % | 2,4 |

Range median **8,2–9,6 m** (thật 7,3–9,1), p95 **14,8–15,8** (thật 14,8–20,6), `|y|` p95
**2,4–3,3 m** (thật **2,31 m**) — khớp, và bề ngang 3,4 m đang hardcode **đúng**, không
cần sửa.

**(2) Nâng khối theo chiều cao xe dẫn**, không theo mét tuyệt đối: khối phủ
**5 %–92 % chiều cao box** (với van 2,6206 m ⇒ **0,13–2,41 m** trên mặt đường).

| km/h | elevation med mô phỏng | elevation med nhãn thật |
|---:|---:|---:|
| 70 | 11,02° | 9,54° |
| 100 | 9,52° | 8,94° |
| 130 | 8,92° | 9,18° |

**(3) `wfh` độc lập với tốc độ** — không phải luật hình học mà là ràng buộc của paper:
`wfh` sample mỗi frame từ `exp(0,1…1,2) mm`, không suy từ `v`. Hiện **chưa có** chỗ nào
sample `wfh`: `PlumeContext` nhận `wfh_mm` từ ngoài, `from_sample()` chưa được nối vào
adapter nào. Cần một adapter dataset làm việc này trước khi chạy augmentation thật.

## D. Hệ quả cho vòng sinh detection

Với `n_max` đo được và range thật 7–10 m: cụm bán kính 0,3 m tại 9 m chiếm **1,91°**,
tức `1,91/0,333 ≈ 5,7` mức elevation × `1,91/0,197 ≈ 9,7` bước phương vị ≈ **55 ô góc**.
`P_det ≈ 0,19` ⇒ ~10 detection/cụm trước bước giữ echo mạnh nhất. 274 cụm sống ⇒ cùng cỡ
**807–1.555 điểm/frame** mà nhãn thật có. Trần `max_injected_points = 2000` (lỗi D7)
**không còn là nút cổ chai** khi hình học đã đúng.

## E. Ba chỗ PM nói sai, và số đúng

1. PM từng đề "nâng khối lên **1,1–1,9 m**". Con số đó suy từ `8·tan(8°)` ở **một** cự ly, chỉ là
   dải trung vị, không chuyển được sang xe khác. Số đúng — đo trực tiếp trên 939.803 điểm — là
   **5 %–92 % chiều cao box** (0,13–2,41 m với van 2,62 m), kiểm lại bằng elevation median (mục C(2)).
2. PM từng đề cắt cụm khi `x < 0`. Số đo mục A bác bỏ: **62–93 %** spray thật nằm ở `x < 0`
   (median `x ≈ −5 m`), nên `x < 0` là xoá đúng phần lớn nhất của plume.
3. PM sau đó đề cắt ở `x < −15 m`. Cũng **sai**: p5 giữa hai nửa scene dao động
   **−40,6 … +3,7 m** (mục C(1)). Kết luận cuối: **không cắt theo mét**; `n_max ∝ 1/d²` tự dập đuôi.

Bài học ghi vào playbook: một ngưỡng rút từ **một mẫu nhỏ** phải được kiểm lại trên **hai tập
scene không giao nhau** trước khi ghi vào tài liệu. Nếu không, nó là overfit chứ không phải số đo.