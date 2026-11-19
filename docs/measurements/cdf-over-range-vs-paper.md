# CDF khoảng cách detection 0–50 m — đúng thước Paper A Fig. 12, áp cho repo

Người đo: subagent đo lường. Ngày: **2026-11-19**. Nhánh `sspp`, HEAD `2c28fed` (working tree
sạch, không sửa `spray/`). Script: `scripts/measure_cdf_over_range.py`. Artifact:
`.scratch/tmp/cdf/{real_static,following,gen_static}.jsonl` + `cdf_summary.json` + `aggregate.out`.

## 0. TL;DR

1. **Following** (kịch bản production, ego chạy theo xe thật): CDF hai vế **cùng dạng thô** (dốc
   đứng trong 0–15 m rồi bão hoà ~20 m, trừ Golf 50–70 của vế sinh: CDF20 = 79,6 %) nhưng **không
   cùng phân bố**: KS = **0,24–0,43** tuỳ nhóm/lớp. Ở **≥80 km/h generator dồn về GẦN hơn thật**
   (p50 4,2–5,0 m so với 7,3–9,7 m; `%<10 m` 77–81 % so với 52–73 %). Ở **50–70 km/h generator XA
   hơn thật** (p50 9,5–16,2 m so với 7,9–9,7 m; `%<10 m` 26–53 % so với 52–72 %).
2. **Chiều lệch ngược với paper.** Paper tự chấp nhận *"detections in the simulation are visible at
   a greater distance"* ở 80–110 km/h (mô phỏng **xa hơn** thật). Repo lệch **gần hơn** ở 80–130 km/h
   — tức đúng dải paper nêu, nhưng **ngược dấu**. Paper **không công bố số** cho Fig. 12 nên không
   thể nói lệch của ta lớn hay nhỏ hơn lệch paper chấp nhận; chỉ so được **hướng** và **dải tốc độ**.
3. **Static (RoadSpray: ego đỗ, xe chạy ra xa) không dùng làm bằng chứng được.** CDF lệch rất lớn
   (KS **0,69–0,90**, sinh lệch phải 12–19 m, `%<10 m` = **0 %** so với 35–53 %) nhưng nguyên nhân
   chính là **dựng kịch bản**, không phải hình dạng plume: (a) generator không bao giờ đặt xe gần hơn
   18,4 m (mặt đuôi); (b) 10–31 % detection của generator nằm **trước** mặt đuôi xe (depth < 0,
   31 % trong tập frame rear ≤ 50 m) do `warm_start` giả lập lịch sử với **box đứng yên**; (c) độ sâu
   plume sau đuôi của generator chỉ đạt p50 = 1,7–9,6 m trong các frame xe còn gần, so với
   3,9–25,4 m của thật.
4. **Kết luận 1 câu:** CDF theo cự ly của generator **cùng xu hướng thô** với dữ liệu thật (cả hai dồn
   về gần và tắt sau ~20 m) nhưng **không cùng phân bố** — lệch nằm ở **đoạn 0–15 m** (near field),
   đổi dấu theo nhóm tốc độ, và ở 80–130 km/h lệch **ngược hướng** với lệch mà paper tự chấp nhận.

## 1. Đại lượng — đúng cái paper dùng

Paper (arXiv 2212.08558) **Fig. 12**, caption: *"Cumulative distribution of number of detections
over range in spray plume from a Crafter with different speeds at 50 m distance. The colors denote
the vehicle speed in km/h."* Hai panel (a) Measured / (b) Simulated; trục x = **detection distance
từ cảm biến, 0–50 m**; trục y = **CDF chuẩn hoá 0–1**. Text (L1064–1070): *"The distributions also
show the same trend in measurement and simulation… However, for medium speed from around 80 km/h to
110 km/h detections in the simulation are visible at a greater distance, so the attenuation is not
as strong as in the measurements for those speeds."* Và L1046: *"The origin of these plots is the
origin of the sensor."*

Vì vậy đại lượng đo ở đây là:

```
range = |p| = sqrt(x² + y² + z²)   từ gốc khung velodyne (không phải depth sau đuôi xe)
CDF(x) = P(range < x)              chuẩn hoá trong cửa sổ 0–50 m, bin 1 m
```

Paper chỉ kiểm **hình dạng CDF**, không định lượng từng bin, và **chấp nhận** một lệch phân bố theo
cự ly (sim xa hơn thật ở 80–110 km/h). Đây là thước để so.

