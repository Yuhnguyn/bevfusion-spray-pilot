# Brief A1–A4: wire "Cách A" (miền hợp lệ) vào `spray/`

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`.
Đọc `docs/adr/0006-detection-protocol-and-calibration-source.md` **§5.7** trước — đó là spec đã
được chốt và commit (`ecfdb23`). File này chỉ là hướng dẫn thi công.

**Tuyệt đối không hỏi lại. Không tự mở rộng phạm vi. Không sửa file ngoài danh sách.**

---

## Bối cảnh (trạng thái thật)

- Baseline test: `CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/` → **213 passed**.
- `spray/plume_transform.py:132` và `spray/plume.py:637` gọi `state.all_alive()` — đây là **hai** call
  site duy nhất trong đường production (`grep -rn "state.all_alive()" spray/`).
- Đo được trên 4 scene Crafter: production sinh 2.339–4.214 detection/frame trong khi spray thật
  (`label == 2`) chỉ 126–1.478; `R_det` p05 = 1,42–1,58 m so với thật 3,72 m; 946–1.272 det ở
  `< 3 m` (thật: **không tồn tại** `label==2` dưới 2,5 m). Cụm trôi tới `x = −137 / −294 m`.
- Nguyên nhân: (a) luật nở `r(t) = r₀ + α·d_rel` `[CHỌN]`, không có trong paper, (b) `C = −0,15` của
  paper bị áp ngoài miền hiệu chuẩn 25 m/ego-đỗ. Tắt α: det → 497. Tắt drag: det → 126.

## Việc phải làm

### Bước 1 — `spray/plume_state.py`

**1a.** Thêm 3 field vào `PlumeStateConfig` (đặt cạnh `diffusion_alpha`, khoảng dòng 166–168):

```python
    # [MIỀN — ADR-0006 §5.7] Giới hạn miền mô hình phát ngôn. Tất cả tắt = hành vi cũ,
    # bit-for-bit. Bật bằng PLUME_PAPER_DOMAIN=1 (xem spray/plume.py).
    #   min/max_range_m: paper §V-D đánh giá 0–50 m; §V cảnh báo mô hình cầu vỡ ở gần
    #     cảm biến. Dữ liệu thật: r p01 = 2,75 m, chỉ 0,02 % điểm có r > 50 m.
    #   diffusion_alpha: Fig. 5 cho r_cl là MỘT lognormal, không nở theo tuổi.
    min_range_m: float = 0.0
    max_range_m: float = float("inf")
```

**Lưu ý:** KHÔNG đổi default của `diffusion_alpha` (giữ `DIFFUSION_ALPHA = 0.06`). Việc tắt là
quyết định của caller, không phải đổi ngầm.

**1b.** Thêm method vào `class PlumeState`, ngay sau `all_alive()` (khoảng dòng 685–691):

```python
    def select_alive(self) -> list[SprayCluster]:
        """Cụm còn sống VÀ nằm trong miền hợp lệ của mô hình (ADR-0006 §5.7).

        Mặc định (``min_range_m = 0``, ``max_range_m = inf``) trả về đúng
        ``all_alive()`` — đường nhanh, bit-for-bit hành vi cũ.

        Hai biên đều có paper làm căn cứ:
        - ``min_range_m``: paper §V cảnh báo *"with higher resolutions, a problem
          with the spherical cluster representation might appear. The problem can
          become especially pronounced in close proximity to the sensor"*; dữ liệu
          thật không có ``label == 2`` dưới 2,5 m.
        - ``max_range_m``: §V-D chỉ đánh giá 0–50 m, và ``P_det`` (Fig. 7) đo ở 25 m.

        Khoảng cách là ``‖pos‖`` (3D, từ cảm biến). Vì ``‖pos‖ ≥ |x|``, biên này
        bao hàm luôn "không trôi quá xa về phía sau": đo được chỉ cắt ``r ≤ 50``
        đã cho ``x min = −49,4 m``, không cần biên sau riêng.
        """
        clusters = self.all_alive()
        cfg = self._config
        if cfg.min_range_m <= 0.0 and not np.isfinite(cfg.max_range_m):
            return clusters
        kept: list[SprayCluster] = []
        for cluster in clusters:
            distance = float(np.linalg.norm(cluster.pos))
            if distance < cfg.min_range_m:
                continue
            if distance > cfg.max_range_m:
                continue
            kept.append(cluster)
        return kept
