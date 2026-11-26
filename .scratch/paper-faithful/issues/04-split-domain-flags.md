# Brief A9: tách 3 điều kiện "Cách A" thành cờ riêng, bật mặc định cho đường train/test

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`.
Đọc `docs/adr/0006-detection-protocol-and-calibration-source.md` §5.7 (mục 1, 2) trước.

**Không hỏi lại. Không mở rộng phạm vi. Không sửa file ngoài §4.**

**PHỤ THUỘC: brief A8 (`.scratch/paper-faithful/issues/03-cleanup-stateless-inject.md`) phải xong và
đã commit trước khi bắt đầu.** Nếu `git status` còn `M spray/plume.py` từ A8 → **DỪNG, báo PM**.

---

## 1. Bối cảnh — vì sao tách

Hiện ba điều kiện bị trói chung một env `PLUME_PAPER_DOMAIN=1` (`spray/plume.py:546`), **mặc định
tắt**:

| # | điều kiện | bản chất thật |
|---|---|---|
| 1 | `2,5 ≤ ‖pos‖ − radius`, `‖pos‖ ≤ 50 m` | **miền** — biên chứng minh được cho kịch bản following (`[ĐO]` + `[PAPER]` §V-D) |
| 2 | `diffusion_alpha = 0` | **xoá một mở rộng repo tự thêm** — `α` KHÔNG có trong paper (§III-B Fig. 5 cho `r_cl` là một lognormal, không phải luật nở). Đây không phải "miền", đây là bỏ thứ sai |
| 3 | `wfh ~ 0,1 + Exp(1,0)` clip `[0,1;1,2] mm` | **hành vi huấn luyện chuẩn** — `[PAPER]` §V nguyên văn *"the water level is sampled from an exponential distribution from the interval 0.1 − 1.2 mm **during training**"* |

Trói ba thứ khác bậc này lại gây hai hệ quả thật, đã trả giá:

- Muốn làm đúng paper phần `wfh` (điều 3) thì bị **ép** tắt `α` và ép biên cự ly — hai thứ độc lập.
  Hướng phát triển hiện tại là **train/test theo paper**, nên cả ba phải là mặc định; trói khiến
  không thể bật riêng.
- Cổng C chạy đúng cấu hình gộp này và trượt nặng (`docs/measurements/gate-c-result.md`: Δrecall
  −0,219 vs pre-register −0,05). Vì gộp, **không tách được** nguyên nhân là miền cự ly, là `α`, hay
  là nguồn hiệu chuẩn sai miền.

**Mục tiêu brief:** ba cờ độc lập, **default bật cho train/test**, kèm đường tắt tái lập bit-for-bit
số cũ.

## 2. Việc phải làm

### Bước 1 — `PlumeStateConfig`: đổi default điều kiện 1 và 2

`spray/plume_state.py`:

- `diffusion_alpha: float = DIFFUSION_ALPHA` (dòng 139) → `diffusion_alpha: float = 0.0`.
- `min_range_m: float = 0.0` (dòng 146) → `min_range_m: float = 2.5`.
- `max_range_m: float = float("inf")` (dòng 147) → `max_range_m: float = 50.0`.

Giữ `DIFFUSION_ALPHA = 0.06` làm hằng số (dòng 83) — nó là giá trị của **mở rộng đã bị loại**, phải
còn để tái lập. Sửa comment dòng 144-146 cho khớp: `α = 0` là **mặc định**, `0.06` là đường tái lập
số cũ.

### Bước 2 — `inject_plume_stateful`: bỏ khối `replace` + tách `wfh`

**Có HAI khối đọc `PLUME_PAPER_DOMAIN` trong `spray/plume.py`:** `:403` (trong `inject_plume`
stateless) và `:546` (trong `inject_plume_stateful`). Nếu A8 đã xong, khối `:403` **đã biến mất
cùng hàm** — xác nhận bằng `grep -n PLUME_PAPER_DOMAIN spray/plume.py` rồi mới sửa. Nếu vẫn còn 2
khối → A8 chưa xong, **DỪNG**.

Khối ở `inject_plume_stateful` (khoảng dòng 545-557): thay bằng **hai tham số hàm độc lập**, không
đọc env nữa:

```python
def inject_plume_stateful(
    ...,
    sample_water_film: bool = True,
    water_film_mm: float | None = None,
) -> PlumeResult:
```

Tương tác với `--wfh-mm` **đã có sẵn** (`scripts/sspp_infer.py:1352`, default `1.0`): đặt
`water_film_mm=None` thì lấy mẫu; truyền số thì dùng số. Default CLI đổi thành `None` (bước 3), nên
muốn tái lập số cũ phải gõ `--wfh-mm 1.0` tường minh.

Logic:

- Nếu `water_film_mm is not None` → dùng giá trị đó (**đường tái lập số cũ**, vd `1.0`), **không** lấy
  mẫu. Ghi một dòng marker `PLUME_WFH fixed=<value>`.
- Ngược lại nếu `sample_water_film` → `context = replace_context_wfh(context,
  sample_wfh_mm(context.scene_token, context.epoch, seed))`. Marker `PLUME_WFH sampled=<value>`.
- Ngược lại → giữ `context.wfh_mm` của caller. Marker `PLUME_WFH caller=<value>`.

**Xoá** khối `state._config = replace(..., diffusion_alpha=0.0, min_range_m=2.5, max_range_m=50.0)`
— ba giá trị này giờ là default của `PlumeStateConfig` (bước 1), không cần replace nữa.

**Bỏ hẳn** việc đọc env `PLUME_PAPER_DOMAIN` trong `spray/plume.py`. Xoá import `os` **chỉ nếu**
không còn chỗ nào khác dùng (grep trước).

`state.spawn(...)` và `state.warm_start(...)` **phải** nhận `context` đã thay `wfh` — kiểm bằng mắt
từng chỗ, `warm_start` dùng `context.wfh_mm` để tính `T`.

### Bước 3 — `scripts/sspp_infer.py`: cờ CLI thay env

- `--paper-domain` (dòng 1361): **giữ cờ** nhưng đổi thành **deprecated, không còn tác dụng** — chỉ
  `print` một dòng cảnh báo ra stderr rồi bỏ qua. Không xoá cờ (kernel cũ còn truyền nó).
- Xoá dòng `os.environ["PLUME_PAPER_DOMAIN"] = "1"` (dòng 555).
- **`--wfh-mm` đã có sẵn** (dòng 1352, default `1.0`): đổi default thành `None`, sửa `type=float` cho
  nhận `None`, và sửa `type` trong `argparse` thành `lambda s: None if s.lower() in ("none","") else
  float(s)`. Cập nhật 3 chỗ đang đọc `args.wfh_mm` (`:500`, `:1001`, `:1277`) để chịu được `None`.
- Thêm một cờ mới:
  - `--no-wfh-sampling` → `sample_water_film=False`
- Cập nhật chỗ gọi `inject_plume(...)` (dòng 1035 và 1174) truyền `sample_water_film` +
  `water_film_mm`.
- Dòng marker (khoảng 1003-1006) in `wfh_sampling=<0|1> wfh_mm=<None|số>` thay cho
  `paper_domain=<0|1>`. Giữ nguyên `wfh_mm={args.wfh_mm}` ở `:1001` nếu đổi thành `None`-safe.

### Bước 4 — test

- `tests/test_plume_paper_domain.py:52-60` (`test_domain_env_switch_does_not_change_default`): test
  này **khoá default CŨ** (`min_range_m == 0.0`, `diffusion_alpha == 0.06`). Phải **đổi kỳ vọng**:
  default mới là `2.5` / `50.0` / `0.0`. Đổi tên thành
  `test_domain_defaults_are_paper_domain` và thêm một test khoá đường tái lập:
  `PlumeStateConfig(diffusion_alpha=DIFFUSION_ALPHA, min_range_m=0.0, max_range_m=float("inf"))`
  phải trả đúng ba giá trị đó (đường cũ vẫn dựng được).
- `tests/test_plume_wfh_sampling.py`: 4 test hiện có giữ nguyên. Thêm 1 test: gọi
  `inject_plume_stateful(..., water_film_mm=1.0)` thì `context.wfh_mm` **không** bị lấy mẫu (kiểm
  marker hoặc `state` nhận `wfh_mm == 1.0`).
- Bất kỳ test nào đang assert `min_range_m == 0.0` hoặc `max_range_m == inf` làm default → sửa theo
  default mới. **Tìm bằng grep trước khi sửa**, liệt kê trong báo cáo.

## 3. Ràng buộc

1. **Không** đổi `wfH` mặc định nào khác: `WFH_MIN_MM = 0.1`, `WFH_MAX_MM = 1.2`,
   `sample_wfh_mm` giữ nguyên công thức `0.1 + Exp(mean 1.0)` + clip.
2. **Không** đổi `spawn_scale` (giữ `1.0`), `streak_scale` (giữ `0.0`), `radius_max_m`,
   `pdet_range_exponent` — §5.7 mục 5 cấm thêm hệ số bù.
3. **Không** đụng `spray/raycast.py`, `spray/plume_context.py` (ngoài việc dùng `sample_wfh_mm` đã
   có), `spray/wet_ground.py`.
4. **Không** sửa `kaggle/gate_c/kernel.py` — nó còn truyền `--paper-domain`, cờ đó giờ no-op và phải
   chạy được. Nếu kernel cần đường tái lập số cổng C cũ, PM sẽ mở ticket riêng.
5. **Không** commit, không `git add`.
6. Không xoá cờ `--paper-domain` (kernel cũ gọi nó).

## 4. File được sửa

- `spray/plume_state.py`
- `spray/plume.py`
- `scripts/sspp_infer.py`
- `tests/test_plume_paper_domain.py`
- `tests/test_plume_wfh_sampling.py`
- các test khác **chỉ khi** grep cho thấy chúng assert default cũ (liệt kê trong báo cáo)

Ngoài danh sách → dừng, báo PM.

## 5. Xong khi — dán số thật

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot

# (a) baseline trước khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
```

