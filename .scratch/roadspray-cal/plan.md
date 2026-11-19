# Kế hoạch phát triển — spray augmentation cho 3DOD trên BEVFusion LiDAR-only

Lập ngày **2026-11-18** · nhánh `sspp` @ `064f1c1` · thay cho 5 bước của
`.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md` (bước 1–2 giữ nguyên, bước 3–5 thay bằng §2 dưới).

Nguồn: 7 tài liệu trong `docs/reference/roadspray-fit-for-repo.md`, `.scratch/roadspray-fit/*.md`,
`.scratch/roadspray-cal/{spec,power-design,detector-choice,pseudo-boxes}.md`.
Quyết định kiến trúc: `docs/adr/0006-detection-protocol-and-calibration-source.md`.

Nhãn số: `[ĐO]` đo trên máy này · `[PAPER]` paper nói · `[CHỌN]` tự chọn · `[TÍNH]` suy từ công thức.

---

## 0. Mục tiêu và phạm vi

**Câu hỏi (không đổi):** train BEVFusion LiDAR-only trên frame đã bỏ điểm spray, chèn thêm plume
tổng hợp lúc train có **giảm FP trên spray thật** không, và có **mất recall** không?

**Deliverable cuối:** một claim về **3DOD** (AP/recall/FP) trên BEVFusion LiDAR-only, có **effect size
+ CI95**, trên một protocol **không leak** và có **đủ đơn vị test**.

**Cái kế hoạch này KHÔNG làm** (đã cân nhắc và loại, lý do ghi trong tài liệu nguồn):

| Không làm | Vì sao |
|---|---|
| Train trên STF | Paper A dùng STF vì **họ không có dataset spray có nhãn**; repo có. STF đổi câu hỏi và tốn ~2–3 tuần (`.scratch/roadspray-cal/spec.md` Phụ lục A) |
| Train trên nuScenes | Nhánh `main` đã chạy hướng này → **null**; và nuScenes không có trên máy (ADR-0005) |
| Đổi sang framework mới (OpenPCDet) | `pointpillars.yaml` đã có sẵn trong pin; OpenPCDet +2–4 ngày và không giải quyết gì thêm |
| Mua thêm dataset | Không cần: thiếu **box** (dựng được từ nhãn) và thiếu **đơn vị test** (chia lại được) |

---

## 1. Chẩn đoán — bốn vấn đề, đã đo

| # | Vấn đề | Số `[ĐO]` | Hệ quả |
|---|---|---|---|
| **V1** | Test quá ít đơn vị | 12 scene / 954 frame; scene-level CV 0,483; **CI95 half-width 28,4 %** ≈ effect 30 % đang nhắm | **Không thể** tuyên bố "giảm ≥ 30 %"; effect 30 % có CI [2 %; 58 %] |
| **V2** | Calibration leak | **6/12 test scene là `cal`** = 503/954 frame (52,7 %); bỏ scene test khỏi `cal` vẫn còn **28 scene `cal` ở đúng 3 tốc độ test** | Tham số plume được chọn trên chính điều kiện sẽ chấm |
| **V3** | Generator chưa đúng | 3 lỗi quy ước box **đã sửa** (`3a971b8`); lỗi **4× số cụm sống chưa sửa**; wet ground đang sửa dở; đuôi phân bố điểm/cụm chưa khớp (sinh max ~91 vs thật 982–1 238 điểm) | Mọi phép đo sau đang đo bug của generator, không đo câu hỏi khoa học |
| **V4** | Criterion nhị phân | "point ≥ 30 % **và** CI loại trừ 0" ⇒ power **~50 %** ngay cả khi effect thật đúng 30 %, với mọi n | Fail vì may mắn xui, không phải vì augment vô dụng |

**Cái gì đã có sẵn để sửa** (không phải mua):

- **V1** → 3-fold leave-speed-out trên 36 scene, pooled **n = 36** ⇒ CI half-width **15,7 %** `[ĐO]`.
- **V2** → calibration từ **RoadSpray `*_static`** (333 recording, ego đỗ) — file đã có
  `~/Downloads/Crafter_static (1).zip` (7 924 255 130 byte, 163 bag, khớp release) `[ĐO]`.
