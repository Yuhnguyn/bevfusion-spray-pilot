# Plan: train BEVFusion LiDAR-only với plume augmentation — nuScenes làm nền, SSPP làm thước đo

> **Trạng thái:** plan thi công, chưa phải brief. Task nào giao CommandCode thì tách thành
> `.scratch/nuscenes-train/issues/<NN>-<slug>.md` theo skill `coding-agent-cli-handoff`.
>
> **Supersedes:** `.hermes/plans/2026-11-26_155812-nuscenes-train-plan.md`.
> Phần **giữ lại** từ plan cũ: mục 0.2 (miền hình học), 0.3 (quy ước box nuScenes khác adapter),
> 0.4 (máy này không train được), QĐ-B (eval ở SSPP), QĐ-C (LiDAR-only).
> Phần **bỏ**: QĐ-A hỏi "nuScenes chậm thì làm gì" (đã có câu trả lời của user — Task 7),
> Task 5 "dùng lại `kaggle/e2e/main.py` bên `main`" (file đó không tồn tại trên nhánh này),
> toàn bộ cách nối `SprayContextTransform` trực tiếp vào dataloader (Task 12–15 thay bằng cache).

---

## Goal

Fine-tune BEVFusion LiDAR-only có **plume spray tổng hợp** trong lúc train, để detector bớt báo
nhầm khi gặp bụi nước thật; đo bằng **paired A/B** (arm A sạch vs arm B có plume) rồi eval
zero-shot trên SSPP.

## Current context / assumptions

### Nhánh và môi trường (đo trên máy này, 2026-11-26)

```
nhánh           nuscenes-train @ 6ca2d6c
pytest          200 passed (51,3 s)
torch           2.2.2 CPU · i5-8210Y · 8,6 GB · KHÔNG CUDA, KHÔNG MPS
nuscenes, mmdet3d, mmcv, spconv, open3d     cả 5 MISSING
sklearn 1.2.2, scipy 1.17.1, pandas 2.2.0, pyyaml 6.0.1   có
data/           16 GB SSPP + 18 GB roadspray + lidar-only-det.pth (33.362.653 B)
nuScenes        0 byte  ·  đĩa trống 28 GiB
```

⇒ **Train bắt buộc chạy Kaggle.** Máy local chỉ làm unit test, dựng cache, và đo.

### Hai đầu vào từ user (chốt, không bàn lại)

1. **"Đầu vào không có vận tốc ⇒ nuScenes thì random vận tốc ra cũng được."**
   Đúng về mặt kỹ thuật: tốc độ chỉ đi vào `PlumeContext`, không đi vào `points` mà model nhận.
   Đây là lời giải cho cái chết của plan cũ (generator sinh **0 cụm** ở mọi v < 50 km/h, đo:
   `v=49 → 0`, `v=50 → 9`). Plume lấy tốc độ **lấy mẫu trong miền hiệu chuẩn của paper
   (50–130 km/h)**, không lấy tốc độ ego thật của frame. Hệ quả phải khai trong báo cáo:
   plume **không phải** "spray mà frame này sẽ có nếu xe chạy đúng tốc độ đó".

2. **"36 scene SSPP có box thật, các scene còn lại dựng pseudo box được, 3D IoU > 90 %."**
   Đã đo và validate sẵn trong repo: `.scratch/roadspray-cal/pseudo-boxes.md` — BEV IoU
   **p50 0,931 / p5 0,847**, 3D IoU **p50 0,872 / p5 0,744**, 99,8 % frame ≥ 0,7, gate pass
   99,7 %. Nhưng **script chưa tồn tại** (`scripts/build_sspp_pseudo_boxes.py` = MISSING);
   quyết định ADR-0006 D4 mới chỉ nằm trên giấy.

### Bốn lỗ của plan cũ, đã đo lại

| # | Lỗ | Số đo | Hệ quả |
|---|---|---|---|
| 1 | `PlumeTransform` **không truyền `dt`** ⇒ generator dùng 0,1 s trong khi nuScenes keyframe cách **0,5 s** | cụm sống 2,26 s thực vs 0,40 s danh nghĩa @60 km/h (**5,7×**); 5,2× @100; 5,1× @130 | plume loãng còn ~1/5 |
| 2 | `PlumeTransform` giữ `self._state`; `set_epoch` **0 call site** trên toàn repo | `workers_per_gpu ≥ 1` ⇒ frame liên tiếp vào 4 process, mỗi process một `PlumeState` | mật độ plume sai, không có lỗi nào bật ra |
| 3 | Plan cũ Task 5 đòi "dùng lại `kaggle/e2e/main.py` bên `main`" | file đó **MISSING** trên nhánh này (xoá ở `c2aa23c`) | vi phạm chính yêu cầu "không restore từ main" |
| 4 | nuScenes nhiều box/frame vs SSPP **đúng 1 box/frame** (đo: 1124/1124) | **đã giải quyết bằng thiết kế**: `select_lead_box` chỉ chọn **1** xe dẫn phía trước là ô tô ⇒ mỗi frame 0 hoặc 1 nguồn phun, raycast ~25 ms, trả một lần lúc dựng cache | rủi ro còn lại **không phải chi phí** mà là **phủ**: nếu ít frame có xe dẫn thì arm B thưa plume (census T11 đo trước) |

Lỗ 1 đo trực tiếp (script trong `verify` của Task 2):

```
v(km/h)  đích cụm/frame   dt=0,1×1   dt=0,5×1   dt=0,5×5(=5 bước 0,1 s)
   60           9            9,0        2,7          7,5
   80          18           20,6        3,2         17,8
  100          23           22,5        5,0         21,9
  130          25           17,8        3,7         17,2
```

⇒ Cách sửa đúng là **giữ chu kỳ 0,1 s của paper và lặp 5 lần cho mỗi keyframe nuScenes**,
không phải nhét `dt=0,5` vào một bước. Sau khi sửa, đích khớp lại trong ±10 %.

### Thiết kế né lỗ 1+2+4 trong một lần: **cache plume offline**

`PlumeTransform` stateful không sống được trong dataloader song song (bẫy 13 của skill
`spray-pilot-ops`). Thay vì vá, ta **sinh plume một lần, tuần tự, đúng `dt`, rồi cache theo
token**. Lúc train chỉ còn một transform không trạng thái: đọc cache, nối điểm.

```
token ──► PlumeCacheTransform ──► points (N+M,5) + points_clean (N,5)
                 ▲
                 └── data/plume_cache/<name>.npz  (sinh bởi scripts/build_plume_cache.py)
```

Lợi: deterministic (mọi epoch cùng một đám mây), an toàn mọi số worker, raycast trả tiền **một
lần** offline thay vì mỗi bước, và eval dùng được đúng đám mây mà train đã thấy.

### Plume chỉ sinh khi **có xe dẫn phía trước** — điều kiện vật lý, không phải tuỳ chọn

Đây là quyết định thiết kế quan trọng nhất về mặt *dữ liệu*, và nó giải quyết luôn vấn đề nhiều
lớp của nuScenes.

Plume là nước bắn lên từ bánh của **xe đang chạy trước ego** — paper A §III-B gọi vùng đó là
*"spray filter region behind the vehicle"* và calibration của họ chỉ dùng bag
`object_direction = +1` (ego nhìn thấy đuôi xe; `−1` là xe ngược chiều, plume bị che). Nên:

```
boxes nuScenes (10 lớp)
   → lọc lớp: chỉ "car" và "truck"          (select_lead_box; generator chỉ có bảng crafter/golf)
   → lọc hình học: x > 0, x ≤ 50, |y| ≤ 5
   → chọn 1: x nhỏ nhất (xe ego đang bám), hoà thì |y| nhỏ nhất
   → 0 hoặc 1 box  ⇒ 0 hoặc 1 nguồn phun mỗi frame
```

Bốn hệ quả, đều tốt:

1. **Không crash vì lớp lạ.** `cluster_visible_target_for_speed(100.0, "pedestrian")` đang
   `raise ValueError`; lọc lớp ở đây chặn trước khi tới generator.
2. **Chi phí về 1 nguồn phun/frame** thay vì ~10 ⇒ raycast ~25 ms, và chỉ trả lúc dựng cache.
3. **Đúng vật lý.** Phun nước sau bánh xe đạp hay người đi bộ là sai; spray chỉ có sau ô tô.
4. **Khớp miền paper.** 50 m và ±5 m chính là miền mà generator được đo và hiệu chuẩn.

**Cái giá phải đo ngay:** nếu phần lớn frame nuScenes không có xe dẫn (đường đô thị, ego chạy
một mình, xe dẫn đang rẽ), arm B gần như không có plume và thí nghiệm thành A vs A. Task 11
(census) đo chính xác `%` frame có xe dẫn **trước khi** dựng cache, và có ngưỡng dừng.

### Ba số chặn đường về phía khoa học (đo trên dữ liệu gate C đã có)

Cổng C (`docs/measurements/gate-c-result.md`, 954 frame, 12 scene, paired):

```
Δrecall(plume − clean) = −0,2188  [−0,295; −0,156]
Δrecall(real  − clean) = −0,0441
cơ chế: 20,1 % hộp đúng chỗ tụt score dưới τ; điểm thật bị xoá chỉ 0,0175 %/frame
```

⇒ Lúc **eval** plume hiện tại hại gấp ~5× spray thật. Đó là lý do phải **train** với nó:
giả thuyết là model học được "bỏ qua" chữ ký đó. Falsification ở §Risks.

Độ phân giải phép đo, tính từ chính dữ liệu gate C (paired theo scene):

```
Δdet/frame(plume − clean) = +3,25   sd 1,93     ← can thiệp sẽ train
Δdet/frame(real  − clean) = +2,07   sd 0,77     ← tham chiếu: spray thật
mức nền clean             = 16,2 det/frame
MDE 80 % power, α 0,05, hai phía, test paired theo scene:
   n=12  → 1,56 det/frame (9,6 % nền)   [dùng plume, sd 1,93]
   n=36  → 0,90 det/frame (5,6 % nền)
   n=207 → 0,38 det/frame (2,3 % nền)
```

### Số liệu SSPP để thiết kế split (đo lại hôm nay, không chép doc)

```
207 scene / 17.419 frame
 36 scene human box / 2.587 frame     (tất cả itr_after_water = 1)
171 scene không box  / 14.832 frame   (itr 2…6)
9 tốc độ: 50,60,…,130 — human chỉ có 36 scene, mỗi tốc độ đúng 4 scene
fold = rank(tốc độ) mod 3 + 1:
  fold1 test [50,80,110]  train 24 human/1.701fr + 115 pseudo/9.011fr
  fold2 test [60,90,120]  train 24 human/1.694fr + 116 pseudo/10.387fr
  fold3 test [70,100,130] train 24 human/1.779fr + 111 pseudo/10.266fr
pooled test human = 36 scene (đúng ADR-0006 D1); pooled test human+pseudo = 207 scene
```

Nếu dùng được pseudo cho eval thì công suất tăng **2,4×** so với n=36 — nhưng đó là **hàng phụ**,
không phải hàng quyết định (§Task 24).

---

## Architecture / proposed approach

**Ba tầng, mỗi tầng một artifact kiểm được bằng máy:**

1. **Tầng sinh** — sửa `inject_plume_stateful` nhận `substeps` (giữ chu kỳ 0,1 s, lặp cho frame
   dài), thêm `spray/nuscenes_context.py` dựng `PlumeContext` từ info dict nuScenes với tốc độ
   **lấy mẫu seed hoá**, và `scripts/build_plume_cache.py` chạy tuần tự từng scene rồi ghi
   `data/plume_cache/<name>.npz`.
2. **Tầng train** — `spray/plume_cache_transform.py` (không trạng thái) + `spray/ab_config.py`
   dựng hai arm, `diff_paths()` chứng minh khác **đúng một** đường. Kernel Kaggle mới
   `kaggle/train_nuscenes/`, dựng từ đầu — **không** chép file nào của `main`.
3. **Tầng chấm** — `scripts/build_sspp_pseudo_boxes.py` mở khoá 171 scene, `data/sspp_folds.json`
   cho 3 fold, và `scripts/ab_eval.py` chấm 3 checkpoint (Model 0 / A / B) trên cùng frame.

---

## Step-by-step tasks

> Mọi lệnh chạy từ root repo. Python của repo: `/opt/anaconda3/bin/python`, **luôn** có
> `CONDA_NO_PLUGINS=true env -u PYTHONPATH` và `PYTHONPATH=.`.
> Đặt tắt: `PY="CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python"`

### Phase 0 — Chốt trạng thái (làm trước, 10 phút)

#### T1. Đóng session đang ghi song song

**Vấn đề:** PID 51404 (Hermes) sống từ 15:07 và đã commit `ba9c705` (16:01) + `6ca2d6c` (16:02)
trong lúc agent khác đang đọc repo. Hai agent ghi cùng một worktree ⇒ `git add -A` của bên này
nuốt file bên kia.

**Làm (user tự làm, không phải agent):** đóng session đó, hoặc xác nhận chỉ còn một agent.

**Verify:**

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
git log --format='%h %ci %s' -1; sleep 20; git log --format='%h %ci %s' -1
```

Kỳ vọng: hai dòng **giống hệt nhau**. Khác ⇒ còn process khác, dừng lại.

#### T2. Ghi baseline đo được thành file, để mọi con số sau này có mốc

**Files:** tạo `.scratch/nuscenes-train/BASELINE.md`

**Nội dung (đúng những gì đo được, không suy):**

```markdown
# Baseline đo 2026-11-26, nhánh nuscenes-train @ 6ca2d6c

