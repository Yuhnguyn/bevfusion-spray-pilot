# HANDOFF — Spray plume pilot (BEVFusion MIT)

Cập nhật: **2026-11-05** · nhánh `main` · HEAD `a0407a7`
Repo: https://github.com/Yuhnguyn/bevfusion-spray-pilot

## TL;DR

- Preconditions **1, 2, 3, 4, 6 đã PASS**. Chỉ còn **precondition 5 = ticket 06 (evaluator adapter)**.
- Ticket 04 vừa xong trên Kaggle **v19** (`TICKET04_OK`): infos train/val **120/120**, load được 1 sample qua pipeline.
- Việc tiếp theo: **implement ticket 06** → flip spec `ready-for-agent` → 07 → 08 → 09 → 10 → 11.
- **Quyết định đang chờ:** ngưỡng plume 50 km/h chỉ phủ **2.0%** frame val (697/34,029); 30 km/h phủ **13.8%** (4,690). Chốt trước ticket 07/10/11.

## Trạng thái ticket

| Ticket | Trạng thái | Ghi chú |
|---|---|---|
| 01 Working copy + pin | done | `da93b27`, 4/4 |
| 02 Smoke test | done | ALL_PASS: 582/582 key, forward finite, depth [6,1,256,704] |
| 02b Fix môi trường | done | numba/torchvision/CUDA/gcc/numba.errors |
| 03 Velocity contract | done | `docs/velocity-contract.md` + số đo 34k frame |
| 04 Dataset gate | done | infos 120/120, load 1 sample (v19) |
| 05 Evaluator core | done | pytest synthetic |
| **06 Evaluator adapter** | **ready — làm tiếp** | precondition 5 |
| 07 Pipeline transform | ready | ticket 04 đã xong |
| 08 Model routing | blocked | chờ 07 |
| 09 Pipeline e2e | blocked | chờ 07, 08 |
| 10 Train/eval config | blocked | chờ 02, 04, 09 |
| 11 Mini A/B | blocked | chờ 06, 10 |
| 12 SemanticSpray stats | done | so sánh cluster |
| 13 Gate review | blocked | chờ 11 |
| 14 Denoise B0 | ready | chờ không còn — 02,05 xong |
| 15 Plume provenance | ready | việc nhỏ, docstring |

Chi tiết từng ticket: `.scratch/spray-augmentation/issues/`.

## Preconditions (spec v1.5)

1. Version `da93b27` — PASS
2. Smoke test checkpoint + forward — PASS
3. Checkpoint fused + hash — PASS (`ee0a3892…2122`)
4. Dataset gate (infos + load sample) — PASS (v19)
5. Evaluator trên frame MIT thật — **PENDING = ticket 06**
6. Velocity contract — PASS

Spec: `.scratch/spray-augmentation/spec.md` (Status: `needs-triage`; chỉ flip khi 5 pass).

## Kaggle

- Kernel: https://www.kaggle.com/code/nguynhuy9669/bevfusion-smoke-test
- Version mới nhất: **v19 COMPLETE**, log có `TICKET04_OK`.
- Lấy output:
  ```bash
  kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k7
  ```
- Artifacts quan trọng trong `/tmp/k7/smoke_test/artifacts/`:
  - `report.json` — 6/6 tiêu chí ticket 02
  - `infos.json` — train 120 / val 120, 109 s
  - `dataset_sample.json` — load index 0, 6 camera, 0 sweep, không thiếu ảnh
  - `checkpoint.json` — 582/582, sha `ee0a3892…2122`
- Notebook: `kaggle/smoke_test/bevfusion-smoke-test.ipynb` (cell 17 = ticket 04b); bản tách từng bước ở `kaggle/smoke_test/cells/`.
- Push lại kernel: `kaggle kernels push -p kaggle/smoke_test` (~13 phút). Không đổi pin.

## Phát hiện quan trọng (2026-11-05)

Quét full val (34,029 frame, 1,160,875 box):

| Ngưỡng | Box vehicle | Front ≤30 m | Frame có ≥1 | Tỷ lệ |
|---|---|---|---|---|
| ≥30 km/h | 44,537 | 7,152 | 4,690 | 13.8% |
| ≥40 km/h | 18,552 | 2,927 | 1,924 | 5.7% |
| ≥50 km/h | 5,514 | 952 | **697** | **2.0%** |
| ≥60 km/h | 950 | 193 | 173 | 0.5% |

Ba scene subset đầu có **0** frame ≥50 km/h (max 43.5 km/h). Nếu giữ 50 km/h, plume chỉ xuất hiện ~2% frame → rất thưa cho train/eval. Chọn: **hạ 30 km/h** hoặc **dùng scene highway**. Chưa đổi code/ngưỡng.

