# BEVFusion spray pilot (MIT)

Mục tiêu: cải thiện khả năng phát hiện của BEVFusion khi có **spray plume** từ xe phía trước, lúc xe đang chạy trên đường ướt. Đây không phải bài toán robustness dưới lỗi cảm biến.

Cách làm: một pilot nhỏ, train hai arm A/B trên cùng frame. Arm A train clean. Arm B train clean cộng spray plume. Đánh giá trên **held-out spray** bằng **proxy mAP**, số false positive và recall theo range. Thêm arm B0 (lọc spray rồi detect, không train) làm mốc so sánh. Nếu có tín hiệu, viết recipe để đội khác full train.

## Trạng thái

- Spec: `.scratch/spray-augmentation/spec.md` (v1.5, **`ready-for-agent`**; preconditions 1–6 pass).
- ADR: `docs/adr/0001` pin MIT commit `da93b27`, `0002` plume-only-first, `0003` SemanticSpray chỉ để hiệu chỉnh thống kê.
- Đã có code: `spray/plume.py` (sinh plume), `spray/plume_transform.py` (pipeline transform + `points_clean`), `spray/spray_stats.py` (thống kê spray thật), `proxy_eval/matcher.py` (proxy mAP/FP/recall), `proxy_eval/mit_adapter.py` (output MIT → evaluator). Test: **56 passed** (laptop CPU).
- Ticket xong: 01–08, 12, 15–22. Ticket tiếp theo: 23 (chỉnh nhỏ) → 09 (e2e trên Kaggle) → 10 → 11 → 13; 14 và 24 song song. Board: `.scratch/spray-augmentation/STATUS.md`.
- Bằng chứng Kaggle: `kaggle/smoke_test/evidence/` (ticket 02/04/06/07).

## Cấu trúc

- `mit/bevfusion` — working copy, pin `da93b27` (`mit/PIN.md`).
- `third_party/` — clone tham chiếu BEVFusion + devkit SemanticSpray, read-only.
- `data/` — nuScenes mirror info + SemanticSpray 31 GB, gitignore.
- `spray/`, `proxy_eval/`, `scripts/`, `tests/`, `kaggle/`, `docs/`.

## Legacy (local only)

`kernel/`, `interactive/`, `results/phase-b1-nuscenes-mini/` là harness cũ chạy BEVFusion của OpenMMLab. Chúng được giữ local và không commit vào repo này. Kết quả ở đó không phải bằng chứng cho pilot và nằm ngoài phạm vi.