# 28a: `spray/plume_state.py` — trạng thái thời gian của cụm (spawn / advect / expire)

HEAD: aae6ac1  Nhánh: main
Skill: tdd — `/Users/huynguyen/.agents/skills/tdd` (1 skill duy nhất)

Đây là **nửa đầu** của ticket 28 (`issues/28-plume-volume-lifetime.md`). Nửa sau (28b: khối sau đuôi,
nối vào `spray/plume.py`, marker, đo gap) làm ở brief riêng. **Brief này KHÔNG được sửa `spray/plume.py`.**

## Hiện trạng (PM đã kiểm)

- `spray/plume.py` sinh plume **không có trạng thái thời gian**: mỗi frame dựng lại từ đầu, không cụm nào có
  tuổi. Đo trên v1: khoảng cách dọc quỹ đạo giữa các cụm p50 = **3,32 m**, giao động 1,16–5,84 m.
- Đã có (ticket 26, commit `20d4a82`): `spray/plume_context.py` — `PlumeContext` với `object_speed_mps`,
  `ego_speed_mps`, `wfh_mm`, `road_z_m`; `spawn` cần `v_abs = object_speed_mps`, `v_rel = object − ego`.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **200 passed, 4 skipped**.

## Quyết định đã chốt — dùng đúng, không suy lại

`[CHỌN 2026-11-10 — user]` **hai tốc độ, hai vai**:

| Vai | Biến |
|---|---|
| `count` cụm và `T` (thời gian sống) | **`v_abs`** = tốc độ xe dẫn so với mặt đường |
| vận tốc đầu của cụm + advection (trôi vệt) | **`v_rel`** = `v_abs − ego_speed` |

`[CHỌN 2026-11-10 — user]` **`wfh` tính bằng mm** cho cả `count` và `T`.

## Số chính xác — chép đúng, cấm tự chỉnh

| Đại lượng | Công thức | Nguồn |
|---|---|---|
| Số cụm **mỗi chu kỳ** | `mean = (0,2·wfh_mm + 0,1)·(v_abs_kmh − 50)`; `n = round(max(0, mean))` — **tất định**, không Poisson | `[CODE]` `dee.cpp:509–512` |
| Bán kính cụm | `min(1,0 ; lognormal(μ=−1,2, σ=0,8))` → median **0,30 m** | `[CODE]` `dee.cpp:531` |
| `T` mỗi cụm | `T ~ N(wfh_mm·0,02·(v_abs_kmh − 50) + 0,2 ; σ = 0,2)`; clamp `T = max(T, 0)` | `[CODE]` `dee.cpp:534–536` |
| `age` khởi tạo | **−0,1 s** (âm, để cụm chưa hoạt động ở frame sinh) | `[CODE]` `dee.cpp:533` |
| Vận tốc đầu | `v_cluster = v_rel` (vector), `v_z = 0 + 5·U(0,1)` — cụm nằm thấp, bay lên | `[CODE]` `dee.cpp:540` |
| `drag` | `N(−0,12 ; 0,04)` (âm = giảm tốc) | `[CODE]` `dee.cpp:542` |
| Gió | 2 m/s, hướng **208°** theo quy ước khí tượng (hướng gió **tới từ**) | `[CODE]` `dee.cpp` |
| Cập nhật vận tốc | `v += drag·v̂_air·|v_air|²·Δt`, với `v_air = v_cluster − W` (W = vector gió) | `[CODE]` `dee.cpp:396–421` |
| Cập nhật vị trí | `pos += v·Δt` | `[CODE]` |
| Xoá cụm | `age > 4·T` | `[CODE]` `dee.cpp:453` |
| `P_t` (hiển thị) | `exp(−age / T)` | `[PAPER]` §III-C |
| Chu kỳ | `Δt = 0,1 s` | `[CODE]` |

## Việc phải làm

### 1. `spray/plume_state.py` (file mới, chỉ numpy + stdlib)

- `@dataclass SprayCluster`: `pos (3,)`, `vel (3,)`, `radius: float`, `age: float`, `ttl: float`,
  `drag: float`, `object_id: int`, `cluster_id: int`.
