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

## 11-d: kết quả train A/B — kernel v9 COMPLETE (2026-11-09 16:18)

Version `scriptVersionId=367214655`, log 1.070 dòng, `AB_TRAIN_OK arms=2 steps=2000 time_s=5919.9`.

| Arm | loss_first | loss_last | loss_mean_last100 | s/step | peak_gb |
|---|---|---|---|---|---|
| A (không plume) | 2,306806 | 1,580883 | 1,852402 | 1,2080 | 4,223 |
| B (có plume) | 2,310777 | 1,745840 | 1,905799 | 1,2097 | 4,224 |

- Mini split: `MINI_SPLIT_OK n=4000 scenes=698 gt_boxes=137737 val_scenes=150 seed=0`.
- Thời gian train 5.919,9 s ≈ 98,7 phút cho 4.000 bước (2 arm), đúng ước tính 1,21 s/bước.
- `s_per_step` hai arm lệch 0,0017 s → plume gần như không tốn thêm thời gian (147 điểm/frame trên nền ~34.700).
- Arm B có loss cao hơn ở cả bước cuối (1,746 vs 1,581) và trung bình 100 bước cuối (1,906 vs 1,852). Đây là
  chiều **hợp lý** (dữ liệu khó hơn) nhưng **2000 bước là quá ngắn để kết luận**: chênh lệch loss huấn luyện
  không phải metric phát hiện, và một điểm loss cuối vẫn chịu nhiễu của batch cuối.
- Kết luận khoa học phải chờ `EVAL_OK` (4 ô trên 196 frame). Không dùng bảng loss này làm kết quả A/B.

## 11-e → 11-g: chuỗi lỗi của lượt eval (2026-11-09)

Mục tiêu: chạy `--task=ab-eval` trên 196 frame / 16 scene, đọc ckpt v9 từ dataset
`nguynhuy9669/bevfusion-spray-ckpt` (2 x 156 MiB, sha256 đã ghi trong log tải).

| Version | Kết quả | Nguyên nhân gốc | Sửa |
|---|---|---|---|
| v11 | `EVAL_FAILED eval_pkl` | `nuscenes-devkit 1.1.11` viết `val = \` rồi list ở dòng sau; regex trong `spray/mini_split.py` đòi `[` ngay sau `=` | 11-f: `ast.parse` + `literal_eval`; `--tokens-json` không còn bắt buộc đọc val split |
| v12 | `EVAL_FAILED cell` | `gt_labels_3d` sau `scatter` là **list** tensor CUDA; `_batch_gt` chỉ xử lý tensor trực tiếp nên rơi vào `np.asarray(list[Tensor])` | 11-g: helper `_to_numpy` chuẩn hoá list / `DataContainer` / `BaseInstance3DBoxes` / tensor CPU-CUDA / ndarray |
| v13 | đang chạy | — | — |

Bằng chứng cho 11-f: giải nén `nuscenes/utils/splits.py` từ wheel 1.1.11 thật rồi gọi
`load_val_scenes()` -> **150 scene**, phần tử đầu `scene-0003`, khớp `SMOKE_DEVKIT_OK version=1.1.11 val=150`.

Đã qua ở v12 trước khi chết: `EVAL_SET_OK frames=196 scenes=16`,
`EVAL_SPLIT_OK frames=196 scenes=16`, `EVAL_INFO device=cuda torch=1.10.1+cu113`.

Chi phí: v11 ~23 phút GPU, v12 ~12 phút GPU. Bài học quy trình: mỗi lần đổi đường code eval
phải chạy `--limit=5` trước; boot 10 phút là chi phí cố định nên lượt nhỏ gần như miễn phí
so với việc chết ở frame 1 của ô 1.

Test: 192 passed, 4 skipped sau 11-g (thêm `tests/test_ab_eval.py` 5 test, đỏ trước khi sửa).
