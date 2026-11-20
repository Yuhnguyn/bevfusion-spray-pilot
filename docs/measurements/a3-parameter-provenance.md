# A3 — Kiểm nguồn gốc tham số generator plume (R2, 2026-11-19)

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S1, S2, S3, S4, S5.
> Phần còn đúng: Audit 49 tham số vẫn đúng về nguồn gốc; các tham số đã bị bỏ thì không còn trong code.

Người rà: `paper-archaeologist` (R2). Thời điểm audit: **2026-11-19 12:27 +07**, commit **`bacff42`**,
tracked working tree **sạch** (R1 có thể đổi sau mốc này — mọi số dòng tính theo đúng commit trên).
Nhiệm vụ: mỗi tham số số học của generator phải có nguồn thật; tìm chỗ còn rò rỉ SSPP, chỗ bịa,
và chỗ docstring **nói** một nguồn nhưng giá trị **không** khớp.

Nhãn: `HỢP LỆ` · `CẦN ĐO LẠI` · `PHẢI BỎ`.
Nguồn paper: arXiv 2212.08558v1, bản text local `~/.hermes/cache/scratch/spray2212.txt` (số dòng `L…`
là dòng trong bản đó — **trích lại từ file local**, không bịa vị trí).
Nguồn đo static: `.scratch/roadspray-cal/tmp/a3_targets_static.json` (Δ = 1,0 / 2,5 / 6,0 m) và
`docs/measurements/roadspray-static-clusters-by-speed.md`.

**Đường sống (quan trọng để đọc bảng):** `PlumeTransform` → `inject_plume_stateful` →
`state.all_alive()` → `raycast_frame` → `detections` (`plume_transform.py:118-142`). Hàm transform
**bỏ** `result.points`/`result.injected`; chỉ dùng `points_clean` + cụm sống cho raycast. Vì vậy
một số tham số "trông như tham số plume" **không thể** ảnh hưởng det/frame — tách ở §3.

---

## 1. Bảng A — tham số ẢNH HƯỞNG đường đo A3 (stateful + raycast)

