# 11-f — parse nuScenes splits.py bằng AST, bỏ phụ thuộc regex

Skill: /Users/huynguyen/.agents/skills/tdd/SKILL.md

Repo: /Users/huynguyen/projects/bevfusion-spray-pilot (nhánh `main`)

## Lỗi thật (từ log kernel, không phải giả thuyết)

```
EVAL_CMD ... make_mini_split.py --tokens-json .../eval_196.json --out .../eval_196.pkl --dataroot ...
Traceback ...
  File "scripts/make_mini_split.py", line 305, in main
    val_scenes = load_val_scenes(_resolve_splits_path(args.splits))
  File "/kaggle/working/repo/spray/mini_split.py", line 110, in load_val_scenes
    scenes = frozenset(_read_list(path, "val"))
  File "/kaggle/working/repo/spray/mini_split.py", line 64, in _read_list
    literal = _extract_list_literal(path.read_text(), name, str(path))
  File "/kaggle/working/repo/spray/mini_split.py", line 47, in _extract_list_literal
    raise ValueError(f"no `{name} = [` assignment in {source}")
ValueError: no `val = [` assignment in /root/bevfusion_e2e/env/lib/python3.8/site-packages/nuscenes/utils/splits.py
EVAL_FAILED eval_pkl
```

Nguyên nhân: `nuscenes-devkit==1.1.11` viết `nuscenes/utils/splits.py` theo kiểu xuống dòng bằng backslash:

```python
val = \
    ['scene-0796', 'scene-0815', ...]
```

Regex hiện tại `^[ \t]*val[ \t]*=[ \t]*\[` đòi `[` nằm ngay sau `=`, nên không khớp. Bản v9 của kernel không dính vì `smoke.py` truyền
`--splits /kaggle/working/mini_splits.py` (file tự sinh); `ab_eval.py` không truyền nên rơi về splits.py của devkit.

## Việc 1 — `spray/mini_split.py`: đọc list bằng AST

Thay `_extract_list_literal` (regex + đếm ngoặc) bằng parse AST:

- `ast.parse(text)` trên nội dung file.
- Duyệt `tree.body`, tìm assignment có target là `ast.Name` với `id == name`:
  - `ast.Assign` với đúng 1 target, hoặc
  - `ast.AnnAssign` (target `ast.Name`).
- Lấy `ast.literal_eval(node.value)`; nếu không phải `list[str]` thì raise `ValueError` như hiện tại.
- Nếu không tìm thấy: raise `ValueError` với thông điệp nêu rõ tên file **và** danh sách tên biến đã thấy ở top-level, để lần sau debug không phải đoán.
- Nếu `ast.parse` ném `SyntaxError`: raise `ValueError` nêu file + dòng, không nuốt lỗi.
- Giữ tên `_extract_list_literal` nếu test cũ đang import nó; nếu bỏ thì phải sửa test cũ, **không** để test cũ bị xoá.

`_read_list` giữ nguyên chữ ký và hành vi công khai. `load_camera_types` và `load_val_scenes` không đổi API.

## Việc 2 — `scripts/make_mini_split.py`: chỉ đọc val scenes khi thật cần

Dòng 305 hiện gọi `load_val_scenes(...)` vô điều kiện. Nhánh `--tokens-json` không dùng `val_scenes` để chọn mẫu, nên:

- Khi `args.tokens_json` có giá trị: thử đọc val scenes nhưng **không được chết** nếu thiếu/không parse được. Thất bại thì dùng `frozenset()`, in một dòng `MINI_SPLIT_VAL_UNKNOWN <lý do ngắn>` và đi tiếp.
- Khi không có `--tokens-json`: giữ nguyên hành vi nghiêm ngặt, thiếu splits là fail (vì `select_tokens` cần nó).
- Dòng `MINI_SPLIT_OK ... val_scenes=` giữ nguyên; ở nhánh tokens-json mà không đọc được thì in `val_scenes=0`.

Không đổi CLI, không đổi format pkl, không đổi marker khác.

## Test bắt buộc

Tạo `tests/test_mini_split_ast.py` (hoặc thêm vào `tests/test_mini_split.py`), dùng chuỗi fixture, **không** cần devkit:

1. Kiểu devkit 1.1.11 có backslash:
   ```python
   val = \
       ['scene-0796', 'scene-0815']
   ```
2. Kiểu ngoặc nhiều dòng:
   ```python
   val = [
       'scene-0796',
   ]
   ```
3. Kiểu annotate: `val: List[str] = ['scene-0796']`
4. Kiểu vendor cũ một dòng: `val = ['scene-0796', 'scene-0815']`
5. File không có `val`: `ValueError` và message có tên file + danh sách tên biến đã thấy.
6. `val = 3` (không phải list) → `ValueError`.
7. `val = ['a', 3]` (list không thuần str) → `ValueError`.
8. `_read_list` trên file không tồn tại vẫn `FileNotFoundError` như cũ.
9. `load_camera_types` vẫn đọc được `camera_types = [...]` từ một fixture giả lập vendor converter.
10. Hàm/helper quyết định "có cần val scenes không" (nếu bạn tách ra, ví dụ `needs_val_scenes(args)`) trả `False` khi có tokens_json và `True` khi không.

## Nghiệm thu

```
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/pytest -q tests/
```

phải xanh toàn bộ (hiện 176 passed, 4 skipped). Commit một lần, message:

```
fix(11-f): parse nuScenes splits via AST; tokens-json no longer needs val split
```

Không sửa `kaggle/train/task_args.txt`, không sửa `kernel-metadata.json`, không push Kaggle.