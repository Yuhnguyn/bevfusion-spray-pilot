# HANDOFF — Spray plume pilot (BEVFusion MIT)

Cập nhật: **2026-11-09 00:30** · nhánh `main` · HEAD `2bb93ea` · https://github.com/Yuhnguyn/bevfusion-spray-pilot
**Nguồn sự thật về tiến độ: `.scratch/spray-augmentation/STATUS.md`.** File này chỉ nói cách dựng lại máy
và bắt đầu lại công việc.

## Đọc gì khi mở session mới (theo thứ tự, đừng đọc thêm)

1. `HANDOFF.md` (file này) — 2 phút.
2. `.scratch/spray-augmentation/STATUS.md` — board + trạng thái thật, phần **"Dừng shift"** ở đầu.
3. Ticket đang làm trong `.scratch/spray-augmentation/issues/` — **chỉ file của ticket đó**.
4. `docs/PROJECT.md` §5 nếu cần khác biệt so với paper + căn cứ.

Không đọc lại toàn repo. Không đọc log cũ trong `/tmp` trừ khi ticket yêu cầu.

## Đang treo ở đâu

**Kernel `nguynhuy9669/bevfusion-spray-train` v1 — `QUEUED` lúc 00:22 ngày 2026-11-09.**
Dataset code **v10** (158 file) đã có `kaggle/train/smoke.py`. Đây là smoke run của ticket **11-b**:
cài `nuscenes-devkit==1.1.11` vào venv → dựng 4.000 sample → dataloader → 5 bước arm A + 15 bước arm B.

```bash
kaggle kernels status nguynhuy9669/bevfusion-spray-train
rm -rf /tmp/ksmoke && mkdir -p /tmp/ksmoke
kaggle kernels output nguynhuy9669/bevfusion-spray-train -p /tmp/ksmoke
grep -E "SMOKE_DEVKIT_OK|MINI_SPLIT_OK|SMOKE_STEP|SMOKE_OK|SMOKE_FAILED|MINI_SPLIT_FAILED" \
  /tmp/ksmoke/bevfusion-spray-train.log
```

Cần 2 số: `s_per_step` và `peak_gb`. Có 2 số đó mới chốt được thời gian train thật (ticket 11-c).

## Tiến độ

**Board: 26 ticket, 24 done.** Còn `11` (mini A/B run) và `13` (gate review).

| mốc | trạng thái |
|---|---|
| Generator plume khớp code Linnhoff (21–23) | xong — `K = 2,51`, 8 cụm @80 km/h, trần bán kính 1,0 m |
| Visualize (20) | xong — `docs/figs/plume/` |
| E2E trên Kaggle (09) | xong — `68 passed, 0 skipped`, `E2E_OK` |
| Config A/B + freeze (10) | xong — `fcaa4f9`; probe `PROBE_OK` `2ed78b3` |
| Mini split 4.000 sample (11-a) | xong — `0125e13`, `105 passed, 4 skipped` |
| Smoke kernel đo s/step (11-b) | code xong `fb214ff`, kernel **QUEUED** |

## Test

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/    # 105 passed, 4 skipped
```

4 skip = 4 test e2e trong `tests/test_pipeline_e2e.py` (cần `mmcv`/`mmdet3d`); chạy thật trên kernel.
Chạy script trong repo phải có `PYTHONPATH=.`.

## Máy này thiếu gì

- **Không có** `mmcv`/`mmdet`/`mmdet3d`, **không có** `nuscenes-devkit` ⇒ không train/eval local.
- **Không có** nuScenes local (chỉ Kaggle: `sahangunasekara92/nuscenes-v1-0-full-keyframes`).
- `mit/bevfusion` là tree pin `da93b27`, **gitignored** — có local, không lên GitHub.
- Có `data/SemanticSprayDataset` 16 GB (108 sequence) — chỉ dùng đo thống kê.

## Kaggle

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py   # đẩy code lên dataset
kaggle kernels push -p kaggle/train                                          # TASK trong main.py
kaggle kernels status nguynhuy9669/bevfusion-spray-train
```

