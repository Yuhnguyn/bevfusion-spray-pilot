# BEVFusion spray pilot

Nghiên cứu cải thiện BEVFusion cho tình huống **spray plume** từ xe phía trước khi xe đang chạy trên đường ướt: dùng augmentation để train, rồi đo mức cải thiện trên held-out spray. Đây không phải bài toán robustness dưới lỗi cảm biến. Thuật ngữ dưới đây dùng thống nhất trong issue, ADR và báo cáo.

## Language

**Spray plume**:
Cụm điểm giả do nước bắn từ lốp xe trên đường ướt, xuất hiện phía sau xe đang chạy.
_Avoid_: spray noise, water noise

**Splash**:
Nước bắn trực tiếp lên bề mặt cảm biến (lens, cửa sổ LiDAR), khác với plume trong không khí.
_Avoid_: spray (khi muốn nói đến bám lên cảm biến)

**Spray preset**:
Một đơn vị augmentation gồm hai phần: làm ướt mặt đường và chèn spray plume. Pilot v1 chỉ dùng phần plume; wet-ground là ablation riêng.
_Avoid_: spray-only, rain augmentation

**Eligible frame**:
Frame có ít nhất một xe dẫn đường đạt ngưỡng tốc độ và nằm trong vùng đặt plume.
_Avoid_: valid frame, candidate frame

**Held-out spray**:
Bộ tham số spray (mức nước, loại xe, severity, seed) không dùng khi train, chỉ dùng khi đánh giá.
_Avoid_: test set

**Clean points**:
Point cloud trước khi chèn spray, dùng làm point-derived sparse depth input cho camera branch.
_Avoid_: raw points, original points, depth supervision

**Sweep**:
Frame LiDAR không có nhãn nằm giữa các keyframe nuScenes, dùng để làm dày point cloud.
_Avoid_: frame, scan

**Corruption**:
Phép biến đổi đầu vào chỉ dùng lúc đánh giá để đo suy giảm.
_Avoid_: augmentation

**Augmentation**:
Phép biến đổi đầu vào chỉ dùng lúc train.
_Avoid_: corruption

**Proxy mAP**:
mAP@0.5 tính bằng matcher tự viết cho pilot MIT, không phải nuScenes NDS.
_Avoid_: mAP, NDS
