# 11-g — `_batch_gt` chết khi `gt_labels_3d` là list tensor trên GPU

Skill: /Users/huynguyen/.agents/skills/tdd/SKILL.md

Repo: /Users/huynguyen/projects/bevfusion-spray-pilot (nhánh `main`)

## Lỗi thật (log kernel v12, không phải giả thuyết)

```
EVAL_SPLIT_OK frames=196 scenes=16
EVAL_INFO frames=196 scored=196
EVAL_INFO device=cuda torch=1.10.1+cu113
EVAL_FAILED cell
arm=A cond=clean
Traceback (most recent call last):
  File "kaggle/train/ab_eval.py", line 465, in main
    run_cell(model, loader, out, limit=limit, total=limit)
  File "kaggle/train/ab_eval.py", line 229, in run_cell
    gt_boxes, gt_labels = _batch_gt(batch)
  File "kaggle/train/ab_eval.py", line 200, in _batch_gt
    labels = np.asarray(labels).reshape(-1).astype(int)
TypeError: can't convert cuda:0 device type tensor to numpy. Use Tensor.cpu() to copy the tensor to host memory first.
```

Nguyên nhân: sau `scatter(batch, [device_index])`, `gt_labels_3d` là **list chứa tensor CUDA** (mỗi phần tử một ảnh). `_batch_gt` chỉ xử lý trường hợp `.detach()` trực tiếp, nên `hasattr(labels, "detach")` là `False`, rồi `np.asarray(list[Tensor])` gọi `Tensor.__array__` trên GPU và nổ. `gt_bboxes_3d` đã có nhánh list, `gt_labels_3d` thì thiếu.

## Việc cần làm — `kaggle/train/ab_eval.py`

Sửa `_batch_gt` (khoảng dòng 182–201) để chuẩn hoá **cả hai** trường qua một helper duy nhất, chịu được mọi dạng đã gặp:

- list/tuple (lấy phần tử đầu, giống `gt_bboxes_3d` hiện tại),
- `DataContainer` (dùng `.data`),
- `BaseInstance3DBoxes` (dùng `.tensor`),
- `torch.Tensor` trên CPU **hoặc** CUDA (`.detach().cpu().numpy()`),
- `np.ndarray` (giữ nguyên).

Helper gợi ý: `_to_numpy(value)` trả `np.ndarray`, dùng cho cả boxes và labels. Không dùng `np.asarray` trên tensor trước khi `.cpu()`.

Giữ nguyên chữ ký `_batch_gt(batch) -> (np.ndarray[N,7], np.ndarray[N])` và hành vi hiện tại với trường hợp rỗng (0 box → `(0,7)` float và `(0,)` int).

Đồng thời **rà toàn file** những chỗ còn gọi `.numpy()` hoặc `np.asarray(...)` trên giá trị có thể ở GPU (dòng 233, 238–246 đã `.detach().cpu()` — chỉ sửa nếu thật sự thiếu). Không refactor ngoài phạm vi.

## Test bắt buộc — `tests/test_ab_eval.py`

Không cần torch/CUDA thật. Dùng stub:

```python
class FakeCudaTensor:
    """Giả lập tensor CUDA: chỉ .detach().cpu().numpy() mới dùng được."""
    def __init__(self, arr): self._arr = arr
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self._arr
    def __array__(self, *a, **k):
        raise TypeError("can't convert cuda:0 device type tensor to numpy")
```

Các case:

1. `gt_labels_3d = [FakeCudaTensor(np.array([1, 2]))]`, `gt_bboxes_3d = [FakeBoxes(...)]` → trả đúng shape `(2,)` dtype int, **không** raise.
2. `gt_labels_3d` là tensor giả trực tiếp (không list) → vẫn đúng như cũ (không regress).
3. Box rỗng: `gt_labels_3d = [FakeCudaTensor(np.array([]))]` và boxes rỗng → `(0,7)` và `(0,)`.
4. Box là `np.ndarray` thuần → đi qua không đổi.
5. Nếu helper `_to_numpy` được tách ra: test riêng nó với cả 5 dạng trên.

Test phải **đỏ trước khi sửa** (chạy `pytest -q tests/test_ab_eval.py` trên code cũ để chứng minh), rồi xanh sau khi sửa. Ghi lại việc đó trong commit message bằng một dòng.

## Nghiệm thu

```
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/pytest -q tests/
```

phải xanh toàn bộ (hiện **187 passed, 4 skipped**). Commit một lần:

```
fix(11-g): handle CUDA/list gt tensors in ab_eval _batch_gt
```

Không sửa `task_args.txt`, không sửa `kernel-metadata.json`, không push Kaggle.