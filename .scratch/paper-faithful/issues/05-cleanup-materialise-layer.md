# Brief A10: xoá tầng materialise (output chết) khỏi generator + đồng bộ `plume_default.yaml`

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`, HEAD `d9646ec`.
Skill: `ponytail` (lite) — đây là refactor xoá, không thêm feature. **Không** thám hiểm ngoài các file
ở §5.

**Không hỏi lại. Không mở rộng phạm vi.**

---

## 1. Bối cảnh — số đo thật, đo trên máy này trước khi viết brief

`inject_plume_stateful` vẫn tự "vật chất hoá" mỗi cụm thành điểm (`chunks` → `injected`) rồi trả về
`PlumeResult.points` / `.injected`. Đường production **không đọc** hai field đó:

```
# spray/plume_transform.py:129-142
clean = result.points_clean
raycast = raycast_frame(clean, state.select_alive(), ...)
```

Khối materialise chỉ còn phục vụ: `test_*`, 7 script đo, và `scripts/probe_sspp_plume.py` (đã hỏng từ
A8). Nó là output chết **nằm trong hàm sống**, và nó mang công thức sai ~4×
(`_POINTS_MEDIAN_BY_RANGE` 30/20/14/10 đo trên SSPP; A3 §3: p50 thật 7 điểm/cụm ở 0–5 m) nằm cạnh
công thức đúng (ray-cast trong `spray/raycast.py`). Hai công thức cho một bước ⇒ lỗi đọc.

### 1a. Bằng chứng: xoá tầng này KHÔNG đổi một detection nào

Chạy 80 frame, 100 km/h, 32 cụm sống, cùng seed cho cả hai lần raycast:

```
raycast_frame(result.points,       ...) -> det = 98
raycast_frame(result.points_clean, ...) -> det = 98
real_points ra: (1000, 5) vs (500, 5)
```

Lý do: điểm materialise có `ring = -1`, và `spray/raycast.py:178-181` ghi rõ điểm có `ring` ngoài
`0..M-1` *"stay in the output but take no part in intersection or occlusion"*. Chúng chỉ làm phình
`real_points`, không sinh detection. Vì vậy phép verify §4(c) là **det phải trùng khít**, không phải
"gần đúng".

### 1b. `spray/config/plume_default.yaml` đã mục từ A8/A9

File tự khai *"exact copy of spray.plume.PlumeConfig defaults. Every key here is a real dataclass
field"*. Sự thật đo được:

```
PlumeConfig(**yaml.safe_load(open('spray/config/plume_default.yaml')))
  -> TypeError: PlumeConfig.__init__() got an unexpected keyword argument 'cluster_radius_bounds_m'

yaml-only (không tồn tại trong dataclass): cluster_radius_bounds_m, distance_range_m,
  height_range_m, lateral_half_width_m, ring
