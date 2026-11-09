# Ticket 11-b — smoke kernel: mini infos + dataloader + 20 bước, đo s/step và VRAM đỉnh

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `0125e13` · **1 lần push kernel**.
Test local phải giữ **105 passed, 4 skipped**.

Mục tiêu duy nhất: biết **một bước train tốn bao nhiêu giây** và **VRAM đỉnh**, đồng thời chứng minh
harness train chạy được end-to-end. **Không** train thật, **không** eval.

## Bối cảnh đã có (đừng làm lại)

- `kaggle/train/main.py` + `probe.py` đã boot được: `extract_code() → clone_pin() → install_env() →
  choose_toolchain() → build_ops() → verify_stack()`, rồi chạy file `.py` trong venv qua `e2e.stream([PY, ...])`.
  `probe.py` cũng đã có `load_config()` (merge chain config vendor) và `register_mmdet3d_pipelines()` — **import lại**,
  không chép.
- `spray/ab_config.py::build_cfg(arm)` cho pipeline A/B; `spray/freeze.py::apply_freeze(model)`;
  `scripts/make_mini_split.py` dựng infos 4.000 sample.

## Việc 1 — devkit vào venv

Venv Python 3.8 hiện **không có** `nuscenes-devkit` (đó là lý do `tests/test_pipeline_e2e.py` phải stub
`mmdet3d.datasets`). `scripts/make_mini_split.py` cần devkit thật.

Trong kernel, trước khi chạy smoke: `pip install nuscenes-devkit==1.1.11` bằng `e2e.stream([str(PY), "-m", "pip",
"install", "nuscenes-devkit==1.1.11"])`, rồi verify `from nuscenes.utils import splits; len(splits.val)==150`
và `from nuscenes.nuscenes import NuScenes`. Nếu pin không cài được, thử `nuscenes-devkit==1.1.10`, ghi lại
version đã dùng. In `SMOKE_DEVKIT_OK version=<x> val=150`.

## Việc 2 — `kaggle/train/smoke.py` (chạy trong venv)

1. `make_mini_split.py --dataroot <đường dẫn nuScenes mount> --out /kaggle/working/mini_train_4000.pkl
   --n 4000 --seed 0 --max-sweeps 10`, in nguyên dòng `MINI_SPLIT_OK`. Nếu `MINI_SPLIT_FAILED` ⇒ dừng,
   in 20 dòng lỗi cuối.
2. Dựng dataset + dataloader: dùng `load_config("configs/nuscenes/default.yaml")` của `probe.py` để lấy
   `data.train.dataset` (pipeline, classes, `ann_file` thay bằng file mini, `data_root` = mount,
   `modality` như config gốc), rồi `mmdet3d.datasets.build_dataloader(dataset, samples_per_gpu=2,
   workers_per_gpu=4, dist=False, shuffle=False, seed=0)`.
   **Ghi đè pipeline**: dùng `build_cfg(arm)["train_pipeline"]` của `spray/ab_config.py` cho arm đang test,
   để đúng code sẽ dùng khi train thật.
3. Dựng model như `probe.py`: `choose_model_config()` → `build()` → `load_weights()` → `apply_freeze()`.
   Không bịa lại.
4. Train loop tối giản, `model.train()`, optimizer `torch.optim.AdamW(model.parameters(),
   lr=1e-4, weight_decay=0.01)` **chỉ truyền tham số `requires_grad`**:
   - arm **A**: 5 bước; arm **B** (spray bật): 15 bước. Cùng `seed=0`.
   - mỗi bước: `losses = model(return_loss=True, **data)`, `loss = sum(losses.values())`,
     `loss.backward()`, `clip_grad_norm_(5.0)`, `opt.step()`, `opt.zero_grad()`, `torch.cuda.synchronize()`.
   - đo thời gian từng bước; **bỏ 3 bước đầu** (warmup) khi tính trung bình.
   - `torch.cuda.reset_peak_memory_stats()` trước bước đầu; đọc `torch.cuda.max_memory_allocated()` sau bước cuối.
   - assert `torch.isfinite(loss)`; nếu không, in `SMOKE_FAILED non_finite_step=<i>` và dừng.
   - in mỗi bước một dòng `SMOKE_STEP arm=<A|B> i=<i> loss=<f> s=<f>`.
5. Ghi `/kaggle/working/smoke.json`: `s_per_step_A`, `s_per_step_B`, `peak_gb`, `loss_first`,
   `loss_last`, `n_points_after_pipeline` (lấy từ batch, trung bình 2 frame), `spray_stats` nếu pipeline B
   trả về, `devkit_version`.
6. In dòng cuối: `SMOKE_OK s_per_step=<f> peak_gb=<f> steps=<n>`

## Việc 3 — `kaggle/train/kernel-metadata.json` sửa lại

```json
"id": "nguynhuy9669/bevfusion-spray-train",
"title": "BEVFusion spray train",
...
"dataset_sources": [
  "nguynhuy9669/bevfusion-spray-pilot-code",
  "sahangunasekara92/nuscenes-v1-0-full-keyframes"
]
```

`main.py` giữ nguyên cơ chế boot, thêm hằng `TASK = "smoke"`, và chạy `kaggle/train/smoke.py` thay vì `probe.py`.

## Việc 4 — chạy

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/     # 105 passed, 4 skipped
git add -A && git commit -m "feat(train): smoke kernel for mini infos, dataloader and step timing"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/train
```

Sau khi push: **dừng, không chờ**. Kernel có thể xếp hàng 30–60 phút. PM tự theo dõi và tự tải log.

## Điều kiện ĐẠT

Log có đủ: `SMOKE_DEVKIT_OK`, `MINI_SPLIT_OK n=4000`, `SMOKE_STEP` cho cả arm A và B với `loss` hữu hạn,
và `SMOKE_OK`. `smoke.json` có `s_per_step_A/B` và `peak_gb`.

## Không được làm

- Không sửa `spray/**`, `tests/**`, `mit/**`, `scripts/make_mini_split.py`.
- Không hạ `n` xuống dưới 4000 để "cho nhanh" (số bước cần đúng).
- Không đổi `max_iters`/`lr`/freeze.
- Nếu loss ra `nan` hoặc model báo thiếu key khi forward: **dừng**, in traceback đầy đủ + 3 dòng cuối của
  batch (key, shape, dtype). Không tự sửa kiến trúc hay bỏ qua lỗi.

## Báo cáo

- `git log --oneline -1`, `git status --porcelain`
- 3 dòng `SMOKE_DEVKIT_OK`, `MINI_SPLIT_OK`, `SMOKE_OK`
- 5 dòng `SMOKE_STEP` đầu và 3 dòng cuối
- nếu fail: 30 dòng log cuối + `kaggle kernels status`