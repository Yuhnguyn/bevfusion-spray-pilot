# 24: `docs/board/kanban.html` phải sinh từ nguồn thật, không hard-code

## Vấn đề [ĐO 2026-11-07]

`scripts/build_kanban.py` chứa **nguyên khối metadata ticket viết cứng** (dòng 60–200: `TICKETS = [...]`
với status/checklist/next/evidence cho từng ticket). Chạy lại script **không** cập nhật gì — nó chỉ render
lại đúng khối cũ ra `docs/board/kanban.html`.

Hệ quả đã kiểm:

| chỗ | board đang ghi | thực tế |
|---|---|---|
| ticket 08 | `ready-for-agent`, 0/4, "Bắt đầu ngay" | **done** `16517f1` |
| ticket 16, 17 | `ready-for-agent` / `blocked`, 0/0 | **done** `08f6715`, `5d7c478` |
| phase P6 | `done 0 / total 0` | 2/2 xong |
| focus | "Ticket 06 + 07 xong — chuyển sang model routing (08)" | đang ở ticket 23/09 |
| `files` của ticket 17 | `.scratch/.../17-plume-shell-geometry.md` | **file đã `git rm`**, ref chết |
| ticket 19–24 | không tồn tại trên board | 19/20/21/22 done, 23/24 ready |

Board này từng được publish thành artifact công khai ⇒ người ngoài đọc sẽ thấy tiến độ sai 6 ticket.

## Yêu cầu

1. **Một nguồn sự thật duy nhất**: `STATUS.md` (bảng ticket) + `issues/*.md` (checkbox). Script chỉ render.
2. Parse bảng markdown của `STATUS.md`: cột `#`, `Việc`, `Trạng thái` (`**done** \`sha\``, `blocked`,
   `ready-for-agent`), `Bằng chứng / next`. Không đoán trạng thái từ tên file.
3. Đếm checkbox `- [x]` / `- [ ]` trong `issues/NN-*.md`. Ticket **không có checkbox** (15, 22, 23) phải
   hiển thị `—` chứ **không** phải `0/4` — thêm 0 vào mẫu số là bịa.
4. Bỏ hết ref file không tồn tại; nếu `files` trỏ vào path không có thì script **in cảnh báo ra stderr**
   và không render path đó.
5. Thêm cột/badge commit SHA cho ticket đã done (lấy từ `STATUS.md`).
6. Header board in `Cập nhật: <ngày giờ chạy>` + `nguồn: STATUS.md @ <sha HEAD>`.

## Không được làm

- Không sửa `STATUS.md` để chiều script.
- Không tự đổi trạng thái ticket nào.
- Không thêm dependency ngoài stdlib (script hiện chỉ dùng stdlib).

## Xong khi

- [ ] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/build_kanban.py` chạy < 2 s, không lỗi
- [ ] `grep -c "17-plume-shell-geometry" docs/board/kanban.html` = **0**
- [ ] board có đủ **24** ticket; 08/16/17/19/20/21/22 hiện `done` kèm SHA
- [ ] P6 hiện `100%`, P1 hiện đúng số (09 ready, không phải blocked)
- [ ] sửa 1 dòng trong `STATUS.md` rồi chạy lại → board đổi theo **mà không sửa script**
- [ ] `git status` sạch sau commit
- [ ] commit: `feat(kanban): render board from STATUS.md and issue checklists`

## PM nghiệm thu 2026-11-07 16:05 — ĐẠT (có 1 lưu ý)

- Agent chạy hết **70 turn** trước khi kịp commit (exit 8). Code đã xong và tự test; **PM commit** `8da032a`.
- PM kiểm độc lập: mutation test — sửa ticket 14 thành `**done** \`deadbee\`` trong `STATUS.md`, chạy lại
  script → board đổi `18 done` → `19 done` và hiện SHA `deadbee`; hoàn nguyên → về `18 done`. **Board đọc
  STATUS.md thật**, không hard-code (`grep 'TICKETS = \['` = 0).
- Board: 25 ticket, 18 done, 72%, P6 100%, 09 = `ready`, ref chết = 0; ticket không có checkbox hiện `—`
  (template dòng 499) đúng yêu cầu 2.
- Cảnh báo path thiếu hoạt động: đường dẫn mit/bevfusion/build (ticket 19) bị bỏ, không render.
- **Lưu ý chưa sửa**: `PHASES` vẫn khai báo cứng danh sách ticket; agent nhét 19 và 24 vào **P0 "Nền móng"**
  cho khỏi cảnh báo. 19 (Kaggle sync) tạm chấp nhận được, **24 (script kanban) thì sai chủ đề**. Không mở
  ticket riêng — sửa 1 dòng trong `PHASES` khi có ai chạm file này lần nữa.

## PM sẽ nghiệm thu

Chạy script 2 lần, lần 2 sau khi PM sửa nhãn một ticket trong `STATUS.md`: board phải đổi theo. Nếu board
vẫn đứng yên thì coi như chưa xong.