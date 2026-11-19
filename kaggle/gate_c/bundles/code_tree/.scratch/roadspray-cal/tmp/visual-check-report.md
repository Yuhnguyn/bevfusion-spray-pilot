# Báo cáo kiểm định bằng mắt — plume generator vs spray thật (2026-11-19)

**Người xem:** lead (model `zai-glm-5-3-flash`, có đầu vào hình ảnh — đã thay thế được agent
`visual-inspector` vốn bị harness cấp nhầm model `deepseek-v4-1-flash-1017` (mù ảnh) nên fail
giữa chừng; một agent độc lập thứ hai đang chạy lại để đối chứng, file của nó:
`visual-check-report-agent.md`).

**Ảnh đã xem (5/12):** `100kmh_t{1.8,3.0,3.6}`, `130kmh_t{0.6,1.8}` — trích từ clip
`plume_vs_real_{100,130}kmh_ray.mp4` (bản ĐÃ SỬA vẽ detections sau raycast).

---

## 1. REAL: spray thật nhìn như thế nào

**Vệt/băng sương dày và liền**, kéo dài theo phương x, từ ngay sau mũi ego (x ≈ −8 m) tới đuôi xe
(x ≈ 18 m) — dài **~25 m**, nhăn nhúm tự nhiên, dày nhất vùng gần ego, mỏng dần về đuôi xe.
Số điểm: 2015–2604 ở các frame đang xét (100: 2162/2015/2604; 130: 2571/2596). Không có một
frame nào "trống" trong 5 khung.

## 2. GENERATOR: plume sinh nhìn như thế nào

**Chấm đỏ rời rạc, thưa thớt**, chỉ xuất hiện ngay sau đuôi xe (x ≈ 9–21 m): 89 / 59 / 149 điểm
(100 km/h) và 14 / 13 điểm (130 km/h). Nhìn thấy rõ các **đoạn ngắn liền theo tia** (vết tích của
lưới tia — mỗi cụm giờ chỉ che được một ít tia), **không** còn cầu tròn như bản trước khi sửa, nhưng
**không tạo được băng liền**.

## 3. Trái vs phải trong cùng ảnh

- **Mật độ:** chênh **> 10×** ở mọi khung đã xem (2162/89, 2015/59, 2604/149, 2571/14, 2596/13) —
  khớp con số ở tầng raycast (thiếu 3,2–10× trung bình, tệ nhất ở frame dày).
- **Vị trí:** giống nhau về *tâm* (đều quanh y ≈ 0, sau đuôi xe) nhưng **độ dài khác hẳn**: thật
  trải ~25 m tới sát ego; sinh chỉ ~10 m ngay sau xe.
- **Điều "giả" mắt bắt được:** chấm generator đứng thành **chuỗi ngắn cách đều theo tia**
  (đúng cấu trúc lưới); thật thì nhăn nhúm, không theo lưới.

## 4. So 100 vs 130 km/h

REAL: **130 km/h dày hơn** ở khung tương ứng (2571–2596 vs 2015–2604 — cùng bậc nhưng 130 dày hơn
ở frame giữa). GENERATOR: **ngược lại — 130 km/h thưa hơn hẳn** (13–14 det so với 59–149).
⇒ **Ngược với kỳ vọng "càng nhanh càng nhiều"**: nguyên nhân là bán kính cầu theo bảng giảm còn
0,079 m ở tốc độ thấp... nhưng 130 km/h vẫn thưa vì **nh dieser cụm sống hơn** (rate không theo
kịp) + P_det vẫn hạ.

## 5. Kết luận của mắt

**KHÔNG giống** — mắt thường phân biệt ngay. Khác ba điểm chính: (i) mật độ chênh >10×,
(ii) độ dài plume ~10 m vs ~25 m — thật kéo **về phía và vượt ego**, (iii) texture: chấm theo lưới
tia vs đám nhăn tự nhiên. Form "băng sương liền mạch" của thật **không tạo được từ các quả cầu
riêng lẻ** — cần nhiều cầu nhỏ chồng liên tục dọc quỹ đạo (chuỗi) hoặc cơ chế hạt liên tục.

---

## Phụ lục — số liệu cùng tầng (raycast, từ scripts/measure_plume_size_tail.py)

| km/h | det/frame | thật | cụm/thật | %≥50đ / thật |
|---:|---:|---:|---:|---|
| 50 | 4 | 43 | 0,3 / 4,8 | 0 % / 15 % |
| 100 | 274 | 875 | 19,9 / 21,6 | 36 % / 82 % |
| 130 | 74 | 592 | 5,3 / 13,1 | 22 % / 83 % |


---

## 6. Đối chiếu với báo cáo của agent độc lập (visual-check-report-agent.md)