| Tham số | File:dòng | Giá trị hiện tại | Nguồn | Nhãn |
|---|---|---|---|---|
| `_CLUSTER_VISIBLE_BY_SPEED` | `plume.py:36-59` | Crafter 5,98…22,24; Golf 4,73…25,18 (cụm/frame) | RoadSpray **static** DBSCAN 0,7°/minPts 3 — `roadspray-static-clusters-by-speed.md` §4, ADR-0006 D2. **Nhưng đo với lát Δ=2,5 m** | **CẦN ĐO LẠI**: nếu Δ=1,0 là chuẩn (charter §1.3) thì đích là 9,0 / 35,9 / 33,1 (`a3_targets_static["50_1.0"].cpf`…); bảng hiện tại under-spawn 0,67–0,39× ở 100/130 |
| `WFH_REF_MM` | `plume.py:65` | 1,0 mm | paper §III-B `L556-557`: “0.5 mm, 0.75 mm and 1.0 mm for moist, partially covered, and fully covered”; chọn 1,0 làm mức chuẩn = `[CHỌN]` | HỢP LỆ |
| `_UPDATE_CYCLE_TIME_S` | `plume.py:70` | 0,1 s | paper `L643-644`: “∆t = 100 ms”; VLP-32 profile `update_cycle_time` | HỢP LỆ |
| `ACTIVATION_SPEED_KMH` | `plume_state.py:67` | 40,0 km/h | `[CODE]` `DetectionEnvironmentalEffects.cpp:502,554`; paper nói spray xuất hiện từ 50 km/h (`L298-299`) nhưng bảng visible trả 0 dưới 50 nên ngưỡng 40 không tạo cụm | HỢP LỆ |
| `cluster_count_velocity_offset_kmh` | `plume.py:117` | 50,0 km/h | `[CODE]` profile `num_clusters_velocity_offset_kmh`; campaign paper 50–130 km/h (`L298-303`) | HỢP LỆ |
| `lifetime_water_film_coeff` / `lifetime_base_s` | `plume.py:119-120` | 0,02 / 0,2 s | `[CODE]` `dee.cpp:530`; paper chỉ định nghĩa `T` qua Fig. 6 (`L548-552`), **không** cho công thức | HỢP LỆ `[CODE]` |
| `lifetime_max_age_factor` | `plume.py:122`; `plume_state.py:73` | 4,0 | `[CODE]` `dee.cpp:446`; paper Eq. 1 mô tả tan xác suất, cắt cứng 4T là `[CODE]` | HỢP LỆ `[CODE]` |
| `LIFETIME_SIGMA_S` | `plume_state.py:71` | 0,2 s | `[CODE]` profile `std_time_constant = 0.2` (`openmsl-sl-1-2-deep-dive.md:345`) | HỢP LỆ |
| `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` | `plume_state.py:90-100` | 0,70 / 0,60 / 0,60 / 0,45 / 0,53 / 0,48 / 0,49 / 0,56 / 0,66 m | RoadSpray static `r50` nhưng **cột Δ=2,5 m** (khớp `a3_targets_static["50_2.5"].r50=0,702`, `100_2.5=0,478`, `130_2.5=0,657`) | **CẦN ĐO LẠI**: cột Δ=1,0 là 0,349 / 0,292 / 0,311 (charter §1.3 đã ký Δ=1,0 là chuẩn) |
| `RADIUS_SIGMA` | `plume_state.py:81` | 0,97 | static `rsig` Δ=2,5 @100 km/h (`a3_targets_static["100_2.5"].rsig = 0,970`); Δ=1,0 cho 0,754 / 0,727 / 0,714 | **CẦN ĐO LẠI** — và comment ngay trên ghi “paper 0,8”: xem §4.1 |
| `RADIUS_MAX_M` | `plume_state.py:82` | 1,0 m | `[CODE]` `dee.cpp:528` `std::min(1.0f,…)`; paper không clip | HỢP LỆ `[CODE]` (khác paper: paper không có trần) |
| `LATERAL_CLAMP_M` | `plume_state.py:112` | 2,43 m | `[ĐO]` p95(\|y−y_block\|) trên **`cal` labels = SSPP** (`plume_state.py:108-111`) | **CẦN ĐO LẠI — vi phạm D2** |
| `RADIUS_MU` | `plume_state.py:80` | −1,2 | paper Fig. 5 `L524-525` | HỢP LỆ `[PAPER]` nhưng **dead**: `spawn()` dùng median table, không dùng `mu` |
| `INITIAL_VZ_MAX_MPS` | `plume_state.py:119` | 0,0 m/s | `[SUY LUẬN]` từ paper §III-C: v0 = vận tốc vật thể, không có phương trình z; giữ 0 = không thêm cơ chế | HỢP LỆ |
| `DRAG_MEAN` / `DRAG_STD` | `plume_state.py:122-123` | −0,15 m⁻¹ / 0,0 | paper `L640`: “C = −0.15 m−1 … constant”; `[CODE]` dùng N(−0,12;0,04) nhưng code cố ý theo paper | HỢP LỆ |
| `WIND_SPEED_MPS` / `WIND_FROM_DEG` | `plume_state.py:125-126` | 2,0 m/s / 208° | `[CODE]` `dee.cpp` (`deep-dive.md:372-373`); paper chỉ nói gió được đo & giả định chung, **không cho số** | HỢP LỆ `[CODE]` |
| `DEFAULT_DT_S` | `plume_state.py:128` | 0,1 s | `[CODE]` profile, trùng paper `L643-644` | HỢP LỆ |
| `spawn_scale` | `plume_state.py:176` (dùng `:423`) | 1,0 | `[CHỌN]` knob không có trong paper; comment dẫn chứng 3,0 từ det/frame **SSPP** | **CẦN ĐO LẠI**: phải khai `[CHỌN]`; nếu đặt ≠1 thì là hiệu chỉnh trên SSPP (D2) |
| `streak_scale` | `plume_state.py:189` (dùng `:539-542`; raycast `:451-463`) | 0,5 | **không có trong paper** — cơ chế tự thêm để nối đám thành băng (charter §1.3b) | **PHẢI BỎ** — default đang BẬT; charter yêu cầu thử 0,0 trước khi sửa `spawn_scale` |
| `source_count` / `source_lateral_m` / `source_sigma_m` / `source_height_m` | `plume_state.py:183,184,185,194` | 0 / (−0,85;0,85) / 0,18 / (0,05;0,90) | **không có trong paper**; hai bánh sau là tự thêm; paper: “spheres are positioned with a uniform distribution in the region behind every moving object” (`L393-395`) | **PHẢI BỎ** (đã tắt mặc định nhưng còn code bật được) |
| `placement_knots` / `placement_knot_sigma_m` | `plume_state.py:162-163` | 0 / 0,25 m | `[CHỌN]` overdispersion, không paper; lý do dẫn “plume thật có 1–2 chuỗi ~1000 điểm” (đo SSPP) | **PHẢI BỎ** (default tắt) |
| `tail_block_width_m` | `plume.py:164` | 3,4 m | `[CODE]` `define_spray_volumes()` hard-code `width = 3.4` (`deep-dive.md:294`); paper NOT STATED | HỢP LỆ `[CODE]` |
| `tail_block_height_frac` | `plume.py:165` (dùng `:568-584`) | (0,05; 0,92) | `[ĐO]` trên **939.803 điểm nhãn SSPP** + `[CHỌN]` (`paper-qa-notebooklm.md` §7/§8.4); paper NOT STATED | **CẦN ĐO LẠI — vi phạm D2** |
| `PAPER_P_DET_MU` / `PAPER_P_DET_SIGMA` | `raycast.py:51-52` | −2,3 / 1,1 | paper Fig. 7 `L678`: “µ = −2.3 and σ = 1.09” | HỢP LỆ (làm tròn 1,09 → 1,1; muốn khít thì sửa 1,09) |
| `mean_attenuation_per_m` | `raycast.py:66` | 0,02 m⁻¹ | paper `L740`: “mean extinction coefficient of 0.02 m−1”; dạng `exp(−2μL)` với hệ số 2 là `[CODE]` `dee.cpp:279` (paper không cho công thức) | HỢP LỆ (khai rõ factor 2 `[CODE]`) |
| `intensity_mu` / `intensity_sigma` | `raycast.py:69-70` | 0,5 / 0,05 | paper `L728-730`; chỉ dùng làm ranking score, intensity phát ra = 0 (`raycast.py:278-284`) | HỢP LỆ |
| `max_distance_m` / `min_intensity` | `raycast.py:71-72` | 100 m / 0,0 | `[CHỌN]` kỹ thuật | HỢP LỆ |
| `sigma = segment_lengths / 6` (range noise) | `raycast.py:276` | L/6 | `[CHỌN]`; paper chỉ nói “normal distribution around the middle of the cluster” (`L721-722`), không cho σ | HỢP LỆ (giả định kỹ thuật) |
| `_keep_strongest_per_beam` | `raycast.py:505-538` | — | paper `L748-750`: “the detection intensities of all detections from a beam are compared and the strongest is added” | HỢP LỆ |
| sub-sphere cho vệt | `raycast.py:451-463` | tối đa **8** quả cầu con, `linspace` trên `streak_m` | **không có trong paper**; là phần của cơ chế streak | **PHẢI BỎ** (cùng `streak_scale`) |
| `ELEVATION_STEP_DEG` | `beam_model.py:40` | 0,333° | paper `L371` “0.333°” (central FOV); dùng làm lưới đều cả FOV là `[CHỌN]` (ticket 29c) | HỢP LỆ (paper chỉ nói central FOV) |
| `ELEVATION_MIN/MAX_DEG` | `beam_model.py:38-39` | −4,06 / +5,88° | `[ĐO]` trên release local (**SSPP**); là hình học cảm biến, không phải tham số calibration | HỢP LỆ (khai rõ đo trên release SSPP) |
| `AZIMUTH_STEP_DEG` | `beam_model.py:42` | 0,197307° | `[ĐO]` trên release local (SSPP); hình học cảm biến | HỢP LỆ (khai rõ) |

