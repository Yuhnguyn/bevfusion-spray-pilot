# 29b: `spray/raycast.py` — casting theo beam + attenuation + strongest return (chưa nối pipeline)

HEAD: f6a6d29  Nhánh: main
Skill: không

## Hiện trạng (PM đã kiểm)

- `spray/beam_model.py` (29a): `load_beam_table()`, `build_beams(table)` → `(elev (20,), azim (1825,))`,
  `ray_directions(elev, az)` → `(K,3)`, `ray_sphere_intersect(dirs, center, radius)` → `(t0, t1)` có `nan`.
  Bảng đo: **20 beam**, `azimuth_step_deg = 0,197307` (⇒ 1825 tia/vòng), elevation `−4,056° … +0,109°`.
- `spray/plume_state.py`: `SprayCluster` có `position` (ego frame, m), `radius` (m), `age` (s),
  `time_constant` (s) — hằng `T`.
- `[CODE]` `dee.cpp:230–281` (nguồn duy nhất của công thức sinh detection):
  `p = min(1, lognormal(μ=−2,3; σ=1,1)) · min(1, e^(−age/T))`; nếu `U > 1−p` thì sinh detection tại
  `N((t0+t1)/2, (t1−t0)/6)` với **azimuth/elevation đúng bằng beam**; intensity `N(0,5; 0,05)` (thang 0–1)
  nhân `e^(−2·0,02·L)` với `L` = tổng chiều dài tia đã đi qua các cụm **trước** điểm đó;
  `add_max_detection` giữ **một** echo mạnh nhất cho mỗi beam.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **232 passed, 4 skipped**.

## Việc phải làm

### 1. `spray/raycast.py` (mới) — thuần numpy + stdlib

```python
@dataclass(frozen=True)
class RaycastConfig:
    mean_attenuation_per_m: float = 0.02      # [CODE] dee.cpp:279
    p_det_mu: float = -2.3                    # [CODE] profile
    p_det_sigma: float = 1.1
    intensity_mu: float = 0.5                 # [CODE] normal_distrib_0_5
    intensity_sigma: float = 0.05
    max_distance_m: float = 100.0
    min_intensity: float = 0.0

@dataclass
class RaycastStats:
    beams_total: int = 0        # M × N
    beams_hit: int = 0          # số beam cắt ít nhất 1 cụm
    det: int = 0                # số detection sống sót
    det_dropped_stronger_real: int = 0   # detection thua điểm thật cùng beam
    real_dropped_plume_stronger: int = 0 # điểm thật bị plume che
    att_m_total: float = 0.0    # tổng L (m) đã dùng để suy giảm
    att_real_points: int = 0    # số điểm thật bị giảm intensity

def raycast_frame(
    points: np.ndarray,            # (N,5) x,y,z,intensity,ring — mây điểm THẬT của frame
    clusters: Sequence[SprayCluster],
    *,
    table: BeamTable,
    road_z_m: float,
    rng: np.random.Generator,
    config: RaycastConfig | None = None,
) -> RaycastResult   # .detections (K,5), .real_points (N,5) đã suy giảm/đã bỏ, .stats
```

Yêu cầu cài đặt (theo đúng thứ tự này):

1. **Lưới beam**: `elev (M,)`, `azim (N,)` từ `build_beams(table)`; khoá beam là `ring * N + az_idx`.
   Mỗi điểm thật được gán về beam gần nhất: `ring = int(p[4])` (bỏ điểm có ring ≥ M),
   `az_idx = round((degrees(atan2(y,x)) % 360) / step) % N`.
2. **Tiền lọc theo hộp góc** (bắt buộc — không thử 36.500 beam × mọi cụm): với mỗi cụm,
   bán kính góc `α = degrees(asin(min(1, radius / |c|)))` quanh hướng tâm cụm; chỉ lấy beam có
   elevation trong `[e_c − α, e_c + α]` và azimuth trong `[a_c − α/sin|e_c|… , a_c + …]`
   (dùng `α / cos(e_c)` và xử lý wrap quanh 0/360). Sau tiền lọc mới gọi `ray_sphere_intersect`.
3. **Mỗi beam**: gom `(t0, t1, cluster)` của các cụm bị cắt, **sort theo `t0`** (khác code gốc: code gốc
   cộng dồn theo thứ tự cụm trong list — ghi rõ đây là chỗ cố ý sửa cho đúng vật lý), `L` cộng dồn.