- **V3** → danh sách sửa đã có thứ tự trong `docs/measurements/plume-root-cause.md` §"Thứ tự sửa đề xuất".
- **V4** → thay criterion bằng **effect size + CI95** (§4).

---

## 2. Sáu giai đoạn

### Giai đoạn A — Sửa generator (0 GPU · 2–3 ngày)

| | Việc | File | Xong khi |
|---|---|---|---|
| A1 ✅ | Sửa lỗi **4× ngân sách cụm**: `alive = rate × 4T/Δt = 4 × visible`. Chọn một hướng: `rate = visible/(4T/Δt)` **hoặc** thinning xác suất trong `prune()` | `spray/plume.py:214-231`, `spray/plume_state.py:417-440` | Test mới: chạy 120 frame, `alive_measured / visible_table` ∈ **[0,9; 1,1]** ở 60/100/120 km/h |
| A2 ✅ | Commit + test **wet ground** đang sửa dở (diff 340 dòng chưa commit) | `spray/wet_ground.py`, `spray/config/wet_ground_default.yaml`, `tests/test_wet_ground*.py` | Test khẳng định `mean_ratio < 1` (giảm cường độ), và `points_in` / `attenuated` / `boosted` được log |
| A3 ⚠️ | Đuôi phân bố điểm/cụm: `P_det`, bán kính, phân bố điểm/cụm | `spray/plume.py` (`_POINTS_MEDIAN_BY_RANGE`, `cluster_radius_*`), `spray/raycast.py` | Cụm lớn nhất sinh ra ≥ **500 điểm** (thật: 982–1 238) |
| A4 | Test tích hợp bắt được lỗi kiểu "unit test dùng box tâm còn adapter ghi box đáy" | `tests/` | Test mới dùng **box đúng quy ước adapter** (9 cột, `box[2]` = đáy) |

### A3 — phát hiện sau A1 (đo 2026-11-18): mục tiêu đang mâu thuẫn, cần quyết

Đo lại sau A1 (100 km/h, steady state, scene `Crafter_dynamic/0060`):

| Đại lượng | Sinh (sau A1) | Thật (SSPP `label==2`) | Paper A |
|---|---:|---:|---|
| cụm/frame | **29,1** ✓ | 28,5 | 18–30 (Fig. 4) |
| điểm/cụm (median) | 5–6 | 5–8 | — |
| điểm/cụm (mean) | ~5 | **37–78** | ~17–28 (suy từ Fig. 4 + Fig. 11a) |
| tổng điểm/frame | **140** | 1.050–2.220 | ~200–500 (Fig. 11a, trục tới 500) |
| phân bố cự ly p50 | 7,3 m ✓ | 7,5 m | — |
| share < 10 m | 62 % | 73 % | — |

Hai kết luận:

1. **A1 làm khớp cụm/frame và cự ly** — hai thứ paper thật sự calibrate. Nhưng nó làm
   điểm/frame tụt 4× (4× = đúng lỗi cũ), nên khoảng cách điểm tăng lên 8–16× so với `label==2`.
2. **Mục tiêu `label==2` không dùng được làm đích**: `label==2` gồm cả nhiễu không phải spray
   (`semantic-spray-stats.md`), và nó cho 1.050–2.220 điểm/frame — gấp 2–4× con số paper đo
   (~200–500). So với đích paper, generator đang thấp **~2–3×**, không phải 16×.

**Quyết định (chốt 2026-11-18, sau khi đo đuôi phân bố): T2, nhưng cài theo CẤU TRÚC chứ không
phóng to cụm.** Đo trên 207 scene SSPP, gộp theo fold (không leak), xem
`docs/measurements/sspp-cluster-size-distribution.md`:

| km/h | điểm/cụm p50 | mean [CI95] | p95 | max | **% điểm trong cụm ≥50 điểm** |
|---:|---:|---|---:|---:|---:|
| 50 | 6 | 8,8 [7,6; 10,3] | 17 | 144 | **15 %** |
| 70 | 5 | 15,9 [13,1; 19,5] | 54 | 732 | **56 %** |
| 100 | 6 | 40,4 [32,2; 47,9] | 182 | 2241 | **82 %** |
| 130 | 6 | 45,3 [38,7; 50,8] | 158 | 2485 | **83 %** |

