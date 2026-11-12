# 29f — Số cụm/frame của generator chỉ bằng 0,59× thật

Type: task
Status: ready-for-agent
Follows: 29e-d closure (`9d3fb69`)
Owner: PM dispatch → agent

## Vấn đề — lỗi thật, không phải limitation

29e-d đóng ba tiêu chí (A2/A4/A11) thành limitation vì chúng do **mô hình cầu** không tạo được mảng
nước liền. Nhưng còn một lỗi **khác bản chất và sửa được**: generator sinh **thiếu cụm**.

| @100 km/h, Crafter | real (`cal`) | gen | tỉ lệ |
|---|---:|---:|---:|
| cụm/frame | **21,8** | **12,9** | **0,59×** |
| cụm/frame @130 | 15,0 | 12,0 | 0,80× |
| cụm/frame @50 | 4,5 | 2,9 | 0,65× |

Nguồn: `docs/measurements/29ed3-gen-overlap.md` §2 (cột `cụm real` vs `cụm gen`).

Nghịch lý cần giải thích: tiêu chí **A1 (cụm/frame ±20 % Bảng 1) lại ĐẠT**. Hai con số đo khác nhau vì
**đơn vị đếm khác nhau**:

- A1 đếm **cụm còn sống** (`state.all_alive()`) — đơn vị của Bảng 1.
- `29ed3` đếm **cụm DBSCAN dựng lại từ detection sinh ra** — sau khi ray-cast, chỉ cụm nào có ≥ 3
  detection mới thành cụm.

⇒ Cụm **sinh ra đủ** nhưng **không đủ detection để DBSCAN nhận ra**. Đây là cùng gốc với `P_det` thấp
(0,47×), nhưng **khác triệu chứng**: nó làm hỏng cả *số cụm* mà model nhìn thấy, không chỉ số điểm.

## Việc 1 — xác nhận cơ chế (chỉ đo)

Viết `scripts/measure_29f.py` trên `cal`, 3 scene × 30 frame/ô, 2 lớp, 9 tốc độ:

| cột | định nghĩa |
|---|---|
| `alive` | số cụm còn sống trong state (`state.all_alive()`) |
| `visible` | số cụm có ≥ 1 detection sinh ra |
| `dbscan` | số cụm DBSCAN dựng lại từ detection (≥ 3 điểm) |
| `alive_not_dbscan` | `alive − dbscan` — cụm sinh ra nhưng biến mất |
| `det_per_alive` | số detection / số cụm alive |

In bảng theo lớp × tốc độ, kèm cột `real dbscan` (từ `29ed3`) và `Δ`.

**Cửa chặn:** nếu `alive` đã ≤ 0,7× real ⇒ lỗi ở **khâu sinh cụm**, không phải khâu ray-cast. Báo PM,
chuyển sang việc 3b. Nếu `alive` ≈ real nhưng `dbscan` thấp ⇒ lỗi ở ray-cast, làm việc 3a.

## Việc 2 — đối chiếu Bảng 1 (đơn vị đếm)

Đọc `docs/measurements/semantic-spray-clusters-by-speed.md` và xác nhận Bảng 1 đếm **cụm DBSCAN**
hay **cụm "còn sống"**. Ghi rõ trong báo cáo. Nếu Bảng 1 đếm DBSCAN thì A1 đạt là **trùng hợp** và phải
siết lại tiêu chí.

## Việc 3a — nếu lỗi ở ray-cast

Mỗi cụm alive phải sinh đủ detection để DBSCAN thấy. Kiểm theo thứ tự:

1. `n_max` = số tia cắt cầu — in phân bố `n_max` theo cự ly. Cụm 0,30 m ở 20 m: `r/d = 0,015`,
   `Ω_cầu/Ω_tia ≈ π·0,015²/2,0e−5 ≈ 35` tia. Nếu code tính ra thấp hơn nhiều ⇒ lỗi `n_max`.
2. `P_det` hiệu dụng sau khi Bernoulli từng tia ⇒ kỳ vọng `n_max × P_det`. Với `n_max = 35`,
   `P_det = 0,18` ⇒ **6,3 điểm/cụm** — khớp `p50 = 6` đo được. Nghĩa là **không đủ** để vượt `minPts = 3`
   một cách chắc chắn: `P(n < 3)` với Binomial(35, 0,18) ≈ **13 %**. Nhưng 13 % không giải thích 0,59×.
3. Kiểm **cụm có bị loại vì nằm ngoài `max_distance_m = 100`** hoặc bị `rejected_box` xoá không.

**Không được** nới `minPts` hay `eps` — đó là tham số recipe paper (0,7°, minPts = 3).

## Việc 3b — nếu lỗi ở khâu sinh cụm

Kiểm `cluster_count_for_speed_abs` (`spray/plume_state.py`) và bảng `_CLUSTER_VISIBLE_BY_SPEED`
(`spray/plume.py`). So trực tiếp với Bảng 1. Nếu bảng đang cho 12,9 @100 trong khi `cal` là 21,8 ⇒
sửa bảng theo số đo, ghi `[ĐO 2026-11-12]`.

## Tiêu chí nghiệm thu

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| D1 | bảng `alive`/`visible`/`dbscan` | đủ 18 ô, không `nan` |
| D2 | đơn vị đếm của Bảng 1 | xác nhận được, ghi rõ |
| D3 | cụm DBSCAN gen vs real | **≥ 0,85×** ở @100 và @130 |
| D4 | cụm/frame alive | ±20 % Bảng 1 (giữ A1) |
| D5 | test | xanh, **≥ 312 passed**, 0 failed |
| D6 | `points_clean` | byte-equal |
| D7 | `capped` | 0 ở 4 tốc độ |
| D8 | không đổi `eps`/`minPts` | `grep` xác nhận 0,7 và 3 |

## Không được làm

- Không đổi `minPts`, `eps`, `Ω_tia` — recipe paper.
- Không thêm `*_PER_KMH`, không thêm dict theo lớp.
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.