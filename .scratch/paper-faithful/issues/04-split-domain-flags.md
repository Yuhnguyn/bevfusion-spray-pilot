# Brief A9: bỏ hẳn tán xạ `diffusion_alpha` + tách 2 điều kiện miền còn lại

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`.
Đọc `docs/adr/0006-detection-protocol-and-calibration-source.md` §5.7 mục 1–2 trước.

**Không hỏi lại. Không mở rộng phạm vi. Không sửa file ngoài §4.**

**PHỤ THUỘC: brief A8 (`.scratch/paper-faithful/issues/03-cleanup-stateless-inject.md`) phải xong và
đã commit.** Kiểm bằng `grep -n PLUME_PAPER_DOMAIN spray/plume.py` — phải còn **đúng 1** khối. Còn 2
→ A8 chưa xong → **DỪNG, báo PM**.

---

## 1. Bối cảnh — vì sao XOÁ HẲN, không để đường tái lập

`diffusion_alpha` là **mở rộng do repo tự thêm, KHÔNG có trong paper**. ADR-0006 §5.7 mục 1 đã đo:
tắt `α` làm det giảm **6,6×** (3.290 → 497 trong 4 scene Crafter) — tức `α` đang thổi phồng 6,6 lần.

Hướng phát triển hiện tại là **train/test theo paper**. Một cơ chế không có trong paper mà đang sai
6,6× không cần "đường tái lập" — nó cần **biến mất**. Giữ hằng số `DIFFUSION_ALPHA = 0.06` chỉ tạo
một nhánh phải bảo trì và một cái cớ để bật lại nhầm.

**Hệ quả phải khai:** mọi số cũ đo với `α = 0.06` (A3-V "production", `trail90`, doc trong
`docs/measurements/`) **không tái lập được** sau brief này. Đánh đổi đã chấp nhận — xem §7.

## 2. Việc phải làm

### Bước 1 — `spray/plume_state.py`: xoá sạch cơ chế tán xạ

**Xoá hằng số và comment** dòng 76-84: `DIFFUSION_ALPHA = 0.06` + khối comment về nó. Comment
`RADIUS_MAX_M` dòng 76-79 nói trần 4,0 m là "của cơ chế tán xạ" → xem bước 2.

`PlumeStateConfig`: xoá trường `diffusion_alpha` (dòng 139) + comment dòng 137-138.

`SprayCluster`: xoá **4 trường chỉ phục vụ tán xạ**:

| trường | dòng | chỉ dùng ở đâu |
|---|---:|---|
| `radius0` | 208 | `radius0 + α·d_rel` |
| `rear_point` | 209 | tính `d_rel` |
| `forward` | 210 | tính `d_rel` |
| `car_speed_mps` | 214 | dời mặt đuôi cho `d_rel` |

Xoá comment dòng 204-207 mô tả cơ chế.

`PlumeState.advance()` (dòng ~562-580): xoá cả khối từ `alpha = float(cfg.diffusion_alpha)` tới
`cluster.radius = min(...)`. **Không thay bằng gì** — bán kính cụm cố định sau khi sinh, đúng paper
§III-B (Fig. 5: `r_cl` là **một** lognormal, không phải luật nở).

`PlumeState.spawn()`: xoá `rear_point = ...` (dòng ~458-462), `car_speed = ...` (dòng ~465), và 4
dòng truyền `radius0=`, `rear_point=`, `forward=`, `car_speed_mps=` vào `SprayCluster(...)` (dòng
~508-511).

**Bắt buộc giữ:** `radius = min(cfg.radius_max_m, radius0)` (dòng 470) — gán bán kính một lần lúc
sinh, không liên quan tán xạ. Đổi tên biến local `radius0` → `radius_draw` cho khỏi lẫn.

### Bước 2 — `RADIUS_MAX_M`: đổi 4.0 → 2.0

`RADIUS_MAX_M = 4.0` (dòng 79) tồn tại **vì tán xạ** (comment: "4,0 m ứng với r ở độ sâu ~60 m").
Xoá tán xạ thì lý do đó mất. Đổi thành **`2.0`** và sửa comment: trần số học theo **p99 của lognormal
paper** — `exp(−1,2 + 2,326·0,72) = 1,94 m`. Paper không đặt trần.

Không dùng `∞`: giữ gần phân bố paper đã khai, tránh đuôi lognormal không kiểm soát.
**Nếu 2,0 làm đổi số nhiều hơn dự kiến → dừng, báo PM** kèm `radius` p99/p999 trước và sau.

### Bước 3 — `inject_plume_stateful`: bỏ khối env, tách `wfh`

Khối `if os.environ.get("PLUME_PAPER_DOMAIN", ...)` trong `inject_plume_stateful`: **xoá hoàn toàn**.
`min_range_m=2.5` / `max_range_m=50.0` giờ là default của `PlumeStateConfig` (bước 4), không replace
nữa.

Thêm 2 tham số hàm, không đọc env:

```python
def inject_plume_stateful(
    ...,
    sample_water_film: bool = True,
    water_film_mm: float | None = None,
) -> PlumeResult:
```

Logic:

- `water_film_mm is not None` → dùng số đó (**đường tái lập số cũ**, vd `1.0`), không lấy mẫu.
  Marker `PLUME_WFH fixed=<value>`.
- ngược lại nếu `sample_water_film` → `context = replace_context_wfh(context,
  sample_wfh_mm(context.scene_token, context.epoch, seed))`. Marker `PLUME_WFH sampled=<value>`.
- ngược lại → giữ `context.wfh_mm` của caller. Marker `PLUME_WFH caller=<value>`.

`state.spawn(...)` và `state.warm_start(...)` **phải** nhận `context` đã thay `wfh` — kiểm từng chỗ;
`warm_start` dùng `context.wfh_mm` để tính `T`.

Sau khi xoá khối env, `import os` trong `spray/plume.py`: nếu không còn dùng → xoá dòng import.

### Bước 4 — `PlumeStateConfig`: default miền

- `min_range_m: float = 0.0` → `2.5`
- `max_range_m: float = float("inf")` → `50.0`

### Bước 5 — `scripts/sspp_infer.py`

- `--paper-domain` (dòng 1361): giữ cờ, đổi thành **deprecated no-op** — `print` cảnh báo ra stderr
  rồi bỏ qua. **Không xoá** (kernel cũ còn truyền).
- Xoá `os.environ["PLUME_PAPER_DOMAIN"] = "1"` (dòng 555).
- `--wfh-mm` **đã có** (dòng 1352, default `1.0`) → default thành `None`; `type=lambda s: None if
  s.lower() in ("none","") else float(s)`. Cập nhật 3 chỗ đọc `args.wfh_mm` (`:500`, `:1001`,
  `:1277`) chịu được `None`.
- Thêm `--no-wfh-sampling` → `sample_water_film=False`.
- Truyền `sample_water_film` + `water_film_mm` ở 2 chỗ gọi `inject_plume(...)` (`:1035`, `:1174`).
- Marker (`:1003-1006`): `paper_domain=...` → `wfh_sampling=<0|1> wfh_mm=<None|số>`.

### Bước 6 — hai script đo đang đọc `diffusion_alpha`

Sẽ `AttributeError` sau bước 1:

- `scripts/measure_cdf_over_range.py:572` — `diffusion_alpha=defaults.diffusion_alpha` trong
  `replace(...)`.
- `scripts/measure_plume_size_tail.py:351,362-363,372,475,505,522,601` — tham số + CLI
  `--diffusion-alpha`.

**Xoá** tham số/CLI/dòng truyền ở cả hai file. **Không** viết lại logic đo — đây là sửa cơ học để
script còn import được, không phải port.

### Bước 7 — test

- `tests/test_plume_paper_domain.py`:
  - xoá import `DIFFUSION_ALPHA` (dòng 6);
  - `test_domain_env_switch_does_not_change_default` (dòng 52-60) đang khoá default CŨ → đổi kỳ vọng
    thành `min_range_m == 2.5`, `max_range_m == 50.0`, **xoá** dòng assert `diffusion_alpha`. Đổi tên
    thành `test_domain_defaults_are_set`;
  - thêm 1 test: `SprayCluster` **không còn** `radius0` / `rear_point` / `forward` / `car_speed_mps`,
    và `PlumeStateConfig()` không còn `diffusion_alpha`.
- `tests/test_plume_wfh_sampling.py`: 4 test giữ nguyên. Thêm 1 test: `inject_plume_stateful(...,
  water_film_mm=1.0)` không lấy mẫu.
- Grep `radius0|rear_point|car_speed_mps|diffusion_alpha|DIFFUSION_ALPHA` trong `tests/` tìm test
  khác cần sửa — **liệt kê trong báo cáo**.
- Test nào khẳng định `radius` tăng theo tuổi (khoá cơ chế tán xạ) → **xoá**, ghi tên vào báo cáo.

### Bước 8 — xoá `--basic-out` ở `scripts/semantic_spray_stats.py`

File này đang **ImportError** từ sau A8:

```
ImportError: cannot import name 'compare_to_simulator' from 'spray.spray_stats'
```

nguyên nhân: dòng 51 import `compare_to_simulator`, dòng 600 gọi nó — cả hai đã bị A8 xoá. Nhánh
`--basic-out` render "legacy summary report" bằng cách so số đo thật với **simulator stateless đã
chết**, nên đường này **vô nghĩa**, không phải hỏng tạm. Xoá hẳn.

Xoá ở `scripts/semantic_spray_stats.py`:

1. docstring dòng 15-22: bỏ mục `* legacy summary report (opt-in via --basic-out)` và
   ``spray.spray_stats.render_markdown``; sửa "Two reports can be produced" → "One report is
   produced".
2. imports dòng 48-55: xoá `StatsAccumulator`, `compare_to_simulator`, `render_markdown`. **Giữ**
   `NOISE_LABEL`, `load_scan`, `single_linkage` — ba cái này còn dùng thật (dòng 117, 121, 178,
   576).
3. `--basic-out` (dòng 551-555) và `--speed-kmh` (dòng 556): xoá cả hai. `--speed-kmh` chỉ phục vụ
   `compare_to_simulator`; kiểm bằng grep rồi mới xoá — nếu còn chỗ khác đọc `args.speed_kmh` thì
   **giữ lại** và ghi vào báo cáo.
4. `basic = (...)` dòng 568-572: xoá.
5. khối `if basic is not None: basic.add(...)` dòng 579-580: xoá.
6. cả khối `if basic is not None:` dòng 598-614: xoá.

**Không** xoá `StatsAccumulator`, `render_markdown`, `load_scan`, `single_linkage` khỏi
`spray/spray_stats.py` — `tests/test_spray_stats.py`, `tests/test_semantic_stats.py` và
`scripts/semantic_spray_split.py` vẫn dùng `StatsAccumulator`; `render_markdown` vẫn có 1 test.

## 3. Ràng buộc

1. **Không** đổi: `RADIUS_MU = -1.2`, `RADIUS_SIGMA = 0.72`, `WFH_MIN_MM = 0.1`,
   `WFH_MAX_MM = 1.2`, công thức `sample_wfh_mm`, `spawn_scale` (1.0), `streak_scale` (0.0),
   `lifetime_*`, `min_speed_kmh`, bảng `_CLUSTER_VISIBLE_BY_SPEED`.
2. **Không** đụng `spray/raycast.py`, `spray/plume_context.py` (ngoài việc dùng `sample_wfh_mm` đã
   có), `spray/wet_ground.py`.
3. **Không** sửa `kaggle/gate_c/kernel.py` (còn truyền `--paper-domain`; cờ no-op phải chạy được).
4. **Không** sửa file nào trong `.scratch/` — 43 file đang dùng `diffusion_alpha`, chúng sẽ hỏng; PM
   tự xử lý.
5. **Không** commit, không `git add`.
6. Không xoá cờ `--paper-domain`.

## 4. File được sửa

- `spray/plume_state.py`
- `spray/plume.py`
- `scripts/sspp_infer.py`
- `scripts/measure_plume_size_tail.py`
- `scripts/measure_cdf_over_range.py`
- `scripts/semantic_spray_stats.py`
- `tests/test_plume_paper_domain.py`
- `tests/test_plume_wfh_sampling.py`
- test khác **chỉ khi** grep cho thấy chúng dùng `radius0|rear_point|car_speed_mps|diffusion_alpha`

Ngoài danh sách → dừng, báo PM.

## 5. Xong khi — dán số thật

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot

# (a) baseline TRƯỚC khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
```

