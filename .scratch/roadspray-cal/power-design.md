# Power analysis + leave-speed-out CV cho SSPP 36 scene

Ngày 2026-11-18 · nhánh `sspp` · đo trên **36 scene có box** (2.587 frame) trong
`data/SemanticSprayDataset/*/*/object_labels/`. Không sửa file tracked nào.
Script + raw output: `.scratch/roadspray-cal/tmp/{measure.py,analysis.py,extras.py}`,
`{frame_stats.json,analysis.json,folds.json,analysis.out,extras.out}`.

## 0. TL;DR — con số để chốt tranh luận

- **Scene-level CV** (đơn vị = scene mean, không phải frame): clusters/frame **0,483**, noise points/frame **0,761**
  trên 36 scene (sau khi trừ nhiễu 10-frame: **0,378 / 0,691**). Trong-scene frame-to-frame CV **0,81 / 0,84** →
  trung bình 80 frame/scene chỉ kéo SE của scene mean xuống ~0,1; phần CV 0,38–0,69 **không** giảm theo frame,
  chỉ giảm theo `1/√n_scene`.
- **CI95 half-width** (scene-level bootstrap, đơn vị = fraction of mean): n=12 → **28,4 %** (clusters) /
  **44,5 %** (noise); n=36 → **15,7 % / 24,1 %**; 6 scene → **37 % / 59 %**. Cùng bậc với effect 30 % đang nhắm.
- **30 % có detectable ở n=12 không?** Với clusters/frame: **không** — half-width 28 % ≈ 95 % của effect (kể cả bản
  lạc quan đã trừ nhiễu 10-frame là 21 %, vẫn bằng 71 % của effect); CI95 của effect 30 % là **[2 %, 58 %]** nên
  30 % không phân biệt được với 2 % hay 58 %; nếu true effect đúng 30 %, xác suất **pass criterion đầy đủ chỉ ~50 %**.
  Với noise/frame: **càng không** — CI của effect 30 % là **[−14 %, 74 %]**, chứa 0. Cần **≈13–24 scene** (clusters,
  tùy dùng CV_b hay CV của test 12) và **≈42–59 scene** (noise) mới đủ 80 % power. **n=36 thì đủ**: CI của effect
  30 % ≈ **[14 %, 46 %]**, power pass ~50 % ở đúng 30 % nhưng 94 % ở 40 %.
- **Split hiện tại không defensible như evidence**: 12 scene + **6/12 scene cal = 503/954 frame (52,7 %) là calibration
  leak** + test lệch (spray thấp hơn 21 %, 65 % frame ở tốc độ extrapolated). Đề xuất: **3-fold leave-speed-out trên
  toàn bộ 36 scene** (mỗi fold 24 train / 12 test, pool out-of-fold → **n=36**), và **bắt buộc** move calibration ra
  RoadSpray `*_static` thì CV mới leakage-free.

## 1. Đo spray signal thật trên 36 scene

Sample: **10 frame cách đều/scene** (`np.linspace(0, nf-1, 10)`, gồm frame đầu & cuối) = **360/2.587 frame (13,9 %)**,
chạy 1 process, **55 s**, RAM ~1 GB nên an toàn trên máy 8 GB. Không đụng hết dataset.

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python .scratch/roadspray-cal/tmp/measure.py
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python .scratch/roadspray-cal/tmp/analysis.py
```

Mỗi frame: `n_noise = #{label==2}`, `n_clusters` = số cụm ≥0 của `spray.semantic_stats.cluster_angular`
(DBSCAN `(azimuth, elevation)`, eps 0,7°, minPts 3 — **tái dùng code repo, không viết lại**). Sanity: sampled p50
noise/frame theo tốc độ khớp bảng `docs/PROJECT.md` trong ~10–20 % ở 7/9 tốc độ (50→70 vs 73; 60→200 vs 208;
90→532 vs 503; 130→570 vs 630); 120 km/h lệch (512 vs 728) vì 10 frame/scene không bắt đủ đuôi burst.

| tốc độ | scene | frame | clusters/frame | noise points/frame |
|---:|---:|---:|---:|---:|
| 50 | 4 | 374 | 6,10 | 77 |
| 60 | 4 | 319 | 9,50 | 204 |
| 70 | 4 | 304 | 15,53 | 412 |
| 80 | 4 | 307 | 17,05 | 577 |
| 90 | 4 | 332 | 18,30 | 675 |
| 100 | 4 | 256 | 22,43 | 1.089 |
| 110 | 4 | 205 | 26,20 | 1.248 |
| 120 | 4 | 242 | 19,35 | 879 |
| 130 | 4 | 248 | 16,77 | 882 |