## 2. Cách đo — bốn vế, cùng một tầng "detection của cảm biến"

| vế | nguồn | đơn vị | chọn mẫu | số dùng |
|---|---|---|---|---|
| THẬT static | RoadSpray `*_static` | residual spray sau trừ nền | bag xe **đang rời xa**, 3 bag/(lớp, tốc độ), 9 tốc độ, 2 lớp | **54 bag, 2 523 frame** |
| SINH static | `inject_plume_stateful` → `raycast_frame` (QĐ14: ego đứng yên, xe 18,5→200 m) | `RaycastResult.detections` | 3 seed × 9 tốc độ | **2 163 frame** |
| THẬT following | SSPP dynamic | điểm `label == 2` | 12 scene **không human box**, 30 frame cách đều/scene | **360 frame** |
| SINH following | cùng scene/frame, `PlumeContext` thật từng frame | `RaycastResult.detections` | seed cố định 20261119, paired | **360 frame** |

- **THẬT static** dùng lại nguyên pipeline T4 (`scripts/roadspray_static_depth_profile.py`): trừ nền
  range-image theo **mode** mỗi `(ring, az_bin 0,4°)`, RANSAC mặt đường (inlier 0,12 m), residual
  `|r − mode| > max(0,7 m; 2 %·r)`, `intensity ≤ 2`, loại hộp 3D thân xe (`geom`, nới sau 0,2 m),
  mask ngang ±5 m / cao 0,15–3,0 m, bỏ range ≤ 4 m, chỉ giữ `depth ≥ 0` sau mặt đuôi. Kiểm chứng
  chéo: depth profile của chính run này ra `%depth≤20` = 97,6 / 55,2 / 33,8 % và trail90 = 13 / 41 /
  49 m — khớp doc T4 (99,6 / 54,0 / 25,7 %; 6 / 44 / 52 m; khác bag).
- **THẬT following**: `label == 2` = *"spray and other noise artifacts"* (README) — giữ nguyên định
  nghĩa, có bảng đối chứng "chỉ trong vùng A3-V" ở §5 (khác ≤ 3 pp).
- **SINH static**: đúng `measure_plume_size_tail.py` (`_static_box`, `_static_context`,
  `production_table`, `PlumeConfig` mặc định, `RaycastConfig()` mặc định) — **không tune**.
- **SINH following**: đúng `measure_following_scenario.py` (cùng `build_sample_b`/`_sample_scene_indices`,
  cùng seed). **Đối chiếu dụng cụ:** 30/30 frame của scene `Crafter_dynamic/0001_2021-09-08-14-37-37_0`
  khớp **chính xác** `generated_total` trong `.scratch/tmp/following_b0.json` (0 lệch) ⇒ cùng toán tử.
- Cửa sổ 0–50 m: CDF chuẩn hoá **trong** cửa sổ; phần detection > 50 m báo riêng (`% >50 m`), không
  bỏ im lặng. Histogram lưu 0–250 m nên quartile toàn dải **không bị censor**.

12 scene following (tất định, đều **không box**): Crafter `0001(50) 0025(70) 0037(80) 0073(110)
0085(120) 0097(130)`, Golf cùng bộ số hiệu. Xe dẫn cách ego **p50 = 21,7–24,9 m**.

## 3. KẾT QUẢ A — following (kịch bản production; đây là phép so có nghĩa)

CDF (%) tại mốc, `%<10` = CDF(10). "thật" = `label==2`, "sinh" = detections.

