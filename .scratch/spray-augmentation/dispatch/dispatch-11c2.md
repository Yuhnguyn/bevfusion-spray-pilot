# 11-c2: eval set 196 frame + bootstrap theo scene (thuần Python, test local)

HEAD: (chờ 11-c1)  Nhánh: main
Skill: tdd (/Users/huynguyen/.agents/skills/tdd/SKILL.md)

## Mục tiêu

Chuẩn bị hai mảnh để kernel eval chấm được A/B, cả hai **test được trên máy local không cần GPU/dataset**:

1. `scripts/make_eval_split.py` — chọn đúng eval set đã chốt: **val split, box phương tiện ≥50 km/h, `d ≤ 50 m` ⇒ 196 frame / 16 scene**.
2. `proxy_eval/bootstrap.py` — paired bootstrap theo scene, tính `G = mAP_clean − mAP_spray` cho từng arm và delta A/B.

## 1. `scripts/make_eval_split.py`

Định nghĩa phải khớp tuyệt đối với lần scan đã có (`kaggle/smoke_test/evidence/eligibility.json`, `definition` + `frames`):

- `split == val` (`nuscenes.utils.splits.val`, 150 scene).
- Box thuộc lớp phương tiện: `bicycle, bus, car, construction_vehicle, motorcycle, trailer, truck`.
- `speed_kmh = ||box_velocity|| * 3.6 ≥ 50`.
- `d_m` = khoảng cách BEV nhỏ nhất từ origin `LIDAR_TOP` tới 4 góc footprint, trong hệ LiDAR; chỉ xét box có `x > 0` (phía trước).
- `d_m ≤ 50`.

Hai chế độ:

```
python scripts/make_eval_split.py --dataroot PATH --out /kaggle/working/eval_196.json [--check 196,16]
python scripts/make_eval_split.py --selftest
```

- Chế độ thật: dùng `nuscenes-devkit` đã cài trong venv, chỉ load 150 scene val (không quét toàn bộ 28k keyframe), ghi json:
  `{"frames": [{"sample_token": …, "scene_token": …, "scene": …, "n_eligible": …}], "expected": {"frames": 196, "scenes": 16}, "got": {...}}`
- Log marker: `EVAL_SET_OK frames=196 scenes=16`; nếu lệch: `EVAL_SET_FAILED expected=196,16 got=<n>,<m>` và `sys.exit(1)`.
- `--selftest`: kiểm tra hàm lọc thuần (không cần devkit) trên box tổng hợp — biên `speed=49.9/50.0`, `d=50.0/50.1`, `x=-0.1` bị loại, lớp `pedestrian` bị loại.

Phần thuần phải tách khỏi phần devkit để test được: `eligible(boxes)`, `frame_distance(corners, origin)`, `select_frames(records)`.

## 2. `proxy_eval/bootstrap.py`

```python
def per_scene_metric(frames, metric) -> dict[str, float]   # gộp frame → scene (mean)
def paired_delta(a: dict, b: dict) -> dict[str, float]      # a − b theo từng scene chung
def scene_bootstrap(deltas, n=2000, seed=0, alpha=0.05) -> dict   # resample scene, trả mean/lo/hi
```

Yêu cầu:

- Chỉ dựa trên `numpy`, không import torch/devkit.
- `paired_delta` chỉ lấy scene có ở **cả hai** phía; log/raise nếu `len(common) < 8` (eval set chỉ 16 scene, phải biết khi mẫu quá nhỏ).
- `scene_bootstrap`: resample **scene** (không resample frame) — đúng đơn vị thống kê; trả `{"mean", "lo", "hi", "n_scenes", "n_resamples"}`.
- Deterministic theo `seed`.

## 3. Test bắt buộc (`tests/test_eval_split.py`, `tests/test_bootstrap.py`)

- Biên speed/d/x như trên, `pedestrian` bị loại.
- `select_frames` trên danh sách giả trả đúng số frame và scene.
- `per_scene_metric` gộp đúng (2 frame cùng scene ⇒ mean).
- `paired_delta` bỏ scene không chung, raise khi còn < 8.
- `scene_bootstrap` deterministic: cùng seed ⇒ cùng kết quả; CI chứa mean; với delta toàn 0 ⇒ `lo == hi == 0`.
- Toàn bộ test chạy < 3 s, không mạng.

## Cấm

- Không sửa `mit/`, `third_party/`, `kaggle/train/` (11-c1 đang sở hữu thư mục đó).
- Không push kernel, không commit.

## Nghiệm thu PM

```bash
pytest -q tests/ -k "eval_split or bootstrap"
python scripts/make_eval_split.py --selftest
```