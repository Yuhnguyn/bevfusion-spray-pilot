Bạn làm ticket 24 trong repo /Users/huynguyen/projects/bevfusion-spray-pilot (branch main).

ĐỌC THEO THỨ TỰ:
1. AGENTS.md (nếu có).
2. .scratch/spray-augmentation/issues/24-kanban-from-source.md — NGUỒN ĐÚNG, 6 yêu cầu + 7 tiêu chí xong.
3. scripts/build_kanban.py — hiện đang hard-code toàn bộ metadata ticket (khối TICKETS).
4. .scratch/spray-augmentation/STATUS.md — nguồn sự thật mới (bảng ticket + cột Bằng chứng / next).
5. .scratch/spray-augmentation/issues/*.md — xem cấu trúc checkbox "## Xong khi" / "## Nghiệm thu".

MỤC TIÊU: `docs/board/kanban.html` phải sinh từ STATUS.md + checkbox trong issues/*.md, KHÔNG hard-code.

YÊU CẦU CỤ THỂ:
1. Parse bảng markdown của STATUS.md (mục "## Bảng ticket"): lấy #, Việc, Trạng thái, Bằng chứng / next.
   Nhận diện trạng thái: `**done**` (có thể kèm `\`sha\``) → done; `blocked` → blocked;
   `ready-for-agent` / `ready` → ready. Không đoán từ tên file.
2. Đếm checkbox `- [x]` / `- [ ]` trong issues/NN-*.md. Ticket không có checkbox nào (15, 22, 23)
   phải hiển thị "—", KHÔNG phải "0/4" — thêm 0 vào mẫu số là bịa.
3. `files`: nếu path không tồn tại thì in cảnh báo ra stderr và KHÔNG render path đó.
   (Hiện 17 trỏ `.scratch/spray-augmentation/issues/17-plume-shell-geometry.md` đã bị git rm.)
4. Ticket done phải hiện commit SHA lấy từ STATUS.md.
5. Header in "Cập nhật: <ngày giờ chạy>" + "nguồn: STATUS.md @ <git rev-parse --short HEAD>".
6. Giữ nguyên phong cách thị giác hiện có của kanban.html (dark theme, phase cards) — chỉ đổi nguồn dữ liệu.
   Nếu file hiện tại có phase P0..P6 thì giữ, phase suy ra từ nhóm ticket; không bịa phase mới.

RÀNG BUỘC:
- Chỉ stdlib (script hiện tại chỉ dùng stdlib). Không thêm dependency.
- KHÔNG sửa STATUS.md, KHÔNG sửa trạng thái ticket nào, KHÔNG sửa file trong issues/.
- Không đụng spray/, tests/, mit/, third_party/.
- Không commit docs/board/kanban.html cũ đang stale trước khi sửa script.

KIỂM TRA TRƯỚC KHI COMMIT:
- CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/build_kanban.py  → chạy < 2 s, không lỗi.
- grep -c "17-plume-shell-geometry" docs/board/kanban.html  → 0
- Board phải có đủ 25 ticket (01, 02, 02b, 03…24); 08/16/17/19/20/21/22 hiện done kèm SHA.
- P6 hiện 100%; ticket 09 hiện ready (không phải blocked).
- TEST QUAN TRỌNG: PM sẽ sửa 1 nhãn trong STATUS.md rồi chạy lại; board phải đổi theo mà không sửa script.
  Bạn tự làm thử: đổi tạm 1 ký tự trong STATUS.md, chạy lại, xác nhận output đổi, RỒI HOÀN NGUYÊN STATUS.md
  (git checkout -- .scratch/spray-augmentation/STATUS.md) trước khi commit.
- CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/ → vẫn 56 passed.

COMMIT đúng 1 commit, message đúng dòng này:
feat(kanban): render board from STATUS.md and issue checklists

BÁO CÁO CUỐI (ngắn): script đọc gì, board ra bao nhiêu ticket / bao nhiêu done, bằng chứng board đổi theo
STATUS.md, pytest, commit sha. Nếu bị chặn: dừng, báo lý do + log.