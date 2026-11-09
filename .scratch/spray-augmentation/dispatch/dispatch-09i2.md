# Ticket 09-i2 — làm chặt test 3 (chỉ sửa `tests/test_pipeline_e2e.py`)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `fc8a363` · không push Kaggle · ~10 turn.

## Vấn đề của test hiện tại

`test_streams_share_frame_and_aug_matrix` chụp `lidar_aug_matrix` **trước** `PlumeTransform` rồi so với
sau chuỗi ⇒ chỉ chứng minh "không transform nào sau đó sửa matrix", gần như hiển nhiên. Nó **không** chứng minh
hai stream cùng một frame.

## Việc phải làm — chỉ trong `test_streams_share_frame_and_aug_matrix`

Chụp thêm **snapshot điểm ngay trước khi `PlumeTransform` chạy** (`np.array(_array(results["points"]), copy=True)`),
sau khi chạy hết chuỗi assert **4 điều**:

1. `_array(batch["points_clean"]).tobytes() == snapshot.tobytes()` — clean stream **đúng bằng** frame tại thời điểm chèn.
2. `len(_array(batch["points"])) == len(snapshot) + int(batch["spray_stats"]["injected"])` — stream bẩn = frame + plume.
3. `np.array_equal(_array(batch["lidar_aug_matrix"]), aug_matrix)` — matrix không bị sửa sau khi chèn.
4. `batch["sample_idx"] == expected_idx` — cùng frame.

Giữ nguyên 3 test còn lại, giữ nguyên tên 4 test.

## Ràng buộc

- Chỉ sửa `tests/test_pipeline_e2e.py`. Không sửa file nào khác. Không thêm dependency. Không gọi `kaggle`.
- Local: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **63 passed, 4 skipped**.

## Commit

```
test(e2e): pin the clean stream to the exact frame seen at injection
```

Dán output pytest + `git log --oneline -1` + `git status --porcelain`.