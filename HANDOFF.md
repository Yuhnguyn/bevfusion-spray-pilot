# HANDOFF — Spray plume pilot (BEVFusion MIT)

Cập nhật: **2026-11-07 15:20** · nhánh `main` · Repo: https://github.com/Yuhnguyn/bevfusion-spray-pilot
**Nguồn sự thật về tiến độ: `.scratch/spray-augmentation/STATUS.md`.** File này chỉ nói cách dựng lại máy.

## TL;DR

- Generator plume **đã khớp code tham chiếu Linnhoff** (ticket 21–22): kích hoạt 40 km/h + `wfh > 0`,
  số cụm `(0,2·wfh + 0,1)·(v−50) × K` với `K = 2,51`, `T ≈ 0,20 s`, σ = 1,1. 80 km/h → **8 cụm/frame**
  (đo thật SemanticSpray: 17,06; trước ticket 22: 0,73).
- **Test: 56 passed** (`python3 -m pytest -q tests/`), 8 file.
- Môi trường Kaggle đã giải xong: venv Python 3.8.20 + torch 1.10.1+cu113 + `mmcv-full 1.4.0` + 12 CUDA
  extension; kernel `bevfusion-e2e` **COMPLETE 516 s / 49 passed**.
- Việc tiếp theo: **23** (3 chỉnh nhỏ) → **09** (e2e trên Kaggle) → **10 → 11 → 13**; **14** (B0) và
  **24** (kanban sinh từ nguồn thật) chạy song song.

## Trạng thái ticket

| Ticket | Trạng thái | Ghi chú |
|---|---|---|
| 01 Working copy + pin | done | `da93b27`, 4/4 |
| 02 Smoke test | done | ALL_PASS: 582/582 key, forward finite, depth [6,1,256,704] |
| 02b Fix môi trường | done | numba/torchvision/CUDA/gcc/numba.errors |
| 03 Velocity contract | done | `docs/velocity-contract.md` |
| 04 Dataset gate | done | infos 120/120, load 1 sample |
| 05 Evaluator core | done | `proxy_eval/matcher.py`, 8 test |
| 06 Evaluator adapter | done | mAP 0.298 trên frame thật |
| 07 Pipeline transform | done | scene-0796, 12/12 check |
| 08 Model routing | **done** `16517f1` | subclass trong `spray/`, param 16 → 16 |
| 09 Pipeline e2e | **ready** | chặn cũ (19) đã gỡ; cần 1 run Kaggle GPU |
| 10 Train/eval config | blocked | chờ 09 |
| 11 Mini A/B | blocked | chờ 10 |
| 12 SemanticSpray stats | done | `docs/semantic-spray-stats.md` |
| 13 Gate review | blocked | chờ 11 |
| 14 Denoise B0 | ready | chạy song song được |
| 15 Plume provenance | done `bc0da86`+`d1bf9bf` | `docs/plume-model-provenance.md` |
| 16 Plume geometry | done `08f6715` | 17,06 cụm/frame; 30/20/14/10/10 điểm/cụm |
| 17 Sửa generator theo số | done `5d7c478` | count theo cự ly; bẹp `S = 0,885` |
| 18 Eligibility nuScenes | done | eval set 196 frame / 16 scene |
| 19 Kaggle code sync | done `feb0a9e` | dataset private v3, kernel `bevfusion-e2e` |
| 20 Visualize plume | done `6143875` | `docs/figs/plume/index.html` |
| 21 Port cơ chế tham chiếu | done `a4fdf24` | 40 km/h, offset 50, `T`, σ 1,1 |
| 22 Sửa lỗi tính hai lần | done `75d210c` | `K = 2,51`, bỏ dropout |
| 23 Trần bán kính + tên cột 5 | ready | nhỏ, không đổi hành vi |
| 24 Kanban từ nguồn thật | ready | script đang hard-code ⇒ board lệch |

## Preconditions (spec v1.5) — 1–6 PASS

