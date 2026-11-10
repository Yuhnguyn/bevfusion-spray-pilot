# Spec v1 — Spray plume augmentation cho BEVFusion (MIT)

> ⚠️ **LỊCH SỬ — không còn hiệu lực.** Spec đang dùng là `../spec-v2-paper-faithful.md`.
> File này mô tả generator **v1** (không state, không ray casting, không wet-ground) và được giữ
> để truy vết quyết định ban đầu. Nhiều mục đã bị thay: xem `docs/history/plume-v1-defects.md`
> và `docs/PROJECT.md` §4–§5.

Version: 1.5
Status: ready-for-agent — preconditions 1–6 **PASS** 2026-11-05/07 (ticket 06 adapter + ticket 07 transform done)

> Status flips to `ready-for-agent` only after the preconditions below pass.
> Changes this round: model forward patch made explicit; plume placement uses velocity direction; velocity frame marked for verification; plume generator reduced to a v1-minimal form; evidence-ladder stages gated behind a positive mini signal; tensor-hash test replaced.
> v1.3: thêm arm tham chiếu B0 (lọc spray rồi detect, ticket 14); ghi ADR-0001..0003; sửa citation RA-L 2023; bỏ paper totals khỏi vai trò anchor thống kê.
> v1.4: thêm `## Related work & positioning` (Piroli 2023, Linnhoff 2022) — nêu rõ 4 claim hẹp, 4 non-claim, và 3 rủi ro effect size; bỏ ngầm hiểu "chưa ai đo augmentation cho spray".
> v1.5: viết lại `### Plume injection` theo đúng `spray/plume.py` đã hiệu chỉnh (bỏ công thức `n = round(k·speed)` cũ); thêm `## Interface contract` (file, class, key, điểm đăng ký, forward patch, signature adapter); thêm `## Definition of done theo ticket` (test name cụ thể); chốt arm B0 (ROR, tham số pre-registered); chốt generator thứ hai (định nghĩa + điều kiện mở, không làm ở v1); nêu rõ precondition 2 đã pass.

## Problem Statement

Nhóm cần biết liệu augmentation **spray plume** có cải thiện khả năng phát hiện của BEVFusion (MIT) khi xe phía trước tạo plume trên đường ướt hay không, trước khi giao full training cho đội khác. Đây là bài toán cải thiện năng lực phát hiện dưới spray plume, không phải robustness dưới lỗi cảm biến. Hiện tại **chưa có phép đo nào**: chưa có training loop cho MIT, chưa có bộ sinh spray, chưa có evaluator cho MIT, và không có spray thật của nuScenes. Harness và kết quả cũ dựa trên BEVFusion của OpenMMLab không phải bằng chứng và nằm ngoài phạm vi. Compute chỉ có Kaggle T4.

Repo MIT ở HEAD có khác biệt so với bản release ở đường depth của camera branch. Điều này **chưa được xác minh là tương thích** với checkpoint fused chính thức. Spec yêu cầu smoke test trước khi đầu tư vào transform.

Đây là một câu hỏi **replication mở rộng**, không phải câu hỏi mở hoàn toàn: phần "spray có hại" và "augment spray có giúp detector LiDAR" đã có kết quả công bố. Xem `## Related work & positioning` ngay dưới.

## Related work & positioning

Hai bài dưới đây là nền của pilot. Không bài nào trả lời câu hỏi của mình, nhưng bỏ qua chúng thì spec sẽ claim novelty sai.

**Piroli et al., "Energy-based Detection of Adverse Weather Effects in LiDAR Data"** (RA-L 2023, arXiv 2305.16129) — SemanticSpray + AWNet.
- Giải: phân loại **point-wise** inlier/outlier, reframe thành outlier detection bằng energy score. **Không** đo object detector nào, **không** đề xuất augmentation.
- Cấp cho plan: (a) thống kê spray thật để calibrate generator (dense cluster median 17 điểm, 144 điểm/frame, intensity ≈ 0); (b) bằng chứng cơ chế: spray là **cụm dày** nên filter thống kê hỏng (DROR/DSOR precision 50–52% trên spray, AWNet 87,5%) — đây là lý do augmentation có chỗ đứng và lý do plume phải sinh cluster; (c) baseline "lọc rồi detect" + cảnh báo sim→real (Fog-sim → spray: AUPR 70,52 dù AUROC 96,29).

