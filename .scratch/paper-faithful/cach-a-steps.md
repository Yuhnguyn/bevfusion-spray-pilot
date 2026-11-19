# Cách A — thi công chi tiết, từng bước

Nhánh `sspp` · 2026-11-19 · nền: `.scratch/paper-faithful/plan.md` §3 Cách A.
Baseline đã đo: `pytest -q tests/` = **213 passed** (25 file test), commit đầu là `a105cce`.

**Nguyên tắc của Cách A, một câu:** *giữ nguyên mọi số của Paper A; chỉ không cho mô hình
phát ngôn ngoài miền paper đã kiểm chứng.* Không sửa `C`, không sửa `r_cl`, không sửa `P_det`,
không sửa `T`. Chỉ thêm **bốn điều kiện miền** + **tắt một luật nở không có trong paper**.

Bốn điều kiện miền:

| điều kiện | ngưỡng | căn cứ |
|---|---|---|
| cụm phải ở **trước** mặt phẳng cảm biến | `x ≥ 0` | Paper §II-A: ego **đỗ**, xe chạy qua; cụm không bao giờ ở sau cảm biến |
| không xét cụm quá gần | `‖pos‖ ≥ 3,0 m` | Paper §V: *"spherical cluster representation ... pronounced in close proximity"* |
| không xét cụm quá xa | `‖pos‖ ≤ 50,0 m` | Paper §V-D: *"entire evaluation range from 0-50 m"* |
| tắt luật nở | `diffusion_alpha = 0` | Paper Fig. 5: `r_cl` là một lognormal, **không** nở theo tuổi |

---

## Bước A0 — Chốt miền vào ADR **trước** khi chạy bất kỳ số nào

**Sửa:** `docs/adr/0006-detection-protocol-and-calibration-source.md`, thêm mục **§5.7**.

Nội dung bắt buộc phải có (chép nguyên, không diễn giải lại sau khi thấy số):

```markdown
### 5.7 Miền hợp lệ của generator (Cách A) — pre-register 2026-11-19

Mô hình Paper A được hiệu chuẩn với ego ĐỖ ở cự ly 25 m (§II-A) và được kiểm chứng trên
0–50 m (§V-D). Repo áp nó vào kịch bản following (ego bám đuôi, |ego−object| = 0,00 km/h
trên 207/207 scene SSPP). Để kết quả có nghĩa, generator chỉ phát cụm trong miền:

    x >= 0 m            (trước mặt phẳng cảm biến)
    3.0 <= |pos| <= 50  (paper §V cảnh báo mô hình cầu vỡ ở gần; 50 m là miền đánh giá)
    diffusion_alpha = 0 (Fig. 5: r_cl là một lognormal, không nở theo tuổi)

Các số paper KHÔNG đổi: C = -0.15 m^-1, r_cl lognormal(-1.2, 0.8), P_det lognormal(-2.3, 1.09),
P_t = exp(-t/T), extinction 0.02 m^-1, dt = 0.1 s (SSPP đo 0.064-0.134 s => không hiệu chỉnh lại C).

Tiêu chí cổng C (ghi TRƯỚC khi chạy):
    |Δrecall(plume − clean) − Δrecall(real − clean)| <= 0.05
    với Δrecall(real − clean) = -0.049 [-0.083; -0.019] (đo trên 954 frame, τ = 0.20)
    => cổng ĐẠT khi Δrecall(plume − clean) nằm trong [-0.099; +0.001]
    ΔFP(plume − clean) phải có CI95 không chứa 0 (giữ tiêu chí TC1 cũ).

Dự đoán ghi trước: Δrecall(plume − clean) sẽ dịch từ -0.268 về khoảng -0.05.
Nếu kết quả vẫn < -0.15 => miền KHÔNG phải nguyên nhân duy nhất; DỪNG, không thêm núm thứ tư.

Cấm: thêm pdet_range_exponent, spawn_scale, density_scale, hay bất kỳ hệ số bù nào.
```

**Artifact:** commit chỉ chứa file ADR này.
**Điều kiện đạt:** `git log -1 --stat` cho thấy đúng 1 file `docs/adr/0006-*.md`, và commit đó
đứng **trước** mọi commit sửa `spray/`. Kiểm bằng `git log --oneline -5`.
**Vì sao bước này phải trước:** user đã bị một lần "đổi ngưỡng sau khi thấy số" ở D2-v2.

---

## Bước A1 — Bốn field + một hàm lọc trong `spray/plume_state.py`

**Chỗ sửa 1:** thêm 4 field vào `PlumeStateConfig` (sau dòng 168, cạnh `diffusion_alpha`):

