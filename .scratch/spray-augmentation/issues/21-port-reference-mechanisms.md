# 21: Port 3 cơ chế từ code thật (openMSL `sl-1-2`)

**Bối cảnh:** code tham chiếu của Linnhoff 2022 **đã publish** (MPL-2.0) —
`https://github.com/openMSL/sl-1-2-reflection-based-lidar-object-model`,
file `src/model/strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp` (833 dòng)
+ `include/detectionenvironmentaleffects/DetectionEnvironmentalEffects.hpp` + `profile_VLP32.hpp.in`.
`STATUS.md` đang ghi *"repo chỉ có README, chưa publish"* → **SAI**, phải sửa.

**Phạm vi:** port 3 cơ chế (dưới). **KHÔNG** port occlusion, **KHÔNG** port drag, **KHÔNG** port beam/ray-sphere.
Ba cái đó ghi thành giới hạn đã biết.

## Đã đọc code, số liệu chốt (dùng đúng mấy số này, không suy diễn thêm)

| việc | code thật | dòng |
|---|---|---|
| kích hoạt | `object_velocity > 40/3.6` **và** `water_film_height > 0` | `dee.cpp:502`, `:554`; `dee.hpp:48` |
| số cụm | `mean = (0.2*wfh + 0.1) * (v_kmh - 50.0)`, rồi `round(max(0, mean))` | `:509–512`; profile `num_clusters_velocity_offset_kmh = 50.0` |
| hằng thời gian | `time_constant = wfh*0.02*(v_kmh - 50) + 0.2` | `:530` |
| sống sót | `existence_probability *= exp(-age/time_constant)` | `:262` |
| xoá | `age > 4 * time_constant` | `:446` |
| cụm/cụm | radius lognormal μ=−1,2 σ=0,8 (**giữ nguyên 0,30 m median**) | profile `cluster_radius_dist_*` |
| điểm trong cụm | lognormal μ=−2,3 **σ=1,1** (mình đang ghi 1,09) | profile `distance_distr_in_cluster_sigma` |
| suy giảm | `exp(-2.0 * 0.02 * d)` | profile `mean_attenuation_in_cluster` |

`40/3.6` **KHÔNG** phải ngưỡng số cụm. Ngưỡng số cụm là **50 km/h**. Đừng đổi 50 thành 40.

## Việc phải làm

### 1. `spray/plume.py` — số cụm

Thay `round(2 + ((speed-50)/80)*6)` bằng `round(max(0, (0.2*wfh + 0.1) * (v_kmh - 50)))`.

- Thêm field `PlumeConfig.water_film_height_m: float = 0.001` (1 mm) với comment **[CHỌN]** — OSI không cho default,
  dataset không khai báo độ ướt. 1 mm là giả định phải ghi rõ ở mọi báo cáo.
- Kích hoạt: `speed > 40/3.6 m/s`. Ở `v ≤ 50 km/h` công thức cho 0 cụm — **giữ đúng 0**, không thêm sàn.

### 2. `spray/plume.py` — lifetime (không state)

Generator chạy per-frame, không có state qua frame. Tái lập **phân bố** tuổi, không tái lập coherence thời gian:

    T   = wfh * 0.02 * (v_kmh - 50) + 0.2          # giây [CODE]
    age ~ U(0, 4T)                                  # [CHỌN]
    giữ cụm với xác suất p = exp(-age / T)           # [CODE + CHỌN]
    loại cụm có p < u, u ~ U(0,1)

Ghi chú trong docstring: **không** tái lập fade theo thời gian thật, chỉ tái lập phân bố tuổi ở một keyframe
(tỉ lệ sống trung bình trên [0,4T] = 24,5%). Deterministic theo seed.

### 3. Điểm/cụm — sửa σ

`1,09` → **`1,1`** theo profile. Không đổi median (vẫn theo bảng ticket 16: 30/20/14/10/10).

### 4. Đo và báo — BẮT BUỘC, không được sửa lặng lẽ

In bảng: `v_kmh = 40/50/60/80/100/130` × `số cụm trước` vs `sau` (kỳ vọng: 40→0, 50→0, 60→1, 80→3, 100→5, 130→8).

Rồi đối chiếu với số **đo được** của ticket 16: **35.305 cụm / 2.070 frame = 17,06 cụm/frame** trên spray thật.
Nếu số cụm sinh ra **thấp hơn 17** ở dải 80–130 km/h thì **ghi rõ độ lệch vào báo cáo** ("generator tạo X cụm/frame,
spray thật 17,06 — thiếu Y×"). **KHÔNG tự nâng số cụm để khớp**, chỉ báo.

### 5. Docs

- `STATUS.md`: xoá/đính chính dòng non-goal *"code GitLab của Linnhoff chưa publish"* → đã publish trên
  GitHub openMSL, MPL-2.0, cite file + dòng. Thêm giới hạn: v1 **không** có occlusion, **không** drag,
  **không** ray-sphere/beam.
- `docs/plume-model-provenance.md`: thêm mục "Code tham chiếu" với bảng 5 dòng ở trên (giá trị thật + dòng code),
  và mục "v1 khác code thật chỗ nào" (3 dòng: occlusion, drag, beam).
- Ghi rõ: occlusion là chỗ làm kết quả lạc quan nhất — model thật **che** detection có sẵn, v1 chỉ **thêm** điểm.

## Ràng buộc

- Không sửa `mit/bevfusion`, `third_party/`. Không đổi `cluster_radius_median_m = 0.30`.
- Không đổi bảng điểm/cụm theo cự ly của ticket 16 (đó là số đo).
- Test cũ phải pass; **thêm** ≥4 test: (a) v=45 km/h → 0 cụm, (b) v=130 + wfh 1 mm → 8 cụm, (c) v=80 → 3 cụm,
  (d) dropout: chạy 2.000 mẫu, tỉ lệ cụm sống trong [0,20; 0,30] (kỳ vọng 0,245).
- Commit: `fix(plume): port activation/count/lifetime from published Linnhoff reference code`

## Xong khi

- [ ] pytest pass (baseline hiện tại **49 passed**, không được giảm)
- [ ] bảng 6 tốc độ trước/sau + dòng so sánh với 17,06 cụm/frame
- [ ] 4 test mới xanh
- [ ] docs sửa xong, không còn câu "chưa publish"
- [ ] `git status` sạch