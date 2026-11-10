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
