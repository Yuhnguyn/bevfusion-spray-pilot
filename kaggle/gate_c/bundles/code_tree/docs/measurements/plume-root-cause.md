# Root cause: vì sao plume sinh ra thưa và vỡ vụn hơn spray thật

Đo ngày 2026-11-17 trên `sspp` @ `bad0f4b`. Script: `scripts/diag_*.py`
(`diag_plume_gap`, `diag_spray_location`, `diag_cluster_extent`, `diag_spray_source`,
`diag_drift_wet`, `diag_steady_state`, `diag_table_check`, `diag_verify_conventions`,
`diag_inside_box`).

Nhãn: `[ĐO]` đo trên máy này · `[TÍNH]` suy ra từ công thức trong code.
**Bản 2**: sửa 4 chỗ số do lỗi quy ước z, thêm 2 lỗi quy ước trục.

---

## 0. Quy ước box của adapter — nền của mọi phép đo

`spray/sspp_adapter.py:117,141` ghi `box[2] = center3D.z − size3D.z/2` = **đáy box**,
và `box[3], box[4] = size_x, size_y` = **(dài, rộng)**.

Đo xác nhận `[ĐO]` (scene 0060 f=16): `box[2] = −0,107`; điểm LiDAR trong footprint
có `z_min = −0,23`, `z_p50 = 1,77`. Nếu `box[2]` là tâm thì `z_min` phải ≈ −1,42.
⇒ **`box[2]` là đáy.** Extent thật của điểm: dọc 4,70 m / ngang 2,11 m, khớp
`box[3]=6,83` là dài, `box[4]=2,42` là rộng.

Script đo cũ tính `road_z = box[2] − h/2` — **sai 1,31 m** (đúng phải là `box[2]`).

---

## 1. Số nền — thật vs sinh (đã sửa road_z)

| v (km/h) | thật điểm/frame | sinh det/frame | tỉ lệ | thật z trên đường p50 | p95 | nóc xe |
|---|---|---|---|---|---|---|
| 60 | 174–203 | 192–316 | 1,1–1,6 | 0,7–0,8 | 2,0 | 2,4–2,5 |
| 100 | 1766–2791 | 123–909 | **0,07–0,32** | 0,75–1,89 | 2,00–2,51 | 2,31–2,51 |
| 120 | 1001–2748 | 111–514 | **0,11–0,19** | 1,18–1,89 | 2,16–2,88 | 2,34–2,56 |

**Sửa lại kết luận cũ**: spray thật **không** cao hơn nóc xe ở median
(p50 = 0,75–1,89 m so với nóc 2,3–2,6 m). Chỉ đuôi p95 mới chạm nóc.
Bản trước ghi 1,5–3,3 m là do road_z sai.

---

## 2. Lỗi số học: số cụm sống gấp 4× mục tiêu `[TÍNH]`

`rate(v) = visible(v) / K` với `K = Σ_{k=0}^{4T/Δt} exp(−k·Δt/T) ≈ T/Δt`
(`plume.py:214-231`, `:283-298`).

`prune()` xoá **cứng** khi `age > 4T`, không thinning xác suất
(`plume_state.py:417-440`). Tích luỹ thực tế là `rate × 4T/Δt`:

```
alive = rate × 4T/Δt = 4 × rate × K = 4 × visible
```

Đo (chạy 120 frame, box 22 m, ego = object):

| v | visible (bảng) | rate | 4T/Δt | rate×4T/Δt | alive đo | ratio |
|---|---|---|---|---|---|---|
| 60 | 11,3 | 2,54 | 16 | 40,6 | 46 | 4,1× |
| 100 | 29,2 | 2,38 | 48 | 114 | 119 | 4,1× |
| 120 | 17,6 | 1,08 | 64 | 69 | 76 | 4,3× |

**Nguyên nhân chính của vỡ vụn**: cùng ngân sách detection rải lên 4× số cụm.

