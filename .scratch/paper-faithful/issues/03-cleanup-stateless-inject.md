# Brief A8: xoá đường `inject_plume` stateless (dead code) khỏi `spray/plume.py`

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`.
Đọc `docs/adr/decision-log.md` mục **QĐ12** (đã có), không cần đọc gì thêm.

**Không hỏi lại. Không mở rộng phạm vi. Không sửa file ngoài danh sách ở §4.**

---

## 1. Bối cảnh

`spray/plume.py:350` có hàm `inject_plume()` — đường **stateless**, dựng lại plume từ đầu mỗi
frame, không có state/tuổi/vệt. Docstring của chính nó (`plume.py:361-364`) ghi:

> *"Đường production KHÔNG dùng hàm này — :func:`inject_plume_stateful` mới là đường sống
> (``plume_transform.py``), và ``PlumeTransform`` cũng không gọi hàm này. Chỉ
> ``scripts/probe_sspp_plume.py`` và test dùng."*

Đường sống là `inject_plume_stateful()` → `PlumeState.spawn()`, khối sinh ở đó là
`slab_length = abs(context.object_speed_mps) * dt` (`plume.py:576`), **đã co giãn theo tốc độ**.

Vì hàm dead này vẫn nằm trong file, `PlumeConfig` đang chứa **7 trường chỉ phục vụ nó**:

| trường | dòng | chỉ dùng ở stateless | production đọc |
|---|---|---:|---|
| `distance_range_m` | `plume.py:153` | ✓ | **không** |
| `height_range_m` | `plume.py:154` | ✓ | **không** |
| `lateral_half_width_m` | `plume.py:157` | ✓ | **không** |
| `cluster_radius_median_m` | — | ✓ | có (qua `plume_state`) |
| `cluster_radius_sigma` | — | ✓ | có |
| `cluster_radius_bounds_m` | — | ✓ | **không** |
| `ring` | — | ✓ | **không** |

`**_lateral_offset`, `_count_for_distance`, `_ball`** và `spray_stats.simulator_estimate()` /
`compare_to_simulator()` cũng chỉ phục vụ đường này.

**Hệ quả thật (đây là lý do ticket tồn tại):** khi đo plume production và so với một tham số
"vùng sinh", người đọc (kể cả PM) đọc phải `distance_range_m = (1.0, 10.0)` và tưởng production
sinh cụm cứng trong 10 m. Sai. Đã có lượt PM dựng cả một bảng số trên nhầm lẫn đó. Dead code
không gây lỗi chạy, nó gây **lỗi đọc** — và đó là loại tốn kém hơn.

## 2. Việc phải làm

### Bước 1 — xác định chính xác cái gì chết (KHÔNG xoá vội)

Chạy và dán nguyên output vào báo cáo:

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
grep -rn "inject_plume\b" --include=*.py . | grep -v baseline_tree | grep -v "inject_plume_stateful"
grep -rn "simulator_estimate\|compare_to_simulator\|_lateral_offset\|_count_for_distance\|_ball\b" --include=*.py . | grep -v baseline_tree
```

Mỗi kết quả phải phân loại **test / script / dead**:

- **test** → xoá theo bước 3.
- **script** trong `scripts/` còn sống → **giữ**, nhưng ghi vào báo cáo (bước 4).
- xuất hiện ở `spray/plume_transform.py` hoặc `spray/plume_state.py` → **DỪNG NGAY, báo PM**.
  Nghĩa là production thật sự gọi nó và brief này sai.

### Bước 2 — xoá code, giữ API sạch

Xoá khỏi `spray/plume.py`:

- hàm `inject_plume()` và toàn bộ helper chỉ nó dùng (`_lateral_offset`, `_count_for_distance`,
  `_ball`, `_thin_radial` **chỉ khi** grep ở bước 1 xác nhận không ai khác gọi);
- các trường `PlumeConfig` có cột "production đọc = **không**" ở bảng §1:
  `distance_range_m`, `height_range_m`, `lateral_half_width_m`, `cluster_radius_bounds_m`, `ring`.

Xoá khỏi `spray/spray_stats.py`: `simulator_estimate()` và `compare_to_simulator()`.

Xoá `inject_plume` khỏi `spray/__init__.py` (`__all__` và dòng import).

**Giữ nguyên** `cluster_radius_median_m`, `cluster_radius_sigma` — production đọc qua
`cluster_radius_median_for_speed`.