Baseline **sau A8**, không phải 224. Ghi số thật.

```bash
# (b) sau khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
# => 0 failed, 0 error

# (c) không còn dấu vết
grep -rn "diffusion_alpha\|DIFFUSION_ALPHA\|radius0\|rear_point\|car_speed_mps" \
  --include=*.py spray/ tests/ scripts/ kaggle/ | grep -v __pycache__
# => KHÔNG dòng nào

grep -rn "PLUME_PAPER_DOMAIN" --include=*.py spray/ tests/ scripts/
# => KHÔNG dòng nào

grep -rn "compare_to_simulator\|simulator_estimate\|basic_out\|basic-out" \
  --include=*.py spray/ tests/ scripts/ | grep -v __pycache__
# => KHÔNG dòng nào

# (c2) MỌI script trong scripts/ phải import được — test suite KHÔNG bắt loại lỗi này.
# A8 để lại đúng lỗi này (semantic_spray_stats.py ImportError) mà `203 passed` không thấy.
# PYTHONPATH phải có :scripts — 2 file import module cùng thư mục (sspp_cluster_table_folds).
for f in scripts/*.py; do
  CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=.:scripts \
    /opt/anaconda3/bin/python -c "import runpy; runpy.run_path('$f', run_name='__test_import__')" \
    > /dev/null 2>/tmp/import_err.txt \
    || { echo "FAIL $f"; tail -3 /tmp/import_err.txt; }
done
echo "--- het danh sach, chi FAIL o tren moi la loi ---"
```

