# Ticket 09-i — CHỈ viết test e2e + chạy local (không đụng Kaggle)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · branch `main` · HEAD `60092a1`

> Việc duy nhất: tạo **1 file** `tests/test_pipeline_e2e.py`, chạy pytest local, commit.
> KHÔNG push Kaggle. KHÔNG sửa file khác. KHÔNG đọc vendor. Xong trong ~20 turn.

## Đọc trước — đúng 3 file, không đọc thêm

1. `spray/pipeline.py` — `CleanPointsFormatBundle3D`, `CleanPointsCollect3D`, `install()`.
2. `spray/plume_transform.py` — `PlumeTransform` (constructor + key `points_clean` + tên field đếm điểm đã chèn).
3. `mit/bevfusion/configs/nuscenes/default.yaml` **chỉ dòng 55–175** (`train_pipeline`).

## Đã xác minh sẵn — dùng luôn

- File config **duy nhất** có `train_pipeline`: `mit/bevfusion/configs/nuscenes/default.yaml`.
  (`det/transfusion/...` chỉ có model, không có pipeline.)
- `train_pipeline` gồm 16 bước: `LoadMultiViewImageFromFiles`, `LoadPointsFromFile`,
  `LoadPointsFromMultiSweeps`, `LoadAnnotations3D`, `ObjectPaste`, `GlobalRotScaleTrans`,
  `LoadBEVSegmentation`, `RandomFlip3D`, `PointsRangeFilter`, `ObjectRangeFilter`, `ObjectNameFilter`,
  `ImageNormalize`, `GridMask`, `PointShuffle`, `DefaultFormatBundle3D`, `Collect3D`.
- `load_dim: 5`, `use_dim: 5`, `reduce_beams: 32`, `point_cloud_range: [-54,-54,-5,54,54,3]`.
- Trong kernel clone ở `mit/bevfusion` (tương đối với cwd) nên đường dẫn tương đối dùng được.
- `spray.denoise.dror_filter(points, k=8, alpha=0.03)` trả `(keep_mask, stats)`.

## Nội dung file test

Đầu file: `pytest.importorskip("mmcv")`, `pytest.importorskip("mmdet3d")` ⇒ local **skip** (đúng ý), kernel chạy thật.

Dựng chain:
- `mmcv.Config.fromfile("mit/bevfusion/configs/nuscenes/default.yaml")`; nếu không có file ⇒ `pytest.skip`.
- Giữ **danh sách trắng 5 bước**: `GlobalRotScaleTrans`, `RandomFlip3D`, `PointsRangeFilter`,
  `ObjectRangeFilter`, `PointShuffle`.
- Nối: `[5 bước trên] + [PlumeTransform(...)] + [CleanPointsFormatBundle3D(...), CleanPointsCollect3D(...)]`
  (theo đúng docstring trong `spray/pipeline.py`; gọi `install()` trước).
- Sample dựng tay: `points` `(40000,5)` float32 uniform trong `[-54,-54,-5,54,54,3]`;
  `gt_boxes` = `LiDARInstance3DBoxes` 1 box tâm `(10,0,0.8)`, size `(4.5,1.9,1.6)`, velocity `(0,13.9,0)`;
  `gt_labels_3d=[0]`; `sample_idx=0`; không có key ảnh.

**4 test** (2 tên đầu là tên spec bắt buộc):
1. `test_three_arms_run_end_to_end` — A: plume off; B: plume on seed 0; B0: B rồi `dror_filter`.
   Assert A `n_injected == 0`, B và B0 `n_injected > 0`, cả 3 có `points_clean` trong batch output,
   không NaN/inf. Nếu `points_clean` mất ⇒ in rõ rồi `pytest.fail` (bug plumbing — báo PM, không tự sửa vendor).
2. `test_disabled_spray_leaves_points_unchanged` — plume off ⇒ `points` == `points_clean` byte-equal.
3. `test_streams_share_frame_and_aug_matrix` — `np.array_equal` trên `lidar_aug_matrix`; `sample_idx` giữ nguyên.
4. `test_inverse_aug_matrix_roundtrip` — 100 điểm: áp `lidar_aug_matrix` rồi nghịch đảo, `atol=1e-4`.

Tên field "số điểm đã chèn" và tên key matrix: **đọc đúng từ 2 file ở mục "Đọc trước"**, không đoán.

## Ràng buộc

- Chỉ tạo/sửa **1 file**: `tests/test_pipeline_e2e.py`. Không sửa `kaggle/e2e/main.py`, `spray/**`, `mit/**`.
- Không thêm dependency, không đổi `PlumeConfig`, không đổi tham số plume/denoise.
- Local: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **63 passed, 4 skipped**.
- Không bật background process, không gọi `kaggle`.

## Commit + báo cáo

```
test(e2e): prove both streams share one frame through the real transform chain
```
Dán: output pytest (1 dòng cuối), `git log --oneline -1`, `git status --porcelain`.