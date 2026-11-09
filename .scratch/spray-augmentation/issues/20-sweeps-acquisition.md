# 20 — Lấy sweeps thật (sau khi smoke xong)

Trạng thái: **hoãn có chủ đích**. Smoke chạy keyframe-only trước (ticket 11-c), sweeps làm sau.
Mục đích file này: lúc có account nuScenes thì không phải suy lại gì.

## Vì sao cần

Pipeline hiện đọc 1 keyframe LiDAR. Bản paper cộng dồn 10 khung (1 keyframe + 9 sweep) — nặng hơn ~10× về số điểm.
Hệ quả nếu thiếu sweeps: ObjectPaste/db_sampler phải tắt; mật độ điểm thưa; plume (điểm **thêm vào**) chiếm tỉ lệ lớn hơn thực tế
⇒ effect size của A/B bị phóng đại. So sánh giữa 2 nhánh vẫn hợp lệ, số tuyệt đối thì không.

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