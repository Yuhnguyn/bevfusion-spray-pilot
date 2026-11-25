# Vì sao đuôi plume ngắn: `drag` paper chặn quãng đường, không phải `wfh`

Ngày 2026-11-25. Câu hỏi: khi user báo "profile độ sâu trượt nặng nhất, generator dồn mass
sát đuôi hơn thật", **đòn bẩy nào của generator điều khiển độ dài đuôi?** Trước khi hiệu
chuẩn phải biết cái này, nếu không sẽ tune nhầm tham số.

## Kết luận trước, chứng minh sau

**Độ dài đuôi bị chặn bởi `drag = −0,15 1/m` (`[PAPER]`, §III-C), không bởi `wfh`/`T`,
không bởi `spawn_scale`, không bởi `P_det(R)`, không bởi `radius_max_m`.**

Hệ quả: hiệu chuẩn độ dài đuôi **không thể** làm bằng cách chỉnh tham số vận hành — nó đụng
trực tiếp vào một hằng số paper. Đây là việc phải quyết ở tầng ADR, không phải tune.

## 1. `[ĐO]` `wfh` không điều khiển độ dài đuôi

Probe `.scratch/paper-faithful/probe_wfh_tail.py`: kịch bản static, ego đứng yên, xe ở
24 m chạy ra xa, 45 frame, seed 7. Quét `wfh` trong dải hợp lệ (bị chặn `0 < wfh ≤ 1,2 mm`
bởi `PlumeContextError`):

| km/h | wfh 0,3 | 0,7 | 1,0 | 1,2 | đích thật p50 / p95 |
|---|---|---|---|---|---|
| 100 p50 | 1,8 | 1,8 | 1,8 | 1,8 | **17,5 / 26,5** |
| 100 p95 | 17,9 | 17,9 | 17,9 | 17,9 | |
| 130 p50 | 3,7 | 3,7 | 3,7 | 3,7 | **20,5 / 29,5** |
| 130 p95 | 21,5 | 21,5 | 21,5 | 21,5 | |

`T` **có** đổi theo wfh: 0,50 → 1,40 s ở 100 km/h; 0,68 → 2,12 s ở 130. Nhưng kết quả
**không đổi một ly**. Vậy `T` không phải nút thắt.

## 2. `[ĐO]` `P_det(R)` cũng không điều khiển độ dài đuôi

Chạy `gen-static` với ba giá trị `PLUME_PDET_RANGE_EXPONENT` (0 / 0,22 / 2,0), dải
`car_x` [20,40), tỉ lệ p95 so với thật:

| km/h | b = 0 | b = +0,22 | b = +2,0 | thật p95 |
|---|---:|---:|---:|---:|
| 50 | 0,23× | 0,23× | 0,23× | 6,5 m |
| 100 | 0,36× | 0,36× | 0,36× | 26,5 m |
| 130 | 0,32× | 0,32× | 0,32× | 29,5 m |

`b = +2,0` là "quang học mỏng" đúng vật lý — vẫn không đổi p95. Đuôi thiếu **không phải**
do luật `P_det` theo cự ly.

## 3. `[ĐO]` Nguyên nhân: `drag` giết vận tốc trong 0,3 s

`drag = −0,15 1/m` áp như `v' = v·(1 − 0,15·v·dt)`. Từ `v0 = 27,8 m/s` (100 km/h):

| t | v | quãng đường |
|---|---|---|
| 0,1 s | 16,2 m/s | 1,6 m |
| 0,5 s | 7,4 m/s | 5,4 m |
| 1,0 s | 4,6 m/s | 8,2 m |
| 2,0 s | 2,7 m/s | 11,5 m |
| 3,0 s | 1,9 m/s | 13,7 m |

**Tổng quãng đường cả đời cụm < 20 m**, bất kể `T` dài bao nhiêu — vì vận tốc về 0 sau
~1 s. So với không drag: t = 1,5 s ⇒ 42 m; t = 3 s ⇒ 83 m.

Đây khớp với quan sát: p95 sinh = 9,5 m ở cả 100 và 130 km/h — **không phụ thuộc `T`**, vì
`T` không còn là biến giới hạn. Giới hạn là quãng đường drag cho phép.

## 4. Vì sao `wfh` không đổi gì dù `T` đổi

`T` chỉ điều khiển **xác suất sống** (`P_t = exp(−age/T)`) và **trần tuổi**
(`max_age_factor·T`). Nhưng cụm đã dừng ở ~14 m sau 3 s, nên dù sống 10 s nữa nó **không đi
thêm được** — detection vẫn nằm ở 14 m. `T` chỉ quyết định cụm **có còn tồn tại** để bị
raycast hay không, không quyết định nó **ở đâu**.

## 5. Hệ quả cho hiệu chuẩn

| đại lượng cần sửa | đòn bẩy hiện có | có không |
|---|---|---|
| số detection/frame | `spawn_scale` / bảng `_CLUSTER_VISIBLE_BY_SPEED` | **có**, nhưng ADR-0006 §5.7 cấm bù |
| độ dài đuôi | `drag` | **không** — đây là `[PAPER]` §III-C, hằng số |
| vị trí bắt đầu | vùng `spawn` (≥ 18 m) | **không** — đụng miền paper |
| near-field < 10 m | vùng `spawn` | **không** — cùng lý do |

⇒ **Không còn tham số tự do nào để hiệu chuẩn hình dạng plume.** Ba thứ cần sửa (đuôi,
near-field, vị trí) đều bị paper hoặc ADR khoá. Đây là lý do A3/A3-V "trượt" mãi không sửa
được bằng tune: **mô hình paper không có bậc tự do cho hình dạng đuôi.**

## 6. Câu hỏi mở, phải trả lời trước khi làm gì

Paper A §III-C cho `C = −0,15 1/m` **hằng số** — nhưng paper dùng nó để mô tả plume **sau
xe đang chạy ở tốc độ không đổi**, trong hệ quy chiếu nào? Nếu drag áp trong hệ **mặt đất**
(như code hiện tại) thì plume dừng so với đường — nhưng plume thật trong ảnh RoadSpray
**đi theo xe** (p50 = 17,5–38,5 m sau đuôi, tức nó trôi cùng chiều xe rồi tản ra).

Cần đọc lại paper §III-C để xác định:
- `C·v²` áp lên vận tốc **tương đối với không khí** (code hiện tại) hay **tương đối với xe**?
- Paper có nói plume trôi theo xe không, hay chỉ tản ra tại chỗ?

**Cho tới khi trả lời được, mọi đề xuất "đổi drag" đều là đoán.** Đây là việc đọc paper
trước, sửa code sau.
