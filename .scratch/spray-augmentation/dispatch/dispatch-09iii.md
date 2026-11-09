# Ticket 09-iii — sửa 2 dòng đăng ký registry rồi push lần 3

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `93d160e` · không đọc vendor, không thám hiểm.

## Chẩn đoán (PM đã đọc log kernel, không phải phỏng đoán)

Run 2 (`/tmp/k9/v4/bevfusion-e2e.log`) fail **cả 4 test** với:

```
KeyError: 'GlobalRotScaleTrans is not in the pipeline registry'
pytest summary: rc=1 passed=63 failed=4 errors=0
```

Nguyên nhân: `PIPELINES` của mmdet chỉ có `CleanPointsFormatBundle3D` / `CleanPointsCollect3D` (do
`spray.pipeline.install()` đăng ký) và vài class của mmdet; **không có transform nào của mmdet3d**, vì
`mmdet3d/datasets/pipelines/transforms_3d.py` chỉ được import khi `mmdet3d.datasets` được import. Test hiện chỉ
import `mmdet3d.core`, nên registry rỗng.

Đã xác minh trong clone: `mit/bevfusion/mmdet3d/datasets/__init__.py:6` có `from .pipelines import *`, và
`transforms_3d.py:124` đăng ký `GlobalRotScaleTrans`.

## Việc phải làm — CHỈ trong `tests/test_pipeline_e2e.py`

1. Trong khối `try:` ở đầu file, thêm **một dòng** để đăng ký pipeline của mmdet3d:

```python
import mmdet3d.datasets  # noqa: F401  (registers mmdet3d transforms into PIPELINES)
```

đặt **trước** `from mmdet3d.core import LiDARInstance3DBoxes`. Nếu vì lý do nào đó import này lỗi, thêm
`import mmdet3d.datasets.pipelines` làm phương án hai — nhưng **chỉ một** trong hai, đừng cả hai.

2. Không sửa gì khác. Không nới assert. Không skip thêm. Không sửa `spray/**`, `mit/**`, `kaggle/**`.

## Chạy local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/   # 63 passed, 4 skipped
```

## Push lần 3 (đây là lần cuối được phép)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/e2e
for i in $(seq 1 30); do
  s=$(kaggle kernels status nguynhuy9669/bevfusion-e2e); echo "$i $s"
  case "$s" in *COMPLETE*|*ERROR*|*FAILED*|*CANCEL*) break;; esac
  sleep 30
done
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9run3
grep -n "pytest summary\|FAILED tests\|E2E_OK\|E2E_FAILED" /tmp/k9run3/*.log | tail -20
```

## Báo cáo (nguyên văn)

- `pytest summary: ...` + `E2E_OK` / `E2E_FAILED`.
- Nếu fail: dòng `FAILED tests/...` + **30 dòng traceback cuối**, và **DỪNG** (không sửa tiếp, không push lần 4).
- Local pytest 1 dòng cuối.

## Commit

Nếu có sửa file: `test(e2e): register mmdet3d pipelines before building the chain`. Dán `git log --oneline -1`.