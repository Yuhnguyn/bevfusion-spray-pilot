# 20 — Lấy sweeps thật (sau khi smoke xong)

Trạng thái: **hoãn có chủ đích**. Smoke chạy keyframe-only trước (ticket 11-c), sweeps làm sau.
Mục đích file này: lúc có account nuScenes thì không phải suy lại gì.

## Vì sao cần

Pipeline hiện đọc 1 keyframe LiDAR. Bản paper cộng dồn 10 khung (1 keyframe + 9 sweep).
Hệ quả nếu thiếu sweeps: ObjectPaste/db_sampler phải tắt; **không có thông tin thời gian** (không thấy vật bị che ở khung trước);
plume (điểm **thêm vào**) chiếm tỉ lệ lớn hơn thực tế ⇒ effect size của A/B bị phóng đại.

**Đính chính kỹ thuật [CODE], đọc từ `mit/bevfusion/mmdet3d/datasets/pipelines/loading.py:184-190`:**
config `mit/bevfusion/configs/nuscenes/default.yaml` đặt `sweeps_num: 9` + `pad_empty_sweeps: true`.
Khi `sweeps == []`, loader **copy keyframe 9 lần** rồi `cat` → 10× số điểm nhưng **toạ độ trùng nhau**.
Nghĩa là: không thưa hơn về số điểm, nhưng (a) không có thông tin mới, (b) voxel hoá gộp các điểm trùng
nên nhận thức vẫn là single-scan, (c) trả giá 10× công đoạn nạp/collate mỗi bước.
Vì vậy với dataset keyframe-only phải đặt `sweeps_num: 0` (trung thực + nhanh hơn), và chỉ đặt 9 khi có sweeps thật.

## Đã kiểm bằng `kaggle datasets files` [ĐO]

| Dataset | Có `sweeps/`? |
|---|---|
| `sahangunasekara92/nuscenes-v1-0-full-keyframes` (45,7 GB) | không |
| `diamond1234/nuscenestrainval` (27,9 GB) | không |
| `pqelectrohis/nuscenes-trainval08-blobs` (30,5 GB) | không (chỉ `samples/`, 3.432 keyframe) |
| `aadimator/nuscenes-mini` (5,37 GB) | **có** — `sweeps/LIDAR_TOP/*.pcd.bin` thật, 404 keyframe, 10 cảnh |

S3 công khai `motional-nuscenes.s3.amazonaws.com/public/…` trả **404** ⇒ phải đăng nhập nuscenes.org.

## Vấn đề chia blob — điểm phải quyết trước khi tải

Blob chính thức chia theo **cảnh**, không theo mẫu. Mini split hiện tại lấy 4.000 keyframe rải khắp 850 cảnh
⇒ lấy đủ sweeps cho nó phải tải **cả 10 blob ≈ 300 GB**. Không khả thi (đĩa local còn 14 GB [ĐO]).

Cách đúng: **giới hạn A/B trong 1 blob**. Blob 08 có 3.432 keyframe [ĐO từ listing dataset trên].
3.432 khung là đủ cho pilot (train/val ~ 2.7k/0.7k), và chỉ cần 1 lần tải.

## Ước lượng dung lượng sau khi cắt [ƯỚC]

Chỉ giữ `sweeps/LIDAR_TOP` (bỏ toàn bộ camera sweep — pipeline không dùng):

- 9 sweep/keyframe: 3.432 × 9 × ~0,8 MB ≈ **25 GB**
- 3 sweep/keyframe: ≈ **8 GB** — mật độ gấp 4 lần hiện tại, đủ để hết phóng đại effect size

## Các bước khi có account

```bash
# 1. tải 1 blob (cần account nuScenes, license non-commercial)
curl -L -o /path/v1.0-trainval08_blobs.tgz "<link từ nuscenes.org>"

# 2. chỉ giải nén sweeps LiDAR
tar -xzf v1.0-trainval08_blobs.tgz --wildcards '*/sweeps/LIDAR_TOP/*'

# 3. cắt còn N sweep/keyframe + dựng metadata v1.0-trainval08 (script cần viết, ticket riêng)

# 4. upload dataset private
kaggle datasets create -p <dir> --dir-mode zip
```

Đĩa cần: blob 30 GB + phần đã cắt 8–25 GB ⇒ phải dọn ~60 GB trước, **hoặc** làm bước 1–2 trong Colab
(đĩa ~100 GB) rồi upload từ đó. Dọn đĩa local phải xin phép user trước.

## Điều kiện nghiệm thu

