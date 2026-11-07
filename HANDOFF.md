# HANDOFF — Spray plume pilot (BEVFusion MIT)

Cập nhật: **2026-11-05** · nhánh `main` · HEAD `a0407a7`
Repo: https://github.com/Yuhnguyn/bevfusion-spray-pilot

## TL;DR

- **Preconditions 1–6 PASS**; spec đã flip **`ready-for-agent`**.
- Ticket 06 (adapter evaluator) xong: frame thật **mAP 0.298**, P 0.512 / R 0.524; threshold 0.05, range 54 m.
- Ticket 07 (`PlumeTransform`) xong: scene-0796, +127 điểm, 12/12 check pass.
- Việc tiếp theo: **ticket 08 (model routing)** → 09 → 10 → 11 → 13; 14/15/16 chạy song song được.
- **Quyết định đang chờ:** ngưỡng plume 50 km/h chỉ phủ **2.0%** frame val (697/34,029); 30 km/h phủ **13.8%** (4,690). Chốt trước ticket 10/11.

## Trạng thái ticket

| Ticket | Trạng thái | Ghi chú |
|---|---|---|
| 01 Working copy + pin | done | `da93b27`, 4/4 |
| 02 Smoke test | done | ALL_PASS: 582/582 key, forward finite, depth [6,1,256,704] |
| 02b Fix môi trường | done | numba/torchvision/CUDA/gcc/numba.errors |
| 03 Velocity contract | done | `docs/velocity-contract.md` + số đo 34k frame |
| 04 Dataset gate | done | infos 120/120, load 1 sample (v19) |
| 05 Evaluator core | done | pytest synthetic |
| 06 Evaluator adapter | done | mAP 0.298 trên frame thật; `proxy_eval/mit_adapter.py` |
| 07 Pipeline transform | done | scene-0796, 12/12 check; `spray/plume_transform.py` |
| **08 Model routing** | **ready — làm tiếp** | nối `points_clean` vào camera, `points` vào LiDAR |
| 09 Pipeline e2e | blocked | chờ 08 |
| 10 Train/eval config | blocked | chờ 09 |
| 11 Mini A/B | blocked | chờ 10 |
| 12 SemanticSpray stats | done | so sánh cluster |
| 13 Gate review | blocked | chờ 11 |
| 14 Denoise B0 | ready | 02,05 xong |
| 15 Plume provenance | ready | việc nhỏ, docstring |
| 16 Plume geometry research | ready | đo hình học thật theo cự ly |
| 17 Plume shell geometry | blocked | chờ số đo của 16 |

Chi tiết từng ticket: `.scratch/spray-augmentation/issues/`.

## Preconditions (spec v1.5)

1. Version `da93b27` — PASS
2. Smoke test checkpoint + forward — PASS
3. Checkpoint fused + hash — PASS (`ee0a3892…2122`)
4. Dataset gate (infos + load sample) — PASS (v19)
5. Evaluator trên frame MIT thật — PASS (mAP 0.298; ticket 06)
6. Velocity contract — PASS

Spec: `.scratch/spray-augmentation/spec.md` (Status: **`ready-for-agent`**; preconditions 1–6 pass).

## Kaggle

- Kernel: https://www.kaggle.com/code/nguynhuy9669/bevfusion-smoke-test
- Version mới nhất: **COMPLETE** (pull ngày 2026-11-07); log có `TICKET04_OK`,
  `TICKET06_OK`, `TICKET07_OK`.
- Lấy output:
  ```bash
  kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k8out
  ```
- Artifacts trong `/tmp/k8out/smoke_test/artifacts/`:
  - `report.json` — 6/6 tiêu chí ticket 02
  - `infos.json` — train 120 / val 120
  - `dataset_sample.json` — load 1 sample, 6 camera, 0 sweep
  - `checkpoint.json` — 582/582, sha `ee0a3892…2122`
  - `eval_frame.json`, `real_frame_*` — model chạy 2 frame thật (ticket 06)
  - `ticket07_infos.json`, `ticket07_transform.json` — PlumeTransform scene-0796