## 2. Bảng B — tham số CHỈ ảnh hưởng tầng “materialised” (không tới detector)

`inject_plume_stateful` có materialise points vào `result.points`/`injected` (`plume.py:618-638`) nhưng
`PlumeTransform` **bỏ** chúng (`plume_transform.py:129-142` chỉ dùng `points_clean` + `state.all_alive()`).
⇒ các tham số này **không thể** làm đổi det/frame, p50, p95, %≥50đ của A3; đừng dùng để “sửa A3”.

| Tham số | File:dòng | Giá trị hiện tại | Nguồn | Nhãn |
|---|---|---|---|---|
| `_POINTS_MEDIAN_BY_RANGE` | `plume.py:13-19` | 30 / 20 / 14 / 10 / 10 | `[ĐO]` ticket 16 trên **SSPP** (`semantic-spray-stats.md`: 2.070 frame SSPP); paper không cho | **PHẢI BỎ** — SSPP + sai ~4× (A3 diagnosis §3) |
| `points_per_cluster_median` | `plume.py:127` | 17 | `[ĐO]` SSPP; generator **không đọc** (chính comment nói vậy) | **PHẢI BỎ** (dead) |
| `points_per_cluster_sigma` | `plume.py:128` | 0,67 | `[CHỌN]` để p90 ~ 40 (SSPP); không paper | **PHẢI BỎ** (dead + SSPP) |
| `points_per_cluster_bounds` | `plume.py:129` | (3, 200) | `[CHỌN]` kỹ thuật | HỢP LỆ (dead) |
| `_count_for_distance` hệ số `(r/r_median)²` | `plume.py:757-784` | bậc 2 | `[SUY LUẬN]` từ mô hình cầu × tia của paper; paper **không** viết “số điểm ∝ r²” | **CẦN ĐO LẠI** (A3 diagnosis H4 + dead với detector) |
| `radial_squash` | `plume.py:144` | 0,885 | `[CHỌN]` fit để `r_range/r_extent = 1,28` đo trên **SSPP** ticket 16 | **PHẢI BỎ** (dead + SSPP) |
| `cluster_radius_median_m` / `cluster_radius_sigma` | `plume.py:133-134` | 0,30 m / 0,8 | paper Fig. 5 `L524-525` (µ=−1,2, σ=0,8) | HỢP LỆ `[PAPER]` — **không dùng** trong đường stateful (PlumeStateConfig override); chỉ stateless |
| `cluster_radius_bounds_m` | `plume.py:136` | (0,10; 1,00) | `[CODE]` `dee.cpp:528` | HỢP LỆ (stateless) |
| `distance_range_m` / `height_range_m` | `plume.py:145-146` | (1;10) / (0,2;2,0) m | `[CHỌN]` không nguồn; chỉ stateless orphan | HỢP LỆ (`[CHỌN]`, dead production) |
| `lateral_half_width_m` | `plume.py:150` | 2,34 m | `[ĐO]` p95 2,22 m trên 1.022 frame **`cal` = SSPP** (`plume.py:147-149`) | **PHẢI BỎ** (dead + D2) |
| `water_film_height_m` | `plume.py:114` | 0,001 | paper fully covered 1,0 mm (`L556-557`) + `[CHỌN]` default | HỢP LỆ (dead trong stateful — `T` dùng `context.wfh_mm`) |
| `box_margin_m` | `plume.py:151` | 0,2 m | `[CHỌN]` | HỢP LỆ (dead output) |
| `intensity` / `ring` | `plume.py:152,154` | 0,0 / 0,0 | paper `L724-726` (intensity 0) / kỹ thuật | HỢP LỆ (dead output) |
| `_injected_budget` | `plume.py:729-735` | max(500, 5% N) | `[CHỌN]` kỹ thuật | HỢP LỆ (dead output; detections không bị budget) |
| `point_cloud_range` | `plume.py:100-107` | KITTI crop | `[CHỌN]` kỹ thuật | HỢP LỆ |
| `_SPAWN_JITTER_HALF_M` | `plume_state.py:132` | 0,5 m | placeholder test-only (`center=None`) | HỢP LỆ |

