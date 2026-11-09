# Ticket 11-b-fix2 — sibling import chết trên kernel: `main.py` phải tự chứa

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `6c1283a` · nhánh `main`.

Kernel v2 (vừa push) **ERROR sau 1 giây**. Log thật:

```
File "/kaggle/src/script.py", line 22, in <module>
    from devkit_deps import devkit_packages
ModuleNotFoundError: No module named 'devkit_deps'
```

**Nguyên nhân:** Kaggle script kernel chỉ upload **đúng một file** `code_file` và chạy nó ở
`/kaggle/src/script.py`. File cùng thư mục (`probe.py`, `smoke.py`, `devkit_deps.py`) **không** được upload;
chúng chỉ có mặt sau khi `e2e.extract_code()` giải nén dataset vào `/kaggle/working/repo`.
Vì import nằm ở top-level, nó chạy **trước** `main()` ⇒ chết ngay.
Bằng chứng cũ: `BOOT = next(pathlib.Path("/kaggle/input").rglob("kaggle/e2e/main.py"))` chính là để lấy
module từ dataset, không phải từ file kề bên.

## Việc 1 — làm `main.py` tự chứa

1. Chuyển nguyên hàm `devkit_packages()` (3 dòng pin, đúng như hiện tại) vào **`kaggle/train/main.py`**,
   đặt ngay dưới `DEVKIT_PINS`.
2. Xoá `sys.path.insert(...)` và `from devkit_deps import devkit_packages` ở đầu file.
3. Xoá file `kaggle/train/devkit_deps.py` (`git rm`).
4. `install_devkit()` giữ nguyên logic hiện có: `e2e.pip_into_env(*devkit_packages(version))` là đường chính,
   `ensurepip` là dự phòng, `SMOKE_DEVKIT_INSTALL via=...`, verify `val=150`, `pinned_stack_drift`. Không đổi gì khác.

Sau việc này `main.py` chỉ được import **thư viện chuẩn** (`importlib.util`, `pathlib`, `sys`) — không import
module nội bộ nào.

## Việc 2 — test chống tái phát (thay test cũ)

Sửa `tests/test_kaggle_devkit_install.py` (bỏ phần load `devkit_deps`), giữ 2 assert cũ
(`pip_into_env(` đứng trước `ensurepip`) và thêm:

1. **Không có import nội bộ:** `ast.parse(MAIN.read_text())`, lấy mọi `Import`/`ImportFrom`; assert tập module
   gốc ⊆ `{"importlib", "pathlib", "sys"}`. Đây là bất biến sống còn: file chạy một mình.
2. **Pin còn nguyên:** source có `"nuscenes-devkit==%s"`, `"numpy==1.22.4"`, `"opencv-python==4.8.1.78"`
   và có `def devkit_packages(`.
3. `assert not DEVKIT_DEPS.exists()` — file phụ không được quay lại.

Đặt tên test rõ nghĩa: `test_main_imports_stdlib_only`, `test_devkit_packages_pins`, `test_no_sibling_module`.

## Việc 3 — kiểm tra local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m py_compile kaggle/train/main.py
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/     # mong đợi 106 passed, 4 skipped
```

## Việc 4 — đẩy lên Kaggle (làm đúng thứ tự)

```bash
git add -A && git commit -m "fix(train): inline devkit pins in kernel script, drop sibling module import"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py   # sync TRƯỚC khi push
kaggle kernels push -p kaggle/train
kaggle kernels status nguynhuy9669/bevfusion-spray-train
```

Sau push: **dừng**. Không chờ, không tải log, không push lần 2.

## Điều kiện ĐẠT

- `git log --oneline -1`, `git status --porcelain` rỗng, `kaggle/train/devkit_deps.py` **không còn** trong `git ls-files`.
- `106 passed, 4 skipped`.
- Dataset version mới (≥ v12), danh sách file **không** còn `devkit_deps.py`.
- `kaggle kernels status` sau push: `RUNNING` hoặc `QUEUED` (không phải `ERROR` ngay).

## Không được làm

- Không đổi `DEVKIT_PINS`, không đổi pin numpy/opencv.
- Không sửa `smoke.py`, `e2e/main.py`, `spray/**`.
- Không "sửa" bằng cách thêm `sys.path` trỏ `/kaggle/working/repo` ở top-level — lúc đó repo chưa được giải nén.
- Không nới `val=150`.