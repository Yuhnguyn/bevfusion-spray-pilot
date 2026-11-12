# 29e-d — Biên bản đóng (PM, 2026-11-12)

Type: research
Status: **closed — limitation, không sửa tham số**
Follows: 29e-c (`40c9c78`), 29e-d-ii (`c46e751`), 29e-d-iii (`19a51be`), 29e-d-iv (`ea9e578`)
Owner: PM (không giao agent)

## Kết luận một câu

Generator v2 **đúng theo mô hình paper**; phần điểm/frame còn thiếu là **giới hạn của chính mô hình
paper ở cự ly gần**, mà paper đã tự cảnh báo. Không sửa tham số để khớp — ghi thành limitation.

## Chuỗi chẩn đoán (4 vòng, mỗi vòng loại một giả thuyết)

| vòng | giả thuyết | số đo | kết luận |
|---|---|---|---|
| 29e-c | bán kính cụm sai | `r_cl` median 0,271 m vs paper 0,30 | **loại** — đã đúng |
| 29e-d | `r_cl`/`P_det` của dataset khác paper | `elong` 1,477 vs 1,48; `P_det` median 0,035 vs 0,10 | **loại** — cùng bậc |
| 29e-d-ii | cụm thật chồng nhau nhiều, gen thì không | real `overlap_frac` **62,7 %**, `pts_in_overlap` 87,8 %, `nn` 0,684 m | **xác nhận** hiện tượng |
| 29e-d-iii | vùng đặt của gen quá rộng | gen `overlap_frac` **84,8 %** vs real 62,7 % | **loại** — gen chồng *nhiều hơn* |
| 29e-d-iv | `P_det` phía gen sai | gen `P_det` median 0,008 vs cal 0,017 (**0,47×**) | **xác nhận** một phần |

## Số cuối cùng — ba lỗi độc lập, tích = mức thiếu

| thành phần | tỉ lệ gen/real | nguồn |
|---|---:|---|
| số cụm/frame @100 Crafter | **0,59×** (12,9 vs 21,8) | `29ed3-gen-overlap.md` |
| điểm/cụm (do `P_det`) | **0,52×** | `29ed-real-distributions.md` §5 |
| **tích** | **0,31×** | khớp đúng 304 vs 979 điểm/frame |

## Vì sao không sửa được bằng tham số — paper tự cảnh báo

`P_det` và `r_cl` của paper được fit ở **25 m**:

> *"probability distributions for all clusters in the spray plume with a vehicle distance of **25 m**
> are shown in Fig. 7."*

Dataset SemanticSpray có **89 % điểm của Crafter@100 nằm < 15 m**. Paper tự nêu hạn chế:

> *"Moreover, with higher resolutions, a problem with the spherical cluster representation might appear.
> The problem can become especially pronounced in **close proximity to the sensor** and is to be
> evaluated in future work."*

Bằng chứng định lượng cho hạn chế đó, đo trên `cal`:

- `P_det > 1` ở **13–15,5 %** cụm trong dải 15–40 m (nhiều điểm hơn số tia cắt cầu ⇒ cụm **không phải
  cầu**). Gộp toàn bộ chỉ 1,46 % nên cửa chặn 5 % không bắt được.
- **66,6 %** tổng điểm nằm trong **5 %** cụm to nhất (p99 = 823 điểm, max 1.723) — mảng nước liền.

⇒ Muốn khớp điểm/frame ở dải gần phải thêm cơ chế **ngoài paper** (mảng nước liền / cụm-của-cụm).
Đó là `[CHỌN]` phải bảo vệ trước reviewer, không phải sửa lỗi. Quyết định: **không làm**.

## Trạng thái tiêu chí

| # | Tiêu chí | Kết quả |
|---|---|---|
| A1 | cụm/frame 9 mốc × 2 lớp ±20 % | **KHÔNG ĐẠT** — tiêu chí SAI, xem `29f-0-table1-unit.md`: A1 so `visible_cluster_count_for_speed` (số lý thuyết) với Bảng 1 (cụm DBSCAN). Số thật: **12,9 vs 21,8 = 0,59×** |
| A2 | điểm/frame 570–1.555 | **KHÔNG ĐẠT — chuyển thành chẩn đoán**, lý do ở trên |
| A3 | p50 điểm/cụm = 6 ± 2 | **ĐẠT** (5–6) |
| A4 | chiều cao p5/med/p95 | **KHÔNG ĐẠT** — p5 0,437 vs 0,111; cùng nguyên nhân mảng nước liền |
| A5 | p95\|y\| 2,308 ± 15 % | ĐẠT ở Crafter, Golf@130 +18,8 % |
| A6 | latency ≤ 100 ms | **ĐẠT** (23,6–81,1 ms) |
| A7 | `capped = 0` | **ĐẠT** |
| A8 | test xanh, không nới test cũ | **ĐẠT** — 312 passed, 4 skipped |
| A9 | `points_clean` byte-equal | **ĐẠT** |
| A10 | thiếu `plume_context` ⇒ `RuntimeError` | **ĐẠT** |
| A11 | fit trên dữ liệu sinh lệch ≤ 25 % | **KHÔNG ĐẠT** — `P_det` median −54 %; cùng nguyên nhân |

**6/11 đạt.** Bốn mục trượt (A1, A2, A4, A11). A1 trượt vì **tiêu chí sai** (so hai đại lượng khác
nhau, xem `29f-0-table1-unit.md`); A2/A4/A11 cùng nguyên nhân mảng nước liền.

## Đã revert (không giữ)

- `RADIUS_MU_BY_CLASS` / `RADIUS_SIGMA_BY_CLASS` trong `spray/plume_state.py` — cắm µ fit (−0,928) cho
  median sinh ra 0,395 m, trong khi đo được 0,271 m và paper 0,30 m. MLE bị đuôi chi phối (p99 = 12 m
  do DBSCAN nối điểm dọc scan line) nên **fit không tái tạo được median**. Đã về −1,2 / 0,8.
- `P_DET_MU_BY_CLASS` / `p_det_params_for_class` trong `spray/raycast.py` — cùng lý do. Đã về −2,3 / 1,09.
- `tests/test_plume_measured_distributions.py` — chỉ kiểm hai dict trên.
- **Giữ** `tests/test_plume_lifetime.py::test_radius_median_does_not_grow_with_speed` — nó bắt đúng lỗi.

## Việc còn lại (chuyển sang ticket khác)

1. **Ghi limitation vào paper** — trích nguyên văn §12.3 của `docs/reference/paper-qa-notebooklm.md`,
   kèm 3 số: 89 % điểm < 15 m, `P_det > 1` ở 13–15,5 % cụm dải 15–40 m, 66,6 % điểm trong 5 % cụm to nhất.
2. **Số cụm/frame 0,59×** — đây là lỗi **thật** và **sửa được** (không phải limitation): bảng
   `cluster_count_for_speed_abs` đang cho 12,9 cụm/frame @100 trong khi `cal` là 21,8. Mở ticket riêng.
3. **A4 chiều cao** — cùng nguyên nhân mảng nước liền ⇒ gộp vào limitation, không sửa riêng.

## Không mở lại

- Không thêm `*_PER_KMH`, không thêm dict theo lớp, không thêm cơ chế gom cụm.
- Không tune để khớp A2/A4/A11.
- Paper chỉ cho: **uniform, độc lập từng cụm, trong vùng sau xe**; `r_cl` lognormal µ = −1,2 σ = 0,8;
  `P_det` lognormal µ = −2,3 σ = 1,09, hằng số theo cụm, hiệu chuẩn ở 25 m.