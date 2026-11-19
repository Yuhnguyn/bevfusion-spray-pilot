# Mật độ spray ở kịch bản **following** — A3-V (2026-11-19)

Người đo: teammate `sspp-table-auditor` (R1), task-14. Script:
`scripts/measure_following_scenario.py`. Số liệu thô: `.scratch/tmp/following_scenario.json`.
Nhãn: `[ĐO]` đo trên máy này · `[CHỌN]` tự chọn · `[TÍNH]` suy ra từ số đo.

**Mục tiêu:** A3 nghiệm thu ở kịch bản **static** (ego đứng yên, xe chạy ra xa), nhưng
production (`spray/plume_transform.py`) chạy **following** (ego chạy theo xe SSPP thật). Cùng
một plume nhưng **góc khối khác** — cụm trôi tới gần cảm biến cho số tia cắt lớn hơn hàng chục
lần — nên số A3 **không suy ra** được mật độ ở kịch bản train (ADR-0006 §5.6). Đây là bước
**A3-V** trong ADR-0006; metric đã pre-register trước khi có số. Phép đo **thuần kiểm chứng**:
không tune, không sửa `spray/`.

## 1. Phương pháp `[ĐO]` / `[CHỌN]`

Với **mỗi frame** của scene SSPP:

| Thành phần | Cách làm |
|---|---|
| **Vùng đo** `[CHỌN]` | 0–60 m sau **box xe dẫn** (depth = rear_face − x); mask `|y| ≤ 5 m`, `0 ≤ z − road_z ≤ 3 m`. **Không** đếm cả frame. |
| **Tử số** | số `RaycastResult.detections` rơi trong vùng |
| **Mẫu số** | số điểm `label == 2` trong **cùng vùng** |
| **Metric chính** | `median_frame(tỉ lệ)` — median trên toàn bộ frame của nhóm; **CI95 bootstrap ở mức scene** (resample scene, B = 2000) |
| **Phụ (không chặn)** | depth profile 2 m/bin; % detection sinh ở range < 10 m và < 4 m; range xe p5/p50/p95 |

**Kịch bản following:** `PlumeContext` dựng từ **chính frame thật** — `ego_speed_mps` = metadata
`ego_velocity`, `object_speed_mps` = metadata `object_velocity`, vị trí xe: **human box** cho 36
scene có box; **pseudo box** `[CHỌN]` cho scene không box (scene không có human box): mặt sau =
percentile 2 của x trên điểm `label == 1` (điểm thân xe gần ego nhất), tâm = mặt sau + dài/2,
y = median, đáy = percentile 2 của z, dims theo lớp (Crafter 6,829×2,419×2,621; Golf
4,250×2,020×1,501). `PlumeState` **warm-start theo scene** (giống production), `inject_plume_stateful`
→ `raycast_frame(load_beam_table())`. **Cùng một seed cho mọi frame** (`20261119`) để paired;
30 frame cách đều/scene.

**Hai tập scene báo riêng:**
- **B — kiểm chứng sạch:** 4 scene/(group, tốc độ) trong **171 scene KHÔNG có box** ⇒ 72 scene
  (24 scene/nhóm tốc độ, cả 2 lớp). Không bao giờ nằm trong eval D1. **Đây là metric chính A3-V.**
- **A — tập eval (D1), mục phụ:** cả 36 scene có human box; chỉ để làm covariate cho cổng C.

## 2. Kết quả chính — tập **B** (171 scene không box) `[ĐO]`

| lớp | nhóm tốc độ | scene | frame | thật/frame | sinh/frame | **median sinh/thật [CI95]** |
|---|---|---:|---:|---:|---:|---|
| Crafter | 50–70 | 12 | 360 | 122,3 | 270,5 | **1,98 [1,58; 2,60]** |
| Golf | 50–70 | 12 | 360 | 119,7 | 121,2 | **0,86 [0,51; 1,68]** |
| Crafter | 80–110 | 16 | 480 | 812,4 | 2 192,6 | **2,73 [2,30; 3,14]** |
| Golf | 80–110 | 16 | 480 | 398,0 | 1 823,0 | **4,63 [3,97; 5,73]** |
| Crafter | 120–130 | 8 | 240 | 605,2 | 3 300,6 | **16,92 [13,88; 20,88]** |
| Golf | 120–130 | 8 | 240 | 464,8 | 2 786,4 | **8,02 [6,07; 11,64]** |

