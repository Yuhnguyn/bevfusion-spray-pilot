Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`
2. `.scratch/spray-augmentation/issues/08-model-routing.md` ← **đọc hết, phần "PM decision 2026-11-07" ở cuối là
   quyết định đã chốt, không cần hỏi lại**
3. `spray/plume_transform.py` (points / points_clean sinh ra thế nào)
4. `mit/bevfusion/mmdet3d/models/fusion_models/bevfusion.py` dòng 148-200 (bản runtime, đã pin `da93b27`)

## Chốt (đừng mở lại)

- Patch bản **`mit/bevfusion` @ `da93b27`**, KHÔNG `third_party/bevfusion` (bản đó không chạy).
- **Không sửa file trong `mit/`** — vendor pinned + gitignored. Dùng **subclass trong `spray/`**.
- Subclass override `extract_camera_features` (chỉ nhánh camera gọi nó), `forward` chỉ nhận
  `points_clean=None` rồi `super().forward(...)`. Code mẫu nằm trong ticket.
- Ticket gồm **2 phần**: (1) plumbing `points_clean` qua collect/format, (2) routing ở model.

## Phần 1 — plumbing (bắt buộc)

`DefaultFormatBundle3D` (`mit/bevfusion/.../formating.py:49-51`) chỉ wrap `points`/`radar`, và `Collect3D`
chỉ lấy key trong list ⇒ `points_clean` **không tới được** `forward`. Viết trong `spray/` (không sửa vendor):

- một `Collect3D` thay thế có thêm `points_clean` vào `keys`
- một `DefaultFormatBundle3D` thay thế wrap `points_clean` thành `DataContainer`
- cả hai phải **tham số hoá được từ config** (ticket 10 sẽ trỏ vào), và khi `points_clean` không có trong
  `results` thì hành vi y hệt bản gốc

## Phần 2 — model routing

`spray/` phải **import được khi không có mmcv/mmdet3d** (laptop không có 3 gói này). Import bên trong
factory/`try`, register vào registry khi có. Test cấy base giả vào `sys.modules` trước khi gọi.

## Xong khi

- [ ] `import spray.<module mới>` chạy được trên máy không có mmcv (kiểm bằng subprocess riêng).
- [ ] Stub base giả: `forward(points_clean=POINTS_MARKER_CLEAN)` → `extract_camera_features` thấy
      **marker của clean**, `extract_lidar_features` thấy **marker của points**. So **giá trị marker**, shape chỉ phụ.
- [ ] `points_clean=None` → camera nhận đúng `points` như cũ (so sánh `torch.equal`).
- [ ] Số param trước = sau (assert số cụ thể trong test).
- [ ] Test plumbing: `points_clean` có trong batch sau format; thiếu `points_clean` → không crash, batch giống bản gốc.
- [ ] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥ 38 passed**
      (baseline **35** ngày 2026-11-07; số thật khác ⇒ DỪNG báo PM).
- [ ] Commit: `feat(model): route clean points to camera branch via spray subclass + collect/format plumbing`

## Ràng buộc cứng

- Không sửa `mit/bevfusion/**` (kể cả để "cho nhanh"), không sửa `third_party/**`.
- Không sửa `spray/plume.py`, không đổi `PlumeConfig`.
- Không sửa 35 test cũ. Không thêm dependency mới.
- Không `git add -A` (chỉ add file mình tạo/sửa).

## Báo lại (ngắn)

1. file mới + dòng chính; vì sao chọn chỗ override đó
2. output pytest + số test mới
3. cách chứng minh "không cần mmcv để import" (lệnh đã chạy + output)
4. còn chỗ nào trong ticket bạn thấy mơ hồ