Ba điều làm quyết định này khác hẳn bảng T1/T2/T3 cũ:

1. **Phân bố hai đỉnh.** `điểm/cụm p50 = 5–7` ở **mọi** tốc độ (gần hằng số), nhưng `mean` tăng
   8,8 → 47,7 vì tỉ lệ điểm trong cụm ≥50 điểm tăng 15 % → 85 %. Plume thật = **nhiều cụm nhỏ + một
   ít chuỗi khổng lồ**, không phải một họng lognormal.
2. **Generator đang đúng ở phần nhỏ, thiếu phần chuỗi.** Đo lại 2026-11-19 bằng **cùng toán tử**
   (`scripts/measure_plume_size_tail.py`, DBSCAN góc trên điểm spray sinh ra): `điểm/cụm` p50 = 7–8
   vs thật 6 (khớp); nhưng share điểm trong cụm ≥50 đ = **29,6 / 50,0 / 23,8 %** ở 50/100/130 km/h
   so với thật **15 / 82 / 83 %**, p95 = 55/84/48 vs thật 17/182/158, max = 160/190/109 vs thật
   144/2241/2485.
   *(Sửa lại ghi chú cũ "share 0 %": con số 0 % là đo trên cụm *sinh ra* trước ray-cast, không phải
   trên điểm sinh ra — không cùng đại lượng với dữ liệu thật.)*

   **Lỗi lớn nhất không phải hình dạng đuôi mà là khối lượng không scale theo tốc độ:** thật
   43 → 875 điểm/frame (20×) khi 50 → 100 km/h; generator 134 → 323 (2,4×). Ở 50 km/h generator
   **thừa 3×**, ở 100–130 km/h **thiếu 2,7–4,2×**.
3. **T1 và T2 chỉ lệch nhau hệ số 2**, không phải mâu thuẫn: T1 (~200–500 detection/frame) và T2
   (600–900 điểm/frame) **cùng đòi thêm chuỗi**. Chọn T2 vì đó là khối lượng detector gặp lúc eval,
   và `điểm/cụm` có **CI95 ±5–10 %** (bảng cụm chỉ ±30–40 %).

**Giả thuyết cơ chế cần kiểm ở A3 (0 GPU):** chuỗi sinh ra khi các cụm nhỏ **chồng nhau trong không
gian góc**. `define_spray_volumes()` của paper rải cụm trong vùng dài `|v|·Δt` (≈2,8 m @100 km/h) nên
mật độ cao; nếu port đang rải trên vùng **dài hơn** thì mật độ thấp và **không có chồng** ⇒ không
chuỗi. Kiểm: so mật độ cụm/thể tích giữa sinh và thật trước khi thêm cơ chế mới.

**Tiêu chí xong của A3 (thay tiêu chí cũ "cụm lớn nhất ≥ 500 điểm"):**
`% điểm trong cụm ≥50 đ` lệch **≤ 10 điểm %** so với bảng trên, `p95 điểm/cụm` trong **[0,5×; 2×]**
thật, **`điểm/frame` trong [0,7×; 1,5×] thật ở cả 3 tốc độ**, và `cụm/frame` không đổi (đang khớp).
Đo bằng `scripts/measure_plume_size_tail.py` (`python scripts/measure_plume_size_tail.py` → PASS/FAIL).
Không cần đổi `_CLUSTER_VISIBLE_BY_SPEED`.

**Chốt chặn A:** `pytest -q tests/` xanh **và** A1 + A2 có test mới. Không đạt thì **không** sang B.

> **Trạng thái 2026-11-18:** A1 ✅ (`8cc9207`, cụm sống/frame 11,9/29,5/17,5 vs bảng
> 11,3/29,2/17,6; test `tests/test_plume_cluster_budget.py`) · A2 ✅ (`f9c8b44`, wet ground
> chỉ giảm cường độ; `mean_ratio` 0,597/0,194/0,033 ở wfh 0,5/1,0/1,2 mm; test
> `tests/test_wet_ground_hahner.py`). `183 passed`. Còn A3 (đuôi phân bố) và A4 (test
> tích hợp box convention) trước khi sang B.

> Ghi chú: hiện `178 passed` `[ĐO]` **không** chứng minh generator đúng — lỗi `box_bottom` từng lọt
> qua vì test dùng box kiểu tâm. Đó là lý do A4.