4. Sinh detection: `p = min(1, lognormal) · min(1, e^(−age/T))`; `U > 1−p`; distance `N(mid, len/6)`;
   `intensity = clip(N(0,5; 0,05), 0, 1) · 255 · e^(−2·mean·L)`; bỏ nếu `distance > max_distance_m` hoặc
   `z_sensor + distance·sin(elev) <= road_z_m` (dưới mặt đường).
5. **Suy giảm điểm thật**: với mỗi điểm thật, `L = Σ min(t1, range) − t0` trên các cụm `t0 < range` của
   beam đó; `intensity *= e^(−2·mean·L)`. Điểm không có cụm nào trên beam: giữ nguyên.
6. **Strongest return**: mỗi beam chỉ giữ **một** echo — so intensity lớn nhất giữa detection của beam và
   điểm thật của beam (sau suy giảm). Detection thắng ⇒ bỏ điểm thật (đếm `real_dropped_plume_stronger`);
   điểm thật thắng ⇒ bỏ detection (đếm `det_dropped_stronger_real`). Hoà ⇒ giữ điểm thật.
7. Detection xuất ra dạng `(x, y, z, intensity, ring)`: toạ độ = `distance · ray_directions(elev, az)`,
   cột `ring` = chỉ số ring của beam (để pipeline sau này còn phân biệt được).

### 2. `tests/test_raycast.py` (mới) — 7 test

Dựng cụm tổng hợp bằng `SprayCluster` (không cần `PlumeState`); mây điểm thật dựng trên **đúng hướng beam**
để kiểm được cả attenuation lẫn strongest return.

1. **Không cắt**: cụm ở `(20, 5, 0)` bán kính 0,3 m ⇒ `stats.beams_hit == 0`, `len(detections) == 0`,
   `real_points` không đổi intensity.
2. **Cắt, `p = 1`** (`p_det_mu = 10`): cụm ở `(20, 0, 0)` bán kính 0,3 m ⇒ `stats.det == stats.beams_hit`,
   **mọi** detection có khoảng cách trong `(t0, t1)` của beam tương ứng (dung sai 1e-6).
3. **Nằm đúng trên tia**: mọi detection có sai số góc so với hướng beam `< 1e-9` độ.
4. **`p = 0`** (`p_det_mu = −10`): 0 detection, nhưng điểm thật phía sau vẫn bị giảm intensity
   (`stats.att_real_points > 0`).
5. **Độ lớn attenuation**: 1 cụm bán kính 0,3 m trên trục `+x`, 1 điểm thật ở 30 m trên cùng beam ⇒
   `ratio ≈ exp(−2·0,02·L)` với `L` đo được từ `ray_sphere_intersect`, sai số 1e-6.
6. **Strongest return — điểm thật thắng**: điểm thật intensity 255 ở 30 m, cụm ở 20 m ⇒
   `real_dropped_plume_stronger == 0`, `det_dropped_stronger_real ≥ 1`, và điểm thật vẫn còn trong
   `real_points`.
7. **Strongest return — plume thắng**: điểm thật intensity 1 (sau suy giảm) cùng beam, cụm ở 20 m,
   `p = 1` ⇒ `real_dropped_plume_stronger ≥ 1`, detection của beam đó có mặt trong `detections`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 239 passed, 4 skipped**, nêu số thật.
- [ ] `git status` chỉ có: `spray/raycast.py`, `tests/test_raycast.py` (và `spray/beam_model.py` **nếu**
      cần thêm helper — khi đó 5 test của 29a phải vẫn xanh).
- [ ] Báo cáo nêu **3 số đo**: thời gian `raycast_frame` cho **1 frame thật của dataset + 100 cụm**
      (ms), `beams_hit` và `det` của lần chạy đó.
- [ ] Không sửa `spray/plume.py`, `plume_state.py`, `plume_context.py`, `wet_ground.py`, YAML.

## Cấm

- Không phát điểm ngoài tia beam để "cho dày"; không tắt attenuation; không đổi `μ`, `σ`, `0,02 m⁻¹`.
- Không thay strongest return bằng "giữ tất cả".
- Không import `scipy`/`sklearn`; không đọc `os.environ`.
- Không tự commit; PM nghiệm thu rồi commit.