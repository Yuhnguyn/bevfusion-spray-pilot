# 20c: truyền cờ chạy cho kernel (để chạy được --sweeps-probe trên Kaggle)

HEAD: 6d614f1  Nhánh: main
Skill: không (ticket hạ tầng/boot chain)

## Hiện trạng (đã kiểm)

- `kaggle/train/main.py:181-186` — chạy `[str(e2e.PY), TASK_SCRIPT]`, **không truyền tham số nào**; kernel script không đặt được biến môi trường.
- `kaggle/train/main.py:188` — `passed = rc == 0 and "SMOKE_OK" in text` ⇒ nếu chạy `--sweeps-probe` (kết thúc bằng `SWEEPS_OK`) thì kernel sẽ bị coi là FAIL.
- `kaggle/train/smoke.py` đã có `--sweeps-probe` và `--nusc-version` (commit `6d614f1`).

## Việc phải làm

1. `kaggle/train/main.py`:
   - thêm `ARGS_FILE = pathlib.Path(__file__).resolve().parent / "task_args.txt"`.
   - thêm hàm thuần `task_args(path=ARGS_FILE)` → `list[str]`: đọc file nếu có, bỏ dòng bắt đầu bằng `#`, tách theo khoảng trắng, bỏ token rỗng; file không có → `[]`.
   - `cmd = [str(e2e.PY), TASK_SCRIPT] + task_args()`; log `TASK_ARGS <các token | (none)>` trước khi chạy.
   - tách verdict thành hàm thuần `verdict(rc, text)` → `(passed: bool, marker: str)`, chấp nhận **một trong** `SMOKE_OK`, `SWEEPS_OK`; log `smoke verdict : <marker | FAILED>`. Giữ nguyên phần in 30 dòng cuối khi fail và giữ các dòng `_field(...)` cũ; thêm khi có `SWEEPS_OK`/`SWEEPS_FAILED` thì in thêm `SWEEPS_INFO`, `SWEEPS_PTS mode=multi`, `SWEEPS_UNIQUE`, `STEP_TIME` (dùng `_field`).
2. `kaggle/train/task_args.txt` — file mới, nội dung chỉ một dòng comment: `# mỗi lần push đặt đúng một chế độ chạy; để trống = luồng A/B mặc định`.
3. `tests/test_task_args.py` — test thuần Python: file thiếu → `[]`; file chỉ comment → `[]`; `# ...\n--sweeps-probe\n` → `["--sweeps-probe"]`; nhiều khoảng trắng/xuống dòng → tách đúng; `verdict(0, "x\nSWEEPS_OK n_single=1\n")` → `(True, "SWEEPS_OK")`; `verdict(0, "SMOKE_OK ...")` → `(True, "SMOKE_OK")`; `verdict(1, "SWEEPS_OK")` → `(False, "")`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` xanh, số test tăng ≥ 5 (hiện 117 passed, 4 skipped).
- [ ] `python3 -c "import ast;ast.parse(open('kaggle/train/main.py').read())"` không lỗi.
- [ ] Không có `task_args.txt` hoặc file chỉ có comment ⇒ hành vi y như v6 (cùng lệnh, cùng verdict `SMOKE_OK`).
- [ ] `git diff` chỉ chạm 3 file nêu trên.

## Cấm

- Không sửa `kaggle/train/smoke.py`, không sửa vendor, không đổi timeout 10800, không push kernel, không commit.
- Không dùng `os.environ` làm cơ chế chính (Kaggle script kernel không đặt được env) — file là nguồn duy nhất.