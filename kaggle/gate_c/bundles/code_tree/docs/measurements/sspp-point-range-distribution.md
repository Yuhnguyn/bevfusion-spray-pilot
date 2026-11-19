# SSPP có giữ near-field không? — phân bố range của điểm thật và `label==2`

Mục đích: kiểm tra giả thuyết "ground truth SSPP bị lọc near-field" trước khi kết luận generator
quá đậm ở kịch bản following (A3-V: 8–17× ở 120–130 km/h). Đo trực tiếp `.bin` + `.label`, không
sửa code. Nguồn: `data/SemanticSprayDataset` (207 scene), script scratch
`.scratch/tmp/sspp_range_probe.py`; nhãn lớp theo `data/SemanticSprayDataset/README.txt`
(`0 background`, `1 leading vehicle`, `2 spray and other noise artifacts`).

## Cách đo

- 18 scene lấy từ **171 scene không human box** (3 scene/(lớp, nhóm tốc độ), chọn đều theo tên; khớp
  tập B của A3-V); 8 frame cách đều/scene ⇒ **144 frame**, 72 Crafter + 72 Golf.
- `velodyne/*.bin` reshape `(-1,5)`, `labels/*.label` int32; range = `sqrt(x²+y²+z²)` khung velodyne.
- Vùng "GT A3-V": `_region_mask` như `scripts/measure_following_scenario.py` (0–60 m sau box, |y|≤5,
  0≤z−road_z≤3 m), box dựng từ điểm `label==1` (pseudo-box, cùng cách A3-V tập B).
- Bin: 0–1, 1–2, 2–4, 4–6, 6–10, 10–20, ≥20 m.

## 1. Phân bố range — TẤT CẢ điểm vs `label==2` (144 frame, pooled)

| bin (m) | 0–1 | 1–2 | 2–4 | 4–6 | 6–10 | 10–20 | ≥20 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **all points %** | 0,00 | 0,62 | 1,61 | 3,60 | 8,64 | — | 85,54 (10–20 + ≥20) |
| **label==2 %** | 0,00 | 0,00 | **18,53** | 16,71 | 31,47 | — | 33,29 (10–20 + ≥20) |

Percentile (median qua các frame): all points p1/p5/p50 = **3,41 / 5,38 / 25,46 m**, min = **0,999 m**
(median min 1,017); `label==2` p1/p5/p50 = **3,71 / 3,73 / 6,81 m**, min toàn cục = **2,501 m**
(median min-theo-frame 3,1–3,8 m).

Thành phần nhãn theo bin range (đếm điểm): 1–2 m = 26 751 background + 2 vehicle + **0 spray**;
2–4 m = 61 213 background + 6 vehicle + **8 169 spray**. Tức điểm 1–2 m là **thân ego/nền**, không phải spray.
## 2. `label==2` trong vùng A3-V — near-field theo nhóm

| nhóm | lớp | scene | frame | `label2` vùng | % <2 m | % <4 m | % <10 m | min lab2 (median) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 50–70 | Crafter | 3 | 24 | 1 765 | **0** | 31,4 | 83,9 | 3,24 m |
| 50–70 | Golf | 3 | 24 | 1 272 | **0** | 25,6 | 69,3 | 3,82 m |
| 80–110 | Crafter | 3 | 24 | 14 135 | **0** | 21,3 | 69,5 | 3,22 m |
| 80–110 | Golf | 3 | 24 | 6 731 | **0** | 13,2 | 59,6 | 3,09 m |
| 120–130 | Crafter | 3 | 24 | 11 506 | **0** | 22,6 | 73,4 | 3,70 m |
| 120–130 | Golf | 3 | 24 | 6 789 | **0** | 11,5 | 61,2 | 3,74 m |

## 3. Trả lời 3 câu

