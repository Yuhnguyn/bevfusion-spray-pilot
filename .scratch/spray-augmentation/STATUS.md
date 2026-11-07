# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-07 09:10 · **PM:** Hermes (chốt phạm vi, tiêu chí, nghiệm thu) · **Thi công:** CommandCode
**Đọc file này trước khi mở bất kỳ ticket nào.** Ticket là chi tiết; file này là thứ tự và phạm vi.

## Mục tiêu một câu

Chứng minh bằng thí nghiệm paired A/B rằng augment spray plume vào nhánh LiDAR của BEVFusion làm giảm
khoảng cách giữa mAP trên frame sạch và frame có spray — đo trên nuScenes, không train trên SemanticSpray.

## Trạng thái hiện tại

**02b đã xong; preconditions 1–6 PASS.** Ticket 02 ALL_PASS (582/582, forward finite), dataset gate 04 xong
(infos 120/120 + load sample), ticket 06 adapter evaluator xong (mAP 0.298 trên frame thật), ticket 07
`PlumeTransform` pass 12/12 check. Spec đã flip `ready-for-agent`.

Việc tiếp theo: **08 (model routing)** → 09 → 10 → 11 → 13; 14 chạy song song; 16 → 17 độc lập với
pipeline (chỉ chạm `scripts/`, `spray/`, `tests/`, `docs/`).

Lịch sử fix môi trường: thiếu `numba` → uv không resolve được torch → escape `%` trong `git log --format`
→ thiếu CUDA dev headers → `gcc-13` không hợp CUDA 11.8 → tên package apt sai. Chi tiết trong
`02b-numba-fix.md`.

## Bảng ticket

| # | Việc | Trạng thái | Phụ thuộc | Next action |
|---|---|---|---|---|
| 01 | Working copy MIT + pin `da93b27` | **done** | — | — |
| 02 | Smoke test checkpoint + 1 sample | **done** | 02b | — |
| 02b | Sửa môi trường Kaggle, chạy lại smoke test | **done** | 01 | — |
| 03 | Velocity frame + ObjectPaste | **done** | 01 | — |
| 04 | Dataset gate trên Kaggle (infos pkl, mini split) | **done** | 02b | — |
| 05 | Evaluator core + synthetic tests | **done** | — | — |
| 06 | Adapter evaluator cho output MIT | **done** | 02, 05 | mAP 0.298 trên frame thật |
| 07 | Pipeline transform + `points_clean` | **done** | 03, 05 | 12/12 check |
| 08 | Model forward routing | ready-for-agent | 07 | route `points_clean` vào camera branch |
| 09 | End-to-end pipeline test | blocked | 07, 08 | test tích hợp, không cần GPU |
| 10 | Train/eval config A/B | blocked | 04, 09 | config theo arm A/B/B0 |
| 11 | Mini A/B run + report | blocked | 06, 10 | chạy 1 seed T4, ghi report |
| 12 | SemanticSpray statistics | **done** | — | — |
| 13 | Gate review sau mini A/B | blocked | 11 | quyết định đi tiếp hay dừng |
| 14 | Arm B0 — lọc spray rồi detect | ready-for-agent | 02, 05 | filter + frame list chốt với PM |
| 16 | Đo hình học plume thật theo cự ly (SemanticSpray) | **ready-for-agent** | — | CommandCode chạy ngay được, không cần Kaggle |
| 17 | Đặt điểm trên vỏ cầu phía cảm biến | blocked | 16 | chờ số `r_range/r_extent` của 16 |

## Critical path

`07` → `08` → `09` → `10` → `11` → `13`

`14` (B0) chạy song song được với `10–11`; chỉ cần evaluator + model.

`16 → 17` **độc lập với pipeline**: chỉ chạm `scripts/`, `spray/`, `tests/`, `docs/` — không cần GPU,
không cần checkpoint. Có thể làm song song với `08`.

## Quyết định đã chốt — không mở lại

- Pin MIT BEVFusion `da93b27`; không dùng HEAD. (`docs/adr/0001`)
- v1 chỉ plume, không mô phỏng wet-ground/attenuation. (`docs/adr/0002`)
- Lý do **định lượng** để bỏ attenuation ở v1: hệ số tắt 0,02 m⁻¹ [PAPER §III] × quãng xuyên thực tế
  0,5–0,8 m (1–2 cụm r = 0,3 m) → intensity còn 98,4–99% → dưới ngưỡng lượng tử hoá intensity của
  nuScenes. Chỉ đáng làm nếu chuyển sang regime fully-watered của paper (500–1.500 điểm/frame).
- v1 đặt điểm plume trên **vỏ cầu phía cảm biến**, không trong khối cầu; không dựng beam grid/OSI
  (ticket 16–17). Mật độ vẫn neo SemanticSpray, **không** phụ thuộc cự ly — nếu ticket 16 chứng minh
  điều đó sai thì PM mở ticket 18.
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