```python
    # [MIỀN — ADR-0006 §5.7] Giới hạn miền mô hình phát ngôn. Tắt hết = hành vi cũ.
    # Paper §II-A hiệu chuẩn với ego ĐỖ nên cụm không bao giờ ở sau cảm biến; §V
    # cảnh báo mô hình cầu vỡ ở gần; §V-D đánh giá 0–50 m.
    min_range_m: float = 0.0            # 0.0 = tắt
    max_range_m: float = float("inf")   # inf = tắt
    drop_behind_sensor: bool = False    # False = tắt
    # min_z_m: KHÔNG thêm — đo được chỉ 2,2–3,3 % cụm dưới mặt đường, > -0,3 m là 0,0–0,1 %.
```

**Chỗ sửa 2:** thêm method vào `class PlumeState`, ngay sau `all_alive()` (dòng 685):

```python
    def select_alive(self) -> list[SprayCluster]:
        """Cụm còn sống VÀ nằm trong miền hợp lệ của mô hình (ADR-0006 §5.7).

        Mặc định (0 / inf / False) trả về đúng `all_alive()` — tái lập bit-for-bit
        hành vi cũ. Chỉ khi caller bật mới lọc.

        Bốn điều kiện, mỗi điều kiện có một câu paper làm căn cứ:
        - ``drop_behind_sensor``: paper §II-A hiệu chuẩn với ego ĐỖ, xe chạy qua, nên
          cụm không bao giờ ở sau mặt phẳng cảm biến. Ở SSPP ego bám đuôi cùng tốc độ
          ⇒ cụm bị drag kéo lùi xuyên cảm biến (đo: 41–65 % instance ở x < 0).
        - ``min_range_m``: paper §V tự cảnh báo "spherical cluster representation
          might appear [as a problem] ... pronounced in close proximity to the sensor".
        - ``max_range_m``: paper §V-D chỉ đánh giá 0–50 m; P_det đo ở 25 m (Fig. 7).
        """
        cfg = self._config
        clusters = self.all_alive()
        if (not cfg.drop_behind_sensor
                and cfg.min_range_m <= 0.0
                and not np.isfinite(cfg.max_range_m)):
            return clusters          # đường nhanh: hành vi cũ, không đổi gì
        kept: list[SprayCluster] = []
        for cluster in clusters:
            if cfg.drop_behind_sensor and float(cluster.pos[0]) < 0.0:
                continue
            distance = float(np.linalg.norm(cluster.pos))
            if distance < cfg.min_range_m:
                continue
            if distance > cfg.max_range_m:
                continue
            kept.append(cluster)
        return kept
```

**Điều kiện đạt:** `python -c "import ast; ast.parse(open('spray/plume_state.py').read())"` OK;
`pytest -q tests/` vẫn **213 passed** (chưa ai gọi `select_alive` nên hành vi không đổi).

**Cố ý KHÔNG sửa default của `diffusion_alpha`** (giữ 0,06). Lý do: production cũ phải tái lập
được; việc tắt tán xạ là quyết định của **caller**, ghi trong ADR, không phải đổi ngầm.

---

## Bước A2 — Nối vào đúng **hai** call site

Đo được có đúng 2 chỗ gọi `state.all_alive()` trong đường production:

| file:line | việc | sửa |
|---|---|---|
| `spray/plume.py:637` | materialise cụm thành điểm `ring=-1` để đẩy vào `points` | `state.select_alive()` |
| `spray/plume_transform.py:132` | danh sách cụm đưa vào `raycast_frame` | `state.select_alive()` |

Đây là chỗ quyết định: `raycast` phải giữ **thuần** (không biết gì về miền), nên lọc nằm ở
`PlumeState`, và cả hai consumer đều đi qua nó.

**Điều kiện đạt:**
```bash
grep -rn "state.all_alive()" spray/ | grep -v plume_state.py
# phải RỖNG (không còn call site nào dùng all_alive trong đường production)
grep -rn "select_alive" spray/ | wc -l   # >= 3 (định nghĩa + 2 call site)
```

**Bẫy phải tránh:** `scripts/diag_*.py` (6 file) cũng gọi `state.all_alive()`. **Không sửa
chúng** — chúng là probe chẩn đoán, giữ nguyên để tái lập số cũ. Ghi một dòng chú thích vào ADR
§5.7 là đủ.

---

## Bước A3 — Bật Cách A qua biến môi trường (không đổi default)

**Chỗ sửa:** `spray/plume.py`, hàm `inject_plume_stateful`, ngay sau dòng 548 (`cfg = config or PlumeConfig()`):

