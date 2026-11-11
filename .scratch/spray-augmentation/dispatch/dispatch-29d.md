# Ticket 29d: cổng chia `cal` / `held-out` cho SemanticSpray + đo lại thống kê

HEAD: `fd501bf`  Nhánh: `main`
Skill: tdd — `/Users/huynguyen/.agents/skills/tdd` (1 skill duy nhất)

Ticket gốc: `.scratch/spray-augmentation/issues/29d-semantic-split-gate.md` — **đọc trước**, luật chia và
7 tiêu chí trong đó là **đóng băng**, brief này chỉ nói cách implement.

Luật không đổi của repo: `/opt/anaconda3/bin/python`; `PYTHONPATH=.`; `CONDA_NO_PLUGINS=true`;
không thêm dependency (chỉ `numpy` + `yaml` + stdlib); mọi số mới phải gắn `[ĐO]`/`[CHỌN]`/`[CODE]`.

## Hiện trạng (PM đã kiểm)

- Dataset đã extract: `data/SemanticSprayDataset/{Crafter_dynamic,Golf_dynamic}/<scene>/` với
  `metadata.txt`, `velodyne/*.bin` (N×5: `x,y,z,intensity,ring`), `labels/*.label` (uint32, `2` = noise/spray).
- **207 scene, 17.419 frame**, ~84 frame/scene. 36 ô = `group × object_velocity × distance_to_object`;
  34 ô có 6 scene, 1 ô có 2, 1 ô có 1.
- Code thống kê đã có nhưng **không dùng lại trực tiếp được**:
  `spray/spray_stats.py` (single-linkage r=0,5, `dense_min=5`) và
  `scripts/semantic_spray_stats.py` (cùng luật, cảnh báo trong docstring: *không phải recipe paper*).
  Recipe dùng ở đây là **cụm ≥ 3 điểm** (xấp xỉ DBSCAN `minPts = 3` của paper; single-linkage là
  DBSCAN với `minPts = 1`, nên lọc thêm theo kích thước cụm — ghi `[CHỌN]` trong docstring).
- `scripts/measure_spray_height.py:31` có `_plane()` fit mặt đường 3 vòng IRLS — **chép nguyên** vào module
  mới (xem §2); **không sửa** file đó.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **239 passed, 4 skipped**.

## Nguyên nhân gốc

Tham số generator v2 (mật độ, chiều cao/bề rộng khối, intensity, ring) đang được đo trên toàn bộ 207 scene,
rồi cũng báo cáo "khớp" trên chính 207 scene đó. Không có split thì mọi con số ở ticket 31 là in-sample.

## Việc phải làm

### 1. `spray/semantic_split.py` (file mới)

```python
ROLE_CAL = "cal"
ROLE_HELD_OUT = "held-out"
SPLIT_VERSION = "semantic-spray-split-v1"
GROUPS = ("Crafter_dynamic", "Golf_dynamic")

@dataclass(frozen=True)
class SceneMeta:
    group: str; scene: str
    object_velocity_kmh: float; distance_to_object_m: float
    itr_after_water: int; amb_tmp_c: float | None
    @property
    def rel_path(self) -> str: ...        # "Crafter_dynamic/0000_2021-09-08-14-36-56_0"

def read_dataset(root: str | Path) -> list[SceneMeta]      # 207 phần tử, sắp theo rel_path
def cell_key(meta: SceneMeta) -> tuple[str, float, float]
def assign_roles(metas: list[SceneMeta]) -> dict[str, str]  # rel_path -> "cal" | "held-out"
def build_split(metas: list[SceneMeta]) -> dict             # cấu trúc dưới đây
def dump_split(split: dict, path: str | Path) -> None       # yaml.safe_dump(..., sort_keys=False, allow_unicode=True)
def load_split(path: str | Path) -> dict
def verify_split(split: dict, path: str | Path) -> list[str]  # [] = khớp; mỗi phần tử = 1 mô tả lệch
def role_scenes(split: dict, role: str, root: str | Path) -> list[Path]  # sắp theo rel_path
def halves(rel_paths: list[str]) -> tuple[list[str], list[str]]          # (a, b) xen kẽ trên danh sách ĐÃ sắp
```

Cấu trúc `split` (khoá cố định, PM grep theo tên này):

```yaml
version: semantic-spray-split-v1
rule: "1:1 trong từng ô (group, object_velocity, distance_to_object); sắp theo tên; xen kẽ cal/held-out; scene dư về cal"
counts: {cal: 104, held-out: 103}
cells:
  - key: {group: Crafter_dynamic, velocity_kmh: 50.0, distance_m: 20.0}
    scenes: {cal: [...], held-out: [...]}
    unpaired: false
criteria:
  - {id: G1, quantity: noise_points_per_frame, estimator: median, floor_rel: 0.15, floor_abs: 0.0}
  # ... đủ G1..G7, đúng số trong ticket
```

