# 29e-b — Sửa dân số cụm + khối đuôi + phong bì ngang (E2 lần 2)

Type: task
Status: superseded-by-29e-c  ← đích A3 (mean det/cụm = 47,3) sai: đó là đuôi phân bố, xem 29e-c
Blocked by: 29e E1 (working tree `885e290` + WIP, 294 passed)
Owner: PM dispatch → CommandCode

## Vì sao có ticket này

29e đóng được **E1 (plumbing)**: `raycast_frame` đã nằm trong `PlumeTransform`, attenuation
thật áp lên điểm thật (`att_m` = 48,8–61,5 m, `capped=0`, 17–44 ms/frame). E2 thì **không đạt**
và PM đã **cắt worker ở phút 61** để không đốt lượt: worker đang quét `RADIUS_MEDIAN_PER_KMH`
(0,0055 → 0,0065) để cứu `det/cụm`, nhưng đích đem ra so bị **lẫn thống kê**.

### Lỗi đích (PM nhận, đã sửa trong ticket này)

Đích cũ `det/cụm = 19,4 @100 → 36,2 @130` là **median trên các cụm**. Đại lượng worker đo, và
đại lượng quyết định tổng điểm/frame, là **trung bình (noise/frame ÷ cụm/frame)**. Hai thống kê
cho hai tỉ lệ khác nhau:

| km/h | cụm/frame | noise/frame | **mean det/cụm** | median det/cụm |
|---|---:|---:|---:|---:|
| 50 | 4,18 | 47,6 | 11,4 | 7,8 |
| 60 | 11,31 | 179,9 | 15,9 | 5,6 |
| 70 | 17,42 | 361,2 | 20,7 | 5,1 |
| 80 | 22,02 | 856,0 | 38,9 | 14,6 |
| 90 | 20,69 | 945,2 | 45,7 | 15,3 |
| 100 | 29,24 | 1.382,0 | **47,3** | 19,4 |
| 110 | 28,49 | 1.417,9 | 49,8 | 16,5 |
| 120 | 17,58 | 753,4 | 42,9 | 53,8 |
| 130 | 17,69 | 877,9 | **49,6** | 36,2 |

- Tỉ lệ 130/100 theo **mean** = **1,05**; theo **median** = 1,87.
- Worker đo được 30,4 @100 → 33,0 @130, tỉ lệ **1,09** ⇒ **hình dạng theo tốc độ đã đúng**,
  không phải nguyên nhân trượt. Việc quét slope để đuổi 1,87 là đuổi một mục tiêu không tồn tại.
- Nguồn: `docs/measurements/semantic-spray-clusters-by-speed.md`, Bảng 1, `cal`, Crafter (45 frame
  × 3 scene). Golf cho cùng hình dạng, thấp hơn.

## Ba lỗi thật của E2

### (1) Dân số cụm gấp 2,25 lần bảng — nguyên nhân chính

Probe của 29e đếm **alive = 42–63 cụm/frame**, bảng `cal` là **18,65 @130**, **29,24 @100**.
Sai số này giải thích luôn `det/cụm` thấp: cùng một lượng nước bị rải cho 2,25× số cụm.

Cơ chế: `cluster_spawn_rate_for_speed_abs` đặt `rate = visible_ref(v) / K(T_ref)`, nhưng `K` được
tính từ `T` của **wfh tham chiếu**, còn `T` thật trong `PlumeState` dùng `wfh` của frame
(`T = 0,02·wfh·(v−50)+0,2`; @130: 1,0 s tại 0,5 mm, 1,8 s tại 1,0 mm). `rate` **không** phụ thuộc
wfh trong khi tuổi thọ **có** ⇒ alive phình theo `T(wfh)/T(wfh_ref)`. 42 / 18,65 = 2,25 khớp đúng
bậc của tỉ lệ đó.

**Yêu cầu:** định nghĩa `WFH_REF_MM = 1,0` (mốc hiệu chuẩn của paper, 0,5 / 0,75 / 1,0), tính
`K(T(wfh_ref, v))`, và **đóng vòng** bằng bảng: `alive/window = cụm/frame` của bảng `cal` ±20 % ở
cả 9 mốc, đo trên ≥500 frame liên tiếp (30 frame × 3 scene, 1 scene = 1 timestamp).
Khi augment với `wfh` khác, alive **được phép** scale theo `T(wfh)/T(wfh_ref)` — đó là vật lý
(đường ướt hơn ⇒ plume sống lâu hơn), không phải lỗi.

### (2) Bán kính: bảng theo tốc độ, không phải một slope

