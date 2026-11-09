# Ticket 09-iv — sửa skip âm thầm, đăng ký pipeline KHÔNG cần nuscenes-devkit

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `8c135dc` · 1 lần push cuối.

## Run 3 "xanh" là xanh giả — bằng chứng

Log `/tmp/k9run3/bevfusion-e2e.log`:

```
63 passed, 4 skipped, 1 warning in 9.52s
pytest summary: rc=0 passed=63 failed=0 errors=0
E2E_OK
```

**4 test e2e bị SKIP**, nên `E2E_OK` không chứng minh gì. Nguyên nhân: dòng `import mmdet3d.datasets`
vừa thêm chạy `mmdet3d/datasets/__init__.py`, mà file đó import `.nuscenes_dataset` →
`from nuscenes.utils.data_classes import Box` (nuscenes-devkit không có trong kernel). Import ném lỗi,
rơi vào `except ImportError` bao trùm cả khối ⇒ `mmcv = None` ⇒ `pytestmark` skip cả 4 test.

## Việc phải làm — chỉ `tests/test_pipeline_e2e.py`

### 1. Đăng ký pipeline mà không kích hoạt `mmdet3d.datasets.__init__`

```python
def _register_mmdet3d_pipelines():
    """Register mmdet3d transforms without importing mmdet3d.datasets.__init__.

    The package __init__ pulls ``.nuscenes_dataset`` which needs nuscenes-devkit;
    that dependency is absent in the pinned kernel, but the pipeline modules only
    need mmcv + mmdet + mmdet3d.core.
    """
    import importlib
    import os as _os
    import sys
    import types

    import mmdet3d

    if "mmdet3d.datasets" not in sys.modules:
        pkg = types.ModuleType("mmdet3d.datasets")
        pkg.__path__ = [_os.path.join(_os.path.dirname(mmdet3d.__file__), "datasets")]
        sys.modules["mmdet3d.datasets"] = pkg
    importlib.import_module("mmdet3d.datasets.pipelines.transforms_3d")
```

### 2. Tách "thiếu thư viện" khỏi "đăng ký hỏng" — không bao giờ skip âm thầm nữa

```python
try:
    import mmcv
    from mmdet.datasets.builder import PIPELINES
    from mmdet3d.core import LiDARInstance3DBoxes
    from mmdet3d.core.points import LiDARPoints
except ImportError:
    mmcv = PIPELINES = LiDARInstance3DBoxes = LiDARPoints = None

REGISTRATION_ERROR = None
if mmcv is not None:
    try:
        _register_mmdet3d_pipelines()
    except Exception as exc:  # noqa: BLE001 - surface it, never swallow
        REGISTRATION_ERROR = exc

pytestmark = pytest.mark.skipif(
    mmcv is None,
    reason="mmcv/mmdet3d core not installed (laptop); the e2e test runs in the pinned kernel",
)
```

Và ở **đầu mỗi test** (trước `_load_config()`):

```python
if REGISTRATION_ERROR is not None:
    pytest.fail(f"mmdet3d pipeline registration failed: {REGISTRATION_ERROR!r}")
assert "GlobalRotScaleTrans" in PIPELINES, "mmdet3d transforms were not registered"
```

⇒ Trong kernel, nếu đăng ký hỏng thì **fail**, không còn `4 skipped` giả.

### 3. Không sửa gì khác

Không nới assert, không bỏ test, không đổi `spray/**`, `mit/**`, `kaggle/**`.

## Verify local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/    # 63 passed, 4 skipped (đúng: laptop)
```

## Push lần 4 (lần cuối)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/e2e
for i in $(seq 1 30); do s=$(kaggle kernels status nguynhuy9669/bevfusion-e2e); echo "$i $s"; case "$s" in *COMPLETE*|*ERROR*|*FAILED*|*CANCEL*) break;; esac; sleep 30; done
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9run4
grep -n "passed\|failed\|skipped\|FAILED tests\|E2E_OK\|E2E_FAILED" /tmp/k9run4/*.log | tail -20
```

## Điều kiện ĐẠT — kiểm bằng mắt, đừng suy ra từ `E2E_OK`

Log phải có **đồng thời**:

1. dòng `67 passed` (63 + 4), và
2. **KHÔNG** có chữ `skipped` trong dòng tổng kết pytest, và
3. `E2E_OK`.

Nếu vẫn ra `4 skipped` ⇒ in dòng `reason` (chạy `pytest -q tests/test_pipeline_e2e.py -rs`) và **DỪNG**, báo PM.

## Commit

`test(e2e): register mmdet3d transforms without nuscenes-devkit` — dán `git log --oneline -1`.
Báo: 3 dòng log ở mục "Điều kiện ĐẠT" + nếu fail thì 30 dòng traceback cuối.