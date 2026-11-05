# Handoff — dataset gate (ticket 04)

## Vì sao handoff

Kaggle API chỉ có `kaggle kernels push`, tức chạy **cả kernel từ đầu đến cuối**.
Không có lệnh chạy từng cell. Muốn sửa một ô rồi chạy lại đúng ô đó thì phải
làm trên UI Kaggle. Vì vậy phần còn lại giao lại để bạn chạy từng ô.

## Đã xác minh từ lần push trước

- Dataset attach tại:
  `/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes`
- Có `v1.0-trainval/`; `sample.json` có **34,149 keyframes**.
- `LICENSE` là CC BY-NC-SA 4.0.
- Top-level: `maps/`, `samples/`, `v1.0-trainval/`, không thấy `sweeps/`.
- Lỗi cũ: `pip install nuscenes-devkit==1.1.11` fail vì build `Shapely<2`
  trên Python 3.13 của Kaggle. Ô 6 trong notebook đã có cách lách
  (cài `shapely==2.0.7` trước, rồi `--no-deps`), nhưng ô đó **tùy chọn**.

## Cách chạy

1. Mở Kaggle, tạo notebook Python, Add Input →
   `sahangunasekara92/nuscenes-v1-0-full-keyframes`.
2. Copy các ô từ `bevfusion-spray-dataset-gate.ipynb` sang notebook
   (hoặc mở file này trực tiếp trên Kaggle).
3. Chạy ô 1 → 5, rồi ô 7. Bỏ qua ô 6 trừ khi cần `nuscenes-devkit`.
4. Nếu ô 1 báo không thấy dataset, in `os.listdir('/kaggle/input')` và
   sửa danh sách `CANDIDATES`.

Mỗi ô idempotent và chỉ phụ thuộc biến của ô trước, nên khi lỗi chỉ cần
sửa rồi chạy lại đúng ô đó.

## Cần trả về

- Nội dung `/kaggle/working/dataset_gate.json`.
- Danh sách sensor và số file mỗi loại (đặc biệt `LIDAR_TOP`, 6 `CAM_*`).
- `sweeps_present` true/false.
- `sample_check`: shape point cloud, 6 camera tồn tại, số annotation.
- Phần thiếu (nếu có).

## Sau gate

Tạo infos bằng converter MIT (`tools/create_data.py`) cần toolchain
`mmcv` 1.x + `mmdet3d` của ticket 02, chưa chạy trong notebook này.
