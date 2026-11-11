# 29e-d — Đo hai phân bố paper trên `cal` rồi cắm vào generator

Type: task
Status: ready-for-agent
Follows: 29e-c (commit `40c9c78`)
Owner: PM dispatch → CommandCode

## Vì sao

29e-c đã đưa generator về **đúng dạng paper** (cầu, `r_cl` lognormal µ = −1,2, σ = 0,8, median
0,30 m) và kết quả là:

- ĐẠT: cụm/frame (A1 ±20 % cả 2 lớp), p50 điểm/cụm = 5–6 (A3), latency 23,6–81,1 ms (A6),
  `capped = 0` (A7), 299 test (A8), byte-equal (A9), `RuntimeError` (A10).
- TRƯỢT: điểm/frame (A2) — Crafter 21/100/158/156/148/251/194/98/226 vs đích 570–1.555;
  chiều cao (A4) — p5 0,437 vs 0,111.

Chẩn đoán từ bảng 4 dải cự ly (`docs/measurements/29ec-range-buckets.md`): mất điểm ở **dải gần**
(89 % điểm thật của Crafter@100 nằm <15 m). Trong **cùng frame**, mỗi cụm thật ở dải gần mang
**43 điểm** (mean), cụm sinh ra mang **15 điểm**; và thật có **20,4 cụm/frame** ở dải đó, sinh ra có
**10,4**.

Hai đại lượng quyết định số điểm mỗi cụm đều là **phân bố paper** mà mình đang lấy nguyên văn cho
dataset khác cảm biến/cách gá:

- `n_max` = số tia cắt cầu ⇒ điểm/cụm ≈ `n_max × P_det`, `n_max ∝ (r/d)²`.
- `r_cl` paper: lognormal µ = −1,2, σ = 0,8 (median 0,30 m) — đo trên **VW Crafter, VLP-32C**.
- `P_det` paper: lognormal µ = −2,3, σ = 1,09 (mean 0,18), *"example"*.

⇒ Phải **đo chính hai phân bố này trên `cal`** thay vì tin paper. Đây không phải tune: đó là thay
tham số mượn bằng tham số đo, đúng nguyên tắc “paper là sở cứ phương pháp, số thì đo trên dữ liệu
mình đánh giá”.

## Việc 1 — đo (không sửa generator)

Viết `scripts/measure_29ed.py`, đọc `cal` (3 scene × 30 frame mỗi ô), Crafter & Golf, 9 tốc độ.
Với **mỗi cụm thật** (DBSCAN 0,7°/minPts = 3 trên điểm label 2):

| đại lượng | định nghĩa |
|---|---|
| `d` | range của tâm cụm tới gốc cảm biến (m) |
| `n` | số điểm của cụm |
| `r_cl` | **max** khoảng cách từ điểm tới tâm cụm (m) — đúng định nghĩa paper |
| `n_max` | số tia Lidar cắt khối cầu bán kính `r_cl` tại `d`, dùng **đúng** `Ω_tia = 2,003e−5 sr` của `spray/raycast.py` |
| `P_det` | `n / n_max` |
| `elong` | extent theo phương range / extent ngang |

In (gộp và tách theo lớp, theo tốc độ, theo 4 dải cự ly):

1. `r_cl`: median / mean / p90 / p99; **fit lognormal** (µ, σ) và so với (−1,2; 0,8).
2. `P_det`: median / mean / p10 / p90; **fit lognormal** (µ, σ) và so với (−2,3; 1,09);
   tỉ lệ `P_det > 1` (nếu > 5 % nghĩa là giả thiết cầu **không đủ** — báo ngay, đừng tự sửa).
3. `elong`: median (Gate G4 của 29d cho 1,48).
4. Số cụm/frame ở dải gần (<15 m) — đối chiếu 20,4 (Crafter@100).

Ghi `docs/measurements/29ed-real-distributions.md` (**file mới**).

## Việc 2 — cắm số đo vào generator

Chỉ sau khi có bảng trên:

- `PlumeStateConfig`: `radius_mu`, `radius_sigma` ← fit lognormal của `r_cl` **theo lớp** (hai bộ
  số, ghi `[ĐO …]` + ngày). Giữ `RADIUS_MAX_M = 1,0` trừ khi p99 đo được vượt 1,0 m.
- `P_det`: `mu_det`, `sigma_det` ← fit lognormal của `P_det` **theo lớp**, ghi `[ĐO]`.
- Nếu `P_det > 1` quá 5 %: **dừng, báo PM**, không tự nới.
- Không thêm hằng số nào khác. Không quét tham số. Không đụng `WATER_FILM`, `T`, `drag`.

Cho phép **1 vòng** cắm số → đo lại A1–A10. Trượt thì dừng, báo số.

## Tiêu chí nghiệm thu (giữ nguyên 29e-c, thêm A11)

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| A1 | cụm/frame 9 mốc × 2 lớp | ±20 % Bảng 1 |
| A2 | điểm/frame | 48/180/361/856/945/1.382/1.418/753/878 ±25 % (Bảng 1, noise/frame) |
| A3 | p50 điểm/cụm | 6 ± 2 |
| A4 | chiều cao p5/med/p95 | 0,111 / 1,197 / 2,264 ± 0,20 m |
| A5 | p95\|y\| | 2,308 ± 15 % |
| A6–A10 | latency / capped / test / byte-equal / RuntimeError | như 29e-c |
| **A11** | `r_cl` và `P_det` fit trên dữ liệu **sinh ra** | lệch ≤ 25 % so với fit trên `cal` |

## Không được làm

- Không tune trên `held-out`. Không sửa `docs/measurements/semantic-spray-*.md`.
- Không thêm `*_PER_KMH` hay hằng số hiệu chỉnh theo tốc độ.
- Không commit.