## Môi trường & bẫy đã gặp

- Pin: `da93b27`, `torch==1.10.1+cu113`, `torchvision==0.11.2+cu113`, `mmcv-full==1.4.0`, `mmdet==2.20.0`, `numpy==1.22.4`, `numba==0.58.1`.
- Kaggle system Python 3.13 không cài được stack; venv Python 3.8 tại `/root/bevfusion_smoke/env` (mất khi hết session).
- Toolchain build ops: CUDA 11.8 + `gcc-11` + đủ `libcusparse/libcublas/libcurand/libcusolver-dev-11-8`; `cuda_guard_bypassed` phải là `false`.
- `numba 0.58` bỏ `numba.errors`; pipeline dataset import `NumbaPerformanceWarning` → đã có shim trong cell 17. Không sửa repo.
- Converter `da93b27` ghi `camera_intrinsics`, dataset đọc `cam_intrinsic` → phải thêm alias (cell 17).
- Mirror thiếu `maps/expansion/*.json` → drop `LoadBEVSegmentation` + `Collect3D.gt_masks_bev` khi `use_map=false`.
- macOS không có `timeout`; apt cài từng gói một (sai tên → exit 100, mất nvcc).
- **Ticket 10–11:** load config bằng `Config.fromfile(..., _base_)`, **không** round-trip JSON; trainer/hook/optimizer dựa vào semantics `mmcv.Config`.

## Chạy tiếp ở máy khác

```bash
git pull
python3 -m pip install numpy pytest   # test local chỉ cần hai gói này
python3 -m pytest -q tests/
python3 scripts/build_kanban.py       # rồi publish lại artifact
```

Cần `kaggle` CLI đã đăng nhập nếu muốn push/pull kernel. Artifact Kanban (private, cùng account):
https://artifacts.commandcode.ai/ee7xfw4tlt45qh96

### Dựng lại working copy MIT (không nằm trong git)

`mit/bevfusion/`, `third_party/` và `data/` bị `.gitignore`. Ticket 06 không cần dataset;
chỉ cần clone MIT đúng pin để đọc code/format:

```bash
git clone https://github.com/mit-han-lab/bevfusion.git mit/bevfusion
git -C mit/bevfusion checkout da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea
git -C mit/bevfusion rev-parse --short HEAD   # phải in da93b27
```

Dataset nuScenes và SemanticSpray nằm trên Kaggle/ổ ngoài, không commit vào repo.

## Prompt dán vào CommandCode (máy mới)

```text
Bạn tiếp quản repo bevfusion-spray-pilot. Đọc HANDOFF.md ở root, spec
.scratch/spray-augmentation/spec.md, và ticket 06
.scratch/spray-augmentation/issues/06-evaluator-adapter.md (cùng ticket 05 và
mục Interface contract trong spec).

Nhiệm vụ: implement ticket 06 — adapter đưa output thật của BEVFusion MIT vào
evaluator core, chấm một frame thật, có test kiểm tra tay được. Đây là
precondition 5 cuối cùng. Dùng frame thật đã load được ở ticket 04 (v19) và
evaluator core đã có ở ticket 05.

Ràng buộc:
- Không đổi pin: da93b27, torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0,
  numpy 1.22.4. Không sửa third_party/.
- Chỉ tick checkbox khi có bằng chứng thật; ghi số liệu vào ticket.
- Không push Kaggle nếu chưa cần; ưu tiên test local.

Sau khi ticket 06 pass: flip Status của spec sang ready-for-agent, cập nhật
README nếu cần, chạy python3 scripts/build_kanban.py và publish lại artifact,
rồi mới sang ticket 07.

Trước ticket 07/10/11: hỏi user chốt ngưỡng plume — 50 km/h (2.0% frame val)
hay 30 km/h (13.8%), hoặc chọn scene highway.

Báo cáo ngắn: đã làm gì, test nào pass, blocker, commit.
```

## Tham chiếu (không lặp nội dung)

- `.scratch/spray-augmentation/spec.md` — spec v1.5, preconditions, interface contract
- `.scratch/spray-augmentation/issues/` — 16 ticket
- `docs/velocity-contract.md` — velocity frame + số đo eligible
- `docs/kanban.html` + `scripts/build_kanban.py` — board tự sinh
- `kaggle/smoke_test/` — notebook, kernel metadata, per-step cells
- `mit/PIN.md` — commit pin + checkpoint mirror/sha256
- `docs/adr/0001..0003` — các quyết định đã chốt