**Linnhoff et al., "Simulating Road Spray Effects in Automotive Lidar Sensor Models"** (arXiv 2212.08558) — model + augmentation.
- Giải: mô hình **hình học** plume (cluster dọc quỹ đạo, ray casting, xác suất detection, attenuation), calibrate trên test track, rồi dùng chính nó để augment và **đo detector**.
- Cấp cho plan: (a) tham số đã calibrate (spray bắt đầu **50 km/h**; bán kính cluster lognormal μ=−1,2 σ=0,8; P_det median ≈ 0,10; attenuation hiệu dụng **0,04 m⁻¹**; intensity 0); (b) bằng chứng augment có tác dụng: PV-RCNN **+17,39 AP** trên spray thật, clear weather không mất gì (58,90 vs 58,23); (c) ba kết quả phụ: DROR **−5,52 AP**, fog-sim **−14,65 AP**, Voxel-RCNN **+0,62 AP** (gần bằng 0); (d) code augmentation open source.

**Đã được công bố, pilot KHÔNG claim:**
- Spray làm detector sinh misdetection và ghost object (Walz et al. ITSC 2021, được cả hai bài trích).
- Spray là cụm dày → filter thống kê không đủ (Piroli, Bảng III).
- Augment bằng model spray đầy đủ cải thiện detector LiDAR trên spray thật (Linnhoff, Bảng II).
- Mô phỏng sai hiện tượng thì có hại, không chỉ vô ích (fog-sim: −14,65 AP; Fog→spray AUPR 70,52).

**Pilot claim (4 điểm, đều hẹp):**
1. **Fusion thay vì LiDAR-only**: cả hai bài chỉ LiDAR. Spray tác động hai modality khác nhau; chưa ai đo trên kiến trúc camera+LiDAR.
2. **`points_clean` tách luồng**: camera branch nhận điểm trước khi inject, LiDAR branch nhận điểm sau inject — biến "augmentation" thành một biến duy nhất tác động đúng một nhánh. Không paper nào bàn.
3. **10 class nuScenes** thay vì chỉ vehicle trên highway.
4. **Paired A/B trên cùng frame + split theo scene + bootstrap theo scene**: Linnhoff train hai lần độc lập (không paired), Piroli split scan-level (không nói chia theo scene).

**Non-claims (ghi trong mọi report):**
- Không kết luận về wet-ground, attenuation, occlusion, camera-side splash (ADR-0002).
- v1 plume-only là **tập con** của model đã được Linnhoff chứng minh. Gain nhỏ hơn 17 AP **không** được diễn giải là "augmentation không hiệu quả", chỉ là "plume-only không đủ".
- Kết quả dương trên plume tổng hợp **không** chứng minh giúp được spray thật; camera branch trong thí nghiệm vẫn sạch lý tưởng, nên mọi kết quả dương là **cận trên lạc quan**.

**Rủi ro effect size (ghi trước, không phải biện minh sau):**

| rủi ro | bằng chứng | hệ quả |
|---|---|---|
| Plume synthetic dễ hơn thật (cluster đặc, không attenuation) | P_det thật median 0,10; generator inject 100% | gain có thể là artefact của generator |
| Effect size ≈ 0 | spray chỉ chiếm 0,25–0,5% điểm/scan; Voxel-RCNN +0,62 AP | mục tiêu là **đo được delta**, không phải chứng minh hiệu quả |
| 1 seed, Kaggle T4 | compute | chỉ kết luận directional |

## Solution

Dùng một **plume injection rút gọn** (không phải port trung thành của simulator Linnhoff) để chèn plume lên nuScenes, chạy thí nghiệm paired A/B (clean-only vs spray-aug) trên cùng frame, với tham số spray **held-out** khi đánh giá. Giai đoạn đầu chỉ có plume, không wet-ground, không attenuation. Kèm theo: so thống kê simulator với spray thật, phân tích độ nhạy tham số, và cross-generator check. Kết quả là báo cáo + recipe để đội khác full train.

