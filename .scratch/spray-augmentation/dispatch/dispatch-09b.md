# Ticket 09 — e2e qua chain thật (bản 2, đã có toạ độ chính xác)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · branch `main` · HEAD `60092a1`

> Lần chạy trước chết vì lỗi mạng sau 32 turn chỉ để **đọc file**. Brief này đã dò sẵn mọi đường dẫn.
> **Đừng đi thám hiểm vendor.** Chỉ đọc đúng 3 file ở mục "Đọc trước", rồi viết test.

## Đọc trước (đúng 3 file, không đọc thêm)

1. `spray/pipeline.py` — có `CleanPointsFormatBundle3D` / `CleanPointsCollect3D` + `install()`.
2. `spray/plume_transform.py` — `PlumeTransform` (tham số constructor + key `points_clean`).
3. `mit/bevfusion/configs/nuscenes/default.yaml` **dòng 55–175** — `train_pipeline` thật.

## Sự thật đã xác minh (dùng luôn, đừng kiểm lại)

- Config thật duy nhất có `train_pipeline`: **`mit/bevfusion/configs/nuscenes/default.yaml`**
  (các config `det/transfusion/...` chỉ có model, **không** có pipeline — đường dẫn cũ trong brief trước là sai).
- `train_pipeline` gồm: `LoadMultiViewImageFromFiles`, `LoadPointsFromFile`, `LoadPointsFromMultiSweeps`,
  `LoadAnnotations3D`, `ObjectPaste`, `GlobalRotScaleTrans`, `LoadBEVSegmentation`, `RandomFlip3D`,
  `PointsRangeFilter`, `ObjectRangeFilter`, `ObjectNameFilter`, `ImageNormalize`, `GridMask`,
  `PointShuffle`, `DefaultFormatBundle3D`, `Collect3D`.
- `load_dim: 5`, `use_dim: 5`, `reduce_beams: 32`, `point_cloud_range: [-54,-54,-5,54,54,3]`.
- Trong kernel, clone nằm ở `mit/bevfusion` **tương đối với cwd** (`/kaggle/working/repo`), nên đường dẫn
  tương đối chạy được. Không cần export env gì.

## Việc phải làm

### 1. `tests/test_pipeline_e2e.py` (file mới duy nhất)

- Đầu file: `pytest.importorskip("mmcv")`, `pytest.importorskip("mmdet3d")` ⇒ local **skip**, kernel chạy thật.
- Lấy `train_pipeline`: `mmcv.Config.fromfile("mit/bevfusion/configs/nuscenes/default.yaml")`; nếu file không
  tồn tại (local) thì `pytest.skip`. Lọc **danh sách trắng** các bước giữ lại:
  `GlobalRotScaleTrans`, `RandomFlip3D`, `PointsRangeFilter`, `ObjectRangeFilter`, `PointShuffle`.
  Bỏ mọi bước cần file thật (`Load*`, `ObjectPaste`, `LoadBEVSegmentation`, `Image*`, `GridMask`).
- Ghép chain: `[bước lọc từ config] + [PlumeTransform(cfg, enabled=…, seed=…)] + [CleanPointsFormatBundle3D
  + CleanPointsCollect3D]` (lấy từ `spray/pipeline.py`; gọi `install()` trước để có trong registry).
- Sample dựng tay: `points` `(40000,5)` float32 uniform trong `[-54,-54,-5, 54,54,3]`;
  `gt_boxes` = `LiDARInstance3DBoxes` 1 box tâm `(10,0,0.8)` size `(4.5,1.9,1.6)` velocity `(0,13.9,0)`;
  `gt_labels_3d=[0]`; `sample_idx=0`; **không** có key ảnh.
- **4 test** (2 tên đầu là tên spec bắt buộc):
  1. `test_three_arms_run_end_to_end` — A: plume off; B: plume on seed 0; B0: plume on seed 0 rồi
     `spray.denoise.dror_filter` trên `points`. Assert: A có `n_injected == 0`; B có `n_injected > 0`;
     B0 `n_injected > 0`; cả 3 `points_clean` **có mặt** trong batch output và không NaN/inf.
     Nếu `points_clean` rỗng/mất ⇒ **in rõ** rồi `pytest.fail` (đó là bug tầng plumbing, báo lại, không tự sửa vendor).
  2. `test_disabled_spray_leaves_points_unchanged` — plume off ⇒ `points` == `points_clean` byte-equal.
  3. `test_streams_share_frame_and_aug_matrix` — `np.array_equal` trên `lidar_aug_matrix` của 2 stream;
     `sample_idx` giữ nguyên.
  4. `test_inverse_aug_matrix_roundtrip` — 100 điểm ngẫu nhiên: áp `lidar_aug_matrix` rồi nghịch đảo ⇒ về chỗ cũ,
     `atol=1e-4`.
- Không `sleep`, không marker `slow`, không đọc/ghi file ngoài.

### 2. KHÔNG sửa gì khác

`kaggle/e2e/main.py` đã chạy `pytest -q tests/` nên file mới tự được chạy. **Không sửa `main.py`.**
Không sửa `spray/**`, `mit/**`, `third_party/**`, test cũ.

### 3. Push + chờ (foreground, không spawn poller)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/e2e
for i in $(seq 1 40); do kaggle kernels status nguynhuy9669/bevfusion-e2e; sleep 30; done   # dừng khi COMPLETE/ERROR
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9
```

Tối đa **2 lần push**. Log cần thấy: `pytest summary: rc=0 passed=67` và `E2E_OK`.

## Ràng buộc

- Local phải: **63 passed, 4 skipped** (`CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/`).
- Không đổi `PlumeConfig`, không đổi tham số sinh plume/denoise, không thêm dependency.
- Không bật background process.

## Nghiệm thu (dán số, không kể)

- Local: `passed`/`skipped`.
- Kernel: dòng `pytest summary:` + `E2E_OK`; nếu FAILED dán 40 dòng traceback cuối.
- `n_injected` của 3 arm (3 dòng) lấy từ log.
- `git log --oneline -1`, `git status --porcelain`.

## Commit

```
test(e2e): prove both streams share one frame through the real transform chain
```