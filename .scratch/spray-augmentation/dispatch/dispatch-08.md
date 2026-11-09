Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`  ← quy ước repo, đọc trước
2. `.scratch/spray-augmentation/STATUS.md`
3. `.scratch/spray-augmentation/issues/08-model-forward-routing.md`  ← ticket, nguồn đúng
4. `spray/plume_transform.py` — hiểu `points` vs `points_clean` được sinh ra thế nào
5. `docs/PROJECT.md` §4 (cơ chế sinh plume) + §5 (luồng dữ liệu)

## Nhiệm vụ — ticket 08: model forward routing

Hiện tại cả hai nhánh của fusion model đều nhận `points` (đã có spray). Phải patch để:

- **nhánh camera** (đường depth supervision) nhận `points_clean`
- **nhánh LiDAR** nhận `points` (giữ nguyên)
- **tương thích ngược**: nếu không có `points_clean` trong batch thì hành vi **y hệt** hiện tại

Anchor để tìm (đừng tin số dòng, tìm theo tên hàm):
`third_party/bevfusion/mmdet3d/models/fusion_models/bevfusion.py` — `BEVFusion.forward(...)` (~dòng 274)
nhận `img, points, radar_points, ...`; phần camera branch dựng depth GT từ `points`.

Nếu `AGENTS.md` nói `third_party/` là vendor không được sửa: **DỪNG**, báo PM kèm 2 phương án
(patch trong `spray/` bằng wrapper/subclass, hoặc patch vendor + ghi lý do). Đừng tự chọn.

## Xong khi

- [ ] Camera path nhận `points_clean`; LiDAR path nhận `points`.
- [ ] Test **stub model** xác nhận routing **bằng shape + marker value**: đặt giá trị đánh dấu khác nhau
      trong `points` và `points_clean`, assert nhánh nào thấy marker nào. Không chỉ assert shape.
- [ ] Test trường hợp **không có** `points_clean` → hành vi như cũ (không crash).
- [ ] Không đổi kiến trúc, không đổi số tham số: thêm assert/kiểm tra số param trước = sau trong test.
- [ ] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥ 36 passed**
      (baseline hiện tại **35**, ngày 2026-11-07; số thật khác thì DỪNG báo PM).
- [ ] Commit: `feat(model): route clean points to camera branch, sprayed points to lidar branch`

## Ràng buộc cứng

- Không sửa `spray/plume.py` (generator vừa chốt, mọi thay đổi ở đó đều sai ticket).
- Không đổi tham số `PlumeConfig`.
- Không sửa 35 test cũ để dễ qua.
- Không thêm dependency mới; test phải chạy CPU, không cần GPU/mmcv-full nếu repo đã có stub.
- Nếu phải đổi interface công khai của `forward` (thêm kwarg): làm **tuỳ chọn** (default `None`), không
  phá call site cũ.

## Báo lại (ngắn)

1. file:line đã sửa + vì sao đúng chỗ đó
2. tên 2 test mới + output pytest
3. cách chứng minh "không đổi kiến trúc/số param" (số cụ thể)
4. chỗ nào trong ticket bạn thấy mơ hồ