cfg-only (dataclass có, yaml thiếu): sample_water_film, water_film_mm
value drift: lifetime_max_age_factor yaml=4.0 vs code=12.0
```

Không runtime nào đọc file này (đã grep: chỉ `spray/config/wet_ground_default.yaml:7` nhắc nó trong
comment, và `tests/test_e2e_config_resolve.py` đọc config model chứ không đọc file này) ⇒ sửa chỉ để
file thôi nói dối. Nhưng phải sửa, vì nó là thứ người viết luận văn mở ra đọc.

---

## 2. Việc phải làm

### Bước 1 — `spray/plume.py`: xoá tầng materialise

Xoá **nguyên khối** trong `inject_plume_stateful`:

| dòng (HEAD `d9646ec`) | nội dung |
|---|---|
| 493–512 | `chunks`, `_count_for_distance`, `_ball`, `_thin_radial`, `_inside_box` loop, `injected = ...` |
| 514–543 | lọc `point_cloud_range`, lọc box, `_injected_budget`, `stats.*` của tầng này |
| 555–566 | `return PlumeResult(points=..., injected=...)` → chỉ còn `PlumeResult(points_clean=..., stats=...)` |

Giữ nguyên: vòng `for index, box in enumerate(box_arr)` + `state.spawn` (đó là đường sinh thật), phần
`wet_ground` + `apply_wet_ground` (xem bước 4), `state.advance/prune`, `print("PLUME_STATE ...")` và
`print(f"PLUME_WFH {wfh_marker}")`.

`stats.clusters` phải được giữ **có nghĩa**: đặt `stats.clusters = len(state.select_alive())` ngay
trước khi in marker (hôm nay nó được cộng trong vòng materialise nên sẽ thành 0 nếu chỉ xoá).

Xoá các hàm chỉ tầng này dùng (đã grep, không ai khác gọi):

```
_points_median_for_distance   (plume.py:621)
_count_for_distance           (plume.py:628)
_ball                         (plume.py:658)
_thin_radial                  (plume.py:668)
_inside_box                   (plume.py:674)
_injected_budget              (plume.py:600)
_POINTS_MEDIAN_BY_RANGE       (plume.py:14-21  + comment khối 13-21)
```

**Giữ** `_in_range` (plume.py:609) — nó lọc box ở dòng 435, vẫn sống.

`PlumeResult` (plume.py:188) chỉ còn `points_clean` + `stats`. Xoá field `points`, `injected`.

`PlumeStats` (plume.py:166): xoá `injected`, `rejected_range`, `rejected_box`, `capped`. Giữ
`eligible_boxes`, `clusters_spawned`, `clusters`, `clusters_dropped_lifetime`, `skipped_*`, `wet_*`,
`det`, `beams_hit`, `att_m_total`, `att_real_points`.

`PlumeConfig`: xoá các field mà sau bước này **không còn chỗ đọc nào trong `spray/`**:
`points_per_cluster_median`, `points_per_cluster_sigma`, `points_per_cluster_bounds`, `radial_squash`,
`box_margin_m`, `intensity`, `cluster_radius_median_m`, `cluster_radius_sigma`.
Cách xác nhận (dán output vào báo cáo):

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python - <<'PY'
import re
from pathlib import Path
src = Path('spray/plume.py').read_text()
i = src.index('def inject_plume_stateful('); j = src.index('\ndef ', i+10)
print(sorted(set(re.findall(r'cfg\.(\w+)', src[i:j]))))
PY
```

### Bước 2 — `spray/raycast.py` + `spray/plume_transform.py`: bỏ tham số `capped`

`capped` chỉ được nuôi bởi `stats.capped` của tầng vừa xoá.

- `raycast_frame(..., capped: int = 0)` (raycast.py:174) — xoá tham số; `_emit_marker(stats, capped,
  started)` (raycast.py:407) — xoá tham số và xoá `capped=` khỏi dòng marker. Marker còn **5** key:
  `beams hit det att_m ms`.
- `spray/plume_transform.py:136` — xoá `capped=result.stats.capped,`.

### Bước 3 — `spray/config/plume_default.yaml`: đồng bộ với dataclass

Sau bước 1, file phải là bản sao khít. Yêu cầu: xoá 5 key ma, thêm `sample_water_film: true` +
`water_film_mm: null`, sửa `lifetime_max_age_factor` 4.0 → 12.0 (theo code), và **giữ đúng comment
đầu file**. Rồi chứng minh:

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python - <<'PY'
import dataclasses, yaml
from spray.plume import PlumeConfig
keys = set(yaml.safe_load(open('spray/config/plume_default.yaml')))
fields = {f.name for f in dataclasses.fields(PlumeConfig)}
print('yaml-only:', sorted(keys-fields), 'cfg-only:', sorted(fields-keys))
cfg = PlumeConfig(**yaml.safe_load(open('spray/config/plume_default.yaml')))
for f in dataclasses.fields(PlumeConfig):
    assert getattr(cfg, f.name) == f.default if f.default is not dataclasses.MISSING else True