| nhóm | lớp | frame | n det thật | n det sinh | CDF10 thật/sinh | CDF20 | CDF30 | CDF40 | CDF50 | KS | tại |
|---|---|---:|---:|---:|---|---|---|---|---|---:|---:|
| 50–70 | Crafter | 60 | 11 125 | 23 632 | **72,1 / 52,5** | 99,5 / 98,7 | 99,9 / 100 | 100 / 100 | 100 / 100 | 0,273 | 12 m |
| 80–110 | Crafter | 60 | 49 017 | 123 788 | **61,4 / 79,3** | 97,4 / 95,6 | 100 / 98,5 | 100 / 99,6 | 100 / 100 | 0,323 | 6 m |
| 120–130 | Crafter | 60 | 39 166 | 192 999 | **73,1 / 80,4** | 98,7 / 94,3 | 100 / 97,9 | 100 / 99,4 | 100 / 100 | 0,359 | 3 m |
| 50–70 | Golf | 60 | 9 970 | 5 498 | **52,2 / 26,0** | 95,1 / 79,6 | 99,8 / 100 | 99,9 / 100 | 100 / 100 | 0,392 | 14 m |
| 80–110 | Golf | 60 | 24 416 | 96 038 | **52,4 / 77,0** | 97,5 / 96,5 | 100 / 98,8 | 100 / 99,7 | 100 / 100 | 0,373 | 6 m |
| 120–130 | Golf | 60 | 19 043 | 155 363 | **58,3 / 78,6** | 96,3 / 93,8 | 99,8 / 97,6 | 100 / 99,3 | 100 / 100 | 0,421 | 6 m |
| 50–70 | gộp | 120 | 21 095 | 29 130 | 62,7 / 47,5 | 97,4 / 95,1 | 99,9 / 100 | 99,9 / 100 | 100 / 100 | 0,235 | 13 m |
| 80–110 | gộp | 120 | 73 433 | 219 826 | 58,4 / 78,3 | 97,4 / 96,0 | 100 / 98,7 | 100 / 99,6 | 100 / 100 | 0,336 | 6 m |
| 120–130 | gộp | 120 | 58 209 | 348 362 | 68,3 / 79,6 | 97,9 / 94,1 | 99,9 / 97,8 | 100 / 99,4 | 100 / 100 | 0,332 | 3 m |

Quantile (m; toàn dải, không censor) — p25 / p50 / p75, thật → sinh:

| nhóm | lớp | p25 | p50 | p75 |
|---|---|---|---|---|
| 50–70 | Crafter | 5,2 → 4,2 | **7,9 → 9,5** | 10,3 → 16,1 |
| 80–110 | Crafter | 5,2 → 2,6 | **8,7 → 4,5** | 12,2 → 8,8 |
| 120–130 | Crafter | 4,5 → 2,2 | **7,3 → 4,2** | 10,2 → 8,4 |
| 50–70 | Golf | 6,0 → 9,6 | **9,7 → 16,2** | 13,1 → 19,6 |
| 80–110 | Golf | 6,7 → 2,6 | **9,7 → 5,0** | 12,9 → 9,5 |
| 120–130 | Golf | 6,7 → 2,5 | **8,9 → 4,6** | 12,1 → 9,0 |

Đọc bảng:

- **Cùng xu hướng thô**: cả hai vế bão hoà ~20 m (CDF20 = 94–99,5 %, riêng Golf 50–70 vế sinh 79,6 %),
  `% >50 m` ≈ 0 (≤ 0,5 %). Toàn bộ khối lượng nằm trong **0–25 m** vì xe dẫn chỉ cách 22–25 m —
  **trục 30/40/50 m của paper gần như rỗng** ở dữ liệu này (khác hình học 50 m của paper).
- **Lệch tập trung ở 0–15 m** (chỗ KS đạt max: 3–14 m). Không phải lệch ở đuôi xa.
- **Đổi dấu theo tốc độ**: 50–70 km/h sinh **xa hơn** thật (`%<10` thấp hơn 15–26 pp, p50 xa hơn
  1,6–6,5 m — nặng nhất là Golf); 80–130 km/h sinh **gần hơn** thật (`%<10` cao hơn 7–25 pp, p50 gần
  hơn 3,1–4,7 m). Tức mô hình tăng mật độ near-field theo tốc độ **mạnh hơn** dữ liệu thật.
- Số detection sinh **2,5–8,2×** số thật ở 80–130 km/h (A3-V đã ghi nhận "quá đậm"); ở 50–70 là
  0,55× (Golf) và 2,1× (Crafter). CDF chuẩn hoá nên không bị ảnh hưởng bởi tổng số, chỉ bởi hình dạng.

## 4. KẾT QUẢ B — static (RoadSpray; KHÔNG phải hình học của paper)

`window_full` = chỉ frame có mặt đuôi xe ≤ 50 m (plume nằm trọn trong cửa sổ paper). Sinh là
Crafter (hộp 6,8 × 2,4 × 2,6 m); thật so với **Crafter**.

