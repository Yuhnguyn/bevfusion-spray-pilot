# 20b: chứng minh đường sweeps chạy thật trên nuScenes mini

HEAD: a46e188  Nhánh: main
Skill: không (ticket hạ tầng/đo đạc — không refactor, không cần ponytail)

## Hiện trạng (đã kiểm)

- `kaggle/train/smoke.py:101-110` — `find_dataroot()` chỉ nhận `v1.0-trainval/sample.json`.
- `kaggle/train/smoke.py:126-170` — `run_mini_split()` gọi `scripts/make_mini_split.py` với `--n 4000`, không truyền `--version`.
- `kaggle/train/smoke.py:112-124` — `ensure_splits_file()` hardcode đòi đúng 150 scene val (đúng cho trainval, sai cho mini).
- `scripts/make_mini_split.py:70` — đã có `--version`, mặc định `v1.0-trainval`; `--splits` nhận file chứa `val = [...]`.
- `mit/bevfusion/configs/nuscenes/default.yaml` — `LoadPointsFromMultiSweeps` với `sweeps_num: 9`, `pad_empty_sweeps: true`.
- `mit/bevfusion/mmdet3d/datasets/pipelines/loading.py:184-190` — khi `sweeps == []` loader **copy keyframe 9 lần**.
- Dataset Kaggle `aadimator/nuscenes-mini` [ĐO]: có `v1.0-mini/*.json`, `samples/LIDAR_TOP/*.pcd.bin`, `sweeps/LIDAR_TOP/*.pcd.bin` (3.531 file sweep).

## Mục tiêu

Chứng minh bằng số đo rằng khi **có sweeps thật**, pipeline nạp nhiều khung hơn keyframe đơn; và đo giá phải trả của việc `sweeps_num: 9` khi **không** có sweeps (nhân bản keyframe).

## Việc phải làm

1. `kaggle/train/smoke.py` — thêm `--nusc-version` (mặc định `v1.0-trainval`) và biến nó thành nguồn duy nhất cho:
   - `find_dataroot()`: dò `<root>/<version>/sample.json`; thêm đường dẫn mặc định `/kaggle/input/nuscenes-mini`.
   - `ensure_splits_file()`: nếu version là `v1.0-mini` thì lấy 2 scene cuối (sorted) của `nusc.scene` làm val, ghi file `val = [...]`, log `SWEEPS_SPLITS val=2`; nếu là trainval giữ nguyên hành vi cũ (150 scene, `SMOKE_SPLITS_OK`).
   - `run_mini_split()`: truyền `--version <version>` và `--n <n>` (mặc định 4000 giữ nguyên).
2. `kaggle/train/smoke.py` — thêm chế độ `--sweeps-probe` (khi bật thì chỉ chạy phần đo sweeps, không chạy A/B):
   - Dựng split mini từ `v1.0-mini` với `--n 300`.
   - Lấy **cùng một sample** (sample đầu tiên của split), build 2 pipeline từ `DATASET_CONFIG`:
     - `mode=single`: `LoadPointsFromMultiSweeps.sweeps_num = 0`
     - `mode=multi`: giữ nguyên 9
   - Log `SWEEPS_INFO version=<v> n_sweeps=<len(info['sweeps'])>`.
   - Log `SWEEPS_PTS mode=<single|multi> n=<số điểm>` cho mỗi mode.
   - Log `SWEEPS_UNIQUE mode=multi ratio=<unique_rows/n_rows, 4 chữ số thập phân>` — dùng `np.unique(points[:, :3], axis=0)`.
   - Chạy 5 bước train (batch 2) cho mỗi mode bằng đúng `build_loader`/model hiện có, log `STEP_TIME mode=<single|multi> s_per_step=<f>`.
   - Kết thúc bằng `SWEEPS_OK` nếu `n_multi > n_single * 2` và `ratio > 0.9`; ngược lại `SWEEPS_FAILED <lý do>`.
3. `kaggle/train/kernel-metadata.json` — thêm `aadimator/nuscenes-mini` vào `dataset_sources` (giữ nguyên các dataset cũ).
4. `tests/test_smoke_sweeps.py` — test thuần Python (không cần GPU/dataset):
   - `find_dataroot` với monkeypatch tạo `tmp/v1.0-mini/sample.json` trả đúng root khi `version="v1.0-mini"`.
   - `ensure_splits_file` với version mini dùng danh sách scene giả (2 phần tử) ghi ra `val = [...]` parse được.
   - Hàm thuần `sweeps_summary(points_single, points_multi)` trả `n_single`, `n_multi`, `ratio` đúng với mảng numpy nhỏ tự tạo (test nhân bản → ratio thấp; test dữ liệu khác nhau → ratio cao).

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` xanh, số test tăng thêm ≥ 3, không test nào bị skip mới.
- [ ] `python3 -c "import json;print(len(json.load(open('kaggle/train/kernel-metadata.json'))['dataset_sources']))"` tăng thêm 1.
- [ ] Không đổi mặc định cũ: chạy không có `--sweeps-probe` vẫn phải chạy đúng luồng A/B của v6 và vẫn log `SMOKE_OK` với `s_per_step`/`peak_gb` (chỉ cần đảm bảo bằng đọc code + test, KHÔNG push kernel).
- [ ] `git diff` chỉ chạm 4 file nêu trên.

## Cấm

- Không sửa `mit/bevfusion/**` (vendor), không sửa `spray/ab_config.py`, không sửa ngân sách A/B, không push kernel, không tải dữ liệu.
- Không đổi `--n 4000` mặc định; không tăng timeout; không nuốt lỗi bằng try/except rỗng.
- Không commit; để PM nghiệm thu.