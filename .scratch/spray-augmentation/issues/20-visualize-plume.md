# 20: Visualize plume (ảnh BEV + clip thật/flicker)

**Mục đích:** test không bắt được lỗi "plume lơ lửng giữa không khí / bay ngược hướng / đè lên box".
Cần nhìn bằng mắt. Không cần GPU, không cần `mmcv` — `spray/plume.py` chỉ numpy, data local có sẵn.

**Đầu ra** (vào `docs/figs/plume/`):

1. `bev-plume.png` — BEV top-down 1 frame nuScenes-like: box + plume, tô đỏ điểm spray.
2. `real-vs-synth.png` — trên: frame SemanticSpray thật có spray; dưới: frame tổng hợp. Cùng `xlim/ylim`,
   cùng marker size. Chọn frame bằng tiêu chí **trong script** (≥50 điểm spray, v > 50 km/h), không chọn tay.
3. `grid-12-22-38.png` — lưới 3 box × 2 seed.
4. `clip-a-real-spray.mp4` — spray **thật** 76 frame IBEO front, tô đỏ điểm spray.
5. `clip-c-flicker.mp4` — cùng frame, sạch ↔ có plume, 2 Hz.
6. `index.html` — trang tự chứa, nền sáng, nhúng ảnh + video.

**Ràng buộc:**

- venv riêng `~/.venvs/viz` (dựng bằng `uv`), **không** đụng env pytest đang 56 passed
  (matplotlib base hỏng vì numpy 2.4.3).
- Số cụm sau ticket 22: 0/0/3/8/13/20 ở 40/50/60/80/100/130 km/h ⇒ **dưới 50 km/h không có plume**.
  Cấm tăng tham số plume cho ảnh đẹp.
- Trục cố định cho cả clip (tính 1 lần), `ffmpeg -framerate 10`.
- Ghi nhãn **"frame-independent"** trên clip C: generator không có trạng thái thời gian, mỗi frame rút mới
  ⇒ clip nhấp nháy là **sự thật của code**, không nội suy/làm mượt.

**Nghiệm thu:** 6 file tồn tại, `index.html` mở được, số cụm in ra khớp bảng trên, pytest vẫn 56 passed.
Commit: `docs(viz): plume BEV stills, real-vs-synth, and two clips`