**Không** đổi `PlumeConfig` sang dataclass khác, không đổi tên trường nào còn sống, không thêm
trường mới.

### Bước 3 — xoá test của đường chết

- Xoá `tests/test_probe_sspp_plume.py` nếu toàn bộ nội dung của nó test `inject_plume` stateless
  (kiểm bằng bước 1). Nếu file đó còn test khác → chỉ xoá phần liên quan, giữ phần còn lại.
- 15 chỗ gọi `inject_plume(` (không phải 20) — trong `tests/test_plume.py`;
- `tests/test_plume_calibration.py` **có** import `_lateral_offset` (dòng 17) và có test
  `test_lateral_offset_is_uniform_on_plus_minus_half_width` (dòng 117) + một assert dòng 138 kiểm
  chuỗi `"_lateral_offset"` có trong source. Ba chỗ đó phải xoá **cùng lúc** với
  `_lateral_offset` — nếu xoá helper mà để test lại thì `224 passed` thành đỏ;
- `scripts/probe_sspp_plume.py:36` import `inject_plume` **module-level**
  (`from spray.plume import PlumeConfig, inject_plume`). Xoá hàm mà không xử lý dòng này thì script
  chết ngay khi import, và comment cảnh báo ở bước 4 không cứu được. Vì vậy bước 4 phải thay dòng
  import đó (xem dưới), không chỉ thêm comment.

**Không** sửa `scripts/probe_sspp_plume.py` (bước 4). **Không** đụng
`tests/test_plume_cluster_budget.py`, `tests/test_plume_paper_domain.py`,
`tests/test_plume_wfh_sampling.py`.

`tests/test_plume_calibration.py`: **chỉ** xoá đúng 3 chỗ liên quan `_lateral_offset` (import dòng
17, test dòng 117, assert dòng 138). Mọi test khác trong file này giữ nguyên — nó chứa
`test_rate_does_not_contain_water_film_height` và các test khoá bảng cụm, xoá nhầm là mất chốt
calibration.

### Bước 4 — script còn gọi hàm chết: đánh dấu, đừng port

`scripts/probe_sspp_plume.py:36` hiện có:

```python
from spray.plume import PlumeConfig, inject_plume  # noqa: E402
```

Xoá `inject_plume` khỏi dòng đó (giữ `PlumeConfig`), **không** viết lại logic script. Rồi thay đầu
file (ngay dưới docstring, trên dòng import) bằng:

```python
# CẢNH BÁO (brief A8): `inject_plume` stateless đã bị xoá khỏi spray/plume.py.
# Script này ĐANG HỎNG — các hàm dưới đây gọi thẳng `inject_plume(...)` và sẽ NameError.
# Số nó từng in (docs/measurements/sspp-plume-probe.md) đo bằng đường ĐÃ CHẾT, KHÔNG dùng
# làm target calibration. Muốn dựng lại: viết trên `inject_plume_stateful`.
```

Nếu muốn script báo lỗi rõ ràng thay vì `NameError`, thêm ngay dưới comment:

```python
inject_plume = None  # gọi vào sẽ TypeError — xem cảnh báo trên
```

Rồi báo PM để mở ticket riêng cho việc port. **Không** tự port trong brief này.

## 3. Ràng buộc

1. **Không** đổi bất kỳ default nào còn sống: `min_speed_kmh`, `water_film_height_m`,
   `cluster_count_velocity_offset_kmh`, `lifetime_*`, `points_per_cluster_*`, `radial_squash`,
   `cluster_radius_median_m`, `cluster_radius_sigma`, `point_cloud_range`, `box_margin_m`.
2. **Không** đụng `spray/plume_state.py`, `spray/plume_transform.py`, `spray/raycast.py`,
   `spray/plume_context.py`, `spray/wet_ground.py`.
3. **Không** sửa `scripts/sspp_infer.py`, `scripts/measure_*.py`, `scripts/diag_*.py`.
4. **Không** commit, không `git add`, không push.
5. **Không** "tiện tay" sửa gì khác. Diff chỉ được chứa: xoá code chết + xoá test + 1 comment cảnh
   báo ở bước 4.

## 4. Danh sách file được sửa