---

## 3. Vi phạm D2-chặt còn lại (SSPP làm nguồn chọn tham số)

D2 (ADR-0006): calibration chỉ từ paper + RoadSpray `*_static`; SSPP chỉ để báo cáo/kiểm chứng.
Không tìm thấy runtime nào đọc `label == 2` để chọn tham số trong `spray/` (đã grep `semantic|sspp|
label == 2|label==2|cal`); các file `semantic_*.py` chỉ dùng cho eval/split. Nhưng **giá trị** còn rò rỉ:

1. **`LATERAL_CLAMP_M = 2,43`** — LIVE, `plume_state.py:108-112`; nguồn ghi rõ “real `cal` labels” = SSPP.
2. **`tail_block_height_frac = (0,05; 0,92)`** — LIVE, `plume.py:155-158`; 939.803 điểm nhãn = SSPP,
   paper NOT STATED (`paper-qa-notebooklm.md` §7/§8.4).
3. **`_POINTS_MEDIAN_BY_RANGE` + `points_per_cluster_median/sigma` + `_count_for_distance`** — dead output
   nhưng vẫn là tham số SSPP (ticket 16, p90) đang nằm trong model.
4. **`radial_squash = 0,885`** — dead output, fit trên SSPP ticket 16.
5. **`lateral_half_width_m = 2,34`** — stateless only, p95 trên `cal` SSPP.
6. **`placement_knots`** (default 0) — lý do chọn dẫn “plume thật có 1–2 chuỗi ~1000 điểm” (SSPP).
7. **`warm_start`** — `plume_state.py:353-358` dẫn “scene SSPP chỉ 40–67 frame” để justify cơ chế khởi
   động nóng; không chọn giá trị trực tiếp từ SSPP nhưng cơ chế tồn tại vì độ dài scene của domain eval.
