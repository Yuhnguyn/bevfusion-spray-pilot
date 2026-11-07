# 07: Pipeline transform + clean points

**What to build:** Một transform trong pipeline mmdet3d bọc core generator: chèn spray plume, giữ **clean points** trước khi chèn, và đưa cả hai stream qua format/collect. Chạy được trên một sample thật với spray off/on.

**Blocked by:** 01, 04

**Status:** done

- [x] Transform chạy sau geometric augmentation và range filter, trước `PointShuffle`.
- [x] `points_clean` được tạo đúng thời điểm và format/collect đầy đủ.
- [x] Spray off thì `points_clean` không xuất hiện hoặc bằng `points`.
- [x] Smoke test trên một sample thật pass.

## Kết quả (Kaggle latest, 2026-11-07)

- Code: `spray/plume_transform.py` (wrap `inject_plume`; optional mmdet3d register);
  notebook cell 19 dựng `scene-0796` (40 val infos) và chạy smoke.
- `ticket07_transform.json`: pipeline có `PlumeTransform` sau `PointsRangeFilter`;
  dropped `LoadBEVSegmentation` + `Collect3D.gt_masks_bev`.
- Frame 0 token `c1676a2f…` (21 GT): points_clean **255,456** → points **255,583**
  (+127 điểm); stats: 2 box eligible, 5 skipped_no_velocity, 11 skipped_low_speed,
  4 cluster, 0 rejected_range/box, 0 capped.
- 12/12 checks true: spray off clean == points; injected khớp stats; điểm chèn không
  nằm trong GT box; deterministic cùng seed; đúng thứ tự pipeline; `points_clean`
  được collect và collate.
- Patch runtime `mmdet3d/datasets/pipelines/formating.py` để wrap `points_clean`
  (nằm trong cell 19; không sửa repo MIT vĩnh viễn).
- Test laptop: `tests/test_plume_transform.py` (off/on) + full suite 33 passed.