- `assign_roles` **không** dùng RNG, **không** phụ thuộc thứ tự đầu vào: sắp `rel_path` rồi mới chia.
- Ô 1 scene → `cal`, `unpaired: true`. Ô 2 scene → 1/1. Ô 6 scene → 3/3.
- `verify_split` so **nội dung ngữ nghĩa** (roles, counts, unpaired), không so byte của YAML.
- `read_dataset` raise `FileNotFoundError` nếu thiếu `metadata.txt`; raise `ValueError` (nêu tên scene)
  nếu `metadata.txt` không đúng 1 dòng dữ liệu hoặc thiếu cột.

### 2. `spray/semantic_stats.py` (file mới)

```python
MIN_PTS = 3
RADIUS_M = 0.5

def fit_ground_plane(points: np.ndarray) -> tuple[float, float, float]
    # CHÉP NGUYÊN scripts/measure_spray_height.py:_plane (3 vòng IRLS, cửa sổ 3–40 m, |z|<0,4,
    # fallback (0.0, 0.0, -0.411)); docstring ghi rõ nguồn + lý do chép thay vì import
    # (không được sửa file gốc, số cũ phải giữ nguyên).

def frame_stats(points: np.ndarray, labels: np.ndarray, *,
                min_pts: int = MIN_PTS, radius_m: float = RADIUS_M) -> dict
```

`frame_stats` trả **đúng** các khoá sau (giá trị là `list`/`np.ndarray`, đơn vị ghi trong docstring):

| Khoá | Nội dung |
|---|---|
| `n_noise` | số điểm `label == 2` |
| `cluster_sizes` | kích thước từng cụm **≥ `min_pts`** (điểm) |
| `range_over_extent` | `r_range / r_extent` từng cụm ≥ `min_pts` (bỏ cụm có `r_extent == 0`) |
| `abs_y` | `|y|` của điểm noise (m) |
| `height_above_road` | `z − (a·x + b·y + c)` của điểm noise (m), plane từ `fit_ground_plane` |
| `elevation_deg` | `degrees(atan2(z, hypot(x, y)))` của điểm noise (độ) — **không** dùng cột `ring` |
| `intensity` | cột 3 của điểm noise |
| `ring` | cột 4 của điểm noise |

`r_extent = max‖p − centroid‖`, `r_range = max‖p‖ − min‖p‖` (giống `ClusterRecord` trong
`scripts/semantic_spray_stats.py`; chép công thức, không import file script).

Thêm:

```python
class StatsAccumulator:              # add(frame: dict) -> None
    def summary(self) -> dict        # {"frames": int, "noise_per_frame": np.ndarray, "clusters_per_frame": np.ndarray,
                                     #  "cluster_sizes": np.ndarray, "range_over_extent": np.ndarray, "abs_y": np.ndarray,
                                     #  "height_above_road": np.ndarray, "elevation_deg": np.ndarray,
                                     #  "intensity": np.ndarray, "ring": np.ndarray}
def metrics(summary: dict) -> dict[str, float]
    # {"G1": .., "G2": .., "G3": .., "G4": .., "G5": .., "G6_p5": .., "G6_med": .., "G6_p95": .., "G7": ..}
```

Định nghĩa metric đúng như bảng 7 tiêu chí của ticket: `G1 = median(noise_per_frame)`,
`G2 = mean(clusters_per_frame)`, `G3 = median(cluster_sizes)`, `G4 = median(range_over_extent)`,
`G5 = p95(abs_y)`, `G6_* = percentile(height_above_road, [5,50,95])`, `G7 = median(elevation_deg)`.

### 3. `evaluate_criteria` (trong `spray/semantic_split.py`)

```python
@dataclass(frozen=True)
class CriterionResult:
    id: str; quantity: str; estimator: str
    cal: float; held_out: float; delta: float
    half_split_delta: float; threshold: float; relative: bool; passed: bool; note: str

def evaluate_criteria(metrics_by_role: dict[str, dict[str, float]], *, min_frames: int = 300,
                      min_clusters: int = 100) -> list[CriterionResult]
    # metrics_by_role: {"cal": …, "held-out": …, "cal_a": …, "cal_b": …}
    # threshold = max(floor, 2 * |cal_a - cal_b|)  → riêng G6 lấy max của 3 phân vị
    # passed = |cal - held-out| <= threshold ; G6 passed khi CẢ BA phân vị đạt
    # thiếu khoá / frames < min_frames / cụm < min_clusters ⇒ passed False, note = "quá ít dữ liệu: ..."
```

### 4. `scripts/semantic_spray_split.py` (file mới)

```
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/semantic_spray_split.py --build
… --verify
… --measure --frames-per-scene 60 [--limit-scenes N] [--out docs/measurements/semantic-spray-cal-vs-heldout.md]
```

