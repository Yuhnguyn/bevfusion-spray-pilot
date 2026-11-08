# 10: Train/eval config A/B

**What to build:** Hai config chỉ khác nhau ở spray: cùng checkpoint, scene split, freeze list, optimizer, LR, seed, data order, batch size, và số update. Kèm memory/time probe trước khi train.

**Blocked by:** 02, 04, 09

**Status:** in-progress (10-i local, 10-ii probe T4)

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

- [ ] Config A (clean) và B (spray) chỉ khác spray transform.
- [ ] Các yếu tố training giống nhau được ghi lại.
- [ ] Memory/time probe chạy trên T4.
- [x] Freeze list được chốt: mở LiDAR encoder, fusion, BEV backbone/neck, head; đóng băng camera (user duyệt 2026-11-08).
