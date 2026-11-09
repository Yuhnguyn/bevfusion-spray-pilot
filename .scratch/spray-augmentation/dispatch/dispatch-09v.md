# Ticket 09-v — resolve `${...}` của config, lấy point_cloud_range từ config

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `0d129e4` · push lần 5 (cuối).

## Run 4 đã đúng hướng — test chạy thật, còn 1 lỗi

Log `/tmp/k9run4/bevfusion-e2e.log`:

```
3 failed, 64 passed, 1 warning in 9.80s
E   ValueError: PointsRangeFilter: could not convert string to float: '${point_cloud_range}'
pytest summary: rc=1 passed=64 failed=3 errors=0
```

Đăng ký pipeline đã chạy (test 4 pass). Lỗi còn lại: `configs/nuscenes/default.yaml` dùng nội suy `${...}`
của mmcv, nhưng khi ta bê nguyên dict bước ra khỏi file thì placeholder **chưa được thay**. Và
`points_range_filter`/`object_range_filter` nhận `point_cloud_range` ở dạng chuỗi ⇒ `ValueError`.

Đồng thời phát hiện: `point_cloud_range` trong **dataset config là `[-51.2, -51.2, -5.0, 51.2, 51.2, 3.0]`**
(không phải `[-54, …]` như brief trước tôi ghi — `-54` là của model config). Test phải lấy từ config, không
hardcode.

## Việc phải làm — chỉ `tests/test_pipeline_e2e.py`

### 1. Tự resolve placeholder (không phụ thuộc mmcv interpolation)

Thêm 2 helper thuần Python (chạy được cả trên laptop):

```python
import re

_PLACEHOLDER = re.compile(r"^\$\{([^}]+)\}$")


def _lookup(roots, path):
    """Đi theo đường dẫn kiểu ``augment3d.rotate`` hoặc ``augment2d.resize[0]``."""
    cur = roots
    for part in path.split("."):
        match = re.match(r"^(\w+)((?:\[\d+\])*)$", part)
        key, index = match.group(1), match.group(2)
        cur = cur[key]
        for i in re.findall(r"\[(\d+)\]", index):
            cur = cur[int(i)]
    return cur


def _resolve(node, roots):
    """Thay mọi chuỗi dạng ``${đường.dẫn}`` bằng giá trị thật trong ``roots``."""
    if isinstance(node, dict):
        return {k: _resolve(v, roots) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, roots) for v in node]
    if isinstance(node, str):
        match = _PLACEHOLDER.match(node.strip())
        if match:
            return _resolve(_lookup(roots, match.group(1)), roots)
    return node
```

### 2. Đọc config bằng `yaml.safe_load`, resolve rồi mới dựng bước

```python
import yaml

def _load_raw_config():
    if not os.path.exists(CONFIG_PATH):
        pytest.skip(f"kernel clone not present: {CONFIG_PATH}")
    with open(CONFIG_PATH) as handle:
        return yaml.safe_load(handle)
```

- `POINT_CLOUD_RANGE` **lấy từ config**, không hardcode:
  `POINT_CLOUD_RANGE = tuple(_load_raw_config()["point_cloud_range"])` — nhưng phải dùng trong `_sample()`,
  nên gọi trong `_sample()` hoặc truyền vào; đừng gọi ở module level (module level phải không đọc file).
- `steps = _resolve(raw["train_pipeline"], raw)`, giữ danh sách trắng 5 bước như cũ.
- Sau khi resolve, **assert không còn chuỗi nào chứa `${`** trong các bước đã chọn (nếu còn ⇒ fail, đừng build).

### 3. Thêm 1 test chạy được trên laptop (không cần mmcv)

```python
def test_resolve_placeholders():
    roots = {"a": [1.0, 2.0], "b": {"c": 3}, "steps": [{"v": "${a}"}, {"w": "${b.c}"}, {"u": "${a[1]}"}]}
    assert _resolve(roots["steps"], roots) == [{"v": [1.0, 2.0]}, {"w": 3}, {"u": 2.0}]
```

Test này **không** bị `pytestmark` skip — đặt nó trong file này nhưng phải chạy được khi không có mmcv.
Muốn vậy: khai báo `pytestmark` thành `skipif` chỉ cho 4 test e2e, dùng **decorator riêng** cho 4 test đó
(hoặc đặt test resolver ở file khác: `tests/test_e2e_config_resolve.py` — cách này gọn hơn, **ưu tiên cách này**).

## Verify local

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/    # 64 passed, 4 skipped
```

## Push lần 5 (cuối) + điều kiện ĐẠT

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/e2e
for i in $(seq 1 30); do s=$(kaggle kernels status nguynhuy9669/bevfusion-e2e); echo "$i $s"; case "$s" in *COMPLETE*|*ERROR*|*FAILED*|*CANCEL*) break;; esac; sleep 30; done
kaggle kernels output nguynhuy9669/bevfusion-e2e -p /tmp/k9run5
grep -n "passed\|skipped\|FAILED tests\|E2E_OK\|E2E_FAILED" /tmp/k9run5/*.log | tail -20
```

ĐẠT khi log có **`68 passed`** (63 + 4 e2e + 1 resolver) và **không** có chữ `skipped`, và có `E2E_OK`.

Nếu vẫn fail: dán 30 dòng traceback cuối + `pytest --collect-only -q tests/test_pipeline_e2e.py` và **DỪNG**.

## Ràng buộc

- Chỉ sửa/tạo file test. Không đụng `spray/**`, `mit/**`, `kaggle/**`, `scripts/**`.
- Không nới assert cũ. Không thêm dependency (yaml có sẵn).

## Commit

`test(e2e): resolve config placeholders and read the cloud range from the config`