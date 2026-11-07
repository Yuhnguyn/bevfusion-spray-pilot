# Smoke-test evidence (tickets 02, 04, 06, 07)

Nguồn: kernel `nguynhuy9669/bevfusion-smoke-test`, các lần chạy 2026-11-05 (ticket 02/04)
và 2026-11-07 (ticket 06/07). Đây là bản sao các JSON nhỏ để bằng chứng nằm trong git;
file lớn (`nuscenes_infos_*.pkl`, log) không commit.

| File | Chứng minh |
|---|---|
| `report.json` | Ticket 02: 6/6 tiêu chí; checkpoint 582/582, forward finite, depth 1 kênh |
| `checkpoint.json` | Checkpoint fused: sha256 `ee0a3892…2122`, size 163,715,701 B |
| `infos.json` | Ticket 04: train 120 / val 120 infos, `max_sweeps=0` |
| `dataset_sample.json` | Ticket 04: load 1 sample, 6 camera, 0 sweep, không thiếu ảnh |
| `cfg_checks.json` | Config invariants (image size, voxel, vtransform, fuser) |
| `cuda_toolchain.json` | Build toolchain: CUDA 11.8, gcc-11, không bypass guard |
| `eval_frame.json` | Ticket 06: model chạy 2 frame thật (200 pred/frame) |
| `real_frame_detections.json` + `real_frame_eval_info.json` | Ticket 06: raw prediction + GT của frame primary |
| `real_frame_range_detections.json` + `real_frame_range_info.json` | Ticket 06: frame secondary, 2 GT ngoài 54 m |
| `mit_eval_result.json` | Evaluator local: mAP 0.298, P 0.512, R 0.524 |
| `ticket07_infos.json` | Ticket 07: scene-0796, 40 val infos |
| `ticket07_transform.json` | Ticket 07: +127 điểm, 12/12 check pass |

Lấy lại toàn bộ output (gồm infos pkl + log):

```bash
kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k8out
```

Code ticket 07 nằm ở `spray/plume_transform.py` và cell 19 của notebook; ticket 06 dùng
`proxy_eval/mit_adapter.py`.

Không nằm trong git: `~/.kaggle/kaggle.json` (credentials), dataset nuScenes (public Kaggle
dataset), checkpoint (URL + sha trong `mit/PIN.md`), và các file output lớn.