Với dân số đã đúng, `r` phải làm `det/cụm` khớp cột **mean**. Neo vào chính số worker đã đo
(`r_median = 0,55 m` → 30,4 det/cụm @100), suy ra bảng:

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `radius_median_m` | 0,34 | 0,40 | 0,46 | 0,62 | 0,67 | **0,69** | 0,70 | 0,65 | **0,70** |

Công thức suy ra: `r(v) = 0,55 · sqrt(det_target(v) / 30,4)`, `det_target` = cột mean ở trên.
Giữ lognormal `σ = 0,8` (đuôi phải là thật: median 19,4 vs mean 47,3 ở dữ liệu đo), giữ
`radius_max_m = 1,0`. Bảng này **thay hẳn** `RADIUS_MEDIAN_PER_KMH` (xoá hằng số đó).

Vì sao không dùng một slope: bảng target **bão hoà** sau 90 km/h (47,3 → 49,6), nên
`r ∝ v` sẽ overshoot 130 khoảng 15–20 %. Bảng 9 mốc là dạng trung thực nhất của dữ liệu đo.

### (3) Khối đuôi và phong bì ngang

- `PlumeConfig.tail_block_height_frac = (0,15, 1,00)` — sai. Số đo `cal`: p5/med/p95 =
  **0,111 / 1,197 / 2,264 m** trên mặt đường, box cao 2,62 m, đáy box = mặt đường
  ⇒ frac **`(0,05, 0,92)`**. Đáy 0,15 làm `h5` ra 0,29 m (đo được ở 29e) thay vì 0,111; đỉnh 1,00
  bị `prune` theo `ceiling` cắt nên `h95` tụt còn 1,90 m.
- `tail_block_width_m = 3,4` cho p95 ngang lý thuyết 1,62 m, nhưng đo ra **3,0 m** vì gió 2 m/s
  đẩy cụm trong suốt `4T`. Đích là **2,308 m** (p95|y| trên `cal`). Cần **kẹp phong bì**: vị trí
  ngang của cụm (tâm + bán kính) không được vượt `±2,308/0,95 = ±2,43 m` trong suốt vòng đời,
  thay vì để gió tự do. Không tăng `tail_block_width_m` để bù — làm vậy là đổi một số đo lấy một
  số đo khác.

## Việc phải làm

1. `spray/plume_state.py`: thêm `WFH_REF_MM`, sửa `cluster_spawn_rate_for_speed_abs` để alive khớp
   bảng ở `wfh_ref`; **xoá** `RADIUS_MEDIAN_PER_KMH`, thêm bảng `RADIUS_MEDIAN_BY_KMH` + nội suy
   9 mốc, dùng cho `radius_mu` khi spawn.
2. `spray/plume.py`: `tail_block_height_frac = (0,05, 0,92)`.
3. Kẹp ngang trong `PlumeState.step` (hoặc chỗ cập nhật `pos`): `|pos[1] − y_block| ≤ 2,43 m`.
4. `scripts/measure_29eb.py` (mới, **ghi ra `docs/measurements/29eb-stateful.md`**, không đụng file
   của 29d): 30 frame × 3 scene × 9 mốc × 2 lớp, `wfh_ref`, in bảng alive/frame, noise/frame,
   det/cụm mean, h p5/med/p95, p95|y|, latency, `capped`, marker `PLUME_RAYCAST`.
5. Test: mỗi mục ở trên có test đơn vị (bảng nội suy, frac, kẹp ngang, rate ở `wfh_ref`).

## Tiêu chí nghiệm thu (đóng băng trước khi chạy)

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| A1 | `alive/frame` vs bảng `cal`, 9 mốc × 2 lớp | ±20 % |
| A2 | `noise/frame` | trong 570–1.555, và ±20 % so bảng ở cả 9 mốc |
| A3 | `det/cụm` **mean** vs bảng | ±20 % |
| A4 | chiều cao p5/med/p95 | 0,111 / 1,197 / 2,264 ± **0,20 m** |
| A5 | p95\|y\| | 2,308 ± **15 %** |
| A6 | latency | ≤ 100 ms/frame |
| A7 | ngân sách | `capped = 0` ở cả 4 tốc độ |
| A8 | test | `pytest -q tests/` xanh, không xoá/nới test cũ |
| A9 | `points_clean` | byte-equal với trước transform |
| A10 | context thiếu key | `RuntimeError` |

## Không được làm

- Không sửa `cal`/`held-out` split, không đụng `docs/measurements/semantic-spray-*.md` của 29d.
- Không tune trên `held-out`.
- Không nới ngưỡng trong bảng nghiệm thu. Nếu trượt, **báo số** và dừng.
- Không commit.