# Dispatch 29d-v3 — ngưỡng cổng = sàn đóng băng, half-split stratify theo `itr_after_water`

Skill: tdd

## 0. Bối cảnh bắt buộc đọc

- Ticket: `.scratch/spray-augmentation/issues/29d-v3-threshold-floor.md`
  (đọc hết, đây là nguồn yêu cầu duy nhất).
- Code liên quan:
  - `spray/semantic_split.py` — `CRITERIA_SPECS` (dòng 84–112, **sàn đóng
    băng**), `halves()` (dòng 427, dead code), phần tính ngưỡng (dòng 485–600).
  - `scripts/semantic_spray_split.py` — chia half inline (dòng 148–150), in
    bảng gate (dòng 284–325), text mô tả ngưỡng (dòng 497, 550).
  - `tests/test_semantic_split.py` — test hiện có.
- HEAD: `09cd650` (gate v2 PASS 7/7, 260 passed, 4 skipped).

## 1. Vấn đề, một câu

Cổng tính `ngưỡng = max(sàn, 2 × Δ_halfsplit)`. Vì `cal_a`/`cal_b` được chia
xen kẽ trên danh sách **đã sắp theo `itr_after_water`**, `Δ_halfsplit` đo
gradient nước thay vì nhiễu lấy mẫu (5,4 % → 33,5 %), khiến ngưỡng G1 bị nới
15 % → 67 %. Cổng tự nới để dễ qua.

## 2. Việc phải làm

Đúng mục §3 của ticket, tóm tắt thứ tự:

1. Viết lại `halves()` thành hàm stratify theo `(group, itr_after_water)`,
   deterministic, không RNG. Script gọi hàm này thay cho `index % 2`.
   Không để hai bản cài đặt.
2. Bỏ `max(...)`: `threshold` = `spec.floor_rel` / `spec.floor_abs` tuyệt đối.
   `Δ_halfsplit` vẫn tính, chỉ để chẩn đoán; nếu `observed > 2 ×
   Δ_halfsplit` thì note thêm `vượt sàn nhiễu nội tại`, **không đổi verdict**.
3. Đổi tiêu đề cột thành `Δ_halfsplit (chẩn đoán)`; sửa text dòng 497 và 550.
4. Viết ≥ 4 test mới theo §4 ticket.

## 3. Ràng buộc

- **Không** đổi 7 con số sàn, không đổi luật chia `cal`/`held-out`
  (`SPLIT_VERSION`, `RULE_VERSION` giữ nguyên `v2-parity-flip-by-cell`),
  không đổi `cluster_angular`, không đổi `frames_per_scene` mặc định.
- **Không** chạy `--measure` full (PM chạy).
- **Không** commit, không push.
- Chỉ sửa: `spray/semantic_split.py`, `scripts/semantic_spray_split.py`,
  `tests/test_semantic_split.py`. Nếu buộc phải sửa file khác thì **dừng lại và
  báo**, không tự mở rộng phạm vi.

## 4. Định nghĩa xong

- `pytest -q tests/` ≥ 264 passed, 4 skipped, không test nào bị skip thêm.
- Ba lệnh smoke ở §6 ticket chạy sạch; dán **nguyên văn** output.
- Bảng gate trong output smoke: cột `ngưỡng` đúng bằng sàn (G1 `15.0%`,
  G2 `20.0%`, G3 `20.0%`, G4 `0.100`, G5 `15.0%`, G6 `0.200`, G7 `0.500`).
- Trả lời cuối cùng gồm: danh sách file sửa, tên các test mới, output smoke,
  và giá trị `Δ_halfsplit` mới của G1 để PM so với 33,5 %.

## 5. Không được làm

- Không "tiện tay" refactor, đổi format báo cáo ngoài 4 mục trên.
- Không nới ngưỡng dưới bất kỳ hình thức nào (kể cả khi test đỏ vì ngưỡng
  chặt — trường hợp đó báo lại, không sửa sàn).
- Không thêm dependency mới.