- Số frame có `label==2` trong vùng = 0 (bị loại khỏi median, không bịa tỉ lệ): 2 / 48 / 6 / 20 /
  0 / 13 tương ứng 6 dòng trên.
- **Near-field `[ĐO]`** (% trên **toàn bộ** detection sinh, không chỉ trong vùng):
  `< 10 m` = **39,6 / 50,1 / 81,5 / 78,0 / 81,1 / 79,7 %**;
  `< 4 m` = **15,9 / 22,9 / 48,2 / 42,4 / 49,2 / 45,4 %** (thứ tự như bảng).
- **Range xe** p5/p50/p95 (m): Crafter 22,3/23,5/26,8 · Golf 18,7/22,7/33,2 (50–70);
  Crafter 19,9/23,6/27,2 · Golf 19,2/21,5/31,3 (80–110); Crafter 21,3/24,6/30,6 ·
  Golf 19,6/22,0/33,2 (120–130).

⇒ **Kết luận 1 câu:** ở kịch bản following, generator **ĐẬM hơn** dữ liệu thật và mức đậm
**tăng theo tốc độ** — khoảng **0,9–2,0× ở 50–70 km/h** (CI rộng; Golf có thể ~1),
**2,7–4,6× ở 80–110**, và **8–17× ở 120–130** (tập B sạch).

## 3. Mục phụ — tập **A** (36 scene eval, covariate cổng C) `[ĐO]`

| lớp | nhóm tốc độ | scene | frame | thật/frame | sinh/frame | **median sinh/thật [CI95]** |
|---|---|---:|---:|---:|---:|---|
| Crafter | 50–70 | 6 | 180 | 264,4 | 195,3 | **0,80 [0,60; 1,23]** |
| Golf | 50–70 | 6 | 180 | 205,7 | 108,8 | **0,36 [0,13; 0,63]** |
| Crafter | 80–110 | 8 | 240 | 1 400,4 | 1 831,8 | **1,30 [1,10; 1,54]** |
| Golf | 80–110 | 8 | 240 | 486,2 | 1 556,8 | **3,50 [2,66; 4,67]** |
| Crafter | 120–130 | 4 | 120 | 1 078,2 | 3 061,4 | **4,61 [3,70; 8,12]** |
| Golf | 120–130 | 4 | 120 | 740,8 | 3 249,1 | **4,51 [3,53; 6,39]** |

**A và B lệch nhau rõ** (A thấp hơn ở mọi nhóm): A là scene `itr_after_water = 1` (nước đầy,
spray thật nhiều: 264 so với 122 điểm/frame @50–70) còn B là `itr 2–6` (khô hơn); thêm khác biệt
box human vs pseudo-box. ⇒ Không được trộn A và B; metric chính dùng **B**.

## 4. Depth profile 2 m/bin — % mass theo cửa sổ độ sâu `[ĐO]`

`thật / sinh` (%) trong vùng 0–60 m; bảng đầy đủ 30 bin nằm trong JSON.

