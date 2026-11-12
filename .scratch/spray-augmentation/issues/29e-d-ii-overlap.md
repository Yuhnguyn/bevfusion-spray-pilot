# 29e-d-ii — Đo cách cụm xếp cạnh nhau (nguồn gốc điểm/frame)

Type: task
Status: ready-for-agent
Follows: 29e-d (`6c775e6`, chưa nghiệm thu)
Owner: PM dispatch → CommandCode

## Vì sao — số đã có, không suy lại

29e-c đưa generator về đúng dạng paper. Kết quả: A1 (cụm/frame) ĐẠT, A3 (p50 = 6) ĐẠT,
**A2 (điểm/frame) TRƯỢT**, **A4 (chiều cao) TRƯỢT**.

29e-d đo hai phân bố paper trên `cal` và cho thấy chúng **đã khớp**:

| đại lượng | `cal` | paper | |
|---|---:|---:|---|
| `r_cl` median | 0,271 m | 0,30 m | khớp |
| `P_det` median | 0,035 | 0,10 | cùng bậc |
| `elong` median | 1,477 | 1,48 (G4 29d) | khớp |

⇒ Không phải `r_cl`, không phải `P_det`. Cụm **đơn lẻ** đã đúng.

Chỗ lệch: Crafter@100 có **21,8 cụm/frame**, **979 điểm/frame** ⇒ mean 45 điểm/cụm nhưng
**p50 = 6**. Nếu các cụm là cầu độc lập, tổng chỉ ~130 điểm. Thật 979 ⇒ **7,5× nằm trong các
mảng do cụm chồng nhau bị DBSCAN gộp**. Paper nói đúng cơ chế này (§III-B): *“overlapping will
occur in random cases… it increases inhomogeneity even further by creating other shapes than
spheres”*.

Generator đặt cụm **rải đều** trong khối đuôi ⇒ gần như không chồng ⇒ mất 7,5× điểm, và p5 chiều
cao sai (0,437 vs 0,111) vì không có mảng nước sát mặt đường.

## Việc 1 — chỉ đo (không sửa generator)

Viết `scripts/measure_29ed2.py`, `cal`, 3 scene × 30 frame/ô, 2 lớp, 9 tốc độ. Với mỗi frame, lấy
tâm cụm DBSCAN (0,7°/minPts = 3) trên điểm label 2, rồi tính:

| đại lượng | định nghĩa |
|---|---|
| `nn` | khoảng cách tâm → tâm cụm gần nhất trong cùng frame (m) |
| `nn_norm` | `nn / (r_i + r_j)` — < 1 nghĩa là hai cầu **chồng nhau** |
| `overlap_frac` | tỉ lệ cụm có `nn_norm < 1` |
| `pts_in_overlap` | % tổng điểm nằm trong cụm có `nn_norm < 1` |
| `n_merged` | số cụm DBSCAN có `elong > 1,5` (dấu hiệu đã gộp) |
| `nn_merged` | `nn_norm` trung vị của các cụm `elong > 1,5` |

In bảng theo **lớp × tốc độ** và theo **4 dải cự ly**. Ghi
`docs/measurements/29ed2-overlap.md` (**file mới**).

**Cửa chặn:** nếu `overlap_frac < 5 %` thì dừng, báo PM — nghĩa là giả thuyết chồng cụm sai,
không được sửa generator.

## Việc 2 — sửa 3 lỗi của script đo cũ

Trong `scripts/measure_29ed.py`:

1. `_stats()` khởi tạo `p10 = nan` nhưng chỉ điền các quantile trong tham số `quantiles`
   (mặc định 50/90/99) ⇒ cột `p10` **luôn `nan`**. Sửa để `p10` được tính thật.
2. `P_det` fit lognormal cho `µ = −4,06, σ = 2,60` ⇒ mean suy ra **0,50** trong khi mean đo được
   **0,118**. Fit bị đuôi chi phối. In thêm **fit trên tập lọc** `elong ≤ 1,2 và P_det ≤ 1`
   (cụm gần cầu, chưa gộp) và ghi rõ số cụm còn lại; **không** dùng fit cũ ở đâu nữa.
3. `P_det > 1` ở dải 15–40 m là **13–15,5 %**. In tỉ lệ này **theo dải cự ly** (đã có) và thêm
   cột `n_max` trung vị theo dải để thấy `n_max` bị đếm thiếu ở dải xa.

Chạy lại, ghi đè `docs/measurements/29ed-real-distributions.md`.

## Việc 3 — KHÔNG cắm số vào generator

Ticket này **không** sửa `spray/`. Số của 29e-d hiện đang được cắm dở trong `spray/raycast.py`
(`P_DET_MU_BY_CLASS = {"crafter": -4.064, "golf": -4.415}`) — **giữ nguyên**, PM sẽ quyết sau khi
có bảng chồng cụm. Không mở rộng, không thêm lớp.

## Tiêu chí nghiệm thu

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| B1 | `overlap_frac` in được cho 2 lớp × 9 tốc độ | đủ 18 ô, không `nan` |
| B2 | `pts_in_overlap` | in được, đối chiếu được với 66 % (5 % cụm to nhất) đã đo |
| B3 | cột `p10` | hết `nan` (trừ ô không có cụm) |
| B4 | fit `P_det` trên tập lọc | `|fit_mean − 0,118| / 0,118 ≤ 0,30` |
| B5 | test cũ | xanh, không xoá/nới |
| B6 | `spray/` | **không đổi** so với `6c775e6` |

## Không được làm

- Không sửa `spray/`, không sửa `tests/` (trừ test cho script đo nếu cần).
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`; cần `if __name__ == "__main__":`.