```python
    # [MIỀN — ADR-0006 §5.7] Cách A: giữ nguyên số paper, chỉ chặn phát ngôn ngoài miền.
    # Bật bằng PLUME_PAPER_DOMAIN=1. Khi tắt (mặc định) không đổi gì so với bản cũ.
    paper_domain = os.environ.get("PLUME_PAPER_DOMAIN", "").strip() not in ("", "0")
    if paper_domain:
        state._config = replace(state._config, diffusion_alpha=0.0)
        state._config = replace(state._config, drop_behind_sensor=True)
        state._config = replace(state._config, min_range_m=3.0)
        state._config = replace(state._config, max_range_m=50.0)
```

Cần thêm `import os` và `from dataclasses import replace` ở đầu `spray/plume.py`.

**Điều kiện đạt:** hai lần chạy **cùng seed, cùng frame, biến môi trường khác nhau**, in md5 của
`RaycastResult.detections`:

```bash
PY="CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=."
eval $PY /opt/anaconda3/bin/python scripts/measure_following_scenario.py --sets B \
     --frames-per-scene 3 --limit-scenes 1 --out /tmp/off.json     # PLUME_PAPER_DOMAIN không set
PLUME_PAPER_DOMAIN=1 eval $PY /opt/anaconda3/bin/python scripts/measure_following_scenario.py \
     --sets B --frames-per-scene 3 --limit-scenes 1 --out /tmp/on.json
# off.json md5 phải bằng md5 31f62749665f280e6ff3f118cd0c0a54 KHÔNG áp dụng được
# (đó là 30 frame/scene) — thay bằng: so md5 của off.json với lần chạy lại y hệt,
# và so det/frame của on.json phải nhỏ hơn hẳn off.json.
```

**Điều kiện đạt thực tế (đo rồi, dùng luôn làm test):** `on.json` có det/frame ≈ 0,13–1,03× thật
và **không** có detection nào ở `< 3 m`; `off.json` có 1,6–17× và 946–1 272 det ở `< 3 m`.

---

## Bước A4 — Ba test mới, baseline 213 → 216

**File mới:** `tests/test_plume_paper_domain.py`

```python
def test_domain_off_is_bitforbit_identical():
    """Tắt miền (default) => md5 detections y hệt trước khi có tính năng."""

def test_domain_drops_clusters_behind_sensor():
    """Cụm ở x<0 không sinh detection nào; det/frame giảm, R_min >= 3 m."""

def test_domain_has_zero_detections_under_3m():
    """Trên 1 scene thật, mọi detection có |pos| >= 3 m và x >= 0."""
```

**Điều kiện đạt:** `pytest -q tests/` = **216 passed**, và test 1 (bit-for-bit) là test **phải
fail nếu ai đổi default** — kiểm bằng cách tạm đổi `min_range_m=3.0` thành default rồi thấy đỏ.

---

## Bước A5 — Đo A3-V trên tập B (72 scene không box)

```bash
PLUME_PAPER_DOMAIN=1 eval $PY /opt/anaconda3/bin/python scripts/measure_following_scenario.py \
    --sets B --frames-per-scene 30 --out .scratch/tmp/following_paper_domain.json
```

**Artifact:** `.scratch/tmp/following_paper_domain.json` + bảng trong
`docs/measurements/following-scenario-paper-domain.md`.

Bảng phải có **6 dòng** (2 lớp × 3 nhóm tốc độ), mỗi dòng 7 cột:
`scene | frame | thật/f | sinh/f | median tỉ lệ [CI95]` **+ `R p05/p50 (m)` + `det <3 m`**.

**Điều kiện đạt:**
- `det <3 m` = **0** ở cả 6 dòng (điều kiện cứng);
- `R p50` của sinh nằm trong ±30 % của `R p50` thật (điều kiện mới, quan trọng hơn tỉ lệ);
- tỉ lệ median: báo số thật, **không** ép vào `[0,5; 2,0]` bằng `spawn_scale`.

**Kỳ vọng đã đo trước (3 scene, 40 frame):** tỉ lệ 0,13 / 0,51 / 1,03×; `R p50` sinh 8,6–10,4 m
so với thật 5,4–8,8 m ⇒ **sinh xa hơn thật 1,2–1,9×**. Nếu bảng đầy đủ cũng ra như vậy thì kết
luận là: *Cách A sửa được near-field nhưng làm plume lệch về phía xa* — và đó là chỗ
`diffusion_alpha` từng che lấp (nó bơm bán kính để cụm gần vẫn "to").

---

## Bước A6 — Bốn clip, trong đó clip `static` là phép kiểm quyết định

