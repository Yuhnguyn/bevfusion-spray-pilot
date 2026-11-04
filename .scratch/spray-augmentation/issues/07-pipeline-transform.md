# 07: Pipeline transform + clean points

**What to build:** Một transform trong pipeline mmdet3d bọc core generator: chèn spray plume, giữ **clean points** trước khi chèn, và đưa cả hai stream qua format/collect. Chạy được trên một sample thật với spray off/on.

**Blocked by:** 01, 04

**Status:** ready-for-agent

- [ ] Transform chạy sau geometric augmentation và range filter, trước `PointShuffle`.
- [ ] `points_clean` được tạo đúng thời điểm và format/collect đầy đủ.
- [ ] Spray off thì `points_clean` không xuất hiện hoặc bằng `points`.
- [ ] Smoke test trên một sample thật pass.