**Scene-to-scene vs frame-to-frame** (per-scene mean từ 10 frame; full per-scene list ở `analysis.json`):

| quantity | n | mean | sd | min | max | CV across scene | CV within scene (median) |
|---|---:|---:|---:|---:|---:|---:|---:|
| clusters/frame, all 36 | 36 | 16,80 | 8,11 | 4,90 | 35,30 | **0,483** | 0,81 |
| clusters/frame, test 12 hiện tại | 12 | 13,72 | 7,23 | 4,90 | 29,10 | **0,527** | — |
| noise/frame, all 36 | 36 | 671,5 | 510,9 | 53 | 1.889 | **0,761** | 0,84 |
| noise/frame, test 12 hiện tại | 12 | 544,7 | 449,0 | 53 | 1.281 | **0,824** | — |

Extremes: clusters/frame min **4,90** (`Crafter_dynamic/0006`, 50 km/h/30 m), max **35,30**
(`Crafter_dynamic/0078`, 110/30); noise/frame min **53** (cùng scene 50/30), max **1.889** (`Crafter_dynamic/0072`, 110/20).
Phần lớn spread là **tốc độ** (6,1 → 26,2 clusters/frame từ 50 → 110 km/h) chứ không phải group/distance.
Frame-to-frame CV lớn hơn between-scene CV (0,81 vs 0,48) — frame rất bursty — nhưng bursty thì trung bình hoá
được theo số frame, còn offset theo scene thì không: vì vậy CI co theo `n_scene` (ICC 0,14/0,32), không theo `n_frame`.

Variance decomposition trên frame: **ICC = 0,137** (clusters), **0,321** (noise); design effect **2,2 / 3,9** →
360 frame đã sample chỉ tương đương **161 / 93** đơn vị độc lập. Đây là lý do bootstrap phải ở **scene level**;
frame-level bootstrap sẽ báo CI hẹp hơn thực tế ~1,5–2×.

## 2. Bootstrap power — 12 scene giải quyết được effect bao nhiêu?

Scene-level percentile bootstrap (B=20.000, resample scene), đơn vị = fraction of mean; effect 30 % giả định
**paired, proportional trên cùng scene** (nếu effect không proportional, cộng thêm model/seed noise → CI thực
**rộng hơn** các số dưới đây, nên đây là optimistic floor):

| n scene | nguồn | CI95 half-width clusters | CI95 half-width noise | CI95 của effect 30 % (clusters / noise) |
|---:|---|---:|---:|---|
| 6 | random 6-of-36 (median [p5,p95]) | 0,371 [0,205; 0,538] | 0,585 [0,344; 0,864] | [−7; 67] / [−29; 89] % |
| 12 | **test 12 hiện tại** | **0,284** | **0,445** | **[2; 58] / [−14; 74] %** |
| 12 | random 12-of-36 (median) | 0,271 | 0,426 | — |
| 36 | **toàn bộ 36 scene** | **0,157** | **0,241** | **[14; 46] / [6; 54] %** |

Refinement: per-scene mean ở đây chỉ từ 10 frame; lúc eval thật mỗi scene ~80 frame nên within-scene term gần 0,
half-width co còn ~0,21–0,25 / 0,40–0,42 (n=12) và ~0,13 / 0,23 (n=36) — **kết luận không đổi**.
CV estimate cũng bất định: bootstrap CI của CV ở n=12 là [0,31; 0,69] (clusters), [0,48; 1,20] (noise).

**Số scene cần cho effect 30 % @ 80 % power (leg "CI excludes 0")**: clusters **≈13 scene** nếu dùng `CV_b`=0,378
(đã trừ nhiễu 10-frame, tương đương lúc eval mỗi scene ~80 frame) nhưng **≈24 scene** theo CV bootstrap của test 12 hiện
tại (0,527); noise **≈42–59 scene**. Ở n=12, xác suất pass criterion đầy đủ ở true 30 % là ~50 % (clusters) / ~32 % (noise).

**Xác suất pass toàn bộ criterion** (point estimate ≥30 % **và** CI95 loại trừ 0), normal model trên `CV_b`:

| true effect | n=6 | n=12 | n=36 |
|---:|---:|---:|---:|
| 30 % clusters / noise | 0,49 / 0,18 | **0,50 / 0,32** | **0,50 / 0,50** |
| 35 % clusters / noise | 0,62 / 0,24 | 0,68 / 0,42 | 0,79 / 0,67 |
| 40 % clusters / noise | 0,74 / 0,29 | 0,82 / 0,52 | 0,94 / 0,81 |