1. Version `da93b27` — PASS
2. Smoke test checkpoint + forward — PASS
3. Checkpoint fused + hash — PASS (`ee0a3892…2122`)
4. Dataset gate (infos + load sample) — PASS
5. Evaluator trên frame MIT thật — PASS (mAP 0.298; ticket 06)
6. Velocity contract — PASS

Spec: `.scratch/spray-augmentation/spec.md`.

## Kaggle

Hai kernel, đừng lẫn:

| Kernel | Dùng cho | Trạng thái |
|---|---|---|
| `nguynhuy9669/bevfusion-smoke-test` | ticket 02–07 (env + dataset + transform), ~13 phút/run | v19 COMPLETE |
| `nguynhuy9669/bevfusion-e2e` | ticket 09+ (code repo qua dataset private), **516 s/run** | COMPLETE, 49 passed |

- Code lên Kaggle bằng **dataset private** `nguynhuy9669/bevfusion-spray-pilot-code` (2.092 KB tracked,
  v3 ready) — không push GitHub vì repo private 404 và `data/` 16 GB.
- Đồng bộ + kiểm tra: `python3 scripts/kaggle_code_sync.py --dry-run` → in `KAGGLE_CODE_SYNC_OK`.
- Lấy log: `kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k19log --file-pattern ".*\.log$"`.
  Log tốt phải có `MIT_PIN_OK da93b27`, `PINNED_WHEELS_OK`, `OPS_OK`, `49 passed`, `E2E_OK`.
  `ModuleNotFoundError: mmdet3d` ở ~129 s là **probe cố ý**, không phải lỗi.
- Evidence JSON nhỏ đã commit ở `kaggle/smoke_test/evidence/`.

## Phát hiện quan trọng

**Eligibility (ticket 18, `docs/nuscenes-eligibility.md`):** val split có **196 frame / 16 scene** với box
vehicle ≥50 km/h phía trước trong 50 m. Trên toàn trainval (850 scene / 34.149 keyframe) tỷ lệ frame có
≥50 km/h chỉ **2,0%** (697 frame) — con số 34.029 frame từng bị dán nhãn sai là "val", thực ra là toàn bộ
trainval. Val có **0** scene highway ⇒ không dùng highway.

**Hình học plume thật (ticket 16):** 873.457 điểm noise / 35.305 cụm ⇒ **17,06 cụm/frame**; điểm/cụm
**30/20/14/10/10** theo bucket 0–5/5–10/10–20/20–30/30–50 m ⇒ mật độ **giảm theo cự ly**; `r_range/r_extent`
median **1,266** ⇒ không phải vỏ cầu mỏng. Đã sửa generator ở ticket 17.

## Môi trường & bẫy đã gặp

- Pin: `da93b27`, `torch==1.10.1+cu113`, `torchvision==0.11.2+cu113`, `mmcv-full==1.4.0`, `mmdet==2.20.0`,
  `numpy==1.22.4`, `numba==0.58.1`.
- Kaggle system Python 3.13 không cài được stack; venv Python 3.8 tại `/root/bevfusion_smoke/env`.
- Build ops: CUDA 11.8 + `gcc-11` + đủ `libcusparse/libcublas/libcurand/libcusolver-dev-11-8`.
- `numba 0.58` bỏ `numba.errors`; dataset import `NumbaPerformanceWarning` → cần shim.
- Converter `da93b27` ghi `camera_intrinsics`, dataset đọc `cam_intrinsic` → thêm alias.
- Mirror thiếu `maps/expansion/*.json` → drop `LoadBEVSegmentation` + `Collect3D.gt_masks_bev` khi `use_map=false`.
- **`points_clean` không đi qua `DefaultFormatBundle3D`** (chỉ wrap `points`/`radar`) → ticket 08 phải thêm
  plumbing collect/format, đã làm trong `spray/pipeline.py`.
- Runtime thật là `mit/bevfusion` @ `da93b27` (**gitignored**); `third_party/bevfusion/` là **bản chết**.
- **`water_film_height` tính bằng MÉT** ⇒ `T ≈ 0,20 s`, `K ≈ 2,51` ở mọi tốc độ. Đọc `1 mm` thành `1,0`
  sẽ sai 3,6×.