**Giá trị PM đo trên code TRƯỚC khi sửa (2026-11-26):** chỉ **1** dòng FAIL là
`FAIL scripts/semantic_spray_stats.py` (đúng cái bước 8 xoá). Sau khi sửa phải **0 dòng FAIL**.

```bash
# (d) default mới
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
from spray.plume_state import PlumeStateConfig, RADIUS_MAX_M, SprayCluster
for name, got, want in [
    ('min_range_m', PlumeStateConfig().min_range_m, 2.5),
    ('max_range_m', PlumeStateConfig().max_range_m, 50.0),
    ('RADIUS_MAX_M', RADIUS_MAX_M, 2.0),
]:
    print(('OK  ' if got == want else 'FAIL'), name, got, 'expect', want)
print('has diffusion_alpha:', hasattr(PlumeStateConfig(), 'diffusion_alpha'), '(expect False)')
for a in ('radius0','rear_point','forward','car_speed_mps'):
    print('has', a, ':', hasattr(SprayCluster, a), '(expect False)')
"
```

```bash
# (e) bán kính cụm KHÔNG còn tăng theo tuổi
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np
from spray.plume_state import PlumeState, PlumeStateConfig
from spray.plume_context import PlumeContext
st=PlumeState(PlumeStateConfig()); rng=np.random.default_rng(0)
v=130/3.6
ctx=PlumeContext(scene_token='r0',frame_index=0,epoch=0,sensor_origin=np.zeros(3),
    ego_speed_mps=0.0,object_speed_mps=v,wfh_mm=1.0,road_z_m=-2.0,ego_pose=np.eye(4),
    elevation_angles_deg=np.zeros(32),boxes=None,object_velocity_ego_mps=np.array([v,0,0]))
for f in range(40):
    st.advance(0.1,ego_velocity=np.zeros(3)); st.prune(dt=0.1,rng=rng)
    ox=25.0+v*0.1*f; sl=v*0.1
    st.spawn(ctx,object_id=0,rng=rng,dt=0.1,
        center=np.array([ox-sl/2,0.0,-1.25]),extents=np.array([sl/2,1.7,0.75]),
        direction=np.array([1.0,0,0]))
r=[c.radius for c in st.all_alive()]
print('radius p50/p99/max:', round(float(np.percentile(r,50)),3),
      round(float(np.percentile(r,99)),3), round(float(np.max(r)),3))
print('expect: p99 <= 2.0, max <= 2.0')
"
```