| nhóm | frame thật/sinh | n det thật/sinh | CDF10 | CDF20 | CDF30 | CDF40 | CDF50 | KS | tại |
|---|---:|---:|---|---|---|---|---|---:|---:|
| 50–70 | 238 / 183 | 51 012 / 18 363 | **46,9 / 0,0** | 85,5 / 22,7 | 100 / 76,1 | 100 / 91,9 | 100 / 100 | 0,691 | 17 m |
| 80–110 | 149 / 153 | 102 424 / 79 249 | **35,0 / 0,0** | 87,3 / 6,4 | 100 / 78,4 | 100 / 98,4 | 100 / 100 | 0,808 | 20 m |
| 120–130 | 56 / 57 | 59 427 / 60 118 | **52,7 / 0,0** | 92,1 / 1,7 | 100 / 68,1 | 100 / 99,2 | 100 / 100 | 0,903 | 20 m |

Quantile p25/p50/p75 (m): thật 7,2/10,8/17,4 · 8,9/12,3/16,3 · 7,3/9,6/14,8 → sinh
20,3/23,5/29,5 · 23,6/26,5/29,5 · 25,4/28,2/30,8. Sinh **lệch phải 12–19 m**, `%<10 m` = **0 %**
(so với 35–53 % của thật). Bỏ các detection nằm trước mặt đuôi (`depth < 0`, biến thể
`static_behind_window_full`) **không đổi kết luận**: KS 0,685 / 0,802 / 0,900.

**Vì sao lệch — ba nguyên nhân đo được, đều thuộc kịch bản chứ không phải hình dạng plume:**

1. **Độ sâu plume sau đuôi (chẩn đoán, không phải đại lượng paper)** — bin 1 m, `depth = rear − x`:

   | vế | 50–70 | 80–110 | 120–130 |
   |---|---|---|---|
   | thật static: p50 / %≤20 m | 3,9 m / 97,6 % | 18,7 m / 55,2 % | 25,4 m / 33,8 % |
   | sinh static (mọi frame): p50 / %≤20 m | 1,8 m / 98,5 % | 16,6 m / 56,8 % | 24,9 m / 41,2 % |
   | sinh static (rear≤50): p50 / %≤20 m | 1,7 m / 99,9 % | 7,9 m / 94,7 % | 9,6 m / 93,1 % |
   | % detection **trước** mặt đuôi (sinh) | 10,1 % | 14,1 % | 15,1 % |

   Trên **mọi frame**, phân bố depth của generator **khớp khá tốt** với thật (p50 1,8/16,6/24,9 so với
   3,9/18,7/25,4). Nhưng trong các frame **xe còn gần** (điều kiện để plume nằm trong 0–50 m) depth của
   generator chỉ 1,7–9,6 m, vì trail chưa kịp hình thành (xe bắt đầu ở 18,5 m và chạy ra).
2. **10–15 % detection của generator nằm TRƯỚC mặt đuôi** (`depth < 0`, tức trong/trước thân xe;
   31 % nếu chỉ lấy frame rear ≤ 50 m). Theo từng frame (100 km/h, seed 0): **45 % ở frame 0**, 33 %
   frame 2, 11 % frame 4, 0,2 % frame 8, 0 % từ frame 10. Nguyên nhân: `warm_start` chạy chu kỳ giả
   với **box đứng yên** trong khi cluster mang vận tốc vật thể nên trôi về phía trước ⇒ "lịch sử" bị
   đặt trước xe thay vì sau đuôi. Quan sát trên code hiện tại (`spray/plume_state.py:376`),
   **không sửa**, chỉ báo.
3. **Lịch trình khoảng cách xe khác nhau**: p50 khoảng cách mặt đuôi trong các frame dùng để đo là
   **48,9 / 76,9 / 89,3 m** (thật) so với **107,3 / 108,1 / 109,2 m** (sinh, tính trên toàn bộ frame).
   Với cùng một depth, range = car_range − depth, nên hai vế bị dịch theo lịch trình.

⇒ **Static không dùng để kết luận về mô hình plume.** Nó chỉ nói: trong kịch bản static hiện tại,
generator đặt spray ở 15–50 m trong khi plume thật (ego đỗ, xe đã chạy từ trước) nằm ở 4–17 m.

## 5. Đối chứng — biến thể "chỉ trong vùng A3-V"

Giới hạn cả hai vế trong vùng A3-V (0–60 m sau box, |y| ≤ 5 m, 0 ≤ z − road_z ≤ 3 m) thay vì toàn
frame: KS following = 0,30 / 0,33 / 0,37 (Crafter), 0,42 / 0,38 / 0,43 (Golf); `%<10 m` thật tăng
≤ 3 pp. Không đổi kết luận §3. `label==2` ngoài vùng (nhiễu khác) chỉ chiếm ≤ 5 % khối lượng.

