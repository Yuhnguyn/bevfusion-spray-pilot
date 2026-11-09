# 11-c1-fix: chọn loss không được cộng trùng

HEAD: 11-c1 chưa commit (working tree)  Nhánh: main
Skill: tdd (/Users/huynguyen/.agents/skills/tdd/SKILL.md)

## Vấn đề

`kaggle/train/ab_run.py:200-207` cộng **mọi** key có chữ `loss`:

```python
terms = [value for name, value in losses.items() if "loss" in name and torch.is_tensor(value)]
loss = sum(terms)
```

Nhiều head của mmdet3d trả **cả** `loss` (đã là tổng) **và** các thành phần `loss_cls`, `loss_bbox`, `loss_dir`. Khi đó `loss` bị tính **2 lần** ⇒ gradient lớn gấp đôi, clip 5.0 cắt lệch, và A/B vẫn "chạy được" nên lỗi im lặng.

## Việc phải làm

1. Tách hàm thuần, không import torch:

```python
def loss_keys(losses):
    """Key dùng để tính loss: 'loss' nếu có, ngược lại mọi key chứa 'loss'."""
```

   - Nếu `"loss" in losses` ⇒ trả `["loss"]` (không cộng thêm thành phần).
   - Ngược lại ⇒ trả các key chứa `"loss"`, giữ thứ tự `sorted()` cho tất định.
   - Không có key nào ⇒ trả `[]`.

2. `train_arm` dùng `loss_keys`, giữ nguyên `fail("no_loss", ...)` khi rỗng, và log tên key đã dùng **một lần** ở dòng `AB_STEP` đầu tiên (hoặc `AB_INFO loss_keys=...`) để log chứng minh không cộng trùng.

3. Test trong `tests/test_ab_run.py`:
   - `{"loss": 1.0, "loss_cls": 0.6, "loss_bbox": 0.4}` ⇒ `["loss"]`.
   - `{"loss_cls": .6, "loss_bbox": .4}` ⇒ `["loss_bbox", "loss_cls"]`.
   - `{"acc": 1.0}` ⇒ `[]`.
   - Không test nào cần torch/GPU.

## Cấm

- Không đổi công thức, optimizer, lr, steps, seed, `sweeps_num`.
- Không sửa `smoke.py`, `main.py`, `mit/`, `third_party/`.
- Không commit, không push kernel.

## Nghiệm thu PM

```bash
pytest -q tests/            # phải vẫn 141 passed + test mới
git diff --stat kaggle/train/ab_run.py
```