```bash
# (f) wfh tất định theo scene
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -c "
from spray.plume_context import sample_wfh_mm
print('sampled        :', round(sample_wfh_mm('Crafter_dynamic/0060'),3))
print('same token again:', round(sample_wfh_mm('Crafter_dynamic/0060'),3), '(expect equal)')
"
```

## 6. Báo lại

Dán nguyên: (b)(c)(d)(e)(f); danh sách test đã sửa/xoá; `git diff --stat`; `git status --short`;
xác nhận `.scratch/` **không** bị sửa.

## 7. PM biết trước — không phải việc của bạn

- 43 file trong `.scratch/` dùng `diffusion_alpha` sẽ hỏng. PM tự xử lý.
- Mọi số A3-V / `trail90` / `docs/measurements/` đo với `α = 0.06` **không tái lập được**.
- Cổng C cũ (`kaggle/gate_c/kernel.py` v5) chạy `α = 0` nên vẫn tái lập về cấu hình — nhưng
  `RADIUS_MAX_M` đổi 4.0 → 2.0 nên số có thể dịch. PM quyết chạy lại hay ghi limitation.

Ngoài phạm vi: sửa `spawn_scale`, sửa `T`/lifetime, port `probe_sspp_plume.py`, chạy lại cổng C,
đổi `kaggle/gate_c/kernel.py`, sửa file trong `.scratch/`.