print('roundtrip OK')
PY
```

Kỳ vọng: `yaml-only: [] cfg-only: [] roundtrip OK`.

### Bước 4 — script gọi `result.points` → `result.points_clean`

Đây là thay **một token**, không phải port logic. Mỗi chỗ sau đổi `result.points` thành
`result.points_clean`:

```
scripts/measure_cdf_over_range.py:492,593
scripts/visualize_plume_vs_real.py:181
scripts/measure_plume_size_tail.py:403
scripts/visualize_sspp_plume.py:207
scripts/smoke_sspp_paperpath.py:183
scripts/measure_following_scenario.py:292
tests/test_sspp_paperpath.py:99,111,112
```

**Ngoại lệ — `scripts/probe_sspp_plume.py`:** đã hỏng từ A8 (`inject_plume = None`). **Không port.**
Chỉ sửa dòng import/khối cũ đủ để `python -c "import scripts.probe_sspp_plume"` không phát sinh thêm
lỗi mới, và ghi vào báo cáo "vẫn hỏng, cần ticket port".

**`scripts/diag_steady_state.py:68`** import `_points_median_for_distance` — hàm sắp bị xoá. Xoá
nguyên khối `=== (c) Điểm/frame ở trạng thái dừng (lý thuyết) ===` (dòng 66 đến hết phần đó) và dòng
import. Không thay bằng công thức khác: bảng đó đang in ra số từ công thức sai.

### Bước 5 — `scripts/semantic_spray_stats.py`: dùng hằng số thật

File đọc `config.cluster_radius_median_m` ở 3 chỗ (341, 492, 494) để so `r_extent` với giá trị cấu
hình. Sau bước 1 field đó biến mất. Thay bằng hằng số của đường sống:
`from spray.plume_state import RADIUS_MEDIAN_M` và dùng `RADIUS_MEDIAN_M` (0,31 m). **Không** đổi
câu chữ trong report.

### Bước 6 — `scripts/sspp_infer.py`: `n_injected` phải đổi nghĩa

Hai chỗ (596, 605) đọc `stats.get("injected", 0)` để tính `n_real_after` / `n_injected`. Field đó
không còn. Thay bằng **số detection thật của plume**, tức `raycast.stats.det` đã có trong `stats`
của `spray_stats` (`stats["det"]`), và giữ **nguyên tên key** trong jsonl:

```
after      = len(points) - int(stats.get("det", 0))
n_injected = int(stats.get("det", 0))
```

Ghi chú vào chỗ sửa: *"trước A10 `n_injected` đếm điểm materialise `ring=-1` (vô hiệu với detector);
từ A10 nó là số detection plume thật."* Không đổi schema jsonl, không đổi tên key.

---

## 3. Test phải xử lý (đây là phần dễ sai nhất)

| file | việc |
|---|---|
| `tests/test_plume_calibration.py` | xoá import `_injected_budget` (dòng 14) + test `test_injected_budget_is_five_percent_with_a_floor_of_500` (dòng 108-111). **Giữ mọi test khác** — file này giữ chốt calibration. |
| `tests/test_plume_tail_block.py` | xoá `test_no_injected_point_lies_inside_the_body_box` (dòng 158-172, dùng `_inside_box` + `result.injected`); xoá `_inside_box` khỏi import dòng 16; bỏ `"capped"` khỏi `set(fields)` ở test marker (dòng ~233). |
| `tests/test_sspp_plume_integration.py` | 3 test dùng `result.injected` (dòng 76-77) để kiểm "plume nằm trên ĐÁY box". **Viết lại để đọc vị trí cụm** `state.all_alive()` thay vì điểm materialise — giữ nguyên tính chất được kiểm (không được dịch lên `h/2`). Đây là test chống bug quy ước box: **không được xoá**. Nếu không viết lại được trong phạm vi brief, DỪNG và báo PM. |
| `tests/test_plume_wet_integration.py` | bỏ các assert trên `.points` / `.injected` (dòng 67-70, 89, 115). Giữ assert `points_clean` và `stats.wet_*`. Test `test_high_cloud_is_untouched...` đổi `result.points` → `result.points_clean`. |
| `tests/test_raycast.py` | marker từ 6 key còn 5: sửa regex dòng 238-239, bỏ `capped=42` khỏi call, bỏ `assert match.group(5) == "42"`. |
| `tests/test_plume_transform.py` | cùng sửa regex marker dòng 102-103. |

**Không** sửa `tests/test_plume_paper_domain.py`, `tests/test_beam_model.py`,
`tests/test_wet_ground*.py`, `tests/test_plume_lifetime.py`.

---

## 4. Ràng buộc

1. **Không** đổi bất kỳ default nào còn sống: `min_speed_kmh`, `water_film_height_m`,
   `cluster_count_velocity_offset_kmh`, `lifetime_*`, `point_cloud_range`, `sample_water_film`,
   `water_film_mm`.
2. **Không** đụng `spray/plume_state.py`, `spray/plume_context.py`, `spray/wet_ground.py`,
   `spray/beam_model.py`, `spray/sspp_adapter.py`.
3. **Không** sửa logic raycast: `_collect_hits`, `_survival`, P_det, attenuation, `_keep_strongest_per_beam`
   giữ nguyên từng dòng.
4. **Không** sửa `docs/**` và `.scratch/**` — PM cập nhật docs sau.
5. **Không** commit, không `git add`, không push.
6. **Không** "tiện tay" sửa gì khác. Diff chỉ chứa: xoá tầng materialise + sửa call site + sửa test +
   đồng bộ yaml.

---

## 5. Danh sách file được sửa

```
spray/plume.py
spray/raycast.py
spray/plume_transform.py
spray/config/plume_default.yaml
scripts/measure_cdf_over_range.py
scripts/visualize_plume_vs_real.py
scripts/measure_plume_size_tail.py
scripts/visualize_sspp_plume.py
scripts/smoke_sspp_paperpath.py
scripts/measure_following_scenario.py
scripts/diag_steady_state.py
scripts/semantic_spray_stats.py
scripts/sspp_infer.py
scripts/probe_sspp_plume.py      (chỉ đủ để không phát sinh lỗi import MỚI)
tests/test_plume_calibration.py
tests/test_plume_tail_block.py
tests/test_sspp_plume_integration.py
tests/test_plume_wet_integration.py
tests/test_raycast.py
tests/test_plume_transform.py
```

Ngoài danh sách này → **dừng, báo PM**.

---

## 6. Xong khi — phải dán số thật, không tóm tắt

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot

# (a) baseline TRƯỚC khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. \
  /opt/anaconda3/bin/python -m pytest -q tests/ 2>&1 | tail -2
```

**Baseline đo thật ngày 2026-11-26 trên HEAD `d9646ec`: `206 passed in 11.06s`.** Số khác → DỪNG, báo PM.

Sau khi sửa, chạy lại: kỳ vọng **0 failed, 0 error**, số passed giảm đúng bằng số test đã xoá.

```bash
# (b) không còn tham chiếu chết
grep -rn "_count_for_distance\|_POINTS_MEDIAN_BY_RANGE\|_injected_budget\|_points_median_for_distance" \
  --include=*.py . | grep -v baseline_tree | grep -v "\.scratch/"
# => KHÔNG có dòng nào

grep -rn "result\.points\b\|\.injected\b\|stats\.capped\|stats\.rejected_" --include=*.py \
  spray/ tests/ scripts/ | grep -v probe_sspp_plume
# => KHÔNG có dòng nào

grep -rn "capped=" --include=*.py spray/ tests/ scripts/
# => KHÔNG có dòng nào

# (c) BẤT BIẾN SỐ HỌC — det phải trùng khít trước/sau, chạy cả script này 1 lần
#     TRƯỚC khi sửa (ghi số ra file) và 1 lần SAU khi sửa
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python - <<'PY'
import contextlib, io, json
import numpy as np
from spray.beam_model import load_beam_table
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame

TABLE = load_beam_table()
out = {}
for v_kmh in (50, 100, 130):
    v = v_kmh / 3.6
    dets, d_all = [], []
    for s in range(3):
        rng = np.random.default_rng(31337 + s)
        pts = np.zeros((800, 5), dtype=np.float32)
        pts[:, 0] = rng.uniform(2, 45, 800)
        pts[:, 1] = rng.uniform(-6, 6, 800)
        pts[:, 2] = -1.9
        pts[:, 4] = np.arange(800) % 32
        st, cfg = PlumeState(), PlumeConfig()
        per_frame = []
        with contextlib.redirect_stdout(io.StringIO()):
            for f in range(60):
                ox = 20.0 + v * 0.1 * f
                ctx = PlumeContext(scene_token=f"s{s}", frame_index=f, epoch=0,
                    sensor_origin=np.zeros(3), ego_speed_mps=v, object_speed_mps=v,
                    wfh_mm=1.0, road_z_m=-2.0)
                bx = np.array([[ox, 0.0, -2.0, 4.5, 1.9, 1.9, 0.0, v, 0.0]])
                r = inject_plume_stateful(pts, bx, ctx, st, seed=11 + s*100 + f,
                                         token=f"s{s}/{f}", config=cfg)
                ray = raycast_frame(r.points, st.all_alive(), table=TABLE,
                                    road_z_m=-2.0, rng=np.random.default_rng(999 + s*100 + f))
                per_frame.append(int(ray.stats.det))
        dets.append(sum(per_frame))
        d_all.extend(per_frame)
    out[v_kmh] = {"det": dets, "det_total": int(sum(dets)),
                  "per_frame_md5": __import__("hashlib").md5(
                      np.asarray(d_all, dtype=np.int64).tobytes()).hexdigest()}
print(json.dumps(out, indent=2))
PY
```

Chạy bản **TRƯỚC** phải dùng `r.points`; bản **SAU** dùng `r.points_clean` (vì `r.points` không còn).
`det`, `det_total` và `per_frame_md5` phải **giống hệt** — đây là bằng chứng tầng materialise không
tham gia sinh detection. Trước khi sửa hãy chạy đúng script này một lần và **lưu output vào
`/tmp/a10_before.json`**.

```bash
# (d) yaml khít dataclass — xem lệnh ở bước 3, kỳ vọng yaml-only: [] cfg-only: [] roundtrip OK

# (e) import-check toàn bộ scripts/ (A9 dùng đúng cách này)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python - <<'PY'
import pathlib, subprocess, sys
bad = []
for p in sorted(pathlib.Path("scripts").glob("*.py")):
    r = subprocess.run([sys.executable, "-c", f"import importlib.util as u; "
        f"s=u.spec_from_file_location('m', {str(p)!r}); m=u.module_from_spec(s); s.loader.exec_module(m)"],
        capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": "."})
    if r.returncode != 0:
        bad.append((p.name, r.stderr.strip().splitlines()[-1] if r.stderr else ""))
print("FAIL:", bad or 0)
PY
```

Kỳ vọng: chỉ `probe_sspp_plume.py` có thể fail (đã hỏng từ A8, ghi rõ trong báo cáo); mọi file khác
phải import được.

---

## 7. Báo lại

Dán nguyên, không tóm tắt:

1. output của 3 lệnh `grep` ở §6(b);
2. `N passed` **trước** và **sau**, kèm danh sách tên test đã xoá và test đã viết lại;
3. `det`/`det_total`/`per_frame_md5` **trước** (từ `/tmp/a10_before.json`) và **sau** — phải trùng;
4. output §6(d) và §6(e);
5. `git status --short` + `git diff --stat`;
6. nội dung khối `try/except` hoặc `_injected` nào còn sót (nếu có) và vì sao giữ.

Ngoài phạm vi, không làm: port `probe_sspp_plume.py` sang stateful, sửa `T`/lifetime, sửa
`scripts/sspp_infer.py` ở chỗ khác 2 dòng `n_injected`, đổi ngưỡng/`P_det`, sửa docs.

---

## 8. Biên bản nghiệm thu — 2026-11-26

Người nghiệm thu: PM. HEAD sau thi công: `af9b4b2`. Diff: 21 file, +74 / −336.

| Hạng mục | Kết quả | Đo bằng |
|---|---|---|
| pytest | **200 passed, 0 failed** (trước: 206) | `pytest -q tests/`, chạy lại sau commit |
| Bất biến det | **TRÙNG KHÍT** | `diff /tmp/a10_before.json /tmp/a10_after.json` → không khác byte nào. det_total 2945 / 15011 / 3854 @50/100/130, md5 từng frame giống hệt |
| Helper chết | 0 tham chiếu | grep §6(b1) |
| Field chết | 0 tham chiếu | grep §6(b2) |
| `capped=` | còn 4 dòng, đều trong `probe_sspp_plume.py` + test của nó (đã hỏng từ A8) | grep §6(b3) |
| yaml ↔ dataclass | `yaml-only: [] cfg-only: []`, mọi giá trị bằng default | script §6(d) |
| import-check scripts/ | 3 FAIL, **cả 3 y hệt trên HEAD `d9646ec`** (thiếu `scripts/` trên sys.path) | chạy harness trên HEAD sạch để đối chứng |
| pyflakes file đã sửa | 6 cảnh báo, **giống hệt HEAD**, không phát sinh mới | pyflakes trên HEAD sạch rồi so |
| wet-ground physics | 15 test `-k wet` pass | `pytest -k wet` |

### Hai việc ngoài danh sách §5 — chấp nhận

1. `tests/test_box_convention.py` (ngoài §5) import `_inside_box` và có 2 test gọi trực tiếp nó. Xoá
   `_inside_box` ⇒ ImportError. Worker xoá 2 test đó. **Đã kiểm lại bằng mutation**: đổi
   `length = box[3]` → `box[4]` trong `spray/plume.py:397` làm **2 test khác đỏ**
   (`test_spawn_box_is_the_reference_slab_behind_the_tail`, `test_spawn_box_matches_the_reference_slab`),
   và trục z vẫn bị `test_box_z_is_bottom_not_centre` khoá. ⇒ Bất biến quy ước box **không mất**,
   phần bị xoá chỉ là unit test của chính hàm helper vừa xoá.
2. `test_sspp_paperpath.py::test_wet_ground_lowers_background_intensity` đọc suy giảm từ
   `result.points` (không còn). Worker chuyển sang `stats.wet_mean_ratio ∈ (0,1)`. Đo độc lập trên máy
   này: bật wet-ground ⇒ `wet_points_in=500`, `mean_ratio=0.526`, `points_clean` **không đổi byte nào**
   so với input ⇒ tính chất "chỉ hạ, không tăng" vẫn đúng và vẫn được kiểm.

### Kết luận: **ACCEPT**

---

## 9. Nợ còn lại sau A10 (không thuộc phạm vi brief này)

| # | Nợ | Bằng chứng |
|---|---|---|
| 9.1 | `plume_transform.py:150` vẫn `stats["injected"] = int(raycast.stats.det)` — key trùng nghĩa với `"det"`, không ai đọc | grep `"injected"` trong `spray/ scripts/ tests/` → chỉ còn dòng này |
| 9.2 | `apply_wet_ground` tính xong rồi **vứt** (`_, wet_stats = ...`). Đo: 38,9 ms/frame trên 40k điểm cho output không đổi một byte | det 14046 = 14046 với `wet_ground` on/off; `points_clean` identical với input |
| 9.3 | docstring `PlumeConfig` còn câu "bù hình học, biên an toàn" — cụm từ của tầng vừa xoá | `plume.py:86` |
| 9.4 | ~25 dòng trong `docs/` còn mô tả tầng đã xoá (`_POINTS_MEDIAN_BY_RANGE`, `result.injected`, `radial_squash`, `stats.capped`…) | `docs/measurements/a3-parameter-provenance.md`, `plume-a3-diagnosis.md`, `generator-reading-map.md`, `sspp-cluster-radius-by-speed.md`, `sspp-plume-probe.md` |
| 9.5 | `probe_sspp_plume.py` + `tests/test_probe_sspp_plume.py` vẫn hỏng / còn nhắc `capped` | A8 |
