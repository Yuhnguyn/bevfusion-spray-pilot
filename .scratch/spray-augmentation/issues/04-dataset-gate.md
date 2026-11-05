# 04: Dataset gate trên Kaggle

**What to build:** Xác minh dataset keyframes trên Kaggle có đủ cấu trúc để tạo infos và load một sample. Nếu thiếu metadata hoặc converter lỗi, dừng sớm và ghi rõ.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Dataset attach được và có đủ camera, LiDAR, metadata.
- [ ] Infos tạo được cho keyframes. (chờ toolchain ticket 02)
- [ ] Load được một sample qua pipeline. (đã load raw một keyframe; pipeline MIT chờ ticket 02)
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
- Phần còn thiếu duy nhất của ticket: `create_data.py` và load qua pipeline
  MIT, cả hai phụ thuộc toolchain của ticket 02.
