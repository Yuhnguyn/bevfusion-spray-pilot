# Handoff — dataset gate (ticket 04)

## Trạng thái

Gate đã chạy xong trên Kaggle (run #4, `COMPLETE`). Kết quả lưu ở
`kaggle/dataset_gate/dataset_gate.json` và trong ticket 04.

- Mount: `/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes`
- 850 scene, 34,149 keyframe, 1,166,187 annotation.
- 6 camera × 34,149 file; `LIDAR_TOP` 34,149; radar ~34,146–34,148.
- Không có `sweeps/` → training phải dùng 0 sweep.
- License: nuScenes Terms of Use / Non-Commercial, sha256 `1a218286…570636a`.
- Một keyframe load được: 34,720 điểm × 5, đủ 6 camera, 10 annotation.

## Vì sao vẫn giữ notebook

Kaggle API chỉ có `kaggle kernels push`, tức chạy **cả kernel từ đầu đến cuối**.
Không có lệnh chạy từng cell. Khi cần sửa một ô và chạy lại đúng ô đó thì phải
làm trên UI Kaggle. Notebook này giữ vai trò đó.

## Lưu ý schema

`sample.json` không chứa `data`/`anns`; devkit dựng lại từ `sample_data` +
`sample_annotation` (xem `__make_reverse_index__`). Đây là schema chuẩn,
không phải lỗi mirror. Notebook làm đúng logic đó cho một sample nên không
cần `nuscenes-devkit`.

## Còn lại của ticket

- `tools/create_data.py` tạo infos cho keyframes.
- Load một sample qua pipeline MIT.

Cả hai phụ thuộc toolchain của ticket 02 (`mmcv` 1.x + `mmdet3d`). Đây là
phần nên chạy từng cell trên Kaggle UI khi bắt đầu debug toolchain.
