# Ticket 10-i — config A/B + freeze list (không cần GPU)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `50454ac` · **không đụng Kaggle**, ~35 turn.
Test chuẩn: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` (đang **64 passed, 4 skipped**).

## Mục tiêu

Hai arm chỉ khác nhau **đúng một chỗ**: arm B chèn `PlumeTransform` vào `train_pipeline`, arm A không.
Mọi thứ khác (seed, batch, lr, optimizer, thứ tự dữ liệu, số update, freeze list) phải **giống tuyệt đối**,
và phải chứng minh bằng test chứ không bằng lời.

## File 1 — `spray/config_merge.py` (mới)

```python
PLACEHOLDER = ...  # regex ^\$\{([^}]+)\}$

def load_yaml(path) -> dict          # yaml.safe_load
def lookup(roots, path) -> Any       # "augment3d.rotate", "augment2d.resize[0]"
def resolve(node, roots)             # thay ${...} đệ quy; raise KeyError nếu không tìm thấy
def merge(base: dict, override: dict) -> dict   # deep merge, override thắng
def diff_paths(a, b, prefix="") -> list[str]    # đường dẫn dotted nơi a và b khác nhau
```

Yêu cầu: không import `mmcv` ở module level (laptop phải dùng được). `resolve` phải raise khi gặp
placeholder không giải được — **không** im lặng giữ nguyên chuỗi.

## File 2 — `spray/ab_config.py` (mới)

Hằng số:

```python
CONFIG_DIR = pathlib.Path("mit/bevfusion/configs/nuscenes")
DATASET_CONFIG = CONFIG_DIR / "default.yaml"
MODEL_CONFIG = CONFIG_DIR / "det/transfusion/secfpn/camera+lidar/swint_v0p075/default.yaml"
SPRAY_CONFIG = pathlib.Path("spray/config/plume_default.yaml")   # xem File 4

KEEP_STEPS = ("GlobalRotScaleTrans", "RandomFlip3D", "PointsRangeFilter", "ObjectRangeFilter", "PointShuffle")

TRAIN_SPEC = dict(          # [CHỌN] — giống hệt cho cả hai arm
    seed=0,
    batch_size=2,
    lr=1e-4,
    weight_decay=0.01,
    optimizer="AdamW",
    max_iters=2000,
    warmup_iters=100,
    grad_clip=5.0,
    eval_every=500,
)
```

API:

```python
def train_pipeline(arm: str) -> list[dict]   # arm in ("A", "B")
def build_cfg(arm: str) -> dict
def diff_paths(a, b) -> list[str]            # re-export từ config_merge
```

`train_pipeline("A")`: load `DATASET_CONFIG`, resolve placeholder, lọc đúng 5 bước theo `KEEP_STEPS`
(giữ nguyên thứ tự trong config, giữ nguyên tham số).

`train_pipeline("B")`: như A nhưng chèn **sau `RandomFlip3D`, trước `PointsRangeFilter`**:

```python
{"type": "PlumeTransform", "enabled": True, "seed": 0,
 "config": <dict tham số plume từ spray/config/plume_default.yaml>}
```

và thay `DefaultFormatBundle3D` → `CleanPointsFormatBundle3D`, `Collect3D` → `CleanPointsCollect3D`
(cả hai arm đều dùng bản `Clean*`, để khác biệt A/B **chỉ** là sự có mặt của `PlumeTransform`).

`build_cfg(arm)` trả dict thuần (JSON-được):

```python
{"arm": arm, "train_spec": TRAIN_SPEC, "model_config": str(MODEL_CONFIG),
 "train_pipeline": train_pipeline(arm), "spray": SPRAY_PARAMS if arm == "B" else None}
```

## File 3 — `spray/freeze.py` (mới)

Freeze theo **tên tham số** (không theo attribute, để không vỡ khi vendor đổi cấu trúc):

```python
FROZEN_PREFIXES = ("img_backbone.", "img_neck.", "encoders.camera.")   # [CHỌN] nhánh camera đóng băng
FROZEN_SUBSTRINGS = ("vtransform.",)                                   # phòng khi prefix khác