- `spray/plume.py`
- `spray/spray_stats.py`
- `spray/__init__.py`
- `tests/test_plume.py`
- `tests/test_spray_stats.py`
- `tests/test_probe_sspp_plume.py` (xoá hẳn, hoặc sửa nếu còn nội dung sống)
- `scripts/probe_sspp_plume.py` (**chỉ** thêm comment cảnh báo, không sửa logic)

Ngoài danh sách này → **dừng, báo PM**.

## 5. Xong khi — và phải dán số thật

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot

# (a) baseline TRƯỚC khi sửa — ghi lại con số này trước tiên
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
```

Ghi lại `N passed`. **Baseline đo thật ngày 2026-11-26 trên máy này: `224 passed in 20.80s`**
(chạy lại để xác nhận; số thật khác → DỪNG, báo PM, đừng tin số trong brief).

Sau khi sửa, chạy lại cùng lệnh. Kỳ vọng: **passed giảm đúng bằng số test đã xoá**, và **0 failed**,
**0 error**.

```bash
# (b) xác nhận không còn tham chiếu chết
grep -rn "inject_plume\b" --include=*.py . | grep -v baseline_tree | grep -v inject_plume_stateful | grep -v probe_sspp_plume
# => KHÔNG có dòng nào (ngoài file script đã đánh dấu cảnh báo)

grep -rn "distance_range_m\|height_range_m\|lateral_half_width_m\|cluster_radius_bounds_m" --include=*.py . | grep -v baseline_tree
# => KHÔNG có dòng nào

grep -rn "simulator_estimate\|compare_to_simulator" --include=*.py . | grep -v baseline_tree
# => KHÔNG có dòng nào

# (c) production KHÔNG đổi hành vi — bắt buộc phải khớp
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/test_plume_cluster_budget.py tests/test_plume_calibration.py 2>&1 | tail -2
# => 5 passed + số test của test_plume_calibration.py, 0 failed
```

```bash
# (d) số cụm/frame production phải y hệt trước khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np
from spray.plume_state import PlumeState, PlumeStateConfig
from spray.plume_context import PlumeContext
def alive(v_kmh, seeds=20, frames=200, warm=60):
    vals=[]
    for s in range(seeds):
        st=PlumeState(PlumeStateConfig()); rng=np.random.default_rng(31337+s); v=v_kmh/3.6
        for f in range(frames):
            ox=25.0+v*0.1*f
            ctx=PlumeContext(scene_token=f's{s}',frame_index=f,epoch=0,
                sensor_origin=np.zeros(3),ego_speed_mps=0.0,object_speed_mps=v,
                wfh_mm=1.0,road_z_m=-2.0,ego_pose=np.eye(4),
                elevation_angles_deg=np.zeros(32),boxes=None,
                object_velocity_ego_mps=np.array([v,0,0]))
            st.advance(0.1,ego_velocity=np.zeros(3)); st.prune(dt=0.1,rng=rng)
            sl=v*0.1
            st.spawn(ctx,object_id=0,rng=rng,dt=0.1,
                center=np.array([ox-sl/2,0.0,-1.25]),extents=np.array([sl/2,1.7,0.75]),
                direction=np.array([1.0,0,0]))
            if f>=warm: vals.append(len(st.all_alive()))
    return float(np.mean(vals))
print({v: round(alive(v),1) for v in (50,100,130)})
"
```

**Giá trị PM đo trên code TRƯỚC khi sửa, seed `31337`, 20 seed × 200 frame:**

```
50 km/h:  9.1
100 km/h: 36.4
130 km/h: 33.2
```

Sau khi xoá dead code, ba số này **phải giống hệt** (sai số ±0,1 do RNG). Khác → bạn đã sửa vào
đường sống, **revert và báo PM**.

## 6. Báo lại

Dán nguyên, không tóm tắt:

1. output 3 lệnh `grep` của bước 1 + phân loại từng dòng;
2. `N passed` **trước** và **sau**, kèm danh sách tên test đã xoá;
3. output (b), (c), (d) ở §5;
4. `git status --short` + `git diff --stat`;
5. nếu `scripts/probe_sspp_plume.py` bị đánh dấu cảnh báo: dán 5 dòng đầu file sau khi sửa.

Ngoài phạm vi, không làm: sửa `distance_range_m` thành công thức co giãn theo tốc độ (dead code bị
xoá thì không còn gì để sửa), port `probe_sspp_plume.py` sang stateful, sửa `T`/lifetime, sửa
`sample_wfh_mm`.
