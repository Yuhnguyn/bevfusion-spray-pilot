# 29: Bước 4–5 — ray casting, attenuation, strongest return

**Type:** task
**Status:** needs-triage
**Blocked by:** 27, 28
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ

`[PAPER]` §III-C: detection chỉ sinh khi **beam cắt** khối cầu, với xác suất `P_det`
lognormal median 0,10; beam xuyên plume bị suy giảm `0,02 m⁻¹`; cảm biến chỉ báo **echo mạnh nhất**.
`[CODE]` `dee.cpp:230–281`: `P = min(1, lognormal(μ=−2,3, σ=1,1))·e^(−age/T)`;
`attenuation = exp(−2·mean·L)`; `add_max_detection` trên mỗi beam.

v1 **không có** cả ba: nó phát thẳng điểm vào không gian, nên (a) mật độ không phụ thuộc hình học
beam, (b) không bao giờ làm mất tín hiệu của vật thật phía sau.

## Việc phải làm

1. `spray/beam_model.py` — nạp elevation từ **bảng đo** (không phải bảng hãng, xem
   `docs/plume-beam-table.md`); hàm giao tia × cầu (vector hoá, trả `(t0, t1)` hoặc rỗng).
   **Đã sửa 2026-11-11:** bản release chỉ còn **20 beam** (ring 0…19), bảng VLP-32C lệch median
   3,49° nên không dùng; bảng đo ổn định ±0,13–0,36° giữa 120 frame.
2. `spray/plume.py` — vòng lặp: cho mỗi beam thật (azimuth lấy từ scan), cho mỗi cụm:
   cắt → `P`; sample; sinh detection tại `N((t0+t1)/2, (t1−t0)/6)`.
3. Attenuation: cộng dồn `L` = tổng chiều dài tia trong các cụm **trước** điểm; nhân
   `e^(−2·0,02·L)` vào intensity của detection mới **và** điểm thật cùng beam nằm sau.
4. Strongest return: mỗi beam giữ **một** detection (intensity lớn nhất); nếu điểm thật thắng
   thì plume không thay điểm đó — đây chính là cơ chế "che xe".
5. `tests/test_beam_casting.py` — 4 test: tia không cắt → 0 detection; tia cắt → detection
   trong khoảng `(t0,t1)`; `P=0` → không sinh; điểm thật sau plume bị giảm intensity.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` không giảm.
- [ ] Marker `PLUME_RAYCAST beams=<n> hit=<n> det=<n> att_m=<L>` mỗi frame.
- [ ] Frame có plume dày: `attenuated_real > 0` (có điểm thật bị giảm intensity).
- [ ] Điểm sinh ra: **100 %** nằm trên tia của beam thật (kiểm bằng góc, sai số < 0,05°).
- [ ] Thời gian < 50 ms/frame trên laptop (đo, ghi số).

## Cấm

- Không sinh detection ngoài tia beam để "cho dày".
- Không tắt attenuation để test xanh.
- Không đổi `P_det`, `0,02 m⁻¹`, `σ` của lognormal.

---

## PM nghiệm thu 29b — 2026-11-11 (`spray/raycast.py`, chưa nối pipeline)

**Trạng thái: done, kèm 2 cảnh báo.**

| Kiểm | Kết quả `[ĐO]` |
|---|---|
| `pytest -q tests/` | **239 passed, 4 skipped** (232 + 7 test raycast) |
| File | `spray/raycast.py` (473 dòng), `tests/test_raycast.py` (214 dòng) |
| Detection nằm trên tia | sai số elevation lớn nhất **1,78e-15°** (yêu cầu < 1e-5) |
| Strongest return hoạt động | probe 100 cụm: **359** điểm thật bị plume che, **1** detection thua điểm thật |
| Attenuation | **631** điểm thật bị giảm intensity, tổng `L` = **2.229,9 m** |

**Cảnh báo 1 — bảng beam đầu vào sai (lỗi của PM).** `spray/config/beam_elevation.yaml` (20 beam) là kết quả
bộ lọc sai trong 29a; xem `docs/plume-beam-table.md` §ĐÍNH CHÍNH. `raycast_frame` nhận `table` qua tham số nên
**code không phải sửa** khi thay nguồn tia, nhưng **không được chạy với bảng này trong eval**.

**Cảnh báo 2 — tốc độ chưa đạt.** Đo trên frame thật `000010`, 100 cụm: **266–476 ms/frame** (yêu cầu
< 50 ms). Phân rã: `0 cụm` = **25,3 ms** (ánh xạ điểm→beam), mỗi cụm ≈ **2,4 ms**. Với ~1.794 cụm sống ở
130 km/h ⇒ 4–7 s/frame ⇒ 196 frame eval ≈ 13–20 phút. Chuyển sang tập tia lấy từ điểm thật (29c) làm thay đổi
chi phí; **tối ưu là tiêu chí bắt buộc của 29c**, không phải "nice to have".

**Số per-cluster hiện tại:** 626 detection / 100 cụm = **6,3/cụm**, cao hơn số thật đo từ nhãn (**2,75/cụm**,
47 điểm / 17 cụm). Chưa kết luận vì hình học probe (cụm rải 3–40 m, ±6° azimuth) khác plume thật; 29c phải đo
lại trên hình học thật trước khi đụng bất kỳ hằng số nào.