- `kaggle datasets files <mới>` thấy `sweeps/LIDAR_TOP/*.pcd.bin` đúng số lượng đã cắt.
- `scripts/make_mini_split.py` sinh `sweeps` khác rỗng, log có `MINI_SPLIT_NOSWEEPS n=0`.
- `validate_info` pass với `len(sweeps) >= 1`.

## 20-b: chứng minh đường sweeps trên nuScenes mini — đã code xong, chưa chạy kernel

Mục đích: trước khi bỏ công tải blob 25–30 GB, chứng minh bằng số đo rằng loader thật sự đọc nhiều khung hơn.

Đã làm (commit `??`, HEAD trước là `a46e188`):

- `kaggle/train/smoke.py` — thêm `--nusc-version` (mặc định `v1.0-trainval`, không đổi luồng cũ) và `--sweeps-probe`:
  dựng split `v1.0-mini` với `n=300`, đo `SWEEPS_INFO n_sweeps`, `SWEEPS_PTS mode=single|multi`,
  `SWEEPS_UNIQUE ratio` (bắt đúng chuyện `pad_empty_sweeps` nhân bản keyframe), `STEP_TIME` cho cả hai mode.
- `kaggle/train/kernel-metadata.json` — `dataset_sources` 2 → **3** (thêm `aadimator/nuscenes-mini`) [ĐO].
- `tests/test_smoke_sweeps.py` — 4 test thuần Python.
- `pytest -q tests/` → **117 passed, 4 skipped** (trước 113) [ĐO].
- An toàn: `build_pipeline_steps()` deepcopy từng step [CODE `smoke.py:207-243`] nên `_set_sweeps_num` không rò rỉ giữa hai mode.

Chưa nghiệm thu: chưa push kernel, nên **chưa có** `SWEEPS_OK`/`SWEEPS_FAILED` thật. Việc tiếp theo là push v7 chạy `--sweeps-probe`.

## 20-d: kết quả đo thật trên kernel v8 — `SWEEPS_OK`

Chuỗi chạy: `06cdf0f` (task_args = `--sweeps-probe`) → v7 chạy sai vì `main.py` đọc `task_args.txt` theo `__file__` (`/kaggle/src`) thay vì `e2e.REPO` ⇒ sửa ở `fb12ffc` → v8 đúng.

Log v8 (`/tmp/ktrain_raw.log`, kernel `COMPLETE`, rc=0):

```
TASK_ARGS_FILE /kaggle/working/repo/kaggle/train/task_args.txt
TASK_ARGS --sweeps-probe
SWEEPS_SPLITS val=2 path=/kaggle/working/mini_splits.py
MINI_SPLIT_OK n=300 scenes=8 gt_boxes=14808 val_scenes=2 seed=0
SWEEPS_INFO version=v1.0-mini n_sweeps=10
SWEEPS_PTS mode=single n=34720
SWEEPS_PTS mode=multi n=273637
SWEEPS_UNIQUE mode=multi ratio=0.9879
STEP_TIME mode=single s_per_step=1.2513
STEP_TIME mode=multi s_per_step=1.9198
SWEEPS_OK n_single=34720 n_multi=273637 ratio=0.9879
```

Đọc số:

- 10 sweep/keyframe thật ⇒ 273.637 điểm so với 34.720 điểm của keyframe, **7,9×**.
- `ratio = 0,9879` ⇒ 98,8 % toạ độ là phân biệt, tức **không** phải keyframe bị nhân bản (nhân bản sẽ cho ≈0,1). Đây là bằng chứng định lượng rằng đường sweeps đọc dữ liệu thật.
- Giá phải trả: **+0,67 s/step** (1,2513 → 1,9198 s, **+53 %**) ở batch 2 trên T4. Với 2.000 bước ⇒ +22 phút/arm.
- Chi phí nằm ở I/O đọc 9 file `.pcd.bin` thêm + transform theo thời gian, không phải ở số điểm: lượt A/B trên dữ liệu keyframe-only (10× điểm nhân bản, 1,4653 s/step) còn nhanh hơn lượt sweeps thật.

Hệ quả cho kế hoạch:

- Đường sweeps thật **chạy được trên kernel** ⇒ tải blob 25–30 GB không còn là việc mò, chỉ còn là việc đĩa/thời gian.
- Nếu chọn keyframe-only cho báo cáo thì phải đặt `sweeps_num: 0`: giữ `9` chỉ tổn công nạp 9 bản sao trùng toạ độ mà không thêm thông tin.
- `peak_gb` chưa được log trong probe (chỉ có `STEP_TIME`); nếu cần con số bộ nhớ cho cấu hình 10 sweep thì phải thêm một dòng log rồi chạy lại 1 lượt ~12 phút.