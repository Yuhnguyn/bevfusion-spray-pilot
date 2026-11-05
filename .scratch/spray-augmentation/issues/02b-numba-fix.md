# 02b: Sửa numba và chạy lại smoke test (bàn giao cho opencode)

**Trạng thái:** needs-triage
**Phụ thuộc:** ticket 02

## Bối cảnh

Kernel `nguynhuy9669/bevfusion-smoke-test` đã chạy lúc 06:27 ngày 2026-11-05 và kết thúc
`COMPLETE`, nhưng **không pass**:

```
SUMMARY support : checkpoint_obtained=true, config_invariants=true, env_pinned=true,
                  ops_built_and_gpu_smoke=true, pin_da93b27=true, model_built=FALSE
SUMMARY criteria: 1_checkpoint_loads=false  2_missing_unexpected_keys_listed=false
                  3_forward_no_shape_error=false  4_outputs_finite=false
                  5_depth_channels_match=false   6_report_saved=true
NOT_ALL_PASS
```

Nguyên nhân duy nhất: `ModuleNotFoundError: No module named 'numba'`.

```
File ".../mmdet3d/models/heads/bbox/centerpoint.py", line 8
  from mmdet3d.core import circle_nms, draw_heatmap_gaussian, gaussian_radius, xywhr2xyxyr
File ".../mmdet3d/core/post_processing/box3d_nms.py", line 1
  import numba
ModuleNotFoundError: No module named 'numba'
```

Cả ba cell `step_model.py`, `step_checkpoint.py`, `step_forward.py` đều chết ở import này, nên 5 tiêu
chí false là **hệ quả của một lỗi**, không phải 5 lỗi riêng. Repo MIT không khai báo `numba` trong
`requirements/`, nên bước tạo venv không cài.

Môi trường đã pin (đừng đổi): Python 3.8.20, `numpy==1.22.4`, `torch==1.10.1+cu113`,
`mmcv-full==1.4.0`, `mmdet==2.20.0`. Vì vậy numba phải là **0.58.1** — bản cuối còn hỗ trợ Python 3.8
và numpy 1.22.x.

## Việc phải làm

1. Trong `kaggle/smoke_test/bevfusion-smoke-test.ipynb`, cell **"Install the pinned stack into the
   Python 3.8 venv"**, thêm `"numba==0.58.1"` vào cùng command `uv pip install` đang cài
   mmcv/mmdet. Không sửa gì khác trong cell, không sửa các cell khác.
2. Push kernel: `kaggle kernels push -p kaggle/smoke_test`, sau đó chờ
   `kaggle kernels status nguynhuy9669/bevfusion-smoke-test` báo `COMPLETE`.
3. Tải output: `kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p <thư mục tạm>`, đọc
   `smoke_test/state.json` và `bevfusion-smoke-test.log`.
4. Báo lại đúng 5 tiêu chí `1_checkpoint_loads`, `2_missing_unexpected_keys_listed`,
   `3_forward_no_shape_error`, `4_outputs_finite`, `5_depth_channels_match`, kèm số thật:
   danh sách missing/unexpected keys, shape của output, `depth_tensor_channels`,
   `depth_tensor_nonzero_fraction`.
5. Ghi kết quả vào repo:
   - `mit/PIN.md`: thêm mục checkpoint. URL chính
     `https://bevfusion.mit.edu/files/pretrained/bevfusion-det.pth` trả **404** (redirect sang hanlab
     cũng 404); bản chạy được là mirror Dropbox `.../bevfusion-det.pth?rlkey=...`; kèm `sha256` lấy
     từ `state.json`.
   - `.scratch/spray-augmentation/issues/02-smoke-test-checkpoint.md`: tick các checkbox đã đạt, ghi
     số thật, cập nhật `Status` cho đúng (đạt hết → `done`).
   - Nếu vẫn fail: dán traceback mới vào ticket và **dừng**, không tự đổi version.
6. Commit trên nhánh hiện tại (`main`):
   `kaggle/smoke: add numba==0.58.1 and rerun smoke test (ticket 02)`

## Ràng buộc

- Không sửa code trong `mit/bevfusion`. Không đổi pin `da93b27`.
- Không upgrade/hạ `torch`, `numpy`, `mmcv-full`, `mmdet`.
- Không commit output tải từ Kaggle (`state.json`, log) trừ khi cần làm bằng chứng và < 50 KB; ưu
  tiên trích số vào ticket.
- Nếu Kaggle từ chối vì quota GPU, dừng và báo lại, không tìm workaround.

## Xong khi

- Kernel chạy lại xong; ticket 02 có bảng 5 tiêu chí với giá trị thật.
- `mit/PIN.md` có mirror checkpoint + sha256.
- `git status` sạch sau commit.

## Lần chạy lại 2026-11-05 — DỪNG (chưa đạt 5 tiêu chí)

### Version 8 — lỗi bootstrap, trước khi tới `numba`

