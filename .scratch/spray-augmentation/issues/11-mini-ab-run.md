# 11: Mini A/B run + report

**What to build:** Train hai arm trên mini, eval trên **held-out spray**, và báo paired delta với bootstrap theo scene, FP, recall theo range, clean retention. Kèm report và recipe bàn giao.

**Blocked by:** 06, 10

**Status:** ready-for-agent

- [ ] Arm A và B chạy cùng ngân sách và seed.
- [ ] Eval trên held-out spray với tham số không dùng khi train.
- [ ] Báo `G = mAP_clean - mAP_spray` cho từng arm và paired delta.
- [ ] Bootstrap theo scene; FP và recall theo range được báo.
- [ ] Report + recipe được lưu.

## PM nghiệm thu 11-b — smoke kernel (shift 2026-11-09)

Mục tiêu: lấy `s_per_step` và `peak_gb` bằng một smoke run không train thật.
Kernel `nguynhuy9669/bevfusion-spray-train`, code dataset `nguynhuy9669/bevfusion-spray-pilot-code`.

| version | kết quả | nguyên nhân thật | fix |
|---|---|---|---|
| v1 | `ERROR` sau 543 s | venv do `uv venv` tạo **không có `pip`**; `main.py` gọi `PY -m pip install nuscenes-devkit` ⇒ `No module named pip`. Mọi lớp trước đó đã xanh: 12/12 CUDA extension, `OPS_OK`, `STACK_OK 1.10.1+cu113 1.4.0 2.20.0` | `6c1283a` — cài devkit bằng `e2e.pip_into_env()` (uv), `ensurepip` chỉ là dự phòng |
| v2 | `ERROR` sau 1 s | Kaggle script kernel chạy **một file duy nhất** ở `/kaggle/src/script.py`; `from devkit_deps import devkit_packages` ở top-level ⇒ `ModuleNotFoundError` | `ad678d8` — inline `devkit_packages()` vào `main.py`, xoá `kaggle/train/devkit_deps.py` |
| v3 | `ERROR` sau ~600 s | `mmdet3d/datasets/pipelines/utils.py:5` (vendor `da93b27`) import `numba.errors`; numba **0.58.1 không còn** module đó (chỉ có `numba/core/errors.py`; kiểm bằng cách mở wheel PyPI). Devkit đã cài đúng: `SMOKE_DEVKIT_INSTALL via=uv version=1.1.11`, `SMOKE_DEVKIT_OK version=1.1.11 val=150` | `70733ab` — shim `site-packages/numba/errors.py` (`from numba.core.errors import *`), probe import cả `mmdet3d.datasets.pipelines` trước khi chạy smoke |
| v4 | đang chạy | — | — |

Nguyên tắc đã giữ: không sửa vendor `mit/bevfusion` (pin `da93b27`), không đổi `numba==0.58.1`,
không đổi `DEVKIT_PINS`, không nới `val=150`.

Test local: **111 passed, 4 skipped** (baseline 105 + 6 test mới của 2 vòng fix).

## PM nghiệm thu — smoke PASS (kernel v6, 2026-11-09 11:4x)

Kernel `nguynhuy9669/bevfusion-spray-train` **v6 COMPLETE**, `smoke rc=0`, `smoke verdict: SMOKE_OK`.
Tổng thời gian kernel 2086 s (≈34,8 phút), trong đó ~10–11 phút là dựng venv + build 12 CUDA extension.

| Chỉ số | Giá trị [ĐO] | Ý nghĩa |
|---|---|---|
| `s_per_step` | **1,4546 s** (batch 2, Tesla T4) | 4.000 bước (2 arm × 2.000) ≈ **5.818 s ≈ 1 h 37 m** compute |
| `peak_gb` | **4,251 / 16 GB** | còn dư 3,7× → batch 4 khả thi nếu cần rút thời gian |
| mini split | `n=4000 scenes=698 gt_boxes=137737 val_scenes=150` | khớp tham số thiết kế |
| `MINI_SPLIT_NOSWEEPS` | `n=4000` | đúng dự kiến: dataset keyframes-only, `sweeps=[]` (ticket 20) |
| arm A pipeline | không có `PlumeTransform` | đúng nhánh đối chứng |
| arm B pipeline | có `PlumeTransform` | đúng nhánh can thiệp |