Thêm một **arm tham chiếu B0** (không train): lọc spray bằng filter thống kê rồi chạy model của arm A. Không có B0 thì kết quả âm không phân biệt được "augmentation không giúp" với "chưa thử cách rẻ hơn" (ticket 14).

## Preconditions (phải pass trước khi implement)

1. **Version**: dùng commit release `da93b27`, hoặc HEAD với `add_depth_features: false` và `height_expand: false`. Ghi lại commit và flags trong config snapshot. Không trộn hai hành vi.
2. **Smoke test một sample**: config + checkpoint load được; liệt kê missing/unexpected keys; forward một sample cho output hữu hạn; tensor depth có đúng số channel mà `dtransform` nhận. Pass nghĩa là không có lỗi shape và không có missing key ảnh hưởng trọng số.
3. **Checkpoint**: cả hai arm khởi tạo từ cùng một checkpoint fused chính thức. Đường dẫn và hash được ghi trong report.
4. **Dataset gate**: xác minh mirror Kaggle có đủ `samples/CAM_*`, `samples/LIDAR_TOP`, metadata; tạo được infos; load được một sample; license được ghi lại. Nếu thiếu metadata hoặc converter lỗi, dừng và báo.
5. **Evaluator**: một frame MIT chạy qua evaluator mới, so với GT của chính frame đó, và cho kết quả kiểm tra được bằng tay. Không dùng kết quả cũ của OpenMMLab làm chuẩn.
6. **Velocity contract**: xác minh velocity của box nằm ở frame nào (ego hay global) từ loader MIT, và velocity của box `ObjectPaste` có hợp lệ hay phải fallback; ghi lại trước khi bật plume.

## User Stories

1. As an ML engineer, I want the codebase pinned to a verified version, so that results are not invalidated by depth-flag differences.
2. As an ML engineer, I want a smoke test with explicit pass criteria, so that shape and checkpoint issues stop the work early.
3. As an ML engineer, I want a spray transform enabled per experiment, so that I can turn augmentation on/off without editing code.
4. As an ML engineer, I want the transform to place plumes using final boxes, so that pasted or augmented objects do not overlap the plume.
5. As an ML engineer, I want plumes generated in the same frame as the points handed to the model, so that `lidar_aug_matrix` inverse-projection stays correct.
6. As an ML engineer, I want clean points captured immediately before injection, so that both streams share one frame.
7. As an ML engineer, I want the camera branch to receive clean points for its point-derived sparse depth input, so that injected points do not distort camera features.
8. As an ML engineer, I want the LiDAR branch to receive augmented points, so that the encoder can learn to suppress plume returns.
9. As an ML engineer, I want `points_clean` formatted and collected like `points`, so that the model contract is explicit.
10. As an ML engineer, I want the generator to clamp to the point-cloud range and drop points inside GT boxes, so that plume points never corrupt labels.
11. As an ML engineer, I want a hard cap on injected points per frame, so that `max_voxels` is not silently exhausted.
12. As an ML engineer, I want spray intensity drawn from the low tail of the real nuScenes intensity distribution, so that returns stay in-distribution.
13. As an ML engineer, I want injection deterministic per sample and seed, so that evaluation is reproducible.
14. As an ML engineer, I want an eval mode with fixed spray parameters, so that arm A and arm B see identical corruption.
15. As an ML engineer, I want spray parameters held out by severity and seed, so that the measured gain is not memorization.
16. As an ML engineer, I want plume-only and wet-ground separated, so that each component's effect can be attributed.
17. As an ML engineer, I want to skip plume placement when no eligible lead vehicle exists, so that frames without spray are not silently corrupted.
18. As an ML engineer, I want velocity read from the documented box features with a zero/unknown fallback, so that placement does not crash.
19. As an ML engineer, I want eligible-frame counts before and after `ObjectPaste`, so that I know how many frames can receive a plume.
20. As an ML engineer, I want the training config to state its sweep policy explicitly, so that train/eval density is not confused.
21. As an ML engineer, I want both arms trained with the same checkpoint, split, freeze list, optimizer, seed, data order, batch size, and update count, so that the only difference is spray.
22. As an ML engineer, I want a memory/time probe before training, so that I do not commit to an OOM configuration.
23. As an ML engineer, I want a scene-level train/val split, so that no scene leaks between training and evaluation.
24. As an ML engineer, I want paired deltas with scene-clustered bootstrap intervals, so that correlated frames do not produce falsely narrow intervals.
25. As an ML engineer, I want precision and unmatched-prediction counts at a fixed score threshold, so that the plume-as-vehicle failure mode is measured directly.
26. As an ML engineer, I want recall reported by range bucket, so that far-range degradation is visible.
27. As an ML engineer, I want a second independent generator for evaluation, so that I can check cross-generator generalization.
28. As an ML engineer, I want simulator statistics compared with published curves and real spray, so that the simulator is not obviously wrong.
29. As an ML engineer, I want a parameter sensitivity sweep, so that conclusions depending on uncertain parameters are flagged.
30. As a reviewer, I want a pre-registered protocol and falsification criteria, so that negative results are reported honestly.
31. As a team lead, I want a handoff recipe, so that the other team can run full training.
32. As a maintainer, I want spray code isolated from the reference clone, so that upstream comparisons stay clean.
33. As an operator, I want augmentation to be train-time only, so that inference latency is unchanged.

