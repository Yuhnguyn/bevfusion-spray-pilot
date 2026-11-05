# Velocity contract (BEVFusion MIT, `da93b27`)

Kiểm tra ngày 2026-11-05 trên working copy `mit/bevfusion` (pin `da93b27`).

## Answer

Box velocity nằm ở **LiDAR frame của keyframe hiện tại** — không phải global, không phải ego-body.

Chuỗi biến đổi, có dẫn chứng:

1. **Nguồn là global.** `nusc.box_velocity(token)` trả velocity trong hệ global (hiệu vị trí global / dt).
2. **Converter xoay sang LiDAR frame.** `tools/data_converter/nuscenes_converter.py:264–268`:
   ```python
   # convert velo from global to lidar
   velo = np.array([*velocity[i], 0.0])
   velo = velo @ np.linalg.inv(e2g_r_mat).T @ np.linalg.inv(l2e_r_mat).T
   velocity[i] = velo[:2]
   ```
   rồi lưu `info["gt_velocity"]` (dòng 282) dưới dạng 2 giá trị.
3. **Loader nối vào box tensor.** `mmdet3d/datasets/nuscenes_dataset.py:305–309`: `gt_velocity` được
   `np.concatenate` thành cột 7:9 → box có 9 chiều; NaN được thay bằng `[0, 0]`.
4. **Rotation giữ đúng.** `mmdet3d/core/bbox/structures/lidar_box3d.py:152–154`:
   ```python
   if self.tensor.shape[1] == 9:
       # rotate velo vector
       self.tensor[:, 7:9] = self.tensor[:, 7:9] @ rot_mat_T[:2, :2]
   ```
5. **Flip giữ đúng.** `flip()` dùng stride slicing: `[:, 1::7]` (chạm cột 1 và 8 = `vy`) và
   `[:, 0::7]` (chạm cột 0 và 7 = `vx`) → velocity bị đảo dấu cùng phía với điểm.

**Kết luận:** tại thời điểm một transform tuỳ biến nhìn thấy box, velocity đã cùng frame với points.
Không cần xoay thêm.

## Hai điều kiện bắt buộc khi dùng

1. **Thứ tự pipeline**: transform sinh plume phải chạy **sau** `GlobalRotScaleTrans` và `RandomFlip3D`.
   Nếu chạy trước, box còn ở frame gốc trong khi points đã xoay → plume lệch hướng. Cách khác: dùng
   `lidar_aug_matrix` để tự đưa về frame sau augment (spec đã yêu cầu điều này).
2. **Scale không áp lên |v|**: `GlobalRotScaleTrans` phóng box và points theo `resize_lim` nhưng **không**
   nhân độ lớn velocity. Sai số ≤ ±5% (theo `resize_lim` điển hình), ảnh hưởng hai chỗ: ngưỡng
   50 km/h và `n_clusters = 0.08 × km/h`. Với frame nằm sát ngưỡng, quyết định có thể lật. Ghi nhận,
   không sửa.

## ObjectPaste

DB ground-truth lưu box 9 chiều (`create_gt_database.py:274` lấy `annos["gt_bboxes_3d"]` **sau** khi
loader đã nối velocity), và `DataBaseSampler` concatenate thẳng vào frame hiện tại. Hệ quả:

- Box paste mang velocity của **object ở scene nguồn**, chỉ đổi vị trí, không tính lại theo pose mới.
- Hướng velocity vì vậy **không đáng tin** cho việc đặt plume.

Khuyến nghị: đặt velocity của box paste về 0 trước khi gọi generator → generator tự skip và tăng
`skipped_no_velocity`. Không đặt plume theo heading như phương án thay thế, vì sai hướng còn tệ hơn
không có plume.

## Fallback

Velocity thiếu, không hữu hạn, hoặc tốc độ dưới ngưỡng → skip box, tăng counter tương ứng.
(`plume.py` hiện làm đúng: `skipped_no_velocity`, `skipped_low_speed`.)

## Số đo eligible (2026-11-05)

Quét toàn bộ val infos (34,029 frame, 1,160,875 box; 1,468 vehicle box trên 120 frame đầu):

| Ngưỡng | Box vehicle | Box front ≤30 m | Frame có ≥1 box | Tỷ lệ frame |
|---|---|---|---|---|
| ≥30 km/h | 44,537 | 7,152 | 4,690 | 13.8% |
| ≥40 km/h | 18,552 | 2,927 | 1,924 | 5.7% |
| ≥50 km/h | 5,514 | 952 | 697 | **2.0%** |
| ≥60 km/h | 950 | 193 | 173 | 0.5% |

Phân bố tốc độ finite: p50 0.21, p90 10.72, p95 26.14, p99 44.46, p99.9 58.98 km/h; max 175.71
(outlier). Ba scene val đầu (120 frame) có **0** box ≥50 km/h, max 43.5 → subset không đại diện.

**Hệ quả:** ngưỡng 50 km/h của `PlumeConfig` chỉ chạm ~2% frame val. Trước ticket 07/10/11 phải chọn
scene highway hoặc hạ ngưỡng (30 km/h → 13.8%). Không đổi ngưỡng trong code khi chưa chốt.

- Bug biên đã phát hiện: xe đúng **30,0 km/h** bị skip do `30/3.6*3.6 = 29.999… < 30`. Cần test biên
  hoặc so sánh với epsilon.