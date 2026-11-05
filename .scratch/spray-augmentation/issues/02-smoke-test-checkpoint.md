# 02: Smoke test checkpoint + một sample

**What to build:** Một lần chạy end-to-end trên một sample nuScenes: load checkpoint fused chính thức, forward model, và báo cáo missing/unexpected keys, output hữu hạn, và số channel của depth tensor khớp với `dtransform`. Ticket này chặn mọi thí nghiệm.

**Blocked by:** 01

**Status:** done

- [x] Checkpoint load được; missing/unexpected keys được liệt kê.
- [x] Forward một sample không lỗi shape.
- [x] Output không có NaN/Inf.
- [x] Depth tensor có đúng số channel mà transform nhận.
- [x] Kết quả được lưu vào report.

## Kết quả cuối — ALL_PASS (2026-11-05, chạy tay trên Kaggle)

`report.json` của session: cả 6 tiêu chí `true`.

| Mục | Số thật |
|---|---|
| Checkpoint | `matched_keys=582`, `missing_keys_total=0`, `unexpected_keys_total=0`, `shape_mismatch_count=0`, `size_bytes=163715701`, `sha256=ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122` (Dropbox mirror; URL gốc MIT 404) |
| Forward | `full_forward_ok=true`, `peak_gpu_mem_gb=1.98`, `seconds=0.6`, `trunk_only_fallback=false` |
| Depth | shape `[6,1,256,704]`, `depth_tensor_channels=1`, `dtransform_accepted_channels=1` (`Conv2d(1,8,1)`), `channels_match=true`, `V_C=80`, `V_D=118`, `feature_size=[32,88]`, `depth_spatial_size=[256,704]`, `nonzero_fraction=0.02359933592379093`, `finite=true` |
| Finite | stages `camera_bev/depth/fused_bev/decoder_neck=true`; head fields (heatmap, dim, rot, vel, ...) `true`; outputs `boxes_3d/scores_3d=true` |
| Env | Python 3.8.20, torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0, numpy 1.22.4; CUDA build 11.8/gcc-11, `cuda_guard_bypassed=false`; ops 12/12 + GPU smoke OK |
| Model | 40,800,087 params; `init_cfg_disabled=true` (bỏ tải Swin init vì fused checkpoint phủ đủ weight) |

Fix vòng cuối: bỏ tải Swin `init_cfg` trong `smoke_model.build` + đọc `out_channels` qua config
fallback. Chi tiết lịch sử: `02b-numba-fix.md`.

## Lịch sử: kernel version 9 (fail)

Checkpoint tải được (mirror Dropbox, `size_bytes=163715701`, `sha256=ee0a3892…2122`, đã ghi
vào `mit/PIN.md`). Model/checkpoint-load/forward **chưa** chạy được vì build `mmdet3d` CUDA
ops fail: thiếu `cusparse.h` trong `cuda-nvcc-11-8` và lỗi `_Float32` với nvcc 11.8 + gcc-13
trên Ubuntu 24.04. Vì vậy cả 5 checkbox trên vẫn `[ ]` và `missing_keys` / output shape /
`depth_tensor_channels` / `depth_tensor_nonzero_fraction` đều không có giá trị (`null`).
Chi tiết + traceback: `02b-numba-fix.md`.