Chú ý: criterion đòi **point estimate ≥30 %** nên ở đúng true 30 % xác suất pass bị chặn trần ~50 % **với mọi n**
(không phải lỗi của 12 scene); n=36 giúp phần "CI excludes 0" và giúp pass 90 %+ khi effect thật ≥40 %.
**Kết luận thẳng: ở 12 scene, một effect 30 % không phân biệt được với effect 2 % hay 58 %; không thể dùng 12 scene
để tuyên bố "giảm ≥30 %".**

## 3. Split hiện tại có 4 vấn đề, không chỉ "ít scene"

1. **n=12 quá nhỏ** so với effect size (mục 2).
2. **Calibration leak**: tái lập bằng `spray.semantic_split.assign_roles` — 6/12 test scene là `cal`,
   **503/954 frame test (52,7 %)** đã được dùng chọn tham số plume generator. Con số này khớp
   `docs/reference/roadspray-fit-for-repo.md:169`; đây là lỗi protocol, không phải chuyện sample size.
3. **Test không đại diện**: frame-weighted noise/frame test = **470** vs all 36 = **595** (ratio 0,79) → test là
   draw spray thấp. Trong 954 frame test, **622 frame (65 %) ở tốc độ extrapolated** (50, 130) và **332 frame (35 %)
   ở 90 km/h interpolated** (train có 80/100) — trộn hai chế độ generalization vào một average 12 scene.
4. **CV của test 12 (0,527) cao hơn median random 12-of-36 (0,478)** — bộ test này là một draw bất lợi.

Train 16 scene / 1.124 frame cũng nhỏ, nhưng **fix gần như miễn phí**: 3-fold CV cho **24 scene / 1.701 frame/fold**
(1,5× train) trong khi vẫn test đủ 36 scene.

### Đề xuất: 3-fold leave-speed-out trên 36 scene

Rule tất định, không RNG, tái tạo được: sort 9 tốc độ 50…130, **`fold = rank(speed) mod 3 + 1`**. Mỗi fold test
= 3 tốc độ × 2 group × 2 distance = **12 scene**; cell nào cũng có đúng 1 boxed scene nên không cần bốc tay.

| fold | tốc độ held out | test scene | test frame | train scene | train frame | cal trong test |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 50, 80, 110 | 12 | 886 | 24 | 1.701 | 6/12 (473 frame) |
| 2 | 60, 90, 120 | 12 | 893 | 24 | 1.694 | 6/12 (463 frame) |
| 3 | 70, 100, 130 | 12 | 808 | 24 | 1.779 | 6/12 (385 frame) |

Full scene list 36 scene: `.scratch/roadspray-cal/tmp/folds.json`. Verification (in trong `analysis.out` §5):

```
fold 1: |test|=12 |train|=24 overlap=NONE speeds_disjoint=True
fold 2: |test|=12 |train|=24 overlap=NONE speeds_disjoint=True
fold 3: |test|=12 |train|=24 overlap=NONE speeds_disjoint=True
all_test_total=36 unique=36 tested_exactly_once=True covers_all_36=True
FOLD_VERIFICATION=PASS
```

- Mỗi fold test có 4 scene/tốc độ; fold 1 test spray 634 noise/frame, fold 2 = 586, fold 3 = 794 → không hoàn hảo
  nhưng chấp nhận được; per-fold CV clusters 0,644 / 0,446 / 0,365 → per-fold CI half-width ~36 / 25 / 21 %.
- **Phân tích chính phải là pooled out-of-fold**: mỗi scene được test đúng 1 lần bởi model không thấy nó →
  paired difference A−B trên 36 đơn vị scene, **n=36**; per-fold chỉ là robustness, per-speed (50 & 130) chỉ là
  **direction check** (n=4 scene/tốc độ, không đủ significance).
- 9-fold leave-one-speed-out (4 scene/fold) không đáng: gấp 3 lần train, pooled n vẫn 36, per-fold vô dụng hơn.
- Không cần val riêng: step/lr cố định (2.000), τ chọn trên clean frame nuScenes → fold-independent.

## 4. Calibration và tính leakage-free

Đo được: trong 36 boxed scene có **18 cal / 18 held-out**, đúng **2 cal + 2 held-out mỗi tốc độ**. Vì fold chia
theo tốc độ, **fold nào cũng có 6/12 test scene là cal** (bảng trên). Không tồn tại partition theo tốc độ nào
trên cả 36 scene mà cal ∉ test — trừ khi bỏ hẳn cal khỏi test. Vậy:

- **CV trên cả 36 scene BẮT BUỘC external calibration** (RoadSpray `*_static`, `docs/reference/roadspray-fit-for-repo.md`)
  để leakage-free. Lý do đúng: khi cal nằm ngoài SSPP, 18 cal scene trở thành scene thường → dùng được cả 36,
  `cal ∩ test = cal ∩ train = ∅` theo nghĩa generator không fit trên bất kỳ scene nào trong 36.
