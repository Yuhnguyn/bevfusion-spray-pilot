# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-05 16:05 · **PM:** Hermes (chốt phạm vi, tiêu chí, nghiệm thu) · **Thi công:** CommandCode
**Đọc file này trước khi mở bất kỳ ticket nào.** Ticket là chi tiết; file này là thứ tự và phạm vi.

## Mục tiêu một câu

Chứng minh bằng thí nghiệm paired A/B rằng augment spray plume vào nhánh LiDAR của BEVFusion làm giảm
khoảng cách giữa mAP trên frame sạch và frame có spray — đo trên nuScenes, không train trên SemanticSpray.

## Blocker duy nhất đang chặn toàn bộ dự án

**Ticket 02b — môi trường Kaggle.** Lần chạy mới nhất: `ops_built_and_gpu_smoke=true`, checkpoint load sạch
(0 missing / 0 unexpected), pin đúng — nhưng `model_built=false` vì harness đọc `vtransform.out_channels`
(không tồn tại trên `DepthLSSTransform`). Kết quả thật là **3/6 tiêu chí**, không phải all-pass. Fix đã
commit (`e3b4c08`, `71a7ab1`) nhưng **chưa push** — lần chạy cuối xảy ra trước commit đó.
Mọi ticket từ 04 trở đi đều cần một forward thật, nên **không mở song song việc khác** cho tới khi 02b xanh.

Chuỗi nguyên nhân đã chốt (đừng điều tra lại): thiếu `numba` → uv không resolve được torch → escape `%`
trong `git log --format` → thiếu CUDA dev headers (`cusparse.h`, `cusolverDn.h`) → host compiler
`gcc-13` không hợp CUDA 11.8 → tên package apt sai (`cuda-cusparse-dev-11-8` không tồn tại).
Trạng thái từng version và bảng mapping header→package nằm trong `02b-numba-fix.md`.

## Bảng ticket

| # | Việc | Trạng thái | Phụ thuộc | Next action |
|---|---|---|---|---|
| 01 | Working copy MIT + pin `da93b27` | **done** | — | — |
| 02 | Smoke test checkpoint + 1 sample | ready-for-agent | 02b | chờ 02b xanh rồi điền số |
| 02b | Sửa môi trường Kaggle, chạy lại smoke test | **ready-for-agent → đang chặn** | 01 | CommandCode xử lý (v12 đang chạy) |
| 03 | Velocity frame + ObjectPaste | **done 3/4** | 01 | số đếm box eligible chuyển sang 04 |
| 04 | Dataset gate trên Kaggle (infos pkl, mini split) | ready-for-agent | 02b | tạo `nuscenes_infos_{train,val}.pkl` |
| 05 | Evaluator core + synthetic tests | **done** | — | — |
| 06 | Adapter evaluator cho output MIT | ready-for-agent | 02 | map output → format evaluator |
| 07 | Pipeline transform + `points_clean` | ready-for-agent | 03, 05 | transform sau flip, đăng ký `PIPELINES` |
| 08 | Model forward routing | ready-for-agent | 06, 07 | route `points_clean` vào camera branch |
| 09 | End-to-end pipeline test | ready-for-agent | 07, 08 | test tích hợp, không cần GPU |
| 10 | Train/eval config A/B | ready-for-agent | 04, 09 | config theo arm A/B/B0 |
| 11 | Mini A/B run + report | ready-for-agent | 10 | chạy 1 seed T4, ghi report |
| 12 | SemanticSpray statistics | **done** | — | — |
| 13 | Gate review sau mini A/B | ready-for-agent | 11 | quyết định đi tiếp hay dừng |
| 14 | Arm B0 — lọc spray rồi detect | ready-for-agent | 09 | vị trí + tham số filter cần PM chốt |

## Critical path

`02b` → `04` → `06` → `07` → `08` → `09` → `10` → `11` → `13`

`14` (B0) chạy song song được với `10–11` vì chỉ cần pipeline của `09`.

## Quyết định đã chốt — không mở lại

- Pin MIT BEVFusion `da93b27`; không dùng HEAD. (`docs/adr/0001`)
- v1 chỉ plume, không mô phỏng wet-ground/attenuation. (`docs/adr/0002`)
- Không train/eval detection trên SemanticSpray; chỉ dùng để calibrate + point-wise sanity check. (`docs/adr/0003`)
- Velocity của box đã ở LiDAR frame của keyframe hiện tại; plume phải chèn **sau** `GlobalRotScaleTrans`
  và `RandomFlip3D`, **trước** `PointShuffle`; box do `ObjectPaste` set velocity = 0. (`docs/velocity-contract.md`)
- Ba arm: A = clean baseline, B = có plume, B0 = lọc spray rồi detect.
- Kết quả dương trên plume tổng hợp là **cận trên lạc quan**, không chứng minh giúp spray thật. Camera branch
  nhận `points_clean` nên lợi ích nếu có chỉ đến từ LiDAR.

## Non-goals (không làm trong dự án này)

- Không port model C++ ray-based của Linnhoff; không dựng OSI/beam angles.
- Không dùng code GitLab của Linnhoff (repo chỉ có README, chưa publish).
- Không tune hyperparameter, không multi-seed ở v1 (1 seed T4, kết quả chỉ mang tính hướng).
- Không hứa hẹn cải thiện trên spray thật.

## PM nghiệm thu một ticket thế nào

1. Có số thật, không có ô `null`, không có "ước tính" ghi như số đo.
2. Mọi con số mới truy được nguồn: `[ĐO] / [PAPER] / [CODE] / [CHỌN]`.
3. Test liên quan pass, `git status` sạch, commit message nêu rõ đã làm gì.
4. Không mở rộng phạm vi: việc ngoài ticket thì ghi thành ticket mới, không làm kèm.
5. Nếu bị chặn: dừng, báo PM kèm log + giả thuyết, không tự đổi pin hay version đã chốt.