## Implementation Decisions

### Version and model contract

- Pin the MIT codebase to the release commit, or run HEAD with `add_depth_features: false` and `height_expand: false`. Record commit and flags.
- The camera branch consumes a **point-derived sparse depth input**. The standard transform does not use the `GTDepth` pipeline output or a depth loss.
- Add `points_clean` to formatting and collection explicitly; `DefaultFormatBundle3D` only wraps `points` and `radar`.
- Patch the fusion model forward so the camera branch consumes `points_clean` and the LiDAR branch consumes `points`. Without this patch, the camera path still receives augmented points.
- Both arms start from the same checkpoint; record path, hash, and load report.

### Pipeline placement

Thứ tự **bắt buộc** trong chain của MIT (sai thứ tự → kết quả vô nghĩa, dù code chạy không lỗi):

```
LoadPointsFromFile → ... → GlobalRotScaleTrans → RandomFlip3D
  → PlumeTransform → PointShuffle → DefaultFormatBundle3D → collect
```

- **Vì sao sau `GlobalRotScaleTrans` + `RandomFlip3D`:** velocity của box trong `nuscenes_infos_*.pkl` đã ở
  LiDAR frame của keyframe hiện tại — chuỗi `nusc.box_velocity()` → `nuscenes_converter.py:264–268` →
  `nuscenes_dataset.py:305–309` (cột 7:9) → `lidar_box3d.py:152–154` [CODE]. Plume sinh sau bước xoay/flip thì
  plume và điểm thật cùng một frame; sinh trước thì plume trôi khỏi vị trí hình học của nó.
- **Vì sao trước `PointShuffle`:** shuffle chỉ đổi thứ tự, không đổi toạ độ; đặt sau shuffle cũng đúng về toán
  nhưng làm test "plume nằm ở cuối mảng" mất ý nghĩa. Chọn trước để kiểm tra được.
- **`points_clean` chụp ngay tại thời điểm chèn**, cùng frame với `points`, không đi qua bất kỳ bước nào khác.
- **Anchor code:** transform đăng ký trong `PIPELINES` tại `mmdet3d/datasets/pipelines/transforms_3d.py`;
  `DefaultFormatBundle3D` trong `mmdet3d/datasets/pipelines/formating.py` chỉ wrap `points` và `radar` →
  phải thêm `points_clean` tường minh.
- **Velocity của box `ObjectPaste`:** box dán từ scene nguồn mang velocity của scene đó → set về 0 khi paste,
  để plume không sinh ra từ box giả (đã ghi trong `docs/reference/velocity-contract.md`).

### Plume injection — contract theo `spray/plume.py` (đã hiệu chỉnh)

**Nguồn sự thật duy nhất là `spray/plume.py` (289 dòng, 29 test).** Spec này mô tả contract; nếu code và spec
lệch nhau, code đúng và spec phải sửa. Đã bỏ hoàn toàn công thức cũ `n = round(k · speed_kmh)` và clip `[1, 6]`.