| set | lớp | tốc độ | 0–10 m | 10–20 m | 20–30 m | 30–40 m | 40–50 m | 50–60 m |
|---|---|---|---|---|---|---|---:|---:|
| B | Crafter | 50–70 | 3,8 / **60,6** | 9,9 / 31,9 | 66,1 / 7,2 | 20,1 / 0,2 | 0,2 / 0,0 | 0,0 / 0,0 |
| B | Crafter | 80–110 | 16,2 / 8,6 | 23,9 / 41,3 | 41,6 / 40,4 | 17,5 / 7,4 | 0,8 / 1,8 | 0,0 / 0,5 |
| B | Crafter | 120–130 | 10,1 / 3,9 | 26,1 / 30,0 | 44,7 / 48,9 | 17,8 / 12,5 | 1,3 / 3,5 | 0,0 / 1,1 |
| B | Golf | 50–70 | 18,9 / **50,8** | 2,5 / 38,3 | 41,9 / 10,4 | 34,0 / 0,4 | 2,6 / 0,0 | 0,0 / 0,0 |
| B | Golf | 80–110 | 9,9 / 13,6 | 4,1 / 46,7 | 54,0 / 30,9 | 29,3 / 6,8 | 2,7 / 1,6 | 0,1 / 0,4 |
| B | Golf | 120–130 | 4,3 / 7,5 | 5,5 / 42,9 | 55,3 / 36,2 | 31,4 / 9,5 | 3,3 / 3,0 | 0,2 / 1,0 |

`[SUY LUẬN]` Ở **50–70 km/h**, generator dồn **50–61 %** detection vào 0–10 m sau đuôi trong khi
thật chỉ **4–19 %** — plume tổng hợp bám sát đuôi hơn thật (cùng gốc với limitation lifetime
@≤60 km/h của A3). Ở 80–130 km/h, hai phân bố gần nhau hơn nhưng generator vẫn **gần đuôi hơn**
(cửa sổ 10–20 m cao hơn thật) và ít đuôi xa hơn.

## 5. Caveats

1. **`label == 2` gồm cả noise** (spray + mưa/phản xạ, có thể từ nguồn khác) ⇒ vì vậy metric giới
   hạn trong vùng 0–60 m sau box xe dẫn; phần ngoài vùng không được đếm. Đây vẫn là xấp xỉ
   "spray thật" chứ không phải ground-truth spray thuần.
2. **SSPP là dynamic subset của chính RoadSpray** ⇒ phép đo này là **consistency check** giữa
   generator (calibrated trên RoadSpray static, D2) và dữ liệu SSPP following, **không phải OOD**.
3. **Pseudo box cho tập B** `[CHỌN]`: ước lượng mặt sau từ percentile 2 của x trên `label == 1`
   (campaign chỉ có một xe/lớp, |yaw| < 0,1 rad ở 531/534 box) — đủ để đặt vùng sinh, không phải
   box chính xác. Tập A dùng human box.
4. **Median thay vì mean**: tỉ lệ frame rất lệch (phân bố bursty); median là metric pre-register.
   Frame có `label==2` trong vùng = 0 bị loại khỏi median (số lượng ghi ở §2).
5. **Near-field tính trên toàn bộ detection sinh** (không chỉ trong vùng) — đây là chỉ số ô nhiễm
   near-field như task yêu cầu; `< 10 m`/`< 4 m` cao (tới 81 % / 49 %) cho thấy phần lớn detection
   sinh nằm sát cảm biến ở tốc độ cao.
6. **Không tune**: mọi tham số generator giữ nguyên bản production (diffusion α = 0,06, streak 0,
   `p_det_scale` 1,0). Phép đo này **không được dùng để chọn lại tham số** (D2-chặt; muốn dùng
   phải mở lại ADR).

## 6. Tái lập

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_following_scenario.py --frames-per-scene 30
# ~8–9 phút (36 scene A + 72 scene B × 30 frame), 1 process
```

`[ĐO]` md5 (2026-11-19):
`scripts/measure_following_scenario.py` = `61d6fac90a75968f28645f85f4708d5e` ·
`.scratch/tmp/following_scenario.json` = `31f62749665f280e6ff3f118cd0c0a54` ·
`spray/plume_state.py` = `8c3ae8cac572490c663b9aa8aab8af05` ·
`spray/raycast.py` = `8c58faf81903f0369f12220ebf90f098` ·
`spray/beam_model.py` = `38acb4b9dc659a7cfb7635589f038710` ·
`spray/sspp_adapter.py` = `02be8a6a5d2cde951b3b62d94ba8d37b`.
