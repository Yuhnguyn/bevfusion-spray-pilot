# BEVFusion spray pilot (MIT)

Mục tiêu: cải thiện khả năng phát hiện của BEVFusion khi có **spray plume** từ xe phía trước, lúc xe đang chạy trên đường ướt. Đây không phải bài toán robustness dưới lỗi cảm biến.

Cách làm: một pilot nhỏ, train hai arm A/B trên cùng frame. Arm A train clean. Arm B train clean cộng spray plume. Đánh giá trên **held-out spray** bằng **proxy mAP**, số false positive và recall theo range. Nếu có tín hiệu, viết recipe để đội khác full train.

## Trạng thái

- Spec: `.scratch/spray-augmentation/spec.md` (version 1.2, `needs-triage`).
- Chưa có code cho spray.
- Chưa có phép đo nào cho BEVFusion MIT.
- 6 precondition trong spec phải pass trước khi implement.

## Target codebase

- `third_party/bevfusion` — clone tham chiếu của BEVFusion (MIT HAN Lab), read-only.
- `mit/` — bản working được phép sửa (sẽ tạo).
- Không dùng `projects/BEVFusion` của OpenMMLab.

## Legacy (local only)

`kernel/`, `interactive/`, `results/phase-b1-nuscenes-mini/` là harness cũ chạy BEVFusion của OpenMMLab. Chúng được giữ local và không commit vào repo này. Kết quả ở đó không phải bằng chứng cho pilot và nằm ngoài phạm vi.
