# Nhánh `nuscenes-train` — trạng thái xuất phát

Tách từ `sspp` @ `9b174b4` ngày 2026-11-26. **200 passed, 0 failed.**

## 0. Trạng thái 2026-11-26 16:00 — đọc plan mới, KHÔNG đọc §4 dưới

§4 trong file này đã **SAI**. Nó bảo merge `main` để lấy dây train, nhưng:

    git rev-list --count main..HEAD  → 96
    git rev-list --count HEAD..main  → 0
    git merge main                   → Already up to date.

`main` là **tổ tiên** của nhánh này ⇒ merge không mang về gì. Dây train biến mất vì bị **xoá**
trên chính nhánh này ở hai commit sspp-cleanup:

    f7f0914  chore(sspp): drop the nuScenes training chain (9 modules + 18 tests)
    c2aa23c  chore(sspp): drop the five Kaggle kernels of the nuScenes chain

Quyết định (user, 2026-11-26): **không restore gì từ `main`**. Dựng lại theo nhu cầu, bám
`spray/` hiện tại. Kế hoạch chi tiết: **`.hermes/plans/2026-11-26_155812-nuscenes-train-plan.md`**.

Ba số đo chặn đường trong plan đó, đo trên máy này:

| # | phát hiện | hệ quả |
|---|---|---|
| 1 | generator sinh **0 cụm** ở mọi vận tốc < 50 km/h (`_CLUSTER_VISIBLE_BY_SPEED` bắt đầu ở 50) | nuScenes đô thị gần như không được augment ⇒ phải chốt miền trước khi train |
| 2 | box nuScenes `[x,y,z_tâm,w,l,h,yaw]` ≠ adapter SSPP `[x,y,z_đáy,dài,rộng,cao,yaw]` | plume phun vào thân xe, lơ lửng 0,87 m nếu không đổi |
| 3 | máy này: torch CPU, không có nuscenes/mmdet3d/mmcv/spconv, không có nuScenes, đĩa trống 28 GiB | train phải chạy trên Kaggle |

## 1. Có gì

Generator plume **đã sửa xong** (A8/A9/A10):

| thứ | giá trị | ghi chú |
|---|---|---|
| `MAX_AGE_FACTOR` | **12.0** | trần số học; `4T` là JS `[CODE]`, paper không có |
| `RADIUS_MAX_M` | **2.0** | p99 lognormal (1,61) < 2,0 < p99,9 (2,79) |
| `diffusion_alpha` | **đã xoá** | mở rộng ngoài paper, đang sai 6,6× |
| `sample_wfh_mm` | **bật mặc định** | `[PAPER]` §V, mẫu 1 lần/scene, Exp(mean 1,0) clip [0,1;1,2] |
| miền sinh | **2,5–50 m** | default của `PlumeStateConfig` |
| tầng materialise | **đã xoá** | A10; production chỉ dùng `raycast_frame` |
| `plume_state.py` | 624 dòng | so với 465 trên `main` |

`spray/plume_transform.py` có, đã đăng ký `PIPELINES` của mmdet3d.

## 2. Thiếu gì — phải merge từ `main`

`main` HEAD `f3fb7d2` **là tổ tiên trực tiếp của `sspp`** (không phân kỳ), nên merge sạch.
21 commit chưa push trên `main` chứa **toàn bộ dây train nuScenes**:

```
spray/ab_config.py      build arm A (sạch) vs arm B (có plume) + diff_paths()
                        kiểm bằng máy: hai arm khác đúng 1 đường
spray/pipeline.py       thay DefaultFormatBundle3D / Collect3D để points_clean
                        xuống được model
spray/freeze.py         đóng băng nhánh camera theo TÊN tham số (không theo attribute)
spray/model_routing.py  BEVFusion subclass: camera thấy points_clean, lidar thấy points
kaggle/train/main.py    339 dòng — train
kaggle/train/ab_run.py  467 dòng — chạy A/B
kaggle/train/ab_eval.py eval
kaggle/train/{smoke,probe}.py, task_args.txt, kernel-metadata.json
```

Cả 6 file này hiện **THIẾU** trên `nuscenes-train`.

**Cảnh báo khi merge:** `main` còn generator cũ (`MAX_AGE_FACTOR=4.0`, `RADIUS_MAX_M=1.0`,
không có `sample_wfh_mm`). Xung đột ở `spray/plume*.py` phải giải **theo phía `nuscenes-train`**.
Cách kiểm nhanh sau merge:

```bash
grep -nE 'MAX_AGE_FACTOR|RADIUS_MAX_M' spray/plume_state.py   # phải là 12.0 / 2.0
grep -c 'sample_wfh_mm' spray/plume.py                        # phải là 3
grep -rn 'diffusion_alpha' --include=*.py spray/               # phải rỗng
```

## 3. Chưa có — phải cài / tải

**Môi trường (đều MISSING trên máy này):**

```
nuscenes     MISSING    nuscenes-devkit
mmdet3d      MISSING
mmcv         MISSING    phải build đúng version với torch, đây là bước dễ hỏng nhất
spconv       MISSING
torch        OK
numpy        OK
```

**Dữ liệu:** không có nuScenes nào trên máy (`find` không thấy). `data/` chỉ có
`SemanticSprayDataset` 31 GB. Cần mini (~4 GB) hoặc full (~300 GB).

**Checkpoint có sẵn:** `data/bevfusion-det.pth` (156 MB = 163.715.701 byte, bản **fusion**),
`data/lidar-only-det.pth` (33.362.653 byte, bản **LiDAR-only**).
`docs/PROJECT.md` §7 chốt: phải dùng `lidar-only-det.pth` đúng **33.362.653 byte**; nếu trỏ nhầm
bản fusion thì `strict=False` che lỗi và model nửa khởi tạo.

## 4. ~~Bước kế tiếp, theo thứ tự~~ — ĐÃ THAY BẰNG `.hermes/plans/2026-11-26_155812-nuscenes-train-plan.md`

Giữ lại làm mốc lịch sử. Bước 1 ("Merge `main`") **sai**, xem §0.

1. Merge `main` vào `nhanh này` (giải xung đột theo phía nhánh hiện tại) → có dây train.
2. Cài `nuscenes-devkit` + `mmdet3d`/`mmcv`/`spconv` (hoặc dùng ảnh Docker có sẵn).
3. Tải nuScenes **mini** trước để chạy `kaggle/train/smoke.py` — xác nhận dây chạy được
   trước khi đụng bản full.
4. `scripts/build_plume_speed_index.py` sinh `data/plume_speed_index.json` mà `ab_config.py` cần.
5. Chạy arm A vs arm B; `diff_paths()` phải chứng minh hai config khác đúng 1 đường.

Ngoài phạm vi nhánh này: sửa generator thêm, chạy lại cổng C trên SSPP, đụng `main`.