| hạng mục | số |
|---|---|
| pytest | 200 passed, 51,3 s |
| lidar-only-det.pth | 33.362.653 byte |
| SSPP | 207 scene / 17.419 frame; 36 human box / 2.587 frame; 171 không box / 14.832 frame |
| nuScenes Mini `[ĐO]` 2026-11-27 | 10 scene / 404 keyframe / 18.538 annotation / 3.531 sweep @20 Hz; keyframe 0,50 s |
| Mini vehicle/frame `[ĐO]` | mean 21,5 · p50 16 · p95 52 · max 57 |
| Mini `with_lead` `[ĐO]` | 71,5 % (289/404) — nhưng **ảo**, xem dòng dưới |
| Mini `spawnable` (lead_x ≥ 6,49 m) `[ĐO]` | **21,5 %** (87/404) · `lead_x` p50 **3,4 m** · ego p50 **18,4 km/h** |
| gate C Δrecall(plume−clean) | −0,2188 [−0,295; −0,156] |
| Δdet/frame(plume−clean) | +3,25, sd 1,93 (12 scene) — can thiệp sẽ train |
| Δdet/frame(real−clean) | +2,07, sd 0,77 (12 scene) — tham chiếu spray thật |
| MDE 80 % power (sd plume 1,93) | n=12: 1,56 · n=36: 0,90 · n=207: 0,38 det/frame |
| raycast | 9 cụm 25 ms · 36 cụm 35 ms · 108 cụm 62 ms · 300 cụm 202 ms |
| generator < 50 km/h | 0 cụm ở mọi tốc độ (bảng `_CLUSTER_VISIBLE_BY_SPEED` bắt đầu ở 50) |
| generator lớp xe | chỉ có `crafter`, `golf`; lớp khác → `ValueError` |
| full `v1.0-trainval` `spawnable` | **CHƯA ĐO** — census phải chạy lại trước khi train thật |
```

**Verify:**

```bash
wc -l .scratch/nuscenes-train/BASELINE.md && grep -c '|' .scratch/nuscenes-train/BASELINE.md
```

Kỳ vọng: ≥ 12 dòng, ≥ 16 dòng có `|`.

**Commit:** `docs(nuscenes): ghi baseline đo được trước khi thi công`

---

### Phase 1 — Giữ chu kỳ 0,1 s khi frame dài hơn 0,1 s (lỗ 1)

> **Vì sao được phép sửa `spray/plume.py`:** đây **không** phải đổi tham số generator
> (`PlumeConfig`, mật độ, bán kính, ngưỡng tốc độ giữ nguyên). Đây là sửa **bộ tích phân** để
> nó chạy đúng số chu kỳ 0,1 s mà paper định nghĩa, khi caller có frame không phải 0,1 s.
> Nếu user không đồng ý sửa generator: dùng phương án B ở Task 3b (không sửa `plume.py`).

#### T3. Test đỏ: `substeps` phải nhân đúng số cụm

**Files:** tạo `tests/test_plume_substeps.py`

```python
"""``inject_plume_stateful`` phải chạy đúng số chu kỳ 0,1 s, không phụ thuộc ``dt``."""

import numpy as np
import pytest

from spray.plume import PlumeConfig, visible_cluster_count_for_speed
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState

BOX = np.array([[20.0, 0.0, 0.0, 4.25, 2.02, 1.50, 0.0, 0.0, 0.0]], dtype=np.float32)


def _context(speed_kmh, frame_index):
    return PlumeContext(
        scene_token="scene-substeps",
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=speed_kmh / 3.6,
        object_speed_mps=speed_kmh / 3.6,
        wfh_mm=1.0,
        road_z_m=-0.36,
    )


def _steady_alive(speed_kmh, frame_dt, substeps, frames=40, seed=0):
    from spray.plume import inject_plume_stateful

    rng_state = PlumeState()
    clean = np.zeros((10, 5), dtype=np.float32)
    seen = []
    for index in range(frames):
        context = _context(speed_kmh, index)
        inject_plume_stateful(
            clean,
            BOX,
            context,
            rng_state,
            seed=seed,
            config=PlumeConfig(),
            dt=frame_dt,
            substeps=substeps,
            vehicle_class="golf",
        )
        seen.append(len(rng_state.select_alive()))
    return float(np.mean(seen[-10:]))


@pytest.mark.parametrize("speed_kmh", [60.0, 100.0])
def test_substeps_recover_the_paper_cycle(speed_kmh):
    target = visible_cluster_count_for_speed(speed_kmh, PlumeConfig(), "golf")
    assert target > 0
    one_cycle = _steady_alive(speed_kmh, 0.1, 1)
    long_frame = _steady_alive(speed_kmh, 0.5, 5)
    assert one_cycle == pytest.approx(target, rel=0.25)
    assert long_frame == pytest.approx(one_cycle, rel=0.20)


def test_single_step_long_frame_under_spawns():
    """Chứng minh lỗi cũ: dt=0,5 một bước ⇒ thiếu cụm rất nhiều."""
    target = visible_cluster_count_for_speed(100.0, PlumeConfig(), "golf")
    broken = _steady_alive(100.0, 0.5, 1)
    assert broken < 0.5 * target
```

**Chạy:**

```bash
PY="CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python"
$PY -m pytest tests/test_plume_substeps.py -q 2>&1 | tail -5
```

Kỳ vọng: **fail** với `TypeError: inject_plume_stateful() got an unexpected keyword argument 'substeps'`.

#### T4. Implement `substeps`

**File:** sửa `spray/plume.py`, hàm `inject_plume_stateful` (khoảng dòng 316–460).

**Thay đổi 1 — signature:** thêm sau `dt: float = _UPDATE_CYCLE_TIME_S,`:

```python
    substeps: int = 1,
```

**Thay đổi 2 — docstring:** thêm một gạch đầu dòng vào phần mô tả:

```
    - ``substeps``: số chu kỳ 0,1 s gộp trong một lần gọi. ``dt`` là độ dài
      **một** chu kỳ; tổng thời gian một lần gọi là ``dt * substeps``. Frame
      0,1 s (SSPP) dùng ``substeps = 1``; keyframe 0,5 s (nuScenes) dùng
      ``substeps = 5``. Không đổi mô hình — chỉ chạy đúng số chu kỳ.
```

**Thay đổi 3 — thân hàm.** Đây là chỗ dễ sửa sai nhất, nên làm đúng theo số dòng hiện tại của
`spray/plume.py` (đọc lại file trước khi sửa — dòng có thể đã trôi):

| dòng hiện tại | nội dung | xử lý |
|---|---|---|
| 362–364 | `box_arr`, `rng`, `stats = PlumeStats()` | **giữ nguyên tại chỗ** |
| 366–369 | `state.advance(...)` + `expired = state.prune(...)` | **CẮT RA**, để dành cho bước 4 |
| 371–384 | khối `wfh` (`if water_film_mm is not None: ... elif sample_water_film: ...`) | **giữ nguyên tại chỗ**, và **ở ngoài** vòng `substeps` — một lần gọi chỉ lấy mẫu `wfh` một lần |
| 386–387 | `spawned = 0` / `assumed = False` | giữ nguyên, thêm `expired = 0` cạnh đó |
| 388–447 | vòng `for index, box in enumerate(box_arr):` | **lùi thêm 4 cột** (nằm trong vòng `substeps`) |
| 449 | `stats.clusters = len(state.select_alive())` | giữ nguyên, **sau** vòng `substeps` |

Bước 4 — hai khối vừa cắt (advance/prune) **dán xuống ngay trước** vòng `for index, box`,
và bọc tất cả trong vòng `substeps`. Kết quả phải đúng như sau (từ dòng 362 tới 452):

```python
    box_arr = _as_boxes(boxes)
    rng = _rng(seed, token or context.scene_token)
    stats = PlumeStats()

    # [PAPER §V] mức ẩm: ... (giữ nguyên khối 371–384, KHÔNG nằm trong vòng dưới)
    if water_film_mm is not None:
        context = replace_context_wfh(context, float(water_film_mm))
        wfh_marker = f"fixed={float(water_film_mm):g}"
    elif sample_water_film:
        context = replace_context_wfh(context, sample_wfh_mm(
            context.scene_token, context.epoch, seed
        ))
        wfh_marker = f"sampled={context.wfh_mm:g}"
    else:
        wfh_marker = f"caller={context.wfh_mm:g}"

    steps = max(1, int(substeps))
    spawned = 0
    assumed = False
    expired = 0
    for _ in range(steps):
        state.advance(
            dt, ego_velocity=np.array([context.ego_speed_mps, 0.0, 0.0])
        )
        expired += state.prune(dt=dt, rng=rng)

        for index, box in enumerate(box_arr):
            # ... toàn bộ thân vòng box 388–447, chỉ lùi thêm 4 cột ...
            if created:
                stats.eligible_boxes += 1
                stats.clusters_spawned += len(created)
                spawned += len(created)
                assumed = assumed or any(
                    cluster.velocity_assumed for cluster in created
                )

    stats.clusters = len(state.select_alive())
```

**Thay đổi 5 — marker:** trong `print("PLUME_STATE ...")`, thêm `f"substeps={steps} "` để log
đọc được số chu kỳ mỗi lần gọi.

**Chạy:**

```bash
$PY -m pytest tests/test_plume_substeps.py -q 2>&1 | tail -5
```

Kỳ vọng: `3 passed`.

**Rồi chạy toàn bộ để chắc không phá gì:**

```bash
$PY -m pytest -q 2>&1 | tail -3
```

Kỳ vọng: `203 passed` (200 cũ + 3 mới). Nếu test cũ đỏ ⇒ đọc diff, `substeps=1` phải là no-op
tuyệt đối.

**Commit:** `fix(plume): chạy đúng số chu kỳ 0,1 s khi frame dài hơn (substeps)`

#### T3b. Phương án B — nếu user không cho sửa `spray/plume.py`

Gọi `inject_plume_stateful` **5 lần** với `dt=0.1` và seed khác nhau trong
`scripts/build_plume_cache.py` (Task 14), bỏ `substeps`. Đổi lại:
- spawn slab mỗi lần là 0,1 s ⇒ đúng;
- nhưng `print` marker 5×/frame và `points_clean` trả 5 lần (bỏ);
- phải seed `base_seed + substep` để 5 lần không bốc cùng một dãy.

Chọn B thì **bỏ T4**, giữ nguyên T3 (sửa test thành helper trong script, không đụng
`inject_plume_stateful`).

---

### Phase 2 — PlumeContext cho nuScenes + tốc độ lấy mẫu (đầu vào của user)

#### T5. Test đỏ: đổi box nuScenes sang quy ước adapter

**Files:** tạo `tests/test_nuscenes_context.py`

```python
"""Box nuScenes [x,y,z_tâm,w,l,h,yaw] -> quy ước plume [x,y,z_đáy,dài,rộng,cao,yaw,vx,vy]."""

import numpy as np
import pytest

from spray.nuscenes_context import nuscenes_boxes_to_plume

# Xe 4,60 × 1,90 × 1,75 m, tâm ở 10 m, đáy cách mặt đường 0,30 m.
NU_BOX = np.array(
    [[10.0, 0.0, 1.175, 1.90, 4.60, 1.75, 0.25]], dtype=np.float32
)
VELOCITY = np.array([[12.0, 1.0]], dtype=np.float32)


def test_z_is_bottom_not_centre():
    out = nuscenes_boxes_to_plume(NU_BOX, VELOCITY)
    assert out.shape == (1, 9)
    assert out[0, 2] == pytest.approx(1.175 - 1.75 / 2.0)


def test_length_slot_holds_the_long_side():
    out = nuscenes_boxes_to_plume(NU_BOX, VELOCITY)
    # box[3] = dài (dọc yaw) = 4,60; box[4] = rộng = 1,90. KHÔNG swap.
    assert out[0, 3] == pytest.approx(4.60)
    assert out[0, 4] == pytest.approx(1.90)
    assert out[0, 5] == pytest.approx(1.75)


def test_yaw_and_velocity_are_carried_through():
    out = nuscenes_boxes_to_plume(NU_BOX, VELOCITY)
    assert out[0, 6] == pytest.approx(0.25)
    assert out[0, 7] == pytest.approx(12.0)
    assert out[0, 8] == pytest.approx(1.0)


def test_empty_input_is_empty_output():
    out = nuscenes_boxes_to_plume(np.zeros((0, 7), dtype=np.float32), None)
    assert out.shape == (0, 9)


def test_velocity_may_be_missing():
    out = nuscenes_boxes_to_plume(NU_BOX, None, gt_names=np.array(["car"]))
    assert out[0, 7] == 0.0 and out[0, 8] == 0.0


def test_only_vehicle_classes_spray():
    """Pedestrian/bicycle không có bánh phun nước — và generator không có bảng cho chúng."""
    boxes = np.vstack([NU_BOX, NU_BOX, NU_BOX])
    names = np.array(["car", "pedestrian", "truck"])
    out = nuscenes_boxes_to_plume(boxes, None, gt_names=names)
    assert out.shape == (2, 9)


def test_velocity_is_filtered_with_the_boxes():
    boxes = np.vstack([NU_BOX, NU_BOX])
    names = np.array(["car", "bicycle"])
    velocity = np.array([[12.0, 1.0], [3.0, 0.0]], dtype=np.float32)
    out = nuscenes_boxes_to_plume(boxes, velocity, gt_names=names)
    assert out.shape == (1, 9)
    assert out[0, 7] == pytest.approx(12.0)   # vận tốc của car, không phải của bicycle


def test_unknown_class_never_reaches_the_generator():
    """Bảo vệ chống crash: bảng cụm chỉ có crafter/golf."""
    boxes = np.vstack([NU_BOX])
    out = nuscenes_boxes_to_plume(boxes, None, gt_names=np.array(["pedestrian"]))
    assert out.shape == (0, 9)


def test_none_keeps_every_box():
    boxes = np.vstack([NU_BOX, NU_BOX])
    out = nuscenes_boxes_to_plume(
        boxes, None, gt_names=np.array(["car", "pedestrian"]), plume_classes=None
    )
    assert out.shape == (2, 9)


