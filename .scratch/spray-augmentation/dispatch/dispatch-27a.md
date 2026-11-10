# 27a: `spray/wet_ground.py` — mặt đường ướt (attenuation intensity), port từ `dee.cpp` MPL-2.0

HEAD: d48de60  Nhánh: main
Skill: không

Ticket mẹ: `.scratch/spray-augmentation/issues/27-wet-ground.md`. **Brief này thay đổi 2 điểm so với ticket** (PM
quyết, ghi ở §"Khác ticket"): không vendor repo `SysCV/LiDAR_snow_sim`, và mô hình **giảm intensity**, không xoá điểm.

## Hiện trạng (PM đã kiểm bằng máy)

- Nguồn chuẩn: `DetectionEnvironmentalEffects.cpp` **dòng 305–380**, hàm `simulate_wet_pavement` (MPL-2.0).
  PM đã đọc nguyên văn; công thức ở §"Số chính xác" dưới đây chép từ đó.
- Ticket 27 ghi "làm mất điểm theo phản xạ gương ướt … `stats.removed`" — **không khớp code gốc**: hàm gốc
  **chỉ gọi `existing_detection.set_intensity(...)`**, không xoá detection nào. Xoá điểm là mô hình tuyết của
  Hahner, không phải mô hình mưa của Linnhoff.
- Repo `SysCV/LiDAR_snow_sim` (HEAD `af376b3`, PM đã clone kiểm): `tools/wet_ground/{augmentation,phy_equations,
  planes,utils}.py`, tổng 796 dòng, cần `scipy` + `sklearn` + `matplotlib`, và giấy phép là
  **CC BY-NC 4.0** (Attribution-NonCommercial). Repo dự án này là công khai → **không vendor** (xem §Khác ticket).
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **213 passed, 4 skipped**.

## Khác ticket (PM quyết, vì 2 lý do cụ thể)

1. **Không vendor 4 file Python.** Giấy phép CC BY-NC 4.0 cấm dùng thương mại và là rủi ro khi công bố artifact
   học thuật kèm repo; trong khi nguồn chuẩn của chính ticket là `dee.cpp` (**MPL-2.0**, đã dùng cho phần khác của
   dự án). ⇒ **Port từ `dee.cpp`**, dùng repo Python chỉ để **đối chiếu đọc**, ghi rõ trong docstring.
2. **Không xoá điểm, chỉ giảm intensity** — đúng nguyên văn hàm gốc. `stats.removed` bỏ; thay bằng
   `stats.points_in`, `stats.attenuated`, `stats.mean_ratio`.

## Số chính xác — chép từ `dee.cpp:305–380`, cấm tự chỉnh

```
sensor_height_over_ground = -road_z_m                     # dùng road_z_m của PlumeContext
pavement_z_tolerance      = 0.2 m
điều kiện áp dụng:  |z_point - road_z_m| <= 0.2  VÀ  y_point in (2.0, 7.0)
                    (cửa sổ y là hằng của code gốc: chỉ điểm mặt đường ở làn bên)
n_air = 1.0003 ; n_w = 1.33 ; pavement_depth_m = 0.0005
Gamma  = clip(intensity / 255.0, 0, 1)                    # [CHỌN] quy đổi sang thang 0–255 của ta
a_in   = atan(range / sensor_height_over_ground)
a_aout = asin(sin(a_in) * n_air / n_w)                    # eq.12 Snell
t_ap   = (2*n_air*cos(a_in) / (n_w*cos(a_in) + n_air*cos(a_aout)))**2 / (cos(a_in)*n_air/n_w/cos(a_aout))
a_wout = asin(sin(a_aout) * n_w / n_air)
r_wp   = ((n_air*cos(a_aout) - n_w*cos(a_wout)) / (n_air*cos(a_aout) + n_w*cos(a_wout)))**2
t_wp   = (2*n_w*cos(a_aout) / (n_air*cos(a_aout) + n_w*cos(a_wout)))**2 / (cos(a_aout)*n_w/n_air/cos(a_wout))
t_p    = t_ap * Gamma * t_wp / (1 - Gamma * r_wp)
gamma  = clip(wfh_mm/1000.0 / pavement_depth_m, 0, 1)     # eq.19; wfh tính bằng mm
intensity_out = ((1-gamma)*Gamma + gamma*t_p) * 255.0 * 0.3      # 0,3 = hằng của code gốc
```

- `wfh_mm` lấy từ `PlumeContext` (mm). `wfh = 0` ⇒ `gamma = 0` ⇒ `intensity_out = Gamma*255*0.3` (giảm 70 % —
  đó là hằng 0,3 của code gốc, giữ nguyên; ghi chú vào docstring).