> **ĐÃ SỬA 2026-11-18** (giai đoạn A1 của `.scratch/roadspray-cal/plan.md`).
> Dùng `steady_state_alive_factor(v) = max_age_factor·T/Δt + 1` thay cho `K` ở cả hai chiều:
> `rate = visible / alive_factor` (`plume.py`) và `visible = rate × alive_factor`
> (`plume.py`, `plume_state.cluster_count_for_speed_abs`).
> Đo lại cụm sống/frame so với bảng `cal`: **11,9 vs 11,3** (60 km/h) · **29,5 vs 29,2** (100) ·
> **17,5 vs 17,6** (120) — trước khi sửa là **76 vs 17,6** ở 120 km/h.
> Test khoá: `tests/test_plume_cluster_budget.py` (5 test). 14 test cũ khoá hành vi cũ đã cập nhật; `183 passed`.
> Ghi chú: `diag_steady_state.py` trước đây truyền `seed=0` mỗi frame nên `ttl ~ N(T, 0,2 s)`
> luôn rút cùng một giá trị — số nó in ra bị lệch; đã đổi sang seed theo frame.


---

## 3. Phân bố điểm/cụm: đuôi nặng, không phải median `[ĐO]`

| | mean | median | p95 | max |
|---|---|---|---|---|
| THẬT @100–120 | 20–69 | **5–8** | 63–311 | **228–1238** |
| SINH | ~8–10 | 4–6 | 18–33 | 20–210 |

Median gần nhau. Khác biệt nằm ở **đuôi**: thật có cụm DBSCAN 982–1238 điểm
(single-linkage nối chuỗi theo tia quét), sinh max ~91.

⇒ Mục tiêu **không** phải "cụm nào cũng 55 điểm" (bản trước ghi sai do so mean),
mà là tái tạo đuôi nặng + tổng điểm/frame.

---

## 4. Generator đặt khối thấp hơn 1,31 m `[ĐO]`

`plume.py:514`: `box_bottom = z − height/2`, nhưng `z` đã là đáy box.

| | khối z |
|---|---|
| code hiện tại | [−2,78, −0,50] (đo được −2,72…−2,49) |
| nếu `box_bottom = z` | [−1,47, +0,81] |

Khối chui **dưới mặt đường** 1,31 m. Unit test `test_plume_tail_block.py:71`
dùng box kiểu tâm nên không bắt được lỗi tích hợp này.

---

## 5. Generator đọc nhầm trục: rộng thay vì dài `[ĐO]`

`plume.py:511`: `_, length, height, yaw = box[3:7]` ⇒ `length = box[4] = 2,42`
(rộng) thay vì `box[3] = 6,83` (dài).

Hệ quả: `offset = length/2 + block_length/2` = 1,21 + 1,39 = 2,60 m thay vì
3,42 + 1,39 = 4,81 m ⇒ khối đặt **gần đuôi hơn 2,2 m** và chồng lấn vào thân box.

---

## 6. `_inside_box` cũng đọc nhầm trục `[ĐO]`

`plume.py:728` unpack `width, length = box[3], box[4]` theo quy ước nuScenes
`(w, l, h)`, nhưng adapter ghi `(l, w, h)`.

Đo trực tiếp: box `[6,83 dài, 2,42 rộng]`, điểm ở 2,0 m **dọc** trục xe (trong box
thật) → `_inside_box` trả **False**; điểm ở 2,0 m **ngang** (ngoài box thật) →
trả **True**. Vùng loại điểm đang bị xoay 90°: 2,42 dài × 6,83 rộng.

---

## 7. Wet ground: rất tác dụng, nhưng tác dụng NGƯỢC `[ĐO]`

Với `road_z` sai (−1,42): `points_in = 183` (0,6%) — bản trước kết luận
"vô tác dụng", SAI.

Với `road_z` đúng (−0,11): `points_in = 12.475` (**42,1%** điểm/frame),
`attenuated = 721`, `boosted = 11.754`, `mean_ratio = 1,029`.

⇒ Wet ground chạm 42% điểm, nhưng **94% trong số đó bị tăng** cường độ thay vì
giảm. Ngược ý định "mặt ướt làm yếu return". Cần review `wet_ground.py:175-210`.

