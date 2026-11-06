# Smoke-test evidence (ticket 02 + 04)

Nguồn: kernel `nguynhuy9669/bevfusion-smoke-test`, **version v19** (2026-11-05),
`TICKET04_OK`. Đây là bản sao các JSON nhỏ để bằng chứng nằm trong git; file lớn
(`nuscenes_infos_*.pkl`, log) không commit.

| File | Chứng minh |
|---|---|
| `report.json` | Ticket 02: 6/6 tiêu chí; checkpoint 582/582, forward finite, depth 1 kênh |
| `checkpoint.json` | Checkpoint fused: sha256 `ee0a3892…2122`, size 163,715,701 B |
| `infos.json` | Ticket 04: train 120 / val 120 infos, `max_sweeps=0` |
| `dataset_sample.json` | Ticket 04: load 1 sample, 6 camera, 0 sweep, không thiếu ảnh; dropped map transforms |
| `cfg_checks.json` | Config invariants (image size, voxel, vtransform, fuser) |
| `cuda_toolchain.json` | Build toolchain: CUDA 11.8, gcc-11, không bypass guard |

Lấy lại toàn bộ output (gồm infos pkl + log):

```bash
kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k7
```

Không nằm trong git: `~/.kaggle/kaggle.json` (credentials), dataset nuScenes
(public Kaggle dataset), checkpoint (URL + sha trong `mit/PIN.md`), và các file
output lớn.
