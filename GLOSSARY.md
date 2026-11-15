# BEVFusion trên SemanticSpray++ — thuật ngữ

Dùng thống nhất trong issue, ADR, báo cáo. Mỗi mục: câu tiếng Việt trần thuật trước, thuật ngữ
trong ngoặc sau.

## Dữ liệu

**SemanticSpray++ (SSPP)**:
Dataset spray thật: 207 scene highway, mỗi scene một lần ghi của một xe (Crafter hoặc Golf) chạy
ở một tốc độ cố định trên đường ướt. Có nhãn điểm theo lớp, trong đó `label == 2` là spray.
_Avoid_: SemanticSpray (bản cũ không có box), spray dataset

**Scene**:
Một lần ghi, khoảng 76 frame. Trong SSPP mỗi scene có đúng một tốc độ và một cự ly.
_Avoid_: sequence, run

**Frame**:
Một scan LiDAR, 5 cột `x, y, z, intensity, ring`.
_Avoid_: scan, sample, keyframe

**Spray**:
Các điểm `label == 2` — nước bắn từ lốp xe dẫn đường, nằm trong không khí phía sau xe.
_Avoid_: noise, spray noise, water noise

**Splash**:
Nước bắn trực tiếp lên bề mặt cảm biến (lens, cửa sổ LiDAR), khác với spray trong không khí.
_Avoid_: spray (khi muốn nói bám lên cảm biến)

**Frame sạch**:
Frame đã bỏ hết điểm `label == 2`. SSPP **không có** frame sạch tự nhiên; đây là frame tự tạo.
_Avoid_: clean frame, ground truth clean

**Box**:
Hộp 3D quanh xe dẫn đường, lưu ở `object_labels/lidar/*.json`. Chỉ 36/207 scene có.
_Avoid_: annotation, label (khi muốn nói box)

## Thí nghiệm

**Model 0**:
Checkpoint `lidar-only-det.pth` của BEVFusion, **không train thêm**. Chỉ chạy inference.
_Avoid_: baseline, zero-shot (zero-shot dễ bị hiểu là không thấy domain nào)

**Arm A**:
Nhánh fine-tune trên frame sạch (đã bỏ `label == 2`), **không** augment. Nhóm đối chứng.
_Avoid_: control arm (dùng "Arm A" cho khớp bảng)

**Arm B**:
Nhánh fine-tune trên cùng frame sạch nhưng có chèn spray tổng hợp, xác suất 0,5 mỗi frame.
_Avoid_: augmented arm

**Spray tổng hợp**:
Điểm spray do generator sinh ra, chèn vào frame sạch lúc train. Khác spray thật ở chỗ không có
nhãn người gán.
_Avoid_: synthetic spray (được, nhưng tiếng Việt trước), plume (plume là tên riêng của generator)

**Split theo tốc độ**:
Chia train/val/test theo tốc độ xe, để test chứa tốc độ **không có** trong train.
_Avoid_: random split

## Đo

**FP/frame**:
Số hộp dự đoán không khớp box thật nào, tính trung bình mỗi frame, tại một ngưỡng score cố định.
Đây là **thước chính** của dự án.
_Avoid_: false positive rate (đó là tỉ lệ, khác đơn vị)

**SPF proxy/frame**:
Số hộp dự đoán vừa là FP vừa nằm gần cụm spray thật (tâm cách ≤ 1,5 m). Đo mức model báo nhầm
**vì spray**, không phải vì lý do khác. Hàng quyết định của thí nghiệm.
_Avoid_: spray FP (dùng SPF cho khớp bảng)

**Recall**:
Tỉ lệ box thật được phát hiện ở IoU ≥ 0,5. Đại lượng phải **giữ nguyên** khi giảm FP.
_Avoid_: detection rate

**τ (tau)**:
Ngưỡng score, chọn trên frame sạch là ngưỡng nhỏ nhất đạt precision ≥ 0,5. Đóng băng, dùng cho
cả ba checkpoint.
_Avoid_: threshold (dùng τ khi nói con số cụ thể)

**Bootstrap theo scene**:
Lấy mẫu lại ở mức scene, không phải frame, để tính CI95. Frame trong cùng scene gần giống nhau
nên lấy mẫu theo frame sẽ làm CI hẹp giả.
_Avoid_: bootstrap (khi chưa nói theo đơn vị nào)

## Nhãn nguồn số

**`[ĐO]`**: đo trên máy này, có script.
**`[PAPER]`**: paper nói, có trích dẫn.
**`[CODE]`**: code tham chiếu (openMSL/sl-1-2) quy định.
**`[CHỌN]`**: tự chọn, không có nguồn ngoài.

Mọi con số trong tài liệu phải mang một trong bốn nhãn này.