Agent kiểm định riêng 6/6 ảnh (ba khung 100 km/h + ba khung 130 km/h, đọc bằng `read_image`,
số điểm lấy từ tiêu đề panel). **Hai báo cáo khớp nhau hoàn toàn**, kể cả chi tiết:

| Mặt | Lead (5 ảnh) | Agent (6 ảnh) |
|---|---|---|
| REAL | băng đỏ liền −8→18 m, dày 2 015–2 604 đ | "vệt dài liền theo x, bám y≈0, rộng 1–3 m, kết cấu cục + đuôi tan" |
| GENERATOR | chấm rời 13–149 đ, gần xe | "chấm/đảo rời rạc, 13–171 đ, không frame nào tạo được vệt liền; KHÔNG có aliasing bó tia" |
| Chênh mật độ | > 10× mọi khung | **14×–184×, luôn > 10×** (100: 51/14/17×; 130: 184/177/42×) |
| Che phủ gần ego | thật dày ở x<5, sinh nhiều frame bỏ trống | "REAL luôn có cụm dày x<5; GENERATOR bỏ trống (đáng chú ý 130kmh_t1.8, t3.0)" |
| 100 vs 130 | thật cùng bậc; sinh **130 thưa hơn 6×** ↔ ngược | giống hệt (REAL ~2 000 đ cả hai; GEN ≈114 vs ≈18) |
| Điểm giống duy nhất | vị trí/độ sải x | "vị trí + hướng ngang đúng — điểm duy nhất giống" |

Ước lượng sống sót của agent: sinh giữ lại **0,5 %–7,4 %** (trung bình ~3 %) số điểm thật mỗi frame.

## 7. Kết luận tổng hợp (hai mắt + số đo cùng hướng)

**A3 KHÔNG CHỐT — FAIL ở tầng detector cả 3 tốc độ.** Trạng thái "2/3 PASS" hôm trước bị rút
(đo nhầm tầng vô hiệu). Bây giờ có dữ liệu nhiều chiều:

1. **Mất dày, không mất hình:** nơi plume sinh xuất hiện thì đúng chỗ (bám y≈0, sải x tương đương);
   mất的是 (i) mật độ (nhân hệ số sống sót 0,5–7 %), (ii) đoạn gần ego, (iii) tính liền của vệt.
2. **Cấu trúc "cụm" của thật là chuỗi đã GỘP:** 1 cụm ~1 000–2 500 điểm = nhiều đoạn cầu nhỏ chồng
   dọc hành lang niño bị DBSCAN nối thành một. Generator đặt cầu **đều và rời** ⇒ mỗi cầu là một
   cụm nhỏ; không bao giờ gộp thành băng.
3. **Số cầu sống không phải núm duy nhất:** ảnh hưởng det/frame = (số cầu) × (tia che mỗi cầu) ×
   P_det × survival(tuổi). Muốn khớp cả det/frame lẫn cụm/frame phải đóng vòng **simulate-and-match**
   ở tầng raycast, không phải tra bảng một tầng.
4. **Đảo chiều 130 < 100 ở tầng sinh** (≈18 vs ≈114 det) — tín hiệu lạ so với bảng (37,7 vs 25,7 cụm
   đích), cần truy: đáng lẽ 130 phải sinh nhiều nhất. Nghi vấn: đặc trưng trôi/tuổi thọ theo tốc độ
   trong instrument, hoặc `alive factor 4T/Δt` (73 ở 130) đang áp ngược vai trò.

## 8. Việc tiếp theo theo thứ tự tác động (đề xuất)

1. **Nguồn cầu CỐ ĐỊNH theo vật thể (bánh sau) + cầu coupon dọc quỹ đạo** — tái tạo "băng liền":
   cầu mới sinh gần cầu cũ của chu kỳ trước (không phải uniform trong hộp mỗi chu kỳ như hiện tại,
   cũng không phải knot ngẫu nhiên đã thử và thất bại ở turn trước). Mục tiêu: share trong cụm ≥50đ
   và đoạn gần ego xuất hiện tự nhiên khi cầu cũ trôi về ego đúng −v+drag.
2. **Hiệu chỉnh P_det / mật độ quay lại**: sau khi cấu trúc xong, chọn hệ số để det/frame ∈
   [0,7; 1,5]× thật (tiêu chí đã có trong measure_plume_size_tail.py — chạy lại là PASS/FAIL tự in).
3. **Truy hiện tượng 130 < 100** trước khi tin bất kỳ bảng tỉ lệ nào (mục 7.4).
4. Sau khi measure instrument PASS mới quay lại **A4 đã xong → cổng C** (không đổi: cổng C dùng
   PlumeTransform đường chuẩn, luôn đo tầng đúng).
