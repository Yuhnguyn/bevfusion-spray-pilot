# Kế hoạch: đưa generator về đúng những gì Paper A đã kiểm chứng

Nhánh `sspp` · 2026-11-19 · nguồn chuẩn: **Paper A = Linnhoff et al. 2022, arXiv 2212.08558**
(`/Users/huynguyen/.hermes/cache/scratch/spray-diag/paperA.pdf`, đọc bằng `pdftotext -layout`).
Dữ liệu: `data/SemanticSprayDataset` (SSPP). Mọi số dưới đây là `[ĐO]` trên máy này, trừ khi ghi nguồn.

Nhãn nguồn: `[PAPER]` paper nói · `[ĐO]` đo trên dữ liệu · `[CODE]` port từ reference impl ·
`[CHỌN]` repo tự chọn, không có nguồn ngoài.

---

## 0. Problem (đọc trước, đừng đọc solution trước)

Generator hiện tại **không** mô phỏng cái paper đã kiểm chứng. Nó mô phỏng một biến thể của
mô hình paper, áp vào một kịch bản mà paper **chưa từng** kiểm chứng, với ba tham số tự thêm
để biến thể đó "chạy được" ở kịch bản mới. Kết quả: plume đậm 1,6–26× spray thật và nằm lệch
chỗ, dẫn tới recall cổng C −0,268 (so với spray thật tự gây −0,049).

Đại lượng cần làm đúng, theo thứ tự ưu tiên:

1. **Phân bố cự ly của detection** `R_det` — phải khớp spray thật, không phải chỉ khớp tổng số.
2. **Tổng detection/frame** trong miền paper đã kiểm chứng (`R ≥ 25 m`, `R ≤ 50 m`).
3. **Không có gì ở sau mặt phẳng cảm biến** — paper không có hiện tượng này.

Cái **không** cần làm: khớp từng ô của bảng `cal` trên following. Bảng đó đo static; dùng nó
làm đích cho following là lỗi miền (xem §2.4).

---

## 1. Paper đã kiểm chứng cái gì, và ở đâu

| Đại lượng | Paper nói | Nơi đo | Kiểm chứng ở |
|---|---|---|---|
| `C = −0,15 m⁻¹` | Eq. 5; *"depends on the step size Δt and has to be re-calibrated for sensors with different scanning frequencies. The here applied step size ... is Δt = 100 ms"* | **25 m, ego ĐỖ**, xe chạy qua | Fig. 12 |
| `r_cl` | lognormal µ = −1,2 σ = 0,8; *"the radii are set to the maximum distance of detections to the respective cluster center"* — **một** phân bố, không nở theo tuổi | Fig. 5 | Fig. 12 |
| `P_det` | lognormal µ = −2,3 σ = 1,09 (Fig. 7 ghi σ = 1,09; code dùng 1,1) | **chỉ ở 25 m** | Fig. 11 |
| `P_t = e^{−t/T}` | Eq. 1 | Fig. 6 | Fig. 11 |
| Số cụm | Fig. 4, hàm của `v`, `class`, `wfh`; *"divided by the length ratio of the spray region to the distance the object traveled during one scan"* | static, 25 m | Fig. 11a |
| Đặt cụm | *"uniform distribution in the region behind every moving object"* | — | Fig. 10 |
| Attenuation | *"mean extinction coefficient of 0.02 m⁻¹"* | Fig. 8 | — |
| Miền đánh giá | *"the entire evaluation range from 0-50 m"* | — | Fig. 11, 12 |

Ba câu paper tự cảnh báo, đều đúng chỗ repo vỡ:

- §V: *"with higher resolutions, a problem with the spherical cluster representation might
  appear. The problem can become especially pronounced in close proximity to the sensor and is
  to be evaluated in future work."* ← repo rơi đúng vào đây.
- §V: *"occlusion by objects that do not generate detections themselves ... is not covered. At
  the moment, the presented spray simulation would generate detections behind those objects."*
  ← nên cơ chế "plume che xe" **không phải** của mô hình paper.
- §II-A: ego đỗ trong toàn bộ hiệu chuẩn; *"An object distance of 25 m from the sensor is
  chosen, since here distinct and stable clusters are observed with high resolution"*.

---

## 2. Sáu chỗ repo lệch paper, xếp theo mức gây hại đo được