---

### Giai đoạn B — Đo generator ↔ spray thật (0 GPU · 2–3 ngày)

Mục tiêu: chứng minh generator khớp thống kê spray thật **trước khi** hỏi detector có thấy nó không.

| | Việc | Xong khi |
|---|---|---|
| B1 | Bảng **sinh vs thật** theo 9 tốc độ: điểm/frame, cụm/frame, điểm/cụm (median + p95 + max) | Tỉ lệ sinh/thật ∈ **[0,7; 1,5]** ở mọi mốc tốc độ |
| B2 | Đuôi phân bố: max cụm, p95 điểm/cụm | Max cụm sinh ≥ **500 điểm**; p95 trong cùng bậc thật |
| B3 | Vị trí: phân bố `x` (dọc) và `z` trên mặt đường so với thật | `z` p50 ≥ 0 (không chui xuống đường); `x` p50 lệch < **2 m** so với thật |

**Chốt chặn B:** nếu sau A vẫn lệch > 2× → **dừng**, quay lại A. Không sang C.

---

### Giai đoạn C — Đo generator ↔ detector (0 GPU · 1 ngày)

Mục tiêu: trả lời *"plume có làm detector báo nhầm không?"* — **độc lập với** việc generator đúng hay sai.

| | Việc | Xong khi |
|---|---|---|
| C1 | Dựng **inference harness** cho Model 0 trên SSPP (`scripts/sspp_infer.py` hoặc tương đương) | Chạy được 954 frame test, ra FP/frame tại τ, log thời gian/frame |
| C2 | Ba phép đo tại **cùng τ, cùng frame**: (a) frame sạch, (b) sạch **+ plume tổng hợp**, (c) spray thật | Bảng 3 dòng: FP/frame **và** recall **và** số điểm plume chèn vào (% frame) |
| C3 | Đọc kết quả | Ghi rõ 3 khả năng: plume vô hình / plume yếu / plume tương đương thật |

**Chốt chặn C (quan trọng nhất):** nếu (b) **không** tăng FP trong khi (c) tăng mạnh → plume **vô hình**
với detector ⇒ **dừng toàn bộ hướng train**, quay lại A. Đây là cửa duy nhất chặn việc đốt 10–17 h GPU.

> Lưu ý khi generator còn bug: chỉ **tin chiều "CÓ"**. Chiều "KHÔNG" chưa kết luận được vì có thể
> do bug chứ không phải do vô hình. Vì vậy C chạy **sau** A/B, và chạy lại sau mỗi lần sửa generator.

---

### Giai đoạn D — Calibration độc lập từ RoadSpray `*_static` (0 GPU · 2–3 ngày)

| | Việc | File | Xong khi |
|---|---|---|---|
| D1 | Ingest `Crafter_static` (163 bag, ~12 058 frame) — chỉ velodyne, 5×f32, áp extrinsic | `spray/roadspray_adapter.py` (mới), `scripts/build_roadspray_static.py` (mới) | `ROADSPRAY_OK scenes=163 frames≈12058`; 2 bag kiểm chéo số frame; 1 frame dynamic biến đổi khớp SSPP ≤ 1e-5 m |
| D2 | Metadata: `meta_data_measurement.xlsx` (549 dòng) vào `data/roadspray/` | — | Đọc được `object_velocity`, `itr_after_water`, `measurement_itr` cho 162/163 bag |
| D3 | Đo theo §III-B với **hai đại lượng tách riêng**: `clusters_visible` (thay bảng `plume.py:21-47`) và `clusters_per_scan` (đối chiếu Fig. 4) | `scripts/measure_roadspray_cal.py` (mới) | Bảng 9 tốc độ × 3 mức nước, có sd giữa 3 lần lặp |
| D4 | Kiểm tracker + độ nhạy vùng lọc | cùng script | Tracker lệch ≤ 5 km/h ở ≥ 90 % recording; độ nhạy 2·L vs 3·L **< 20 %** |

**Chốt chặn D:** nếu độ nhạy vùng > 20 % → chưa dùng được RoadSpray làm cal; fallback: giữ cal SSPP
nhưng eval chỉ trên **18 held-out scene** (§3 của ADR).

---

