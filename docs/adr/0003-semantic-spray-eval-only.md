# ADR-0003: Chạy detection trên nuScenes + plume inject, SemanticSpray chỉ dùng để hiệu chỉnh thống kê

Status: Accepted (2026-01)

## Context

Có hai cách để đo "spray plume có làm hỏng detection không":

1. Train/eval BEVFusion trực tiếp trên SemanticSpray (Piroli et al., RA-L 2023) — có spray thật,
   label tay.
2. Chạy trên nuScenes, chèn plume tổng hợp, so paired với frame sạch.

Trước ADR này, spec chỉ ghi phương án 1 là "Out of Scope" mà không nêu lý do, nên dễ bị đọc thành
"chưa nghĩ tới". ADR ghi lại lý do, kèm số đo trên `data/SemanticSprayDataset`.

## Decision

Detection (train + eval + mAP/FP/recall) chạy trên **nuScenes keyframes** với plume inject.
SemanticSpray chỉ dùng cho: (a) hiệu chỉnh thống kê simulator (ticket 12), (b) kiểm tra point-wise
như sanity check. **Không** train/eval BEVFusion trên SemanticSpray trong v1.

## Evidence — vì sao không dùng trực tiếp được

Số đo trên bản release local (207 scene, 17.419 scan), không lấy từ paper:

| yêu cầu của phép đo | nuScenes + inject | SemanticSpray | hệ quả |
|---|---|---|---|
| GT để tính mAP | 34.149 keyframe, 1,17M annotation, 10 class | **2.595 box / 2.587 frame / 36 scene**, 1 box/frame (max 2), class chỉ Car/Van/Other Vehicle | mAP trên 1 object/frame là nhiễu, không phải phép đo |
| frame đối chứng sạch | cùng frame, bật/tắt inject | **100% frame có spray**, không có bản sạch | `G = mAP_clean − mAP_spray` không tồn tại; mọi chênh lệch lẫn domain (highway, 2 xe ego, 1 ngày) |
| camera branch của BEVFusion | 6 view + calibration + ego pose | **1 camera trước** | không dựng được BEV feature map từ 6 view; chạy được chỉ còn LiDAR-only |
| độ khó điều khiển được | tham số plume held-out theo severity/seed | 1 điều kiện vật lý cố định | không quét được độ nhạy, không tách được "spray dày" vs "spray mỏng" |
| chi phí tích hợp | viết transform + routing | viết adapter pose/box, retune voxel & point_cloud_range, train lại head cho 1 class | tuần-người, mà vẫn không giải quyết 3 dòng trên |

Bổ sung: spray thật chỉ chiếm **0,25–0,5%** số điểm mỗi scan (28.546 điểm/scan, VLP32C 32 tia;
plume dense median 17 điểm). Nghĩa là ngay cả khi eval được, tín hiệu cũng nằm trong 1 class
và 1 object — không đủ để nói gì về 10 class của nuScenes.

## Precedent trong chính paper

Paper không train detector trên spray thật. Họ dựng **NuScenes-Fog bằng fog simulation**
(Hahner et al., ICCV 2021): 27.449 scan train / 6.019 scan test, rồi mới đo cross-domain.
Spray thật (RoadSpray + label tay) chỉ dùng để **eval point-wise** (AUROC/AUPR/IoU), không dùng
để đo mAP detection.

Tức cách làm "simulate trên nuScenes" là cách nhóm tác giả đã chọn, không phải né tránh.

## Cảnh báo đi kèm (không được bỏ qua khi viết report)

Sim→real là mắt yếu nhất, và paper có số liệu chứng minh: AWNet train trên NuScenes-Fog rồi test
trên spray thật chỉ đạt AUPR 70,52 và FPR95 21,24 (so với 96,29 AUROC — AUROC che mất lỗi này).
Vì vậy mini A/B dương trên plume tổng hợp **không** chứng minh giúp được spray thật.

## Điều gì sẽ khiến ta mở lại ADR này

- SemanticSpray++ (hoặc bản sau) release đủ 6 camera 360°, calibration, và box đa class cho toàn bộ
  207 scene → khi đó "BEVFusion trên spray thật" thành khả thi và nên làm anchor.
- Hoặc có dataset spray thật khác có frame sạch đi kèm.
- Hoặc mini A/B dương nhưng cross-generator check thất bại → lúc đó cần spray thật để phân xử,
  dù chỉ ở mức FP count + qualitative.