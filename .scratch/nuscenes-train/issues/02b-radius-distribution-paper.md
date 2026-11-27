# Brief 02b: phân bố bán kính cụm khớp paper + viz dùng `select_alive`

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `nuscenes-train`.
**Không hỏi lại. Không mở rộng phạm vi. Không sửa file ngoài danh sách.**

---

## Bối cảnh

### 1. Phân bố bán kính đang lệch paper ở 3 chỗ

Paper: `~/.hermes/drafts/spray_paper/2212.08558.pdf`, §III-B + Fig. 5. Nguyên văn:

> "Since the clusters are approximated by spheres, the radii r_cl are set to the maximum
> distance of detections to the respective cluster center. [...] A lognormal distribution is
> chosen as the best fit by Matlab's fitdist function. **The parameters of the distribution are
> µ = −1.2 and σ = 0.8 as an example.**"

Tức `r_cl = exp(µ + σ·Z)`, `Z ~ N(0,1)`, µ = −1.2, σ = 0.8 ⇒ median `e^−1.2 = 0.3012 m`.
**Paper không đặt trần trên.**

Code hiện tại (`spray/plume_state.py:72-79, 439-443`):

```python
RADIUS_MU = -1.2          # đúng
RADIUS_SIGMA = 0.72       # paper: 0.8
RADIUS_MAX_M = 2.0        # paper: không có
RADIUS_MEDIAN_M = 0.31    # paper: e^-1.2 = 0.3012
...
radius = min(cfg.radius_max_m, float(np.exp(rng.normal(np.log(radius_median), cfg.radius_sigma))))
```

Comment của `RADIUS_MAX_M` (`spray/plume_state.py:76-78`) biện minh:

```
# (exp(−1,2 + 2,326·0,72) = 1,61 m). Paper không đặt trần; 2,0 m nằm giữa
# p99 (1,61) và p99,9 (2,79) nên cắt bớt ~0,1 % đuôi, không đụng thân phân bố.
```

Một chỗ sai trong lập luận đó: comment ghi "cắt ~0,1 % đuôi" trong khi với
`σ = 0.72` thì `P(r > 2.0) = 0.43 %` (không phải 0,1 %). Ngược lại, con số
`e^{−1,2+2,326·0,72} = 1.61` trong comment là **đúng**.

### 2. Đo hệ quả từng sai lệch `[ĐO]`

Scene `Crafter_dynamic/0060_...` (100 km/h) và `0096_...` (130 km/h), 50 frame, cùng seed,
đo sau `select_alive()`. Script: `.scratch/tmp/radius_variants.py`, log `radius_variants.log`.

| 100 km/h | r p50 | r p90 | r p99 | r max | ở trần | det p50 | det mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| A paper (µ=−1,2 σ=0,8, không trần) | 0,31 | 1,03 | 2,14 | 3,23 | 0 % | 436 | 484 |
| **B code hiện tại** (0,31 σ=0,72 trần 2,0) | 0,31 | 0,91 | 1,76 | 2,00 | 0,5 % | 373 | 407 |
| C 0,31 σ=0,72 không trần | 0,31 | 0,91 | 1,76 | 2,56 | 0 % | 378 | 411 |
| D 0,31 σ=0,80 không trần | 0,31 | 1,03 | 2,14 | 3,23 | 0 % | 436 | 484 |

| 130 km/h | r p50 | r p90 | r p99 | r max | det p50 | det mean |
|---|---:|---:|---:|---:|---:|---:|
| A paper | 0,29 | 0,77 | 1,41 | 1,41 | 220 | 268 |
| **B code hiện tại** | 0,29 | 0,70 | 1,21 | 1,21 | 200 | 239 |
| C 0,31 σ=0,72 không trần | 0,29 | 0,70 | 1,21 | 1,21 | 200 | 239 |
| D 0,31 σ=0,80 không trần | 0,29 | 0,77 | 1,41 | 1,41 | 220 | 268 |

`[SUY LUẬN]` Bỏ trần ở 100 km/h chỉ thêm 1,3 % det (373→378) vì 0,5 % cụm chạm trần.
Sửa σ 0,72→0,80 thêm 17 % (373→436) vì đuôi nặng hơn. Ở 130 km/h trần **không bao giờ chạm**
(`r max` 1,21 < 2,0) nên bỏ trần ở tốc độ đó là no-op.

### 3. Comment `RADIUS_SIGMA` đang dẫn nguồn sai

