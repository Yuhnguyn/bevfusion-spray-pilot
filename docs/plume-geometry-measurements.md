# Hình học plume: nhãn thật vs mô phỏng — đo theo thang tốc độ

Script: `scripts/measure_plume_geometry.py` (tất định, chạy lại cho cùng số).
Nhãn spray = giá trị `2` trong `labels/*.label` (README dòng 91–94).
Mô phỏng: `PlumeState` + `PlumeContext` với `wfh = 1,0 mm`, xe dẫn ở 20 m,
`dt = 0,1 s`, `ego_speed = object_speed` (đúng như metadata: hai giá trị bằng nhau
ở 207/207 scene).

## A. Nhãn thật — spray nằm ở đâu `[ĐO]`

2 scene mỗi mức tốc độ, tối đa 60 frame/scene:

| km/h | điểm spray/frame | range p5 / **med** / p95 (m) | elevation med | phân bố range |
|---:|---:|---:|---:|---|
| 50 | 65 | 3,39 / **3,84** / 20,57 | 7,14° | 54,2 % trong 2–4 m |
| 60 | 162 | 3,38 / **7,45** / 16,43 | 7,34° | 76,3 % trong 4–12 m |
| 70 | 471 | 3,41 / **8,16** / 14,79 | 9,54° | 74,9 % trong 6–12 m |
| 80 | 878 | 3,72 / **9,09** / 17,45 | 8,16° | 73,0 % trong 6–12 m |
| 90 | 1.059 | 3,69 / **8,33** / 15,92 | 8,08° | 71,5 % trong 6–12 m |
| 100 | 1.555 | 3,68 / **7,98** / 16,28 | 8,94° | 69,8 % trong 6–12 m |
| 110 | 1.399 | 3,66 / **8,17** / 17,45 | 8,24° | 69,2 % trong 6–12 m |
| 120 | 950 | 3,52 / **7,99** / 16,52 | 8,61° | 69,0 % trong 6–12 m |
| 130 | 807 | 3,38 / **7,35** / 15,73 | 9,18° | 63,8 % trong 6–12 m |

Ba tính chất quan trọng, đều **không** phụ thuộc tốc độ:

1. **Range median 7,3–9,1 m** ở mọi tốc độ ≥60; p95 **14,8–20,6 m**. Plume luôn nằm
   giữa ego và xe dẫn, cách cảm biến dưới 20 m, không phải một vệt dài hàng trăm mét.
2. **Elevation median 7,1–9,5°**, tức đám nước ở **cao hơn cảm biến ~0,9–1,4 m**
   (tại range 8 m: `8·tan(8°) ≈ 1,1 m`). Nước bắn lên từ bánh, không nằm sát mặt đường.
3. **Số điểm/frame không đơn điệu**: 65 → 1.555 (đỉnh ở 100 km/h) → 807 (130 km/h).

## B. Mô phỏng — cấu hình hiện tại sai ở tốc độ cao `[ĐO]`

90 frame, 30 frame cuối lấy trung vị:

| km/h | cụm sống | range med | p95 | elevation med |
|---:|---:|---:|---:|---:|
| 50 | **0** | — | — | — |
| 60 | 51 | 9,83 | 16,2 | 7,60° |
| 70 | 155 | 10,65 | 28,3 | 6,29° |
| 80 | 302 | 13,99 | 50,3 | 4,51° |
| 90 | 497 | 22,27 | 75,1 | 2,96° |
| 100 | 738 | 37,43 | 104,0 | 1,98° |
| 110 | 1.030 | 54,62 | 136,4 | 1,41° |
| 120 | 1.354 | 73,03 | 170,0 | 1,07° |
| 130 | 1.700 | **91,01** | **204,3** | **0,85°** |

**Lỗi 1 — vệt kéo dài vô hạn ở tốc độ cao.** Ở 130 km/h mô phỏng cho range median
**91 m**, thật là **7,35 m** (lệch **12×**), p95 204 m so với 15,7 m (lệch **13×**).

