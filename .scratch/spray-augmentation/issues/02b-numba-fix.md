# 02b: Sửa môi trường và chạy lại smoke test (brief cho CommandCode)

**Trạng thái:** ready-for-agent
**Phụ thuộc:** ticket 02
**Chủ:** CommandCode (code + chạy Kaggle). PM: Hermes — chỉ chốt phạm vi, tiêu chí, không sửa code.
**Cập nhật:** 2026-11-05 16:00

## Brief (đọc mục này trước, phần dưới là lịch sử)

**Một câu:** làm cho kernel `nguynhuy9669/bevfusion-smoke-test` đạt cả 6 tiêu chí trong
`artifacts/report.json`, rồi ghi số thật vào ticket 02 và `mit/PIN.md`.

**Đang ở đâu (đã xác minh, không cần điều tra lại):**

| Version | Toolkit chọn | Kết quả | Kết luận |
|---|---|---|---|
| 8 | — | chết ở bootstrap | đã fix (uv index strategy + escape `%` trong `git log --format`) |
| 9 | CUDA 11.8 | fail `cusparse.h` | thiếu CUDA dev headers, host compiler là gcc-13 |
| 10 | CUDA 13 + bypass guard | fail | tên package `cuda-cusparse-dev-11-8` không tồn tại → apt exit 100 → mất cả nvcc 11 |
| 11 | CUDA 11.8, không bypass | fail `cusolverDn.h` | gcc-11 + cusparse/cublas/curand đã OK; thiếu cusolver |
| 13 | CUDA 11.8, gcc-11 | ops + GPU smoke **OK**, checkpoint load 0 missing / 0 unexpected, nhưng harness chết ở `vtransform.out_channels` | class `DepthLSSTransform` không có attribute đó — lỗi của harness, không phải của model |
| 14 | CUDA 11.8, gcc-11 | **3/6 tiêu chí** (1, 2, 6 true); `model_built=false` | cùng lỗi harness; fix đã commit `e3b4c08` nhưng lần chạy này xảy ra **trước** commit đó nên chưa có tác dụng |
| 15 | chưa chạy | — | cần push lại với fix `e3b4c08` + `71a7ab1` |

**Trạng thái đã xác minh bằng `report.json` của lần chạy mới nhất (không phải all-pass):**

```
support : checkpoint_obtained=true  env_pinned=true  pin_da93b27=true
          cuda_11x_toolkit="11.8"   cuda_guard_bypassed=false
          ops_built_and_gpu_smoke=TRUE   model_built=FALSE
criteria: 1=true  2=true  3=false  4=false  5=false  6=true
```

Đã đạt và không cần làm lại: build 11 CUDA extension (`build_rc=0`), GPU smoke trên T4, checkpoint load sạch
(0 missing / 0 unexpected key), pin đúng. **Còn thiếu đúng một thứ:** harness dựng sai chỗ đọc thuộc tính
của `DepthLSSTransform` — đọc `vtransform.out_channels` trong khi class đó lấy `out_channels` từ config.
Fix đã nằm trong working tree/commit; việc còn lại chỉ là push lại.

**Việc tiếp theo duy nhất (v13):** thêm `"torchvision==0.11.2+cu113"` vào **cùng** command `uv pip install`
đang cài `torch==1.10.1+cu113` trong cell 4, giữ nguyên `--index-strategy unsafe-best-match`.
Lý do: `mmdet3d/ops/__init__.py` → `mmcv.ops` → `torchvision` → `ModuleNotFoundError`. torchvision 0.11.2
là bản khớp cứng với torch 1.10.1, không đổi version nào khác. Push lại và đọc `ops.json`.
Dự phòng: sau `torchvision` có thể còn thiếu `pycocotools` (chỉ cần cho eval, không cần cho forward) —
nếu lỗi, xử từng gói một, ghi vào bảng dưới, không cài theo lô.

