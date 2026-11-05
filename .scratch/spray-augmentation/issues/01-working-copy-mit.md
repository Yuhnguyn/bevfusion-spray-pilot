# 01: Dựng working copy MIT và pin version

**What to build:** Một bản working copy của BEVFusion (MIT) tách khỏi reference clone, checkout đúng commit release, và ghi lại quyết định về các flag depth của camera branch. Việc này đảm bảo mọi ticket sau chạy trên cùng một version.

**Blocked by:** None

**Status:** done

- [x] Working copy tồn tại và checkout đúng commit đã chọn.
- [x] `third_party/` không bị sửa.
- [x] Quyết định `add_depth_features` và `height_expand` được ghi kèm lý do.
- [x] Có một lệnh kiểm tra version chạy được.