**API (đã có, dùng nguyên, không viết lại):**

```python
inject_plume(points, boxes, *, seed, token="", config=None) -> PlumeResult
# points: (N, >=4) float32 hoặc (N,5); boxes: (M, >=9) -> x,y,z,dx,dy,dz,yaw,vx,vy
# PlumeResult: .points (N+K,5) | .points_clean (N,5) | .injected (K,5) | .stats (PlumeStats)
cluster_count_for_speed(speed_kmh, config=None) -> int   # 0 nếu dưới ngưỡng
```

**Tham số v1 và nguồn:**

| Tham số | Giá trị | Nguồn |
|---|---|---|
| `min_speed_kmh` | 50,0 | Linnhoff §III-A — spray bắt đầu ở 50 km/h [PAPER] |
| `speed_epsilon_kmh` | 1e-3 | bug float32: `float32(30/3.6)*3.6 = 29,999999` < 30 → phải có epsilon [CODE] |
| số cụm theo tốc độ | tuyến tính 2 @ 50 km/h → 8 @ 130 km/h, 0 dưới 50 | hai đầu là [CHỌN], chọn để khớp dense clusters/frame median 5 đo trên SemanticSpray [ĐO] |
| `points_per_cluster_median` | 17,0 (sigma 0,67, bounds 3–200) | cluster size median 17 đo trên SemanticSpray [ĐO] |
| `cluster_radius_median_m` | 0,30 (sigma 0,8, bounds 0,10–1,50) | Linnhoff Fig. 5, lognormal μ=−1,2 σ=0,8 [PAPER] |
| `distance_range_m` | 1,0–10,0 sau box | [CHỌN] |
| `height_range_m` | 0,2–2,0 | [CHỌN] |
| `lateral_sigma_m` | 0,5 | [CHỌN] |
| `box_margin_m` | 0,2 (nới box trước khi loại điểm) | [CHỌN] |
| `max_injected_points` | 2000 / frame | [CHỌN] — tránh làm cạn `max_voxels` |
| `intensity` | 0,0 | 81,95% điểm spray thật có intensity = 0 [ĐO] |
| `time_lag` | 0,0 | [CHỌN] |

**Thuật toán (theo code, không phải theo ý định):**

1. Với mỗi box: bỏ nếu toạ độ không hữu hạn, hoặc tâm ngoài `point_cloud_range`.
2. Bỏ nếu thiếu velocity (mảng box < 9 cột, hoặc `vx/vy` không hữu hạn, hoặc speed ≈ 0) → `skipped_no_velocity`.
3. Tính `speed_kmh = hypot(vx, vy) · 3,6`. Nếu `< 50 − ε` → bỏ (`skipped_low_speed`).
4. `n_clusters = cluster_count_for_speed(speed_kmh)`; hướng plume = **ngược** vector velocity, chuẩn hoá; phương
   vuông góc dùng cho lệch ngang.
5. Mỗi cụm: khoảng cách đều `[1,10]` m theo hướng ngược velocity, lệch ngang `N(0; 0,5)` m, độ cao đều
   `[0,2; 2,0]` m. Bán kính và số điểm rút từ lognormal có clip.
6. Điểm trong cụm phân bố đều trong hình cầu bán kính đó; kênh `[x, y, z, intensity, time_lag]`.
7. Loại điểm ngoài `point_cloud_range` (`rejected_range`) và điểm nằm trong GT box đã nới 0,2 m (`rejected_box`).
8. Nếu vượt 2000 điểm → subsample không hoàn lại, giữ thứ tự (`capped`).
9. Determinism: `rng` dựng từ `seed` + hash(`token`) → cùng sample + seed cho cùng kết quả.
10. Log đủ: `eligible_boxes`, `skipped_no_velocity`, `skipped_low_speed`, `clusters`, `injected`,
    `rejected_range`, `rejected_box`, `capped`.

**Số kiểm chứng được (dùng làm assert trong test):** 49,9 km/h → 0 điểm; 50 → 2 cụm ≈ 76 điểm (0,22% của
34.720); 80 → 4 cụm ≈ 99 điểm; 130 → 8 cụm ≈ 174 điểm (0,50%) [ĐO].