`spray/plume_state.py:70-71`:

```
# Paper KHÔNG cho bán kính phụ thuộc tốc độ, và phép đo trên RoadSpray `*_static`
# (Δ=1,0 m) xác nhận: r50 = 0,288–0,349 m ở cả 9 tốc độ, **rsig median 0,720**.
```

`0,720` là **σ của phép đo RoadSpray**, không phải σ của paper. Dùng nó thay σ = 0,8 của paper
là trộn hai nguồn. Chính `docs/measurements/sspp-cluster-radius-by-speed.md` §3 mục 2 đã ghi:
σ đo được (1,67) **bị phồng bởi các chuỗi đã gộp**, không so được với số paper.

### 4. Viz dùng `all_alive`, production dùng `select_alive`

`scripts/visualize_plume_vs_real.py:183` truyền `state.all_alive()`; production
(`spray/plume_transform.py:132`) truyền `state.select_alive()`. Hệ quả đo được
(`.scratch/tmp/filters_by_speed.log`):

```
             clip (all_alive)   production (select_alive)
100 km/h     603 det            406 det   (max_range_m=50 cắt 17 % cụm)
130 km/h     550 det            239 det   (max_range_m=50 cắt 44 % cụm)
```

Clip đang tô hồng 130 km/h gấp rưỡi so với thực tế production.

---

## Việc phải làm

### Bước 1 — `spray/plume_state.py`: sửa hằng số + comment

1. `RADIUS_SIGMA`: `0.72` → **`0.8`**. Sửa comment thành:

```python
# [PAPER] Fig. 5 nguyên văn: "The parameters of the distribution are µ = −1.2 and
# σ = 0.8 as an example." ⇒ σ = 0,8. (Trước đây dùng 0,720 — đó là σ của phép đo
# RoadSpray `*_static`, KHÔNG phải σ của paper; xem
# docs/measurements/sspp-cluster-radius-by-speed.md §3 mục 2: σ đo bị phồng bởi
# các chuỗi đã gộp nên không so được với số paper.)
RADIUS_SIGMA = 0.8
```

2. `RADIUS_MAX_M`: `2.0` → **`inf`** (paper không đặt trần). Sửa comment thành:

```python
# [PAPER] Paper §III-B KHÔNG đặt trần cho r_cl — nguyên văn "The parameters of the
# distribution are µ = −1.2 and σ = 0.8 as an example", không có clip. Trần 2,0 m
# trước đây là [CHỌN] của repo, biện minh bằng "cắt ~0,1 % đuôi" — sai số học
# (với σ=0,72 thì P(r>2,0) = 0,48 %; với σ=0,8 là 1,1 %). Giữ hằng số = inf để
# một chỗ duy nhất điều khiển được (test/probe vẫn truyền số hữu hạn khi cần).
RADIUS_MAX_M = float("inf")
```

3. `RADIUS_MEDIAN_M`: `0.31` → **`0.3012`**, comment ghi `e^-1.2 = 0.3012 m` là số paper.
   Giữ `RADIUS_MU = -1.2` nguyên (log(0.3012) = −1.2 nên hai hằng số nhất quán).

4. Trong `PlumeState.spawn`, dòng `radius = min(cfg.radius_max_m, radius_draw)` phải chịu được
   `inf`: `min(inf, x) = x` nên **không cần sửa**, nhưng thêm comment một dòng:
   `# radius_max_m = inf (paper không có trần) ⇒ min() là no-op; caller có thể truyền số hữu hạn.`

5. Cập nhật docstring `PlumeStateConfig` (dòng ~125) ghi rõ `radius_max_m` mặc định `inf` =
   paper, và ai muốn clip thì truyền số.

### Bước 2 — `scripts/visualize_plume_vs_real.py`: dùng `select_alive`

Dòng 183: `state.all_alive(),` → `state.select_alive(),`.

Thêm ngay phía trên block `ray = raycast_frame(...)` một comment:

```python
# Dùng select_alive() như production (spray/plume_transform.py:132), KHÔNG dùng
# all_alive(): all_alive gồm cả cụm nằm ngoài miền mô hình (min_range 2,5 m /
# max_range 50 m), nên clip tô hồng phần detections mà training không bao giờ thấy.
# Đo được: 130 km/h 550 det (all_alive) vs 239 det (select_alive) — lệch 2,3×.
```

