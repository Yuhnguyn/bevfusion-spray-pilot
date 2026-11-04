# 02: Smoke test checkpoint + một sample

**What to build:** Một lần chạy end-to-end trên một sample nuScenes: load checkpoint fused chính thức, forward model, và báo cáo missing/unexpected keys, output hữu hạn, và số channel của depth tensor khớp với `dtransform`. Ticket này chặn mọi thí nghiệm.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Checkpoint load được; missing/unexpected keys được liệt kê.
- [ ] Forward một sample không lỗi shape.
- [ ] Output không có NaN/Inf.
- [ ] Depth tensor có đúng số channel mà transform nhận.
- [ ] Kết quả được lưu vào report.
