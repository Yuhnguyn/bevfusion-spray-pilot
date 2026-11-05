# 04: Dataset gate trên Kaggle

**What to build:** Xác minh dataset keyframes trên Kaggle có đủ cấu trúc để tạo infos và load một sample. Nếu thiếu metadata hoặc converter lỗi, dừng sớm và ghi rõ.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Dataset attach được và có đủ camera, LiDAR, metadata.
- [ ] Infos tạo được cho keyframes.
- [ ] Load được một sample qua pipeline.
- [ ] License và provenance được ghi lại.
- [ ] Danh sách phần thiếu (nếu có) được báo.

## Comments

- Dataset chọn để gate: `sahangunasekara92/nuscenes-v1-0-full-keyframes`
  (v1.0-trainval, 34,149 keyframe, license CC BY-NC-SA 4.0, không có `sweeps/`).
- Kaggle mount: `/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes`.
- Notebook từng cell + hướng dẫn: `kaggle/dataset_gate/`.
- Đã xác minh metadata và license từ xa; còn chờ chạy notebook trên Kaggle để
  đếm sensor và load một keyframe.
- `nuscenes-devkit==1.1.11` fail build Shapely trên Python 3.13 của Kaggle;
  notebook có workaround tùy chọn, gate chính không phụ thuộc devkit.