**Bằng chứng v12 (đã đạt, không cần làm lại):** `pin_da93b27=true`, `env_pinned=true`,
`config_invariants=true`, `cuda_11x_toolkit="11.8"`, `cuda_guard_bypassed=false`,
`checkpoint_obtained=true` (mirror Dropbox), `build_rc=0`, 11 extension `.so` đã copy vào
`site-packages/mmdet3d`, GPU `Tesla T4` ×2, `TORCH_CUDA_ARCH_LIST=7.5`.

**Việc phải làm, theo thứ tự:**

0. `kaggle kernels status nguynhuy9669/bevfusion-smoke-test`. Nếu v12 đã `COMPLETE` thì nhảy tới bước 3.
1. Nếu v12 `ERROR` hoặc ops vẫn fail: `kaggle kernels output ... -p /tmp/k` rồi
   `grep -n "fatal error" /tmp/k/smoke_test/logs/build_ops.log | head`. Cài đúng gói cho header thiếu,
   **mỗi gói một lệnh `apt-get install` riêng**:
   `cusparse.h`→`libcusparse-dev-11-8`, `cublas_v2.h`/`cublasLt.h`→`libcublas-dev-11-8`,
   `curand.h`→`libcurand-dev-11-8`, `cusolverDn.h`→`libcusolver-dev-11-8`,
   `cufft.h`→`libcufft-dev-11-8`, `nvToolsExt.h`→`cuda-nvtx-11-8`.
   Push lại: `kaggle kernels push -p kaggle/smoke_test`. Lặp tối đa 3 vòng, sau đó dừng và báo PM.
2. Kiểm tra điều kiện tiên quyết trước khi tin bất kỳ tiêu chí nào: `SUMMARY support` phải có
   `cuda_11x_toolkit: "11.8"`, `cuda_guard_bypassed: false`, `ops_built_and_gpu_smoke: true`.
   Nếu vẫn `13.0`/`bypassed: true` thì cả 5 tiêu chí false là hệ quả — quay lại bước 1, đừng đọc tiếp.
3. Đọc `artifacts/model.json`, `checkpoint.json`, `forward.json` + `state.json`; điền bảng 5 tiêu chí
   vào `.scratch/spray-augmentation/issues/02-smoke-test-checkpoint.md` với số thật
   (missing/unexpected keys, output shape, `depth_tensor_channels`, `depth_tensor_nonzero_fraction`).
4. Ghi vào `mit/PIN.md`: `served_by` = mirror Dropbox (URL chính thức trả 404) + sha256
   `ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`.
5. Commit, `git status` sạch, báo PM: 6 tiêu chí kèm giá trị thật + hash commit.

**Ràng buộc (không thương lượng):**

- Không đổi pin `da93b27`, không đổi `torch 1.10.1+cu113`, `numpy 1.22.4`, `mmcv-full 1.4.0`, `mmdet 2.20.0`.
- Không sửa code trong `mit/bevfusion`. Chỉ được sửa `kaggle/smoke_test/*`.
- macOS: **không có lệnh `timeout`**. Đừng bọc lệnh CLI bằng `timeout`.
- Không commit output Kaggle (`state.json`, log) — chỉ trích số vào ticket.
- Quota GPU bị từ chối → dừng, báo PM. Không tìm workaround.

**Nghiệm thu của PM (đủ cả 4 mới tính xong):**

1. `report.json` có 6/6 tiêu chí `true`, và `ops_built_and_gpu_smoke: true`.
2. Bảng 5 tiêu chí trong ticket 02 có giá trị thật, không có ô `null`.
3. `mit/PIN.md` có mirror + sha256 + ghi chú URL chính thức 404.
4. Tree sạch, commit message nêu rõ version kernel đã pass.

**Ngoài phạm vi (đừng làm trong ticket này):** tạo `nuscenes_infos_{train,val}.pkl` (ticket 04), sửa
`spray/plume.py`, viết arm B0, viết spec v1.5. Mỗi thứ đó là ticket riêng.

---

# Lịch sử ticket (giữ nguyên làm bằng chứng)

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