**Baseline sau A8 sẽ khác 224** (A8 xoá test của đường chết). Ghi số thật, không so với 224.

```bash
# (b) toàn bộ test sau khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
# => 0 failed, 0 error

# (c) default mới
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
from spray.plume_state import PlumeStateConfig, DIFFUSION_ALPHA
c = PlumeStateConfig()
print('diffusion_alpha =', c.diffusion_alpha, '(expect 0.0)')
print('min_range_m =', c.min_range_m, '(expect 2.5)')
print('max_range_m =', c.max_range_m, '(expect 50.0)')
print('legacy path:', DIFFUSION_ALPHA, '(expect 0.06)')
"

# (d) wfh: ba đường phải cho ba kết quả khác nhau, in marker PLUME_WFH
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np
from spray.plume_context import PlumeContext
for label, kw in [('sampled', {}), ('fixed1.0', {'water_film_mm': 1.0}), ('off', {'sample_water_film': False})]:
    from spray.plume_context import sample_wfh_mm
    print(label, '->', round(sample_wfh_mm('Crafter_dynamic/0060'), 3) if label=='sampled' else kw)
"
# => dòng 'sampled' phải == kết quả sample_wfh_mm('Crafter_dynamic/0060') (tất định);
#    'fixed1.0' phải là 1.0; ba nhánh phải KHÁC nhau

# (e) đếm cụm sống KHÔNG đổi (wfh=1.0 giữ số cũ), nhưng wfh mẫu làm thưa ~10-20%
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np
from spray.plume_state import PlumeState, PlumeStateConfig
from spray.plume_context import PlumeContext
def alive(v_kmh, wfh, seeds=10, frames=150, warm=50):
    out=[]
    for s in range(seeds):
        st=PlumeState(PlumeStateConfig()); rng=np.random.default_rng(31337+s); v=v_kmh/3.6
        for f in range(frames):
            ox=25.0+v*0.1*f
            ctx=PlumeContext(scene_token=f's{s}',frame_index=f,epoch=0,
                sensor_origin=np.zeros(3),ego_speed_mps=0.0,object_speed_mps=v,
                wfh_mm=wfh,road_z_m=-2.0,ego_pose=np.eye(4),
                elevation_angles_deg=np.zeros(32),boxes=None,
                object_velocity_ego_mps=np.array([v,0,0]))
            st.advance(0.1,ego_velocity=np.zeros(3)); st.prune(dt=0.1,rng=rng)
            sl=v*0.1
            st.spawn(ctx,object_id=0,rng=rng,dt=0.1,
                center=np.array([ox-sl/2,0.0,-1.25]),extents=np.array([sl/2,1.7,0.75]),
                direction=np.array([1.0,0,0]))
            if f>=warm: out.append(len(st.all_alive()))
    return float(np.mean(out))
print('wfh=1.0  ', {v: round(alive(v,1.0),1) for v in (50,100,130)})
print('wfh=0.766', {v: round(alive(v,0.766),1) for v in (50,100,130)})
"
```

**Giá trị PM đo trên code TRƯỚC khi sửa (wfh=1.0, seed 31337, 20 seed × 200 frame, α=0.06):**
`{50: 9.1, 100: 36.4, 130: 33.2}` — nhưng lần này 10 seed × 150 frame và **α=0 mặc định mới**, nên
**không kỳ vọng khớp** số trên. Điều phải đúng: nhóm `wfh=1.0` **cao hơn** nhóm `wfh=0.766` ở cả ba
tốc độ, tỉ lệ trong khoảng **0,75–0,95** (đo trước đây: 0,90/0,81/0,80). Ngoài khoảng đó → báo PM,
đừng tự sửa.

## 6. Báo lại

Dán nguyên: output (b) (c) (d) (e); danh sách test đã sửa tên/đổi kỳ vọng; `git diff --stat`;
`git status --short`; và một dòng xác nhận `PLUME_PAPER_DOMAIN` không còn được đọc ở đâu trong `spray/`.

Ngoài phạm vi: sửa `spawn_scale`, sửa `T`/lifetime, port `probe_sspp_plume.py`, chạy lại cổng C, đổi
`kaggle/gate_c/kernel.py`.