- Bản sao JSON nhỏ đã commit ở `kaggle/smoke_test/evidence/`; `mit_eval_result.json`
  là kết quả evaluator local.
- Notebook: `kaggle/smoke_test/bevfusion-smoke-test.ipynb` (cell 17–21 = ticket 04/06/07);
  bản tách từng bước ở `kaggle/smoke_test/cells/`.
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

### Cái gì ở ngoài git (và lấy lại thế nào)

| Thứ | Ở đâu | Cần làm gì |
|---|---|---|
| Kaggle credentials | `~/.kaggle/kaggle.json` trên máy | Tạo/đăng nhập lại; **không bao giờ commit** |
| Kernel | `nguynhuy9669/bevfusion-smoke-test` (private) | Code đã có trong `kaggle/smoke_test/`; push lại bằng `kaggle kernels push -p kaggle/smoke_test` |
| Output kernel (infos pkl, log) | Version v19 trên Kaggle | `kaggle kernels output nguynhuy9669/bevfusion-smoke-test -p /tmp/k7` |
| Evidence JSON nhỏ | `kaggle/smoke_test/evidence/` | **Đã commit** (report, infos, sample, checkpoint, cfg, toolchain) |
| Dataset nuScenes | Kaggle dataset public, gắn qua `kernel-metadata.json` | Tự attach khi push; không cần tải local |
| Checkpoint fused | Dropbox mirror | URL + sha256 trong `mit/PIN.md`; kernel tự tải |
| Kanban artifact | artifacts.commandcode.ai | Link private, mở bằng cùng account; bản local ở `docs/kanban.html` |

Tóm lại: code/docs/tickets/evidence JSON đã ở git; Kaggle chỉ giữ kernel + output
lớn, và mọi thứ tái tạo được từ repo + `HANDOFF.md`.

## Prompt dán vào CommandCode (máy mới)

```text
Bạn tiếp quản repo bevfusion-spray-pilot. Đọc HANDOFF.md ở root, spec
.scratch/spray-augmentation/spec.md (đã ready-for-agent), và ticket 08
.scratch/spray-augmentation/issues/08-model-routing.md (xem thêm ticket 07
và mục Interface contract trong spec).

Nhiệm vụ: implement ticket 08 — model forward routing. Camera branch nhận
points_clean, LiDAR branch nhận points đã chèn plume. Test bằng stub model với
shape + marker value; không đổi kiến trúc hay số tham số.

Ràng buộc:
- Không đổi pin: da93b27, torch 1.10.1+cu113, mmcv-full 1.4.0, mmdet 2.20.0,
  numpy 1.22.4. Không sửa third_party/.
- Chỉ tick checkbox khi có bằng chứng thật; ghi số liệu vào ticket.
- Không push Kaggle nếu chưa cần; ưu tiên test local (`pytest` hiện 33 passed).

Sau ticket 08: ticket 09 (e2e test) → 10 (config A/B) → 11 (mini A/B) → 13.
Ticket 14/15/16 có thể làm song song; 17 chờ số đo của 16.

Trước ticket 10/11: hỏi user chốt ngưỡng plume — 50 km/h (2.0% frame val)
hay 30 km/h (13.8%), hoặc chọn scene highway.

Báo cáo ngắn: đã làm gì, test nào pass, blocker, commit.
```

## Tham chiếu (không lặp nội dung)

- `.scratch/spray-augmentation/spec.md` — spec v1.5, preconditions, interface contract
- `.scratch/spray-augmentation/issues/` — 18 ticket
- `docs/velocity-contract.md` — velocity frame + số đo eligible
- `docs/kanban.html` + `scripts/build_kanban.py` — board tự sinh
- `kaggle/smoke_test/` — notebook, kernel metadata, per-step cells
- `mit/PIN.md` — commit pin + checkpoint mirror/sha256
- `docs/adr/0001..0003` — các quyết định đã chốt