def test_missing_names_with_default_filter_raises():
    with pytest.raises(ValueError, match="gt_names is required"):
        nuscenes_boxes_to_plume(NU_BOX, None)


# --- chọn xe dẫn ---------------------------------------------------------

def _plume_box(x, y=0.0, length=4.6):
    return [x, y, 0.3, length, 1.9, 1.75, 0.0, 0.0, 0.0]


def test_lead_box_is_the_nearest_vehicle_ahead():
    boxes = np.array(
        [_plume_box(30.0), _plume_box(12.0), _plume_box(45.0)], dtype=np.float64
    )
    lead = select_lead_box(boxes)
    assert lead.shape == (1, 9)
    assert lead[0, 0] == pytest.approx(12.0)


def test_no_lead_box_when_every_vehicle_is_behind_the_ego():
    """Xe đi ngược chiều hoặc đỗ phía sau ⇒ không có plume."""
    boxes = np.array([_plume_box(-8.0), _plume_box(-25.0)], dtype=np.float64)
    assert select_lead_box(boxes).shape == (0, 9)


def test_no_lead_box_beyond_the_generator_range():
    boxes = np.array([_plume_box(62.0)], dtype=np.float64)
    assert select_lead_box(boxes).shape == (0, 9)


def test_no_lead_box_in_another_lane():
    boxes = np.array([_plume_box(20.0, y=7.5)], dtype=np.float64)
    assert select_lead_box(boxes).shape == (0, 9)


def test_tie_breaks_toward_the_ego_lane():
    boxes = np.array(
        [_plume_box(20.0, y=3.0), _plume_box(20.0, y=-0.5)], dtype=np.float64
    )
    lead = select_lead_box(boxes)
    assert lead[0, 1] == pytest.approx(-0.5)


def test_empty_input_selects_nothing():
    assert select_lead_box(np.zeros((0, 9))).shape == (0, 9)
```

**Chạy:** `$PY -m pytest tests/test_nuscenes_context.py -q`
Kỳ vọng: `ModuleNotFoundError: No module named 'spray.nuscenes_context'`.

#### T6. Implement `nuscenes_boxes_to_plume`

**Files:** tạo `spray/nuscenes_context.py`

```python
"""Dựng ``PlumeContext`` cho nuScenes.

Hai việc, tách hẳn để test được từng cái:

1. :func:`nuscenes_boxes_to_plume` — đổi quy ước box. nuScenes/mmdet3d dùng
   ``[x, y, z_TÂM, w, l, h, yaw]`` (``nuscenes_converter.py:276``), còn
   ``inject_plume_stateful`` đọc ``[x, y, z_ĐÁY, dài, rộng, cao, yaw, vx, vy]``
   (``spray/sspp_adapter.py:117,141``). Lẫn hai quy ước làm plume phun vào thân xe
   và lơ lửng 0,87 m trên mặt đường, mà không có lỗi nào bật ra.
2. :func:`sample_augmented_speed_kmh` — chọn tốc độ cho plume.

**Tốc độ là LẤY MẪU, không phải tốc độ ego thật.** nuScenes đô thị chạy chậm;
generator chỉ có số đo từ 50 km/h trở lên (``_CLUSTER_VISIBLE_BY_SPEED``) và trả
0 cụm dưới mốc đó. Vì đầu vào của detector không chứa vận tốc, plume dùng một
tốc độ **trong miền hiệu chuẩn của paper** là hợp lệ — chỉ phải khai rõ trong báo
cáo rằng đây không phải tốc độ của frame.
"""

from __future__ import annotations

import numpy as np

# 9 mốc đo của paper, dùng làm giá trị rời rạc thay vì nội suy liên tục: mỗi mốc
# đều có số đo thật đứng sau (``_CLUSTER_VISIBLE_BY_SPEED``), không mốc nào bịa.
MEASURED_SPEEDS_KMH: tuple[float, ...] = (
    50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0,
)

PLUME_BOX_DIM = 9


def select_lead_box(
    boxes: np.ndarray,
    *,
    max_range_m: float = 50.0,
    max_lateral_m: float = 5.0,
    ahead_only: bool = True,
) -> np.ndarray:
    """Chọn **một** xe dẫn để phun plume, hoặc box rỗng.

    Đây là điều kiện vật lý, không phải mẹo né nhiều lớp. Plume sinh ra từ nước
    bắn lên sau bánh **xe đang chạy trước ego**; nó chỉ tồn tại khi ego đang bám
    đuôi một xe. Không có xe dẫn ⇒ không có spray.

    3 điều kiện, mỗi điều có nguồn:

    - ``ahead_only``: ``x > 0``. Paper A §III-B: *"spray filter region behind the
      vehicle"* — ego nhìn thấy **đuôi** xe, tức xe ở phía trước. Đây cũng là
      lý do một nửa campaign RoadSpray (``object_direction = −1``) bị loại khỏi
      calibration: xe đi ngược chiều thì plume bị che.
    - ``max_range_m``: ``x <= 50``. Trùng ``PlumeStateConfig.max_range_m`` của
      generator; box xa hơn thì cụm sinh ra cũng bị lọc bỏ.
    - ``max_lateral_m``: ``|y| <= 5``. Trùng nửa chiều rộng vùng đo A3-V
      (``REGION_HALF_WIDTH_M``) — xe lệch quá 5 m thì plume không còn nằm sau
      đuôi mà đã sang làn khác.

    Nếu nhiều box thoả: lấy box có ``x`` **nhỏ nhất** (xe ngay trước ego) — đó
    là xe mà ego đang bám, và cũng là xe mà plume của nó rơi gần cảm biến nhất,
    tức tín hiệu mạnh nhất. Hoà thì lấy ``|y|`` nhỏ nhất.
    """
    if boxes.size == 0:
        return np.zeros((0, PLUME_BOX_DIM), dtype=np.float64)
    array = np.asarray(boxes, dtype=np.float64).reshape(-1, PLUME_BOX_DIM)
    keep = np.ones(array.shape[0], dtype=bool)
    if ahead_only:
        keep &= array[:, 0] > 0.0
    keep &= array[:, 0] <= max_range_m
    keep &= np.abs(array[:, 1]) <= max_lateral_m
    candidates = array[keep]
    if candidates.shape[0] == 0:
        return np.zeros((0, PLUME_BOX_DIM), dtype=np.float64)
    order = np.lexsort((np.abs(candidates[:, 1]), candidates[:, 0]))
    return candidates[order[:1]]


def nuscenes_boxes_to_plume(
    gt_boxes: np.ndarray | None,
    gt_velocity: np.ndarray | None = None,
    gt_names: np.ndarray | None = None,
    plume_classes: tuple[str, ...] = ("car", "truck"),
) -> np.ndarray:
    """``[x,y,z_tâm,w,l,h,yaw]`` (+ vận tốc) → ``[x,y,z_đáy,dài,rộng,cao,yaw,vx,vy]``.

    Chỉ giữ box thuộc ``plume_classes``. Bắt buộc: generator chỉ có bảng cụm cho
    hai lớp ``crafter``/``golf`` và **raise** với lớp khác
    (``cluster_visible_target_for_speed(100.0, "pedestrian")`` → ``ValueError``).
    Ngoài ra phun nước sau bánh xe đạp hay người đi bộ là sai vật lý — paper A
    đo trên xe hạng nhẹ.

    ``plume_classes=None`` giữ **mọi** box (dùng cho test và cho probe).
    """
    if gt_boxes is None:
        return np.zeros((0, PLUME_BOX_DIM), dtype=np.float32)
    boxes = np.asarray(gt_boxes, dtype=np.float64)
    if boxes.size == 0:
        return np.zeros((0, PLUME_BOX_DIM), dtype=np.float32)
    if boxes.ndim != 2 or boxes.shape[1] < 7:
        raise ValueError(f"gt_boxes must be (M,>=7), got {boxes.shape}")

    velocity = None
    if gt_velocity is not None:
        velocity = np.asarray(gt_velocity, dtype=np.float64).reshape(-1, 2)
        if velocity.shape[0] != boxes.shape[0]:
            raise ValueError(
                f"gt_velocity has {velocity.shape[0]} rows for {boxes.shape[0]} boxes"
            )

    keep = np.ones(boxes.shape[0], dtype=bool)
    if plume_classes is not None:
        if gt_names is None:
            raise ValueError(
                "gt_names is required to filter by class; pass plume_classes=None "
                "to keep every box"
            )
        names = np.asarray(gt_names).astype(str)
        if names.shape[0] != boxes.shape[0]:
            raise ValueError(
                f"gt_names has {names.shape[0]} rows for {boxes.shape[0]} boxes"
            )
        keep = np.isin(names, np.asarray(plume_classes))

    boxes = boxes[keep]
    if boxes.shape[0] == 0:
        return np.zeros((0, PLUME_BOX_DIM), dtype=np.float32)

    out = np.zeros((boxes.shape[0], PLUME_BOX_DIM), dtype=np.float64)
    out[:, 0] = boxes[:, 0]
    out[:, 1] = boxes[:, 1]
    out[:, 2] = boxes[:, 2] - boxes[:, 5] / 2.0   # tâm -> đáy
    out[:, 3] = boxes[:, 4]                        # l (dọc yaw)  <- slot 4, KHÔNG phải 3
    out[:, 4] = boxes[:, 3]                        # w (ngang)    <- slot 3
    out[:, 5] = boxes[:, 5]                        # h
    out[:, 6] = boxes[:, 6]                        # yaw
    if velocity is not None:
        out[:, 7:9] = velocity[keep]
    return out.astype(np.float32)


def sample_augmented_speed_kmh(
    scene_token: str, epoch: int = 0, base_seed: int = 0
) -> float:
    """Tốc độ plume cho **một scene**, rời rạc trên 9 mốc đo.

    Rời rạc, không ``U(50,130)``: mỗi mốc có số cụm/frame đo được đứng sau, còn
    giá trị nội suy giữa hai mốc (vd 87 km/h) thì không có số đo nào.
    Một lần bốc cho cả scene để plume trong scene **nhất quán** theo thời gian —
    bốc lại mỗi frame sẽ làm cụm nhảy tốc độ và tuổi thọ đổi liên tục.
    """
    import zlib

    seed = (int(base_seed) * 1_000_003 + int(epoch) * 7919
            + zlib.crc32(scene_token.encode("utf-8"))) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    return float(MEASURED_SPEEDS_KMH[int(rng.integers(len(MEASURED_SPEEDS_KMH)))])
```

**Chạy:** `$PY -m pytest tests/test_nuscenes_context.py -q` → `16 passed`

**Commit:** `feat(nuscenes): đổi quy ước box + lấy mẫu tốc độ plume trên 9 mốc đo`

#### T7. Test đỏ: dựng `PlumeContext` từ info dict

**Files:** thêm vào `tests/test_nuscenes_context.py`

```python
from spray.nuscenes_context import (
    MEASURED_SPEEDS_KMH,
    build_nuscenes_context,
    sample_augmented_speed_kmh,
    select_lead_box,
)


def test_speed_draw_is_deterministic_and_in_the_measured_domain():
    a = sample_augmented_speed_kmh("scene-0001", epoch=0, base_seed=0)
    b = sample_augmented_speed_kmh("scene-0001", epoch=0, base_seed=0)
    assert a == b
    assert a in MEASURED_SPEEDS_KMH
    assert 50.0 <= a <= 130.0


def test_every_draw_lands_on_a_measured_speed_and_uses_more_than_one():
    draws = {
        sample_augmented_speed_kmh(f"scene-{index:04d}", 0, 0) for index in range(200)
    }
    assert draws <= set(MEASURED_SPEEDS_KMH)
    assert len(draws) >= 7, f"only {sorted(draws)} drawn — seed mixing is broken"


def test_context_carries_sampled_speed_not_ego_speed():
    info = {
        "scene_token": "scene-0001",
        "timestamp": 1533151603547590,
        "ego2global_translation": [0.0, 0.0, 0.0],
        "ego2global_rotation": [1.0, 0.0, 0.0, 0.0],
        "lidar2ego_translation": [0.0, 0.0, 1.84],
        "lidar2ego_rotation": [1.0, 0.0, 0.0, 0.0],
        "gt_boxes": NU_BOX,
        "gt_velocity": VELOCITY,
    }
    context, boxes = build_nuscenes_context(
        info, frame_index=3, epoch=0, road_z_m=-1.84, base_seed=0
    )
    expected = sample_augmented_speed_kmh("scene-0001", 0, 0)
    assert context.ego_speed_mps == pytest.approx(expected / 3.6)
    assert context.object_speed_mps == pytest.approx(expected / 3.6)
    assert context.road_z_m == pytest.approx(-1.84)
    assert context.boxes is not None and context.boxes.shape == (1, 9)
    assert boxes.shape == (1, 9)
    assert 0.0 < context.wfh_mm <= 1.2
```

#### T8. Implement `build_nuscenes_context`

**Files:** thêm vào `spray/nuscenes_context.py`

```python
from spray.plume_context import PlumeContext, sample_wfh_mm


