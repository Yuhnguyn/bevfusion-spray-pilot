# Ticket 11-a — mini train split + infos builder (local, không cần GPU)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `274b5cb` · ~45 turn.
Test chuẩn: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` (đang **94 passed, 4 skipped**).
**Không** đụng Kaggle, **không** sửa `mit/`, `spray/plume.py`, `spray/ab_config.py`, `spray/freeze.py`.

## Vấn đề

Ticket 11 cần train 2000 bước × batch 2 = **4.000 sample** trên nuScenes. Dựng infos cho toàn bộ
28.130 sample train là việc nặng (chục phút trên Kaggle mỗi lần chạy) và không cần. Cần một **tập con cố
định 4.000 sample**, giống hệt nhau giữa arm A và B, sinh ra bằng seed.

## File 1 — `spray/mini_split.py`

Hàm thuần, **không** import `nuscenes` ở module level (local không có devkit):

```python
VAL_SCENES_CACHE = None

def load_val_scenes(path_or_none=None) -> frozenset[str]:
    """Official nuScenes val scene names."""

def select_tokens(samples, n, seed, val_scenes) -> list[str]:
    """samples: list[dict] có 'token' và 'scene_token'.
    Loại bỏ sample thuộc val scene, sắp xếp token tăng dần rồi lấy rng.choice
    không hoàn lại bằng random.Random(seed). Trả list đã sắp xếp lại.
    Cùng (samples, n, seed, val_scenes) ⇒ cùng kết quả, chạy lại trên máy khác vẫn vậy."""

def validate_info(info) -> list[str]:
    """Trả danh sách lỗi (rỗng = hợp lệ). Kiểm: token, scene_token, timestamp, 6 CAM_*,
    LIDAR_TOP, sweeps_prev >= 1, gt_boxes shape (N,7), gt_names cùng độ dài, 'cams' có
    calibrated_sensor + sensor2ego + ego2global."""

def summarize(infos) -> dict:
    """n_samples, n_scenes, gt_boxes_total, per_cam_count, per_class_counts."""
```

`load_val_scenes` mặc định đọc `mit/bevfusion/nuscenes/utils/splits.py` (grep `val = [`); nếu không có
file, nhận `path_or_none` trỏ tới file splits. Nếu cả hai không có ⇒ **raise**, không đoán bằng split
khác (sai split = rò rỉ dữ liệu val vào train, hỏng cả thí nghiệm).

## File 2 — `scripts/make_mini_split.py` (CLI, chạy trên Kaggle)

```
python scripts/make_mini_split.py \
  --dataroot /kaggle/input/nuscenes-v1-0-full-keyframes \
  --out data/infos/mini_train_4000.pkl \
  --n 4000 --seed 0 --max-sweeps 10
```

- Đọc `v1.0-trainval` metadata qua `NuScenes(version=..., dataroot=..., verbose=False)` — import **trong
  main()**, không ở module level.
- Gọi `select_tokens` để lấy 4.000 token; **không** dùng `create_nuscenes_infos` của vendor cho toàn bộ vì
  nó không nhận filter token. Xem `mit/bevfusion/tools/data_converter/nuscenes_converter.py`: hàm
  `_fill_trainval_infos` nhận `nusc, train_scenes, val_scenes, ...` và có vòng lặp per-sample — **viết bản
  rút gọn** dựa đúng logic đó (cùng key `cams`, `lidar_path`, `sweeps`, `gt_boxes`, `gt_names`, `num_pts`),
  chỉ chạy trên 4.000 token đã chọn. Ghi rõ trong docstring là bản rút gọn của file nào, dòng nào.
- Lưu pickle format `dict(infos=[...], metadata=dict(version=..., ...))` — cùng format vendor để
  `NuScenesDataset` đọc được.
- In kết quả: `MINI_SPLIT_OK n=<n> scenes=<k> gt_boxes=<m> val_scenes=<v> seed=0`
- Nếu số sample dựng được < 3.800 ⇒ `MINI_SPLIT_FAILED got=<n>` + exit 1 (thiếu file ảnh/LiDAR thì biết ngay,
  không để vỡ giữa lúc train).
- Cờ `--dry-run`: chỉ in số sample sẽ chọn, không đọc ảnh/LiDAR, không ghi file.

## Test — `tests/test_mini_split.py` (local, không cần dữ liệu thật)

Tối thiểu 8 test, **không** test nào cần `nuscenes`:

1. `select_tokens` cùng seed ⇒ cùng kết quả; khác seed ⇒ khác (với n nhỏ so với tổng).
2. Không trùng token, đúng `n` phần tử.
3. Loại sạch sample thuộc val scene.
4. Đầu ra đã sắp xếp (thứ tự không phụ thuộc thứ tự input).
5. `n` lớn hơn số ứng viên ⇒ raise `ValueError` có số cụ thể trong message.
6. `validate_info` pass trên một info tổng hợp hợp lệ.
7. `validate_info` bắt được: thiếu 1 camera, `gt_boxes` sai shape, `sweeps_prev` rỗng.
8. `summarize` đếm đúng `n_samples`, `n_scenes`, `gt_boxes_total` trên 3 info giả.

## Ràng buộc

- Không sửa file ngoài: `spray/mini_split.py`, `scripts/make_mini_split.py`, `tests/test_mini_split.py`.
- Không bịa hằng số nào của nuScenes (số camera, tên channel) — đọc từ vendor converter.
- Commit message dòng cuối: `feat(mini-split): deterministic 4000-sample train subset and infos builder`

## Báo cáo

- `git log --oneline -1`, `git status --porcelain`
- số test trước/sau
- output `--dry-run` nếu chạy được local (không có nuScenes local thì ghi rõ "không chạy được, thiếu devkit")
- danh sách key của info dict (để PM so với vendor)