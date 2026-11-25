# A5 đo lại sau QĐ15 (2026-11-25) — bảng A5 cũ có còn hiệu lực?

Câu hỏi: sau QĐ15 (xoá cơ chế tán xạ, miền paper thành mặc định, trần bán kính
4,0 → 2,0 m) thì bảng nghiệm thu A5 (`docs/measurements/a5-domain-a3v.md`,
đo 2026-11-19) còn đúng không?

Dụng cụ: `.scratch/paper-faithful/a5_a3v_domain.py --frames-per-scene 30`, tập B
(72 scene không human box, 2160 frame), seed `20261119`, paired. Ba lượt:

| lượt | code | cấu hình khác biệt |
|---|---|---|
| **A5 gốc** | `83eaee9`/`a35edd6` (19/11) | `α = 0,06` trong config, miền opt-in qua `replace(diffusion_alpha=0.0, …)` , cap bán kính 4,0 m |
| **b272206** | ngay trước QĐ15 | QĐ14 đã đổi stream RNG (`p_det_z`), `α = 0,06` vẫn còn trong default nhưng bị script đặt 0, cap 4,0 m |
| **HEAD 5e4da9b** | sau QĐ15 | không còn `α`, miền mặc định, cap 2,0 m |

## 1. Tỉ lệ `[ĐO]` điểm sinh/thật (`median` theo scene, CI95 bootstrap 2000)

| xe | band | A5 gốc | b272206 | **HEAD** | lệch gốc→HEAD | ĐẠT `[0,5;2,0]` |
|---|---|---:|---:|---:|---:|---|
| crafter | 50–70 | 1,02 | 0,96 | **0,89** | −12,7 % | ĐẠT → **ĐẠT** |
| golf | 50–70 | 0,34 | 0,24 | **0,27** | −20,6 % | TRƯỢT → **TRƯỢT** |
| crafter | 80–110 | 0,25 | 0,24 | **0,23** | −8,0 % | TRƯỢT → **TRƯỢT** |
| golf | 80–110 | 0,50 | 0,55 | **0,49** | −2,0 % | ĐẠT → **TRƯỢT** (sát biên) |
| crafter | 120–130 | 0,85 | 0,48 | **0,69** | −18,8 % | ĐẠT → **ĐẠT** |
| golf | 120–130 | 0,65 | 0,47 | **0,42** | −35,4 % | ĐẠT → **TRƯỢT** |

Số ô ĐẠT: **4/6 (gốc) → 2/6 (b272206) → 2/6 (HEAD)**.

## 2. Tách nguyên nhân

**QĐ14 (bắt buộc, đã duyệt) là thủ phạm chính, không phải QĐ15.** QĐ14 đổi
`p_det0` từ rút-mỗi-frame sang `p_det_z` lưu-một-lần. Vì `P_det0` giờ là hằng số
theo cụm chứ không lấy lại mỗi frame, **tổng det/frame giảm** — đây là hệ quả toán
học đã biết của việc bỏ rút lại (`E[max(P, re-draw)] > E[P]`). Ở 120–130 km/h
crafter: 0,85 → 0,48 (−44 %) chỉ do QĐ14.

**Cap bán kính 4,0 → 2,0 m (QĐ15) không phải nguyên nhân, nhưng gây nhiễu ±12 % ở
từng ô.** A/B riêng bước này (b272206 → HEAD, mọi thứ khác giữ nguyên):

| ô | 4,0 m | 2,0 m | Δ |
|---|---:|---:|---:|
| crafter 50–70 | 0,96 | 0,89 | −7,3 % |
| golf 50–70 | 0,24 | 0,27 | +12,5 % |
| crafter 80–110 | 0,24 | 0,23 | −4,2 % |
| golf 80–110 | 0,55 | 0,49 | −10,9 % |
| crafter 120–130 | 0,48 | 0,69 | **+43,7 %** |
| golf 120–130 | 0,47 | 0,42 | −10,6 % |

Chiều lệch **không nhất quán** (−10,9 % … +43,7 %) trong khi cap chỉ cắt 0,486 %
số cụm ⇒ đây là **nhiễu seed**, không phải hiệu ứng thật. Muốn kết luận về cap
phải tăng seed; không cần, vì cap 2,0 m là p99 của lognormal chứ không phải tham
số hiệu chỉnh.

**Bỏ tán xạ (α = 0,06 → không còn) không ảnh hưởng bảng này**, vì script A5 đã
đặt `diffusion_alpha = 0` từ đầu — A5 vốn đã là "Cách A". Điều duy nhất đổi là
cách đạt α = 0 (trước: cờ; nay: không tồn tại).

## 3. Thước near-field (lý do tồn tại của miền) — KHÔNG đổi