- Dataset code: `nguynhuy9669/bevfusion-spray-pilot-code` **private**.
- Kernel: `nguynhuy9669/bevfusion-spray-train` (GPU T4 **1 con**, `enable_gpu: true`, không `machine_shape`).
- Queue 20–60 phút là bình thường. `QUEUED` lâu **không phải** hết quota (hết quota sẽ ra `ERROR` ngay).
- Đổi code xong phải **sync rồi mới push**, nếu không kernel chạy bản cũ.

## Ngân sách train đã chốt

`max_iters = 2000`, `batch_size = 2`, `lr = 1e-4`, `weight_decay = 0.01`, AdamW, `warmup 100`,
`grad_clip 5.0`, `seed = 0`. Freeze: chỉ camera; mở `encoders.lidar`, `fuser`, `decoder`, `heads`.

VRAM không phải rủi ro (param state 0,254 GB / 16 GB). Nếu vẫn thiếu, thứ tự xử lý:
**gradient accumulation → batch 1 + tăng số bước → DDP**.

## Cách làm việc (giữ nguyên, đừng đổi)

- **PM không tự code.** Việc thi công giao CommandCode: brief trong `~/.hermes/drafts/spray-pilot/`,
  chạy `commandcode -t -p "$(cat dispatch-XX.md)" --yolo --max-turns N`, log `/tmp/tXX.log`.
- **Một agent tại một thời điểm** — cùng worktree, `git add -A` của agent này nuốt file agent kia.
- Mỗi ticket: brief → chạy → **PM tự verify** (commit, `git status`, pytest, grep log) → ghi nghiệm thu
  vào ticket + `STATUS.md` → commit. Không tin báo cáo của agent.
- `EXIT=8` = cạn `--max-turns`, **không** có nghĩa là fail: kiểm `git log`/`git status` trước khi kết luận.
- Điều kiện đạt của việc chạy trên kernel: phải thấy **số test kỳ vọng** và **không có `skipped`**, không
  chỉ nhìn `E2E_OK`.

## Bẫy đã gặp (đừng lặp lại)

1. **Đọc tên file config rồi suy ra nội dung** — sai 2 lần: `point_cloud_range` ±54 (thật ±51.2), và
   `swint_v0p075/default.yaml` có `fuser = None` (file đúng: `convfuser.yaml`). Luôn mở file.
2. **Hardcode `±54`** — đó là model config; dataset dùng `±51.2`.
3. **Tin `E2E_OK` một mình** — đã có lần xanh giả vì 4 test bị skip.
4. **`timeout` không tồn tại** trên shell macOS.
5. **CommandCode stream đứt** (`TransportError`) ở việc dài ⇒ chia việc ngắn, đừng resume `-r`.
6. **`wfh` đơn vị mét** (`0,001`), không phải mm.
7. **Resume `-r`** khi CLI báo `No session ... found` ⇒ chia việc khác, đừng cố.

## Nơi chứa

| thứ | đường dẫn |
|---|---|
| Board + trạng thái | `.scratch/spray-augmentation/STATUS.md` |
| Ticket | `.scratch/spray-augmentation/issues/*.md` |
| Brief giao việc | `~/.hermes/drafts/spray-pilot/dispatch-*.md` |
| Quyết định + khác biệt paper | `docs/PROJECT.md` §5, `docs/adr/` |
| Kanban HTML | `docs/kanban.html` (sinh bằng `scripts/build_kanban.py`) |
| Ảnh/clip | `docs/figs/plume/` |
| Provenance plume | `docs/plume-model-provenance.md` |
| Log kernel | `/tmp/ksmoke/`, `/tmp/kprobe/`, `/tmp/k9run*/` |