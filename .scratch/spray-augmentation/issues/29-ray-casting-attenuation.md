# 29c: sửa 4 lỗi còn lại của ray casting

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (29a/29b đã xong)
**Chủ:** CommandCode. PM: Hermes.

## Hiện trạng (đã kiểm bằng code và số đo)

| Hạng mục | Trạng thái |
|---|---|
| 29a — bảng `ring → elevation` | **BỊ BÁC BỎ.** ring id không phải beam id trên bản release này. Quyết định thay thế: cast trên lưới tia đều **0,333° × 0,197307°**, FOV −4,06…+5,88° ⇒ ~30 × 1.826 ≈ 54.800 tia. `docs/plume-beam-table.md` §ĐÍNH CHÍNH. `spray/config/beam_elevation.yaml` **phải xoá** |
| 29b — `spray/raycast.py` | Xong: cast beam × cầu, `P_det = n/n_max`, attenuation `e^(−2·0,02·L)`, strongest-return mỗi beam. 239 passed, 4 skipped |
| Latency | **266–476 ms/frame** với 100 cụm (~2,4 ms/cụm) ⇒ 4–7 s/frame ở 1.794 cụm @130 km/h |
| `intensity` | Xuất **72–166** trên thang 255 (`raycast.py:256–261`) |
| Marker | `PLUME_RAYCAST` **chưa tồn tại** |
| Trần điểm | `plume.py:104` `max_injected_points = 2000` (lỗi D7) |
| Khối sau đuôi | `plume.py:115–116` cao `1,5 m` cứng |

## Việc phải làm

1. **`intensity` của detection sinh ra = 0.** `[PAPER]`: *"Over 80 % of spray detections from the
   VLP32 have an intensity value of 0 and 16 % are 1. Therefore, the final intensity value of the
   simulated spray detections are set to 0."* `N(0,5; 0,05)` **chỉ** dùng để xếp hạng giữa nhiều
   detection trong **một** beam (strongest-return) — không được nhân `255`, không được xuất ra.
   Điểm **thật** bị attenuation thì giữ nguyên cơ chế: nhân `e^(−2·0,02·L)` vào intensity thật.
2. **Bỏ trần tuyệt đối.** Thay `max_injected_points = 2000` bằng ngân sách theo frame:
   `max_injected = max(500, round(0,05 × số điểm thật))`, vẫn báo `capped=<n>` trong marker.
   Lý do: hình học đúng cho **807–1.555 điểm/frame**; trần 2.000 hiện tại cắt 45–82 % ở frame dày.
3. **Chiều cao khối theo phân số box.** `tail_block_height_m` thành
   `tail_block_height_frac = (0,05; 0,92)` của chiều cao object; đáy khối = mặt đường + `0,05·h`
   (`z` đáy box SemanticSpray = `−0,411 m`). Bề rộng giữ `3,4 m` (`|y|` p95 thật 2,31 m — khớp).
   Kiểm: elevation median của điểm sinh ra phải vào **8,9–11,0°** ở 70/100/130 km/h (thật 9,2–9,5°).
4. **Hạ latency xuống < 100 ms/frame.** Hai luật lấy từ chính code tham chiếu
   (`dee.cpp:232–238`): (a) lọc beam theo cửa sổ `min/max_azimuth` của từng cụm trước khi cast;
   (b) bỏ qua cụm đã ra sau mặt phẳng cảm biến khi không beam nào phủ tới. **Không** dùng
   vector hoá bằng cách tăng bộ nhớ vượt 2 GB; đo lại bằng `time.perf_counter` và in số.
5. **Marker mới** mỗi frame: `PLUME_RAYCAST beams=<n> hit=<n> det=<n> att_m=<L> capped=<n> ms=<t>`.
6. **Xoá** `spray/config/beam_elevation.yaml`; `beam_model.py` chỉ còn lưới đều.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ **239 passed, 4 skipped** (không giảm).
- [ ] Marker `PLUME_RAYCAST` xuất hiện mỗi frame có plume, đủ 6 khoá.
- [ ] `intensity` của **100 %** detection sinh ra = **0** (assert trong test).
- [ ] Điểm thật sau plume có `intensity` giảm; `points_clean` **không đổi** (byte-equal).
- [ ] Chiều cao điểm sinh ra: p5/med/p95 = **0,16 / 1,51 / 2,36 m** trên mặt đường ±0,15 m.
- [ ] Latency **< 100 ms/frame** ở 100 cụm, đo trên laptop, in số thật.
- [ ] `spray/config/beam_elevation.yaml` không còn tồn tại; không file nào reference.
- [ ] Biên bản nghiệm thu ghi trong ticket này: số đo trước/sau, phần chưa khớp.

## Cấm

- Không đổi `P_det` (đang đúng paper: lognormal Fig. 7 bốc mỗi cụm, Bernoulli mỗi tia).
- Không đổi `T`, `C = −0,15`, `age > 4T`.
- Không thêm ngưỡng cắt cụm theo mét — p5 của `x` dao động −40,6…+3,7 m giữa hai nửa scene.
- Không nâng `wfh` hay hệ số nào để khớp số điểm.
- Không train lại, không chạy Kaggle.