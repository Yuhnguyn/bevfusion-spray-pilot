# Brief A1-b: lấy mẫu `wfh` theo scene (điều kiện 3 của ADR-0006 §5.7)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot`, nhánh `sspp`.
Đọc `docs/adr/0006-detection-protocol-and-calibration-source.md` **§5.7 mục 2, dòng "mức ẩm lấy mẫu"**.

**Không hỏi lại. Không mở rộng phạm vi. Không sửa file ngoài danh sách.**

---

## Bối cảnh

§5.7 đã wire 2/3 điều kiện (`2,5 ≤ ‖pos‖ ≤ 50`, `diffusion_alpha = 0`) — commit `ecfdb23` + lượt
trước đã xong, 216 test passed. Điều kiện thứ 3 chưa làm.

Paper A §V nguyên văn: *"Since the simulation model is a function of the water level, the water level
is sampled from an exponential distribution from the interval 0.1 − 1.2 mm during training."*

Repo hiện **hard-code `wfh_mm = 1.0`** ở `scripts/sspp_infer.py:1340` (`--wfh-mm` default 1.0) và
nhiều script đo. 1,0 mm là mức **"fully covered"** của paper — mức **cao nhất**, không phải mức
trung bình. Phân bố mũ trên [0,1; 1,2] có mean = 0,766 mm ⇒ repo đang đúng và **cao hơn mean 30 %**.

Đo được (không cần chạy lại): `alive(wfh)/alive(1,0 mm)` = **0,90** @60 km/h, **0,81** @100,
**0,80** @130. Tức lấy mẫu làm plume thưa 10–20 % — **nhỏ**, không phải 30–45 %.

**Quan trọng — thiết kế:** lấy mẫu **cố định theo scene**, KHÔNG theo từng frame. Lý do: cổng C là
paired A/B trên cùng frame; nếu hai nhánh nhận `wfh` khác nhau thì Δrecall trộn hai biến. Một scene
một mức ướt ⇒ mỗi scene-session có điều kiện riêng nhưng hai nhánh vẫn so sánh được.

---

## Việc phải làm

### Bước 1 — `spray/plume_context.py`: thêm hàm lấy mẫu

Thêm vào cuối file (sau `seed_for`, trước các hàm `_` private), và thêm `"sample_wfh_mm"` vào
`__all__` nếu file có `__all__` (không có thì bỏ qua):

```python
# [PAPER] arXiv 2212.08558 §V: "the water level is sampled from an exponential
# distribution from the interval 0.1 - 1.2 mm during training."
WFH_MIN_MM = 0.1
WFH_MAX_MM = 1.2


def sample_wfh_mm(scene_token: str, epoch: int = 0, base_seed: int = 0) -> float:
    """Mức ẩm cho MỘT SCENE, rút từ phân bố mũ trên ``[0.1, 1.2]`` mm [PAPER §V].

    Rút theo ``scene_token`` (không theo frame índice) để paired A/B của cổng C
    dùng **cùng** một mức ướt trên cùng frame — nếu rút theo frame thì hai nhánh
    sẽ khác ``wfh`` và ``Δrecall`` trộn hai biến.

    Phân bố: ``wfh = 0.1 + Exp(mean=1.0)``, clip vào ``[0.1, 1.2]``. Chọn mean 1,0
    vì khoảng khả dĩ rộng 1,1 mm và paper không cho tham số ⇒ mức "fully covered"
    1,0 mm vẫn là mode-ish; **đây là [CHỌN]**, phải ghi khi báo cáo: paper cho
    *khoảng* + *dạng phân bố*, không cho ``lambda``.

    Deterministic theo ``(scene_token, epoch, base_seed)`` — dùng ``hashlib`` như
    :func:`seed_for`, không dùng ``hash()``.
    """
    payload = f"wfh:{scene_token}:{int(epoch)}:{int(base_seed)}"
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest()
    rng = np.random.default_rng(int.from_bytes(digest, "little"))
    value = WFH_MIN_MM + float(rng.exponential(1.0))
    return float(np.clip(value, WFH_MIN_MM, WFH_MAX_MM))
```

