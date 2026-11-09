# Ticket 11-b-fix — devkit install chết vì venv không có pip

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `1eb3e59` · nhánh `main`.
Kernel `nguynhuy9669/bevfusion-spray-train` v1 đã chạy và **ERROR**; log (tải bằng `kaggle kernels logs`) cho:

```
$ /root/bevfusion_e2e/env/bin/python -m pip install nuscenes-devkit==1.1.11 numpy==1.22.4 opencv-python==4.8.1.78
/root/bevfusion_e2e/env/bin/python: No module named pip
[exit=1 in 0.0s]
SMOKE_DEVKIT_INSTALL_FAILED version=1.1.11
$ /root/bevfusion_e2e/env/bin/python -m pip install nuscenes-devkit==1.1.10 ...
/root/bevfusion_e2e/env/bin/python: No module named pip
[exit=1 in 0.0s]
SMOKE_DEVKIT_INSTALL_FAILED version=1.1.10
SMOKE_FAILED devkit
```

Phần còn lại của boot **đã xanh**: 12/12 CUDA extension `ok: true`, `OPS_OK`, `STACK_OK 1.10.1+cu113 1.4.0 2.20.0`.
Chỉ chết ở bước cài devkit. Đừng sửa gì khác.

**Nguyên nhân:** `kaggle/e2e/main.py::install_env()` tạo venv bằng `uv venv` ⇒ venv **không có `pip`**.
Cả repo cài package vào venv bằng `uv pip install --python <PY>` (hàm `pip_into_env()`), không bao giờ
dùng `PY -m pip`. `kaggle/train/main.py::install_devkit()` là chỗ duy nhất còn gọi `-m pip` ⇒ sai.

## Việc 1 — sửa `kaggle/train/main.py::install_devkit()`

Thứ tự bắt buộc:

1. **Đường chính:** `e2e.pip_into_env(*packages)` — hàm này của `kaggle/e2e/main.py`, đã dùng uv của
   chính kernel đó, đã set `--python <PY>`, timeout 3600. `packages` = `devkit_packages(version)`, một hàm
   thuần mới bạn thêm vào cùng file, trả list:
   `["nuscenes-devkit==<version>", "numpy==1.22.4", "opencv-python==4.8.1.78"]`
   (giữ nguyên 2 pin này — devkit có requirement `numpy` lỏng, để uv nâng numpy là vỡ torch 1.10/numba).
2. **Đường dự phòng** chỉ chạy khi (1) `rc != 0`:
   `e2e.stream([str(e2e.PY), "-m", "ensurepip", "--upgrade"])`, nếu rc == 0 thì
   `e2e.stream([str(e2e.PY), "-m", "pip", "install"] + devkit_packages(version))`.
   Nếu `ensurepip` cũng rc != 0 ⇒ bỏ, sang version kế tiếp trong `DEVKIT_PINS`.
3. In `SMOKE_DEVKIT_INSTALL via=<uv|ensurepip> version=<x>` ngay trước khi verify import.
   Giữ nguyên `SMOKE_DEVKIT_INSTALL_FAILED version=<x>` khi cả hai đường fail.
4. Giữ nguyên toàn bộ verify hiện có: `SMOKE_DEVKIT_OK version=... val=150`, `SMOKE_DEVKIT_VERIFY_FAILED`,
   và check `pinned_stack_drift` (`1.22.4` + `e2e.PINNED_PROBE`). Không nới điều kiện nào.

Không sửa `kaggle/e2e/main.py`, không sửa `kaggle/train/smoke.py`, không đổi `DEVKIT_PINS`.

## Việc 2 — test chống tái phát

Tạo `tests/test_kaggle_devkit_install.py` (test tĩnh, không import `kaggle/train/main.py` vì file đó
`rglob("/kaggle/input")` lúc import). Đọc `kaggle/train/main.py` bằng `pathlib`, assert:

1. Có `pip_into_env(` và có `ensurepip`.
2. `src.index("pip_into_env(") < src.index("ensurepip")` — chứng minh uv là đường chính, ensurepip là dự phòng.
3. `devkit_packages("<version>")` trả đúng 3 phần tử và có `"numpy==1.22.4"` + `"opencv-python==4.8.1.78"`;
   muốn test được hàm này thì **tách nó ra file riêng** `kaggle/train/devkit_deps.py` và
   `from devkit_deps import devkit_packages` trong `main.py` (thêm `sys.path` cùng thư mục là được,
   `main.py` đã import `pathlib`/`sys`). Test import module đó trực tiếp, không cần Kaggle.

Tên test rõ nghĩa, ví dụ `test_uv_is_primary_path`, `test_packages_pin_numpy`.

## Việc 3 — kiểm tra local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m py_compile kaggle/train/main.py kaggle/train/devkit_deps.py
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/     # 105 passed, 4 skipped + test mới
```

Baseline hiện tại là **105 passed, 4 skipped**; sau việc này phải là **106 passed, 4 skipped**
(số pass tăng đúng bằng số test bạn thêm).

## Việc 4 — đẩy lên Kaggle

```bash
git add -A && git commit -m "fix(train): install nuscenes-devkit through uv, fall back to ensurepip"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py   # sync TRƯỚC khi push
kaggle kernels push -p kaggle/train
```

`kaggle_code_sync.py` phải báo dataset version mới (≥ v11) và có `kaggle/train/devkit_deps.py` trong danh sách file.
Sau khi push: **dừng, không chờ**. PM tự theo dõi status và tải log.

## Điều kiện ĐẠT

- `git log --oneline -1` + `git status --porcelain` (phải rỗng).
- `106 passed, 4 skipped`.
- Kernel version đã push + dataset version mới, kèm dòng `kaggle kernels status` ngay sau push.

## Không được làm

- Không đổi `DEVKIT_PINS`, không đổi `numpy==1.22.4` / `opencv-python==4.8.1.78`.
- Không sửa `smoke.py`, `e2e/main.py`, `spray/**`, `scripts/make_mini_split.py`.
- Không nới `val=150` hay `pinned_stack_drift`.
- Không tự thêm package khác (shapely, pyquaternion…) — uv resolve deps của devkit là đủ; nếu thiếu thì
  báo lại kèm traceback, đừng đoán.