def build_nuscenes_context(
    info: dict,
    *,
    frame_index: int,
    epoch: int = 0,
    road_z_m: float,
    base_seed: int = 0,
) -> tuple[PlumeContext, np.ndarray]:
    """``PlumeContext`` + box đã đổi quy ước, cho một info dict nuScenes.

    ``ego_speed_mps`` **và** ``object_speed_mps`` cùng nhận tốc độ lấy mẫu:
    nếu để chúng khác nhau, ``state.advance`` trừ ego một đằng còn ``spawn``
    cộng vận tốc vật thể một nẻo, và cụm sẽ trôi ngược qua cảm biến — đúng lỗi
    ``C = −0,15`` áp sai miền đã ghi trong HANDOFF.

    ``road_z_m`` là **tham số**, không suy trong hàm: nuScenes có cao độ mặt
    đường khác SSPP và khác theo từng khu vực.
    """
    scene_token = info.get("scene_token") or info.get("scene")
    if not scene_token:
        raise KeyError("info dict has no 'scene_token' (rebuild the pkl)")

    speed_kmh = sample_augmented_speed_kmh(scene_token, epoch, base_seed)
    speed_mps = speed_kmh / 3.6

    boxes = nuscenes_boxes_to_plume(
        info.get("gt_boxes"),
        info.get("gt_velocity"),
        gt_names=info.get("gt_names"),
    )
    boxes = select_lead_box(boxes)          # 0 hoặc 1 box — xe dẫn phía trước
    velocity = None
    if boxes.shape[0] > 0:
        velocity = np.array([boxes[0, 7], boxes[0, 8], 0.0], dtype=np.float64)

    origin = np.asarray(
        info.get("lidar2ego_translation", [0.0, 0.0, 0.0]), dtype=np.float64
    )
    context = PlumeContext(
        scene_token=str(scene_token),
        frame_index=int(frame_index),
        epoch=int(epoch),
        sensor_origin=origin,
        ego_speed_mps=speed_mps,
        object_speed_mps=speed_mps,
        wfh_mm=sample_wfh_mm(str(scene_token), epoch, base_seed),
        road_z_m=float(road_z_m),
        boxes=boxes,
        object_velocity_ego_mps=velocity,
    )
    return context, boxes
```

**Chạy:** `$PY -m pytest tests/test_nuscenes_context.py -q` → `19 passed`

**Commit:** `feat(nuscenes): dựng PlumeContext từ info dict với tốc độ lấy mẫu`

---

### Phase 3 — Cache plume offline (né lỗ 2 và lỗ 4)

#### T9. Test đỏ: transform cache không trạng thái, worker-safe

**Files:** tạo `tests/test_plume_cache_transform.py`

```python
"""``PlumeCacheTransform`` chỉ đọc cache: không state, cùng input ⇒ cùng output."""

import numpy as np
import pytest

from spray.plume_cache_transform import PlumeCache, PlumeCacheTransform


def _write_cache(path, token, detections):
    np.savez_compressed(
        path,
        tokens=np.array([token]),
        offsets=np.array([0, len(detections)]),
        points=np.asarray(detections, dtype=np.float32).reshape(-1, 5),
    )


def test_appends_cached_detections_and_keeps_points_clean(tmp_path):
    cache_path = tmp_path / "cache.npz"
    detections = np.array([[5.0, 0.0, 0.5, 40.0, 3.0]] * 7, dtype=np.float32)
    _write_cache(cache_path, "tok-1", detections)
    transform = PlumeCacheTransform(cache_path=str(cache_path))
    points = np.zeros((100, 5), dtype=np.float32)

    out = transform({"points": points, "metadata": {"token": "tok-1"}})

    assert out["points"].shape == (107, 5)
    assert np.array_equal(out["points_clean"], points)
    assert np.array_equal(out["points"][100:], detections)


def test_two_calls_are_byte_identical(tmp_path):
    cache_path = tmp_path / "cache.npz"
    _write_cache(cache_path, "tok-1", np.ones((3, 5), dtype=np.float32))
    transform = PlumeCacheTransform(cache_path=str(cache_path))
    points = np.arange(20, dtype=np.float32).reshape(4, 5)
    first = transform({"points": points, "metadata": {"token": "tok-1"}})["points"]
    second = transform({"points": points, "metadata": {"token": "tok-1"}})["points"]
    assert np.array_equal(first, second)


def test_missing_token_raises_instead_of_silently_skipping(tmp_path):
    cache_path = tmp_path / "cache.npz"
    _write_cache(cache_path, "tok-1", np.zeros((2, 5), dtype=np.float32))
    transform = PlumeCacheTransform(cache_path=str(cache_path))
    with pytest.raises(KeyError):
        transform({"points": np.zeros((4, 5), dtype=np.float32),
                   "metadata": {"token": "tok-missing"}})


def test_disabled_is_a_passthrough(tmp_path):
    cache_path = tmp_path / "cache.npz"
    _write_cache(cache_path, "tok-1", np.ones((3, 5), dtype=np.float32))
    transform = PlumeCacheTransform(cache_path=str(cache_path), enabled=False)
    points = np.zeros((10, 5), dtype=np.float32)
    out = transform({"points": points, "metadata": {"token": "tok-1"}})
    assert np.array_equal(out["points_clean"], points)
    assert np.array_equal(out["points"], points)


def test_cache_object_is_reused_without_mutation(tmp_path):
    cache_path = tmp_path / "cache.npz"
    _write_cache(cache_path, "tok-1", np.ones((3, 5), dtype=np.float32))
    cache = PlumeCache(cache_path)
    before = cache.get("tok-1").copy()
    cache.get("tok-1")[0, 0] = 999.0
    assert np.array_equal(cache.get("tok-1"), before)
```

**Chạy:** `$PY -m pytest tests/test_plume_cache_transform.py -q`
Kỳ vọng: `ModuleNotFoundError: No module named 'spray.plume_cache_transform'`.

#### T10. Implement `spray/plume_cache_transform.py`

```python
"""Transform mmdet3d đọc plume đã sinh sẵn từ cache — KHÔNG có trạng thái.

Vì sao không dùng ``PlumeTransform`` stateful: nó giữ ``self._state``, mà
dataloader chia frame giữa nhiều worker, nên mỗi worker có một ``PlumeState``
riêng và frame liên tiếp không chia sẻ trạng thái. Kết quả là mật độ plume sai
mà không có lỗi nào bật ra. Cache keyed theo token làm điều đó thành bất khả:
mỗi frame chỉ tra một khoá.

Hai điều transform này **bảo đảm**:

- ``points_clean`` là bản sao **byte-identical** của ``points`` vào;
- cùng token ⇒ cùng điểm, ở mọi epoch, mọi số worker, mọi thứ tự sample.
"""

from __future__ import annotations

import pathlib

import numpy as np

try:  # pragma: no cover - chỉ chạy trong môi trường MIT đã pin
    from mmdet3d.datasets import PIPELINES
except Exception:  # noqa: BLE001 - laptop không có mmdet3d
    PIPELINES = None


def _register(cls):
    if PIPELINES is None:
        return cls
    return PIPELINES.register_module()(cls)


class PlumeCache:
    """Tra cứu ``token -> (M, 5)`` từ một file ``.npz`` (tokens, offsets, points)."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        with np.load(self.path) as payload:
            self._tokens = [str(token) for token in payload["tokens"]]
            self._offsets = payload["offsets"].astype(np.int64)
            self._points = payload["points"].astype(np.float32)
        self._index = {token: position for position, token in enumerate(self._tokens)}

    def get(self, token: str) -> np.ndarray:
        """Điểm của ``token``. **Copy** — caller sửa cũng không ảnh hưởng cache."""
        if token not in self._index:
            raise KeyError(
                f"{self.path}: no cached plume for token {token!r} "
                f"({len(self._tokens)} tokens in cache)"
            )
        position = self._index[token]
        start = int(self._offsets[position])
        stop = int(self._offsets[position + 1])
        return self._points[start:stop].copy()

    def __len__(self) -> int:
        return len(self._tokens)


@_register
class PlumeCacheTransform:
    """Nối điểm plume đã cache vào ``points``, giữ ``points_clean`` nguyên bản."""

    def __init__(self, cache_path, enabled: bool = True, **kwargs):
        self.cache = PlumeCache(cache_path)
        self.enabled = bool(enabled)

    def __call__(self, results: dict) -> dict:
        points = np.asarray(results["points"], dtype=np.float32)
        results["points_clean"] = points.copy()
        if not self.enabled:
            return results
        metadata = results.get("metadata") or {}
        token = str(metadata.get("token", results.get("token", "")))
        detections = self.cache.get(token)
        if detections.size == 0:
            return results
        results["points"] = np.concatenate([points, detections], axis=0)
        results["spray_stats"] = {"injected": int(detections.shape[0])}
        return results
```

**Chạy:** `$PY -m pytest tests/test_plume_cache_transform.py -q` → `5 passed`

**Commit:** `feat(train): PlumeCacheTransform — đọc plume đã cache, không trạng thái`

#### T11. Census: bao nhiêu frame **sinh plume được** — đã đo trên Mini, phải chạy lại trên full

**Vì sao task này quan trọng nhất trong Phase 3.** Thiết kế đã chốt: plume chỉ sinh khi có **xe
dẫn phía trước là ô tô** (`select_lead_box`, T6). Hệ quả trực tiếp:

- mỗi frame sinh **0 hoặc 1** nguồn phun ⇒ chi phí raycast không còn là vấn đề (1 box ≈ 25 ms,
  và chỉ trả một lần lúc dựng cache, không phải mỗi bước train). **Lỗ 4 biến mất.**
- nhưng nếu phần lớn frame nuScenes **không có** xe dẫn trong 50 m phía trước (đường đô thị
  hay tắc, ego đứng một mình, hoặc xe dẫn đang rẽ), thì arm B gần như **không có plume** và
  thí nghiệm thành A vs A.

Nên phải đo **trước** khi dựng cache. Đây là con số quyết định plan có nghĩa hay không.

**Files:** tạo `scripts/measure_lead_availability.py`

```bash
$PY scripts/measure_lead_availability.py \
  --infos data/nuscenes_infos_mini_train.pkl \
  --out .scratch/nuscenes-train/lead-census.md 2>&1 | grep LEAD_CENSUS
```

Phải in được, tính bằng chính `select_lead_box` (không viết lại logic):

| chỉ số | ý nghĩa |
|---|---|
| `frames` | tổng frame train |
> ⚠️ **Đã chạy census này trên nuScenes Mini (2026-11-27).** Kết quả đầy đủ:
> `docs/measurements/nuscenes-mini-census.md`. Ngưỡng dưới đây đã được **sửa** vì ngưỡng đầu
> tiên ("có xe dẫn") cho 71,5 % — một con số ảo. Xem lý do ngay dưới bảng.

| chỉ số | ý nghĩa |
|---|---|
| `frames` | tổng frame train |
| `with_lead` / `%` | số frame có ≥1 ô tô phía trước trong 50 m, \|y\| ≤ 5 m |
| **`spawnable` / `%`** | **số frame mà plume THẬT SỰ sinh được** — xem định nghĩa dưới |
| `no_lead_reason` | tách: không có box / chỉ có phía sau / quá xa / lệch làn / **quá gần** |
| `lead_x` p5/p50/p95 | khoảng cách xe dẫn. **p50 phải ≥ ~20 m để giống paper** |
| `ego_speed` p50, `% frame > 40 km/h` | nuScenes đô thị chậm; nếu phần lớn < 20 km/h thì đó là tắc đường, không phải bám đuôi |
| `speed_gap` | tốc độ ego − tốc độ box xe dẫn. ≈ 0 là cùng tốc độ (hợp lý); lệch lớn là bắt sai xe |

**Định nghĩa `spawnable` — đây là chỗ plan đầu tiên sai.** Plume spawn trong slab dài
`|v_aug|·dt` ngay sau **mặt đuôi** xe, và `min_range_m = 2,5 m` lọc theo **mặt cầu** cụm
(bán kính tới 2,0 m). Nên điều kiện để cụm còn sống sau `select_alive` là:

```
lead_x − λ/2 − |v_aug|·dt/2 − r  ≥  2,5 m
```

Với `λ = 4,6 m` (car), `v_aug = 100 km/h` (`dt = 0,1` ⇒ slab 2,78 m), và `r` lấy từ lognormal
của generator (`μ = −1,2`, `σ = 0,8`): **`lead_x ≥ 6,49 m`** khi `r = p50 = 0,30 m`,
**`7,31 m`** khi `r = p95`. Đo trên Mini (404 frame):

```
lead_x ≥  5,00 m: 25,0 % frame
lead_x ≥  6,49 m: 21,5 %   ← ngưỡng sinh được ở r = p50
lead_x ≥  7,31 m: 20,3 %   ← ngưỡng sinh được ở r = p95
lead_x ≥ 20,00 m:  1,5 %   ← khoảng cách campaign của paper (SSPP: distance_to_object = 20)
```

Nên `spawnable` phải dùng ngưỡng **6,49 m**, không phải "có xe dẫn" và cũng không phải số tròn
9 m (một bản nháp trước của plan này đã ghi 9 m ⇒ 12,8 %, sai vì lấy `r ≈ 1 m` trong khi trung
vị `r` chỉ 0,30 m). Khi slab rơi vào vùng
`‖pos‖ − r < 2,5`, `select_alive` lọc sạch cụm mà **không báo lỗi** — transform vẫn `return`
bình thường. Đây là lỗi câm, và nó là lý do phải đo bằng công thức chứ không đếm box.

**Ba cửa quyết định, đọc theo `spawnable %` (KHÔNG phải `with_lead %`):**

| `spawnable %` | kết luận | hành động |
|---|---|---|
| **≥ 40 %** | plume xuất hiện đủ dày | tiếp tục |
| **10–40 %** | dùng được nhưng phải khai: arm B chỉ augment `X %` frame | tiếp tục; ghi `X` vào `docs/measurements/` |
| **< 10 %** | arm B gần như không khác arm A | **dừng, báo user.** Đừng train 2 kernel để đo thứ không tồn tại. Phương án theo thứ tự: (a) lọc bớt frame quá gần thay vì nới ngưỡng; (b) đổi sang dataset có đường trường; (c) **không** nới `max_range_m` — nó vượt miền paper |

**Đã đo trên Mini: `spawnable (≥6,49 m) = 21,5 %` → cửa thứ hai.** Mini vì thế chỉ đủ để
**thông luồng**, không đủ để kết luận. Census phải chạy lại trên full `v1.0-trainval`.

**Commit:** `measure(nuscenes): census xe dẫn — bao nhiêu % frame có plume`

#### T12. Test đỏ: cache builder sinh đúng số điểm, đúng token

**Files:** tạo `tests/test_build_plume_cache.py`

```python
"""Builder cache: token nào có trong infos thì phải có trong cache, theo đúng thứ tự."""

import numpy as np
import pytest

from scripts.build_plume_cache import build_cache, write_cache


class _FakeDataset:
    """Dataset tối thiểu cho builder: chỉ cần infos + load_points."""

    def __init__(self, infos, points):
        self.infos = infos
        self._points = points

    def load_points(self, info):
        return self._points


def _info(token, scene, frame, with_lead=True):
    """Info giả. ``with_lead=False`` đặt box **sau** ego để test nhánh không-plume."""
    x = 15.0 if with_lead else -12.0
    return {
        "token": token,
        "scene_token": scene,
        "timestamp": frame * 500_000,
        "lidar2ego_translation": [0.0, 0.0, 1.84],
        "gt_boxes": np.array([[x, 0.0, 0.9, 1.9, 4.6, 1.75, 0.0]], dtype=np.float32),
        "gt_names": np.array(["car"]),
        "gt_velocity": np.array([[10.0, 0.0]], dtype=np.float32),
        "frame_index": frame,
    }


def test_one_entry_per_token_and_offsets_line_up(tmp_path):
    infos = [_info("t0", "s0", 0), _info("t1", "s0", 1), _info("t2", "s1", 0)]
    points = np.zeros((50, 5), dtype=np.float32)
    cache = build_cache(_FakeDataset(infos, points), road_z_m=-1.84, substeps=5,
                        frames_per_scene=10, base_seed=0)
    # Mọi token đều có mặt, kể cả frame KHÔNG có xe dẫn (offset bằng nhau = 0 điểm).
    assert sorted(cache["tokens"]) == ["t0", "t1", "t2"]
    assert len(cache["offsets"]) == len(cache["tokens"]) + 1
    assert cache["offsets"][-1] == cache["points"].shape[0]

    out = tmp_path / "cache.npz"
    write_cache(cache, out)
    with np.load(out) as payload:
        assert payload["points"].shape[1] == 5
        assert payload["offsets"][-1] == payload["points"].shape[0]


def test_frame_without_a_lead_vehicle_gets_an_empty_entry(tmp_path):
    """Không có xe dẫn ⇒ entry rỗng, KHÔNG bị bỏ khỏi cache và KHÔNG raise."""
    infos = [_info("t0", "s0", 0, with_lead=False)]
    points = np.zeros((500, 5), dtype=np.float32)
    cache = build_cache(_FakeDataset(infos, points), road_z_m=-1.84, substeps=5,
                        frames_per_scene=10, base_seed=0)
    assert cache["tokens"] == ["t0"]
    assert cache["offsets"].tolist() == [0, 0]
    assert cache["points"].shape == (0, 5)


def test_cache_is_reproducible(tmp_path):
    infos = [_info("t0", "s0", 0)]
    points = np.random.default_rng(0).normal(size=(300, 5)).astype(np.float32)
    a = build_cache(_FakeDataset(infos, points), road_z_m=-1.84, substeps=5,
                    frames_per_scene=10, base_seed=0)
    b = build_cache(_FakeDataset(infos, points), road_z_m=-1.84, substeps=5,
                    frames_per_scene=10, base_seed=0)
    assert np.array_equal(a["points"], b["points"])
```

**Chạy:** `$PY -m pytest tests/test_build_plume_cache.py -q`
Kỳ vọng: `ModuleNotFoundError: No module named 'scripts.build_plume_cache'`.

> Nếu `scripts/` không import được như package, thêm `scripts/__init__.py` rỗng ở task này.

#### T13. Implement `scripts/build_plume_cache.py`

**Files:** tạo `scripts/build_plume_cache.py` (+ `scripts/__init__.py` nếu thiếu)

Khung chính (phần đo/parse để implementer tự viết theo style `scripts/sspp_infer.py`):

```python
#!/usr/bin/env python3
"""Sinh plume một lần, tuần tự, đúng chu kỳ 0,1 s, rồi ghi cache theo token.

