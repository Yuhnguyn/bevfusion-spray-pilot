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