def is_frozen(name: str) -> bool
def apply_freeze(module, frozen_prefixes=FROZEN_PREFIXES, frozen_substrings=FROZEN_SUBSTRINGS) -> dict
```

`apply_freeze` set `requires_grad=False` cho tham số khớp, trả:

```python
{"n_total_params": int, "n_trainable_params": int,
 "trainable_names": [...], "frozen_names": [...], "unmatched": [...]}
```

- `unmatched` = tham số **không** khớp prefix nào trong danh sách "mở" — hãy định nghĩa `TRAINABLE_PREFIXES`
  (`pts_voxel_encoder.`, `pts_middle_encoder.`, `pts_backbone.`, `pts_neck.`, `encoders.lidar.`, `fuser.`,
  `decoder.`, `heads.`) và đưa tên lạ vào `unmatched`. Mục đích: kernel in ra để PM thấy ngay nếu vendor
  đổi tên. Không raise.
- Phải chạy được trên module giả (`torch.nn.Module` với các submodule cùng tên) — không cần mmdet3d.

## File 4 — `spray/config/plume_default.yaml` (mới)

Chép **nguyên** giá trị đang dùng trong `spray/plume.py::PlumeConfig` (đọc code, không tự đặt số mới):
`water_film_height_m: 0.001`, `min_speed_kmh: 50` (nếu `PlumeConfig` dùng km/h thì ghi km/h), trần bán kính
`(0.10, 1.00)`, `radial_squash: 0.885`, `points_per_cluster_median`, `cluster_radius_median_m: 0.30`,
`max_points_per_frame: 2000`, attenuation… **Nếu field nào không tồn tại thì bỏ, không bịa.**
Thêm test: `PlumeConfig(**yaml.safe_load(...))` dựng được, và mọi key trong yaml đều là field của `PlumeConfig`.

## Test bắt buộc

`tests/test_config_merge.py`:
1. `resolve` xử lý `${a}`, `${a.b}`, `${a[1]}`; raise `KeyError` khi thiếu.
2. `merge` deep, override thắng, không mutate input.
3. `diff_paths` trả đúng đường dẫn khi lồng nhau.

`tests/test_ab_config.py` — **đây là test quan trọng nhất của ticket**:
1. `diff_paths(build_cfg("A"), build_cfg("B"))` **chỉ** nằm trong `train_pipeline` hoặc key `spray`.
   Nếu lộ ra `train_spec.*` ⇒ FAIL (nghĩa là hai arm khác ngân sách).
2. `build_cfg("A")["train_spec"] == build_cfg("B")["train_spec"]`.
3. `train_pipeline("A")` **không** có `PlumeTransform`; `train_pipeline("B")` có đúng **1**, và vị trí của nó
   nằm ngay sau `RandomFlip3D` (index của `PlumeTransform` = index của `RandomFlip3D` + 1).
4. Cả hai arm: 5 bước gốc có mặt, đúng thứ tự; không còn chuỗi nào chứa `${`.
5. `build_cfg(arm)` là JSON-serializable (`json.dumps` không lỗi).

`tests/test_freeze.py`:
1. Module giả có `img_backbone`, `img_neck`, `encoders.camera`, `encoders.lidar`, `fuser`, `heads` →
   sau `apply_freeze` chỉ camera frozen; `n_trainable_params` đúng số kỳ vọng (tự tính trong test).
2. `unmatched` rỗng với module giả; thêm 1 tham số lạ → nó xuất hiện trong `unmatched`.
3. Gọi 2 lần không đổi kết quả (idempotent).

`tests/test_plume_config_yaml.py`: như mục File 4.

## Ràng buộc

- Chỉ tạo/sửa: `spray/config_merge.py`, `spray/ab_config.py`, `spray/freeze.py`, `spray/config/plume_default.yaml`,
  4 file test trên. **Không** sửa `spray/plume.py`, `tests/test_pipeline_e2e.py`, `mit/**`, `kaggle/**`.
- Không thêm dependency mới (`yaml`, `torch` đã có).
- Không đổi bất kỳ tham số nào của `PlumeConfig`.

## Xong

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/   # phải ≥70 passed, 4 skipped
git add -A && git commit -m "feat(ab): freeze list and A/B config builder with only-spray diff"
git log --oneline -1
```

Báo: số test passed/skipped, `git log -1`, và dán output `diff_paths(build_cfg("A"), build_cfg("B"))`.