- `range` = `norm(xyz)` của điểm.
- Điểm nằm trong dải `|z − road_z| ≤ 0,2` nhưng `y` **ngoài** (2,7) ⇒ code gốc **cộng** `+2/255*100` vào
  intensity (≈ +0,78 trên thang 0–100). Port đúng hành vi này, đừng bỏ.

## Việc phải làm

### 1. `spray/wet_ground.py` (file mới, chỉ numpy + stdlib)

- `@dataclass WetGroundConfig`: `z_tolerance_m=0.2`, `y_window_m=(2.0, 7.0)`, `pavement_depth_m=0.0005`,
  `n_air=1.0003`, `n_w=1.33`, `intensity_scale=0.3`, `enabled=False`.
- `@dataclass WetGroundStats`: `points_in: int`, `attenuated: int`, `boosted: int`, `mean_ratio: float`.
- `apply_wet_ground(points (N,5), *, road_z_m, wfh_mm, config=None) -> (points_out (N,5), WetGroundStats)`:
  - trả **bản sao**, không sửa mảng đầu vào;
  - chỉ đổi cột 3 (intensity); cột 0–2 và 4 giữ nguyên;
  - clip intensity ra `[0, 255]`;
  - in marker **một** dòng: `WET_GROUND_STATS points_in=<n> attenuated=<n> boosted=<n> mean_ratio=<x.xxx>`;
  - `enabled=False` ⇒ trả bản sao y nguyên, `points_in = attenuated = boosted = 0`, vẫn in marker.
- Docstring ghi: nguồn `dee.cpp:305–380`, MPL-2.0, "**không** phải bản port của `SysCV/LiDAR_snow_sim`
  (CC BY-NC 4.0) — repo đó chỉ dùng để đối chiếu đọc".

### 2. `spray/config/plume_default.yaml`

Thêm khối `wet_ground:` với **đúng** các khoá của `WetGroundConfig` (`enabled: false` mặc định) để
`tests/test_plume_config_yaml.py` vẫn xanh nếu nó kiểm khối này; **không** đổi khoá nào khác của YAML.
Không thêm field nào vào `PlumeConfig` ở ticket này.

### 3. `tests/test_wet_ground.py` (file mới) — 5 test, viết **trước**

1. `enabled=False` → `points_out` **bằng hệt** `points` (`np.array_equal`), `points_in == 0`.
2. Bật trên cloud tổng hợp: 3 điểm — mặt đường trong cửa sổ `y ∈ (2,7)`, mặt đường ngoài cửa sổ, và điểm cao
   1,5 m. Chỉ điểm thứ nhất bị **giảm** intensity; điểm thứ hai **tăng** (nhánh boost); điểm thứ ba **không đổi**.
3. `wfh_mm` tăng ⇒ `mean_ratio` tăng đơn điệu (gamma tăng ⇒ ít giảm hơn), kiểm với `wfh = 0, 0,5, 1,0`.
4. Không điểm nào bị **xoá**: `len(points_out) == len(points)`; cột 0–2 và 4 không đổi.
5. **1 frame thật** (`data/SemanticSprayDataset/Crafter_dynamic/0000_2021-09-08-14-36-56_0/velodyne/000000.bin`,
   đọc bằng `numpy.fromfile(..., float32).reshape(-1,5)`, `road_z_m = -0.411`, `wfh_mm = 1.0`):
   `points_in > 0`, `attenuated > 0`, và `0,2 ≤ mean_ratio ≤ 1,0`. In số thật vào báo cáo.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 218 passed, 4 skipped** (213 + 5). Nêu số thật.
- [ ] `pytest -q tests/test_wet_ground.py` xanh, 5 test, không skip.
- [ ] `git status` chỉ có: `spray/wet_ground.py` (mới), `tests/test_wet_ground.py` (mới), `spray/config/plume_default.yaml`.
- [ ] Báo cáo nêu **3 số của frame thật**: `points_in`, `attenuated`, `mean_ratio`.
- [ ] `grep -n "MPL-2.0\|CC BY-NC" spray/wet_ground.py` có kết quả (ghi nguồn + cảnh báo license).
- [ ] Không import `scipy`, `sklearn`, `matplotlib`; không đọc `os.environ`.

## Cấm

- Không sửa `spray/plume.py`, `spray/plume_state.py`, `spray/plume_context.py`, `inject_plume*`, `PlumeConfig`.
- Không vendor bất kỳ file nào của `SysCV/LiDAR_snow_sim`; không thêm dependency mới.
- Không xoá điểm; không đổi hằng `n_air/n_w/pavement_depth/0,2/(2,7)/0,3`.
- Không bật mặc định (`enabled: false`).
- Không tự commit; PM nghiệm thu rồi commit.