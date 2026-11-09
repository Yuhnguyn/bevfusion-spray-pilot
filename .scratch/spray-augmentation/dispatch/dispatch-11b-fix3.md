# Ticket 11-b-fix3 — `numba.errors` không còn trong numba 0.58.1

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `ad678d8` · nhánh `main`.

Kernel v3 tiến thêm 2 bước rồi chết. Log thật (đã verify):

```
SMOKE_DEVKIT_INSTALL via=uv version=1.1.11
SMOKE_DEVKIT_OK version=1.1.11 val=150
SMOKE_INFO dataroot=/kaggle/input/datasets/sahangunasekara92/nuscenes-v1-0-full-keyframes
Traceback (most recent call last):
  File "scripts/make_mini_split.py", line 302, in main
    from mmdet3d.datasets import NuScenesDataset
  File ".../mmdet3d/datasets/pipelines/utils.py", line 5, in <module>
    from numba.errors import NumbaPerformanceWarning
ModuleNotFoundError: No module named 'numba.errors'
SMOKE_FAILED mini_split
```

**Nguyên nhân (đã kiểm chứng, đừng điều tra lại):** venv pin `numba==0.58.1` (bắt buộc cho Python 3.8 +
numpy 1.22). Bản 0.58.1 **chỉ có `numba/core/errors.py`**, không có `numba/errors.py` — module cũ đã bị bỏ.
Vendor `mit/bevfusion @ da93b27` vẫn import đường cũ. `grep -rn "numba.errors" mit/bevfusion --include=*.py`
chỉ ra **đúng một dòng**: `mmdet3d/datasets/pipelines/utils.py:5`. Ticket 02 (smoke test) và ticket 09 (e2e)
không chết vì chưa bao giờ import `mmdet3d.datasets.pipelines`.

## Cách sửa: shim trong venv, KHÔNG sửa vendor, KHÔNG đổi pin numba

1. Thêm hàm vào `kaggle/train/main.py`:

```python
def install_numba_errors_shim(e2e):
    """Alias ``numba.errors`` -> ``numba.core.errors`` (numba >= 0.49 moved it).

    ``mit/bevfusion@da93b27`` does ``from numba.errors import
    NumbaPerformanceWarning`` in ``mmdet3d/datasets/pipelines/utils.py``. The
    pinned numba 0.58.1 dropped that module. Patching the vendor tree would
    break the pin, so write a one-line alias into the venv's site-packages.
    """
    shim = e2e.VENV / "lib" / "python3.8" / "site-packages" / "numba" / "errors.py"
    ...
```

Nội dung file shim (đúng như vầy, không thêm gì):

```python
"""Compatibility shim: numba moved these classes to numba.core.errors."""
from numba.core.errors import *  # noqa: F401,F403
```

2. Gọi nó trong `main()` **sau** `e2e.verify_stack()` (tức là sau khi venv + ops đã xong) và **trước**
   `install_devkit(e2e)`. Trả `bool`; nếu `False` thì log `SMOKE_FAILED numba_shim` và `return 1`.
   Hàm phải tự kiểm chứng, không chỉ ghi file:
   - Nếu `site-packages/numba` không tồn tại ⇒ log `SMOKE_FAILED numba_shim_missing_numba`, `return False`.
   - Ghi file, rồi chạy
     `e2e.capture([str(e2e.PY), "-c", "import numba, numba.errors, mmdet3d.datasets.pipelines; print('SMOKE_NUMBA_SHIM_OK', numba.__version__)"])`.
   - Nếu `SMOKE_NUMBA_SHIM_OK` có trong output ⇒ log nguyên dòng đó, `return True`.
     Nếu không ⇒ log `SMOKE_FAILED numba_shim` + 2000 ký tự cuối của output, `return False`.

   Điểm quan trọng: probe import **cả `mmdet3d.datasets.pipelines`** — đây chính là đường đã chết, nên
   shim đúng thì probe xanh, shim sai thì biết ngay trong 1 giây thay vì chết ở mini split.

3. Giữ nguyên `callable` cũ: `install_devkit`, `devkit_packages`, `DEVKIT_PINS`, thứ tự boot
   (`extract_code → clone_pin → install_env → choose_toolchain → build_ops → verify_stack`). `main.py`
   vẫn chỉ import thư viện chuẩn.

## Test chống tái phát

Thêm vào `tests/test_kaggle_devkit_install.py` (hoặc file mới `tests/test_kaggle_kernel_boot.py`):

1. Source `kaggle/train/main.py` có chuỗi `"numba" / "errors.py"` trong một hàm tên `install_numba_errors_shim`.
2. Thứ tự gọi trong `main()`: `install_numba_errors_shim(` đứng **trước** `install_devkit(` (so index trong source).
3. `main.py` vẫn chỉ import stdlib (test `test_main_imports_stdlib_only` đã có phải pass).

Việc 3 — kiểm tra local:

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m py_compile kaggle/train/main.py
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/   # báo số thật; baseline hiện tại 109 passed, 4 skipped
```

Việc 4 — đẩy lên:

```bash
git add -A && git commit -m "fix(train): alias numba.errors for pinned numba 0.58.1 before mini split"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py   # sync TRƯỚC
kaggle kernels push -p kaggle/train
kaggle kernels status nguynhuy9669/bevfusion-spray-train
```

Sau push: **dừng**, không chờ.

## Điều kiện ĐẠT

- `git status --porcelain` rỗng; commit nêu rõ shim.
- pytest: số pass tăng đúng bằng số test thêm, 0 fail.
- Dataset version mới (≥ v13); kernel version mới ở `RUNNING`/`QUEUED`.
- Báo lại: 3 dòng `SMOKE_DEVKIT_OK`, `SMOKE_NUMBA_SHIM_OK`, `SMOKE_INFO` sẽ có trong log lần chạy tới
  (PM tự lấy log, bạn không cần chờ).

## Không được làm

- **Không** sửa `mit/bevfusion/**` (tree vendor, pin `da93b27`, gitignored) — dù chỉ một dòng import.
- **Không** đổi `numba==0.58.1`, không hạ numba, không cài thêm numba version khác.
- Không sửa `smoke.py`, `scripts/make_mini_split.py`, `spray/**`, `e2e/main.py`.
- Không "fix" bằng `try/except ImportError` trong vendor code.
- Không nới `val=150` hay `pinned_stack_drift`.