Đã thêm `numba==0.58.1` vào command cài đặt và push version 8. Kernel kết thúc
`KernelWorkerStatus.ERROR` sau ~15 giây, **trước khi** chạy tới model/checkpoint/forward,
vì hai lỗi có sẵn trong notebook (đã có trong commit `83c6bce`, không phải do thay đổi của
ticket này và không liên quan `numba`).

#### Lỗi 1 — `uv` không resolve được torch (cell "Install the pinned stack...")

```
$ uv pip install --python /root/bevfusion_smoke/env/bin/python \
    --index-url https://download.pytorch.org/whl/cu113 \
    --extra-index-url https://pypi.org/simple \
    "torch==1.10.1+cu113" "numpy==1.22.4"
error: No solution found when resolving dependencies
  cause: Because there is no version of torch==1.10.1+cu113 and you require
         torch==1.10.1+cu113, we can conclude that your requirements are unsatisfiable.

hint: `torch` was found on https://pypi.org/simple, but not at the requested version
(torch==1.10.1+cu113). ... By default, uv will only consider versions that are published
on the first index that contains a given package ... If all indexes are equally trusted,
use `--index-strategy unsafe-best-match` ...
[exit=1 in 0.3s]
STEP FAILED (rc=1): uv pip install ... "torch==1.10.1+cu113" "numpy==1.22.4"
```

Hệ quả: `step_env.py` chết với `ModuleNotFoundError: No module named 'torch'`; venv lúc đó
chỉ có `ninja`, `packaging`, `pyparsing`, `setuptools`, `wheel`.

#### Lỗi 2 — format string của `git log` không escape `%` (cell "Clone MIT BEVFusion...")

```
Exception encountered at "In [5]":
  File "<cell line: 0>", line 30
    report["log1"] = sc.capture('git -C "%s" log -1 --format="%H %ci %s"' % sc.REPO)
TypeError: not enough arguments for format string
```

Hai fix bootstrap đã được áp vào notebook (`--format="%%H %%ci %%s"` và
`--index-strategy unsafe-best-match`), rồi version 9 được push và chạy `COMPLETE` sau
~104 giây.

### Version 9 — bootstrap đạt, build CUDA ops fail

```
SUMMARY support : checkpoint_obtained=true, config_invariants=true, env_pinned=true,
                  pin_da93b27=true, cuda_11x_toolkit=11.8,
                  model_built=FALSE, ops_built_and_gpu_smoke=FALSE
SUMMARY criteria: 1_checkpoint_loads=false  2_missing_unexpected_keys_listed=false
                  3_forward_no_shape_error=false  4_outputs_finite=false
                  5_depth_channels_match=false  6_report_saved=true
NOT_ALL_PASS
```

| # | Tiêu chí | Kết quả | Số thật / lý do |
|---|---|---|---|
| 1 | `1_checkpoint_loads` | **false** | model không build được nên `step_checkpoint` không chạy; `missing_keys`, `unexpected_keys`, `matched_keys` đều `null` |
| 2 | `2_missing_unexpected_keys_listed` | **false** | cùng lý do; không có danh sách key nào được tính |
| 3 | `3_forward_no_shape_error` | **false** | `forward=null`; không có output shape |
| 4 | `4_outputs_finite` | **false** | `finite_check=null` |
| 5 | `5_depth_channels_match` | **false** | `depth_check=null`; không có `depth_tensor_channels` / `depth_tensor_nonzero_fraction` |
| 6 | `6_report_saved` | **true** | `artifacts/report.json` |

Bước tải checkpoint **đạt**: `served_by` = mirror Dropbox, `size_bytes=163715701`,
`sha256=ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`
(đã ghi vào `mit/PIN.md`).

Build ops (`build_rc=1`, `ops_ok=false`) fail ở hai chỗ:

```
.../torch/include/ATen/cuda/CUDAContext.h:6:10: fatal error: cusparse.h: No such file or directory
...
/usr/include/x86_64-linux-gnu/bits/mathcalls.h(110): error: identifier "_Float32" is undefined
100 errors detected in the compilation of ".../spconv/src/reordering_cuda.cu".
```

Toolchain lúc build: `cuda-nvcc-11-8` cài bằng apt (chỉ có nvcc, thiếu header cuSPARSE),
`gcc-13`/`g++-13`, base image Ubuntu 24.04 (glibc mới). `step_model.py` sau đó chết với
`ModuleNotFoundError: No module named 'mmdet3d'`.

Theo ticket: **dừng**, không tự đổi version. Đề xuất (chờ duyệt, không đổi pin
torch/numpy/mmcv/mmdet): cài đủ CUDA 11.8 dev libraries (`cuda-libraries-dev-11-8`, hoặc
`libcusparse-dev-11-8` + `libcublas-dev-11-8`) và/hoặc build bằng `gcc-11`/`gcc-12` thay
cho `gcc-13`; đây là thay đổi toolchain, không phải đổi version của stack đã pin.

`numba==0.58.1` + hai fix bootstrap nằm trong working tree nhưng **chưa commit** vì kernel
chưa pass. `mit/PIN.md` đã có checkpoint + sha256; ticket 02 chưa được tick.