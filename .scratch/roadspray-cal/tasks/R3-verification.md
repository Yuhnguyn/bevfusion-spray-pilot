# R3 — kiểm chứng độc lập A3 (trạng thái PREP, **chưa chấm điểm cây R1**)

Vai: independent-verifier (R3). Ngày 2026-11-19 · nhánh `sspp`.
Quyền ghi: file này + `.scratch/tmp/`. Không sửa code/test/doc, không `git commit`.
**TRẠNG THÁI: PREP.** Chưa được Lead báo "freeze" ⇒ mọi số dưới đây là **baseline HEAD `bacff42`**
(trước khi R1 sửa) + đo trên máy bị throttle. Dùng để chốt budget + đăng ký trước tiêu chí nghiệm thu,
**không** dùng để kết luận về cây R1.

## 0. Tiêu chí nghiệm thu MỚI (Lead, 2026-11-19 — thay 12 mục cũ)

R1 hiệu chuẩn chính toán tử đo (cầu bán kính biết trước → raycast → lát Δ=1,0 → `cluster_angular`):
r_in 0,20/0,31/0,50/0,80 m đo lại 0,176/0,242/0,360/0,459 m (tỉ lệ 0,88/0,78/0,72/0,57); tăng mật độ
1→120 cụm chỉ kéo r50 +30 %. ⇒ **mọi tiêu chí cluster (r50, rsig, p95, share, cụm/frame) KHÔNG so được
sphere-vs-chain, bị bỏ khỏi PASS**; chỉ còn chẩn đoán.