### Giai đoạn E — Protocol + mở rộng data train (0 GPU · 3–4 ngày)

| | Việc | File | Xong khi |
|---|---|---|---|
| E1 | **3-fold leave-speed-out**, rule tất định `fold = rank(speed) mod 3 + 1` | `scripts/build_sspp_split.py`, `data/sspp_split.json` | fold1 {50,80,110} 12 test/886 f · fold2 {60,90,120} 12/893 · fold3 {70,100,130} 12/808; mỗi scene test **đúng 1 lần**; `train ∩ test = ∅` mỗi fold |
| E2 | Tách `cal` khỏi SSPP + assertion cứng | `spray/semantic_split.py` | Assert `cal ∩ SSPP = ∅`; nếu `calibration_source != "sspp_cal"` thì bảng SSPP không được đọc (fail fast) |
| E3 | Nguồn cal ghi vào config + checkpoint metadata | `spray/plume.py` (`PlumeConfig.calibration_source`) | Cả hai nguồn chọn được; báo cáo ghi nguồn |
| E4 | **Pseudo-box** cho 171 scene thiếu box, chỉ dùng train | `scripts/build_sspp_pseudo_boxes.py` (mới), từ `.scratch/roadspray-cal/tmp/pseudo/` | Chạy lại ra **BEV IoU p50 = 0,931**, 3D p50 = 0,872, 99,8 % frame ≥ 0,7 trên 36 scene có box; gate `purity ≥ 0,7` & `n_primary ≥ 50` |

**Chốt chặn E:** pooled out-of-fold n = 36 ⇒ CI half-width **≈ 16 %** (đo lại bằng bootstrap). Nếu
không đạt, kiểm lại E1 trước khi train.

**Quy mô data sau E:** train 16 scene/1 124 frame → **92 scene/~7 180 frame (6,4×)** `[ĐO]`;
test/val **giữ nguyên human box** (12/8 scene). Pseudo scene là `itr_after_water` 2–6, eval là 1.

---

### Giai đoạn F — Train (5–27 h GPU · 1–2 tuần)

| | Việc | Xong khi |
|---|---|---|
| F0 | Khôi phục harness Kaggle từ lịch sử `main` (`c2aa23c` xoá 5 kernel; `e2e/main.py`, `train/ab_run.py`, `ab_eval.py`) | Kernel chạy được 1 step, log `SSPP_STEP` |
| F1 | Dry-run 100 step để **đo s/step thật** (mọi estimate hiện tại là `[ƯT]`) | Có số s/step; nếu lệch > 2× so với ước lượng thì tính lại matrix |
| F2 | **Pilot**: 1 fold × 2 arm (detector nhẹ, `pointpillars.yaml` + crop `[0,64]×[−16,16] m`) | Có A vs B trên 1 fold; pipeline augment chạy đúng; ~2–3,5 h |
| F3 | **Matrix**: 3 fold × 2 arm × 2 seed | Báo cáo theo §4 |
| F4 | **Claim cuối trên BEVFusion LiDAR-only**: 3 fold × 2 arm × 1–2 seed | Effect size + CI95 cho BEVFusion |

**Ngân sách `[CHỌN]` — chờ chốt:** phương án B = light pilot + BEVFusion, **15–27 h GPU**
(6–17 h light + 5–10 h BEVFusion). Phương án A (chỉ BEVFusion) = 5–10 h nhưng **không có seed variance**.

**Cảnh báo kỹ thuật F** (chi tiết: `.scratch/roadspray-cal/detector-choice.md`):

1. `with_velocity: false` bắt buộc — `box_dim = 9` đã có vx,vy; không tắt → 11 chiều.
2. `test_cfg.dataset: nuScenes` → `IndexError` **mỗi step** khi `num_classes = 2`.
3. `test_cfg.grid_size` kế thừa 1024² trong khi train 512² → `bev_pos` sai **mà không crash**; phải assert shape.
4. `pointpillars.yaml` **chưa từng được chạy** → smoke 20 step (~20–25 phút GPU) trước khi mua matrix.

---

## 3. Bảng tổng hợp

