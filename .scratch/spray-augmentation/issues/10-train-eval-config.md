# 10: Train/eval config A/B

**What to build:** Hai config chỉ khác nhau ở spray: cùng checkpoint, scene split, freeze list, optimizer, LR, seed, data order, batch size, và số update. Kèm memory/time probe trước khi train.

**Blocked by:** 02, 04, 09

**Status:** done (`fcaa4f9` + `2ed78b3`, nghiệm thu 2026-11-08)

## PM chốt 2026-11-08 (user duyệt)

**Freeze list:** đóng băng nhánh camera — mọi tham số tên bắt đầu bằng `img_backbone.`, `img_neck.`,
`encoders.camera.`; **mở** LiDAR encoder (`pts_*`, `encoders.lidar.`), fusion (`fuser.`), BEV backbone/neck
(`decoder.`), head (`heads.`). Tên lạ ⇒ ghi vào `unmatched` để kernel in ra, không raise.

**Ngân sách train [CHỌN]:** `max_iters = 2000`, `batch_size = 2`, `lr = 1e-4`, `weight_decay = 0.01`,
AdamW, `warmup_iters = 100`, `grad_clip = 5.0`, `seed = 0`, `eval_every = 500` (~1,5 h T4/arm).

**Checkpoint:** link chính thức trong vendor README **đã chết** (`bevfusion.mit.edu` → `hanlab.mit.edu`
→ 404, kiểm 2026-11-08). Bản dùng được:
`https://huggingface.co/SCU-VIP-Lab/Pretrained_BEVFusion/resolve/main/bevfusion-det.pth`,
156 MB (163.715.701 bytes), `sha256 = ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`
— **khớp** `x-linked-etag` của HF và khớp `checkpoint_sha256` mà ticket 06 đã ghi trong
`kaggle/smoke_test/cells/18-ticket06-eval-frame.py`. Tức là đúng file đã dùng cho mAP 0,298.

**Dữ liệu:** Kaggle dataset `sahangunasekara92/nuscenes-v1-0-full-keyframes` (như `kaggle/dataset_gate`).

- [x] Config A (clean) và B (spray) chỉ khác spray transform — `diff_paths` = `["arm","spray","train_pipeline"]`, không có `train_spec.*`; test `tests/test_ab_config.py`.
- [x] Các yếu tố training giống nhau được ghi lại — `spray/ab_config.py::TRAIN_SPEC` + `docs/ab-protocol.md`.
- [x] Memory/time probe chạy trên T4 — kernel `bevfusion-spray-probe` v1 `COMPLETE`, `PROBE_OK`; memory đo được, **s/step hoãn sang 11** (cần batch thật).
- [x] Freeze list được chốt: mở LiDAR encoder, fusion, BEV backbone/neck, head; đóng băng camera (user duyệt 2026-11-08).

## PM nghiệm thu 2026-11-08

**10-i — commit `fcaa4f9`.** `94 passed, 4 skipped` (trước: 64/4). Code: `spray/config_merge.py`,
`spray/ab_config.py`, `spray/freeze.py`, `spray/config/plume_default.yaml` + 4 file test (30 test mới).

- `diff_paths(A,B)` đúng 3 khoá: `arm`, `spray`, `train_pipeline`. Pipeline B chèn `PlumeTransform`
  sau `RandomFlip3D`, trước `PointsRangeFilter` — đúng vị trí đã chốt ở ticket 08/09.
- `plume_default.yaml` 21 field, **toàn bộ là field thật của `PlumeConfig`**, giá trị khớp code
  (`wfh 0.001`, `min_speed 40`, offset `50`, `ppm 17.0` σ `0.67` kẹp `[3,200]`, bán kính `0.30`,
  kẹp `(0.10,1.00)`, `squash 0.885`). Không có số bịa.
- Freeze theo **tên tham số**, không theo attribute — vendor là tree pin, đổi bản là attribute đổi.

**10-ii — commit `2ed78b3`, kernel `nguynhuy9669/bevfusion-spray-probe` v1 `COMPLETE`.**
Agent cạn turn (`EXIT=8`) trước bước commit; PM đọc 580 dòng `probe.py`, commit và push.

`PROBE_OK`:
- `ckpt_sha256 = ee0a3892…2122` khớp; 163.715.701 bytes.
- `ckpt_load missing=0 unexpected=0`; 582 key cả hai phía (khớp `582/582` của ticket 06).
- `n_total_params = 40.800.087`; `n_trainable_params = 9.080.686` (22,3%); frozen 31.719.401 (222 tensor).
- `frozen_roots = ["encoders.camera"]`; `frozen_names_not_camera = []`; `unmatched = []`.
  Tức là **chỉ** nhánh camera bị đóng băng, không có tên nào lọt lưới.
- `trainable_roots` = `decoder.backbone`, `decoder.neck`, `encoders.lidar`, `fuser.0/1`, `heads.object`.
- Memory (fp32, từ param count thật): weights **0,152 GB** + grad **0,034 GB** + AdamW **0,068 GB**
  = **0,254 GB**. ⇒ VRAM 16 GB **không** phải ràng buộc; activation mới là phần chưa biết (đo ở 11).

**Hai lỗi brief của PM do agent bắt được:**
1. `swint_v0p075/default.yaml` cho `model.fuser = None` — chỉ có camera + LiDAR encoder, **không có khối
   fusion**. File đúng là `swint_v0p075/convfuser.yaml` (`ConvFuser [80,256]→256`), chain 8 file config.
   Nếu build từ file sai, checkpoint sẽ missing toàn bộ `fuser.*` và PM dễ kết luận nhầm "checkpoint hỏng".
2. `TRAINABLE_PREFIXES` có `pts_voxel_encoder.` / `pts_middle_encoder.` / `pts_backbone.` / `pts_neck.`
   là tên kiểu mmdet3d cũ, **không tồn tại** trong model này (`trainable_prefixes_unused`). Không gây hại
   vì `unmatched = []`, nhưng danh sách nên rút gọn còn `encoders.lidar.` + `fuser.` + `decoder.` +
   `heads.` ở lần sửa tới.

**Còn thiếu, chuyển sang ticket 11:** giây/bước thật và VRAM đỉnh (cần forward + batch thật).