Bảng dưới là ablation trên 4 scene Crafter (2 có human box, 2 pseudo box), cùng seed, cùng
frame, cùng toán tử `raycast_frame`. Đơn vị: detection/frame; "thật" = `label == 2`/frame.

| # | Chỗ lệch | Nguồn | Bằng chứng đo | Mức |
|---|---|---|---|---|
| 2.1 | **Tán xạ `r(t) = r₀ + 0,06·d_rel`, trần 4,0 m** | `[CHỌN]` — paper không có luật nở; Fig. 5 là đại lượng **đo** | tắt α: r p50 1,35 → 0,33 m; det 3.290 → 497 | **6,6×** |
| 2.2 | **Áp `C` ngoài miền 25 m** (ego chạy xuyên plume) | `[PAPER]` số đúng, **miền sai** | tắt drag: R min 0,66 → 15,9 m; det 3.290 → 126 | **26×** |
| 2.3 | **Cụm trôi qua cảm biến rồi ra sau lưng** | không có trong paper (ego đỗ) | 41–65 % cluster-instance ở `x < 0`; 68–97 cụm/cảnh **cắt** mặt phẳng x=0; x tới **−137 / −294 m** | chặn |
| 2.4 | **Bảng `cal` đo RoadSpray `*_static` dùng làm đích cho following** | `[ĐO]` trên static, dùng ở following | 207/207 scene SSPP có `|ego−object| = 0,00 km/h`; static có `/adma/twist` = 0,005 km/h | miền |
| 2.5 | **Cụm vật chất ở `ring = −1` không bao giờ bị lọc** | `[CODE]` | `_POINTS_MEDIAN_BY_RANGE` cho median 10–30 điểm/cụm, `_injected_budget` cap 5 % — nhưng raycast không dùng chúng | vô hại |
| 2.6 | **`wet_ground` bị vứt** | `[CODE]` | `plume_transform.py:130` raycast `points_clean`; đo: `points_clean` identical khi bật wet_ground | vô hại cho số, **sai method** |

### 2.3 — chuyện "cụm xuyên qua ego" bạn thấy: **đúng, và nặng hơn bạn nghĩ**

Ba phép đo riêng:

```
Crafter 0060 (box, 53 frame): 1837 cluster-instance
  x < 0 (sau cảm biến):           758  (41,3 %)  ở 53/53 frame
  cụm CẮT mặt phẳng x=0:           68
  x p01/p05/p50/p95 = -137,0 / -67,1 / 4,7 / 18,9 m
Crafter 0097 (pseudo box, 78 frame): 2801 cluster-instance
  x < 0:                         1824  (65,1 %)  ở 78/78 frame
  cụm CẮT mặt phẳng x=0:           97
  x p01/p05/p50/p95 = -293,8 / -166,9 / -14,6 / 18,5 m
```

Cơ chế: ở kịch bản following, `v_rel` lúc sinh ≈ 0 (ego và xe cùng tốc độ), drag `C·|v_air|²`
làm cụm mất vận tốc trong ~0,2–0,5 s, sau đó `pos += (vel − ego_velocity)·dt` với
`ego_velocity ≈ 28 m/s` đẩy cụm **lùi với 28 m/s** trong hệ ego. Với `T = 1,2 s` @100 km/h,
cụm đi được **~34 m về phía sau** — quá cả cảm biến. Ở kịch bản static của paper, ego đỗ nên
`ego_velocity = 0` và hiện tượng này **không thể xảy ra**.

Vì vậy đây không phải bug nhỏ: đó là **hệ quả trực tiếp của việc áp mô hình paper ra ngoài
miền hiệu chuẩn**, và nó giải thích luôn phần near-field.

### 2.2 + 2.3 là **cùng một** nguyên nhân, không phải hai

Tắt drag ⇒ R min 15,9 m và không còn cụm nào ở `x < 0`. Hai cách chữa dưới đây tương đương về
mặt "làm đúng paper", khác nhau ở chỗ có bỏ được drag hay không.

---

## 3. Ba lựa chọn, và mặc định

### Cách A — Cắt theo miền hiệu chuẩn (khuyến nghị, rẻ nhất)

Giữ nguyên toàn bộ số của paper (`C`, `r_cl`, `P_det`, `T`), chỉ **không cho mô hình phát ngôn
ngoài miền đã kiểm chứng**:

- bỏ cụm có `x < 0` (sau mặt phẳng cảm biến);
- bỏ cụm có `‖pos‖ < 3 m` (paper §V: mô hình cầu vỡ ở gần);
- bỏ cụm có `‖pos‖ > 50 m` (miền đánh giá của paper);
- `diffusion_alpha = 0`.

Đo được (`measure_faithful.py`, 40 frame/scene, cùng seed):

| scene | thật/frame | production | paper-faithful | R p05/p50 thật | R p05/p50 faithful | `< 3 m` |
|---|---:|---:|---:|---|---|---:|
| 0060 @100 | 1660 | 2685 (1,62×) | **214 (0,13×)** | 3,72 / 8,75 m | 4,78 / 10,36 m | **0** |
| 0096 @130 | 368 | 3138 (8,54×) | **188 (0,51×)** | 3,72 / 5,40 m | 5,48 / 9,47 m | **0** |
| 0097 @130 | 180 | 3063 (16,97×) | **186 (1,03×)** | 3,73 / 6,97 m | 5,27 / 8,60 m | **0** |

Production có R p05 = 1,42–1,58 m và 946–1272 det ở `< 3 m`; faithful có **0**.

**Đánh đổi phải khai:** faithful **thưa hơn thật ở 0060** (0,13×). Đây không phải lỗi mới —
0036 nói `trail90` của static là 44 m còn following thật chỉ ~20 m, tức **hai kịch bản có tổng
lượng spray khác nhau thật**, và mô hình hiệu chuẩn trên static không tái tạo được lượng của
following. Đó là limitation của **dữ liệu hiệu chuẩn**, không phải của cách sửa.

### Cách B — Bỏ drag (bám đúng chữ của paper)

`C = 0` ⇒ R min 15,9 m, không cụm nào ở `x < 0`, det/frame 0,07–0,50× thật. Rẻ, nhưng **mất một
cơ chế paper có** (Eq. 5). Chỉ nên chọn nếu Cách A cho kết quả cổng C tệ.

### Cách C — Giữ nguyên production, chỉ sửa `wet_ground`

Không khuyến nghị: `wet_ground` bị vứt nên sửa nó không đổi được detection nào; near-field vẫn
còn. Đây là cách duy nhất **không** làm giảm recall.

**Mặc định: Cách A.** Lý do: giữ được mọi số paper (không phải "sửa paper"), chỉ khai một
giả định duy nhất là *"mô hình chỉ có giá trị trong miền đã hiệu chuẩn"* — và giả định đó chính
paper nói ra (§II-A, §V).

---

## 4. Kế hoạch thi công, từng bước một

Mỗi bước có **artifact** và **điều kiện đạt**; không bước nào được "ước lượng là xong".

### Bước G0 — Chốt miền vào ADR **trước khi** đo (bắt buộc)

Viết §5.7 mới vào `docs/adr/0006-detection-protocol-and-calibration-source.md`:

- miền hợp lệ: `0 ≤ x`, `‖pos‖ ≥ 3 m`, `‖pos‖ ≤ 50 m`, `diffusion_alpha = 0`;
- mọi ngưỡng ghi **trước** khi chạy cổng C;
- tiêu chí cổng C mới: `Δrecall(plume − clean)` phải nằm trong `Δrecall(real − clean) ± 0,05`
  (vì `real − clean = −0,049 [+; −0,019]` là mức spray thật tự gây);
- **cấm** thêm hệ số thứ tư để khớp số.

**Đạt:** commit có §5.7, `git log -1` là commit đó, **trước** bất kỳ lần chạy số nào.

### Bước G1 — Wire 4 ngưỡng vào `spray/`, opt-out được, bit-for-bit khi tắt

Sửa `spray/plume_state.py` (`PlumeStateConfig`) + `spray/plume.py` (`inject_plume_stateful`):

```
PlumeStateConfig:
    min_range_m: float = 0.0        # 0 = tắt (hành vi cũ)
    max_range_m: float = 1e9
    drop_behind_sensor: bool = False
PlumeStateConfig.diffusion_alpha   giữ nguyên default 0.06 (không đổi default!
                                   production cũ phải tái lập được)
```

Lọc ở **một chỗ duy nhất**: ngay trước khi materialise/vẽ, trong `inject_plume_stateful`,
sau `state.advance()`/`prune()`. Không lọc trong `raycast` (raycast phải giữ thuần).

