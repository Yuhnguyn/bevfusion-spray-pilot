# 29a: bảng beam đo được + `spray/beam_model.py` (nền cho ray casting)

HEAD: 6e7da47  Nhánh: main
Skill: không

## Hiện trạng (PM đã kiểm)

- `docs/plume-beam-table.md` (PM đo 2026-11-11): ring id **là** beam id thật (azimuth span 359,8°, elevation
  std 0,26–0,59° trong frame); bản release chỉ còn **20 beam** trong dải ~**−3,91° … +0,51°**; ring id đánh lại
  `0…19`. Bảng góc **của hãng KHÔNG dùng được** (lệch median 3,49°).
- Ring 0 chứa outlier tới `+52°` ⇒ bảng phải tính bằng **median trong IQR**, không dùng mean.
- Đã có `spray/plume_context.py::compute_elevation_deg(points)` (đường dự phòng, không dùng ring).
- `yaml` đã có trong môi trường (`spray/config_merge.py` import), không cần dependency mới.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **223 passed, 4 skipped**.

## Việc phải làm

### 1. `scripts/measure_beam_table.py` (mới)

- Đọc **≥ 100 frame** rải trên ≥ 20 scene trong `data/SemanticSprayDataset/*/*/velodyne/*.bin`
  (dùng `np.fromfile(..., float32).reshape(-1, 5)`, **không** `cat`/`head` file nhị phân).
- Với mỗi ring có ≥ 100 điểm trong frame: `elevation = atan2(z, hypot(x,y))`, lấy **median của các điểm nằm
  trong IQR** (bỏ outlier); `azimuth = atan2(y, x)`.
- **Bước phương vị**: với mỗi ring, sort azimuth, lấy các khoảng dương giữa hai điểm liên tiếp, bỏ khoảng lớn hơn
  5° (khúc nối vòng), rồi lấy **median** — đó là bước phương vị của cảm biến ở scan 10 Hz.
- Xuất `spray/config/beam_elevation.yaml`:
  ```yaml
  # Sinh bởi scripts/measure_beam_table.py — [ĐO] trên SemanticSpray (207 scene)
  source: "SemanticSpray VLP-32C, 100+ frame, ring id 0..N-1 (release đánh lại)"
  azimuth_step_deg: <số đo>
  elevation_deg: [<ring 0>, <ring 1>, ...]
  ```
- In bảng markdown ra stdout: `ring | n_frame | n_điểm | elevation_median | std_giữa_frame | azimuth_step`.
- Chạy 2 lần phải cho **cùng file** (tất định, không random): kiểm bằng `shasum`.

### 2. `spray/beam_model.py` (mới, numpy + yaml + stdlib)

- `@dataclass(frozen=True) BeamTable`: `elevation_deg: tuple[float, ...]`, `azimuth_step_deg: float`.
- `load_beam_table(path="spray/config/beam_elevation.yaml") -> BeamTable`; raise lỗi rõ nếu file thiếu khoá.
- `build_beams(table, azimuth_range_deg=(0,360)) -> (elev (M,), azim (N,))`: lưới beam rời rạc
  `M = len(elevation)`, `N = round(360 / azimuth_step)`; trả hai mảng 1-D (độ) đã `meshgrid`-phẳng.
- `ray_directions(elev_deg, az_deg) -> (K,3)` float64: `[cos e·cos a, cos e·sin a, sin e]`.
- `ray_sphere_intersect(dirs (K,3), center (3,), radius: float) -> (t0, t1)`: phương trình
  `a = dir·dir`, `b = 2·(-center)·dir`, `c = center·center − r²`; trả `t0,t1 = (−b ∓ √disc)/(2a)` khi
  `disc ≥ 0` và `t0 > 0`; ngược lại `nan`. Vector hoá, thuần numpy.
- Ghi docstring: nguồn bảng là `docs/plume-beam-table.md`, **không** dùng bảng nhà sản xuất; ring id dùng làm
  chỉ số beam, góc lấy từ bảng đo.

### 3. `tests/test_beam_model.py` (mới) — 5 test

1. Nạp bảng: `len(elevation_deg) >= 18`, mọi giá trị trong `[-6°, +3°]`, và **khớp** bảng trong
   `docs/plume-beam-table.md` ở ring 1 và ring 14 (sai số ≤ 0,3°).
2. `azimuth_step_deg` trong khoảng `[0,05°, 1,0°]` và `build_beams` cho `N = round(360/step)` cột, `M = len(elev)`.
3. `ray_sphere_intersect`: cầu bán kính 0,3 m tại `(10, 0, 0)`, tia `+x` ⇒ `t0 ≈ 9,7`, `t1 ≈ 10,3`
   (dung sai 1e-6).
4. Tia trượt (cầu tại `(10, 5, 0)`) ⇒ cả `t0`, `t1` là `nan`.
5. Tia cắt theo phương xiên: dựng tia từ elevation 0,5° và cầu nằm trên tia đó tại khoảng cách 20 m ⇒ có cắt,
   và `(t0+t1)/2` nằm trên tia (khoảng cách từ tâm cầu tới tia ≤ 1e-9).

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` → **≥ 228 passed, 4 skipped**, nêu số thật.
- [ ] `scripts/measure_beam_table.py` chạy 2 lần cho **cùng shasum** của `spray/config/beam_elevation.yaml`.
- [ ] `git status` chỉ có: `scripts/measure_beam_table.py`, `spray/beam_model.py`,
      `spray/config/beam_elevation.yaml`, `tests/test_beam_model.py`.
- [ ] Báo cáo nêu **3 số**: số beam (`M`), `azimuth_step_deg` đo được, và thời gian chạy script (giây).
- [ ] Không sửa `spray/plume.py`, `plume_state.py`, `plume_context.py`, `wet_ground.py`, YAML cũ.

## Cấm

- Không dùng bảng elevation của Velodyne; không dùng mean (phải median trong IQR).
- Không thêm dependency; không đọc `os.environ`.
- Không sinh beam theo azimuth ngẫu nhiên — lưới đều theo `azimuth_step_deg` đo được.
- Không tự commit; PM nghiệm thu rồi commit.