| clip | lệnh | vì sao |
|---|---|---|
| `viz_3way_100kmh.mp4` | `viz_three_way.py --scene Crafter_dynamic/0060_...` | ca khó nhất, nước đầy |
| `viz_3way_130kmh.mp4` | `--scene Crafter_dynamic/0096_...` | ca production tệ nhất (16,97×) |
| `viz_3way_golf_100kmh.mp4` | `--scene Golf_dynamic/<@100>` | bắt lỗi `vehicle_class="crafter"` hard-code |
| **`viz_3way_static.mp4`** | RoadSpray `Crafter_static` | **kịch bản duy nhất paper thực sự đã kiểm chứng** |

Clip thứ tư cần: stream 1 bag từ `data/roadspray/Crafter_static.zip` (đã có, 7 924 255 130 B)
vào `.scratch/tmp/`, đọc bằng `rosbags` (offset intensity = **16**, không phải 12), ego đỗ nên
`ego_velocity = [0,0,0]` — chính là điều kiện paper.

**Điều kiện đạt và cách đọc:**
- faithful **khớp** static, **lệch** following ⇒ kết luận "lỗi miền", đúng dự đoán ⇒ đi tiếp A7.
- faithful **cũng lệch** static ⇒ có lỗi **port**, phải tìm trước A7. Dừng.
- Clip phải có hàng nhìn ngang `x–z`; BEV một mình không thấy được `x < 0`.

---

## Bước A7 — Cổng C theo §5.7

Kernel mới, copy `kaggle/gate_c/`, dùng **cùng** dataset `sspp-gate-c-data`, chỉ đổi code version.
Tham số phải khớp cổng C cũ để paired: 954 frame, τ = 0,20, IoU 0,5, range 54 m, seed 0, epoch 0,
`wfh_mm = 1,0`, `road_z = −0,411` — **cộng** `PLUME_PAPER_DOMAIN=1`.

**Điều kiện đạt:** bảng `ΔFP` + `Δrecall` với CI95 theo scene, chấm theo ngưỡng §5.7 đã commit
ở A0. Bắt buộc in kèm `det/frame` và `R p50` mỗi nhánh — để biết nhánh plume có còn là "tấm màn
trước cảm biến" không.

**Ba kết cục, quyết trước:**

| kết quả | làm gì |
|---|---|
| `Δrecall ∈ [−0,099; +0,001]` | ĐẠT ⇒ augmentation hợp lệ ⇒ câu hỏi train mới có nghĩa (bước F) |
| `Δrecall < −0,15` | DỪNG, ghi kết luận âm tính; **không** thêm hệ số |
| ở giữa | báo nguyên trạng, để Lead quyết; mặc định DỪNG |

---

## Bước A7.5 (tuỳ chọn, phải được duyệt riêng) — mức ẩm `wfh`

Đây là chỗ lệch **thứ bảy**, tôi chưa tính vào Cách A vì nó đổi default:

- Paper §V: *"the water level is sampled from an exponential distribution from the interval
  0.1 − 1.2 mm during training."*
- Repo: cố định `wfh_mm = 1,0` — **đúng mức cao nhất** ("fully covered").
- Đo được: `T = 0,02·wfh·(v−50) + 0,2` ⇒ @100 km/h, `wfh=1,0` cho `T = 1,2 s`, `wfh=0,5` cho
  `T = 0,7 s` ⇒ số cụm sống giảm ~40 %.

**Cảnh báo chiều tác động:** hạ `wfh` làm plume **thưa hơn nữa**, mà Cách A đã cho 0,13× ở
scene 0060. Nên **không** làm cùng lượt. Chỉ mở nếu A5/A7 cho thấy plume vẫn **dày** ở một ô.

---

## Thứ tự và cái gì chặn cái gì

```
A0 (ADR) ──► A1 (field + method) ──► A2 (2 call site) ──► A3 (env switch) ──► A4 (3 test, 216)
                                                                    │
                                                                    ▼
                                              A5 (A3-V, 72 scene) ──► A6 (4 clip) ──► A7 (cổng C)
                                                                         │
                                                              A6 đọc trước: nếu static lệch => dừng
```

Ước lượng: A0 20 ph · A1 30 ph · A2 20 ph · A3 30 ph · A4 1 h · A5 12 ph · A6 40 ph (gồm
extract bag static) · A7 22 ph kernel + 20 ph bootstrap.

---

## Sáu điều cấm của Cách A

1. Không đổi **default** của bất kỳ field nào — bật bằng `PLUME_PAPER_DOMAIN`.
2. Không sửa `scripts/diag_*.py` (phải tái lập được số cũ).
3. Không lọc bên trong `raycast.py` — raycast phải thuần.
4. Không thêm `min_z_m` (đo được: cụm dưới mặt đường quá −0,3 m chỉ 0,0–0,1 %).
5. Không dùng `spawn_scale`/`density_scale` để bù độ thưa. Ghi limitation thay vào.
6. Không chạy A7 trước khi A0 đã commit.
