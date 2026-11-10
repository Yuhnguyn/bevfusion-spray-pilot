# Prompt khởi động session mới

File này thay bản cũ (2026-11-09) — bản cũ dẫn theo đường **v1** và đã sai.

Dán khối sau vào session mới:

```
Đọc theo thứ tự, đừng đọc thêm:
1. HANDOFF.md
2. .scratch/spray-augmentation/STATUS.md (header + "Quyết định 2026-11-11" + bảng ticket)
3. docs/PROJECT.md §4 và §5.2
4. Nếu làm ticket: .scratch/spray-augmentation/issues/<ticket>.md

Trạng thái: generator v2. Xong 25–28, 29a, 29b. Đang làm 29c (4 lỗi ray casting) và
29d (cổng split cal/held-out + đo lại thống kê). Test 239 passed, 4 skipped.
Không train lại, không chạy Kaggle trước khi 31 xong.

Luật không đổi: /opt/anaconda3/bin/python; không thêm dependency; không đọc file nhị phân
bằng cat; không sửa spray/config/plume_default.yaml; PM tự kiểm bằng probe riêng, không tin
test của agent; mọi con số phải có nhãn [PAPER]/[CODE]/[ĐO]/[CHỌN].
```

## Bẫy đã gặp (đừng lặp lại)

- `.scratch/spray-augmentation/spec.md` và `docs/walkthrough-tickets.md` §3 là **v1** — đừng lấy
  công thức từ đó.
- `spray/config/beam_elevation.yaml` sinh từ bảng đã **bị bác bỏ**; xoá ở 29c.
- Số cụm/điểm-cụm của v1 (17,06 cụm/frame) đo bằng **single-linkage** ⇒ không dùng làm mốc.
- Không đặt ngưỡng cắt cụm theo mét: p5 của `x` dao động −40,6…+3,7 m.