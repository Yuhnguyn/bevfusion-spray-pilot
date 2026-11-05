# 04: Dataset gate trên Kaggle

**What to build:** Xác minh dataset keyframes trên Kaggle có đủ cấu trúc để tạo infos và load một sample. Nếu thiếu metadata hoặc converter lỗi, dừng sớm và ghi rõ.

**Blocked by:** 01

**Status:** done

- [x] Dataset attach được và có đủ camera, LiDAR, metadata.
- [x] Infos tạo được cho keyframes. (bằng chứng `infos.json` từ version đã commit)
- [x] Load được một sample qua pipeline. (v19 `TICKET04_OK`; `dataset_sample.json`)
- [x] License và provenance được ghi lại.
- [x] Danh sách phần thiếu (nếu có) được báo.

## Comments

- Dataset chọn để gate: `sahangunasekara92/nuscenes-v1-0-full-keyframes`
  (v1.0-trainval, 34,149 keyframe, license CC BY-NC-SA 4.0, không có `sweeps/`).
- Kaggle mount: `/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes`.
- Notebook từng cell + hướng dẫn: `kaggle/dataset_gate/`.
- `nuscenes-devkit==1.1.11` fail build Shapely trên Python 3.13 của Kaggle;
  notebook có workaround tùy chọn, gate chính không phụ thuộc devkit.
- **Kết quả run #4**: `kaggle/dataset_gate/dataset_gate.json`
  - 850 scene, 34,149 sample, 1,166,187 annotation.
  - Đủ 13 bảng metadata, gồm `sensor`.
  - 6 camera × 34,149 file, `LIDAR_TOP` 34,149, radar ~34,146-34,148.
  - Không có `sweeps/`; 4 map.
  - License: `nuScenes ... Terms of Use / Non-Commercial Use`,
    sha256 `1a218286...570636a`.
  - Một keyframe load được: 34,720 điểm × 5, đủ 6 camera, 10 annotation.
- **Lưu ý schema**: `sample.json` không chứa `data`/`anns`; devkit dựng lại
  từ `sample_data` + `sample_annotation`. Không phải lỗi mirror; notebook
  làm đúng logic devkit cho một sample.
- Đã load được một sample qua pipeline MIT ở v19 (xem mục dưới). Toolchain ticket 02 đã sẵn sàng.

## Kết quả tạo infos (version đã commit, 2026-11-05)

- `infos.json`: train **120 infos** (3 scene), val **34,029 infos** (toàn bộ phần còn lại),
  file 1,729,648 B / 407,187,382 B; `max_sweeps=0`.
- First info: 6 camera, 0 sweep, 10 GT (train) / 37 GT (val); `lidar_path` trỏ
  `/kaggle/working/data/nuscenes/samples/LIDAR_TOP/...`.
- Lưu ý: `create_nuscenes_infos` gán mọi sample **không thuộc train scene** vào val, nên
  `MAX_SCENES` chỉ chặn train. Đã sửa cell: filter `nusc.sample` theo train∪val scene.
- Load sample fail ở `LoadBEVSegmentation`: mirror chỉ có `maps/*.png`, thiếu
  `maps/expansion/*.json`. `modality.use_map=false` nên cell đã drop transform này khi load;
  cần rerun để lấy `dataset_sample.json`.

## v19 — TICKET04_OK (2026-11-05)

- `infos.json`: train **120** / val **120** infos, 109.4 s, `max_sweeps=0`.
- `dataset_sample.json`: load index 0 qua val pipeline; đủ 6 camera, 0 sweep, 2 GT;
  `missing_image_paths=[]`; batch có đủ `img`, `points`, `gt_bboxes_3d`, `gt_labels_3d`,
  calibration/meta keys.
- Đã drop `LoadBEVSegmentation` và `Collect3D.gt_masks_bev` vì `modality.use_map=false`
  và mirror thiếu `maps/expansion/*.json`; ghi trong `dropped_transforms`.
- Lỗi schema của pin `da93b27` đã xử lý: converter ghi `camera_intrinsics`, dataset đọc
  `cam_intrinsic` → thêm alias khi tạo infos (và fallback khi load).
