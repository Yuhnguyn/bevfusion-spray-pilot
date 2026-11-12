# 30 — Rà soát: còn gì thật sự chưa làm

Type: task
Status: **3/4 mục đã xong ở 29c; 1 mục còn thiếu tiêu chí đo**
Owner: PM (rà soát, không giao agent)

## Rà từng mục của ticket gốc

| # | Mục | Trạng thái | Bằng chứng |
|---|---|---|---|
| D8a | `intensity` của detection = **0** | **XONG** | `spray/raycast.py:311` — `np.zeros(detection_indices.size)` |
| D8b | seed theo `(token, epoch, arm)`, eval tách rời | **XONG** | `spray/plume_context.py:204–213` — `seed_for(scene_token, frame_index, epoch, base_seed)`, dùng `hashlib` |
| ring | ring của điểm sinh ra = ring **thật của tia** đã cast | **XONG** | `spray/raycast.py:307` — `ring = keys_hit[...] // azimuth_count`, tức ring của beam cắt cầu, không phải hằng số |
| D7 | bỏ trần `max_injected_points = 2000` | **XONG** | `grep -rn "max_injected_points" spray/ tests/` → **0 hit** (chỉ còn trong `.pyc` cũ) |

⇒ **Cả 4 mục nội dung đã xong.** Ticket 30 không cần giao agent.

## Mục còn thiếu — không phải code, mà là **bằng chứng**

Ticket 30 có 3 tiêu chí nghiệm thu chưa từng được đo:

| # | Tiêu chí | Đo được chưa |
|---|---|---|
| 1 | `ring` của điểm sinh ra phủ **0–31**, median **4 ± 1** | **CHƯA** |
| 2 | `intensity_p50/p90/p99` = **0/0/0** | **CHƯA** (code đúng, chưa in số) |
| 3 | không còn hằng số `max_injected_points`, trần theo `N_real` | **CHƯA** (đã xoá hằng số, chưa chứng minh trần mới) |

Điểm 1 là điểm **có rủi ro thật**: `ring = keys_hit // azimuth_count` lấy ring của beam **cắt cầu**.
Cụm nằm ở elevation thấp (gần mặt đường) sẽ chỉ sinh điểm ở ring thấp. Nếu median ra 30 hoặc 2 thay vì
4, phân bố ring của frame bị lệch và voxelisation sai — đúng thứ D8b cảnh báo.

## Việc phải làm — 1 script, không sửa code

Viết `scripts/measure_30.py`, chạy trên `cal` (3 scene × 30 frame/ô, 2 lớp, 9 tốc độ), in:

| cột | định nghĩa |
|---|---|
| `ring_min` / `ring_p50` / `ring_max` | phân vị ring của **detection sinh ra** |
| `ring_hist` | 32 ô đếm, để thấy có phủ đủ 0–31 không |
| `int_p50/p90/p99` | intensity của detection sinh ra |
| `n_det` / `n_real` | số detection sinh ra / số điểm thật của frame |
| `ratio` | `n_det / n_real` — kiểm trần 5 % có hiệu lực không |

Ghi `docs/measurements/30-fields.md` (**file mới**).

## Tiêu chí nghiệm thu

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| E1 | `ring` phủ | `ring_min = 0`, `ring_max ≥ 28` |
| E2 | `ring_p50` | **4 ± 2** |
| E3 | `int_p50/p90/p99` | **0 / 0 / 0** tuyệt đối |
| E4 | `ratio` `n_det/n_real` | ≤ 0,05 ở mọi ô (trần 5 %) |
| E5 | test | ≥ 312 passed, 0 failed |

Nếu E1/E2 trượt ⇒ mở ticket sửa cách gán ring (map elevation → ring danh nghĩa VLP-32C, `ceil` theo
bảng góc), **không** sửa bằng hằng số.

## Không được làm

- Không sửa `spray/` trong ticket này — chỉ đo.
- Không đổi `eps`/`minPts`/`Ω_tia`.
- Không commit.