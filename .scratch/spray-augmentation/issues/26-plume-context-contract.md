# 26: Hợp đồng dữ liệu + state theo scene cho generator v2

**Type:** task
**Status:** needs-triage
**Blocked by:** 25
**Quyết định nguồn khối nước (2026-11-10, user chốt):** hướng (c) — sinh từ `metadata.txt` +
`poses.txt`, nghiệm thu bằng nhãn spray thật (`label == 2`). `boxes` là optional, `None` ⇒ metadata. (cần biết tốc độ/beam/`w`-`l` trước khi chốt chữ ký hàm)
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

---

## PM nghiệm thu — 2026-11-10

**Trạng thái: done.** CommandCode `--skill tdd --max-turns 80`, log `/tmp/t26.log`, exit 0.

| Kiểm | Kết quả `[ĐO]` |
|---|---|
| `pytest -q tests/` (2 lượt) | **200 passed, 4 skipped** = 192 cũ + **8 test mới**, 0 skip mới |
| `git status --porcelain` | đúng 3 file: `spray/plume_context.py` (mới, 294 dòng), `spray/plume_transform.py` (+17 dòng), `tests/test_plume_context.py` (mới, 135 dòng) |
| `git diff --stat spray/plume.py` | **rỗng** — chữ ký `inject_plume()` không đổi |
| `spray/config/*.yaml` | 0 file bị chạm |
| `grep os.environ` trong 3 file | **0 hit** |
| `grep "0\.411\|1\.84"` trong 3 file | **0 hit** — không hardcode mặt đường |

**Nội dung thật (PM đọc code, không tin báo cáo):**

- `PlumeContext` frozen dataclass, 8 trường bắt buộc + 3 optional, validate trong `__post_init__`;
  `wfh_mm` ràng buộc `0 < wfh_mm <= 1.2` (mm), `ego_pose` kiểm trực giao `|R·Rᵀ−I| < 1e-6`,
  `road_z_m` bắt buộc finite.
- `from_sample()` **không có default** cho `wfh_mm`/`road_z_m`; thiếu key → `PlumeContextError` liệt kê
  **tất cả** key thiếu, sắp xếp alphabet. `ego2global` được nghịch đảo thành world→ego; `ego_pose` dùng nguyên.
  Không suy `ego_speed_mps` từ dịch chuyển pose (đúng phát hiện #1 của ticket 25).
- `seed_for()` dùng `blake2b`, không dùng `hash()` (tránh randomize theo process).
- `compute_elevation_deg()` tính `atan2(z, hypot(x,y))`, không đọc cột 4 — đúng phát hiện #4.
- `PlumeTransform.set_epoch()` + nhánh `results["plume_context"]`: có context thì seed =
  `seed_for(scene_token, frame_index, epoch, self.seed)`; **không** có context thì đường cũ. Test #3 chứng minh
  đường cũ bằng `np.array_equal` trên `points`, `points_clean` và `spray_stats["injected"]`.

**Ghi chú phạm vi:** ticket này chưa sinh plume mới. Nó chỉ dựng hợp đồng dữ liệu + nhánh seed; bước 1–5 của
v2 (khối sau đuôi, vòng đời, ray casting, attenuation) là ticket 28–30. `compute_elevation_deg()` hiện chỉ có
test gọi tới, sẽ được ticket 29 dùng thật.