`numba==0.58.1` + hai fix bootstrap nằm trong commit `7addff3`. `mit/PIN.md` đã có checkpoint + sha256;
ticket 02 chưa được tick.

## Bàn giao 15:45 ngày 2026-11-05 — dừng giữa chuỗi fix toolchain

Người dùng chuyển việc này cho công cụ khác. Trạng thái thật, không tô hồng:

### Đã xác định nguyên nhân (v10, v11)

Hai lỗi toolchain, **độc lập với `numba`**, đều nằm trong cell "Pick a CUDA toolkit":

1. **Không có CUDA dev headers.** Cell chỉ cài `cuda-nvcc-11-8 cuda-cudart-dev-11-8`, nên
   `ATen/cuda/CUDAContext.h` không tìm thấy `cusparse.h`, rồi `cusolverDn.h`.
2. **Host compiler quá mới.** Image Kaggle hiện chỉ có `gcc-13`; CUDA 11.8 dùng gcc-13 làm host
   compiler thì nvcc chết với `identifier "_Float32" is undefined` trong `/usr/include/stdlib.h`.
   Cờ `--allow-unsupported-compiler` trong cell build chỉ tắt cảnh báo, không làm nó compile được.

Ngoài ra tên package gói dev của NVIDIA trong repo ubuntu2204 là `lib*-dev-11-8`, **không phải**
`cuda-cusparse-dev-11-8`. Dùng sai tên thì `apt-get` trả `exit 100` và **không cài gì cả** — kể cả
nvcc, khiến cell rơi xuống nhánh CUDA 13 + bypass guard (v10: `cuda_11x_toolkit: "13.0"`,
`cuda_guard_bypassed: true`, ops fail ngay).

### Đã sửa trong working tree (chưa commit)

`kaggle/smoke_test/bevfusion-smoke-test.ipynb`, cell 4, 5, 6:

| Cell | Sửa | Lý do |
|---|---|---|
| 4 (pinned stack) | `--index-strategy unsafe-best-match` | uv chỉ xét index đầu tiên chứa `torch`, nên `torch==1.10.1+cu113` (chỉ có trên pytorch index) bị coi là không tồn tại |
| 5 (clone/pin) | `--format="%%H %%ci %%s"` | chuỗi `%` bị Python hiểu là format → `TypeError: not enough arguments for format string` |
| 6 (toolchain) | `apt-get install gcc-11 g++-11` khi máy chỉ có gcc-13 | CUDA 11.8 + gcc-13 → `_Float32` undefined |
| 6 (toolchain) | tách lệnh apt: `cuda-nvcc-11-8 cuda-cudart-dev-11-8`, rồi `libcusparse-dev-11-8 libcublas-dev-11-8 libcurand-dev-11-8`, rồi `libcusolver-dev-11-8` | gói dev đúng tên; tách ra để một tên sai không kéo sập cả toolkit |

### Kết quả từng version

| Version | Toolkit | Ops build | Ghi chú |
|---|---|---|---|
| 8 | — | không chạy tới | chết ở bootstrap (uv + format string) |
| 9 | 11.8 | fail: `cusparse.h` | thiếu dev headers, host compiler gcc-13 |
| 10 | 13.0 + bypass | fail | tên package `cuda-cusparse-dev-11-8` sai → apt exit 100 → mất luôn nvcc 11 |
| 11 | **11.8, không bypass** | fail: `cusolverDn.h` | gcc-11 OK, cusparse/cublas/curand OK; thiếu mỗi cusolver |
| 12 | 11.8 | **chưa biết** | thêm `libcusolver-dev-11-8`; đang chạy lúc bàn giao |

### Việc còn lại

1. Chờ hoặc chạy lại v12:
   ```
   kaggle kernels push -p kaggle/smoke_test
   kaggle kernels status nguynhuy9669/bevfusion-smoke-test
   mkdir -p /tmp/k && kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k
   ```
   (macOS không có lệnh `timeout`; đừng bọc bằng `timeout`.)
