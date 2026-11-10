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

---

## PM nghiệm thu 28a — 2026-11-10 (nửa đầu: state module)

**Trạng thái: 28a done, 28b next.** Brief: `dispatch/dispatch-28a.md` · CommandCode `--skill tdd`, exit 0.

| Kiểm | Kết quả `[ĐO]` |
|---|---|
| `pytest -q tests/` | **207 passed, 4 skipped** (200 cũ + 7 mới), 0 skip mới |
| `pytest -q tests/test_plume_lifetime.py` | 7 passed |
| `git status` | đúng 2 file mới: `spray/plume_state.py` (280 dòng), `tests/test_plume_lifetime.py` (165 dòng) |
| `spray/plume.py` | **không chạm** (diff rỗng) |
| `grep time.time\|os.environ\|import spray.plume` | **0 hit** |
| Ba số chốt công thức | `count(130 km/h, wfh=1 mm) = 24`; `T = 1,80 s`; `count(50 km/h) = 0` — khớp brief |

**Hai vai tốc độ đã vào code đúng chỗ** (đọc code, không tin báo cáo):
`plume_state.py:199–201` — `v_abs_kmh = object_speed_mps·3.6` nuôi `count` + `T`;
`plume_state.py:200` — `v_rel = object_speed_mps − ego_speed_mps` nuôi vận tốc đầu của cụm.
Gió 208°/2 m/s: `wind_vector()` cho `(0,939; 1,766; 0)` m/s = hướng 28°, đúng quy ước khí tượng (gió **từ** 208°).

### Ba điểm phải xử lý ở 28b (PM ghi lại, không sửa lúc này)

1. **Vận tốc cụm đang gán cứng theo `+x`**: `vel = [v_rel, 0, vz]`. Đúng dấu cho xe phía trước trên trục x,
   nhưng sai nếu hướng xe lệch trục x > ~10°. `PlumeContext` hiện chỉ có **độ lớn** tốc độ ⇒ 28b phải thêm
   vector/hướng vận tốc của vật (hoặc ghi rõ đây là giả định và kiểm bằng góc heading của eval set).
2. **`P_t` > 1 ở frame sinh**: `age` khởi tạo `−0,1 s` nên `exp(−age/T) = e^{+0,055} = 1,057`. Phải clamp `1,0`.
3. **Vị trí spawn là placeholder**: `pos = sensor_origin + jitter(±0,5 m)` (có ghi chú trong code). 28b thay
   bằng khối sau đuôi `3,4 × 1,5 × v_abs·0,1` m, đáy = đáy box.

**Chưa kiểm được ở 28a (đúng phạm vi):** marker `PLUME_STATE`, gap dọc quỹ đạo, và ràng buộc "không cụm nào
nằm trong thân box" — cả ba cần nối vào `spray/plume.py`, tức 28b.
