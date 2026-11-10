# Ticket 09 — e2e: config thật chạy hết chain, chứng minh 2 stream cùng frame

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · branch `main`
Đọc trước: `.scratch/spray-augmentation/issues/09-pipeline-e2e-test.md`,
`spray/plume_transform.py`, `spray/model_routing.py`, `spray/pipeline.py`, `spray/denoise.py` (vừa thêm),
`.scratch/spray-augmentation/history/spec-v1.md` dòng 271.

## Vì sao phải chạy trên Kaggle

Test này cần `mmdet3d` (transform + `DefaultFormatBundle3D` + `Collect3D`). Máy local **không có**. Nên:
test phải `pytest.importorskip("mmdet3d")` ở đầu để local **skip** (không fail), và chạy thật trong kernel
`kaggle/e2e`.

## Việc phải làm

### 1. `tests/test_pipeline_e2e.py` (file mới)

- Dòng đầu: `pytest.importorskip("mmdet3d")` + `pytest.importorskip("mmcv")`.
- **Config thật**: tìm theo thứ tự (dùng cái đầu tiên tồn tại):
  1. `$MIT_BEVFUSION_ROOT/configs/nuscenes/det/centerhead/lssfpn/camera+radar/resnet50/default.yaml`
  2. `mit/bevfusion/configs/nuscenes/det/centerhead/lssfpn/camera+radar/resnet50/default.yaml`
  3. bất kỳ `configs/nuscenes/det/centerhead/**/default.yaml` đầu tiên tìm thấy dưới 2 gốc trên
  Không tìm thấy ⇒ `pytest.skip("không thấy config thật")` kèm 2 đường dẫn đã thử. **Không** dựng config giả.
- **Chain**: lấy `train_pipeline` từ config thật, **giữ** các bước áp lên LiDAR
  (`GlobalRotScaleTrans`, `RandomFlip3D`, `PointShuffle` nếu có, `PlumeTransform`, `DefaultFormatBundle3D`, `Collect3D`),
  **bỏ** bước cần file thật (`LoadPointsFromFile`, `LoadMultiViewImageFromFiles`, `LoadAnnotations3D`, các bước ảnh).
  Nếu một bước cần file thật mà không bỏ được, bỏ nó và ghi chú trong docstring — nhưng **không** được thay
  `PlumeTransform`/`DefaultFormatBundle3D` bằng đồ giả.
- **Sample dựng tay** (dict đúng format mmdet3d): `points` `(40000,5)` float32 uniform trong
  `[-54,-54,-5, 54,54,3]`, `gt_boxes` 1 box `Box3DMode.LIDAR` tại `(10, 0, 0.8)` size `(4.5,1.9,1.6)` với
  velocity `(0, 13.9, 0)` (= 50 km/h), `gt_labels_3d = [0]`, `box_type_3d = LiDAR`, `sample_idx = 0`.
- **3 test đúng tên trong spec + 1 test bổ sung**:
  1. `test_three_arms_run_end_to_end` — arm A = plume off; arm B = plume on seed 0; arm B0 = plume on seed 0
     rồi `spray.denoise.ror_filter` trên `points`. Mỗi arm chạy chain 1 lần. Assert:
     - arm A: `n_injected == 0` và `points` == `points_clean` (byte-equal).
     - arm B: `n_injected > 0`; `len(points) == len(points_clean) + n_injected` sau lớp format.
     - arm B0: `n_injected > 0` và `len(points) <= len(points)` của arm B.
     - cả 3 arm: không NaN/inf; `points_clean` **còn tồn tại** trong batch output (đây là chỗ ticket 08
       nhận plumbing — nếu nó rỗng, đó là bug của 08, **báo lại, đừng tự sửa vendor**).
  2. `test_disabled_spray_leaves_points_unchanged` — như trên, chỉ arm A.
  3. `test_streams_share_frame_and_aug_matrix` — `points` và `points_clean` đi qua **cùng một**
     `lidar_aug_matrix` (so `np.array_equal`), `sample_idx` giữ nguyên.
  4. `test_inverse_aug_matrix_roundtrip` — lấy 100 điểm bất kỳ, áp `lidar_aug_matrix` rồi nghịch đảo ⇒ về
     vị trí ban đầu với `atol = 1e-4`.
- Không có `pytest.mark.slow`, không `time.sleep`.

### 2. `kaggle/e2e/main.py` — chỉ sửa nếu cần

Nó đã chạy `pytest -q tests/`, nên file test mới tự được chạy. **Chỉ** thêm (nếu chưa có) một dòng log sau
bước pytest:

```
log("E2E_09_OK" if tests_ok else "E2E_09_FAILED")
```

Đồng thời, nếu `MIT_BEVFUSION_ROOT` chưa được export cho pytest, export nó (thư mục chứa working copy
`mit/bevfusion` đã clone trong kernel) — **đây là sửa duy nhất được phép** ngoài file test. Không đổi pin,
không đổi wheels, không đổi thứ tự 7 bước.

### 3. Push + chờ (làm trong foreground, không spawn poller)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py   # dataset version mới
kaggle kernels push -p kaggle/e2e
kaggle kernels status nguynhuy9669/bevfusion-e2e      # lặp tới COMPLETE/ERROR, ngủ 30s giữa các lần
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9
```

Tối đa **2 lần push kernel**. Nếu lần 1 fail vì lý do môi trường, đọc log rồi sửa và push lần 2.

## Ràng buộc

- KHÔNG sửa `mit/**`, `third_party/**`, `spray/plume.py`, `spray/denoise.py`, các test cũ.
- KHÔNG đổi `PlumeConfig`, không đổi ngưỡng/tham số sinh plume.
- KHÔNG bật background process; mọi `sleep` nằm trong vòng `for` foreground.
- Local phải xanh: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **60 passed
  + 4 skipped** (file mới skip vì thiếu mmdet3d). Nếu local báo lỗi import thì sửa `importorskip`, không
  viết lại test.

## Nghiệm thu (dán bằng chứng, không kể)

- Local: số `passed`/`skipped`.
- Log kernel: dòng `pytest summary:` và `E2E_09_OK`; nếu FAILED thì dán nguyên traceback 30 dòng cuối.
- `git log --oneline -1`, `git status --porcelain`.
- Số `n_injected` của 3 arm (3 dòng), lấy từ log kernel.

## Commit

```
test(e2e): prove both streams share one frame through the real transform chain
```