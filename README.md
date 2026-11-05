# BEVFusion spray pilot (MIT)

Mục tiêu: cải thiện khả năng phát hiện của BEVFusion khi có **spray plume** từ xe phía trước, lúc xe đang chạy trên đường ướt. Đây không phải bài toán robustness dưới lỗi cảm biến.

Cách làm: một pilot nhỏ, train hai arm A/B trên cùng frame. Arm A train clean. Arm B train clean cộng spray plume. Đánh giá trên **held-out spray** bằng **proxy mAP**, số false positive và recall theo range. Thêm arm B0 (lọc spray rồi detect, không train) làm mốc so sánh. Nếu có tín hiệu, viết recipe để đội khác full train.

## Trạng thái

- Spec: `.scratch/spray-augmentation/spec.md` (v1.3, `needs-triage`).
- ADR: `docs/adr/0001` pin MIT commit `da93b27`, `0002` plume-only-first, `0003` SemanticSpray chỉ để hiệu chỉnh thống kê.
- Đã có code: `spray/plume.py` (sinh plume), `spray/spray_stats.py` (thống kê spray thật), `proxy_eval/matcher.py` (proxy mAP/FP/recall). Test: 26 passed (laptop CPU).
- Ticket xong: 01 (pin), 05 (evaluator), 12 (stats). Ticket 03/04 xong phần chính.
- **Blocker: ticket 02** — smoke test checkpoint + 1 sample trên Kaggle. Notebook viết xong (`kaggle/smoke_test/`), chưa push/run. Ticket 06–11 chờ ticket 02.

## Cấu trúc

- `mit/bevfusion` — working copy, pin `da93b27` (`mit/PIN.md`).
- `third_party/` — clone tham chiếu BEVFusion + devkit SemanticSpray, read-only.
- `data/` — nuScenes mirror info + SemanticSpray 31 GB, gitignore.
- `spray/`, `proxy_eval/`, `scripts/`, `tests/`, `kaggle/`, `docs/`.

## Legacy (local only)

`kernel/`, `interactive/`, `results/phase-b1-nuscenes-mini/` là harness cũ chạy BEVFusion của OpenMMLab. Chúng được giữ local và không commit vào repo này. Kết quả ở đó không phải bằng chứng cho pilot và nằm ngoài phạm vi.