## 6. So với lệch mà paper tự chấp nhận

| | paper (Fig. 12 + text) | repo (phép đo này) |
|---|---|---|
| đại lượng | CDF range 0–50 m, 2 panel | CDF range 0–50 m, bin 1 m |
| hình học | Crafter ở **50 m cố định**, ego chạy | following: xe dẫn **22–25 m**; static: ego đỗ, xe 18,5→200 m |
| kết luận của tác giả | *"the same trend in measurement and simulation"* | cùng xu hướng thô, **khác phân bố** |
| lệch được chấp nhận | **định tính, một dải**: 80–110 km/h sim **xa hơn** thật ("attenuation not as strong") | **định lượng**: KS 0,24–0,43; lệch **0–15 m**, đổi dấu theo tốc độ |
| dải lệch | chỉ 80–110 km/h | **cả 3 nhóm**, mạnh nhất 80–130 (gần hơn) và 50–70 Golf (xa hơn) |
| số của paper | **không công bố** (paper chỉ kiểm hình dạng, không định lượng bin) | — |

Hệ quả: **không thể nói lệch của ta lớn hơn hay nhỏ hơn lệch paper chấp nhận** — paper không cho số,
và bản arXiv không tách được 9 đường cong theo màu để số hoá (đã thử `pdftocairo -svg`: trang chứa
Fig. 12 chỉ có path đen/xám, không có `stroke` màu; môi trường này cũng không đọc được ảnh). Cái so được là **hướng**:
paper chấp nhận sim **xa hơn** thật ở 80–110 km/h; repo lệch **gần hơn** thật ở 80–130 km/h — **ngược
dấu ở đúng dải tốc độ paper nêu**, và thêm một lệch **cùng dấu** (sinh xa hơn) ở 50–70 km/h mà paper
không báo.

## 7. Kết luận (1 câu)

CDF theo cự ly của generator **cùng xu hướng thô** với dữ liệu thật (dồn về gần, bão hoà ~20 m) nhưng
**không cùng phân bố**: lệch KS 0,24–0,43 nằm ở **đoạn 0–15 m** (near field), sinh **gần hơn** thật
3–5 m ở 80–130 km/h và **xa hơn** 1,6–6,5 m ở 50–70 km/h; ở 80–110 km/h chiều lệch **ngược** với lệch
mà paper tự chấp nhận, còn kịch bản static thì lệch quá lớn (KS 0,69–0,90) vì lý do **dựng kịch bản**
nên không dùng làm bằng chứng.

## 8. Caveat

- **Hình học following khác paper**: xe dẫn 22–25 m (paper 50 m) ⇒ mốc CDF 30/40/50 m gần như rỗng ở cả
  hai vế; so sánh có ý nghĩa chỉ trong 0–20 m. Không thể tạo tập con "xe ở 50 m" từ SSPP.
- **Static confound** đã nêu ở §4 (2): `warm_start` + box đứng yên. Số static **không** dùng để kết
  luận mô hình; muốn dùng phải sửa kịch bản (ngoài phạm vi phép đo này).
- `label == 2` gồm cả *"other noise artifacts"*; bảng §5 cho thấy ảnh hưởng ≤ 3 pp.
- Mẫu: 54 bag / 2 523 frame (thật static), 12 scene / 360 frame (following, 2 scene/(lớp, nhóm)),
  2 163 frame (sinh static: 3 seed × 9 tốc độ, 51–131 frame/tốc độ/seed). Không tính CI cho KS (KS là
  một số cho cả phân bố, không có CI theo frame).
- Không tune tham số nào; mọi mặc định production. Không `git commit`.

## 9. Tái lập

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_cdf_over_range.py --mode real-static --bags-per-speed 3
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_cdf_over_range.py --mode following
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_cdf_over_range.py --mode gen-static --seeds 3
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/measure_cdf_over_range.py --mode aggregate
```

Thời gian: 4,5 phút (real-static) + 45 s (following) + 2,5 phút (gen-static) + 1 s (aggregate).
Artifact: `.scratch/tmp/cdf/real_static.jsonl` (2 523 dòng), `following.jsonl` (360 dòng, paired thật +
sinh từng frame), `gen_static.jsonl` (2 163 dòng), `cdf_summary.json`, `aggregate.out` (bảng đầy đủ,
gồm cả biến thể `static_all` và `following_region`).