**Không làm ở v1** (thuộc v2, xem `ADR-0002`): attenuation hiệu dụng **0,04 m⁻¹**, occlusion (thay return yếu), wet-ground,
ray casting theo từng tia, `P_det` lognormal per-beam, decay T = 0,5–1,5 s. Hệ quả phải nêu trong mọi kết luận:
v1 chỉ **cộng** điểm lạ, không **lấy đi** điểm thật.

### A/B training equivalence

Both arms must share and log: checkpoint path/hash, train/val scene split, freeze list, optimizer and scheduler, LR, batch size, number of updates/epochs, seed, data order, and eval frame list. Any difference other than the spray transform invalidates the comparison.

### Evaluation

- Evaluation for MIT is new code. Class order comes from the MIT dataset definitions. Boxes are converted explicitly; the conversion rule is frozen in the evaluator and tested.
- Matching rule: one rule per class, frozen before training. Use BEV IoU@0.5 for vehicle classes and centre-distance thresholds for small classes; document the thresholds.
- FP: predictions above the fixed score threshold (default 0.05) that remain unmatched after greedy matching per class.
- Range: evaluate within the configured BEV range; report outside-range GT separately and exclude it from mAP.
- Sweep policy: identical for A and B within a pair; never compare absolute numbers across different sweep policies.
- **Success criteria (pre-registered)**:
  - Clean retention: `mAP_clean(B) >= 0.9 * mAP_clean(A)`.
  - Gap reduction: `G_A - G_B >= 0.5 * G_A`, where `G_X = mAP_clean(X) - mAP_spray(X)`.
  - Require `G_A` to be positive and above the noise floor; otherwise report "no measurable gap".
  - FP direction: unmatched-prediction count on held-out spray is lower for B, with scene-clustered intervals.
- **Reference arm B0** (filter-then-detect, không train): báo cùng bộ metric trên cùng frame list.
  B không vượt B0 thì kết luận phải nêu rõ augmentation không hơn được filter thống kê, không được
  viết "spray augmentation không hiệu quả" (ticket 14).
- Noise floor: half-width of the scene-clustered interval for `G_A`. With one training seed, results are directional only.
- Intervals are bootstrapped by **scene**, not by frame.

### Evidence ladder

1. Mini A/B directional signal — đây là kết quả bắt buộc duy nhất của v1.
2. Nếu mini A/B dương và trên noise floor, mới chạy larger subset A/B.
3. Chỉ sau (2): cross-generator check.
4. Chỉ sau (2): parameter sensitivity sweep và so thống kê với paper/spray thật.
5. Future, không thuộc v1: LiDAR-only real-spray anchor.
6. Future, không thuộc v1: fleet data.

### Environment

- Python 3.8, torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0, CUDA ops built by the repo setup; idempotent build script.
- Kaggle: 12-hour sessions, ~30 GPU-hours/week, 2×T4 16 GB, ~20 GB working disk.
- If the pinned environment cannot be built, stop and report; do not silently switch codebases or versions.

## Interface contract

Mọi tên dưới đây là **hợp đồng**, không phải gợi ý. Đổi tên = đổi spec.