**Đạt:** `pytest -q tests/` vẫn **213 passed**; thêm 3 test mới:
`test_plume_min_range_filters`, `test_plume_drop_behind_sensor`,
`test_paper_faithful_bitforbit_when_off` (so md5 của output giữa config mới-all-off và
commit trước). Baseline mới 216 passed.

### Bước G2 — Đo lại A3-V trên tập B (72 scene không box)

`scripts/measure_following_scenario.py --sets B --frames-per-scene 30` với config Cách A
(`PLUME_PAPER_FAITHFUL=1` hoặc cờ CLI, không đổi default).

**Đạt:** báo **median + CI95 bootstrap theo scene** cho 6 ô; kèm `R_det` p05/p50/p95 mỗi ô và
số det ở `< 3 m` (phải = 0). Không đạt/đạt ghi theo ngưỡng `[0,5; 2,0]` đã pre-register ở ADR,
**kèm** cột `R p50` vì đây là thứ thực sự quyết định.

### Bước G3 — Cổng C, đúng pre-register §5.7

Kernel mới (copy `kaggle/gate_c`), 3 nhánh paired clean/plume/real, **954 frame**, τ = 0,20.
Phải dùng **cùng** `sspp-gate-c-data`, chỉ đổi code version.

**Đạt:** bảng `ΔFP`, `Δrecall` + CI95 theo scene; quyết định theo §5.7 đã ghi trước.
Dự đoán phải ghi trước: `Δrecall(plume−clean)` sẽ **dịch từ −0,268 về khoảng −0,05**; nếu vẫn
< −0,15 thì kết luận "miền không phải nguyên nhân duy nhất" và dừng, **không** thêm núm.

### Bước G4 — Chỉ sau khi G3 đạt: mới bàn tới train

Không mở trước. Nếu G3 trượt, sản phẩm cuối là **kết luận âm tính có số**: "mô hình paper không
tái tạo được spray của bộ dữ liệu ego-bám-đuôi; nguyên nhân là miền hiệu chuẩn (ego đỗ, 25 m),
không phải tham số."

---

## 5. Visualize — thứ để kiểm bằng mắt (đã dựng và đã chạy)

### 5.1 Công cụ đã có, không cần viết mới

`scripts/visualize_plume_vs_real.py` — 2 panel REAL | GENERATOR, BEV, mp4. Đã chạy:
`.scratch/diag/viz_before_fix_100kmh.mp4` (50 frame, 0060 @100 km/h, trước khi sửa).

### 5.2 Bản 3 panel + nhìn ngang (đã dựng, để trong scratch)

`~/.hermes/cache/scratch/spray-diag/viz_three_way.py` → 2 hàng × 3 cột:

| | REAL | PRODUCTION | PAPER-FAITHFUL |
|---|---|---|---|
| hàng trên | BEV `x–y`, ±60 m dọc | như trái | như trái |
| hàng dưới | nhìn ngang `x–z` | như trái | như trái |

Hàng dưới là thứ **bắt được** chuyện cụm ở sau cảm biến và chuyện cụm dưới mặt đường — BEV
không thấy. Đường chấm đỏ dọc = mặt phẳng cảm biến `x = 0`.

Đã chạy: `.scratch/diag/viz_3way_100kmh.mp4` + `.scratch/diag/viz_3way_contactsheet.png`
(4 frame × 3 cột). Số trên clip: real 371–2185, production 2063–4933, faithful 157–307.

### 5.3 Yêu cầu kỹ thuật của visualize (để so bằng mắt có nghĩa)

1. **Ba bản dùng cùng giới hạn trục + cùng thang màu** — không thì so vô nghĩa.
2. **Bản sinh phải chạy tuần tự từ frame 0** tới frame cần vẽ (state qua frame); vẽ frame k
   riêng lẻ cho plume rỗng.
3. **Chọn frame bằng `argmax` số điểm spray thật**, không lấy frame 0 (frame đầu thường thưa).
4. **Luôn có hàng nhìn ngang** — đây là chỗ lộ `x < 0`, `z < road`, `R < 3 m`.
5. **Panel số thô** (đếm det, R p05/p50, số cụm sống) in ngay dưới mỗi cột, để mắt và số không
   rời nhau.
6. Xuất **mp4**, không chỉ PNG: user đã nói rõ muốn xem dạng quét nhiều frame.

### 5.4 Bộ clip cần có để nghiệm thu (làm ở Bước G2)

