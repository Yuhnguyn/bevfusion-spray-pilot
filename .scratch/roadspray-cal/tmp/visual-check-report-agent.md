# Báo cáo kiểm định bằng mắt — REAL spray thật vs GENERATOR det-sau-raycast

**Kiểm định viên:** agent có đầu vào hình ảnh (chỉ dùng `read_image`, không suy đoán từ bối cảnh, không đọc code).
**Số ảnh đã mở:** 6/6, tất cả đều là ảnh 2 panel BEV (trục x dọc 0→60 m, trục y ngang −22→22 m; trái = REAL, phải = GENERATOR).
**Ghi chú nguồn số liệu:** các con số N/M dưới đây là chữ in ngay trên tiêu đề từng panel trong ảnh (vd. "REAL — spray thật (1072 điểm)"), không phải số đo ngoài.

| Ảnh (file) | Nhãn cần tách | REAL (N) | GENERATOR (M) | Tỉ lệ N/M |
|---|---|---|---|---|
| 100kmh_t0.6.png | Crafter_dynamic/0060_2021-09-08-16-27-14_0 · frame 7/40 | 1 072 | 21 | ~51× |
| 100kmh_t2.4.png | …/0060_… · frame 25/40 | 2 320 | 171 | ~14× |
| 100kmh_t3.6.png | …/0060_… · frame 37/40 | 2 604 | 149 | ~17× |
| 130kmh_t0.6.png | Crafter_dynamic/0096_2021-09-08-17-49-24_0 · frame 7/40 | 2 571 | 14 | ~184× |
| 130kmh_t1.8.png | …/0096_… · frame 19/40 | 2 306 | 13 | ~177× |
| 130kmh_t3.0.png | …/0096_… · frame 31/40 | 1 145 | 27 | ~42× |

---

## Câu 1 — REAL: hình dạng spray thật

- **Hình dạng chung:** spray thật là **vệt dài liền (băng đỏ liên tục) chạy theo phương x, bám sát y ≈ 0** (chiều rộng y chỉ ~1–3 m), kéo dài từ gần ego (x ≈ −6 m, tức phía sau gốc tọa độ) đến khoảng x ≈ 15–17 m. Bên trong vệt có kết cấu cục (clumpy): có chỗ đặc như khối đặc (vd. 100kmh_t2.4 trái: khối đỏ đặc từ x ≈ −6 đến x ≈ 15), có chỗ thưa dần về phía đuôi (phía gt box). Không thấy red nào thật sự dày phía sau x ≈ 20 (ngay cạnh/vượt gt box) ngoài vài chấm lác đác chạm mép trái box.
- **Diễn biến theo frame:**
  - 100kmh_t0.6 — vệt liền 1 khối chính x ≈ 2→17, đầu trái thưa vài chấm rời (x ≈ −2…3). Nhỏ nhất trong 6 ảnh: **1 072 điểm (ít nhất)**.
  - 100kmh_t2.4 — **dày và liền nhất ở chuỗi 100 km/h (2 320)**: băng đỏ gần như đặc, phủ x ≈ −6→15.
  - 100kmh_t3.6 — **nhiều điểm nhất trong 6 ảnh (2 604)**: cụm đặc to gần ego (x ≈ −6→0) + các cụm rời (x ≈ 3, 10, 14–17); spray đang tan, phần lớn đã tụt lại gần xe.
  - 130kmh_t0.6 — băng liền dày x ≈ −6→17 (2 571), tương tự 100kmh_t2.4.
  - 130kmh_t1.8 — băng liền x ≈ −6→15 (2 306), cụm dày gần ego, thưa dần về đuôi.
  - 130kmh_t3.0 — đã tan mạnh: chỉ còn cụm đặc nhỏ sát ego (x ≈ −6→0) + cụm nhỏ x ≈ 4–5 và vài chấm tại x ≈ 21 cạnh mép box (=**1 145, ít nhất chuỗi 130**).
- **Trả lời ngắn:** spray thật = vệt dài liền theo phương x, kèm cấu trúc cục con và độ đậm giảm dần theo tuổi vệt. **Nhiều nhất: 100kmh_t3.6 (2 604); ít nhất: 100kmh_t0.6 (1 072).**

