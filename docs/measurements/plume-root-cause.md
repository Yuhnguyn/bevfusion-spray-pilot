# Root cause: vì sao plume sinh ra thưa và vỡ vụn hơn spray thật

Đo ngày 2026-11-17 trên `sspp` @ `bad0f4b`. Script: `scripts/diag_plume_gap.py`,
`diag_spray_location.py`, `diag_cluster_extent.py`, `diag_spray_source.py`,
`diag_drift_wet.py`, `diag_steady_state.py`, `diag_table_check.py`.

Nhãn: `[ĐO]` đo trên máy này · `[TÍNH]` suy ra từ công thức trong code.

---

## 0. Số đo nền — thật vs sinh

| v (km/h) | thật điểm/frame | sinh det/frame | tỉ lệ | thật điểm/cụm | sinh điểm/cụm | thật z trên mặt đường (p50) | sinh z trên mặt đường (p50) |
|---|---|---|---|---|---|---|---|
| 60 | 174–203 | 192–316 | 1,1–1,6 | 6–8 | 4–17 | 1,6 | 1,6 |
| 100 | 1766–2791 | 123–909 | **0,07–0,32** | 27–69 | 5–10 | 1,8–3,3 | 1,6–1,9 |
| 120 | 1001–2748 | 111–514 | **0,11–0,19** | 20–31 | 5–9 | 1,5–3,3 | 1,6–1,9 |

Ở 60 km/h generator khớp. Từ 100 km/h trở lên sụp còn 7–32%.

## 1. Lỗi số học: số cụm sống gấp 4× mục tiêu `[TÍNH]`

`rate(v) = visible(v) / K` với `K = Σ_{k=0}^{4T/Δt} exp(−k·Δt/T) ≈ T/Δt`
(`plume.py:214-231`, `:283-298`).

Nhưng `prune()` xoá cứng khi `age > 4T`, **không có thinning xác suất**
(`plume_state.py:417-440`). Nên số cụm tích luỹ thực tế là `rate × 4T/Δt`, không
phải `rate × K`:

```
alive = rate × 4T/Δt = 4 × rate × K = 4 × visible
```

Đo xác nhận (chạy 120 frame, box 22 m, ego = object):

| v | visible (bảng) | rate | 4T/Δt | rate×4T/Δt | alive đo được | ratio |
|---|---|---|---|---|---|---|
| 60 | 11,3 | 2,54 | 16 | 40,6 | 46 | 4,1× |
| 100 | 29,2 | 2,38 | 48 | 114 | 119 | 4,1× |
| 120 | 17,6 | 1,08 | 64 | 69 | 76 | 4,3× |

Hệ quả: cùng một ngân sách detection bị rải lên **4× số cụm**, mỗi cụm yếu đi
4× (`survival = exp(−age/T)` trong `raycast.py:270-273` bù lại tổng số, nhưng
không bù lại cấu trúc). Đây chính là **nguyên nhân vỡ vụn**.

## 2. Điểm mỗi cụm thiếu 6–8× `[ĐO]`

Thật: 27–69 điểm/DBSCAN-cluster (median 55,6 @ 100 km/h).
Sinh: 5–10 điểm/cluster.

`_POINTS_MEDIAN_BY_RANGE` (14 điểm @ 10–20 m) chỉ dùng cho đường materialise
`injected` — đường này **không đi ra output** (`plume_transform.py:129-142`).
Số điểm thật sự ra output do raycast quyết: mỗi tia cắt cụm × P_det lognormal
median 0,10. Quá ít tia cắt mỗi cụm ⇒ quá ít điểm.

## 3. Chưa đạt trạng thái dừng ở tốc độ cao `[TÍNH]`

`4T/Δt` = 64 frame @ 120 km/h, 72 frame @ 130. Scene SSPP chỉ 53–67 frame.
⇒ Plume vẫn đang **tăng dần** khi scene kết thúc, chưa bao giờ ổn định.

## 4. Chiều cao thấp hơn thật 0,5–1,4 m `[ĐO]`

Thật @ 100–120 km/h: z p50 = 1,5–3,3 m **trên mặt đường** (cao hơn nóc xe 2,62 m).
Sinh: 1,6–1,9 m trên mặt đường.

**Sửa lại kết luận trước**: khi xem hình tôi nói "sinh bay cao hơn" — SAI, vì
so z tuyệt đối mà không trừ `road_z` (road_z = −1,4…−1,7). Thật cao hơn.

## 5. Wet ground gần như không tác dụng `[ĐO]`

`points_in` = 0–310 trên ~20.000 điểm/frame ⇒ **0–1,5%** điểm bị ảnh hưởng.
Trên dải đường tổng hợp 2.000 điểm: `boosted=1375`, `attenuated=625` — 69% điểm
bị **tăng** cường độ, không phải giảm. Cần review `wet_ground.py:175-210`.

## 6. Bảng calibration: đúng ±40% trừ mốc 120 `[ĐO]`

Đo lại toàn train (DBSCAN 0,7°/minPts 3): crafter 60→11,0 (bảng 11,3 ✓),
80→20,0 (22,0 ✓), 100→33,0 (29,2 ✓), **120→11,0 (bảng 17,6, lệch 1,6×)**.
Golf tương tự. Bảng không phải nguyên nhân chính.

## 7. Spray thật là gì — quan trọng cho thiết kế

`[ĐO]` trên scene 0060 (box giữ x≈22–24 m suốt 40 frame, ego 100 km/h):
- spray_x p50 trôi từ **+12,2 m → −6,6 m** trong 40 frame;
- `near_ego(d<10 m)` tăng 31% → 86%;
- `in_tail` (vùng sau đuôi box) giảm 68% → 8%;
- azimuth: 0,1–4% ở hai bên, còn lại dồn trước/sau theo trục x.

Nghĩa là spray thật **không bám đuôi xe dẫn đường** — nó được hắt ra rồi ego
lái xuyên qua, nên trong hệ ego nó trôi ngược về phía và vượt qua ego. Khối
đuôi cố định trong `inject_plume_stateful` mô phỏng đúng *lúc sinh*, nhưng
thiếu việc spray cũ phải **lấp đầy cả vùng trước ego** sau vài chục frame.

## Thứ tự sửa đề xuất

1. **Sửa hệ số 4×** (rate dùng `4T/Δt` thay `K`, hoặc thinning xác suất trong
   `prune`) — rẻ nhất, sửa đúng gốc vỡ vụn.
2. **Tăng điểm/cụm** — nới P_det hoặc tăng bán kính cụm để nhiều tia cắt hơn.
3. **Nâng khối sinh** lên 0,4–1,0 chiều cao box thay vì 0,05–0,92.
4. **Wet ground**: review nhánh boost; nếu không sửa được thì tắt và ghi rõ.
5. **Scene ngắn**: chấp nhận, hoặc warm-up state từ frame âm (không có dữ liệu).