- macOS không `timeout`; matplotlib base env hỏng (numpy 2.4.3) → viz dùng `~/.venvs/viz`.
- Shell nào cũng in crash report của conda plugin — **không phải lỗi agent**, lọc khi đọc log.

## Chạy tiếp ở máy khác

```bash
git pull
python3 -m pip install numpy pytest              # test local chỉ cần hai gói này
CONDA_NO_PLUGINS=true python3 -m pytest -q tests/ # phải ra 56 passed
```

Cần `kaggle` CLI đã đăng nhập nếu muốn chạy kernel. Artifact knowledge base (private, cùng account):
`https://artifacts.commandcode.ai/hk7d56v2pqp5q76x` (v2, publish 2026-11-07, hết hạn 14-11).

### Dựng lại working copy MIT (không nằm trong git)

`mit/bevfusion/`, `third_party/` và `data/` bị `.gitignore`:

```bash
git clone https://github.com/mit-han-lab/bevfusion.git mit/bevfusion
git -C mit/bevfusion checkout da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea
git -C mit/bevfusion rev-parse --short HEAD   # phải in da93b27
```

### Cái gì ở ngoài git (và lấy lại thế nào)

| Thứ | Ở đâu | Cần làm gì |
|---|---|---|
| Kaggle credentials | `~/.kaggle/kaggle.json` | Đăng nhập lại; **không commit** |
| Dataset code | `nguynhuy9669/bevfusion-spray-pilot-code` (private v3) | `python3 scripts/kaggle_code_sync.py` |
| Kernel e2e | `nguynhuy9669/bevfusion-e2e` | `kaggle kernels push -p kaggle/e2e` |
| Dataset nuScenes | Kaggle dataset public | Tự attach khi push |
| Dataset SemanticSpray | `data/SemanticSprayDataset` ~16 GB local | Không cần cho test; chỉ cho ticket 16/20 |
| Checkpoint fused | Dropbox mirror | URL + sha256 trong `mit/PIN.md`; kernel tự tải |
| Knowledge base artifact | artifacts.commandcode.ai | Link private; bản local `docs/knowledge-base.html` |

## Prompt dán vào CommandCode (máy mới)

```text
Bạn tiếp quản repo bevfusion-spray-pilot. Đọc STATUS.md ở
.scratch/spray-augmentation/STATUS.md (nguồn sự thật về thứ tự), rồi ticket
được giao trong .scratch/spray-augmentation/issues/.

Ràng buộc:
- Không đổi pin: da93b27, torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0,
  numpy 1.22.4. Không sửa mit/bevfusion hay third_party/.
- Chỉ tick checkbox khi có bằng chứng thật; ghi số liệu vào ticket.
- Test local: CONDA_NO_PLUGINS=true python3 -m pytest -q tests/ (hiện 56 passed).
- Không tự đổi tham số plume (PlumeConfig) để khớp số kỳ vọng; muốn đổi thì
  dừng, báo PM kèm số.

Báo cáo ngắn: đã làm gì, test nào pass, blocker, commit.
```

## Tham chiếu

- `.scratch/spray-augmentation/STATUS.md` — board + quyết định đã chốt
- `.scratch/spray-augmentation/issues/` — 24 ticket
- `docs/PROJECT.md` — sổ tay kỹ thuật; `docs/knowledge-base.html` — bản đọc
- `docs/plume-model-provenance.md` — nguồn từng tham số `[ĐO]/[PAPER]/[CODE]/[CHỌN]`
- `docs/plume-geometry-vs-real.md`, `docs/nuscenes-eligibility.md`, `docs/velocity-contract.md`
- `docs/figs/plume/index.html` — ảnh + clip plume
- `mit/PIN.md` — commit pin + checkpoint mirror/sha256
- `docs/adr/0001-mit-bevfusion-pin.md`, `0002-plume-only-first.md`, `0003-semantic-spray-eval-only.md`