| GĐ | Việc | GPU | Ngày | Chốt chặn |
|---|---|---:|---:|---|
| A | Sửa generator | 0 | 2–3 | test A1/A2/A4 xanh |
| B | Sinh vs thật | 0 | 2–3 | lệch ≤ 1,5× |
| C | Plume vs detector | 0 | 1 | (b) tăng FP |
| D | Cal từ RoadSpray | 0 | 2–3 | độ nhạy vùng < 20 % |
| E | CV + pseudo-box | 0 | 3–4 | CI half-width ≈ 16 % |
| F | Train | 5–27 h | 1–2 tuần | theo §4 |

**Tổng trước khi cần GPU: ~10–14 ngày công, 0 GPU-giờ.** Sau đó mới tới F.

---

## 4. Thống kê: pre-registration (chốt **trước** khi chạy F)

Ghi vào đây trước, không sửa sau khi thấy số:

| Hạng mục | Giá trị |
|---|---|
| **Primary metric** | SPF proxy/frame, **paired theo scene**, pooled out-of-fold **n = 36** |
| Effect size | `expm1(mean(log(FP_B(s)/FP_A(s))))` — chênh tương đối trung bình |
| CI95 | percentile bootstrap **theo scene**, B = 20 000, phân vị 2,5 / 97,5 |
| Secondary | tổng FP/frame; recall (phải ≥ A − 0,02); AP@0,5 |
| Robustness | per-fold (3 giá trị), seed spread |
| Direction-only | per-speed 50 và 130 km/h (n = 4 scene/tốc độ — **không** dùng để kết luận) |
| **Ngưỡng claim** | chỉ viết "giảm ≥ X %" khi **cận dưới CI ≥ X** |

Mẫu báo cáo: `giảm 40 %, CI95 [−52 %, −26 %]` — **không** báo "pass/fail".

Vì sao: `docs/PROJECT.md` §5 (đã sửa) và `docs/adr/0006-...` — criterion nhị phân có power ~50 %
ở đúng effect 30 %, với mọi n.

---

## 5. Quyết định cần ký

| # | Quyết định | Trạng thái |
|---|---|---|
| Q1 | Criterion: **effect size + CI95**, bỏ pass/fail nhị phân | ✅ chốt (ADR-0006) |
| Q2 | Ngân sách F: **phương án B** (light pilot + BEVFusion, 15–27 h) | ✅ **chốt 2026-11-18** |
| Q3 | Pseudo-box: dùng cho train, **giữ một cặp A/B human-only** làm đối chứng | ✅ chốt (ADR-0006) |
| Q4 | Không train trên STF/nuScenes; nuScenes chỉ làm clean control (~5 GB) | ✅ chốt (ADR-0006) |

---

## 6. Hạ tầng còn thiếu (không nằm trong 7 tài liệu, dễ tốn hơn A–E)

| Thiếu | Ảnh hưởng | Cách xử |
|---|---|---|
| Harness Kaggle | Không train được | Khôi phục từ `main`: `e2e/main.py`, `train/ab_run.py`, `ab_eval.py` (F0) |
| Nơi chạy eval 2 587 frame | Máy nhà i5/8 GB, **không GPU** | Đo thời gian/frame ở C1; nếu quá chậm thì eval trên Kaggle CPU |
| Đĩa | Còn **26 GiB** `[ĐO]` | Xoá `data/SemanticSprayDataset.tar` (15,7 GB, đã giải nén) khi cần; output static ~7,4 GB |
| `Golf_static.zip` | Chưa có (nếu muốn bảng theo lớp xe cho D3) | Chưa cần: paper chỉ định lượng Crafter (Fig. 4/5/7) |
| Clean control | `nuScenes` **không có trên máy** | ~5 GB nuScenes-mini val, hoặc hoãn tới sau F |

---

## 7. Điều kiện dừng

| Dừng khi | Nghĩa là |
|---|---|
| C: plume không tăng FP dù đã xác nhận plume hiện diện | Can thiệp vô hiệu → sửa generator hoặc đổi generator |
| B: sau A vẫn lệch > 2× | Port chưa đúng → đọc lại paper, không train |
| F: cận dưới CI < 0 | Không kết luận được; báo cáo trung thực là "không phát hiện tác dụng" |

**Kết quả âm vẫn là kết quả hợp lệ** nếu CI đủ hẹp. Kết quả dương với CI chứa 0 **không** là kết quả.
