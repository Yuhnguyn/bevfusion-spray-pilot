# Ticket 26: `PlumeContext` + state theo scene — hợp đồng dữ liệu cho generator v2

HEAD: 8c0ef3e  Nhánh: main
Skill: tdd — `/Users/huynguyen/.agents/skills/tdd` (1 skill duy nhất)

Ticket gốc: `.scratch/spray-augmentation/issues/26-plume-context-contract.md` — đọc trước.
Đặc tả: `.scratch/spray-augmentation/spec-v2-paper-faithful.md` §2 (hợp đồng dữ liệu) và §1 (`wfh` = **mm**).
Số đo nền: `docs/plume-v2-measurements.md` (ticket 25, xong).

## Hiện trạng (PM đã kiểm)

- `spray/plume_transform.py:37` — `class PlumeTransform`, `__init__(config, enabled=True, seed=0, **kwargs)`,
  `__call__(results: dict) -> dict`, đọc `results["points"]`, `results.get("gt_bboxes_3d")`,
  `results.get("metadata")["token"]`. **Chưa có** context/ego_pose/road_z/elevation.
- `spray/plume.py:187` — `inject_plume(points, boxes, *, seed, token="", config=None) -> PlumeResult`.
  Chữ ký này **không được đổi** (caller hiện có trong pipeline + test).
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **192 passed, 4 skipped**.
- Năm phát hiện của ticket 25 **ràng buộc hợp đồng này** (đọc `issues/25-measure-zero-gpu.md` §PM):
  1. `poses.txt` của SemanticSpray **không có tịnh tiến** → không suy được ego speed từ quỹ đạo ở nguồn đó.
  2. `object_velocity == ego_velocity` 207/207 scene ⇒ phải giữ **hai** trường tốc độ riêng, không gộp.
  3. Box thật chỉ có ở **36/207 scene** ⇒ `boxes` là optional, `None` là hợp lệ.
  4. Ring id **không** dùng được làm elevation (lệch median 3,49° so với bảng VLP-32C) ⇒ phải tính
     elevation từ toạ độ điểm.
  5. `z` mặt đường **khác nhau theo dataset** (`−0,411 m` SemanticSpray, `−1,84 m` nuScenes) ⇒ không hardcode.

## Nguyên nhân gốc

`inject_plume()` nhận `(points, boxes)` nên bước 3–5 của v2 (ray casting, lifetime, attenuation) không có
nguồn cho `ego_pose`, gốc tia, elevation, tốc độ, `wfh`, `frame_index`, `epoch` — và không tái lập được seed
theo scene. Không có hợp đồng dữ liệu thì không viết được bước nào trong 28–30.

## Việc phải làm

### 1. `spray/plume_context.py` (file mới)

`@dataclass(frozen=True) class PlumeContext` với **đúng** các trường sau; sai kiểu/thiếu → raise.

| Trường | Kiểu | Bắt buộc | Ràng buộc |
|---|---|---|---|
| `scene_token` | `str` | có | không rỗng |
| `frame_index` | `int` | có | ≥ 0 |
| `epoch` | `int` | có | ≥ 0 — dùng cho seed |
| `sensor_origin` | `np.ndarray (3,)` float64 | có | finite |
| `ego_speed_mps` | `float` | có | ≥ 0, finite |
| `object_speed_mps` | `float` | có | ≥ 0, finite — **riêng**, không suy từ ego |
| `wfh_mm` | `float` | có | `0 < wfh_mm <= 1.2` (**mm**, không phải mét) |
| `road_z_m` | `float` | có | finite — `z` mặt đường của **dataset đang augment**, không hardcode |
| `ego_pose` | `np.ndarray (4,4)` hoặc `None` | không | nếu có: 3×3 là rotation trực giao (`|R·Rᵀ−I| < 1e-6`) |
| `elevation_angles_deg` | `np.ndarray (32,)` hoặc `None` | không | nếu `None` ⇒ transform **tự tính** elevation từ toạ độ điểm |
| `boxes` | `np.ndarray (M,9)` hoặc `None` | không | `None` = đường sinh từ `metadata.txt` (hướng c (c)) |