- `class PlumeState`:
  - `spawn(context, *, rng, dt=0.1, config=None) -> list[SprayCluster]` — dùng **`v_abs`** cho `n` và `T`,
    **`v_rel`** cho vận tốc đầu; `object_id` lấy từ tham số (`object_id: int`).
  - `advance(dt: float) -> None` — advection theo bảng trên, rồi `age += dt`.
  - `prune() -> int` — xoá cụm `age > 4·T`, trả số cụm bị xoá.
  - `alive(object_id) -> list[SprayCluster]`.
  - `counters` — `spawned`, `alive`, `expired` (số học trong chu kỳ vừa rồi), để 28b in marker.
  - Khoá state theo `(scene_token, object_id)`; **reset khi `scene_token` đổi** (không rò cụm giữa scene).
- `cluster_count_for_speed_abs(v_abs_kmh, wfh_mm) -> int`, `lifetime_mean_s(v_abs_kmh, wfh_mm) -> float`:
  hàm thuần, tách riêng để test công thức mà không cần dựng state.
- Không import `spray.plume` (tránh vòng import). Không đọc `os.environ`. Không dùng `time.time()`.

### 2. `tests/test_plume_lifetime.py` (file mới) — viết **trước**, 7 test

1. `cluster_count_for_speed_abs`: `wfh=1,0 mm`, `v=130` → **24**; `v=80` → **9**; `v=50` → **0**;
   `v=40` → **0** (dưới ngưỡng kích hoạt 40 km/h); `v=130, wfh=0,001` (nếu ai truyền mét nhầm) → **8**
   (test này ghim đơn vị mm: truyền mét cho ra số khác).
2. `lifetime_mean_s`: `v=130, wfh=1,0` → **1,80 s** (sai số 1e-9); `v=50` → 0,20 s.
3. Vệt liên tục: `spawn` ở frame `k` với `T` cố định (σ=0) → `alive` > 0 ở `k+1`, `k+2`,
   và chưa bị xoá trước `age > 4T`.
4. `P_t = exp(−age/T)` giảm đơn điệu: `P(age=0,2T) > P(0,5T) > P(2T)`.
5. Xoá khi `age > 4T`: sau đủ số bước `Δt`, `expired` tăng và `alive` giảm.
6. Advection giảm tốc: với `drag < 0`, `|v_cluster − W|` sau một bước **nhỏ hơn** trước; với `drag = 0`
   thì bằng nhau (so sánh `np.allclose`).
7. Tất định theo seed: cùng seed → cùng danh sách cụm (so `pos` từng phần tử); khác seed → khác.

### 3. Không làm gì khác

Không sửa `spray/plume.py`, `spray/plume_context.py`, `spray/config/*.yaml`, `tests/` cũ. Không thêm dependency.

## Tiêu chí nghiệm thu

- [ ] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥ 207 passed, 4 skipped**
      (200 cũ + 7 mới). Nêu số thật.
- [ ] `pytest -q tests/test_plume_lifetime.py` xanh, không skip.
- [ ] `git status --porcelain` chỉ có 2 file mới: `spray/plume_state.py`, `tests/test_plume_lifetime.py`.
- [ ] `grep -c "v_abs\|v_rel" spray/plume_state.py` > 0 và trong docstring ghi rõ vai nào dùng biến nào.
- [ ] Không có `time.time()`, không `os.environ`, không import `spray.plume`.
- [ ] Báo cáo nêu 3 số: `count(130, wfh=1)`, `T(130, wfh=1)`, số test thật.

## Cấm

- Không đổi các hằng 0,2 / 0,1 / 50 / 0,02 / 0,2 / 4 / 0,1 s, `μ=−1,2 σ=0,8`, `drag N(−0,12; 0,04)`,
  gió 208° / 2 m/s.
- Không thêm sàn cho `v ≤ 50`; không đổi ngưỡng kích hoạt 40 km/h.
- Không sửa `PlumeConfig` (việc đổi `water_film_height_m` → `_mm` là của 28b).
- Không tự commit; PM nghiệm thu rồi commit.