8. **`spawn_scale`** — hiện 1,0 (trung tính); comment dẫn chứng 3,0 từ det/frame SSPP ⇒ nếu ai đặt ≠1
   thì thành hiệu chỉnh SSPP.

Ghi chú: `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` **không** vi phạm D2 (giá trị từ RoadSpray static), nhưng
comment của nó lại ghi SSPP — xem §4.2.

---

## 4. Docstring nói sai về nguồn (loại lỗi tệ nhất — trông như đã kiểm chứng)

1. **`RADIUS_SIGMA = 0.97` nhưng comment ngay trên ghi paper σ=0,8** — `plume_state.py:79-81`:
   dòng 79 `[PAPER] Linnhoff Fig. 5: … sigma = 0,8`, dòng 81 `RADIUS_SIGMA = 0.97`; và
   `PlumeStateConfig` docstring `:144` nói “radius_mu / radius_sigma are the paper's lognormal”.
   Thực tế 0,97 = `rsig` static Δ=2,5 @100. **Phải sửa comment + đưa về 0,727–0,754 (Δ=1,0).**
2. **`_CLUSTER_RADIUS_MEDIAN_BY_SPEED` bị gán sai nguồn** — `plume_state.py:84-89` nói “đo trên SSPP
   207 scene gộp theo fold”, nhưng giá trị hiện tại (0,70/0,60/…/0,66) là **RoadSpray static Δ=2,5**
   (commit `bacff42` đã thay; comment không cập nhật). Người đọc sẽ tưởng đang vi phạm D2, trong khi
   lỗi thật là **sai cột Δ**.
3. **`plume.py:88-90`** — docstring nói `_POINTS_MEDIAN_BY_RANGE` và `r_range/r_extent = 1,28` “đo trên
   SemanticSpray (bản release local)” ⇒ docstring tự khai nguồn SSPP cho tham số đang dùng.
4. **`plume.py:130-134`** — comment “cluster_radius_median 0,30 m (Linnhoff Fig. 5)” đúng cho
   `PlumeConfig`, nhưng đây **không phải** giá trị generator thực dùng ở đường stateful (bảng
   0,45–0,70 m). Docstring dễ làm tưởng generator đang theo paper.
5. **`raycast.py:4-6`** — “It is **not** wired into the generator yet” **SAI**: `plume_transform.py:130`
   đã gọi `raycast_frame` (comment cũ, chưa cập nhật).
6. **`plume_transform.py:14-15`** — docstring nói `P_det = n/n_max`; code thực dùng
   `min(1, lognormal(−2,3;1,1)) × exp(−age/T)` (`raycast.py:269-273`). Paper có Eq. 7 `n/n_max` **và**
   Fig. 7 lognormal — phải ghi rõ đang mô hình theo Fig. 7, không phải Eq. 7.