Bản vá `32cf436` là mắt xích cuối: v5 chết vì `MINI_SPLIT_FAILED got=0` (mọi sample bị loại do thiếu file sweep);
v6 cho `sweeps=[]` và split dựng được 4.000 sample.

Ghi chú: `LoadPointsFromMultiSweeps` vẫn nằm trong pipeline cả 2 arm nhưng nhận `sweeps=[]` — chạy được,
không thêm điểm. Khi có sweeps thật (ticket 20) thì transform này tự dùng, không phải sửa pipeline.

## 11-c: ba mảnh code (PM nghiệm thu)

| Mảnh | Nội dung | Commit | Test |
|---|---|---|---|
| 11-c1 | `kaggle/train/ab_run.py` train 2 arm × 2.000 bước, `sweeps_num: 0`, lưu `ckpt_arm{A,B}.pth`, marker `AB_STEP/AB_ARM_OK/AB_TRAIN_OK`; sửa lỗi cộng trùng loss bằng `loss_keys()` | `322e26a` | 144 passed |
| 11-c2 | `scripts/make_eval_split.py` (assert 196 frame / 16 scene, `--selftest`) + `proxy_eval/bootstrap.py` bootstrap paired theo scene | `9e3b4dd` | 165 passed |
| 11-c3a | `make_mini_split.py --tokens-json`: dựng pkl từ danh sách token cố định, không chọn lại ngẫu nhiên | `a60b78b` | 169 passed |
| 11-c3b | `kaggle/train/ab_eval.py`: 4 ô (2 arm × sạch/có plume) trên cùng 196 frame, dump pred + GT, gọi `evaluate_files`, `EVAL_CELL`, `EVAL_OK` có `ci95` theo scene | `1c24d9a` | 176 passed |

Hai điểm PM đã kiểm tra trong 11-c3b thay vì tin agent:

1. **Khác biệt duy nhất giữa hai điều kiện là plume.** `build_pipeline_steps` dựng arm B bằng
   `spray.ab_config.train_pipeline("B")`, tức đúng pipeline của arm A **cộng một** `PlumeTransform`
   chèn sau `RandomFlip3D`. Không có bước augment riêng nào khác, nên `delta = spray − clean`
   không bị nhiễu bởi cấu hình khác.
2. **Plume tất định theo frame.** `PlumeTransform` dùng `seed: 0`, còn `inject_plume()` sinh RNG từ
   `blake2b("{token}:{seed}")`; hai ô dùng cùng token nên nhận đúng cùng một đám mây plume.

Hạn chế phải ghi vào báo cáo: eval chạy trên `train` pipeline (`test_mode=False`) nên vẫn có
`GlobalRotScaleTrans`/`RandomFlip3D`; GT được biến đổi cùng điểm nên phép so sánh vẫn đúng cặp,
nhưng mAP tuyệt đối không phải chuẩn nuScenes và **chỉ đọc phần chênh lệch**, không đọc giá trị tuyệt đối.

### Vì sao eval cần một lượt chạy riêng
v9 đang train với `--task=ab-run` và không có bước eval trong cùng session. Checkpoint nằm trong
output của version 9; lượt eval sau phải đọc được chúng. Hai đường:
(a) tải `ckpt_arm{A,B}.pth` về rồi upload thành dataset, push `--task=ab-eval --ckpt-dir=/kaggle/input/<ds>`;
(b) gộp train+eval vào một task để session sau tự chạy liền. Đường (a) rẻ GPU hơn, đường (b) sạch hơn
về mặt "cùng một session". Chọn sau khi biết dung lượng checkpoint thật.