| # | Thành phần | File | Symbol / key | Ghi chú |
|---|---|---|---|---|
| 1 | Transform chèn plume | `spray/plume_transform.py` (mới) | class `PlumeTransform`, `@PIPELINES.register_module()` | input dict: `points` (N,5 float32), `gt_bboxes_3d` (`LiDARInstance3DBoxes`), `metadata` (có `token`, `seed`). output: `points` (N+K,5), `points_clean` (N,5), `spray_stats` (dict) |
| 2 | Sinh plume (đã có) | `spray/plume.py` | `inject_plume`, `cluster_count_for_speed`, `PlumeConfig` | transform chỉ **gọi**, không chép lại thuật toán |
| 3 | Formatting | `mmdet3d/datasets/pipelines/formating.py` | `DefaultFormatBundle3D` | thêm `points_clean` vào danh sách wrap y như `points`; kết quả `img_metas[i]['points_clean']` là list tensor |
| 4 | Forward patch | `mmdet3d/models/fusion_models/bevfusion.py:169–180` | `BEVFusion.forward` | camera branch đọc `kwargs.get('points_clean', kwargs['points'])`; LiDAR branch giữ `kwargs['points']`. Chỉ sửa đúng các dòng này |
| 5 | Adapter evaluator | `proxy_eval/mit_adapter.py` (mới) | `to_eval_format(detections, class_names) -> list[dict]`, `load_gt_from_infos(info, class_names)` | mỗi phần tử: `{'boxes': (M,7) [x,y,z,dx,dy,dz,yaw], 'scores': (M,), 'labels': (M,)}`; thứ tự class lấy từ MIT dataset |
| 6 | Lọc B0 | `spray/denoise.py` (mới) | `ror_filter(points, k=8, r=0.5) -> (keep_mask, stats)` | numpy, không thêm dependency |
| 7 | Config | `configs/spray/*.yaml` | `arm: A\|B\|B0`, `spray: {enabled, min_speed_kmh, seed}` | 3 file, khác nhau **chỉ** ở `spray.enabled` và filter |
| 8 | Thống kê | `spray/spray_stats.py` | `main()` | chạy trên SemanticSpray, xuất bảng so với simulator |

## Arm B0 — filter-then-detect (pre-registered)

- **Không train.** Dùng checkpoint của arm A, eval trên cùng frame list có plume.
- Filter: **Radius Outlier Removal**, `k = 8` láng giềng, bán kính `0,5 m` [CHỌN], chạy trên `points` sau khi chèn
  plume, trước `DefaultFormatBundle3D`, **chỉ ở eval**.
- Tham số chốt trước khi xem kết quả, không tune trên eval set. Nếu tune, phải báo là tuned và chạy lại arm B.
- Báo cáo: % điểm giữ lại, ms/frame, mAP, FP. So trực tiếp với B.
- Kỳ vọng có sẵn: DROR trong Linnhoff làm AP **−5,5** (52,45 vs 57,97) [PAPER] → ROR nhẹ hơn nhưng vẫn có thể
  âm. **B0 âm là kết quả hợp lệ**, không phải lỗi cần sửa.

## Second generator — định nghĩa, mở có điều kiện

- **Định nghĩa:** implementation độc lập theo cơ chế Linnhoff — ray-cast theo từng tia, `P_det` lognormal
  (median 0,10), attenuation hiệu dụng **0,04 m⁻¹**, decay 0,5–1,5 s. Không dùng lại `plume.py`, không share RNG.
- **Điều kiện mở:** chỉ sau khi G3 đạt (mini A/B dương và trên noise floor) — evidence ladder bước 3. Không code
  trước, không tạo ticket trước.
- **Lý do:** cross-generator check chỉ có nghĩa khi đã có tín hiệu để kiểm. Làm trước là đốt thời gian.

## Definition of done theo ticket

| Ticket | Xong khi | Test (pytest) |
|---|---|---|
| 06 adapter | 1 frame MIT đi qua adapter, box/scores/labels đúng thứ tự class, roundtrip không mất box | `test_mit_adapter.py::test_box_format_roundtrip`, `::test_class_order_matches_mit` |
| 07 transform | chèn plume vào `points`, `points_clean` = input nguyên vẹn; cùng seed → cùng kết quả | `test_plume_transform.py::test_points_clean_equals_input`, `::test_injected_count_matches_stats`, `::test_deterministic_same_seed`, `::test_no_point_inside_gt_box`, `::test_below_threshold_no_injection` |
| 08 routing | camera branch nhận `points_clean`, LiDAR branch nhận `points` (kiểm bằng marker, không bằng hash) | `test_routing.py::test_camera_branch_receives_clean_points`, `::test_lidar_branch_receives_augmented_points` |
| 09 e2e | 3 arm A/B/B0 chạy hết pipeline trên 1 sample; tắt spray thì `points_clean` == `points` | `test_pipeline_e2e.py::test_three_arms_run_end_to_end`, `::test_disabled_spray_leaves_points_unchanged` |
| 10 config | 3 config tồn tại, khác nhau chỉ ở spray/filter | `test_config_arms.py::test_arms_differ_only_in_spray` |
| 11 run | `results/<run>/report.md` có bảng A/B/B0 + CI theo scene + noise floor | kiểm bằng mắt, PM duyệt |
| 14 B0 | lọc bỏ điểm cô lập, giữ cấu trúc dày; thời gian/frame được ghi | `test_denoise.py::test_ror_removes_isolated_points`, `::test_ror_keeps_dense_structures` |
| 02b | `report.json` 6/6 true + version đã Save trên Kaggle | `--` (đọc artifact) |
| 04 | forward 1 sample thật chạy được, `real_infos_available: true`, có bảng đếm | `--` (đọc artifact) |