`hashlib` và `np` đã import sẵn trong file — kiểm lại, nếu thiếu thì thêm.

### Bước 2 — `spray/plume.py`: dùng hàm này khi bật miền

Trong khối `if os.environ.get("PLUME_PAPER_DOMAIN", ...)` đã thêm ở `inject_plume_stateful`
(khoảng dòng 570), thêm **một dòng** sau `state._config = replace(...)`:

```python
        # [PAPER §V] mức ẩm lấy mẫu theo SCENE (không theo frame) — xem sample_wfh_mm.
        context = replace_context_wfh(context, sample_wfh_mm(
            context.scene_token, context.epoch, seed
        ))
```

Vì `PlumeContext` là `frozen dataclass`, thêm helper này ngay trên `inject_plume_stateful`
(không cần export):

```python
def replace_context_wfh(context, wfh_mm: float):
    """``PlumeContext`` với ``wfh_mm`` khác — frozen nên phải dựng lại."""
    from dataclasses import replace as _replace

    return _replace(context, wfh_mm=float(wfh_mm))
```

Import `sample_wfh_mm` từ `spray.plume_context` ở đầu `spray/plume.py` (giữ style import hiện có
trong file — nếu file import module-level thì import module-level).

**Bắt buộc:** mọi chỗ **sau** dòng này trong `inject_plume_stateful` phải dùng `context` mới
(không dùng tham số `context` gốc). Kiểm: `state.spawn(..., context)` và `state.warm_start(...)`
phải nhận `context` đã thay. `warm_start` dùng `context.wfh_mm` để tính `T` ⇒ nếu không thay thì
`warm_start` và `spawn` lệch `wfh`.

### Bước 3 — test mới: `tests/test_plume_wfh_sampling.py`

```python
def test_sample_wfh_in_paper_range(): ...
    """1000 lần với token khác nhau: mọi giá trị trong [0.1, 1.2]."""

def test_sample_wfh_is_deterministic_per_scene(): ...
    """Cùng (token, epoch, seed) => cùng giá trị; khác epoch => khác giá trị
       (ít nhất một trong 20 cặp khác)."""

def test_sample_wfh_does_not_depend_on_frame_index(): ...
    """Chữ ký hàm không có frame_index; hai lần gọi liền nhau cùng token => bằng nhau."""

def test_sample_wfh_mean_near_0766(): ...
    """1000 mẫu: mean trong [0.70, 0.85] — chốt đặc tính phân bố, không phải giá trị tuyệt đối."""
```

## Ràng buộc

1. Không đổi `--wfh-mm` default ở `scripts/sspp_infer.py` (script kia phải tái lập được số cũ).
2. Không đổi `PlumeContext.wfh_mm` default / validator (`0 < wfh <= 1.2` giữ nguyên — 1,2 nằm sát
   biên nên `clip` phải dùng `WFH_MAX_MM = 1.2` chính xác, không 1.2000001).
3. Không rút `wfh` theo frame.
4. Không thêm núm mới nào khác.
5. Không sửa `scripts/diag_*.py`, không sửa `spray/raycast.py`.
6. Không commit, không `git add`.

## Xong khi

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/ | tail -2
# => 220 passed (216 + 4)

# harness thật: bật miền phải cho wfh != 1.0 và ổn định trong scene
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. PLUME_PAPER_DOMAIN=1 \
  /opt/anaconda3/bin/python -c "
from spray.plume_context import sample_wfh_mm
for s in ('Crafter_dynamic/0060','Golf_dynamic/0006'):
    print(s, round(sample_wfh_mm(s, 0, 0), 3), round(sample_wfh_mm(s, 0, 0), 3))
"
# => hai số bằng nhau trong cùng dòng, khác nhau giữa hai dòng
```

Báo lại: số `passed`, output đoạn python trên, danh sách file đã sửa.
