# Bản đồ tài liệu (`docs/`)

Cập nhật: 2026-11-11. Nguyên tắc: **mỗi file một vai**, và vai được suy từ **thư mục chứa nó**.
Không đọc gì ngoài nhóm mình cần.

| Thư mục | Vai | Ai ghi |
|---|---|---|
| `docs/PROJECT.md` | **Cửa vào duy nhất.** Câu hỏi, phạm vi, cơ chế generator, sổ quyết định | người |
| `docs/reference/` | Hợp đồng & nguồn tham chiếu đang dùng | người |
| `docs/measurements/` | **Số `[ĐO]` đang dùng** — nguồn của mọi tham số | người + script |
| `docs/history/` | v1, thứ đã bị bác bỏ. **Không dùng làm căn cứ** | người |
| `docs/audit/` | Biên bản rà soát tài liệu (ảnh chụp một thời điểm) | người |
| `docs/adr/` | Quyết định kiến trúc, có ngày và trạng thái | người |
| `docs/board/` | Board tự sinh từ `STATUS.md` | `scripts/build_kanban.py` |
| `docs/agents/` | Quy ước làm việc cho agent (tracker, nhãn, domain) | người |
| `docs/figs/` | Ảnh/clip bằng chứng | script |

## Đường đi ngắn nhất cho từng việc

| Bạn cần | Đọc |
|---|---|
| Hiểu dự án đang hỏi gì | `PROJECT.md` §1 |
| Hiểu generator hiện tại | `PROJECT.md` §4 → `measurements/plume-geometry-measurements.md` |
| Biết paper nói gì (nguyên văn) | `reference/paper-qa-notebooklm.md` |
| Biết chỗ nào mình **lệch** paper và vì sao | `PROJECT.md` §5.2 |
| Chạy tiếp công việc | `../HANDOFF.md` → `../.scratch/spray-augmentation/STATUS.md` |
| Thiết kế eval (arm, eval set, tiêu chí) | `PROJECT.md` §7 |
| Tìm số gốc của một tham số | `measurements/` trước, rồi `history/plume-model-provenance.md` (v1) |
| Kiểm lịch sử quyết định | `PROJECT.md` §8 + `adr/` |

## Nhóm `reference/` (đang dùng)

| File | Nội dung |
|---|---|
| `velocity-contract.md` | velocity của box ở frame nào; số đo eligible; đính chính nhãn val |
| `nuscenes-eligibility.md` | bảng eligibility đầy đủ (ticket 18) — nguồn của eval set 196 frame |
| `paper-qa-notebooklm.md` | hỏi đáp nguyên văn với PDF paper: `[PAPER]` vs `[CODE]` vs "NOT STATED" |

## Nhóm `measurements/` (đang dùng)

| File | Nội dung | Sinh bởi |
|---|---|---|
| `plume-v2-measurements.md` | tốc độ, beam, quỹ đạo ego, hình học frame, hằng số (ticket 25) | `scripts/measure_*.py` (marker) |
| `plume-geometry-measurements.md` | plume thật vs mô phỏng theo 9 mức tốc độ; chiều cao, `|y|`, `x` | `scripts/measure_plume_geometry.py`, `measure_spray_height.py` |
| `semantic-spray-stats.md` | thống kê spray thật (điểm/frame, intensity) — **cảnh báo**: số cụm là cận trên | `scripts/semantic_spray_stats.py` |
| `plume-geometry-vs-real.md` | hình học theo cự ly, clustering single-linkage — cùng cảnh báo trên | `scripts/semantic_spray_stats.py` |

## Nhóm `history/` (không dùng làm căn cứ)

| File | Vì sao ở đây |
|---|---|
| `plume-v1-defects.md` | 8 lỗi cấu trúc của v1 (D1–D8); D1–D6 đã sửa, D7/D8 ở 29c |
| `plume-beam-table.md` | bảng `ring → elevation` **bị bác bỏ** — giữ làm phản chứng |
| `plume-model-provenance.md` | provenance của `PlumeConfig` v1 |
| `walkthrough-tickets.md` | giải thích pipeline + công thức v1 |
| `denoise-b0-params.md` | tham số arm B0 |
| `knowledge-base.html` | sổ tay v1 (2026-11-07), đã lạc hậu |

## Bất biến

1. **Số nào cũng phải có nhãn** `[PAPER]` / `[CODE]` / `[ĐO]` / `[CHỌN]`.
2. File trong `measurements/` **do script sinh** → sửa bằng cách sửa script rồi chạy lại, không sửa tay.
3. File trong `history/` **không được trích dẫn** trong báo cáo hay luận văn.
4. Board duy nhất là `../.scratch/spray-augmentation/STATUS.md`; `board/kanban.html` chỉ là bản render.