- `--build`: `read_dataset` → `assign_roles` → `build_split` → `dump_split` lên
  `spray/config/semantic_spray_split.yaml`. In `SPLIT_BUILT cal=<n> heldout=<n> cells=<n> unpaired=<k>`.
- `--verify`: dựng lại split từ dataset, `verify_split` với file trên đĩa; in `SPLIT_VERIFY_OK` (exit 0)
  hoặc `SPLIT_VERIFY_MISMATCH n=<k>` + từng dòng lệch (exit 1).
- `--measure`: đọc split, chọn scene theo vai, mỗi scene lấy `--frames-per-scene` frame **rải đều**
  (`np.linspace` như `sample_scan_ids` trong `scripts/semantic_spray_stats.py`), gộp bằng
  `StatsAccumulator`, tính `metrics` cho `cal`, `held-out`, `cal_a`, `cal_b`, rồi
  `evaluate_criteria`, ghi báo cáo, in marker cuối:
  `SPLIT_GATE ok=True failed=[] frames_cal=<n> frames_heldout=<n>` hoặc
  `SPLIT_GATE ok=False failed=[G4,...]`. **Exit 1 khi `ok=False`.** Báo cáo **luôn** được ghi, kể cả khi fail.
- Frame có `labels.size != points.shape[0]` → bỏ frame (đếm `skipped`), in số đã bỏ.

Báo cáo `docs/measurements/semantic-spray-cal-vs-heldout.md` — các mục, theo thứ tự:

1. `## Bối cảnh` — vì sao có cổng này (2–4 câu), nhãn `[CHỌN]` cho luật chia.
2. `## Mẫu` — lệnh chạy (in nguyên `sys.argv`), `--frames-per-scene`, scene/frame mỗi vai, `skipped`.
3. `## Bảng 1 — Split theo ô` — 36 dòng: `group | km/h | distance | #scene | cal | held-out | unpaired`.
4. `## Bảng 2 — 7 tiêu chí đóng băng [ĐO]` — `id | đại lượng | cal | held-out | Δ | Δ_halfsplit | ngưỡng | verdict`.
5. `## Bảng 3 — Số bàn giao cho 29c [ĐO]` — trên `cal`:
   `điểm noise/frame (p5/med/p95)`, `cụm/frame (mean)`, `điểm/cụm (p5/med/p95)`,
   `tail_block_height_frac` = p5/p95 của `height_above_road / 2,6206` (box height van, ghi nguồn),
   `p95(|y|)`, `intensity p50/p90/p99`, `ring` phủ khoảng nào + median.
6. `## Kết luận` — 7/7 PASS ⇒ "split đại diện được"; có FAIL ⇒ liệt kê mã, câu "không đổi ngưỡng, không trộn vai".
7. `## Caveats` — half-split chỉ là sàn nhiễu nội tại `[CHỌN]`; single-linkage + lọc cụm ≥ 3 ≈ DBSCAN
   `minPts = 3` `[CHỌN]`; label 2 gồm cả nhiễu không phải spray; `amb_tmp` không đưa vào ô chia.

Sinh lại báo cáo phải **idempotent**: chạy 2 lần cùng tham số → cùng nội dung (không timestamp, không đường dẫn tuyệt đối).

### 5. Test — viết **trước** khi code

`tests/test_semantic_split.py` (7 test, dùng metadata tổng hợp, **không** đọc dataset thật):

1. 36 ô dựng từ `SceneMeta` tổng hợp: mỗi ô 6 scene → 3 `cal` + 3 `held-out`.
2. Đảo thứ tự list đầu vào (2 lần, khác nhau) → `assign_roles` cho **cùng** kết quả.
3. Ô 1 scene → `cal` + `unpaired: true`; ô 2 scene → 1/1.
4. Hợp hai vai = toàn bộ scene; giao = rỗng; `counts` khớp độ dài thật.
5. `dump_split` 2 lần → byte-identical; `load_split` → `verify_split` trả `[]`; sửa 1 role trong YAML →
   `verify_split` trả đúng 1 dòng lệch.
6. `halves()`: rời nhau, hợp = `cal`, xen kẽ, ổn định khi gọi lại.
7. `evaluate_criteria`: (a) 4 dict số giống nhau → 7/7 PASS; (b) đẩy `G4` lệch 0,11 → chỉ `G4` FAIL;
   (c) `frames=100` → các dòng cần dữ liệu FAIL với note chứa `quá ít dữ liệu`.

`tests/test_semantic_stats.py` (5 test, dữ liệu tổng hợp):