Nguyên nhân: `advance()` chỉ rút vận tốc cụm về **vận tốc gió (1,77 m/s)**, nên trong
hệ ego cụm rơi lại phía sau với tốc độ ≈ `v_ego`, suốt cả `4T` = 7,2 s. Quãng đường
tương đối = 36,1 × 7,2 ≈ 260 m. Luật xoá duy nhất hiện có là `age > 4T`.

**Lỗi 2 — plume nằm quá thấp.** Elevation median mô phỏng 0,85–7,60° (giảm khi tốc độ
tăng vì plume lan xa), thật 7,1–9,5°. Khối sau đuôi hiện đặt `z` từ mặt đường lên
1,5 m (đỉnh +1,09 m trong hệ cảm biến), trong khi nhãn thật cho z ≈ **1,2–1,4 m**.

## C. Sửa bằng hình học, không bằng hằng số `[ĐO]`

Thêm **một** luật: xoá cụm khi nó đã đi qua cảm biến (`pos[0] < 0`). Không đổi `T`,
không đổi `P_det`, không đổi `C`.

| km/h | cụm sống | range med | p95 | elevation med | nhãn thật: range med / p95 |
|---:|---:|---:|---:|---:|---:|
| 50 | **0** | — | — | — | 3,84 / 20,57 |
| 60 | 40 | 10,78 | 15,9 | 5,96° | 7,45 / 16,43 |
| 70 | 80 | 9,77 | 15,8 | 5,34° | 8,16 / 14,79 |
| 80 | 104 | 9,44 | 15,6 | 5,09° | 9,09 / 17,45 |
| 90 | 122 | 9,37 | 15,5 | 4,57° | 8,33 / 15,92 |
| 100 | 132 | 9,46 | 15,5 | 4,33° | 7,98 / 16,28 |
| 110 | 142 | 9,19 | 15,4 | 4,22° | 8,17 / 17,45 |
| 120 | 150 | 8,78 | 15,3 | 4,18° | 7,99 / 16,52 |
| 130 | 154 | 9,03 | 15,4 | 3,96° | 7,35 / 15,73 |

Sau khi thêm luật, range median **8,78–10,78 m** so với thật **7,35–9,09 m** (lệch
≤ 1,7 m), p95 **15,3–15,9 m** so với thật **14,8–20,6 m**. Sai lệch 12× biến mất, và
**không cần chỉnh một tham số nào của paper**.

Còn lại hai việc, cả hai đều có số:

1. **Nâng khối sau đuôi** để elevation median khớp 7,1–9,5°: khối hiện phủ 0–1,5 m trên
   mặt đường (đỉnh +1,09 m trong hệ cảm biến), cần phủ khoảng **1,1–1,9 m trên mặt
   đường** để med rơi vào 0,9–1,4 m như nhãn thật.
2. **Lỗ ở 50 km/h**: công thức `mean = (0,2·wfh + 0,1)(v − 50)` cho **0 cụm**, nhưng
   nhãn thật có **65 điểm/frame**. 24 scene (16,33 % frame) ở đúng 50 km/h sẽ **không
   được tăng cường gì**. Đây là xung đột dữ liệu ↔ công thức, đã ghi ở ticket 31, chưa
   quyết định.

## D. Hệ quả cho vòng sinh detection

Với `n_max` đo được và range thật 7–10 m: cụm bán kính 0,3 m tại 9 m chiếm **1,91°**,
tức `1,91/0,333 ≈ 5,7` mức elevation × `1,91/0,197 ≈ 9,7` bước phương vị ≈ **55 ô góc**.
Với `P_det ≈ 0,19`, mỗi cụm cho ~10 detection trước bước giữ echo mạnh nhất. 154 cụm
sống ⇒ cùng cỡ **807–1.555 điểm/frame** mà nhãn thật có. Nghĩa là trần
`max_injected_points = 2000` (lỗi D7) **không còn là nút cổ chai** khi hình học đã đúng.