## Testing Decisions

- Test external behavior only: points land in the intended region, both streams describe the same frame, intensities stay in range, injection is deterministic, the model receives the right tensor on the right branch.
- **Pipeline end-to-end test** (primary seam): run a real config through the transform chain up to collection with a recording stub model; assert both streams exist, share the same frame, and that disabling spray leaves `points_clean` absent or equal to `points`.
- **Same-frame assertion**: with a known point, apply the inverse `lidar_aug_matrix` and assert the coordinate is recovered as expected; this proves clean and augmented points share one frame.
- **Model routing test**: assert the camera path receives `points_clean` and the LiDAR path receives `points` by shape and a distinct marker value, not by float hashes.
- **Plume invariants**: no injected point inside a GT box; no point outside range; injected count within cap; same seed produces identical output.
- **Evaluator test**: synthetic boxes with known IoU and known matches, plus one real MIT output frame inspected manually.
- No test suite exists in the repo; new tests are plain pytest and run on a laptop CPU.
- Do not use the old OpenMMLab harness as a reference result.

## Out of Scope

- Camera-side spray (lens droplets, direct splash).
- Wet-ground in v1.
- Attenuation, occlusion, removal of real returns.
- Generator thứ hai (ray-cast, cơ chế Linnhoff) — chỉ mở sau khi G3 đạt; xem `## Second generator`.
- Full nuScenes training.
- Architecture changes to fusion.
- Temporal misalignment.
- Using SemanticSpray for BEVFusion training/evaluation. Lý do và số đo: ADR-0003. Tóm tắt: 1 box/frame, 36/207 scene, 1 camera trước, 100% frame có spray nên không có counterfactual.
- Claims about real-world effectiveness.

## Further Notes

- nuScenes is CC BY-NC-SA; the Kaggle mirror has an "Unknown" license. Internal R&D only; verify structure and record provenance.
- SemanticSpray (~16 GB sau giải nén; 31 GB trên đĩa vì giữ cả tar) chỉ dùng để so thống kê simulator
  và làm point-wise sanity check. Không dùng tổng số điểm của paper làm anchor: tổng trong paper lệch
  80–150 lần so với bản release, xem `docs/measurements/semantic-spray-stats.md`. Citation đúng: Piroli et al.,
  RA-L 2023, vol. 8, no. 7, pp. 4322–4329, DOI 10.1109/LRA.2023.3282382.
- ADR đã ghi: `docs/adr/0001` (pin MIT commit), `0002` (plume-only-first), `0003` (SemanticSpray chỉ
  để hiệu chỉnh thống kê, không train/eval detection).
- Velocity provenance: box features carry velocity for real boxes; pasted boxes come from the database sampler and must be verified. Confirm the velocity coordinate frame (ego vs global) from the loader before use, and report counts of eligible boxes with valid velocity.
- Eligibility đo trên val (34,029 frame, 2026-11-05): ngưỡng 50 km/h + front ≤30 m chỉ có **697 frame (2.0%)**; 30 km/h có 4,690 (13.8%). Ba scene subset đầu có 0 frame ≥50 km/h. Phải chọn scene highway hoặc hạ ngưỡng trước ticket 07/10/11.
- Sweep policy differs by config: detection training uses 0 sweeps; evaluation may use 9 on mini and 0 on the keyframes-only subset. Do not compare absolute numbers across those sets.
- If HEAD is used instead of the release commit, re-verify checkpoint loading and the depth tensor shape before any experiment.
