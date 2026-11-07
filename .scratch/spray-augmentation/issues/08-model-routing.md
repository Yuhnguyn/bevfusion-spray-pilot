# 08: Model forward routing

**What to build:** Patch fusion model để camera branch nhận `points_clean` và LiDAR branch nhận `points`. Không có patch này, camera vẫn nhận point đã có spray.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] Camera path nhận `points_clean`.
- [ ] LiDAR path nhận `points`.
- [ ] Stub model test xác nhận routing bằng shape và marker value.
- [ ] Không thay đổi kiến trúc hay số tham số.

## PM decision 2026-11-07 (sau khi agent dừng đúng lúc)

**Patch bản `mit/bevfusion` @ `da93b27`, KHÔNG patch `third_party/bevfusion`.**
`mit/bevfusion` là bản runtime (`mit/PIN.md:4-8`, `docs/PROJECT.md:34`) và bị gitignore
(`.gitignore:4`). `third_party/bevfusion` mới hơn nhưng **không chạy** → patch vào đó là code chết.

**Cách ship: subclass trong `spray/`, KHÔNG sửa vendor.** Vendor pinned + gitignored ⇒ sửa file vendor là
thay đổi không version-control được. Subclass cũng làm ticket 10 (`model.type` đổi 1 dòng) chạy được ngay,
và giữ nguyên số tham số.

Design (không duplicate `forward`): override **`extract_camera_features`** là đủ, vì chỉ nhánh camera gọi
nó. `forward` chỉ cần nhận `points_clean=None` rồi delegate `super().forward(...)`.

```
class CleanPointsBEVFusion(BEVFusion):
    def forward(self, img, points, *a, points_clean=None, **kw):
        self._points_clean = points_clean
        try:    return super().forward(img, points, *a, **kw)
        finally: self._points_clean = None
    def extract_camera_features(self, img, points, *a, **kw):
        c = getattr(self, "_points_clean", None)
        return super().extract_camera_features(img, c if c is not None else points, *a, **kw)
```
`mit/bevfusion/.../bevfusion.py:149-182`: `forward` đã có `**kwargs`, camera branch gọi
`extract_camera_features(img, points, ...)` ở dòng 169-180, lidar gọi `extract_lidar_features(points)` 182.

**Đính chính brief của PM (2 lỗi):** tên file ticket là `08-model-routing.md` (không phải
`08-model-forward-routing.md`); `forward` **không** có `radar_points`.

**Việc thêm, bắt buộc cùng ticket này:** `points_clean` hiện **không tới được** `forward` —
`DefaultFormatBundle3D` (`formating.py:49-51`) chỉ wrap `points`/`radar`. Routing mà không có plumbing là
code chết. Nên ticket này gồm 2 phần: (1) plumbing `points_clean` qua collect/format trong `spray/`,
(2) routing ở model. Ticket 09 chỉ còn nhiệm vụ **chứng minh end-to-end**.

**Lazy import:** `spray/` không được import `mmcv/mmdet3d` ở module import time (laptop không có). Đưa class
vào hàm factory + register khi có registry; test cấy base giả vào `sys.modules`.