**PASS cần ĐỦ 3 điều:**
1. **(a)** tổng điểm/frame trong vùng **0–60 m sau đuôi** ∈ **[0,7; 1,5]×** dữ liệu thật (số thật do T4 cấp);
2. **(b')** profile độ sâu 2 m khớp: (i) mỗi bin có ≥10 % mass thật lệch ≤ **30 %**; (ii) độ sâu chứa
   **90 % mass** lệch ≤ **25 %**;
3. **(c)** CI95 half-width của (a) qua 8 seed ≤ **25 %** — không đạt thì in `NHIỄU`, **không kết luận**.

**Chẩn đoán (in, không dùng để kết luận):** `r50_slice`, `rsig_slice`, `p95_slice`, `share_slice`,
`cụm_slice`, `cụm_frame`. Phán quyết cuối của tôi vẫn là ba mức PASS BỀN / MONG MANH / FAIL nhưng
điều kiện "sống còn" giờ là đúng 3 điều trên (+ tính trung thực của dụng cụ, tests, không tham số bịa).

## 1. Baseline HEAD `bacff42` (cách ly khỏi cây R1 đang sửa)

R1 sửa `spray/plume_state.py` + script trong lúc tôi chạy ⇒ baseline được import từ snapshot **git archive HEAD**
(`.scratch/tmp/baseline_tree`), không đọc working tree. md5 baseline: script `b465f10c…`, `plume.py` `cbb02f88…`,
`plume_state.py` `2418c5be…`, `raycast.py` `6aa6b235…`, `beam_model.py` `38acb4b9…`, `semantic_stats.py` `61aec146…`.
(Working tree lúc chạy đã đổi `plume_state.py` → `cb6f309e…`, script `measure_plume_size_tail.py` cũng đã bị sửa.)

**50 km/h — 8 seed, `MEASURE_FRAMES=60`, script defaults (`radius_sigma=0.8, streak_scale=1.0, spawn_scale=1.0`)**
(file log: `.scratch/tmp/r3_prep_baseline.log` + `r3_budget_runs.jsonl`):

| seed | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| det/frame | 390,0 | 293,8 | 512,9 | 450,8 | 417,9 | 371,8 | 452,9 | 382,6 |
| p50 | 5 | 5 | 4 | 4 | 5 | 5 | 4 | 4 |
| p95 | 319 | 286,5 | 374 | 294,6 | 300,4 | 259,9 | 293,5 | 313,2 |
| share ≥50đ | 86,6 | 86,6 | 86,1 | 85,5 | 88,0 | 81,3 | 86,3 | 89,6 |

`mean = 409,1 · sd = 65,8 · CV = 16,1 % · min 293,8 · max 512,9`.
**Script criteria PASS 1/8** (chỉ seed 1). Số seed FAIL theo từng criterion: **det 7/8** (band 0,7–1,5×235,5 =
[164,9; 353,2]); **p50 4/8** (p50=4, band 4,25–8,05); p95 0/8 và share 0/8 (đều nằm trong band rộng).
**Δ=1,0-only: strict 0/8, ±40 % 0/8** — vì p95 đo 305 vs đích Δ=1,0 **172,35** (1,77×); band cũ 172–329
che mất đúng chỗ sai này ⇒ kết luận đổi khi chỉ dùng cột chuẩn thức.
`cpf ratio = 0,98` (đích 9,03, đo 8,84) ⇒ **cụm/frame khớp**; points/cluster = 409/8,84 = **46,3** vs
235,5/9,03 = **26,1** ⇒ **1,77× quá lớn**. Khớp chẩn đoán §1.2 của hiến chương.
⇒ **"50 km/h PASS" cũ (SEEDS=2, seed 0+1 → det 342) là artifact của seed**: 7/8 seed khác vượt trần det.

**100/130 km/h — single-seed baseline** (mf=60, seed 0, chạy lúc máy rảnh): 100 → det 1497, cpf 26,42, p50 6,
p95 294,8, share 85,5 %; 130 → det 1667, cpf 12,5, p50 9, p95 811, share 94,2 %. Multi-seed baseline cho
100/130 **chưa chạy** — Lead đã chốt budget từ 50 km/h nên không đốt CPU vào phần này.

## 2. Bảng (seeds, frames) → CI95 — trả lời câu hỏi budget của Lead

Công thức: đo S seed độc lập, mỗi seed `MEASURE_FRAMES=mf`; `hw95(S,mf) = t_{S−1} · CV(mf) / √S`;
chi phí = `S × (thời gian 1 run ở mf)`. CV lấy từ 8 seed ở 50 km/h (mf=60): **16,07 %**.

| seeds S | hw95 **t-based** | hw95 **z-based** | wall mf=60, máy rảnh (3,2 s/run) | wall, máy throttle (15 s/run) |
|---:|---:|---:|---:|---:|
| 2 (hiện tại) | **144,4 %** | 22,3 % | 6 s | 30 s |
| 3 | 39,9 % | 18,2 % | 10 s | 45 s |
| **4** | **25,6 %** | 15,8 % | 13 s | 1,0 min |
| 5 | 20,0 % | 14,1 % | 16 s | 1,3 min |
| 6 | 16,9 % | 12,9 % | 19 s | 1,5 min |
| **8** | **13,4 %** | 11,1 % | 26 s | 2,0 min |

- **SEEDS=2 hiện tại ⇒ CI95 vô nghĩa** (t(1)=12,7): không thể báo mean ± CI từ 2 seed.
- **S=4 chạm đúng ngưỡng 25 %**; **S=8** dư an toàn (13,4 %). Khớp quyết định của Lead:
  tối thiểu S=4, nghiệm thu S=8.
- Thời gian: 1 run mf=60 @50 km/h = **3,2 s** máy rảnh / **8,9–32 s** lúc load 60–180; 100 km/h ≈16 s,
  130 km/h ≈19 s (rảnh). Vậy nghiệm thu 8 seed × 3 tốc độ ≈ 0,4 + 2,1 + 2,6 phút ≈ **5 phút máy rảnh**
  (chưa kể warm-up process + import ~2 s/run). Load throttle hiện tại làm wall tăng 3–10×.
- CV đo ở mf=120 (n=2 seed mỗi tốc độ, **rất không đáng tin**): 50 → 5,7 %, 100 → 7,0 %, 130 → 7,6 %.
  Nhưng §3 cho thấy det/frame có **dao động chậm** (block 60 frame lệch ±20–30 %), nên CV thật của
  window mean lớn hơn số n=2 này; ước lượng bi quan từ block (2 block/window, xem §3b):
  50 ≈ 15 %, 100 ≈ 16 %, 130 ≈ 9 %. Với các CV đó: **S=8, mf=120 → hw95(t) ≈ 7–13 %** (đạt ≤25 %);
  **S=4 → 12–22 %** (chạm/vượt ngưỡng ở 50–100 km/h). ⇒ **S=8 + mf=120 là cấu hình nghiệm thu đúng**.

## 3. Drift `MEASURE_FRAMES` 60 → 120 — KHÔNG phải warm-up drift, mà là dao động chậm

Phát hiện khi kiểm tra: mf 60→120 đổi det/frame rất mạnh (100 km/h +23,2 %; 130 +9,9 %; 50 −7,8 %).
Đã truy nguyên bằng trace từng frame (`.scratch/tmp/r3_stationarity_{50,100,130}.json`,
`r3_stationarity.py`) — tái lập **đúng** `measure_speed`: block 60 frame đầu của trace = det mf=60
của cùng seed (100: 1497,0 = 1497,0; 130: 1667,3 = 1667,3; 50: 390,0 = 390,0) và trung bình 2 block
= det mf=120 (100: 1730,1 = 1730,1…).

| tốc độ | alive clusters (frame 0 → 260) | det/frame 6 block × 60 frame (260…619) | kết luận |
|---|---:|---|---|
| 50 | 5 → 6 (dao động 4–9) | 390 · 402 · 367 · 282 · 447 · 247 | **không ramp**; block CV 21,7 % |
| 100 | 25 → 27 (dao động 24–28) | 1497 · 1963 · 1027 · 1482 · 1626 · 1287 | **không ramp**; block CV 22,2 % |
| 130 | 22 → 20 (dao động 20–23) | 1667 · 1903 · 1590 · 1544 · 1946 · 1423 | **không ramp**; block CV 12,1 % |

**Kết luận:** (i) `alive` clusters **phẳng** từ frame 0 ⇒ state đã ở trạng thái dừng, **không** có warm-up
ramp — mf 60 vs 120 không phải lỗi "chưa tới steady state"; (ii) nhưng `det/frame` có **dao động chậm
chu kỳ ≳60 frame, biên độ ±20–30 %** (không tương quan với alive) ⇒ mf 60→120 chỉ là **lấy mẫu pha
khác nhau của cùng một quá trình dừng**; (iii) hệ quả thực dụng: **một window 60–120 frame là ước lượng
kém ổn định**, phải cố định mf và trung bình đủ nhiều seed; so sánh mf60 vs mf120 **không** dùng làm
tiêu chí pass/fail mà là **độ nhạy window** phải khai báo.

### 3b. Ngân sách nghiệm thu dưới dao động chậm (khuyến nghị)

- Block CV (bảng trên) ⇒ window mean mf=120 (≈2 block) có CV ≈ blockCV/√2: 50 ≈ 15,4 %, 100 ≈ 15,7 %,
  130 ≈ 8,6 %. **S=8, mf=120: hw95(t) ≈ 7,2–13,1 %** → đạt CI95 ≤ 25 % thoải mái.
- **S=4, mf=120: hw95 ≈ 11,9–21,8 %** → đạt ngưỡng 25 % nhưng sát ở 50–100 km/h; nếu Lead muốn
  "tối thiểu 4" thì nên là 4 **cộng thêm** 2 seed dự phòng hoặc nâng mf=120 → 180.
- **mf=120 nên cố định** trong acceptance; ghi kèm det(mf=60) như độ nhạy (đừng trộn hai mf vào một kết luận).
- Chi phí 8 seed × 3 tốc × mf=120: 100/130 ≈ 70–80 s/run (đo lúc load ~60; máy rảnh ~30–40 s), 50 ≈ 20 s/run
  ⇒ **≈ 6–10 phút** cả cụm (chưa kể import). Số wall này đo dưới load dao động nên chỉ là cận trên.

## 4. Kế hoạch nghiệm thu khi freeze (đúng lệnh, đúng tham số, đúng tiêu chí)

Chờ Lead báo freeze → claim task-12 (`team_task_get` rev mới nhất → `claim`) → chạy trên working tree R1:

```bash
# 1) script thật, default config (ground truth criterion của R1)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_plume_size_tail.py            # default; ghi wall time + 3 dòng PASS/FAIL
# 2) nếu R1 có --seeds/--frames: nghiệm thu chính thức
... scripts/measure_plume_size_tail.py --seeds 8 --frames 120
# 3) harness độc lập (10 seed, drift, repro, Δ=1,0-only)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    .scratch/tmp/r3_verify.py --tree current
# 3b) đo ĐỘC LẬP (a)+(b')+(c): 8 seed x 120 frame, 2 biến thể vùng
... .scratch/tmp/r3_region_profile.py --tree current --seeds 8 --frames 120 \
    --targets <T4 aggregate json>
# 4) test
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python -m pytest tests -q
# 5) rò rỉ + bịa đặt
grep -rn "label == 2\|labels == 2\|SemanticSpray\|sspp\|_CLUSTER_RADIUS_MEDIAN_BY_SPEED\|_POINTS_MEDIAN_BY_RANGE\|RADIUS_SIGMA\|LATERAL_CLAMP_M" spray scripts/measure_plume_size_tail.py tests
git diff HEAD -- spray scripts tests docs/measurements
```

Sẽ ghi: 10 seed × 3 tốc (mean ± CI95, PASS count) + **acceptance S=8/mf=120** (Lead chốt 2026-11-19, R1 đặt lại default),
drift mf 60/120 **như độ nhạy window** (bỏ mf240), repro ×2 exact, Δ=1,0 strict/loose, 7 kiểm tra 4b,
số test + rc, diff audit. Ghi rõ **md5 working tree lúc chấm** (sẽ khác baseline vì R1 đang đổi bán kính
thành hằng 0,31 m / `RADIUS_SIGMA=0.73` / beam grid 30×1825 từ `load_beam_table()` / CLI default từ config /
cờ `--seeds/--frames` / criterion (c) CI95≤25 %).

### 4b. Danh sách chấm MỚI — 9 mục (thay 12 mục cũ)

Đo trên cây đã freeze. Harness: `.scratch/tmp/r3_region_profile.py` (độc lập (a)(b')(c), 2 biến thể vùng),
`r3_verify.py` (đa seed + chạy script thật + drift + repro + Δ=1,0-only), `r3_box_checks.py` (chẩn đoán
hộp/height/radius), `git diff`/grep cho mục code.

| # | Kiểm | Cách đo độc lập | Đạt khi |
|---|---|---|---|
| 1 | `pytest` xanh? bao nhiêu test? | `python -m pytest tests -q`; đếm; so 208 ở HEAD `5596511` | rc=0, ≥208 |
| 2 | 8 seed × 120 frame → (a)+(c)+profile | chạy script thật default (8/120) + harness độc lập; ghi mean±CI95 | bảng số đầy đủ |
| 3 | **độc lập** kiểm (a) | `r3_region_profile.py --tree current --seeds 8 --frames 120`: tự inject/raycast, tự đếm vùng; KHÔNG đọc output R1 | khớp script thật trong sai số đo |
| 4 | dụng cụ dùng `load_beam_table()` 30×1825; generator **không còn streak** | grep `load_beam_table`/`production_table` trong script; grep `streak` toàn `spray/`; kiểm `PlumeStateConfig.streak_scale` default & mọi nơi gán | lưới 30×1825; streak default 0,0 và không có đường bật |
| 5 | bán kính VẪN 0,30–0,31 m | đọc `spray/plume_state.py`: `RADIUS_MEDIAN_M`, `cluster_radius_median_for_speed`; grep 0,349/0,292/0,311 | ∈[0,30;0,31] |
| 6 | vùng sinh = 3,4×1,5×20 m; \|y\|≤1,7; z∈[mặt đường; +1,5] | đọc code sinh trong `plume_state.spawn`; đo phân bố tâm cụm (chẩn đoán) | đúng hộp |
| 7 | profile generator tính bằng **binning điểm**, không clustering | đọc code `measure_speed` QĐ10 (chỉ `depth` + `bincount`) | đúng binning |
| 8 | diff tests/: dung sai KHÔNG bị nới | `git diff bacff42..HEAD -- tests/` + so %/abs tolerance từng assertion | tolerate không tăng |
| 9 | sổ toán tử: mỗi tiêu chí hai vế cùng phép đo | bảng đối chiếu (dưới) | tất cả khớp |

**Ba điểm tôi đã phát hiện khi đọc code HEAD `5596511` — phải xác nhận lúc chấm:**

- **(9-a) Lệch toán tử profile (nguy cơ cao):** phía generator, `measure_speed` tính `depth` trên **mọi**
  detections có depth ∈[0;60) — **không** mask `|y|` và `height`. Phía thật, `scripts/roadspray_static_depth_profile.py`
  đo depth 0–60 m, **ngang ±5 m**, **cao 0,15–3,0 m**. Nếu T4 cấp số strict mà R1 so với số loose thì
  hai vế khác phép đo ⇒ PASS/FAIL vô hiệu. Harness của tôi báo **cả hai biến thể** (`points_per_frame` loose
  và `_strict`) để phát hiện.
- **(9-b) `depth_at_mass` lệch nửa bin:** R1 trả `EDGES[index]` (biên trái của bin đạt mass) trong khi độ sâu
  90 % mass nên là biên **phải** `EDGES[index+1]`; sai 0–2 m trên ngưỡng ≤25 % của (b')(ii). Harness của tôi
  tính biên phải (chuẩn) và in thêm biên trái để so.
- **(9-c) rear_x lệch 0,1 m:** vùng dùng `BOX_HALF_LENGTH_M = 3,5` ⇒ rear = 16,5 m; nhưng box sinh dùng dài
  6,8 ⇒ rear = 16,6 m. Nhỏ, nhưng phải khai trong sổ toán tử.

**Sổ toán tử (mục 9) — đối chiếu từng tiêu chí:**

| Đại lượng | Vế generator | Vế thật | Cùng? |
|---|---|---|---|
| điểm/detections | `RaycastResult.detections` | residual sau range-image nền | ✓ (đều là "detections của cảm biến") |
| tia | `load_beam_table()` 30×1825, az 0,197307° (đã xác nhận) | cùng sensor VLP-32C | kiểm lại sau freeze |
| vùng (a)/(b') | depth 0–60 sau đuôi, **chưa mask ngang/cao** | depth 0–60, ±5 m, 0,15–3,0 m | ✗ nếu T4 strict — xem 9-a |
| vùng sinh cụm | hộp 3,4×1,5×20, z∈[mặt đường;+1,5] | hộp calibration static | kiểm code (#6) |
| cụm (chẩn đoán) | lát Δ=1,0 m + DBSCAN góc | cùng công thức `roadspray_static_plume_box.py` | ✓ theo QĐ1 |
| radius clip | 2,0 m (paper p99 lognormal = 1,94) | paper không đặt clip | ghi nhận |

### 4c. Snapshot code-audit trước freeze (HEAD `5596511`, commit A3.6)

Đọc trước để lúc freeze chỉ cần kiểm delta. Các điểm đã xác nhận **trên code**:

- **#4 tia:** `scripts/measure_plume_size_tail.py::production_table()` gọi `load_beam_table()`;
  đã tự kiểm bằng import: **30 ring × 1825 az (0,197307°) = 54.750 tia** ✓. (Baseline cũ 32×1800 = 57.600 ✗.)
- **#4 streak — KHÔNG đạt nghĩa "đã xoá hẳn":** `PlumeStateConfig.streak_scale` vẫn còn (default **0,0**,
  ghi chú "[BỎ THEO AUDIT R2]"), `spray/raycast.py:451` vẫn có nhánh sinh chuỗi sub-sphere khi `streak_m > 0`;
  `streak_m = |v_ego|·dt·cfg.streak_scale` ⇒ default 0,0 thì **inert** ✓ nhưng cơ chế chưa bị xoá.
  **Bẫy:** `measure_speed(..., streak_scale=1.0)` vẫn còn default 1,0 trong chữ ký hàm (CLI truyền 0,0) —
  ai gọi trực tiếp hàm mà không truyền thì **bật lại streak**. Kiến nghị: CLI/hàm default phải là 0,0, hoặc xoá hẳn.
- **#5 bán kính:** `RADIUS_MEDIAN_M = 0.31`, `RADIUS_SIGMA = 0.72`, `RADIUS_MAX_M = 2.0`,
  `cluster_radius_median_for_speed()` trả hằng 0,31 ✓. Grep 0,349/0,292/0,311 trong `spray/` lúc chấm.
- **#6 vùng sinh:** `SPAWN_BOX_WIDTH_M=3.4`, `SPAWN_BOX_HEIGHT_M=1.5`, `SPAWN_BOX_DEPTH_M=20.0`;
  `spawn()` lấy `offset ~ U(-1,1)^3 · extents`, tâm khối cách rear `depth/2`, đáy = `road_z` ⇒
  depth∈[0;20], |y|≤1,7, z∈[mặt đường; +1,5] ✓ (chờ xác nhận bằng phân bố tâm cụm thực đo, nếu kịp).
- **#7 profile binning:** `measure_speed` QĐ10 chỉ tính `depth = rear_x − x` rồi `np.bincount` theo bin 2 m —
  **không clustering** ✓. NHƯNG toán tử vùng hai vế khác nhau (xem 9-a) — đây là rủi ro chính của (a)/(b').
- **#8 tests:** diff `bacff42..HEAD -- tests/` = 5 test def thêm, 4 bỏ (đổi tên/gộp); expected value đổi theo
  bảng Δ=1,0 (6→9, 27→25, 26→36, 22→33) — **không** phải nới dung sai. Hai chỗ cần soi kỹ lúc chấm:
  (i) `assert 14 <= mean(per_cluster) <= 30` → `12 <= ... <= 26` (nới cận dưới 2, siết cận trên 4 — net hẹp
  nhưng **một phía bị nới**); (ii) `0.05 <= at_cap <= 0.09` → `0.004 <= at_cap <= 0.015` (giá trị kỳ vọng đổi
  theo clip bán kính 1,0→2,0 m — cần đọc ngữ cảnh, không phải nới tolerance nếu là cùng đại lượng).
- **#2/#3 (a)+(c)**: `SEEDS=8`, `MEASURE_FRAMES=120`, CI95 bootstrap theo seed (B=2000) ≤25 % → in `NHIỄU`
  đúng như mô tả ✓ (xác nhận bằng chạy thật lúc freeze).

## 5. Rò rỉ SSPP đã biết trước freeze (sẽ xác nhận lại trên diff R1)

| # | chỗ | dùng SSPP để chọn gì | trạng thái chờ freeze |
|---|---|---|---|
| 1 | `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` (SSPP) | bán kính theo tốc độ | **A3.6 đã thay** bằng `RADIUS_MEDIAN_M = 0.31` — kiểm lại lúc chấm |
| 2 | `RADIUS_SIGMA` | σ lognormal | **A3.6 = 0,72** (cột Δ=1,0); kiểm lại |
| 3 | `spray/plume.py::_POINTS_MEDIAN_BY_RANGE` | số điểm/cụm theo cự ly, ticket 16 SSPP | R2: điểm materialised không tới detector ⇒ không sửa được det/frame; vẫn là provenance leak |
| 4 | `LATERAL_CLAMP_M = 2.43` | p95 trên `cal` labels | **A3.6 đã bỏ** (theo audit R2) — xác nhận bằng grep |
| 5 | `lateral_half_width_m = 2.34` | p95 trên 1.022 frame `cal` | còn trong `PlumeConfig`? — kiểm lúc chấm |
| 6 | `spray/plume.py::height_range_m=(0.2, 2.0)`, `radial_squash=0.885` | [ĐO] trên SSPP `cal` | chưa thấy trong kế hoạch R1 — báo |

Mục 1–2 R1 đang sửa (theo Lead). Mục 3–6 là **leak nguồn chọn tham số còn lại** — R2 đã có doc provenance;
tôi sẽ liệt kê lại khi chấm và để Lead quyết định có block A3 hay không (không nằm trong 7 mục task-12
nhưng nằm trong mục 5 của task-12).

## 6. Đã làm / chưa làm

- **Đã**: harness (`r3_prep_harness.py`, `r3_budget.py`, `r3_drift.py`, `r3_stationarity.py`, `r3_box_checks.py`,
  `r3_verify.py`, `r3_region_profile.py`), code-audit snapshot §4c, baseline
  50 km/h 8 seed, bảng (seeds→CI95), baseline 100/130 single-seed, snapshot HEAD cách ly, phát hiện
  "50 km/h PASS là artifact" + "Δ=1,0-only đổi kết luận".
- **Chưa** (chờ freeze): chấm 9 mục mới (0–4c), pytest 208, profile/region độc lập, diff audit test, grep streak/SSPP.
- **Số không dùng để kết luận**: mọi số §1–3 đo trên dụng cụ cũ (beam 32×1800 az 0,2° — R2 phát hiện
  production dùng `load_beam_table()` 30×1825 az 0,197307°); R1 đang sửa nên cây sau freeze sẽ khác.

---

# 8. CHẤM CUỐI A3 — freeze 2026-11-19 (kết quả độc lập)

Cây lúc chấm (working tree, chưa commit): `measure_plume_size_tail.py` `134f7233…`, `plume_state.py`
`8c3ae8ca…`, `plume.py` `08635334…`, `raycast.py` `8c58faf8…`; defaults: `diffusion_alpha=0.06`,
`radius_sigma=0.72`, `radius_median=0.31`, `radius_max=4.0`, `streak=0.0`, `lifetime_sigma=0.0`,
`p_det_scale=1.0`, beam `load_beam_table()` **30×1825 = 54.750 tia** (tự import kiểm).
`pytest`: **208 passed** (28,77 s).

## 8.1 Bảng 3 tốc độ × 3 tiêu chí (harness RIÊNG, 8 seed, không đọc aggregate của R1)

`r3_final_static.py`: tự chạy generator (ego đứng yên, xe 18,5→200 m, slab `|v|·Δt`), tự mask
`|y|≤5 / 0,15≤h≤3,0 / bỏ hộp thân xe / range>4`, tự bin 2 m, tự tính trail90 (biên phải) + bootstrap.

| km/h | frame/seed | det/frame | (a) tỉ lệ | (a) | (b')(i) bin≥10% | (b')(ii) trail90 | (c) CI95 | KẾT LUẬN |
|---:|---:|---:|---:|---|---|---|---:|---|
| 50 | 120 | **13,03** | 0,153× (85,1) | **FAIL** | **FAIL**: 3 bin, lệch max **98,2 %** | **2,0 m = 0,333×** (6 m) → **FAIL** | ±11,1 % | **FAIL** |
| 100 | 66 | **144,0** | 0,711× (202,6) | **PASS** | **vacuous** (0 bin ≥10 % mass thật) | 40,0 m = 0,909× (44 m) → PASS | ±5,8 % | **PASS** |
| 130 | 51 | **283,4** | 1,357× (208,9) | **PASS** | **vacuous** (0 bin) | 50,0 m = 0,962× (52 m) → PASS | ±9,0 % | **PASS** |

**Phán quyết: A3 KHÔNG ĐẠT** (50 km/h ngoài miền tin cậy: det 0,15×, trail 0,33×). 100/130 PASS
(a)+(b')(ii)+(c) nhưng **MONG MANH**: (b')(i) không có bin nào để chấm ở 100/130 (xem §8.4-1), và
α có dấu hiệu tune đa mục tiêu (§8.3-1). Mass20 (không thuộc PASS): 100,0 / 60,8 / 44,1 % vs thật
99,5 / 53,8 / 25,7 % → @130 lệch **+71,5 %**.

## 8.2 Đối chiếu với bảng script của R1 (8 seed, cùng default)

| km/h | R1 det | R3 det | lệch | R1 trail90 | R3 trail90 | R1 CI95 | R3 CI95 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 13,0 | 13,03 | +0,2 % | 2,2 m | 2,0 m | ±11,1 % | ±11,1 % |
| 100 | 144,0 | 144,02 | 0,0 % | 40,2 m | 40,0 m | ±5,8 % | ±5,8 % |
| 130 | 283,4 | 283,38 | 0,0 % | 49,8 m | 50,0 m | ±9,0 % | ±9,0 % |

Không mục nào lệch >20 % ⇒ hai harness dùng **cùng cấu hình**; khác biệt duy nhất là biên độ
trail90 (2,2 vs 2,0 m) do giá trị bin rời rạc + cách lấy trung bình (per-run vs trên profile gộp).
Lưu ý: lần chạy đầu của tôi **không cap** frame → 131 frame @50 và det 11,93 (lệch −8,2 % so R1);
sau khi cap đúng `MEASURE_FRAMES=120` thì khớp. Đây là bằng chứng cần nói rõ "120 frame" là **cap**,
không phải luôn 120 (xem §8.4-2).

## 8.3 Bốn điều Lead yêu cầu kiểm kỹ

1. **α = 0,06 dùng chung + "chỉ hiệu chỉnh từ trail90":** (i) dùng chung ✓ — một `DIFFUSION_ALPHA=0.06`
   trong `PlumeStateConfig`, áp trong `advance()` cho mọi tốc độ, không nhánh theo speed.
   (ii) **KHÔNG chứng minh được "chỉ từ trail90"**: theo chính bảng quét trong doc §7.11, α = 0,03 cho
   trail90 41/49 m và α = 0,08 cho 41/49 m — **cả hai đều đạt ±25 %** ở 100/130 (đích 44/52), tức
   trail90 **không phân biệt** được α trong [0,03; 0,08]. α = 0,06 chỉ nổi lên khi xét thêm
   det/frame: α=0,03 có det@100 = 0,42× (trượt), α=0,06 có 0,73× (đạt); doc cũng viết "khớp **cả det
   lẫn trail**", ADR lại ghi "chỉ từ trail90". ⇒ **có dấu hiệu tune 2 mục tiêu**; đề nghị ADR sửa câu
   provenance thành "chọn trong dải trail90 chấp nhận được, ưu tiên det@100 vào dải" và ghi là [CHỌN].
2. **`p_det_scale` = 1,0 thật:** ✓ `RaycastConfig.p_det_scale = 1.0` (chỉ nhân ở `raycast.py:279`);
   production `PlumeTransform` gọi `raycast_frame(...)` **không truyền config** ⇒ 1,0; script CLI default
   1,0; không có scale ẩn ở path khác (grep toàn `spray/` chỉ 2 chỗ). Điều **cần khai**: R1 đã quét và
   biết p_det≈0,22 mới khớp 100/130 (§7.8) nhưng nghiệm thu giữ 1,0 theo quyết định của Lead.
3. **Cửa kiểm QĐ14:** `range ≤ 4 m` = **0 detections** cả 3 tốc độ ✓. `range < 15 m`: 100/130 = **0**;
   @50 = **4/15.123 detections = 0,0264 %** (range min 14,66 m) — **không đúng tuyệt đối "= 0 %"**;
   script của R1 in "0,0 %" do làm tròn 1 chữ số. Mức 0,026 % là không đáng kể nhưng phải ghi đúng.
4. **Kịch bản static đúng:** ✓ `_static_context` đặt `ego_speed_mps=0.0`, `object_velocity_ego=[v,0,0]`;
   loop `car_x = start_x + step·i` tới **200,9 / 202,3 / 203,2 m** (max, do +1 bước); `advance()` nhận
   ego_velocity = 0 ⇒ không có chuyển động ego. **Caveat ngữ cảnh:** T4 thật có `car_range` max
   **97 / 166 / 207 m** (50/100/130) — generator chạy tới ~186 / 202 / 203 m (sau cap) ⇒ @50 generator
   mô phỏng **xa hơn dữ liệu thật** (186 vs 97 m). 50 vẫn FAIL nên không đổi verdict, nhưng nếu sau này
   cứu 50 km/h thì phải cắt trajectory theo phân bố car_range thật.

## 8.4 Doc/tool của R1 nói quá — danh sách cụ thể

1. **(b')(i) KHÔNG chạy được ở 100/130:** profile thật 100/130 không có bin 2 m nào ≥10 % mass
   (max 8,68 %/7,11 %). Hệ quả: (i) **vacuous** ở hai tốc độ này; script nghiệm thu của R1
   `.scratch/tmp/a3_acceptance.py` sẽ **crash** `ValueError: zero-size array to reduction` tại
   `rel_dev.max()`/`argmax`; script chính `measure_plume_size_tail.py` **không hề cài** (i), chỉ in
   trail90. Vậy "PASS" công bố là PASS của (a) + trail proxy + (c), **không phải** đủ 3 tiêu chí đã
   đăng ký. Cần hoặc sửa ngưỡng (i) cho phù hợp (vd ≥5 % mass hoặc KS-distance), hoặc ghi rõ (i)
   vacuous. (Sensitivity của tôi: bin ≥5 % → 3 bin, lệch max 47 % @130.)
2. **"8 seed × 120 frame" là không đúng nguyên văn:** `MEASURE_FRAMES` chỉ là **cap**; số frame thực đo
   = **120 / 66 / 51** (50/100/130) vì trajectory 200 m dài hơn 120 frame ở tốc độ thấp. Doc §6.6/§6.7
   ghi "nghiệm thu 8 seed × 120 frame" (và bảng script in cột n_frame 120) dễ đọc thành luôn 120.
3. **§6.6 "Tiêu chí A3 hiện hành"** vẫn liệt kê tiêu chí **cũ** (r50/rsig ±20 %) — trái với ADR
   addendum §3 ((a)(b')(c) profile). Dễ khiến người đọc chấm sai bộ tiêu chí; phải đánh dấu superseded.
4. **§7.4 nói "bỏ `tail_block_height_frac`"** nhưng field vẫn tồn tại `PlumeConfig.tail_block_height_frac
   = (0.05, 0.92)`, còn được `tests/test_sspp_plume_integration.py:33` và
   `scripts/diag_verify_conventions.py:141` đọc. "Bỏ" chỉ đúng nghĩa "generator không dùng", không phải
   xoá khỏi code/test.
5. **§7.9 viết α default 0,0 "cho tới khi chốt α"**, nhưng default đã bake **0,06** (cả `PlumeStateConfig`
   lẫn CLI). Câu này chỉ đúng ở thời điểm lịch sử, cần cập nhật.
6. **Profile (b') hai vế lệch nhẹ toán tử:** profile thật dùng cho (b')(i) là bản **base-mask**
   (99,0/203,2/208,6; còn ~14 % điểm thân xe @50), còn profile generator là bản **đã bỏ hộp thân xe**
   (target geom 85,1/202,6/208,9). Ở 100/130 chênh <1 % nên không đổi kết luận; @50 hai bên khác
   14 % cần khai (50 fail cả hai cách). Ngoài ra (i) vacuous 100/130 nên mismatch không thành vấn đề.
7. **"range<15 m = 0,0 %"**: đúng đến 1 chữ số thập phân; số thật @50 là 0,0264 % (4 detection) — xem §8.3-3.

## 8.5 9 mục task-12 (bản Lead cập nhật) — kết quả

| # | Mục | Kết quả |
|---:|---|---|
| 1 | pytest xanh, số test | **208 passed**, rc=0, 28,77 s ✓ |
| 2 | 8 seed × frame → (a)(c)+profile | ✓ §8.1 (frame 120/66/51) |
| 3 | kiểm (a) độc lập, không dùng output R1 | ✓ khớp R1 <0,5 % (det) |
| 4 | beam 30×1825; generator hết streak | beam ✓ 54.750 tia; streak: default 0,0 + static ego=0 ⇒ **luôn 0**, nhưng **code path vẫn còn** trong `raycast.py:458-470` và field `streak_scale` vẫn tồn tại ⇒ "hết streak" chỉ đúng nghĩa "inert" |
| 5 | bán kính vẫn 0,30–0,31 m | ✓ `RADIUS_MEDIAN_M=0.31`, σ=0,72; không dùng 0,349/0,292/0,311 làm input (chỉ trong comment) |
| 6 | vùng sinh 3,4×1,5×slab | ✓ `SPAWN_BOX_WIDTH=3.4`, `HEIGHT=1.5` từ `road_z`, `slab=|v|·Δt`; test `test_spawn_box_matches_the_reference_slab` khẳng định đúng |
| 7 | profile bằng binning điểm | ✓ `_static_profile` chỉ `depth` + `np.bincount`, không clustering; harness độc lập tái tạo khớp |
| 8 | diff tests không nới dung sai | 5 file, 8 def thêm/bớt; các thay đổi: giá trị kỳ vọng theo QĐ12/13 (vd 6→9, 27→25, 26→36, 22→33), `at_fifty` abs **siết** 1e-3→1e-4, clip 1→4 m, `at_cap` window 0,004–0,015 → 0,0001–0,0025 (đổi theo clip; **bề rộng tương đối 3,75× → 25×** — nới, nhưng là kiểm tra sanity không phải tiêu chí A3), test lifetime mới dùng dải ±40 % quanh exp(−t/T) (hợp lý cho cơ chế xác suất paper, ±~2,2σ binomial). **Không phát hiện nới dung sai của tiêu chí A3** (tiêu chí nằm trong script, không trong tests) |
| 9 | sổ toán tử 2 vế | ✓ phần lớn khớp: detections layer, beam production, mask ±5/0,15–3,0, binning, trail biên phải. **Còn 2 lệch**: (i) frame window 200 m vs car_range thật 97/166/207; (ii) profile base-mask (body) vs generator body-removed — xem §8.4-6 |

## 8.6 Điều kiện làm phán quyết đổi

- Nếu **không** chấm 50 km/h (tuyên bố rõ "A3 chỉ áp dụng ≥100 km/h"): 100/130 PASS (a)+(b')(ii)+(c)
  ⇒ có thể ghi "PASS có điều kiện", nhưng phải khai (b')(i) vacuous + α tune đa mục tiêu.
- Nếu sửa (b')(i) thành ngưỡng khác (≥5 % mass): @130 lệch 47 % ⇒ **130 sẽ FAIL** ⇒ A3 vẫn không đạt.
- Nếu p_det_scale đổi khỏi 1,0: mọi số (a) đổi, phải chấm lại.
- Nếu trajectory cắt theo car_range thật (@50 ≤97 m): (a)@50 có thể tăng nhưng trail vẫn 2 m ⇒ 50 vẫn FAIL.

## 8.7 Addendum — kiểm tra còn lại của task-12 (gốc) trên cây freeze

- **Đa seed, mức seed (tiêu chí (a) áp cho từng seed thay vì mean):** tỉ lệ det/đích từng seed
  50: 0,15–0,19 → **0/8 seed PASS**; 100: [0,727; 0,736; 0,811; 0,662; 0,633; 0,739; 0,750; 0,627]
  → **5/8 seed PASS**; 130: [1,300; 1,088; 1,509; 1,699; 1,377; 1,310; 1,360; 1,209] → **6/8 seed PASS**
  (2 seed vượt trần 1,5). ⇒ nếu áp ngưỡng cũ "≥70 % seed PASS" thì **100 km/h là MONG MANH** (62,5 %).
  Quan trọng hơn: **biên của (a)@100 chỉ 0,711 vs ngưỡng 0,70 = +1,1 %** ⇒ PASS ở 100 nằm sát ngưỡng;
  130 có biên +9,5 % (so 1,5). Trail: 100 dev 9,1 % (ngưỡng 25 %), 130 dev 3,8 %.
- **Tái lập (cây freeze):** `measure_speed(100, seed=0)` chạy 2 lần → **toàn bộ dict giống tuyệt đối**
  (det_masked 147,393939; unmasked 183,575758; trail90 42,0; mass20 62,122501; 66 frame) ⇒ không có
  nguồn ngẫu nhiên ngoài seed. ✓
- **Rò rỉ SSPP (grep `label == 2`, `SemanticSpray`, `sspp`, `_CLUSTER_RADIUS_MEDIAN_BY_SPEED`):**
  không còn trong `scripts/measure_plume_size_tail.py` hay đường chọn tham số của generator; các hit
  còn lại ở `spray/sspp_adapter.py`, `semantic_split.py`, `semantic_stats.py`, `spray_stats.py`,
  `plume_context.py` (đọc dữ liệu/ghi doc, không phải nhánh chọn tham số A3). Hai tham số gốc SSPP
  vẫn tồn tại nhưng **ngoài đường det/frame**: `PlumeConfig.lateral_half_width_m = 2.34` (p95 trên
  `cal`) và `_POINTS_MEDIAN_BY_RANGE` (ticket 16, chỉ tầng materialised — R2: `PlumeTransform` bỏ các
  điểm này). Ghi nhận là tồn dư provenance, **không ảnh hưởng A3**.
- **Tham số không nguồn trong diff A3** (mục 7 cũ): `diffusion_alpha=0,06` + `RADIUS_MAX_M=4,0`
  (**ngoài paper**, QĐ13, user-approved, ghi trong ADR §2); `STATIC_MIN_TAIL_RANGE_M=18,5` và margin
  `+0,5` là **số kỹ thuật [CHỌN]** để slab nằm ngoài 15 m (không phải paper/static) — cần nhãn [CHỌN]
  trong doc; `STATIC_DT_S=0,1` [CODE] update cycle; `STATIC_BODY_DIMS`/`MARGIN 0,2`/mask ±5–0,15–3,0/
  `TARGET_*` đều lấy từ T4 (`roadspray-static-depth-profile.md` §5b + `depth_signal_v2_summary.json`).
  Không phát hiện tham số bịa không khai báo khác.

## 8.8 Cái gì đã thay đổi vì phán quyết này

1. **ADR sửa provenance của α:** câu *"α hiệu chỉnh chỉ từ trail90"* đã được thay bằng nhãn **[CHỌN]**:
   trail90 không phân biệt được α ∈ [0,03; 0,08] (cả ba cho 41/49 m), α = 0,06 được chọn đồng thời theo
   det (α=0,03 làm det@100 = 0,42× trượt) — ADR §5.2 ghi rõ.
2. **4 caveat vào ADR §5.5:** (b')(i) vacuous ở 100/130; "8 seed × 120 frame" thực chất là **cap** →
   120/66/51; `range<15 m` @50 = **0,0264 %** (4 detection, không tuyệt đối 0); @50 generator chạy tới
   ~200 m trong khi dữ liệu thật max 97 m.
3. **Verdict A3 giữ nguyên: KHÔNG ĐẠT** (50 km/h ngoài miền tin cậy: det 0,153×, trail 0,333×).
4. **100/130 "PASS mong manh" chỉ đúng DƯỚI ĐỊNH NGHĨA VACUOUS:** chúng PASS (a)+(trail)+(c) khi
   (b')(i) không có bin nào để chấm. Dưới **định nghĩa hiệu lực** — chấm mọi bin nằm trong vùng chứa
   90 % mass thật — profile **trượt 268 % @100 và 995 % @130** (tính lại từ `r3_final_static.json` +
   `depth_signal_v2_summary.json`; @50 trượt 98 %). Vì tiêu chí rỗng đã bị bác, **kết luận đúng là
   FAIL cho cả 100/130 theo bộ tiêu chí như đã đăng ký**, không phải PASS. Kèm biên (a): @100 chỉ
   0,711 vs ngưỡng 0,70 (**+1,1 %**); mức seed: 0/8 · 5/8 · 6/8 seed PASS (50/100/130).
5. **Frame/seed phải ghi là 120/66/51** (50/100/130), không được viết "120 frame" cho cả ba.