Vì sao tuần tự: generator **có trạng thái** — cụm sống qua frame, trôi, tan. Chạy
song song là mỗi process một trạng thái riêng và mật độ plume sai. Ở đây trạng
thái chỉ tồn tại trong một vòng lặp theo đúng thứ tự thời gian của từng scene.

Vì sao cache: train đọc lại cùng một đám mây ở mọi epoch. Điều đó làm phép A/B
sạch hơn (biến thiên duy nhất giữa hai arm là *có plume hay không*, không phải
"plume khác nhau mỗi epoch") và cắt được chi phí raycast khỏi vòng train.

Frame dài hơn 0,1 s (nuScenes keyframe 0,5 s) phải dùng ``substeps=5``: truyền
``dt=0.5`` một bước làm cụm sống lâu gấp ~5 lần và plume loãng đi tương ứng.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

from spray.beam_model import load_beam_table
from spray.nuscenes_context import build_nuscenes_context
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame


def build_cache(
    dataset,
    *,
    road_z_m: float,
    substeps: int,
    frames_per_scene: int = 0,
    base_seed: int = 0,
    config: PlumeConfig | None = None,
) -> dict:
    cfg = config or PlumeConfig()
    table = load_beam_table()
    detections = {}
    state = PlumeState()
    order = sorted(
        range(len(dataset.infos)),
        key=lambda i: (dataset.infos[i]["scene_token"], dataset.infos[i]["timestamp"]),
    )
    for position in order:
        info = dataset.infos[position]
        token = str(info["token"])
        points = np.asarray(dataset.load_points(info), dtype=np.float32)
        context, boxes = build_nuscenes_context(
            info,
            frame_index=int(info.get("frame_index", 0)),
            epoch=0,
            road_z_m=road_z_m,
            base_seed=base_seed,
        )
        # ``build_nuscenes_context`` đã lọc lớp và chọn **1** xe dẫn.
        # Rỗng ⇒ không có xe dẫn phía trước ⇒ frame này không có plume.
        if boxes.shape[0] == 0:
            detections[token] = np.zeros((0, 5), dtype=np.float32)
            continue
        result = inject_plume_stateful(
            points, boxes, context, state,
            seed=base_seed, token=token, config=cfg,
            dt=0.1, substeps=substeps, vehicle_class="crafter",
        )
        cast = raycast_frame(
            result.points_clean, state.select_alive(), table=table,
            road_z_m=road_z_m, rng=np.random.default_rng(base_seed),
        )
        detections[token] = np.asarray(cast.detections, dtype=np.float32).reshape(-1, 5)

    tokens = sorted(detections)
    offsets = np.zeros(len(tokens) + 1, dtype=np.int64)
    for index, token in enumerate(tokens):
        offsets[index + 1] = offsets[index] + detections[token].shape[0]
    points_out = (
        np.concatenate([detections[t] for t in tokens], axis=0)
        if tokens and offsets[-1] > 0
        else np.zeros((0, 5), dtype=np.float32)
    )
    return {"tokens": tokens, "offsets": offsets, "points": points_out.astype(np.float32)}


def write_cache(cache: dict, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        tokens=np.array(cache["tokens"]),
        offsets=cache["offsets"],
        points=cache["points"],
    )
```

**CLI:** `--infos`, `--out`, `--road-z-m`, `--substeps`, `--base-seed`, và `--sspp-lead-only`.
Phải in **hai** marker:

- `PLUME_CACHE tokens=<n> points=<N> empty=<k> out=<path>` (tóm tắt cuối);
- `PLUME_LEAD no_box=<a> behind=<b> too_far=<c> off_lane=<d> selected=<e>` (lý do loại, để
  phân biệt "không có xe dẫn" với "lọc sai"). Bốn khoá này phải khớp **đúng** tên mà
  `select_lead_box` phân biệt được; nếu hàm chỉ trả box rỗng thì nó không nói được lý do —
  nên thêm vào `spray/nuscenes_context.py`:

```python
def explain_lead_selection(
    boxes: np.ndarray,
    *,
    max_range_m: float = 50.0,
    max_lateral_m: float = 5.0,
    ahead_only: bool = True,
) -> dict[str, int]:
    """Đếm lý do loại, dùng cho log/census. Cùng điều kiện với ``select_lead_box``."""
    if boxes.size == 0:
        return {"no_box": 1, "behind": 0, "too_far": 0, "off_lane": 0, "selected": 0}
    array = np.asarray(boxes, dtype=np.float64).reshape(-1, PLUME_BOX_DIM)
    behind = int((array[:, 0] <= 0.0).sum()) if ahead_only else 0
    ahead = array[array[:, 0] > 0.0] if ahead_only else array
    too_far = int((ahead[:, 0] > max_range_m).sum())
    near = ahead[ahead[:, 0] <= max_range_m]
    off_lane = int((np.abs(near[:, 1]) > max_lateral_m).sum())
    selected = int(len(near) - off_lane)
    return {
        "no_box": 0, "behind": behind, "too_far": too_far,
        "off_lane": off_lane, "selected": min(selected, 1),
    }
```

**Test bắt buộc cho hàm này** (cộng vào `tests/test_nuscenes_context.py`):

```python
def test_explain_counts_sum_to_the_input():
    boxes = np.array(
        [_plume_box(-5.0), _plume_box(70.0), _plume_box(20.0, y=9.0), _plume_box(15.0)],
        dtype=np.float64,
    )
    counts = explain_lead_selection(boxes)
    assert counts == {
        "no_box": 0, "behind": 1, "too_far": 1, "off_lane": 1, "selected": 1,
    }
    assert sum(counts.values()) == boxes.shape[0]
```

**Chạy:** `$PY -m pytest tests/test_build_plume_cache.py -q` → `3 passed`

**Commit:** `feat(plume): builder cache plume tuần tự với đúng chu kỳ 0,1 s`

#### T14. Chạy builder cho một split nhỏ, kiểm số thật

**Trước tiên kiểm đường SSPP (đã có infos trên đĩa, không cần nuScenes):**

```bash
$PY scripts/build_plume_cache.py \
  --infos data/sspp_infos_val.pkl \
  --dataset-root data/SemanticSprayDataset \
  --road-z-m -0.376 --substeps 1 \
  --sspp-lead-only \
  --out .scratch/nuscenes-train/cache_sspp_val.npz \
  2>&1 | grep PLUME_CACHE
```

Kỳ vọng: `PLUME_CACHE tokens=509 points=<hàng chục nghìn> empty=<0..3> out=...`.

**Chú ý cờ `--sspp-lead-only`:** SSPP có đúng 1 box/frame và box đó **chính là xe dẫn**
(campaign ghi `object_direction = +1`, `distance_to_object = 20 m`). Nên trên SSPP, "chọn xe
dẫn" là no-op — nhưng vẫn phải đi qua `select_lead_box` để **một hàm duy nhất** quyết định,
thay vì hai đường logic khác nhau cho hai dataset. Cờ này chỉ tắt bước lọc lớp (SSPP đã là
`Car`/`Van`); điều kiện hình học `x > 0`, `x ≤ 50`, `|y| ≤ 5` vẫn bật.

Nếu `empty` lớn: đọc `PLUME_LEAD` trong log — nó in lý do loại
(`behind`, `too_far`, `off_lane`, `no_box`). Đó là chỗ phân biệt "không có xe dẫn" với
"có nhưng lọc sai".

**Ghi số vào `.scratch/nuscenes-train/BASELINE.md`** (một dòng: `cache SSPP val: tokens=… points=… empty=…`).

**Commit:** `measure(plume): cache SSPP val — kiểm builder trên dữ liệu có thật`

---

### Phase 4 — Pseudo box cho 171 scene SSPP (đầu vào số 2 của user)

#### T15. Test đỏ: pseudo box dựng lại được box human trong ±0,15 m

**Files:** tạo `tests/test_pseudo_boxes.py`

```python
"""Pseudo box từ ``label == 1``: gate phải loại frame rác, và box phải khớp human."""

import numpy as np
import pytest

from scripts.build_sspp_pseudo_boxes import (
    CLASS_CONSTANTS,
    build_pseudo_box,
)

CAR = CLASS_CONSTANTS["Car"]


def _vehicle_cloud(n=300, rear_x=20.0, seed=0):
    """Đám điểm thân xe: mặt sau ở ``rear_x``, dài 4,25, rộng 2,02."""
    rng = np.random.default_rng(seed)
    x = rear_x + rng.uniform(0.0, 4.25, n)
    y = rng.normal(0.0, 0.45, n)
    z = rng.uniform(-0.35, 1.05, n)
    return np.column_stack([x, y, z])


def test_pseudo_box_matches_a_clean_vehicle_cloud():
    points = _vehicle_cloud()
    labels = np.ones(len(points), dtype=np.uint32)
    road = np.column_stack([
        np.random.default_rng(9).uniform(4, 30, 400),
        np.random.default_rng(8).uniform(-2, 2, 400),
        np.full(400, -0.40),
    ])
    box = build_pseudo_box(points, labels, "Car", road_points=road)
    assert box is not None
    assert box[3] == pytest.approx(CAR["size_x"], abs=1e-6)   # dài 4,2503
    assert box[4] == pytest.approx(CAR["size_y"], abs=1e-6)   # rộng 2,0215
    assert box[5] == pytest.approx(CAR["size_z"], abs=1e-6)   # cao 1,5006
    assert box[6] == 0.0                                      # yaw = 0
    # đáy box lấy từ mặt đường, không từ điểm thấp nhất của thân xe
    assert box[2] == pytest.approx(-0.40, abs=0.20)


def test_gate_rejects_a_spray_dominated_cluster():
    rng = np.random.default_rng(3)
    spray = np.column_stack([
        rng.uniform(5, 15, 500), rng.normal(0, 1.5, 500), rng.uniform(-0.3, 1.6, 500)
    ])
    vehicle = _vehicle_cloud(n=40)
    points = np.vstack([spray, vehicle])
    labels = np.concatenate(
        [np.ones(len(spray), dtype=np.uint32), np.ones(len(vehicle), dtype=np.uint32)]
    )
    assert build_pseudo_box(points, labels, "Car", road_points=None) is None


