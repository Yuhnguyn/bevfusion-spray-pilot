# ADR-0002: v1 chỉ có plume trên LiDAR, không wet-ground

Status: **Superseded by ADR-0004** (2026-11-10) · ban đầu Accepted (2026-01)

## Context

Một plume thật trên đường ướt đi kèm nhiều hiệu ứng khác: mặt đường ướt phản xạ, hơi nước làm
suy giảm (attenuation) điểm phía sau plume, occlusion do chính plume, và nước bắn lên lens camera.
Mỗi hiệu ứng cần một mô hình riêng, hiệu chỉnh riêng, và có thể tương tác với nhau.

Repo chỉ có compute Kaggle T4 (~30 GPU-giờ/tuần) và chưa có phép đo nào.

## Decision

v1 chỉ chèn **plume point vào LiDAR**, giữ camera branch dùng `points_clean` (điểm trước khi inject).
Không làm: wet-ground, attenuation, occlusion/xóa điểm thật, temporal history, ray casting, camera-side
splash. Toàn bộ phần đó là v2.

## Consequences

- Câu hỏi nghiên cứu thu hẹp còn: "học cách bỏ qua cụm điểm plume có giúp ích không", không phải
  "mô phỏng đầy đủ thời tiết xấu".
- Kết quả âm không được diễn giải là "spray không quan trọng" — chỉ là "plume-only augmentation không đủ".
- Mọi tuyên bố về wet-ground hay camera-side splash bị cấm trong report v1.
- Đổi lại: một biến duy nhất thay đổi giữa hai arm, nên phép so sánh paired còn hiệu lực.