> **ĐÃ SỬA 2026-11-18** (giai đoạn A2 của `.scratch/roadspray-cal/plan.md`).
> `wet_ground.py` viết lại theo đúng nguồn paper dùng: Hahner et al. 2022
> (arXiv 2203.15118) §3.1 + Algorithm 2 — Fresnel/Snell cho màng nước mỏng và chuỗi
> phản xạ vô hạn (Eq. 12–17, 19–20). Bản cũ port `simulate_wet_pavement` của
> `openMSL/.../DetectionEnvironmentalEffects.cpp`, không phải nguồn paper trích.
> Nhánh "boost" không còn: `ratio = (1−γ) + γ·T_total/ρ0 ≤ 1`.
> Đo lại trên frame thật (`Crafter_dynamic/0000`, frame 10, `road_z = −0,411`):
> `points_in = 23.265` (**79,9 %**, band `ε_g = 0,5 m`) · `mean_ratio = 0,597`
> (wfh 0,5 mm) → **0,194** (1,0 mm) → **0,033** (1,2 mm, γ = 1) ·
> `mean_alpha_deg = 88,9°` · `removed = 0` (`intensity_floor = 0`). Càng xa càng
> grazing càng mất — đúng chiều Fresnel.
> Caveat phải khai: band 0,5 m tính theo mặt phẳng đường nên **9,2 % điểm
> `label == 1`** (bánh/cản dưới xe dẫn) cũng nằm trong band và bị giảm cường độ,
> dù chúng chỉ chiếm **0,14 %** tổng điểm trong band. Chấp nhận được nhưng phải ghi
> vào Limitations, vì Arm B khác Arm A ở cả wet ground lẫn plume (method đầy đủ).
> Test: `tests/test_wet_ground_hahner.py` (5 test) + `tests/test_wet_ground.py` +
> `tests/test_plume_wet_integration.py` (assert `wet ground must not boost`).

---

## 8. Độ dài scene: vấn đề của scene ngắn ở tốc độ cao `[ĐO]`

Toàn train (16 scene): min 40, p25 60, median 70, p75 76, max 107 frame.

- chưa đạt dừng @120 km/h (cần 64 frame): **5/16 scene = 31%**
- chưa đạt dừng @100 km/h (cần 48 frame): **1/16 = 6%**

Bản trước ghi "scene 53–67 frame" chỉ đúng cho 3 scene đã đo.

---

## 9. Spray thật không bám đuôi xe dẫn đường `[ĐO]`

Scene 0060 (box giữ x≈22–24 m suốt 40 frame, ego 100 km/h):
- spray_x p50 trôi **+12,2 m → −6,6 m**;
- `near_ego(d<10 m)` tăng 31% → 86%;
- `in_tail` (sau đuôi box) giảm 68% → 8%;
- azimuth: chỉ 0,1–4% ở hai bên.

Spray được hắt ra rồi **ego lái xuyên qua**, nên trong hệ ego nó trôi ngược và
cuối cùng phủ kín vùng **trước** cảm biến. Khối đuôi mô phỏng đúng lúc sinh,
nhưng thiếu giai đoạn spray cũ lấp đầy vùng trước ego.

---

## 10. Bảng calibration: đúng ±40% trừ mốc 120 `[ĐO]`

Đo lại toàn train (DBSCAN 0,7°/minPts 3): crafter 60→11,0 (bảng 11,3 ✓),
80→20,0 (22,0 ✓), 100→33,0 (29,2 ✓), **120→11,0 (bảng 17,6, lệch 1,6×)**.
Golf tương tự. Bảng không phải nguyên nhân chính.

---

## Thứ tự sửa đề xuất

| # | Việc | Loại | Rủi ro |
|---|---|---|---|
| 1 | `box_bottom = z` (bỏ `− h/2`) | lỗi quy ước | thấp, 1 dòng |
| 2 | `length = box[3]` (không phải `box[4]`) | lỗi quy ước | thấp, 1 dòng |
| 3 | `_inside_box`: `length, width = box[3], box[4]` | lỗi quy ước | thấp |
| 4 | Sửa hệ số 4×: `rate = visible/(4T/Δt)` hoặc thinning trong `prune` | lỗi số học | trung bình (đổi test) |
| 5 | Wet ground: review nhánh boost | cần điều tra | trung bình |
| 6 | Đuôi phân bố điểm/cụm (P_det, bán kính) | tinh chỉnh | trung bình |
| 7 | Vùng trước ego (spray cũ trôi qua) | thiết kế | cao, cần bàn |

Ba việc đầu là **sửa lỗi**, không phải chỉnh tham số — phải làm trước khi train.
