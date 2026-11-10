Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`
2. `.scratch/spray-augmentation/issues/20-visualize-plume.md` ← **nguồn đúng, 6 đầu ra**
3. `spray/plume.py` (generator: `PlumeConfig`, `inject_plume`) + `spray/plume_transform.py`
4. `scripts/semantic_spray_stats.py` ← **dùng lại parser label của file này**, không tự viết lại
5. `docs/measurements/plume-geometry-vs-real.md` (số đo thật của ticket 16 — ảnh phải khớp số nào)

Baseline test hiện tại là **56 passed** (đã qua ticket 21–22), không phải 49.

## Môi trường — BẮT BUỘC đọc trước khi code

`matplotlib` trong `/opt/anaconda3` **hỏng**: bản 3.8.0 build cho numpy 1.x, numpy đang 2.4.3 →
`ImportError: numpy.core.multiarray failed to import`. **Không** pip install vào base env (sẽ đụng env
mà pytest đang dùng, 49 test đang xanh).

Dựng venv riêng:

    uv venv ~/.venvs/viz --python 3.11
    uv pip install --python ~/.venvs/viz/bin/python numpy matplotlib pillow
    ~/.venvs/viz/bin/python -c "import matplotlib; print(matplotlib.__version__)"

Mọi script viz chạy bằng `~/.venvs/viz/bin/python`. Script **chỉ được** dùng numpy/matplotlib/pillow
(`spray/plume.py` thuần numpy nên import được, không cần mmcv).

## Nhiệm vụ — ticket 20: visualize plume (ảnh + clip)

Viết `scripts/visualize_plume.py` (ảnh) và `scripts/render_clips.py` (clip), xuất vào `docs/figs/plume/`.

### Ảnh 1 — BEV một frame

- 1 box cố định `(x=22 m, y=0)`, box 4,5 × 1,9 m, tốc độ **72 km/h**, `seed=0`.
- Vẽ: ego ở gốc `(0,0)` tam giác; box chữ nhật xanh; `points_clean` xám nhạt; điểm plume **đỏ đậm**,
  marker lớn hơn.
- Mét, `axis('equal')`, `xlim [-10, 45]`, `ylim [-15, 15]`.
- Ghi trên ảnh: số điểm plume, số cụm, `r_range/r_extent` median của frame đó.
- **Mũi tên** chỉ hướng `−v/|v|` tại tâm box, để mắt kiểm plume có nằm sau đuôi.

### Ảnh 2 — Thật vs tổng hợp

- Trên: 1 frame SemanticSpray thật có spray, đọc từ `data/SemanticSprayDataset`. Chọn frame theo tiêu chí
  **viết trong script** (frame đầu tiên có ≥50 điểm spray), không chọn tay. Điểm spray tô cùng màu đỏ.

  **Số cụm sau ticket 22 — dùng để kiểm output, không được sửa tham số cho ảnh đẹp:**
  | v_kmh | 40 | 50 | 60 | 80 | 100 | 130 |
  |---|---:|---:|---:|---:|---:|---:|
  | cụm/frame | 0 | 0 | 3 | 8 | 13 | 20 |

  ⇒ dưới 50 km/h **không có plume** (đúng code thật). Frame chọn phải có vận tốc > 50 km/h và ≥50
  điểm spray; nếu không tìm được frame nào thoả ở 80 km/h thì **hạ ngưỡng xuống 30 điểm**, ghi rõ
  ngưỡng đã dùng vào HTML. Không được tăng số cụm để có ảnh đẹp.
- Dưới: frame tổng hợp của ảnh 1.
- **Cùng `xlim/ylim`, cùng thang màu, cùng marker size.** Ghi nguồn + số điểm/cụm mỗi panel.

### Ảnh 3 — Lưới mật độ theo cự ly

- 3 hàng = box ở `x` = **12 / 22 / 38 m**; 2 cột = `seed` **0 / 1**.
- Mỗi panel chỉ vẽ điểm plume (bỏ điểm sạch), `axis('equal')`, cùng tỉ lệ.
- Ghi `n_points`, `n_clusters`, `median points/cluster`.
- Mục đích: mắt thấy mật độ giảm **30 → 20 → 14 → 10** điểm/cụm, khớp bảng ticket 16.

### Clip A — spray THẬT (quan trọng nhất)

- Chọn sequence `Crafter_dynamic` đầu tiên có **≥60 frame** (mỗi sequence 76 frame). Ghi tên sequence vào
  báo cáo.
- Mỗi frame: BEV `ibeo_front`, điểm spray-labelled **đỏ**, còn lại xám.
- **Trục CỐ ĐỊNH cho cả clip** (`xlim`/`ylim` tính 1 lần từ toàn bộ 76 frame rồi dùng lại) — nếu mỗi frame
  tự rescale thì chuyển động vô nghĩa.
- Encode: `ffmpeg -framerate 10 -i frame_%03d.png -c:v libx264 -pix_fmt yuv420p -crf 20`.
- Output `docs/figs/plume/clip-a-real-spray.mp4`, in số frame + thời lượng.

### Clip C — flicker A/B

- 2 frame: (1) sạch, (2) cùng frame + plume seed 0. Lặp **6 vòng** = 12 frame ở 2 Hz (~6 s).
- **Cùng trục, cùng point size** giữa 2 frame — nếu khác thì hiệu ứng giả.
- Overlay chữ `clean` / `with plume (seed 0)` góc trên trái, cùng font cùng vị trí.
- Output `docs/figs/plume/clip-c-flicker.mp4`.

### Ảnh 4 — `docs/figs/plume/index.html`

Trang HTML tự chứa, nền sáng: nhúng 3 nhóm ảnh + 2 clip bằng thẻ `<video controls loop muted>`.
Mỗi mục 1 dòng nói **chứng minh gì** và **KHÔNG chứng minh gì**.

## Ràng buộc cứng

- **Không nội suy, không làm mượt giữa các frame.** Generator hiện tại độc lập từng frame (không có hạt,
  không lifetime/fade như paper `Δt=100ms`, `P_t(t)=e^(−t/T)`). Nếu clip nhấp nháy thì **giữ nguyên** và ghi
  rõ "generator frame-independent" trong báo cáo + caption HTML. Cấm fake cho mượt.
- **Tất định**: mọi frame sinh từ seed cố định trong script; chạy 2 lần, `md5` ảnh 1 phải giống nhau.
- Không sửa `spray/plume.py`, `spray/plume_transform.py`, `tests/`, `scripts/semantic_spray_stats.py`.
- Không đọc/ghi ngoài: `data/SemanticSprayDataset` (đọc), `docs/figs/plume/` (ghi), `scripts/` (2 file mới).
- Không tự đổi tham số plume cho ảnh đẹp hơn. Thấy sai thì giữ nguyên ảnh và báo.

## Xong khi

- [ ] `~/.venvs/viz/bin/python scripts/visualize_plume.py` và `scripts/render_clips.py` chạy xong
- [ ] ≥ 7 PNG trong `docs/figs/plume/`, mỗi file > 40 KB
- [ ] 2 mp4 tồn tại, `ffprobe` báo đúng độ phân giải + số frame (dán output vào báo cáo)
- [ ] chạy 2 lần liên tiếp, `md5` ảnh 1 giống nhau
- [ ] pytest vẫn **49 passed** (chạy bằng `/opt/anaconda3/bin/python`, không phải venv viz)
- [ ] Commit: `feat(viz): render plume geometry + clips (real spray, synthetic, flicker A/B)`

## Báo lại

1. danh sách file, số điểm/cụm từng panel, tên sequence dùng cho clip A
2. **phát hiện bằng mắt**: plume lơ lửng / đè box / ngược hướng / quá thưa?
3. camera clip A: 76 frame encode ra **bao nhiêu giây**, và số điểm spray mỗi frame có biến thiên không
4. số liệu mỗi panel có khớp `docs/measurements/plume-geometry-vs-real.md` không (lệch thì ghi lệch bao nhiêu)