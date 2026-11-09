# Ticket 11-c — sweeps không tồn tại trong dataset keyframes → mini split ra 0 mẫu

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `main`, HEAD `6cf4275`.

## Triệu chứng (kernel v5, nguynhuy9669/bevfusion-spray-train)

Log 911 KB, 4.900 dòng, kết thúc:

```
MINI_SPLIT_MISSING token=<mọi sample> path=/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes/sweeps/LIDAR_TOP/<...>.pcd.bin
MINI_SPLIT_FAILED got=0
SMOKE_FAILED mini_split
rc=1
```

## Nguyên nhân gốc (đã xác minh, không phải giả thuyết)

1. Dataset đang mount chỉ có **keyframes**: có `samples/LIDAR_TOP/*.bin`, **không có** `sweeps/LIDAR_TOP/*.bin` (đã kiểm bằng `kaggle datasets files`).
2. Metadata nuScenes vẫn khai báo `prev` cho từng sample_data, nên `_build_info` đi tìm file sweep và `raise FileNotFoundError` (`scripts/make_mini_split.py:206-207`). Mỗi sample ném lỗi → bị đếm `MINI_SPLIT_MISSING` → `got=0`.
3. `spray/mini_split.py:207` chặn thêm: `sweeps_prev empty (need >= 1)`.
4. Sweeps **không được dùng vào việc gì** trong pipeline hiện tại: `kaggle/train/smoke.py:67` ghi rõ ObjectPaste/db_sampler đã tắt vì thiếu `nuscenes_dbinfos_train.pkl`. Chúng chỉ đang chặn validate.

## Việc phải làm (đúng 3 file, không mở rộng)

**1. `scripts/make_mini_split.py` (~dòng 200-222) — không raise khi thiếu sweep file**

```python
if not os.path.exists(sweep_abs):
    break          # dataset keyframes-only: dừng thu sweeps, giữ những cái đã có
```
- Cho phép `info["sweeps"] == []` (bỏ luôn `raise`). Không đổi schema, không thêm key mới.
- Đếm số sample không có sweep; in **một** dòng tổng kết ở cuối: `MINI_SPLIT_NOSWEEPS n=<số>`.
- Cập nhật docstring dòng ~30-34 (đang nói "bắt buộc ≥1 sweep" và "chỉ bỏ frame đầu scene") cho khớp hành vi mới.

**2. `spray/mini_split.py:204-208` — nới validate**

- Giữ kiểm tra kiểu: `sweeps` phải là list/tuple → sai thì báo `"missing sweeps"`.
- **Bỏ** nhánh `elif len(sweeps) < 1: errors.append("sweeps_prev empty (need >= 1)")`.
- Cập nhật docstring của `validate_info` (dòng ~175-182): "at least one previous sweep" → "sweeps list (may be empty if the dataset ships keyframes only)".

**3. Log hygiene trong `scripts/make_mini_split.py`**

- `MINI_SPLIT_MISSING` chỉ in **5 dòng đầu**, sau đó im.
- Cuối run in `MINI_SPLIT_MISSING_TOTAL n=<số>` nếu > 0.
- Lý do: lần vừa rồi 4.000 dòng lặp làm log 911 KB, không đọc nổi.

**4. `tests/test_mini_split.py` — cập nhật test**

- `validate_info` với `sweeps=[]` phải trả `[]` (hợp lệ).
- Giữ nguyên test `sweeps` sai kiểu vẫn báo lỗi.
- Nếu test được `_build_info` với sweep path không tồn tại (mock `nusc`) thì thêm 1 test; nếu phải dựng mock quá lớn thì bỏ, ghi lý do trong commit body.

## Ràng buộc

- KHÔNG sửa `kaggle/train/main.py`, `kaggle/train/smoke.py`, `kernel-metadata.json`, configs.
- KHÔNG đổi tên marker đang có (`MINI_SPLIT_OK`, `MINI_SPLIT_FAILED`, `SMOKE_*`).
- `pytest -q tests/` phải xanh (hiện 111 passed, 4 skipped).
- 1 commit duy nhất, message: `fix(11-c): allow keyframe-only mini splits (no sweeps)`.

## Skill

Skill: không. Đây là ticket hạ tầng sửa đúng chỗ, không dùng `ponytail` (nó có xu hướng xoá bớt bước đang cần).

## Báo cáo khi xong

1. `git log --oneline -1` + `git show --stat HEAD`.
2. Output `pytest -q tests/` (số passed/skipped).
3. `grep -n "NOSWEEPS\|MISSING_TOTAL\|sweeps_prev" scripts/make_mini_split.py spray/mini_split.py`.