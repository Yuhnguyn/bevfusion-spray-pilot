Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. .scratch/spray-augmentation/STATUS.md (mục "Thứ tự hiện tại")
2. .scratch/spray-augmentation/issues/16-plume-geometry-research.md  ← ticket, là nguồn đúng
3. scripts/semantic_spray_stats.py + docs/semantic-spray-stats.md (script và số cũ, để không phá cái đã có)

## Nhiệm vụ

Làm trọn ticket 16: đo hình học plume thật theo cự ly trên SemanticSpray, rồi ghi bảng + kết luận
vào docs. Đây là ticket ĐO, **không sửa generator**.

Ba câu phải trả lời bằng số: `median n_points` theo bucket cự ly; `r_range / r_extent`; `n_rings`.

## Cách chạy

- Python: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python` (conda in crash report là nhiễu, bỏ qua).
- Dữ liệu: `data/SemanticSprayDataset` (16 GB, đã có local, KHÔNG tải lại, KHÔNG commit).
- Giữ nguyên sample cũ (207 scene × 10 frame = 2.070 frame) và clustering single-linkage r=0,5 m,
  dense ≥5 điểm, để còn so được với `docs/semantic-spray-stats.md`.
- **Nếu bucket nào có < 30 cụm** thì mở rộng sample (ví dụ 20 frame/scene, hoặc thêm group scene),
  chạy lại, và **báo cả hai** (sample cũ + sample mở rộng) chứ không lặng lẽ đổi sample.
- Script phải chạy lại được bằng MỘT lệnh, có cờ chọn sample, ghi cờ đó vào output.

## Ràng buộc cứng

- KHÔNG sửa `spray/`, KHÔNG đổi `PlumeConfig`, KHÔNG đổi test. `git diff` chỉ được chạm
  `scripts/semantic_spray_stats.py` + `docs/`.
- KHÔNG kết luận định tính. Viết dạng: "median n_points giảm từ 21,4 (0–5 m) xuống 1,8 (20–30 m),
  tỉ lệ 11,9×". Câu "có vẻ giảm" là câu trả về không đạt.
- Nếu bạn cho rằng phải đổi tham số generator: **DỪNG**, báo PM kèm số. Đó là ticket 17, không phải ticket này.
- Mọi số mới gắn nhãn `[ĐO]`, kèm `n` từng bucket.
- Không commit dữ liệu thô vào git.

## Test + commit

- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → phải vẫn **33 passed**.
- Commit: `docs(spray): measure real plume geometry vs range on SemanticSpray`

## Báo lại (ngắn)

1. thời gian chạy + sample đã dùng (2.070 hay mở rộng)
2. 3 bảng số (hoặc bảng gộp) — dán nguyên văn số, không tóm tắt
3. trả lời 3 câu, mỗi câu một con số
4. bucket nào < 30 cụm và bạn đã xử lý thế nào
5. chỗ nào trong ticket bạn thấy mơ hồ