Đồng thời in thêm vào dòng log cuối mỗi frame (chỗ `print(f"  [{position+1}/...]")`) số cụm
bị lọc, để soi được:

```python
print(f"  [{position + 1}/{len(selected)}] real spray "
      f"{int(real_spray.sum()):5d} · sinh {synthetic.shape[0]:5d} điểm "
      f"· cụm {len(state.all_alive())} (giữ {len(state.select_alive())})",
      flush=True)
```

Lưu ý: `state.select_alive()` phải gọi **sau** `inject_plume_stateful` và **cùng frame**, không
cache qua vòng lặp (state đổi mỗi frame). Nếu gọi hai lần trong cùng frame thì kết quả giống
nhau nên không cần lo.

### Bước 3 — test

1. Chạy `pytest tests/ -x -q` — phải xanh toàn bộ. Nếu `tests/test_plume_lifetime.py:405-406`
   fail vì `pytest.approx(0.31, rel=0.20)` (median bán kính), sửa **giá trị kỳ vọng** thành
   0.3012 và giữ `rel=0.20`; ghi rõ trong commit là đổi theo paper.
2. Thêm **một** test mới vào `tests/test_plume.py` (file đã tồn tại):

```python
def test_radius_distribution_matches_paper():
    """[PAPER] Fig. 5: r_cl = exp(-1.2 + 0.8 Z), KHÔNG có trần."""
    from spray.plume_state import PlumeState, PlumeStateConfig, RADIUS_MAX_M
    import numpy as np

    assert RADIUS_MAX_M == float("inf"), "paper không đặt trần cho r_cl"
    cfg = PlumeStateConfig(radius_sigma=0.8)
    rng = np.random.default_rng(0)
    draws = np.exp(rng.normal(np.log(0.3012), cfg.radius_sigma, size=200_000))
    assert abs(np.median(draws) - 0.3012) < 0.01
    # p90 lý thuyết = exp(-1.2 + 1.2816*0.8) = 0.84 m
    assert abs(np.percentile(draws, 90) - 0.84) < 0.05
```

