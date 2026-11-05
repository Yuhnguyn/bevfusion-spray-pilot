# Spec — Spray plume augmentation cho BEVFusion (MIT)

Version: 1.3
Status: needs-triage

> Status flips to `ready-for-agent` only after the preconditions below pass.
> Changes this round: model forward patch made explicit; plume placement uses velocity direction; velocity frame marked for verification; plume generator reduced to a v1-minimal form; evidence-ladder stages gated behind a positive mini signal; tensor-hash test replaced.
> v1.3: thêm arm tham chiếu B0 (lọc spray rồi detect, ticket 14); ghi ADR-0001..0003; sửa citation RA-L 2023; bỏ paper totals khỏi vai trò anchor thống kê.

## Problem Statement

Nhóm cần biết liệu augmentation **spray plume** có cải thiện khả năng phát hiện của BEVFusion (MIT) khi xe phía trước tạo plume trên đường ướt hay không, trước khi giao full training cho đội khác. Đây là bài toán cải thiện năng lực phát hiện dưới spray plume, không phải robustness dưới lỗi cảm biến. Hiện tại **chưa có phép đo nào**: chưa có training loop cho MIT, chưa có bộ sinh spray, chưa có evaluator cho MIT, và không có spray thật của nuScenes. Harness và kết quả cũ dựa trên BEVFusion của OpenMMLab không phải bằng chứng và nằm ngoài phạm vi. Compute chỉ có Kaggle T4.

Repo MIT ở HEAD có khác biệt so với bản release ở đường depth của camera branch. Điều này **chưa được xác minh là tương thích** với checkpoint fused chính thức. Spec yêu cầu smoke test trước khi đầu tư vào transform.

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

- Spray is inserted **after geometric augmentation and range filtering, before `PointShuffle`**.
- Rationale: the model inverse-projects all points with `lidar_aug_matrix`; points generated in the post-augmentation frame follow the same path as real points. Capturing clean points at the same point keeps both streams in one frame.
- The generator clamps to the point-cloud range and drops points inside GT boxes.
- `PointShuffle` reorders only the augmented cloud; clean points keep their order, which is irrelevant to depth projection.

### Plume injection (v1-minimal generator)

Mục tiêu v1 chỉ là tạo tín hiệu directional, không tái tạo động học spray. Generator tối thiểu:

Inputs: augmented points, final GT boxes, point-cloud range, sample token, config seed, mode.

1. **Candidates**: vehicle classes. Box centre trong range; dùng final boxes sau `ObjectPaste`.
2. **Direction**: hướng ngược chiều velocity. Nếu velocity thiếu, không hữu hạn, hoặc dưới ngưỡng, bỏ qua box và log lý do; không đặt plume khi không có speed. Velocity frame phải được xác minh trước khi dùng.
3. **Cluster count**: `n = round(k * speed_kmh)` với `k` là hằng số config, clip `[1, max_clusters_per_box]`.
4. **Placement**: mỗi cluster đặt sau box theo direction, khoảng cách đều trong `[1, 10]` m, z đều trong `[0.2, 2.0]` m, lateral offset nhỏ.
5. **Shape**: mỗi cluster là một số điểm ngẫu nhiên trong hình cầu, count và radius đơn giản; không dùng tham số hiệu chỉnh của paper ở v1.
6. **Intensity**: low percentile của nuScenes thật; default 0 khi chưa đo.
7. **Channels**: `[x, y, z, intensity, 0]`; time lag 0.
8. **Rejection**: bỏ điểm ngoài range hoặc trong GT box inflated 0.2 m; log tỉ lệ bị bỏ.
9. **Cap**: `max_injected_points` (default 2000) mỗi frame; deterministic subsample nếu vượt.
10. **Logging**: eligible boxes, clusters, injected points, reject reasons.

Không làm ở v1: attenuation, occlusion, xóa điểm thật, wet-ground, temporal history, ray casting, và toàn bộ tham số hiệu chỉnh của paper. Những thứ này thuộc v2.

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
- Full nuScenes training.
- Architecture changes to fusion.
- Temporal misalignment.
- Using SemanticSpray for BEVFusion training/evaluation. Lý do và số đo: ADR-0003. Tóm tắt: 1 box/frame, 36/207 scene, 1 camera trước, 100% frame có spray nên không có counterfactual.
- Claims about real-world effectiveness.

## Further Notes

- nuScenes is CC BY-NC-SA; the Kaggle mirror has an "Unknown" license. Internal R&D only; verify structure and record provenance.
- SemanticSpray (~16 GB sau giải nén; 31 GB trên đĩa vì giữ cả tar) chỉ dùng để so thống kê simulator
  và làm point-wise sanity check. Không dùng tổng số điểm của paper làm anchor: tổng trong paper lệch
  80–150 lần so với bản release, xem `docs/semantic-spray-stats.md`. Citation đúng: Piroli et al.,
  RA-L 2023, vol. 8, no. 7, pp. 4322–4329, DOI 10.1109/LRA.2023.3282382.
- ADR đã ghi: `docs/adr/0001` (pin MIT commit), `0002` (plume-only-first), `0003` (SemanticSpray chỉ
  để hiệu chỉnh thống kê, không train/eval detection).
- Velocity provenance: box features carry velocity for real boxes; pasted boxes come from the database sampler and must be verified. Confirm the velocity coordinate frame (ego vs global) from the loader before use, and report counts of eligible boxes with valid velocity.
- Sweep policy differs by config: detection training uses 0 sweeps; evaluation may use 9 on mini and 0 on the keyframes-only subset. Do not compare absolute numbers across those sets.
- If HEAD is used instead of the release commit, re-verify checkpoint loading and the depth tensor shape before any experiment.
