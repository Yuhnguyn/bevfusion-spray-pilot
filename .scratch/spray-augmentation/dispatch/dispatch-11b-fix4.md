# Ticket 11-b-fix4 — shim numba chạy quá sớm: probe import `mmdet3d.datasets` cần devkit

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `d6bd9c6` · nhánh `main`.

Kernel v4 chết ở chính cái probe của shim, **trước** khi cài devkit. Log thật:

```
SMOKE_FAILED numba_shim
Traceback (most recent call last):
ModuleNotFoundError: No module named 'nuscenes'
```

**Nguyên nhân:** probe import `mmdet3d.datasets.pipelines`, mà để vào subpackage đó Python phải chạy
`mmdet3d/datasets/__init__.py` trước; file này có `from .nuscenes_dataset import *`, và
`nuscenes_dataset.py:9` là `from nuscenes.utils.data_classes import Box`. Devkit lúc đó **chưa cài** ⇒ chết.
(`pyquaternion` cũng đến từ devkit, không phải từ `setup.py` của mmdet3d — `setup.py` vendor không có
`install_requires`.)

Đây là lỗi thứ tự, **không** phải lỗi logic shim: shim ghi file đúng, chỉ probe quá sớm.

## Việc 1 — đổi thứ tự trong `main()`

Hiện tại:

```python
    if not install_numba_errors_shim(e2e):
        return 1

    version = install_devkit(e2e)
    if version is None:
        return 1
```

Phải thành: `install_devkit(e2e)` **trước**, rồi `install_numba_errors_shim(e2e)`, rồi mới
`e2e.stream([str(e2e.PY), TASK_SCRIPT], ...)`. Giữ nguyên hai nhánh `return 1`.

Không đổi thân hàm `install_numba_errors_shim` (vẫn ghi `site-packages/numba/errors.py`, vẫn probe
`import numba, numba.errors, mmdet3d.datasets.pipelines`, vẫn `SMOKE_NUMBA_SHIM_OK` / `SMOKE_FAILED numba_shim`).
Không đổi `install_devkit`, `devkit_packages`, `DEVKIT_PINS`.

## Việc 2 — sửa test thứ tự

Test hiện đang assert shim đứng **trước** `install_devkit(` — sai so với thiết kế đúng. Sửa thành:

1. `src.index("install_devkit(") < src.index("install_numba_errors_shim(")` — devkit trước, shim sau.
2. `src.index("install_numba_errors_shim(") < src.index("TASK_SCRIPT]")` — shim sau devkit nhưng **trước**
   dòng chạy smoke (`e2e.stream([str(e2e.PY), TASK_SCRIPT]`). Nếu index `TASK_SCRIPT]` không tìm thấy,
   dùng `src.index("TASK_SCRIPT"), src.index("TASK_SCRIPT)")`… miễn là so được với lời gọi stream; nếu khó,
   assert `src.count("install_numba_errors_shim(") == 2` (1 định nghĩa + 1 lời gọi) và lời gọi nằm sau
   `install_devkit(e2e)`.
3. Giữ nguyên các test cũ: stdlib-only import, `pip_into_env(` trước `ensurepip`, pin numpy/opencv, không có
   `devkit_deps`.

Đặt tên rõ: `test_shim_runs_after_devkit_install`.

## Việc 3 — kiểm tra local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m py_compile kaggle/train/main.py
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/    # 111 passed, 4 skipped (giữ nguyên số)
```

## Việc 4 — đẩy lên

```bash
git add -A && git commit -m "fix(train): install devkit before the numba shim probe"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/train
kaggle kernels status nguynhuy9669/bevfusion-spray-train
```

Sau push: **dừng**, không chờ, không tải log.

## Điều kiện ĐẠT

- `git status --porcelain` rỗng, commit message như trên.
- `111 passed, 4 skipped`.
- Dataset version ≥ v14, kernel version mới ở `RUNNING`/`QUEUED`.
- Báo lại: thứ tự boot trong `main()` (5 dòng tên hàm theo đúng thứ tự gọi).

## Không được làm

- Không đổi nội dung file shim, không probe chỉ `numba.errors` (phải probe cả `mmdet3d.datasets.pipelines`
  — đó là đường đã chết).
- Không sửa vendor `mit/bevfusion/**`, không đổi pin numba/devkit.
- Không thêm `pip install pyquaternion` — nó đến từ devkit; nếu vẫn thiếu thì báo lại kèm traceback.