1. Chỉ điểm `label == 2` vào thống kê; cụm 2 điểm bị loại khi `min_pts = 3`, cụm 3 điểm được giữ.
2. `range_over_extent` của 1 cụm dựng tay khớp giá trị tính tay (sai số 1e-6).
3. `abs_y` = `|y|` của điểm noise, không lẫn điểm foreground.
4. `height_above_road`: mặt phẳng `z = 0,5` (điểm ground + điểm noise) → median height ≈ giá trị đặt vào (≤ 0,05 m).
5. `elevation_deg` khớp `degrees(arctan2(z, hypot(x,y)))`; `intensity` và `ring` lấy đúng cột 3, 4.

Kỳ vọng: **251 passed, 4 skipped** (239 + 12). Nêu số thật vào báo cáo cuối.

### 6. Smoke (bắt buộc, < 1 phút)

```
--build  → SPLIT_BUILT cal=104 heldout=103 cells=36 unpaired=1
--verify → SPLIT_VERIFY_OK
--measure --limit-scenes 6 --frames-per-scene 5 → chạy hết, ghi báo cáo, in SPLIT_GATE …
```
**Không** chạy `--measure` full 207 scene trong lượt này (PM chạy, cần vài phút); chỉ cần smoke trên.

## Tiêu chí nghiệm thu (agent tự kiểm trước khi báo xong)

- [ ] `pytest -q tests/` ≥ 251 passed, 4 skipped; dán số thật.
- [ ] `--build` in `cal=104 heldout=103 cells=36 unpaired=1`; YAML có `version`, `counts`, `cells`, `criteria` đủ 7.
- [ ] `--verify` exit 0; `--build` lại rồi `--verify` vẫn exit 0.
- [ ] `--measure --limit-scenes 6 --frames-per-scene 5` ghi báo cáo đủ 7 mục, có dòng `SPLIT_GATE`.
- [ ] `git status --porcelain` chỉ có: 2 module mới, 1 script mới, 2 test mới, 1 YAML mới (+ báo cáo nếu chạy).
- [ ] Không sửa file có sẵn nào (`git diff --stat` không có file cũ).
- [ ] Không có `sorted(os.listdir(...))` làm nguồn thứ tự chia; không RNG; không timestamp trong báo cáo.

## Cấm

- Không sửa `spray/plume.py`, `spray/raycast.py`, `spray/beam_model.py`, `spray/config/plume_default.yaml`,
  `scripts/measure_spray_height.py`, `scripts/semantic_spray_stats.py`, `scripts/plume_v2_measure_common.py`.
- Không đổi luật chia / 7 ngưỡng / định nghĩa đại lượng. Không dùng `held-out` để chọn tham số.
- Không train, không Kaggle, không tải dữ liệu mới, không thêm dependency.
- Không tự commit; PM nghiệm thu rồi commit.
## PHỤ LỤC 2026-11-11 (sau khi dispatch, trước khi đo full) — SỬA TOÁN TỬ ĐẾM CỤM

Paper dùng **DBSCAN `minPts = 3`, neighborhood góc `0,7°`, elevation discretisation `0,333°`**
(`docs/reference/paper-qa-notebooklm.md` §4). Brief gốc dùng neighbor Euclid `0,5 m` ⇒ **cổng `G2/G3/G4`
phải dùng recipe góc**; `0,5 m` chỉ còn là bảng phụ để so `17,06` cụm/frame của ticket 16.

Yêu cầu bổ sung cho `spray/semantic_stats.py`:

```python
ELEVATION_STEP_DEG = 0.333
ANGULAR_EPS_DEG = 0.7

def cluster_angular(points: np.ndarray, *, eps_deg: float = ANGULAR_EPS_DEG,
                    min_pts: int = MIN_PTS) -> np.ndarray
    # chỉ nhận điểm noise; trả nhãn cụm int (-1 = không vào cụm nào)
    # azimuth_deg = degrees(atan2(y, x)); elevation_deg = degrees(atan2(z, hypot(x, y)))
    # elevation snap về lưới ELEVATION_STEP_DEG (round(el / step) * step)
    # lân cận: khoảng cách Euclid trong mặt phẳng (az, el) <= eps_deg, azimuth xử lý wrap modulo 360
    # CORE/border đúng DBSCAN: điểm core khi có >= min_pts điểm (kể cả chính nó) trong eps
```

`frame_stats(..., recipe="paper")` dùng `cluster_angular`; `frame_stats(..., recipe="legacy")` giữ
single-linkage `0,5 m` + lọc cụm `>= 3` điểm. `metrics()` báo thêm khoá `legacy_*` cho bảng phụ;
**cổng chỉ đọc G1..G7 của recipe paper**.

Test bổ sung (≥ 2): cùng một đám điểm, cụm 2 điểm bị loại với `min_pts=3`; hai điểm lệch azimuth
`359°` và `1°` phải được coi là gần nhau (wrap); elevation lệch `0,34°` snap về cùng một hàng lưới.