| clip | scene | mục đích |
|---|---|---|
| `viz_3way_100kmh.mp4` | 0060 | 100 km/h, có human box, nước đầy (`itr=1`) — ca khó nhất |
| `viz_3way_130kmh.mp4` | 0096 | 130 km/h, ca production tệ nhất (16,97×) |
| `viz_3way_golf_100kmh.mp4` | Golf @100 | kiểm `vehicle_class` (production đang hard-code `"crafter"` cho cả Golf) |
| `viz_3way_static.mp4` | RoadSpray `Crafter_static` | kịch bản **đúng miền paper** — nếu faithful không khớp ở đây thì cả kế hoạch sai |

Clip thứ tư là clip quan trọng nhất và hiện **chưa có**: nó là phép kiểm duy nhất mà paper
thật sự đã làm. Nếu faithful khớp static mà lệch following ⇒ kết luận là "miền", đúng như dự
đoán. Nếu faithful cũng lệch static ⇒ có lỗi port, phải tìm trước khi làm bất cứ gì khác.

---

## 6. Bốn lỗi khác đã đo được, sửa cùng đợt hoặc ghi rõ là bỏ qua

| # | Lỗi | Bằng chứng | Xử lý |
|---|---|---|---|
| 6.1 | `vehicle_class="crafter"` cho **mọi** scene, kể cả Golf | `plume_transform.py:118` không truyền `vehicle_class`; runbook §6.3 đã ghi | truyền từ `metadata.txt`/`group`; ảnh hưởng bảng cụm + `r_cl` |
| 6.2 | `z_shift`: cụm ở `z − road_z` p05 = +0,04…+0,09 m nhưng **2,2–3,3 % ở dưới mặt đường** | đo 1558+1495 cluster-instance | bỏ qua được (dưới 0,3 m chỉ 0,0–0,1 %) — **ghi là bỏ qua**, đừng thêm clamp |
| 6.3 | Cụm sống tới `age/TTL` p95 = **2,5–3,4** (Eq. 1 cho `P = e^{−3,4} = 3 %`) | đo cùng trên | không phải lỗi: `prune` thinning xác suất đúng Eq. 1; đuôi dài là hệ quả toán học, không phải bug |
| 6.4 | `wet_ground` bị vứt khỏi đường production | `plume_transform.py:130` | hoặc nối `base` vào raycast (đổi số), hoặc ghi rõ "wet-ground không tham gia" — **không** để lửng lơ |

---

## 7. Cấm — những việc sẽ làm hỏng kế hoạch

1. **Không** thêm hệ số thứ tư (không `pdet_range_exponent`, không `spawn_scale`, không
   `density_scale`). D2-v2 đã FAIL 4/6 ô vì đúng lý do này.
2. **Không** đổi ngưỡng sau khi thấy số. §5.7 phải commit trước.
3. **Không** "sửa cho khớp" bằng cách tăng số cụm — nếu faithful thưa hơn thật, ghi limitation
   (§3 Cách A), không bù bằng `spawn_scale`.
4. **Không** dùng SSPP để chọn tham số. SSPP chỉ kiểm chứng; hiệu chuẩn chỉ từ RoadSpray static.
5. **Không** đổi default của `PlumeStateConfig` — production cũ phải tái lập bit-for-bit.

---

## 8. Thứ tự làm, và cái gì chặn cái gì

```
G0 (ADR §5.7)  ──chặn──► G1 (wire)  ──chặn──► G2 (A3-V + 4 clip)  ──chặn──► G3 (cổng C)  ──► G4 (train)
                                                    │
                                            clip static sinh ra ở đây
                                            (phép kiểm duy nhất paper đã làm)
```

Ước lượng: G0 30 phút · G1 ~2 h + 216 test · G2 ~12 phút local + render clip · G3 ~22 phút
kernel + bootstrap. Tổng dưới một ngày, không cần GPU cho G0–G2.

---

## 9. Câu cần user chốt trước khi tôi dispatch G1

1. **Cách A hay B?** (mặc định A: giữ mọi số paper, cắt miền).
2. **G3 trượt thì dừng hẳn, hay cho phép thử Cách B?** (mặc định: dừng, viết kết luận âm tính).
3. **Clip static (RoadSpray `Crafter_static`) có làm không?** — cần stream 1 bag từ zip 7,9 GB
   (đã có sẵn), ~10 phút. Mặc định: **có**, vì đó là phép kiểm duy nhất paper thực sự đã làm.