7. **`plume.py:766-772`** — “Paper mô hình cụm là quả cầu và suy ra số detection … số điểm ∝ r²”: paper
   **không** viết tỉ lệ này; đây là `[SUY LUẬN]`, phải ghi nhãn.
8. **Trích dẫn chết** — `plume.py:77,80,87` dẫn `docs/history/plume-model-provenance.md` và `docs/adr/0003`; `plume.py:96` dẫn
   `docs/measurements/plume-geometry-vs-real.md`; `plume.py:160-162` dẫn test
   `tests/test_plume_config_yaml.py` — **cả ba không tồn tại** trong repo hiện tại
   (`docs/history/` rỗng, `docs/adr/0003` cũng không còn). Không được dựa vào các file đó.

---

## 5. Đã rút lại — 3 điều không được lặp

1. **Dùng SSPP (`label == 2`) làm nguồn chọn tham số** (D2). Nguồn hợp lệ: paper + RoadSpray `*_static`;
   SSPP chỉ để báo cáo/kiểm chứng. Sót lại ở §3.
2. **Đo trên `PlumeResult.injected`** (điểm `ring = -1` bị raycast loại khỏi mọi tính toán): mọi phán
   quyết A3 trước 2026-11-19 vô hiệu; phải đo `RaycastResult.detections`.
3. **`source_count = 2` (hai bánh xe)**: tự bịa, không có trong paper; paper nói đặt đều trong vùng sau
   vật thể (`L393-395`). Đã tắt mặc định nhưng code vẫn còn.

(Ghi chú thêm: các “PASS” trước 2026-11-19 đo bằng dụng cụ sai nên vô hiệu — không dùng làm baseline.)

---

## 6. Cảnh báo dụng cụ đo (ngoài phạm vi sửa của R1 — báo trước khi tin số A3)

1. **Beam grid của dụng cụ ≠ production.** `scripts/measure_plume_size_tail.py:68-74` dùng
   `linspace(−4,06; +5,88; 32)` + az 0,2° = **32 × 1800 tia**; production `beam_model.load_beam_table()`
   dùng `arange(0,333°)` (30 tia) + az 0,197307° (≈1825) = **54.750 tia**. Số A3 đang đo trên lưới khác
   lưới detector thật (~5% tia + góc khác).
2. **`_context` hard-code** `wfh_mm = 1.0`, `road_z_m = −1.6`, box tại `x = 20 m`
   (`measure_plume_size_tail.py:76-88`); đo static dùng mặt đường `z ≈ −2,01 m` và gom plume khi xe chạy
   qua 18–38 m. Đích lấy từ static nhưng dụng cụ mô phỏng following @20 m, road z khác — cần khai báo.
3. **CLI default ≠ config default** (charter §1.4 bug 1 chưa sửa tại mốc audit):
   `--radius-sigma` default **0,8**, `--streak-scale` default **1,0**
   (`measure_plume_size_tail.py:171-172`) trong khi `PlumeStateConfig` default **0,97 / 0,5**. “Chạy
   default” hiện không đo config default.
4. **`vehicle_class` chưa được nối** — `PlumeTransform` gọi `inject_plume_stateful` không truyền
   `vehicle_class` (`plume_transform.py:118-127`), nên mọi scene dùng bảng/radius **Crafter** kể cả scene
   Golf. Với A3 (đích Crafter) thì được, nhưng train trên SSPP trộn 2 lớp sẽ sai nguồn tham số.

---

## 7. Kết luận ngắn

- Bảng A: 33 dòng, trong đó **HỢP LỆ 23 · CẦN ĐO LẠI 6 · PHẢI BỎ 4**.
- Bảng B: 16 dòng, trong đó **HỢP LỆ 10 · CẦN ĐO LẠI 1 · PHẢI BỎ 5**.
- Tổng: **49 dòng tham số · HỢP LỆ 33 · CẦN ĐO LẠI 7 · PHẢI BỎ 9** (đếm máy từ bảng).
- Ưu tiên sửa (đúng charter): `RADIUS_SIGMA` + `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` sang cột Δ=1,0; tắt
  `streak_scale`; bỏ `LATERAL_CLAMP_M`/`tail_block_height_frac` (SSPP); sửa docstring §4.1–4.3 trước khi
  trích dẫn lại paper.