- **Fallback nếu chưa có external calibration**: chỉ eval trên **18 held-out scene** (3 fold × 6 test scene:
  413 / 430 / 423 frame; train 30 scene: 2.174 / 2.157 / 2.164 frame; `cal-in-test=0`). Khi đó eval không leak,
  nhưng toàn bộ 18 cal scene nằm trong train → generator fit trên training data (in-sample training exposure,
  không phải eval leak). Pooled **n=18** → half-width clusters ≈ **0,18**; per-fold n=6 → ~0,31.
  Cách này dùng được nhưng **yếu hơn** và không trả lời được "generator có generalize ngoài SSPP không".
- Nếu giữ nguyên calibration trên SSPP và test 12 scene cal như hiện tại: **không có thiết kế thống kê nào cứu được**,
  vì evaluator đã thấy scene trước khi chọn tham số.

## 5. Budget Kaggle (30 h GPU/week, 2×T4; giả định **1 T4/run**)

Repo **chưa có** số đo wall-clock/run → 2 giả định phải verify bằng dry-run 100 step trước khi chốt:
light detector from-scratch ~**20 min/run**; BEVFusion LiDAR-only fine-tune (2.000 step, batch 2) ~**50 min/run**.
Mỗi kernel push tốn ~11 min build env → **gộp tất cả run vào 1 kernel** (Kaggle notebook ≤12 h), đừng push từng run.

| config | matrix | runs | wall (1×T4) | % 30 h/tuần | claim được / không claim được |
|---|---|---:|---:|---:|---|
| light from-scratch | 3 folds × 3 arms (A, B-ssppcal, B-extcal) × 2 seeds | 18 | 6,0 h | 20 % | **được**: fold-to-fold stability, seed noise, so 3 calibration nguồn; **không**: kết luận về BEVFusion |
| light from-scratch | × 3 seeds | 27 | 9,0 h | 30 % | thêm được seed variance chắc hơn |
| **BEVFusion fine-tune (khuyến nghị)** | **3 folds × 2 arms (A, B) × 2 seeds** | **12** | **10,0 h** | **33 %** | **được**: pooled effect n=36 + seed variance + per-fold robustness; **không**: per-speed significance (4 scene), per-fold significance (hw 21–36 %) |
| BEVFusion | × 3 seeds | 18 | 15,0 h | 50 % | thêm seed, vẫn không mua được per-speed |
| BEVFusion baseline | current split × 2 arms × 3 seeds | 6 | 5,0 h | 17 % | chỉ để chứng minh lại 12-scene test không kết luận được |

Model 0 = inference only (2.587 frame, ~5 min), fold-independent. 1 seed **không** tách được seed noise khỏi effect
→ tối thiểu 2 seed; báo cáo cả hai, dùng seed 0 làm primary và seed spread làm uncertainty.

## 6. Khuyến nghị — thẳng

1. **Current 16/12 split: defensible như pilot, KHÔNG defensible như evidence.** Kể cả bỏ qua chuyện 16 train scene,
   test 12 scene hiện tại vừa **leak 52,7 % frame cal** vừa có CI ≈ effect size; một reviewer sẽ reject claim
   "giảm ≥30 %". Train ít là vấn đề nhỏ hơn — nó chỉ làm model yếu, không làm kết luận sai; test ít + leak làm kết luận sai.
2. **Thay đổi một thứ, leverage cao nhất: bỏ single split, dùng 3-fold leave-speed-out trên 36 scene, pooled out-of-fold
   analysis ở scene level → n=36.** Miễn phí về data (1,5× train/fold), 3× đơn vị test, vẫn giữ claim "tốc độ test
   không có trong train", và nằm trong budget 10 h/tuần. 3 fold × 2 arms × 2 seeds = 12 run BEVFusion.
3. **Move calibration ra RoadSpray external là điều kiện để (2) leakage-free.** Nếu external chưa xong: chạy fallback
   held-out-only (n=18) và ghi rõ limitation; đừng lấy test 12 scene hiện tại làm primary.
4. **Pre-register trước khi chạy**: primary = pooled paired bootstrap n=36 với CI95; per-fold = robustness;
   per-speed 50/130 = direction-only. Và lưu ý criterion hiện tại (point ≥30 % **và** CI>0) chỉ có ~50 % power ở đúng
   30 % kể cả n=36 — nên báo cáo CI + effect size thay vì binary "pass/fail", hoặc chấp nhận rằng cần true effect ~37–40 %
   để có 80 % power.