def test_too_few_points_returns_none():
    points = _vehicle_cloud(n=5)
    labels = np.ones(5, dtype=np.uint32)
    assert build_pseudo_box(points, labels, "Car", road_points=None) is None
```

**Chạy:** `$PY -m pytest tests/test_pseudo_boxes.py -q`
Kỳ vọng: `ModuleNotFoundError: No module named 'scripts.build_sspp_pseudo_boxes'`.

#### T16. Implement `scripts/build_sspp_pseudo_boxes.py`

**Nguồn học thuật:** `.scratch/roadspray-cal/pseudo-boxes.md` §3 (rule) + `constants.json`
(hằng số đã fit). **Chép nguyên hằng số, không fit lại** — chúng đã validate held-out 3-fold
(BEV IoU p5 0,844 / p50 0,929 trên 12 scene không dùng để fit).

```python
#!/usr/bin/env python3
"""Dựng pseudo 3D box cho 171 scene SSPP không có human box.

Nguồn: ``.scratch/roadspray-cal/pseudo-boxes.md`` (validate held-out 3-fold:
BEV IoU p5 0,844 / p50 0,929 / p95 0,976; 3D IoU p50 0,872; 99,8 % frame ≥ 0,7).

**Chỉ dùng cho TRAIN.** Không dùng cho val/test/metric: 3D IoU p50 0,872 nghĩa là
metric trên pseudo box bị chính label noise chi phối. Ngoài ra pseudo scene là
``itr_after_water`` 2…6 (khô hơn) còn 36 scene human đều ``itr = 1`` ⇒ đổi cả
phân bố spray, không chỉ đổi nhãn.
"""

from __future__ import annotations

import numpy as np

# Hằng số fit trên 36 scene CÓ box, scene-CV ổn định (δx Car 0,126–0,147;
# Van 0,200–0,212). Không phụ thuộc scene nào.
CLASS_CONSTANTS = {
    "Car": dict(size_x=4.2503, size_y=2.0215, size_z=1.5006, dx=0.1268, dy=0.0194),
    "Van": dict(size_x=6.8288, size_y=2.4186, size_z=2.6206, dx=0.1864, dy=0.0762),
}
VEHICLE_LABEL = 1
ROAD_LABEL = 0
DBSCAN_EPS_M = 0.7
DBSCAN_MIN_SAMPLES = 8
MIN_PRIMARY_POINTS = 50
MIN_PURITY = 0.7


def _largest_cluster(points_xyz: np.ndarray) -> np.ndarray:
    from sklearn.cluster import DBSCAN

    if points_xyz.shape[0] < DBSCAN_MIN_SAMPLES:
        return points_xyz
    labels = DBSCAN(eps=DBSCAN_EPS_M, min_samples=DBSCAN_MIN_SAMPLES).fit_predict(points_xyz)
    keep = labels >= 0
    if not keep.any():
        return points_xyz
    values, counts = np.unique(labels[keep], return_counts=True)
    best = values[int(np.argmax(counts))]
    return points_xyz[labels == best]


def _ground_z(x: float, y: float, road_points: np.ndarray | None) -> float | None:
    if road_points is None or road_points.shape[0] < 30:
        return None
    design = np.column_stack([np.ones(len(road_points)), road_points[:, 0], road_points[:, 1]])
    solution, *_ = np.linalg.lstsq(design, road_points[:, 2], rcond=None)
    residual = road_points[:, 2] - design @ solution
    keep = np.abs(residual - np.median(residual)) < 0.35
    if keep.sum() >= 20:
        solution, *_ = np.linalg.lstsq(
            design[keep], road_points[keep, 2], rcond=None
        )
    return float(solution[0] + solution[1] * x + solution[2] * y)


def build_pseudo_box(
    points: np.ndarray,
    labels: np.ndarray,
    vehicle_class: str,
    road_points: np.ndarray | None = None,
) -> np.ndarray | None:
    """Một box ``[x, y, z_đáy, dài, rộng, cao, yaw, 0, 0]`` hoặc ``None`` khi gate loại."""
    constants = CLASS_CONSTANTS[vehicle_class]
    mask = labels == VEHICLE_LABEL
    n_primary_total = int(mask.sum())
    if n_primary_total < MIN_PRIMARY_POINTS:
        return None
    xyz = np.asarray(points[mask][:, :3], dtype=np.float64)
    cluster = _largest_cluster(xyz)
    purity = cluster.shape[0] / float(n_primary_total)
    if cluster.shape[0] < MIN_PRIMARY_POINTS or purity < MIN_PURITY:
        return None

    rear_x = float(np.percentile(cluster[:, 0], 2.0))
    center_x = rear_x - constants["dx"] + constants["size_x"] / 2.0
    center_y = float(np.median(cluster[:, 1])) + constants["dy"]

    ground = _ground_z(center_x, center_y, road_points)
    if ground is None:
        # Fallback: đáy cluster trừ 0,35 m (bumper cao hơn đáy box chừng đó).
        ground = float(np.percentile(cluster[:, 2], 2.0)) - 0.35
    return np.array(
        [[center_x, center_y, ground, constants["size_x"], constants["size_y"],
          constants["size_z"], 0.0, 0.0, 0.0]],
        dtype=np.float32,
    )