3. Chạy lại đúng lệnh đo để verify số khớp bảng ở Bối cảnh §2:

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    .scratch/tmp/radius_variants.py 2>&1 | grep -v "^PLUME"
```

Biến thể "A paper" và "B code hiện tại" phải **khác nhau** trước khi sửa; sau khi sửa, chạy lại
`transit_mechanism.py` + `filters_by_speed.py` và ghi số mới vào ticket.

### Bước 4 — Cập nhật tài liệu

`docs/measurements/a3-parameter-provenance.md`: thêm mục ghi 3 sai lệch đã sửa (σ 0,72→0,8;
bỏ trần 2,0 m; median 0,31→0,3012) kèm bảng đo ở Bối cảnh §2 và nhãn `[ĐO]`.

`docs/adr/0007-superseded-claims.md`: thêm một dòng vào bảng tra — cơ chế `RADIUS_MAX_M = 2,0 m`
đã bị bỏ, lý do: paper không có trần, và comment biện minh cũ tính sai p99.

---

## Ràng buộc

- **Không** đổi `RADIUS_MU` (−1.2) — nó đúng paper.
- **Không** đổi `P_det` (`PAPER_P_DET_MU/SIGMA` trong `spray/raycast.py`) — ngoài phạm vi.
- **Không** đổi công thức `T`, `C = −0,15`, hay số cụm/frame — ngoài phạm vi.
- **Không** sửa `scripts/measure_*.py` hay `.scratch/tmp/*.py` (đó là dụng cụ đo, phải giữ
  nguyên để so trước/sau).
- **Không** commit. PM sẽ đọc diff rồi commit.
- Không upgrade dependency, không đổi pin.

---

## Xong khi

1. `pytest tests/ -x -q` xanh, có test mới `test_radius_distribution_matches_paper`.
2. `git diff --stat` chỉ đụng: `spray/plume_state.py`, `scripts/visualize_plume_vs_real.py`,
   `tests/test_plume.py`, `docs/measurements/a3-parameter-provenance.md`,
   `docs/adr/0007-superseded-claims.md`.
3. Chạy `radius_variants.py` sau khi sửa và **dán bảng số mới** vào cuối ticket này dưới heading
   `## Kết quả sau sửa`, kèm nhận xét det mean 100 km/h đã lên ~484 chưa (bảng A).
4. Chạy `filters_by_speed.py` và ghi det cuối mới cho 100/130 km/h.

---

## Kết quả sau sửa — PM nghiệm thu 2026-11-27

### Test
```
pytest tests/ -x -q  →  201 passed in 25.16s
```

### Xác nhận hằng số trong code khớp paper
```
RADIUS_MU       = -1.2
RADIUS_SIGMA    = 0.8          (paper Fig. 5)
RADIUS_MAX_M    = inf          (paper không đặt trần)
RADIUS_MEDIAN_M = 0.3012       (e^-1.2)

400 000 mẫu: p50=0.3011  p90=0.840  p99=1.940  max=13.27
kỳ vọng paper: p50=0.3012  p90=0.840  p99=1.936        ← khớp
```

### `radius_variants.py` sau sửa
Code hiện tại giờ trùng nhánh A/D của chính phép đo (đó là điều cần chứng minh).

| 100 km/h | r p50 | r p90 | r p99 | r max | ở trần | det p50 | det mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| A paper (µ=−1,2 σ=0,8, không trần) | 0,30 | 1,00 | 2,08 | 3,14 | 0 % | 418 | 460 |
| **B code cũ** (0,31 σ=0,72 trần 2,0) | 0,30 | 0,89 | 1,71 | 2,00 | 0,5 % | 352 | 387 |
| C 0,31 σ=0,72 không trần | 0,30 | 0,89 | 1,71 | 2,49 | 0 % | 360 | 392 |
| D 0,31 σ=0,80 không trần | 0,30 | 1,00 | 2,08 | 3,14 | 0 % | 418 | 460 |

| 130 km/h | r p50 | r p90 | r p99 | r max | det p50 | det mean |
|---|---:|---:|---:|---:|---:|---:|
| A paper | 0,28 | 0,74 | 1,37 | 1,37 | 216 | 258 |
| **B code cũ** | 0,28 | 0,68 | 1,18 | 1,18 | 178 | 223 |
| C 0,31 σ=0,72 không trần | 0,28 | 0,68 | 1,18 | 1,18 | 178 | 223 |
| D 0,31 σ=0,80 không trần | 0,28 | 0,74 | 1,37 | 1,37 | 216 | 258 |

`[SUY LUẬN]` det mean 100 km/h: **387 → 460 (+19 %)**, cao hơn con số 484 ở brief §2 vì brief đo
trước khi `RADIUS_MEDIAN_M` đổi 0,31 → 0,3012 (median nhỏ hơn ⇒ điểm/cụm ít hơn một chút).
130 km/h: **223 → 258 (+16 %)**. Trần bán kính vẫn không chạm ở 130 km/h (`r max` 1,37 < 2,0).

### Sai sót trong brief (PM tự sửa)
Brief viết `P(r>2,0) = 0,48 %` với σ=0,72 và `1,1 %` với σ=0,8 — **sai**. Số đúng: **0,43 %** và
**0,90 %**. Comment cũ của repo ghi `e^{−1,2+2,326·0,72} = 1,61 m` là **đúng**, không phải sai
(brief §Bối cảnh 1 nói "1,65" là sai). Code và 2 doc đã sửa theo số đúng.

### `filters_by_speed.py` sau sửa (production default, `select_alive()`)

```
 km/h  T(s)    ego  đi/life |  cụm all  sau min2.5  sau max50  giữ lại | det không lọc  det ≤100m  det cuối
   60  0.40   16.7      6.7 |     14.8        14.8       14.8     14.8 |           107        107       105
  100  1.20   27.8     33.3 |     38.1        35.3       31.5     31.5 |           634        634       460
  130  1.80   36.1     65.0 |     42.3        40.5       23.5     23.5 |           588        587       258

Tỉ lệ mất so với không lọc:
   60 km/h: max_range 50 m cắt 0% cụm · max_distance 100 m cắt 0% det · cuối còn 98%
  100 km/h: max_range 50 m cắt 17% cụm · max_distance 100 m cắt 0% det · cuối còn 73%
  130 km/h: max_range 50 m cắt 44% cụm · max_distance 100 m cắt 0% det · cuối còn 44%
```

**det cuối (production):** 100 km/h **406 → 460**, 130 km/h **239 → 258**, 60 km/h **96 → 105**.

`[SUY LUẬN]` Cơ chế cắt **không đổi**: `max_range 50 m` vẫn cắt 17 % / 44 % cụm ở 100 / 130 km/h,
`max_distance 100 m` vẫn cắt 0 % det. Cái tăng là **số det phát ra trước khi lọc** (603→634 @100,
550→588 @130) vì đuôi bán kính nặng hơn (σ 0,72→0,8) ⇒ cụm to hơn ⇒ nhiều tia×cầu trúng hơn.
Tỉ lệ "cuối còn" tăng nhẹ (67→73 % @100, 43→44 % @130) vì cụm to hơn sống sót qua `select_alive()`
tốt hơn.

### `transit_mechanism.py` (chạy kèm để đối chiếu — không thuộc "Xong khi")

```
 km/h   T(s)  spawn_x  ego m/s  đi/life  t_vượt nhìn thấy  cụm x<0  r-ρ<2,5
   60   0.40     18.1     16.7      6.7    1.09        0%       1%       0%
  100   1.20     19.6     27.8     33.3    0.71       41%      46%       7%
  130   1.80     20.8     36.1     65.0    0.58       68%      73%       4%
```

Sửa bán kính **không** chạm nguyên nhân 130 km/h tệ hơn 100 km/h: 130 km/h vẫn mất 68 % đời cụm.

### Ghi chú kỹ thuật: vì sao probe A cho 460 chứ không phải 484

`.scratch/tmp/radius_variants.py` (bất biến theo ràng buộc) truyền median qua
`PlumeStateConfig(radius_mu=...)`, nhưng `spawn()` **bỏ qua** `cfg.radius_mu` và đọc module
constant `cluster_radius_median_for_speed()` → `RADIUS_MEDIAN_M`. Nên khi `RADIUS_MEDIAN_M` đổi
0,31 → 0,3012, biến thể "A paper" trong probe cũng đổi median theo. Đo cách ly (script trong
scratchpad, không đụng `.scratch/tmp`):

```
median=0.31    r_p50=0.311 det_p50=436 det_mean=484   ← tái lập đúng bảng Bối cảnh §2
median=0.3012  r_p50=0.302 det_p50=418 det_mean=460   ← số sau sửa
```

Tức bảng §2 đo trên median 0,31, còn code sau sửa dùng 0,3012 (số paper). Sau sửa, cấu hình
production ≡ biến thể "A paper" (det 460 = 460), đúng điều cần chứng minh. `tests/test_plume_lifetime.py:405-406`
**không** phải sửa: `pytest.approx(0.31, rel=0.20)` vẫn bao 0,3012 (lệch 2,9 % < 20 %).

### `filters_by_speed.py` sau sửa
```
 km/h  T(s)    ego  đi/life |  cụm all  sau min2.5  sau max50  giữ lại | det không lọc  det ≤100m  det cuối
   60  0.40   16.7      6.7 |     14.8        14.8       14.8     14.8 |           107        107       105
  100  1.20   27.8     33.3 |     38.1        35.3       31.5     31.5 |           634        634       460
  130  1.80   36.1     65.0 |     42.3        40.5       23.5     23.5 |           588        587       258
```
det cuối: 105 / 460 / 258 (trước sửa: 96 / 406 / 239). `max_range_m = 50` vẫn cắt 44 % cụm ở
130 km/h — **ngoài phạm vi ticket này**, để ticket riêng về số cụm (xem ghi chú dưới).

### Ghi chú mở — chưa xử lý trong ticket này
Đo bằng đúng toán tử bảng RoadSpray static (cắt lát Δ=1,0 m, DBSCAN góc 0,7°/minPts 3, hộp sau
đuôi box 20×3,4×1,5 m) trên SSPP `*_dynamic`, `.scratch/tmp/object_region_v2.json`:

| km/h | bảng code | THẬT cụm/f | SINH cụm/f | SINH/THẬT | THẬT điểm/f | SINH điểm/f |
|---:|---:|---:|---:|---:|---:|---:|
| 60 | 14,40 | 6,7 | 4,8 | 0,71 | 58 | 77 |
| 100 | 35,86 | 24,0 | 16,0 | 0,66 | 396 | 258 |
| 130 | 33,08 | 20,2 | 6,7 | 0,33 | 358 | 109 |

Generator thiếu cụm trong chính vùng nó sinh; điểm/cụm gần đúng (17,7 thật vs 16,3 sinh @130).
Nguyên nhân chính ở 130 km/h là `max_range_m = 50` cắt 44 % cụm. Cần ticket riêng.
