# 26: Hợp đồng dữ liệu + state theo scene cho generator v2

**Type:** task
**Status:** needs-triage
**Blocked by:** 25 (cần biết tốc độ/beam/`w`-`l` trước khi chốt chữ ký hàm)
**Chủ:** CommandCode. PM: Hermes.

## Hiện trạng

`PlumeTransform.__call__` hiện chỉ có `points (N,5)` + `boxes (M,9)` `[ĐO đọc code]`.
Bước 3–5 của v2 cần `ego_pose`, `sensor_origin`, `elevation_angles`, `speed`, `wfh`,
`frame_index`, `scene_token`, `epoch`. Không có các thứ này thì không làm được ray casting
và không tái lập được seed.

## Việc phải làm

1. `spray/plume_context.py` — dataclass `PlumeContext` chứa các trường trên; hàm
   `from_sample(sample, epoch)` đọc từ dict sample của dataset. Thiếu trường bắt buộc → raise
   lỗi rõ ràng (không im lặng dùng default).
2. `spray/plume_transform.py` — nhận `PlumeContext` qua `__call__`/`set_epoch`; giữ nguyên
   hành vi cũ khi context là `None` (để test cũ chạy).
3. `tests/test_plume_context.py` — 4 test: đủ trường; thiếu trường → raise; `context=None`
   → đường cũ; seed đổi theo `epoch`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ 192 passed / 4 skipped (không giảm).
- [ ] `grep -c PlumeContext spray/*.py` > 0 và đường cũ vẫn chạy.
- [ ] Không đổi chữ ký `inject_plume()` theo cách phá caller hiện có.

## Cấm

- Không đọc config mới trong `plume.py` bằng `os.environ`.
- Không refactor ngoài 2 file trên + 1 file test.
