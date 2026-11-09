# 20e: `task_args.txt` không được đọc trên kernel (đường dẫn tính từ `__file__`)

HEAD: 06cdf0f  Nhánh: main
Skill: không (ticket hạ tầng/boot chain)

## Bằng chứng

- Kernel v7 `COMPLETE`, log `/tmp/ktrain_v7.log` dòng 987: `TASK_ARGS (none)`; dòng 989: `version=v1.0-trainval` ⇒ chạy lại luồng A/B, không chạy `--sweeps-probe`.
- Dataset `nguynhuy9669/bevfusion-spray-pilot-code` **version 16** có `kaggle/train/task_args.txt` 115 byte [ĐO `kaggle datasets files`], và `main.py` trong cùng version đã có `TASK_ARGS` ⇒ code mới, chỉ file cờ không tìm thấy.
- Nguyên nhân gốc: `kaggle/train/main.py:23` đặt `ARGS_FILE = pathlib.Path(__file__).resolve().parent / "task_args.txt"`. Kernel script chạy `code_file: main.py` từ `/kaggle/src/main.py`, còn cây code nằm ở `e2e.REPO` (`/kaggle/working/repo`, `kaggle/e2e/main.py:34`). Vì vậy `__file__` trỏ sai thư mục và `task_args()` nuốt `FileNotFoundError` → trả `[]` im lặng.

## Việc phải làm

1. `kaggle/train/main.py`:
   - `task_args(path)` giữ nguyên hành vi khi được truyền `path` cụ thể (test cũ phải xanh).
   - thêm hàm thuần `resolve_args_file(candidates)` → `pathlib.Path | None`: trả **path đầu tiên tồn tại** trong danh sách.
   - trong `main()`, sau khi có `e2e`, gọi `task_args(resolve_args_file([...]))` với danh sách theo thứ tự: `pathlib.Path(e2e.REPO) / "kaggle/train/task_args.txt"`, `pathlib.Path.cwd() / "kaggle/train/task_args.txt"`, `pathlib.Path(__file__).resolve().parent / "task_args.txt"`.
   - log trước khi chạy: `TASK_ARGS_FILE <path | none>` và `TASK_ARGS <tokens | (none)>`. Nếu `none` thì vẫn chạy tiếp (luồng A/B mặc định phải không phụ thuộc file cờ).
2. `tests/test_task_args.py` — thêm test cho `resolve_args_file`:
   - repo có file, cwd không có ⇒ trả path trong repo;
   - không đâu có ⇒ `None`;
   - cả hai có ⇒ trả cái đầu theo thứ tự ưu tiên.
3. Không đổi `smoke.py`, không đổi timeout, không đổi `TASK`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` xanh, số test tăng ≥ 3 (hiện 126 passed, 4 skipped).
- [ ] `grep -n "ARGS_FILE" kaggle/train/main.py` chỉ còn dùng trong `resolve_args_file`/`task_args` mặc định, không còn là nguồn duy nhất.
- [ ] Mô phỏng được bằng test: `main.py` nằm ở thư mục khác với gốc repo vẫn tìm ra cờ (test dùng `tmp_path`).
- [ ] `git diff` chỉ chạm 2 file.

## Cấm

- Không dùng `os.environ`, không thêm dependency, không push kernel, không commit.