```

### Bước 2 — đổi đúng 2 call site

- `spray/plume.py:637`: `for cluster in state.all_alive():` → `for cluster in state.select_alive():`
- `spray/plume_transform.py:132`: `state.all_alive(),` → `state.select_alive(),`

**KHÔNG** sửa `scripts/diag_*.py` (6 file cũng gọi `all_alive`) — chúng phải tái lập được số cũ.

### Bước 3 — bật/tắt qua env, trong `spray/plume.py`

Thêm `import os` (nếu chưa có) và `from dataclasses import replace` ở đầu file.

Trong `inject_plume_stateful`, ngay sau dòng `cfg = config or PlumeConfig()` (khoảng dòng 548),
thêm:

```python
    # [MIỀN — ADR-0006 §5.7] Cách A: giữ nguyên mọi số paper, chỉ chặn phát ngôn ngoài
    # miền đã kiểm chứng. Bật bằng PLUME_PAPER_DOMAIN=1; tắt (mặc định) = hành vi cũ.
    if os.environ.get("PLUME_PAPER_DOMAIN", "").strip() not in ("", "0"):
        state._config = replace(
            state._config,
            diffusion_alpha=0.0,
            min_range_m=2.5,
            max_range_m=50.0,
        )
```

**Quan trọng:** đặt đoạn này **TRƯỚC** vòng lặp `for index, box in enumerate(box_arr)` nhưng
**SAU** `state.advance()`/`state.prune()` không quan trọng — miễn là trước khi
`state.select_alive()` được gọi (tức trước dòng 637). Chọn vị trí ngay sau
`expired = state.prune(...)` cho gọn.

### Bước 4 — file test mới `tests/test_plume_paper_domain.py`

Ba test, dùng numpy thuần + `SprayCluster` dựng tay (không cần dữ liệu SSPP):

```python
def test_domain_off_returns_all_alive(): ...
    """min_range_m=0, max_range_m=inf => select_alive() == all_alive() (cùng list)."""

def test_domain_filters_by_radius(): ...
    """3 cụm ở |pos| = 1.0, 10.0, 80.0 m với min=2.5/max=50 => chỉ còn cụm 10 m."""

def test_domain_env_switch_does_not_change_default(): ...
    """Không set PLUME_PAPER_DOMAIN => PlumeStateConfig().min_range_m == 0.0
       và diffusion_alpha == 0.06 (default không bị đổi)."""
```

## Ràng buộc — cái KHÔNG được làm

1. Không đổi **default** của bất kỳ field nào trong `PlumeStateConfig`/`PlumeConfig`.
2. Không sửa `spray/raycast.py` (raycast phải thuần, không biết gì về miền).
3. Không sửa `scripts/diag_*.py`.
4. Không thêm biên `x`/`min_x_m`/`min_z_m` — `‖pos‖` đã bao hàm (xem docstring trên).
5. Không thêm hệ số bù mật độ nào (`spawn_scale`, `pdet_range_exponent`, `density_scale`).
6. Không format lại file, không đổi import style, không sửa docstring cũ không liên quan.
7. Không commit, không `git add`. Chỉ sửa file và chạy test.

## Xong khi

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/ | tail -2
# => 216 passed

grep -rn "state.all_alive()" spray/ | grep -v plume_state.py
# => RỖNG

grep -c "select_alive" spray/plume.py spray/plume_transform.py spray/plume_state.py
# => mỗi file >= 1

CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. PLUME_PAPER_DOMAIN=1 \
  /opt/anaconda3/bin/python -c "
from spray.plume_state import PlumeStateConfig
import spray.plume as p
print('OK default unchanged:', PlumeStateConfig().diffusion_alpha, PlumeStateConfig().min_range_m)
"
```

Báo lại trong câu trả lời cuối: số `passed`, output 3 lệnh trên, và danh sách file đã sửa.
