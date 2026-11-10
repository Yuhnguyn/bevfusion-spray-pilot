# 31: Nghiệm thu thống kê + render + audit độc lập v2

**Type:** task
**Status:** needs-triage
**Blocked by:** 25–30 (gồm 29c, 29d)
**Chủ:** PM (Hermes) chạy audit; CommandCode chỉ sửa lỗi phát hiện.

## Việc phải làm

1. `scripts/validate_v2_stats.py` trong repo — in bảng: số điểm/frame, số cụm/frame,
   phân bố `ring`, phân bố `intensity`, `rejected_box`, `attenuated_real`, `capped`,
   ms/frame; so với mốc Fig. 11a tại tốc độ **đo được ở ticket 25** và mốc `[ĐO]` của SemanticSpray.
2. `scripts/render_plume_frame.py` — 1 ảnh BEV + 1 ảnh nghiêng có/không plume, cùng frame.
3. PM chạy `ponytail-review` trên toàn bộ diff v2; audit độc lập 0 GPU, **không** tin commit message.

## Tiêu chí nghiệm thu

- [ ] Bảng số có đủ 8 dòng, mỗi dòng một marker.
- [ ] Mật độ khớp Fig. 11a ở tốc độ đo được, sai số ±50 detection; lệch thì **ghi lệch**, không sửa số.
- [ ] `ring` phủ 0–31, median 4 ± 1.
- [ ] `intensity` p50 = 0, p90 = 1, p99 = 3 ± 1.
- [ ] Ảnh BEV: plume nằm sau đuôi, không xuyên thân xe.
- [ ] `pytest -q tests/` ≥ **239** passed / 4 skipped.
- [ ] Biên bản nghiệm thu ghi trong ticket này: số đo, nguồn, phần chưa khớp.

## Cấm

- Không train lại trước khi ticket này xong.
- Không dùng "ra gain" làm tiêu chí nghiệm thu.
