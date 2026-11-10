# 30: trường dữ liệu của điểm sinh ra — intensity, ring, seed, ngân sách điểm

**Type:** task
**Status:** ready-for-agent (sau 29c)
**Blocked by:** 29c
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ

Ba lỗi còn lại của v1 (`docs/plume-v1-defects.md` D7, D8 và mục "còn phải xác minh") đều nằm ở
**trường dữ liệu** của điểm được chèn, không ở hình học:

- **D7 — trần global `max_injected_points = 2000`.** Cắt 45–82 % ở frame dày, không tương quan với
  số điểm thật của frame. Frame 34.720 điểm và frame 60.000 điểm bị cùng một trần.
- **D8 — can thiệp đông cứng qua các epoch + `intensity = 0`.** Nếu cùng một sample luôn nhận đúng
  một plume thì model học thuộc, A/B mất nghĩa. Paper sample `wfh` mỗi lần dùng và giữ tập tham số
  eval tách rời.
- **Cột 4 (ring) của điểm sinh ra.** Ghi ring giả (hằng số hoặc theo cụm) sẽ làm voxelisation và
  các thống kê theo ring sai.

## Việc phải làm

1. **`intensity`**: điểm sinh ra = **0** (đã làm ở 29c — ticket này chỉ kiểm lại và ghi vào
   `spray_stats`). Điểm thật bị attenuation giữ cơ chế nhân `e^(−2·0,02·L)`.
2. **`ring`**: gán ring cho điểm sinh ra theo **elevation của tia** đã dùng để cast, map về ring id
   thật gần nhất trong 32 ring của VLP-32C (`ceil` theo bảng góc danh nghĩa), để phân bố ring của
   điểm sinh ra **phủ 0–31** và có median ≈ 4 như dữ liệu thật. Không gán hằng số.
3. **Seed theo epoch**: augmentation phải **rút lại mỗi epoch** (hoặc mỗi lần đọc sample), không
   cache theo token. Hợp đồng: `seed = hash(token, epoch, arm)`. Eval dùng seed **tách rời** khỏi
   train (held-out spray).
4. **Ngân sách điểm** thay trần tuyệt đối — nếu 29c chưa làm: `max_injected = max(500, 0,05 × N_real)`,
   báo `capped`. Trần phải **tỉ lệ**, không phải hằng số.
5. **`spray_stats` + marker** phải báo đủ: `points_in`, `injected`, `capped`, `attenuated_real`,
   `ring_p50`, `intensity_p50/p90/p99`, `ms`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ 239 passed, 4 skipped (không giảm).
- [ ] Hai epoch liên tiếp trên **cùng** sample cho **hai** plume khác nhau (test bằng sha của
      `injected`), và cùng `(token, epoch, arm)` cho cùng kết quả.
- [ ] `ring` của điểm sinh ra phủ **0–31**, median **4 ± 1**.
- [ ] `intensity` của điểm sinh ra: p50 = 0, p90 = 1, p99 = 3 ± 1 (khớp nhãn thật).
- [ ] Không còn hằng số `max_injected_points`; trần tính theo `N_real` mỗi frame.
- [ ] Biên bản nghiệm thu trong ticket này: số đo trước/sau.

## Cấm

- Không đổi hình học, `P_det`, `T`, `C`.
- Không dùng cùng seed cho train và eval.
- Không "giảm liều" bằng cách hạ số cụm để vừa trần.