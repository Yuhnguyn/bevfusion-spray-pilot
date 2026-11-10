# Index dispatch — lịch sử, KHÔNG phải trạng thái hiện tại

Thư mục này là **nhật ký giao việc** cho CommandCode, không phải board. Trạng thái thật nằm ở
`../STATUS.md`; spec hiện hành là `../spec-v2-paper-faithful.md`.

Luật: mỗi file là một brief đã gửi, giữ nguyên văn để truy vết. Không sửa lại file cũ khi quyết
định đổi — viết brief mới và ghi đè quyết định ở STATUS.

## v2 (2026-11-10 → 11)

| Brief | Nội dung | Kết quả |
|---|---|---|
| `dispatch-25.md` | đo 0 GPU: tốc độ, beam, quỹ đạo, hình học frame | done, `docs/measurements/plume-v2-measurements.md` |
| `dispatch-26.md` | `PlumeContext` + state theo scene | done |
| `dispatch-27a.md`, `dispatch-27b.md` | wet ground (port `dee.cpp`), config riêng | done, mặc định tắt |
| `dispatch-28a.md` … `dispatch-28d.md` | khối sau đuôi, sinh cụm, advection hệ ground, `C` | done, vệt 73,4 m @130 |
| `dispatch-29a.md` | bảng `ring → elevation` | **bị bác bỏ** → lưới tia đều |
| `dispatch-29b.md` | ray casting, attenuation, strongest return | done; còn 4 lỗi ở `issues/29-…md` 29c |

## v1 (2026-11-08 → 11-09) — lịch sử

`dispatch-08.md` … `dispatch-24.md`: dựng pipeline, routing hai nhánh, evaluator, 3 config,
mini A/B (kết quả **null**, chẩn đoán ở `issues/11-mini-ab-run.md`), B0 denoise, provenance,
statistics, eligibility, Kaggle sync, visualize, port cơ chế. Không dùng các brief này làm căn cứ
cho v2 — nhiều chỗ đã bị thay (xem `docs/history/plume-v1-defects.md`).