2. Nếu ops vẫn fail: `grep -n "fatal error" /tmp/k/smoke_test/logs/build_ops.log | head` rồi cài đúng
   gói theo header thiếu — `cusparse.h`→`libcusparse-dev-11-8`, `cublas_v2.h`/`cublasLt.h`→
   `libcublas-dev-11-8`, `curand.h`→`libcurand-dev-11-8`, `cusolverDn.h`→`libcusolver-dev-11-8`,
   `cufft.h`→`libcufft-dev-11-8`, `nvToolsExt.h`→`cuda-nvtx-11-8`. Mỗi gói một lệnh apt riêng.
3. Khi `ops_ok=true`: đọc `artifacts/model.json`, `checkpoint.json`, `forward.json` và điền bảng 5
   tiêu chí vào ticket 02; ghi `served_by` + `sha256` vào `mit/PIN.md` (sha256 đã có:
   `ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`).
4. Không đổi pin `da93b27`, không đổi `torch/numpy/mmcv/mmdet`. Chỉ toolchain và gói hệ thống.

### Bài học cho lần sau

- Đừng gộp nhiều package chưa kiểm tra tên vào một `apt-get install`: sai một tên là mất cả lệnh.
- `cuda_guard_bypassed: true` trong `artifacts/cuda_toolchain.json` là dấu hiệu **sai hướng**, không
  phải thành công: ops build gần như chắc chắn fail với nvcc 13 + torch 1.10.
- Kiểm tra nhanh sau khi push: `SUMMARY support` phải có `cuda_11x_toolkit: "11.8"` **và**
  `ops_built_and_gpu_smoke: true` trước khi tin bất kỳ tiêu chí nào.

### Version 12 — CUDA/toolchain OK, ops compiled, nhưng thiếu `torchvision`

Kernel `COMPLETE` (version 12). Bootstrap + toolchain đạt:
- `cuda_11x_toolkit: "11.8"`, `cuda_guard_bypassed: false`, `gcc_chosen: /usr/bin/gcc-11`
- `cuda-nvcc-11-8` + `cuda-cudart-dev-11-8` + `libcusparse/libcublas/libcurand/libcusolver-dev-11-8` cài OK
- Checkpoint tải OK (Dropbox mirror, `sha256=ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`)
- Config invariants OK, pin `da93b27` OK

Build ops (`build_ops.json`): `build_rc=0`, `ops_check_rc=0`, `skipped=false`, CUDA 11.8/gcc-11, arch 7.5 (T4). Các `.so` được copy vào `mmdet3d/ops/*` (spconv, bev_pool, iou3d, voxel, roiaware_pool3d, ball_query, knn, paconv, group_points, interpolate, furthest_point_sample, gather_points).

Nhưng ops smoke (`ops.json`) fail toàn bộ: `ModuleNotFoundError: No module named 'torchvision'`. Root cause: `mmcv` (runner/checkpoint) import `torchvision` khi `mmdet3d.ops.__init__` kéo `mmcv.ops`. Vì `ops_ok=false` nên model/checkpoint-load/forward không chạy.

5 tiêu chí ticket 02 vẫn `false` (cùng hệ quả: ops smoke chưa pass).

Fix tiếp theo (đã áp vào notebook, chưa push lúc ghi): thêm `torchvision==0.11.2+cu113` (pair với `torch==1.10.1+cu113`) vào bước cài pinned stack. Không đổi pin torch/numpy/mmcv/mmdet.


### Version 13 — ops OK, model build fail (`train_cfg` attr access)

Kernel `COMPLETE` (version 13).
- `cuda_11x_toolkit: "11.8"`, `cuda_guard_bypassed: false`, `ops_built_and_gpu_smoke: true` ✅
- `torchvision==0.11.2+cu113` cài OK; tất cả extensions import OK; GPU smoke `bev_pool` + `voxelize` OK.
- Checkpoint tải OK (Dropbox mirror, sha256 đã ghi).

