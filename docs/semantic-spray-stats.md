# SemanticSpray statistics

Sinh bởi `scripts/semantic_spray_stats.py`. Chỉ dùng để so thống kê
simulator; dataset này không dùng để train/eval BEVFusion.

## Câu hỏi và kết luận

Câu hỏi: spray plume thật trông như thế nào (bao nhiêu điểm, to cỡ nào,
ở đâu, sáng đến đâu), và bộ sinh `spray/plume.py` có tạo ra thứ tương
tự không?

- Tổng mật độ mỗi frame cùng bậc: dense median 144 điểm so với simulator 128.
- Mỗi plume simulator dày hơn plume thật: 32 so với median 17 điểm.
- Intensity thật gần như bằng 0: median 0, p99 3, khớp mặc định 0.
- Kích thước plume thật chưa kết luận được vì clustering có thể nối
  chuỗi điểm; xem caveat về extent.

## Sample

- scenes: **207**
- frames đã đọc: **2070** (lấy mẫu đều mỗi scene)
- frames có noise label: **2034**
- clustering: single-linkage, radius **0.5 m**
- dense cluster: **>= 5 điểm**
- simulator tham chiếu: `PlumeConfig` mặc định, lead vehicle **50 km/h**

## Nguồn dữ liệu

- SemanticSpray (Piroli et al., RA-L 2024), license CC BY 4.0.
- Devkit: https://github.com/uulm-mrm/semantic_spray_dataset
- Root đọc: `data/SemanticSprayDataset` (2 nhóm scene, 207 scene).
- `velodyne/*.bin`: `(x, y, z, intensity, ring)`; `labels/*.label`:
  int32 với `0 = background`, `1 = foreground vehicle`, `2 = noise`
  theo loader của devkit.
- Script đọc trực tiếp file nhị phân, không áp dụng ego-box filter
  của devkit.

## Observed distribution

| metric | value |
|---|---|
| noise points / frame (median) | 159.0 |
| noise points / frame (mean) | 422.0 |
| noise points / frame (p90) | 1138.6 |
| noise points / frame (max) | 4088 |
| clusters / frame (median) | 14.0 |
| cluster size (median) | 2.0 |
| cluster size (mean) | 24.7 |
| cluster size (p90) | 40.0 |
| cluster size (max) | 2934 |
| dense clusters observed | 11607 |
| dense cluster size (median) | 17.0 |
| dense points / frame (median) | 144.0 |
| dense clusters / frame (median) | 5.0 |
| dense cluster extent (median) | 1.16 m |
| dense cluster extent (p90) | 3.75 m |
| dense ego distance (median) | 10.8 m |
| dense distance to foreground (median) | 26.1 m |
| ego distance (median) | 12.3 m |
| ego distance (p90) | 23.5 m |
| distance to foreground (median) | 23.8 m |
| distance to foreground (p90) | 41.7 m |
| intensity median | 0.0 |
| intensity p90 | 1.0 |
| intensity p99 | 3.0 |
| intensity max | 220.0 |
| intensity == 0 fraction | 81.95% |
| height median | 0.98 m |
| height p10 | 0.07 m |
| height p90 | 1.90 m |

## So với simulator

| metric | real | simulator | note |
|---|---|---|---|
| points/frame | 144.00 | 128.00 | dense clusters only, vs one 50 km/h lead vehicle |
| clusters/frame | 5.00 | 4.00 | dense clusters only, vs clipped k*speed |
| points/cluster (median) | 2.00 | 32.00 | all clusters, including singletons |
| points/cluster (dense median) | 17.00 | 32.00 | clusters with >= 5 points |
| cluster extent (m) | 3.75 | 0.70 | p90 max axis-aligned span (chaining caveat) vs 2*radius |
| distance to nearest vehicle point (m) | 26.08 | 1-10 | không so trực tiếp: real đo tới điểm foreground, simulator đo từ tâm box |
| height (m) | 0.98 | 0.2-2 | median vs configured uniform range |
| intensity (median) | 0.00 | 0.00 | raw SemanticSpray intensity vs configured constant |

## Khác biệt lớn

- Dense plume thật nhỏ hơn một cluster simulator: median 17 so với 32 điểm.

## Caveats

- Label `2` của SemanticSpray là *noise*, gồm spray và các nguồn
  nhiễu khác (mưa, phản xạ). Vì vậy phần lớn cluster là singleton.
  Các so sánh hình học chỉ dùng dense cluster (>= 5 điểm)
  để tránh kết luận từ nhiễu rời rạc.
- Single-linkage nối các điểm cách nhau <= radius, nên một chuỗi điểm
  có thể bị gộp thành một cluster dài. Extent vì vậy là **cận trên**,
  không dùng để kết luận plume thật to hay nhỏ hơn simulator.
- Khoảng cách tới foreground là khoảng cách centroid tới điểm
  foreground gần nhất, không phải tới tâm box của xe. Điểm foreground
  thưa do occlusion nên giá trị này thiên lớn và không so trực tiếp
  được với offset 1-10 m của simulator.
- Ticket này chỉ so với `PlumeConfig` của repo, chưa so với đường cong
  trong paper. Đây là bước stage 4 của evidence ladder, không phải
  bằng chứng cho pilot A/B.
