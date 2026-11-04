# 08: Model forward routing

**What to build:** Patch fusion model để camera branch nhận `points_clean` và LiDAR branch nhận `points`. Không có patch này, camera vẫn nhận point đã có spray.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] Camera path nhận `points_clean`.
- [ ] LiDAR path nhận `points`.
- [ ] Stub model test xác nhận routing bằng shape và marker value.
- [ ] Không thay đổi kiến trúc hay số tham số.