**(a) SSPP raw có giữ điểm <2 m / <4 m không?** **CÓ, nhưng chỉ từ ~1 m và không có spray dưới
2,5 m.** Raw có 0,62 % điểm ở 1–2 m (min 0,999 m) và 2,23 % ở <4 m; nhưng toàn bộ 1–2 m là
background/ego, `label==2` bắt đầu từ **2,501 m**. Không có dấu hiệu lọc near-range trong `.bin`:
0–1 m = 4 điểm duy nhất (nhiễu số), tức dữ liệu bị chặn ở min-range cảm biến ~1 m, không phải do
lọc thân ego. Devkit có `ego_box_filter` (`tools/dataset/semantic_spray_dataset.py:145-148`,
`SIZE=2`, bỏ `|x|<2 & |y|<2`) nhưng nó chỉ bỏ **0,65 % tổng điểm và 0,00 % `label==2`** — và repo
đọc raw `.bin` (`spray/sspp_adapter.py:221` "not filtered here"), nên A3-V **không** dùng bộ lọc này.

**(b) `label==2` có ở range <4 m không, bao nhiêu %?** **CÓ** — 11,5–31,4 % `label==2` trong vùng
A3-V nằm ở 2–4 m (tuỳ lớp/tốc độ), nhưng **0 % ở <2 m**; min ~2,5 m. Vậy ground truth **có** near-field
spray (2–4 m), chỉ **trắng hoàn toàn dưới 2,5 m**.

**(c) Bao nhiêu % "đậm 8–17×" là do near-field GT không có, bao nhiêu là mô hình thật quá đậm?**
Dùng tỉ lệ A3-V (tập B) + % sinh <4 m/<10 m và GT ở bảng 2 (xấp xỉ vì % sinh tính toàn frame, GT tính
trong vùng — `[SUY LUẬN]`):

| nhóm | lớp | r_total | r_≥4m | r_≥10m | near-field <4 giải thích |
|---|---|---:|---:|---:|---:|
| 120–130 | Crafter | 16,92 | **11,11** | 12,02 | 34,4 % |
| 120–130 | Golf | 8,02 | **4,95** | 4,20 | 38,3 % |
| 80–110 | Crafter | 2,73 | 1,80 | 1,66 | 34,2 % |
| 80–110 | Golf | 4,63 | 3,07 | 2,52 | 33,7 % |
| 50–70 | Crafter | 1,98 | 2,43 | n/a | **không** (GT near-field còn nhiều hơn sinh) |
| 50–70 | Golf | 0,86 | 0,89 | n/a | **không** |

⇒ Near-field (GT thiếu spray <2,5 m, và ít hơn ở 2–4 m) chỉ giải thích **~34–38 %** phần đậm ở
120–130 km/h. **Phần lớn còn lại là mô hình thật quá đậm**: nếu chỉ so phần ≥4 m thì vẫn **5,0–11,1×**.
Kể cả giả định cực đoan rằng **toàn bộ** det <4 m của generator rơi vào vùng GT trắng (<2,5 m), phần
≥2,5 m vẫn đậm **4,4–8,6×** (Crafter 8,6; Golf 4,4). Ở 80–110 mức đậm thật còn **1,7–3,1×**; ở
50–70 near-field không phải vấn đề (GT near-field còn nhiều hơn generator), tỉ lệ vốn 0,9–2,0×.
## 4. Caveat

- Mẫu 18 scene/144 frame (khớp tập B A3-V), chưa tính CI cho % near-field GT; 3 scene/nhóm-lớp.
- `label==2` = "spray and other noise artifacts" (README) ⇒ có thể gồm noise khác spray.
- % sinh <4/<10 lấy từ A3-V (toàn frame), GT tính trong vùng A3-V; phân rã ở (c) là xấp xỉ, không phải
  paired exact — nhưng đủ để bác giả thuyết "GT bị lọc near-field là nguyên nhân chính".
- Không sửa code/generator/ADR; file sinh: `.scratch/tmp/sspp_range_probe.py`, `.scratch/tmp/sspp_range_probe.json`.
