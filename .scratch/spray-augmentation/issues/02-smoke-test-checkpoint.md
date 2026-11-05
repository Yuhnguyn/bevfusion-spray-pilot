# 02: Smoke test checkpoint + một sample

**What to build:** Một lần chạy end-to-end trên một sample nuScenes: load checkpoint fused chính thức, forward model, và báo cáo missing/unexpected keys, output hữu hạn, và số channel của depth tensor khớp với `dtransform`. Ticket này chặn mọi thí nghiệm.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Checkpoint load được; missing/unexpected keys được liệt kê.
- [ ] Forward một sample không lỗi shape.
- [ ] Output không có NaN/Inf.
- [ ] Depth tensor có đúng số channel mà transform nhận.
- [ ] Kết quả được lưu vào report.

## Kết quả lần chạy 2026-11-05 (kernel version 9)

Checkpoint tải được (mirror Dropbox, `size_bytes=163715701`, `sha256=ee0a3892…2122`, đã ghi
vào `mit/PIN.md`). Model/checkpoint-load/forward **chưa** chạy được vì build `mmdet3d` CUDA
ops fail: thiếu `cusparse.h` trong `cuda-nvcc-11-8` và lỗi `_Float32` với nvcc 11.8 + gcc-13
trên Ubuntu 24.04. Vì vậy cả 5 checkbox trên vẫn `[ ]` và `missing_keys` / output shape /
`depth_tensor_channels` / `depth_tensor_nonzero_fraction` đều không có giá trị (`null`).
Chi tiết + traceback: `02b-numba-fix.md`.
