# Ticket 09-ii — đẩy lên Kaggle, chờ, tải log (không sửa logic)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `2826f06` · tree sạch.
Code đã xong: `tests/test_pipeline_e2e.py` (4 test, local **63 passed, 4 skipped**). Việc của bạn là **chạy nó
trong kernel thật** và mang log về.

## Việc phải làm (đúng thứ tự, foreground, KHÔNG bật background/poller)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/e2e
```

Rồi chờ (một lệnh duy nhất, tối đa ~15 phút; kernel bình thường 9 phút):

```bash
for i in $(seq 1 30); do
  s=$(kaggle kernels status nguynhuy9669/bevfusion-e2e)
  echo "$i $s"
  case "$s" in *COMPLETE*|*ERROR*|*FAILED*|*CANCEL*) break;; esac
  sleep 30
done
```

Nếu sau 15 phút chưa xong: chạy lại đúng vòng lặp đó **một lần nữa** (đừng kill gì).

Tải log:

```bash
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9
ls -la /tmp/k9 && grep -n "pytest summary\|E2E_OK\|FAILED\|Error" /tmp/k9/*.log | tail -20
```

## Cần báo về (dán nguyên văn, không diễn giải)

1. Dòng `pytest summary: ...` (kỳ vọng `rc=0 passed=67`; 63 + 4 test mới).
2. `E2E_OK` có hay không.
3. Nếu FAILED: **40 dòng cuối của traceback** + tên test fail.
4. `n_injected` của 3 arm nếu log có in (test không bắt buộc in — nếu không có thì ghi "không có trong log").

## Được sửa gì, không được sửa gì

- **Được** sửa **1 lần** nếu fail vì lý do môi trường/đường dẫn (thiếu import, sai path config, `KeyError` do
  `DataContainer`, `cfg.object_classes` không tồn tại) — sửa tối thiểu trong `tests/test_pipeline_e2e.py`,
  chạy lại local (63 passed, 4 skipped), push lại lần 2, rồi báo.
- **KHÔNG được** nới assert, xoá test, `pytest.skip` thêm, hay sửa `spray/**`, `mit/**`, `kaggle/**`.
  Nếu fail vì bản chất (ví dụ `points_clean` mất trong batch, matrix khác nhau) ⇒ **DỪNG**, báo PM.
- Tối đa **2 lần push kernel**.

## Kết thúc

Nếu có sửa file test: commit `test(e2e): fix kernel-side wiring for pipeline e2e` và dán `git log --oneline -1`.
Nếu không sửa gì: chỉ báo số, không commit.