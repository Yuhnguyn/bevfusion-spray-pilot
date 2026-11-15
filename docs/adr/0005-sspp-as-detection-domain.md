# ADR-0005: Detection chạy trên SemanticSpray++ thay vì nuScenes

Status: Accepted (2026-11-15)

## Context

Nhánh `main` chạy detection trên **nuScenes** và chèn plume tổng hợp, theo ADR-0003. ADR đó ghi
rõ "SemanticSpray chỉ dùng để hiệu chỉnh thống kê, **không** train/eval detection trên đó", với
bốn lý do đo được: 1 box/frame, không có frame sạch, không có calibration 6 camera, và không
quét được độ khó.

Kết quả của hướng đó là **null**: `delta = −0,0031`, CI95 chứa 0. Chẩn đoán tìm ra cơ chế —
plume chỉ thêm ~0,4 % số điểm nên hộp dự đoán dịch trung vị **3 mm**, số hộp không đổi. Nói
cách khác: phép thử không đủ lực, không phải augmentation vô dụng.

Đổi lại, nhánh `sspp` chấp nhận đúng những hạn chế mà ADR-0003 liệt kê, để lấy hai thứ nuScenes
không có: **spray thật** và **box thật trên chính frame đó**.

## Decision

Detection (train + eval + FP/recall) chạy trên **SemanticSpray++**, nhánh LiDAR-only.
36 scene có box 3D, 2.587 frame, 2.595 box, 2 lớp (Car, Van).

Bù lại bốn hạn chế bằng bốn quyết định thiết kế:

| Hạn chế | Cách bù |
|---|---|
| 1 box/frame → mAP là nhiễu | **FP/frame tại ngưỡng score cố định** là thước chính, mAP là phụ |
| Không có frame sạch | Frame "sạch" = bỏ điểm `label == 2`; dùng làm nền train cho **cả hai** arm |
| Không có calib camera | Chỉ LiDAR-only; không claim gì về nhánh camera/fusion |
| Không quét được độ khó | Chia split theo **tốc độ** (test = 50/90/130 km/h chưa thấy) |

## Consequences

**Được:**

- Nhãn spray là nhãn thật của dataset, không phải nhãn do simulator sinh → phép thử có lực.
- Box GT nằm trên đúng frame có spray, không phải ghép từ hai nguồn.
- Không phải tin vào giả định "plume tổng hợp giống spray thật" để có kết quả.

**Mất:**

- Không đo được "sạch vs có spray" trên cùng frame như một phép so sánh tự nhiên. Phải tự tạo
  frame sạch bằng cách xoá điểm, và đó là một giả định (điểm `label == 2` là toàn bộ spray).
- Không chạy được nhánh camera → kết quả không nói gì về BEVFusion fusion, chỉ về LiDAR.
- Số tuyệt đối (AP, FP/frame) không chuyển sang nuScenes đô thị. Chỉ delta ghép cặp chuyển được.
- 12 scene test → khoảng tin cậy rộng. Bootstrap phải theo **scene**, không theo frame.

## Điều gì sẽ khiến mở lại ADR này

- SemanticSpray++ (hoặc bản sau) release đủ 6 camera 360° + calibration + box đa class cho toàn
  bộ 207 scene → khi đó chạy được fusion, nên làm lại trên domain này.
- Có dataset spray thật khác **có frame sạch đi kèm** → lấy lại được phép so sánh tự nhiên.
- Kết quả trên SSPP dương nhưng không tái lập được trên nuScenes + plume → lúc đó cần cả hai
  domain để phân xử.

## Không thay thế ADR-0003 bằng cách xoá nó

ADR-0003 bị xoá khỏi nhánh này vì nội dung của nó **ngược** với hướng mới. Bản gốc vẫn nằm
trong lịch sử: `git show main:docs/adr/0003-semantic-spray-eval-only.md`. Lý do đảo ngược ghi ở
đây, không ghi ở đó.