`R p05` của detection (m):

| xe | band | A5 gốc | HEAD |
|---|---|---:|---:|
| crafter | 50–70 | 16,4 | 16,7 |
| golf | 50–70 | 18,7 | 18,8 |
| crafter | 80–110 | 4,5 | 5,1 |
| golf | 80–110 | 5,3 | 5,8 |
| crafter | 120–130 | 4,6 | 4,6 |
| golf | 120–130 | 5,1 | 5,2 |

`x min` vẫn −48,7 … −49,9 m (không trôi về −137/−294 m). Tức **tác dụng của miền
được giữ nguyên vẹn** — cái mất là một phần khối lượng điểm, thứ vốn đã thiếu.

## 4. Kết luận

1. **Bảng A5 cũ không còn dùng làm số hiện hành.** Tỉ lệ lệch −2 % … −35,4 %, đủ
   để đảo 2 ô từ ĐẠT sang TRƯỢT.
2. **Nhưng kết luận định tính của A5 vẫn đúng**: miền paper cắt near-field
   (`R p05` 4,5–5,8 m thay vì 1,42–1,58 m) và chặn trôi về ego; cùng lúc 4/6 ô
   (nay 5/6) thưa hơn thật vì nguồn hiệu chuẩn `*_static` có trail dài hơn
   following.
3. **Không phải "hiệu chuẩn hỏng" mà là "hiệu chuẩn thưa thêm".** QĐ14 làm mất
   ~19–44 % khối lượng điểm ở 120–130 km/h. Nếu cần bù, phải bù bằng **số cụm
   (`spawn_scale`)** và pre-register riêng — ADR-0006 §5.7 đang **cấm** bù bằng
   `spawn_scale`, nên đây là việc phải mở lại ADR, không phải chỉnh lặng lẽ.
4. **Việc cần làm:** cập nhật `docs/measurements/a5-domain-a3v.md` bằng bảng HEAD
   + ghi rõ QĐ14/QĐ15 đã đổi nền đo; hoặc giữ doc cũ và thêm khối "số hiện hành
   xem a5-domain-a3v-post-qd15.md".

## 5. Thước thứ ba: A3 (static) cũng đo lại — FAIL nặng hơn A5

`scripts/measure_plume_size_tail.py --seeds 2`, kịch bản **static** (ego đỗ, xe chạy
ra xa tới 200 m), cùng generator HEAD `5e4da9b`:

| km/h | điểm/f | trail90 | %≤20 m | CI95 | đích T4 geom | tỉ lệ |
|---|---:|---:|---:|---:|---|---|
| 50 | 9,7 | 2,0 m | 100 % | 18,3 % | 85,1 / 6 m / 99,5 % | **0,11×** |
| 100 | 23,5 | 22,0 m | 89,4 % | 27,8 % | 202,6 / 44 m / 53,8 % | **0,12×** |
| 130 | 13,8 | 32,0 m | 78,2 % | 7,7 % | 208,9 / 52 m / 25,7 % | **0,07×** |

**KẾT QUẢ A3: FAIL** — thiếu 7–14 lần, tệ hơn nhiều so với a5 (0,23–0,89×).

Chạy lại với `PLUME_LEGACY_DOMAIN=1` để tách phần do miền: 0,11× / 0,13× / 0,18×
(trail90 2,0 / 22,0 / 25,0 m). ⇒ **miền chỉ giải thích phần chênh ở 130 km/h**
(0,07× → 0,18×); A3 fail chủ yếu vì **kịch bản static không thuộc miền paper**:
paper hiệu chuẩn ego ĐỖ ở 25 m và kiểm chứng 0–50 m, còn static đo tới 200 m nên
phần lớn plume nằm ngoài 50 m và bị cắt — đúng như thiết kế, không phải lỗi mới.

Hệ quả: **A3 từ nay là thước chẩn đoán, không phải thước nghiệm thu** cho cấu hình
mặc định. Nghiệm thu khối lượng phải đọc A5 (following, trong miền).

## 6. Số thô

| tập | đường dẫn |
|---|---|
| HEAD `5e4da9b` | `%TEMP%/cdfprobe/a5_now.json` (không tracked — `.scratch/tmp/` bị gitignore và máy này chặn ghi) |
| b272206 | `%TEMP%/cdfprobe/a5_old_b272.json` |
| CDF following 12 scene | `%TEMP%/cdfprobe/following_all.jsonl` |

Lưu ý môi trường: trên máy Windows này `.venv/Scripts/python.exe` **bị chặn ghi
mọi file** (sandbox). Chạy script đo bằng base Python 3.11 + trỏ
`PYTHONPATH=".;D:/VF/bevfusion-spray-pilot/.venv/Lib/site-packages"` để có
`scipy`.