## Câu 2 — GENERATOR: plume sinh nhìn như gì

- **Kiểu hình tổng thể:** ở **không frame nào** plume sinh tạo được vệt liền. Đó là **các chấm/cụm chấm nhỏ rời rạc** (mỗi cụm cỡ vài điểm, vài pixel), xếp dọc theo y ≈ 0 trong dải x ≈ 6→18 (gần trùng hướng với vệt thật nhưng chỉ chiếm những "đảo" nhỏ).
- **Theo ảnh:**
  - 100kmh_t0.6 (21 điểm): vài chấm + 2 gạch ngang ngắn; nhìn như **các vạch nhỏ thẳng hàng theo phương x**, không phải plume.
  - 100kmh_t2.4 (171 điểm): nhiều nhất trong 100 km/h: cụm tại x ≈ 6–8, 12, 15, 17 — **đảo rời rạc, khoảng cách không đều**, có cụm hơi kéo dãn theo x (như gạch ngang) nhưng không tạo băng liền.
  - 100kmh_t3.6 (149): cụm tại x ≈ 7, 13, 17 + 1 chấm sát mép trái box — tương tự.
  - 130kmh_t0.6 (14) và 130kmh_t1.8 (13): **gần như rỗng**, chỉ 1–3 chấm bé li ti (x ≈ 14–20, quanh mép box).
  - 130kmh_t3.0 (27): vài cụm nhỏ x ≈ 12, 17–18; 1 cụm chạm mép trái box.
- **Có "bó"/cấu trúc lặp·dt nguy hiểm mắt không?** **Không thấy** aliasing kiểu bó tia, nan hoa, hay chu kỳ lặp dt điểm-mỗi-frame; khoảng cách giữa các cụm không đều đặn một cách cơ học, nên không đánh lừa mắt theo hướng đó. **Nguy hiểm nằm ở chiều ngược lại:** plume quá thưa đến mức như nhiễu ngẫu nhiên/trống trải — mắt chỉ thấy vài chấm, không đọc ra "quả cầu cụm nào" đang được bắn tia.
- **Trả lời ngắn:** plume sinh = **chấm và cụm chấm rời rạc, thưa thớt**, có gợi ý hướng x nhưng không liền vệt; không có cấu trúc lặp dt đáng chú ý.

## Câu 3 — Trái vs phải trong CÙNG ảnh

- **Chênh lệch mật độ đỏ:** tất cả 6 ảnh đều **chênh >10×** (tính theo số điểm in trên tiêu đề: 14×, 17×, 42×, 51×, 177×, 184×; theo mắt, diện tích đỏ panel phải chỉ chiếm khoảng 1–5% panel trái). Không có ảnh nào "cùng bậc" hay chỉ chênh 2–5×.
- **Vị trí vùng đỏ:** **khớp ở mức thô** — cả hai panel đều đặt đỏ quanh y ≈ 0, chủ yếu x ≈ −6→18, không tràn ra y ngoài ±3 m hay x > 28. Nhưng ở mức tinh: panel phải **bỏ trống phần gần ego (x < 5)** ở nhiều frame (đặc biệt 130kmh_t1.8, 130kmh_t3.0, 100kmh_t0.6 còn ít chấm gần ego) trong khi REAL luôn có cụm dày vùng này; các đảo đỏ của generator rơi rải trong lòng vệt thật chứ không phủ kín.
- **Độ dài vùng đỏ:** độ giãn theo x của tập đỏ hai panel **gần giống nhau** (cùng cỡ ~15–20 m), tức generator đặt plume đúng tầm dài; nhưng vì mật độ tụt quá sâu, "độ dài" đó không còn ý nghĩa thị giác — nhìn vào panel phải không thấy vệt dài, chỉ thấy vài chấm.
- **Trả lời ngắn:** cùng vị trí thô, cùng sải dài, nhưng **mật độ chênh >10× ở cả 6 ảnh**.

## Câu 4 — 100 km/h vs 130 km/h

