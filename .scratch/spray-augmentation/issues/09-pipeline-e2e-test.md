# 09: End-to-end pipeline test

**What to build:** Một test chạy config thật qua transform chain đến collection với stub model ghi lại input, chứng minh hai stream cùng frame và đúng routing.

**Blocked by:** 07, 08

**Status:** **done** `c66e867` — kernel `68 passed, 0 skipped`, `E2E_OK`

## PM note 2026-11-07

Dependency ẩn đã phát hiện ở ticket 08: `points_clean` không tự tới `forward` (`DefaultFormatBundle3D`
chỉ wrap `points`/`radar`). Ticket 08 nhận luôn phần plumbing; ticket 09 chỉ **chứng minh e2e** trên config
thật. Nếu 09 thấy `points_clean` vẫn rỗng ⇒ đó là bug của 08, không phải lý do bỏ qua test.


- [x] Cả hai stream tồn tại và cùng frame sau augmentation. — `test_streams_share_frame_and_aug_matrix`:
  `points_clean` **byte-equal** với snapshot ngay tại thời điểm chèn, `len(points) == len(snapshot) + injected`.
- [x] Inverse `lidar_aug_matrix` trên một điểm đã biết cho đúng tọa độ. — `test_inverse_aug_matrix_roundtrip`.
- [x] Spray off thì hai stream tương đương. — `test_disabled_spray_leaves_points_unchanged`: `tobytes()` bằng nhau.
- [x] Test chạy được trên CPU. — local `64 passed, 4 skipped`; kernel `68 passed, 0 skipped` (10,4 s).

## PM nghiệm thu 2026-11-08

Năm lần push mới xanh thật. Ba lần đầu hỏng vì **wiring của test**, không phải code nghiên cứu:

| run | lỗi | sửa |
|---|---|---|
| 1 | `box_dim=7` trong khi box có vận tốc (9 cột) | `box_dim=9` (`93d160e`) |
| 2 | `KeyError: GlobalRotScaleTrans is not in the pipeline registry` | import module đăng ký (`8c135dc`) |
| 3 | thêm `import mmdet3d.datasets` → kéo `.nuscenes_dataset` → thiếu nuscenes-devkit ⇒ `ImportError` rơi vào `except` bao trùm ⇒ **4 test skip**, `E2E_OK` **xanh giả** | stub `mmdet3d.datasets` trong `sys.modules` + `importlib` nạp `pipelines.transforms_3d`; tách "thiếu thư viện" khỏi "đăng ký hỏng" (`0d129e4`) |
| 4 | `ValueError: could not convert string to float: '${point_cloud_range}'` | tự resolve `${...}` + lấy `point_cloud_range` từ config, không hardcode (`c66e867`) |
| 5 | — | `68 passed, 0 skipped`, `E2E_OK` ✅ |

Bài học ghi vào kỷ luật nghiệm thu: **`E2E_OK` một mình không phải bằng chứng** — phải đọc dòng tổng kết
pytest và kiểm **không có chữ `skipped`**. Run 3 `rc=0` chỉ vì 67 test bị skip.

Số đếm: 63 test cũ + 4 e2e + 1 resolver = **68**. Local skip 4 vì laptop không có `mmcv`.Ưu điểm phụ: lỗi
`${point_cloud_range}` phát hiện luôn rằng `point_cloud_range` của **dataset config là `[-51.2, …, 51.2]`**,
không phải `[-54, …]` (đó là model config).