```

**CLI** (`build`): đọc `data/sspp_infos_{train,val,test}.pkl`, với mỗi frame **không có**
`gt_boxes`, đọc `labels/*.label` + `velodyne/*.bin`, gọi `build_pseudo_box`, gán
`info["gt_boxes"]`, `info["gt_names"]`, `info["num_lidar_pts"]`, thêm ba khoá:
`info["pseudo"] = True`, `info["purity"]`, `info["n_primary"]`. Ghi
`data/sspp_infos_<split>_pseudo.pkl` + một dòng marker mỗi 500 frame:
`PSEUDO_BOX split=<s> frames=<n> built=<k> dropped=<d> pure_p50=<p>`.

**Chạy:** `$PY -m pytest tests/test_pseudo_boxes.py -q` → `3 passed`

**Commit:** `feat(sspp): builder pseudo box từ label==1 cho 171 scene không box`

#### T17. Chạy builder trên toàn bộ 207 scene, kiểm payoff bằng số

```bash
$PY scripts/build_sspp_pseudo_boxes.py build \
  --dataset-root data/SemanticSprayDataset \
  --infos-dir data --splits train val test \
  2>&1 | grep PSEUDO_BOX
```

Kỳ vọng (mốc phải khớp, sai là dừng):
- `built` cộng lại **≥ 99 %** của 14.832 frame không box;
- `pure_p50` **≥ 0,95** (study đo 0,994 trên mẫu);
- file sinh ra: `data/sspp_infos_train_pseudo.pkl` v.v.

**Kiểm bằng số độc lập** — dựng lại box cho 36 scene human rồi so với human box:

```bash
$PY scripts/build_sspp_pseudo_boxes.py validate \
  --dataset-root data/SemanticSprayDataset --max-frames 600 2>&1 | grep PSEUDO_VALIDATE
```

Kỳ vọng: `PSEUDO_VALIDATE frames=600 bev_iou_p50=0.9xx iou3d_p50=0.8xx ge07=0.9xx`.
Ngưỡng chặn: **BEV p50 ≥ 0,90 và 3D p50 ≥ 0,85**; thấp hơn ⇒ builder sai, không dùng.

**Commit:** `measure(sspp): payoff pseudo box — 171 scene, IoU khớp study`

#### T18. `data/sspp_folds.json` — 3 fold leave-speed-out, kiểm được bằng máy

**Files:** tạo `scripts/build_sspp_folds.py` + `tests/test_sspp_folds.py`

Quy tắc (ADR-0006 D1): `fold = rank(speed) mod 3 + 1` trên 9 tốc độ đã sort.

Test phải assert **bằng số đã đo**, không phải "chạy được":

```python
def test_folds_are_disjoint_and_cover_every_scene():
    folds = build_folds(scene_rows)
    assert len(folds["folds"]) == 3
    test_scenes = [s for fold in folds["folds"] for s in fold["test"]["scenes"]]
    assert len(test_scenes) == len(set(test_scenes)) == 207
    assert sum(f["test"]["frames"] for f in folds["folds"]) == 17_419


def test_each_fold_keeps_24_human_train_scenes():
    folds = build_folds(scene_rows)
    for fold in folds["folds"]:
        assert len(fold["train"]["human_scenes"]) == 24
        assert len(fold["test"]["human_scenes"]) == 12


def test_test_speeds_match_the_ranking_rule():
    folds = build_folds(scene_rows)
    assert [f["test"]["speeds"] for f in folds["folds"]] == [
        [50.0, 80.0, 110.0], [60.0, 90.0, 120.0], [70.0, 100.0, 130.0]
    ]
```

**Chạy:** `$PY -m pytest tests/test_sspp_folds.py -q` → `3 passed`, rồi

```bash
$PY scripts/build_sspp_folds.py --dataset-root data/SemanticSprayDataset \
  --out data/sspp_folds.json 2>&1 | grep SSPP_FOLDS
```

Kỳ vọng: `SSPP_FOLDS folds=3 test_scenes=207 test_frames=17419`.

**Commit:** `feat(sspp): 3 fold leave-speed-out trên 9 tốc độ, pool 207 scene`

---

### Phase 5 — Dây train A/B (dựng mới, không chép `main`)

#### T19. `spray/ab_config.py` — hai arm khác đúng một đường

**Files:** tạo `spray/ab_config.py` + `tests/test_ab_config.py`

> Đây là file **trùng tên** với file đã xoá ở `f7f0914` trên `sspp`, nhưng **nội dung mới**:
> arm B dùng `PlumeCacheTransform` (không state) chứ không dùng `PlumeTransform` +
> `SprayContextTransform`. Không `git show main:spray/ab_config.py` — bản đó gắn với dây
> stateful đã bỏ.

Test bắt buộc:

```python
# Vị trí chèn KHÔNG hard-code: `train_pipeline` thật của pin da93b27 có 18 bước
# (LoadMultiViewImageFromFiles … Collect3D), và ObjectPaste/ImageAug3D/GridMask
# nằm giữa. Test phải TÌM vị trí, không giả định số.
PLUME_STEP = "PlumeCacheTransform"


def test_arms_differ_at_exactly_one_pipeline_path():
    cfg_a = build_cfg("A")
    cfg_b = build_cfg("B")
    diff = diff_paths(cfg_a, cfg_b)
    assert len(diff) == 1, f"hai arm khác {len(diff)} đường: {diff}"
    assert diff[0].endswith(".type")
    index = int(diff[0].split(".")[1])
    assert cfg_b["train_pipeline"][index]["type"] == PLUME_STEP
    assert cfg_a["spec"] == cfg_b["spec"]        # cùng ngân sách, cùng seed


def test_plume_step_sits_right_after_the_geometric_augment():
    """Plume phải nằm SAU RandomFlip3D (hộp đã ở hệ cuối) và TRƯỚC mọi bước format."""
    types = [step["type"] for step in build_cfg("B")["train_pipeline"]]
    index = types.index(PLUME_STEP)
    assert types.index("RandomFlip3D") < index
    for formatting in ("DefaultFormatBundle3D", "CleanPointsFormatBundle3D", "Collect3D"):
        if formatting in types:
            assert index < types.index(formatting)
    # chỉ MỘT bước plume, không nhân đôi
    assert types.count(PLUME_STEP) == 1


def test_arm_a_has_no_plume_step():
    types = [step["type"] for step in build_cfg("A")["train_pipeline"]]
    assert PLUME_STEP not in types


def test_removing_the_plume_step_makes_the_invariant_fail():
    broken = build_cfg("B")
    broken["train_pipeline"] = [
        step for step in broken["train_pipeline"] if step["type"] != PLUME_STEP
    ]
    with pytest.raises(AssertionError):
        assert_one_difference(build_cfg("A"), broken)
```

`build_cfg` dựng `train_pipeline` bằng cách **đọc** `mit/bevfusion/configs/nuscenes/default.yaml`,
giữ nguyên thứ tự, rồi chèn bước plume ngay sau `RandomFlip3D` (cùng chỗ `main` từng chèn
`SprayContextTransform` + `PlumeTransform`), và đổi hai bước format sang bản có `points_clean`:

```python
RENAMED_STEPS = {
    "DefaultFormatBundle3D": "CleanPointsFormatBundle3D",
    "Collect3D": "CleanPointsCollect3D",
}
PLUME_ANCHOR = "RandomFlip3D"       # chèn ngay sau bước này
```

> **Vì sao đổi tên bước format:** `DefaultFormatBundle3D` của pin chỉ gói `points`, còn
> `Collect3D` chỉ chuyển các key trong `keys` — nên `points_clean` không xuống được model.
> `spray/pipeline.py` trên `main` (đã xoá ở `f7f0914`) chính là hai lớp thay thế đó.
> Trong plan này phải **viết mới** `spray/pipeline.py` với hai lớp
> `CleanPointsFormatBundle3D` / `CleanPointsCollect3D`, cùng test assert `points_clean`
> có mặt trong batch sau `Collect3D`. Bước này thuộc **T19b** bên dưới, làm trước T20.

`TRAIN_SPEC` (một chỗ duy nhất, cả hai arm đọc):

```python
TRAIN_SPEC = dict(
    seed=0, batch_size=2, lr=1e-4, weight_decay=0.01,
    optimizer="AdamW", max_iters=2000, warmup_iters=100,
    grad_clip=5.0, eval_every=500,
)
```

**Verify:** `$PY -m pytest tests/test_ab_config.py -q` → `≥ 5 passed`

**Commit:** `feat(train): A/B config — hai arm khác đúng một đường pipeline`

#### T19b. `spray/pipeline.py` — để `points_clean` xuống được model

**Vì sao phải có:** `PlumeCacheTransform` ghi `results["points_clean"]`, nhưng hai bước format
của pin nuốt nó: `DefaultFormatBundle3D` chỉ gói `points`, `Collect3D` chỉ chuyển key có trong
`keys` và **raise `KeyError`** nếu key thiếu. Không có hai lớp thay thế thì `points_clean`
không bao giờ tới `BEVFusion.forward`.

**Files:** tạo `spray/pipeline.py` + `tests/test_pipeline_clean_key.py`

```python
"""Hai lớp format thay thế để mang ``points_clean`` xuống model.

Bản gốc của pin bỏ qua key lạ (``DefaultFormatBundle3D``) hoặc raise
(``Collect3D``), nên ``points_clean`` chỉ tới được model nếu cả hai bước được
thay. ``clean_key=None`` trả về đúng hành vi của bản gốc — để một config không
dùng plume vẫn chạy y như trước.
"""

from __future__ import annotations

DEFAULT_CLEAN_KEY = "points_clean"


def build_format_bundle():
    from mmdet3d.datasets.pipelines.formating import DefaultFormatBundle3D

    class CleanPointsFormatBundle3D(DefaultFormatBundle3D):
        def __init__(self, clean_key=DEFAULT_CLEAN_KEY, **kwargs):
            self.clean_key = clean_key
            super().__init__(**kwargs)

        def __call__(self, results):
            clean = results.get(self.clean_key) if self.clean_key else None
            results = super().__call__(results)
            if clean is not None:
                # DC(arr, stack=False) đúng như bản gốc xử lý "points":
                # xem DefaultFormatBundle3D.__call__ trong
                # mit/bevfusion/mmdet3d/datasets/pipelines/formating.py
                from mmcv.parallel import DataContainer as DC

                results[self.clean_key] = DC(clean, stack=False)
            return results


def build_collect3d():
    from mmdet3d.datasets.pipelines.formating import Collect3D

    class CleanPointsCollect3D(Collect3D):
        def __init__(self, keys, clean_key=DEFAULT_CLEAN_KEY, **kwargs):
            self.clean_key = clean_key
            keys = list(keys)
            if clean_key is not None and clean_key not in keys:
                keys.append(clean_key)
            super().__init__(keys=keys, **kwargs)

        def __call__(self, results):
            output = super().__call__(results)
            if self.clean_key is not None and self.clean_key not in output:
                raise KeyError(
                    f"{self.clean_key} missing after Collect3D — "
                    "PlumeCacheTransform must run before the formatting steps"
                )
            return output


def install():
    from mmdet.datasets.builder import PIPELINES

    PIPELINES.register_module(name="CleanPointsFormatBundle3D")(
        build_format_bundle()
    )
    PIPELINES.register_module(name="CleanPointsCollect3D")(build_collect3d())
```

> **Lưu ý cho implementer:** `_wrap` ở trên là khung, **không** phải bản cuối. Bản đúng phải
> theo `DefaultFormatBundle3D` của pin: bọc bằng `DataContainer(array, stack=False)` và gắn
> `meta_keys` giống bản gốc. Đọc
> `mit/bevfusion/mmdet3d/datasets/pipelines/formating.py` dòng của `DefaultFormatBundle3D`
> và **copy đúng cách nó xử lý `points`**, thay key. Đừng tự nghĩ ra cách bọc mới.

**Test (chạy được trên laptop, không cần mmdet3d — dùng monkeypatch):**

```python
import sys
import types

import pytest

from spray.pipeline import build_collect3d


class _FakeCollect3D:
    """Thay cho bản của pin: chỉ chuyển các key có trong ``keys``."""

    def __init__(self, keys, **kwargs):
        self.keys = list(keys)

    def __call__(self, results):
        return {key: results[key] for key in self.keys}


@pytest.fixture
def fake_mmdet3d(monkeypatch):
    module = types.SimpleNamespace(Collect3D=_FakeCollect3D)
    monkeypatch.setitem(
        sys.modules, "mmdet3d.datasets.pipelines.formating", module
    )
    return module


def test_collect3d_appends_the_clean_key(fake_mmdet3d):
    step = build_collect3d()(keys=["points", "gt_bboxes_3d"])
    out = step({"points": 1, "gt_bboxes_3d": 2, "points_clean": 3})
    assert "points_clean" in out
    assert out["points_clean"] == 3


def test_clean_key_none_restores_vendor_behaviour(fake_mmdet3d):
    step = build_collect3d()(keys=["points"], clean_key=None)
    out = step({"points": 1})
    assert out == {"points": 1}


def test_missing_clean_key_raises_with_a_useful_message(fake_mmdet3d):
    step = build_collect3d()(keys=["points"])
    with pytest.raises(KeyError, match="PlumeCacheTransform must run before"):
        step({"points": 1})
```

**Chạy:** `$PY -m pytest tests/test_pipeline_clean_key.py -q` → `3 passed`

**Commit:** `feat(train): hai bước format mang points_clean xuống model`

#### T20. Kernel Kaggle `kaggle/train_nuscenes/` — dựng mới

**Files:** tạo
```
kaggle/train_nuscenes/kernel-metadata.json
kaggle/train_nuscenes/bootstrap.py      # cài môi trường MIT (py3.8 + mmcv-full 1.4.0 + mmdet3d da93b27)
kaggle/train_nuscenes/main.py           # train 1 arm theo --arm
kaggle/train_nuscenes/task_args.txt
```

**Bắt buộc đọc trước khi viết `bootstrap.py`:** `kaggle/gate_c/kernel.py` dòng 315–340 đã có
đúng chuỗi cài + compile 12 CUDA op của `mmdet3d`, và nó **đang chạy được**. Chép logic đó,
không phát minh lại. Ghi rõ trong file: "ported from `kaggle/gate_c/kernel.py`".

`task_args.txt`:

```
--arm=B --max-iters=2000 --seed=0 --out=/kaggle/working/arm_b.pth
```

**Điều kiện bắt buộc trong `main.py`** (mỗi cái một assert, in ra log):

1. In `AB_INFO arm=<A|B> steps=<n> batch=<n> lr=<x> plume_cache=<path|none> n_tokens=<k>`;
2. Mỗi 50 bước in `n_points_min` và `n_points_max` **của batch** — arm B phải **lớn hơn**
   arm A trên cùng frame chỉ số; bằng nhau ⇒ plume không vào, dừng;
3. `checkpoint` phải đúng **33.362.653 byte** trước khi load (sai ⇒ `SystemExit`);
4. Kết thúc in `AB_TRAIN_OK arm=<X> steps=<n> ckpt=<path> size=<bytes>`.

**Verify local (không tốn GPU):**

```bash
$PY -m py_compile kaggle/train_nuscenes/main.py kaggle/train_nuscenes/bootstrap.py && echo COMPILE_OK
$PY -c "import json;d=json.load(open('kaggle/train_nuscenes/kernel-metadata.json'));print(d['id'],d['enable_gpu'],len(d['dataset_sources']))"
```

Kỳ vọng: `COMPILE_OK` và `nguynhuy9669/<tên> True <n>`.

**Commit:** `feat(kaggle): kernel train A/B nhánh nuscenes (dựng mới, không chép main)`

#### T20b. `scripts/kaggle_code_sync.py` — đóng gói code thành Kaggle dataset

**Vì sao cần:** kernel đọc code từ dataset `nguynhuy9669/bevfusion-spray-pilot-code`, không
đọc từ repo. Script sync đã bị xoá cùng dây nuScenes (`c2aa23c`), phải viết lại.

**Files:** tạo `scripts/kaggle_code_sync.py` + `tests/test_kaggle_code_sync.py`

Yêu cầu tối thiểu:

1. `--dry-run` in danh sách file sẽ đóng gói **và** tổng byte; không ghi gì;
2. mặc định **loại** `data/`, `results/`, `.scratch/`, `*.pth`, `__pycache__` — đóng gói nhầm
   18 GB roadspray sẽ làm dataset vượt hạn mức;
3. bắt buộc có `spray/`, `scripts/`, `proxy_eval/`, `mit/bevfusion/configs/`, `kaggle/`;
4. in marker `CODE_SYNC files=<n> bytes=<b> out=<path>`;
5. test assert: có `spray/plume.py`, **không** có `data/` và không có `*.pth`.

**Verify:**

```bash
$PY scripts/kaggle_code_sync.py --dry-run 2>&1 | grep CODE_SYNC
```

Kỳ vọng: `bytes` < 5 MB (nếu ra hàng trăm MB ⇒ bộ lọc sai, dừng lại).

> **Bẫy đã trả giá:** upload dataset **không** bump version ⇒ kernel chạy code cũ với log xanh.
> Sau khi upload phải gọi riêng `kaggle datasets version -p <dir> -m "<why>" --dir-mode zip`
> rồi kiểm `lastUpdated` trước khi push kernel.

**Commit:** `feat(kaggle): script đồng bộ code thành dataset, lọc data/pth`

#### T21. Smoke test trên Kaggle trước khi đốt GPU

**Thứ tự bắt buộc** (mỗi bước dừng nếu bước trước sai):

```bash
# 1. đồng bộ code lên dataset Kaggle — script KHÔNG có trên nhánh này
#    (đã bị xoá cùng dây nuScenes). Implementer viết mới ở T20b, xem dưới.
ls scripts/kaggle_code_sync.py        # kỳ vọng: tồn tại SAU T20b
$PY scripts/kaggle_code_sync.py 2>&1 | tail -3
kaggle datasets list -m 2>/dev/null | grep bevfusion-spray-pilot-code

# 2. push kernel smoke
kaggle kernels push -p kaggle/train_nuscenes

# 3. theo dõi — KHÔNG poll bằng sleep, dùng background + notify
kaggle kernels status nguynhuy9669/bevfusion-spray-train-nuscenes
```

Kỳ vọng trong log: `SMOKE_OK`, `n_points arm=A <n>`, `n_points arm=B <m>` với `m > n`,
`plume_cache tokens=<k> empty=0`.

Hai bẫy phải nhớ (đã trả giá trên `sspp`):
- upload dataset code **không bump version** ⇒ kernel chạy code cũ với log xanh. Phải
  `kaggle datasets version` riêng rồi kiểm `lastUpdated`.
- `QUEUED` 20–60 phút là bình thường; hết quota GPU thì `ERROR` **ngay**, không treo.

**Commit:** `chore(kaggle): smoke test dây train A/B`

#### T21b. Chạy smoke trên nuScenes Mini — nghiệm thu "thông luồng"

**Mục tiêu duy nhất của bước này:** chứng minh dây chạy đúng đầu-cuối trên dữ liệu thật.
**Không** trả lời "augment có tác dụng" — Mini có 404 keyframe, không đủ lực (xem §Risks R2).

**Files:** `data/nuscenes_infos_mini_{train,val}.pkl` sinh trên Kaggle bằng
`scripts/make_mini_split.py` (viết mới — bản `main` đã xoá; dùng danh sách
`val` chính thức của `mit/bevfusion/nuscenes/utils/splits.py` để **không** rò val vào train).

**Bốn assert phải xanh, in ra log:**

```bash
$PY scripts/build_plume_cache.py --infos data/nuscenes_infos_mini_train.pkl \
  --dataset-root /kaggle/input/nuscenes-mini --road-z-m -1.84 --substeps 5 \
  --out data/plume_cache_mini.npz 2>&1 | grep -E 'PLUME_CACHE|MINI'
```

| # | assert | kỳ vọng | nếu sai nghĩa là |
|---|---|---|---|
| M1 | `PLUME_CACHE tokens=404` | đúng 404 (10 scene × ~40) | infos dựng sai hoặc lọc mất frame |
| M2 | `empty <= 4` (≤1 % token không có điểm) | gần 0 | box lọc lớp quá tay, hoặc `v_aug` bị 0, hoặc `road_z` sai ⇒ plume ngoài `point_cloud_range` |
| M3 | `det/frame p50 > 0` | > 0 | raycast không bắn trúng gì |
| M4 | `z - road_z` p50 ∈ [0; 1,5] m | trong dải | `road_z_m = -1,84` sai (đây là giá trị của nuScenes LiDAR so với mặt đường, phải kiểm bằng đo chứ không tin) |

Rồi train 50 bước mỗi arm (không phải 2.000):

```bash
$PY kaggle/train_nuscenes/main.py --arm=B --max-iters=50 --plume-cache=data/plume_cache_mini.npz
```

**Nghiệm thu (cả 5 phải đúng, sai cái nào dừng cái đó):**

```
SMOKE_OK
n_points arm=A <n>            n_points arm=B <m>     với m > n   (plume vào được)
points_clean present=1                                (T19b chạy)
loss step 50 < loss step 1                            (gradient chảy)
boxes/frame p50 = <số đo>                             (census Task 11 khớp)
```

**Bảng Mini phải ghi vào `docs/measurements/nuscenes-mini-smoke.md`**, kèm câu chốt cố định:

> Mini (10 scene / 404 keyframe) chỉ dùng để chứng minh dây chạy. Mọi so sánh A/B trên Mini
> **không** được trích dẫn như bằng chứng về tác dụng của augmentation: 10 epoch trên 404
> frame là overfit, và CI ở n=10 scene là quá rộng để phân biệt bất cứ effect nào.

**Commit:** `measure(nuscenes): smoke Mini — dây chạy đầu-cuối, 4 assert xanh`

#### T22. Chạy A/B thật (2 kernel, cùng ngân sách)

```bash
kaggle kernels push -p kaggle/train_nuscenes   # arm A
kaggle kernels push -p kaggle/train_nuscenes   # arm B (đổi task_args)
```

Kỳ vọng: hai `AB_TRAIN_OK`, cùng `steps=2000`, hai file `.pth` khác sha256 nhưng **cùng cỡ**
(chênh < 1 % — cùng kiến trúc).

**Commit:** `measure(train): kết quả A/B nuScenes, 2000 bước mỗi arm`

---

### Phase 6 — Chấm và báo cáo

#### T23. `scripts/ab_eval.py` — chấm 3 checkpoint, paired theo scene

**Files:** tạo `scripts/ab_eval.py` + `tests/test_ab_eval.py`

Không viết lại matcher: `proxy_eval.matcher.evaluate_frame` đã chạy được cho SSPP ngay
(`class_names=("object",)` để so nhãn-agnostic, đúng như `scripts/sspp_infer.py:739`).

Bắt buộc:
1. Nhận `--checkpoint` **nhiều lần** (Model 0, A, B) và `--infos` cho phép file pseudo;
2. `assert info.get("pseudo") is not True` khi `--split` là `val`/`test` và cờ
   `--allow-pseudo-eval` **không** bật — pseudo box không được lọt vào hàng quyết định;
3. In bảng `scene × arm → {tp, fp, fn, recall, fp_per_frame, det_per_frame, score_p50}`;
4. Báo effect size + CI95 bootstrap theo scene (B = 20 000), **không** pass/fail.

**Verify:** `$PY -m pytest tests/test_ab_eval.py -q` → `≥ 5 passed`

**Commit:** `feat(eval): chấm A/B paired theo scene, chặn pseudo box ở hàng quyết định`

#### T24. Chạy eval, hai hàng tách hẳn

```bash
# Hàng quyết định: chỉ 36 scene human box, 3 fold, pooled n=36
$PY scripts/ab_eval.py --folds data/sspp_folds.json --split all \
  --human-only \
  --checkpoint data/lidar-only-det.pth \
  --checkpoint /kaggle/input/ab/arm_a.pth \
  --checkpoint /kaggle/input/ab/arm_b.pth \
  --out .scratch/nuscenes-train/eval_human.json

# Hàng phụ (khai rõ trong báo cáo): + 171 scene pseudo, pooled n=207
$PY scripts/ab_eval.py --folds data/sspp_folds.json --split all \
  --allow-pseudo-eval \
  --checkpoint ... --out .scratch/nuscenes-train/eval_pseudo.json
```

**Kỳ vọng định lượng** (để biết phép đo có đủ lực hay không):
- n=36: MDE **0,90 det/frame**; nếu effect thật ≤ 0,9 thì kết quả là "không phân biệt được",
  phải viết đúng như vậy, không viết "không có tác dụng";
- n=207: MDE **0,38 det/frame**;
- Δreal−clean đo được trên cùng harness = **+2,07** ⇒ thang đo có chỗ cho tín hiệu.

**Commit:** `measure(eval): A/B trên SSPP, hàng human + hàng pseudo khai riêng`

#### T25. Ghi kết quả vào doc, gắn nhãn nguồn

**Files:** tạo `docs/measurements/nuscenes-train-ab.md`

Bắt buộc có:
1. bảng 3 checkpoint × (recall, FP/frame, det/frame, score p50, boxes/frame);
2. dòng effect size + CI95 cho từng cặp;
3. **hạn chế** phải khai: (a) tốc độ plume là **lấy mẫu** trên 9 mốc, không phải tốc độ
   ego thật; (b) plume chỉ sinh khi **có xe dẫn phía trước là ô tô** trong 50 m / ±5 m, nên
   arm B chỉ augment `X %` frame — `X` lấy từ census T11; (c) train nền nuScenes, eval SSPP
   ⇒ chuyển domain, không phải cùng domain;
4. nhãn `[ĐO]` / `[PAPER]` / `[CODE]` / `[CHỌN]` cho **mọi** số.

**Commit:** `docs(eval): kết quả A/B nuScenes→SSPP, kèm ba hạn chế`

#### T26. Bảng quyết định — chép từ số đo, không diễn giải lại

Viết vào cuối `docs/measurements/nuscenes-train-ab.md`:

| câu hỏi | trả lời bằng | ngưỡng đọc |
|---|---|---|
| plume lúc train có giúp gì trên spray thật? | `ΔFP/frame(B − A)` tại `τ` cố định | cận trên CI < 0 mới được nói "giảm" |
| có mất gì trên domain gốc? | `ΔFP/frame(B − A)` trên nuScenes val sạch | ≤ +0,5 điểm |
| model học "bỏ qua" hay "học sai chỗ"? | `score_p50` của hộp đúng chỗ + dịch tâm hộp | score tăng & tâm đứng yên = học bỏ qua |

**Commit:** `docs(eval): bảng quyết định A/B`

---

## Tests / validation

**Chạy sau mỗi task, không gộp:**

```bash
$PY -m pytest -q 2>&1 | tail -3
```

| mốc | kỳ vọng |
|---|---|
| trước khi bắt đầu | `200 passed` |
| sau T4 (substeps) | `203 passed` (+3) |
| sau T6 (box + chọn xe dẫn) | `219 passed` (+16) |
| sau T8 (PlumeContext nuScenes) | `222 passed` (+3) |
| sau T10 (cache transform) | `227 passed` (+5) |
| sau T13 (builder + explain) | `231 passed` (+4) |
| sau T16 (pseudo box) | `234 passed` (+3) |
| sau T18 (folds) | `237 passed` (+3) |
| sau T19 (ab_config) | `242 passed` (+5) |
| sau T19b (pipeline clean key) | `245 passed` (+3) |
| sau T23 (ab_eval) | `250 passed` (+5) |

> Số test trong bảng là **kỳ vọng**, không phải ràng buộc: nếu một task viết thêm test thì
> mốc tăng lên. Điều bắt buộc là **0 failed** và không có `skipped`.

**Bốn invariant phải đúng ở mọi thời điểm** (nếu sai là đã hỏng thứ khác):

```bash
# 1. generator không bị đổi tham số
grep -nE 'MAX_AGE_FACTOR|RADIUS_MAX_M' spray/plume_state.py   # 12.0 / 2.0
grep -rn 'diffusion_alpha' --include=*.py spray/              # rỗng
# 2. box vẫn là quy ước adapter
$PY -m pytest tests/test_box_convention.py -q                # pass
# 3. pseudo không lọt eval
grep -n 'pseudo' scripts/ab_eval.py | grep -c assert          # >= 1
# 4. hai arm khác đúng một đường
$PY -m pytest tests/test_ab_config.py -q                      # pass
```

---

## Risks, tradeoffs, open questions

### Rủi ro có thể giết kết luận

| # | rủi ro | dấu hiệu | xử lý |
|---|---|---|---|
| R1 | **Plume lúc train không chuyển được sang spray thật.** Gate C cho thấy plume hại gấp 5× spray thật **lúc eval**; train có thể chỉ dạy model "bỏ qua đúng chữ ký của generator", không phải "bỏ qua nước". | `ΔFP/frame(B−A)` trên spray thật ≈ 0 nhưng trên plume tự sinh thì giảm mạnh | phép thử tách bạch: eval thêm một nhánh `plume` (tự sinh) và một nhánh `real`. Nếu B chỉ thắng ở nhánh tự sinh ⇒ **kết luận âm**, wording: "generator hiện tại không chuyển được", **không** phải "augment vô dụng". |
| R2 | **nuScenes Mini rất nhỏ.** `[ĐO]` 2026-11-27: **10 scene / 404 keyframe / 18.538 annotation**, keyframe cách 0,50 s, **3.531 sweep ở 20 Hz** (8,7 sweep/keyframe). 2.000 bước × batch 2 = 4.000 sample ⇒ **~10 epoch**. | log `AB_INFO n_samples=404 n_scenes=10` | 10 epoch trên 404 frame là **rất dễ overfit**. Mini chỉ đủ **thông luồng**, không kết luận. |
| R3 | **Plume chỉ phủ một phần frame.** `select_lead_box` trả rỗng khi ego không bám đuôi ô tô, hoặc xe dẫn **quá gần** tới mức slab sinh rơi vào vùng bị lọc. | **ĐÃ ĐO trên Mini**: `with_lead = 71,5 %` nhưng `spawnable (lead_x ≥ 6,49 m) = 21,5 %`; `lead_x` p50 = **3,4 m** (paper: 20 m); ego p50 = 18,4 km/h | `spawnable < 10 %` ⇒ **dừng, báo user**. Trên Mini nó là 21,5 % ⇒ Mini **chỉ để thông luồng**, không kết luận. Phải census lại trên full `v1.0-trainval` trước khi train thật. Chi tiết: `docs/measurements/nuscenes-mini-census.md` |
| R4 | **`road_z_m` của nuScenes khác SSPP**, plume lơ lửng hoặc chìm. | test T8 chỉ kiểm hằng số truyền vào, không kiểm mặt đường thật | thêm phép đo ở Task 14: in `z − road_z` của điểm plume; p50 phải trong `[0; 1,5] m`. |
| R5 | **Pseudo box dùng cho eval** làm hỏng metric (3D IoU p50 0,872, yaw = 0, itr 2–6). | ai đó bật `--allow-pseudo-eval` cho hàng quyết định | Task 23 assert chặn; hàng pseudo chỉ là hàng phụ, khai riêng. |

### Đánh đổi đã chọn và vì sao

| chọn | thay vì | vì sao |
|---|---|---|
| **cache offline** | stateful trong dataloader | stateful + `workers_per_gpu ≥ 1` là bẫy 13 đã trả giá; cache deterministic và trả tiền raycast một lần |
| **tốc độ lấy mẫu rời rạc 9 mốc** | `U(50,130)` liên tục | mỗi mốc có số cụm/frame đo được đứng sau; nội suy thì không |
| **giữ 0,1 s + substeps** | nhét `dt=0,5` một bước | đo được: 5 bước 0,1 s khớp đích ±10 %, một bước 0,5 s thiếu 4–5× |
| **pseudo box train, human box eval** | pseudo box cả hai | ADR-0006 D4; 3D IoU 0,872 đủ tốt làm target, không đủ tốt làm thước |
| **dựng kernel mới** | chép `kaggle/e2e/main.py` từ `main` | user chốt không restore từ `main`; chỉ chép **logic bootstrap** từ `kaggle/gate_c/kernel.py` (cùng nhánh) |

### Câu hỏi mở — cần user trả lời

1. **Cho sửa `spray/plume.py` để thêm `substeps` không?** (Task 3/4 vs Task 3b)
   Plan cũ ghi "không đụng generator". Tôi cho rằng đây là sửa **bộ tích phân**, không phải
   tham số generator, nhưng đó là quyết định của user.
   **Đã chốt (2026-11-26):** plume chỉ sinh khi có **xe dẫn phía trước là ô tô** (`car`/`truck`)
   trong 50 m và |y| ≤ 5 m — xem §Architecture. Điều này thay cho phương án "phun cho mọi box"
   và tự nó giải quyết vấn đề 10 lớp của nuScenes.
2. **Pseudo box có được vào hàng eval không?** Mặc định của tôi: **không** — hàng phụ, khai
   riêng. Công suất tăng 2,4× nhưng confound `itr 1 vs 2–6` (spray thật lệch 1,4×) là thật.
3. **nuScenes Mini hay full?** — **ĐÃ CHỐT: Mini trước, chỉ để thông luồng.**
   **Đã khám phá Mini trên Kaggle (2026-11-27)** — chi tiết `docs/measurements/nuscenes-mini-census.md`:
   - Bản dùng được: `babydriver1233/lephyjepa-nuscenes-mini-lidar-dataset-v-1-0` hoặc
     `aadimator/nuscenes-mini` (cả hai 4,20 GB, có **13 file** `v1.0-mini/*.json`).
     Ba bản khác trên Kaggle **thiếu metadata** ⇒ devkit không chạy.
   - `[ĐO]` 10 scene / **404 keyframe** / 18.538 annotation / **3.531 sweep ở 20 Hz**.
     Sweeps thật ⇒ mật độ điểm trung thực với paper — điều bản full keyframe-only không có.
   - `[ĐO]` **21,5 vehicle/frame** (p50 16, max 57). Xác nhận: không được phun cho mọi box.
   - `[ĐO]` `with_lead = 71,5 %` nhưng **`spawnable = 21,5 %`**, `lead_x` p50 = **3,4 m**
     (paper đo ở **20 m**), ego p50 **18,4 km/h**. Mini toàn tắc đường / bãi đỗ: ego 0 km/h ở
     2 scene, và tâm "xe dẫn" ở 3,4 m nghĩa là ego đang xuyên qua thân xe.
   Hệ quả:
   - Mini **đủ** chứng minh dây chạy: cache có điểm, `points_clean` xuống model, loss giảm,
     `n_points arm B > arm A`;
   - Mini **không đủ** kết luận: n = 10 scene **và** vị trí plume sai miền so với paper;
   - **Trước khi train thật phải census lại trên full `v1.0-trainval`**, và ngưỡng đọc là
     `spawnable`, không phải `with_lead`.
4. **Ngân sách GPU còn bao nhiêu lượt?** 2000 bước × 2 arm + eval 3 checkpoint trên 207 scene
   là ít nhất 3 lượt kernel. Nếu ít hơn, phải cắt xuống 1 arm đối chứng (bỏ Model 0 khỏi eval
   — sai số đo đã có sẵn từ gate C).
5. **Một xe dẫn hay mọi xe phía trước?** Plan chốt **một** (xe gần ego nhất) vì: (a) paper A
   đo một xe; (b) chọn nhiều xe thì chi phí tăng tuyến tính và mật độ plume vượt xa dữ liệu
   thật (A3-V đã đo: following đậm 2,7–4,6× ở 80–110 km/h khi chỉ một nguồn). Nếu census T11
   cho thấy `with_lead` thấp dưới 25 %, phương án nới là **thêm xe dẫn thứ hai cùng làn**
   trước khi nới `max_range_m` — vì nới range là vượt miền paper, còn thêm xe cùng làn thì
   vẫn đúng vật lý.