Blocker mới: `step_model.py` / `step_checkpoint.py` / `step_forward.py` fail:
`AttributeError: TransFusionHead: 'dict' object has no attribute 'assigner'`
tại `mmdet3d/models/heads/bbox/transfusion.py:208` (`if isinstance(self.train_cfg.assigner, dict):`).
Nguyên nhân: resolved config được nạp từ dict/JSON nên `train_cfg` là plain `dict`, nhưng mmcv 1.4.0/mmdet3d pin này dùng attribute access (`.assigner`). Đây là lỗi smoke harness (không phải pin stack).

Fix (áp dụng cho v14, chưa push lúc ghi): trong `smoke_model.build`, wrap `cfg_model` bằng `mmcv.ConfigDict` đệ quy trước `build_model`. Không đổi pin.


### Version 14 — checkpoint + ops OK, forward/model harness fail (`vtransform.out_channels`)

Kernel `COMPLETE` (version 14). Tiến bộ lớn:
- `cuda_11x_toolkit: "11.8"`, `cuda_guard_bypassed: false`, `ops_built_and_gpu_smoke: true` ✅
- `env_pinned: true`, `pin_da93b27: true`, `config_invariants: true`, `checkpoint_obtained: true` ✅
- Checkpoint (`checkpoint.json`): `sha256=ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`, 163,715,701 B, served by Dropbox mirror; **582/582 matched, missing 0, unexpected 0, shape_mismatch 0**, `cross_check_mmcv.ok=true`, `load_seconds=0.21`.
- Tiêu chí 1,2,6 đạt. 3,4,5 `false` vì `model_built:false` / `forward/depth_check/finite_check=null` (harness crash, không phải lỗi checkpoint).

Blocker harness mới:
- `step_model.py:57`: `AttributeError: 'DepthLSSTransform' object has no attribute 'out_channels'`
- `step_forward.py:268`: cùng lỗi (`V_C = int(vtransform.out_channels)`), dù forward đã chạy tới head (có Swin download + warning transfusion). `model.json`/`forward.json` không được ghi.

Fix (đã patch notebook local, chưa push): đọc `out_channels` từ `getattr(vtransform,'out_channels', cfg['model']['encoders']['camera']['vtransform']['out_channels'])` trong `step_model`/`step_forward` embedded scripts. Không đổi pin.

**Hành động đề xuất cho lần chạy tay (session Kaggle mới):** sửa `out_channels` như trên → chạy `01-bootstrap` (nếu sửa qua notebook) → rerun `11-model,12-checkpoint-load,13-batch,14-forward,15-report` (hoặc bundle). Không cần rebuild ops/venv nếu session cũ còn; nếu session mới thì run full nhưng bug harness đã vá.


### Version 15 (chạy tay) — ALL_PASS

Chạy cell-by-cell trong session Kaggle (sau khi vá `smoke_model.build` để bỏ tải Swin init_cfg):

```
SUMMARY support : checkpoint_obtained=true, config_invariants=true, env_pinned=true,
                  ops_built_and_gpu_smoke=true, pin_da93b27=true,
                  cuda_11x_toolkit=11.8, cuda_guard_bypassed=false, model_built=true
SUMMARY criteria: 1_checkpoint_loads=true  2_missing_unexpected_keys_listed=true
                  3_forward_no_shape_error=true  4_outputs_finite=true
                  5_depth_channels_match=true   6_report_saved=true
ALL_PASS
```

Model: 40,800,087 params; `DepthLSSTransform` out_channels=80, D=118, feature_size [32,88],
dtransform first layer `Conv2d(1, 8, 1)`; init_cfg disabled (Swin download skipped) — fused
checkpoint cung cấp đủ weight.

Fix cuối: `smoke_model.build` đặt `cfg_model["encoders"]["camera"]["backbone"]["init_cfg"]=None`
trước `build_model` (đã đưa vào notebook local). Ticket 02 đạt; cập nhật số cụ thể từ
`artifacts/report.json` của session.
