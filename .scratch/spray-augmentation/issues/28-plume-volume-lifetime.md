# 28: Bước 1–3 — vùng phun sau đuôi, sinh cụm, vòng đời

**Type:** task
**Status:** needs-triage
**Blocked by:** 26, 25 (`wfh` đơn vị + `K`)
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ

`[PAPER]` §III-C: vùng phun sau đuôi xe, dài theo `v·Δt`; chu kỳ `Δt = 0,1 s` `[CODE]`.
Sinh cụm `[CODE]`: `mean = (0,2·wfh + 0,1)·(v_kmh − 50)`, bán kính lognormal `μ=−1,2 σ=0,8`
(median 0,30 m), `T = 0,02·wfh·(v−50) + 0,2`, drag `N(−0,12; 0,04)`, `P_t = e^(−age/T)`.
v1 hiện **không có trạng thái thời gian**: mỗi frame sinh lại từ đầu, không cụm nào có tuổi
⇒ không có vệt, gap 1,16–5,84 m `[ĐO]`.

## Số chính xác vừa đọc lại từ code (2026-11-10) — dùng đúng, không suy

| Đại lượng | Giá trị | Nguồn |
|---|---|---|
| Số cụm/frame | `round(max(0, (0,2·wfh_mm + 0,1)·(v_kmh − 50)))` — **tất định** | `dee.cpp:509–512` |
| Khối phun | dài `|v|·0,1`; rộng **3,4 m**; cao **1,5 m**; đáy = đáy box | `dee.cpp:571–591` |
| `radius` | `min(1,0; lognormal(−1,2; 0,8))` | `dee.cpp:531` |
| `age` khởi tạo | **−0,1 s** (âm) | `dee.cpp:533` |
| `T` | `N(wfh·0,02·(v_kmh−50) + 0,2; σ = 0,2)` | `dee.cpp:534–536`, `hpp:47` |
| `v_z` cụm | `v_z,vật + 5·U(0,1)` | `dee.cpp:540` |
| `drag` | `N(−0,12; 0,04)` | `dee.cpp:542` |
| Cập nhật vận tốc | `v += drag·v̂_rel·|v_rel|²·Δt`, gió 208° / 2 m/s | `dee.cpp:396–421` |
| Xoá cụm | `age > 4·T` | `dee.cpp:453` |

## Việc phải làm

1. `spray/plume_state.py` — `SprayCluster` (pos, vel, radius, age, T, drag, object_id) +
   `PlumeState` giữ dict `{(scene_token, object_id): [clusters]}`; `resample(rng)` số hạt
   mỗi cụm **mỗi frame** (không lặp y hệt).
2. `spray/plume.py` — thay `_open_plume_box`/vùng quanh tâm bằng khối sau đuôi theo bảng trên
   (rộng 3,4 / cao 1,5 là hằng của code gốc, **không** lấy theo kích thước box).
3. Cập nhật mỗi frame theo đúng công thức drag có gió; xoá khi `age > 4·T`.
4. `tests/test_plume_lifetime.py` — vệt liên tục: cụm sinh ở frame `k` phải còn ở `k+1..k+3`;
   `P_t` giảm đơn điệu; `age > 3T` → mất.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` không giảm.
- [ ] Marker `PLUME_STATE spawned=<n> alive=<n> expired=<n>` mỗi frame.
- [ ] Trên 5 frame liên tiếp cùng scene: `alive` > 0 và `expired` > 0 ít nhất 1 lần.
- [ ] Không còn cụm nào nằm trong thân box (`rejected_box` giữ nguyên counter).
- [ ] Gap dọc quỹ đạo: p50 < 1,0 m (v1: 3,32 m `[ĐO]`).

## Cấm

- Không đổi ngưỡng 40 km/h, không đổi `K`, `T`, drag.
- Không dùng `time.time()`; thời gian lấy từ `age` cộng dồn theo frame.