- **REAL:** trung bình 100 km/h ≈ (1072+2320+2604)/3 ≈ **2 000 điểm**; 130 km/h ≈ (2571+2306+1145)/3 ≈ **2 007 điểm**. Hai chuỗi **xấp xỉ bằng nhau**; 130 chỉ nhỉnh hơn ở frame đầu (2571 > 1072) và thua ở frame cuối (1145 < 2604). → Không có xu hướng "càng nhanh càng nhiều đỏ" ở REAL (ít nhất trên 6 cặp frame này — cần lưu ý 2 chuỗi lấy từ thư mục/clip khác nhau nên còn phụ thuộc nội dung từng frame).
- **GENERATOR:** 100 km/h ≈ (21+171+149)/3 ≈ **114 điểm**; 130 km/h ≈ (14+13+27)/3 ≈ **18 điểm**. → 100 km/h sinh ra **nhiều đỏ hơn ~6×**, tức xu hướng bị **đảo ngược** so với trực giác "càng nhanh càng nhiều".
- **Trả lời ngắn:** REAL — hai bên ngang nhau (không đúng "càng nhanh càng nhiều"); GENERATOR — 100 km/h nhiều hơn 130 km/h (cũng không đúng, thậm chí ngược chiều).

## Câu 5 — Kết luận

**Ở tầng det-sau-raycast, plume generator KHÔNG giống spray thật đến mức mắt thường khó phân biệt.** Ngược lại, trong cả 6 ảnh, mắt phân biệt ngay trong dưới một giây: panel trái có vệt đỏ dày đặc, panel phải gần như đen.

Khác biệt chính, xếp theo mức độ:

1. **Dày (thấp nhất):** chênh 14×–184×, luôn >10×. Đây là khác biệt quyết định — plume sinh thưa đến mức như rớt điểm, rất có thể do P_det gợi ý/diệt gần như toàn bộ điểm plume.
2. **Độ liền:** REAL là băng liên tục có kết cấu cục; GENERATOR là chấm/đảo rời rạc, không nối được thành vệt. Không nhìn thấy cấu trúc plume (mép cuộn, đuôi loang) nào ở panel phải.
3. **Che phủ gần ego:** REAL luôn có cụm dày tại x < 5; GENERATOR nhiều frame bỏ trống hoàn toàn vùng này (đáng chú ý ở 130kmh_t1.8, 130kmh_t3.0, 100kmh_t0.6).
4. **Độ dài/sải x:** điểm duy nhất gần đúng — tập đỏ generator giãn cùng tầm ~15–20 m theo x và bám đúng hành lang y ≈ 0, tức vị trí thô và hướng vệt là ổn.
5. **Loại khác biệt KHÔNG xuất hiện:** không thấy bó tia, chu kỳ lặp dt, hay sắp xếp theo tia một cách máy móc; lỗi của plume là **thiếu điểm**, không phải "quá máy móc về hình học".

### Nhận định tổng

- **Vị trí + hướng đi ngang (x) của plume sinh là đúng**; sai ở **tỉ lệ sống sót qua P_det quá thấp** và ở **kết cấu liền mạc của vệt**.
- Trên dữ liệu này, chuỗi 130 km/h còn sinh ra ít đỏ hơn 100 km/h ở tầng det, ngược cả với số điểm thật (hai chuỗi REAL ngang nhau) và với trực giác tốc độ-cao→spray-nhiều.
- **Khuyến nghị cho bước Californication:** cần chỉnh tầng raycast/P_det (hệ số sống sót điểm plume), thêm độ phủ gần ego, và dựng lại độ liền của vệt (nội suy/nhóm cụm nhỏ) trước khi plume sinh có thể thay cho spray thật trong mắt (và mọi metric thị giác). Số điểm trên tiêu đề panel xác nhận: 1 072–2 604 điểm thật chỉ còn 13–171 điểm ở panel phải, tức giữ lại ~0,5%–7,4% mỗi frame (trung bình ~3%).

*Hạn chế của bản kiểm định: chỉ quan sát 6 ảnh (2 chuỗi, mỗi chuỗi 3 frame), không có số liệu gốc; số điểm lấy từ tiêu đề ảnh; kết luận về "càng nhanh càng nhiều" chưa khống chế được khác biệt giữa 2 clip nguồn.*