- `PlumeContextError(ValueError)` — message phải **nêu tên trường** vi phạm (test bắt chuỗi này).
- `from_sample(sample: dict, *, epoch: int, wfh_mm: float, road_z_m: float, frame_index: int) -> PlumeContext`:
  đọc dict sample kiểu nuScenes/mmdet3d (`ego2global` **hoặc** `ego_pose`, `scene_token`, `timestamp`,
  `sensor_origin`/`lidar2ego` nếu có, `gt_bboxes_3d` nếu có). **Không có default cho `wfh_mm` và `road_z_m`** —
  đây là hai số phải truyền vào, cấm tự bịa. Thiếu key bắt buộc ⇒ raise `PlumeContextError` liệt kê **tất cả**
  key thiếu, sắp xếp alphabet.
- Tốc độ: `from_sample` **không** tự suy `ego_speed_mps` từ hiệu toạ độ ego (nuScenes mini chạy keyframe-only,
  khoảng cách keyframe 0,5 s nên suy ra vẫn được, nhưng phát hiện #1 nói nguồn khác có thể không có tịnh tiến).
  Cho phép override qua tham số `ego_speed_mps=None`; nếu `None` **và** sample không có trường tốc độ ⇒ raise.
- `seed_for(scene_token, frame_index, epoch, base_seed=0) -> int`: hàm thuần, tất định; cùng input → cùng seed;
  đổi `epoch` → seed khác. Dùng `hashlib` (không dùng `hash()` của Python vì bị randomize theo process).

### 2. `spray/plume_transform.py`

- `PlumeTransform.set_epoch(epoch: int) -> None` — lưu epoch, dùng cho seed.
- `__call__(results)` nhận `results["plume_context"]` (kiểu `PlumeContext`) nếu có:
  - có context ⇒ seed = `seed_for(context.scene_token, context.frame_index, context.epoch, self.seed)`;
    vẫn gọi `inject_plume(points, boxes, seed=..., token=..., config=...)` — **không đổi chữ ký** hàm đó.
  - không có context ⇒ **hành vi y hệt hiện tại** (đường cũ, không đổi một bit nào).
- Không đọc `os.environ`, không đọc file config mới, không thêm tham số vào `PlumeConfig`.

### 3. `tests/test_plume_context.py` (file mới) — 6 test, viết **trước** khi code

1. Dựng `PlumeContext` đủ trường → các trường giữ nguyên giá trị (kể cả `wfh_mm`).
2. Thiếu `scene_token` trong `from_sample` → `PlumeContextError`, message chứa `"scene_token"`.
3. `results` **không** có `plume_context` → kết quả `points` **giống hệt** gọi `inject_plume` trực tiếp
   (so sánh `np.array_equal`), tức đường cũ không đổi.
4. `seed_for` đổi theo `epoch`: cùng scene/frame, `epoch=0` và `epoch=1` → seed khác; gọi lại `epoch=0` → seed cũ.
5. `wfh_mm = 0` và `wfh_mm = 1.3` → `PlumeContextError`; `road_z_m = nan` → `PlumeContextError`.
6. `elevation_angles_deg = None` → helper tính elevation từ `points (N,5)` chạy được, trả mảng độ dài `N`,
   và giá trị khớp `np.degrees(np.arctan2(z, hypot(x, y)))`.

Đặt helper `compute_elevation_deg(points)` trong `spray/plume_context.py` (thuần numpy, không import `spray.plume`).

## Tiêu chí nghiệm thu

- [ ] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥ 198 passed, 4 skipped**
      (192 cũ + 6 mới; **không** skip mới). Nêu số thật vào báo cáo.
- [ ] `grep -c "PlumeContext" spray/plume_context.py spray/plume_transform.py` > 0 ở cả hai file.
- [ ] Đường cũ: test #3 xanh, và `inject_plume` **không đổi chữ ký** (`git diff spray/plume.py` rỗng).
- [ ] Chỉ 3 file mới/đổi: `spray/plume_context.py`, `spray/plume_transform.py`, `tests/test_plume_context.py`.
- [ ] Không có `os.environ`, không hardcode `-0.411` hay `-1.84`, không dùng cột 4 (ring) làm elevation.

## Cấm

- Không sửa `spray/plume.py`, `spray/config/*.yaml`, `kaggle/`, `proxy_eval/`, `mit/`, `tests/` (trừ file test mới).
- Không đổi chữ ký `inject_plume()` hay `PlumeConfig`.
- Không refactor ngoài phạm vi; không thêm dependency (chỉ `numpy` + stdlib).
- Không tự commit; PM nghiệm thu rồi commit.