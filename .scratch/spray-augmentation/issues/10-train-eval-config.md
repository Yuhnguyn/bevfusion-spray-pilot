# 10: Train/eval config A/B

**What to build:** Hai config chỉ khác nhau ở spray: cùng checkpoint, scene split, freeze list, optimizer, LR, seed, data order, batch size, và số update. Kèm memory/time probe trước khi train.

**Blocked by:** 02, 04, 09

**Status:** ready-for-agent

- [ ] Config A (clean) và B (spray) chỉ khác spray transform.
- [ ] Các yếu tố training giống nhau được ghi lại.
- [ ] Memory/time probe chạy trên T4.
- [ ] Freeze list được chốt: mở LiDAR encoder, fusion, BEV backbone/neck, head.
