# Pseudo-3D-box từ nhãn semantic: có "unbox" được 171 scene SSPP không?

Đo xong · 2026-11-18 · nhánh `sspp` · task-6. Script + CSV: `.scratch/roadspray-cal/tmp/pseudo/`
(`lib.py`, `step1`…`step11`, `features.csv`, `final_eval.csv`, `unboxed_final.csv`). Không sửa file tracked nào.

## TL;DR

| | |
|---|---|
| `distance_to_object` ↔ box | khớp nhất với **mặt sau (near face)** `cx − sx/2`, δ ≈ −0,4 m ở frame đầu, **nhưng trôi ±3,8 m trong scene** → metadata không đặt được box, chỉ làm prior/gate |
| Pseudo box vs human box | **BEV IoU p5 = 0,847 / p50 = 0,931 / p95 = 0,977; 99,8 % frame ≥ 0,7**; 3D p50 = 0,872, 98,3 % ≥ 0,7 |
| Bias | centre −0,10/+0,08 m (p5/p95); z_bottom ±0,17 m; dims = hằng số/class (sd 0,003 m); yaw = 0 |
| Verdict | **dùng được cho TRAIN** (target noise ≪ detector error); **cấm cho test/val/metric** |
| Payoff | thêm **76 scene / 6.081 frame** (chỉ tốc độ train) → train 16→92 scene, 1.124→≈7.200 frame (**6,4x**) |

---

## 1. Human boxes: schema thật + hình học

`object_labels/lidar/<frame>.json` = JSON **list** (len 1) → `[].instances[]` (1 instance/frame;
8 frame có 2) → mỗi instance:

```
{"id": "<uuid>", "type": "3D_BOX",
 "contour": {"center3D": {"x","y","z"}, "pointN": int, "rotation3D": {"x","y","z"},
             "size3D": {"x","y","z"}},
 "className": "Car" | "Van" | "Other Vehicle"}
```

Class nằm **trong box JSON** (`className`), không cần `metadata.txt`. Đối chiếu: `Car` ↔
`object_name=Golf` (1.362 box), `Van` ↔ `Crafter` (1.225). 8 instance `Other Vehicle`
(10,13×3,92×2,55 m, đúng 8 frame 36–43 của Golf `0102`) bị `spray/sspp_adapter.py` drop
⇒ **2.587 box Car/Van = đúng 1 box/frame**; tổng instance trong file = 2.595.
36 scene có box đều `itr_after_water = 1`; 171 scene không box là `itr 2…6`.

**Dims** — hằng số gần tuyệt đối (campaign chỉ có 1 xe/class):

| class | size_x (length) | size_y (width) | size_z (height) |
|---|---|---|---|
| Car (Golf) | 4,250 ± 0,003 | 2,020 ± 0,003 | 1,501 ± 0,002 |
| Van (Crafter) | 6,829 ± 0,003 | 2,419 ± 0,041 | 2,621 ± 0,002 |

centre-y p5/p50/p95 = −0,41/−0,05/+0,31 m; yaw p5/p50/p95 = −0,053/−0,002/+0,068 rad
(chỉ 16/2.587 box |yaw| > 0,1; 480 frame |yaw| > 0,05 — cua ở 120 km/h); z_bottom
p5/p50/p95 = −0,585/−0,373/−0,161 (Car −0,396 ± 0,128; Van −0,340 ± 0,124) ⇒ z đáy **không
phải hằng số**, là mặt đường tại vị trí xe, trôi theo pitch của ego → phải ước lượng per-frame.

**Quan hệ `distance_to_object` ↔ box (câu hỏi chính).** So 3 giả thuyết trên 36 scene:

| giả thuyết | Car p50 | Van p50 | lệch 2 class |
|---|---:|---:|---:|
| tới centre: `cx − dist` | +0,87 | +2,70 | 1,83 m |
| tới **mặt sau**: `(cx − sx/2) − dist` | −1,25 | −0,71 | **0,54 m** |
| tới mặt trước: `(cx + sx/2) − dist` | +3,00 | +2,05 | 0,95 m |

⇒ khớp nhất là **đo tới mặt sau (near face)**, tham chiếu lidar origin (rear axle của ego).
Ở frame đầu mỗi scene: δ = (cx − sx/2) − dist có p5/p50/p95 = −3,40 / **−0,44** / +8,72 m
(Car −0,23; Van −0,98). Nhưng `distance_to_object` là **setpoint của campaign, không phải
measurement per-frame**: trong 1 scene δ trôi range p50 = **3,82 m** (p95 13,4 m), slope tới
±0,15 m/frame; median per-scene δ p5/p50/p95 = −3,61/−1,25/+1,11, sd 1,7 m; chỉ 13/36 scene
|median δ| ≤ 1 m. Hệ quả: đặt box chỉ bằng metadata → BEV IoU p50 = **0,544**, chỉ **29 %**
frame ≥ 0,7. **Vị trí thật phải lấy từ point cloud.**

## 2. `label==1` points: nhìn thấy gì của xe?

- Số điểm/frame p5/p50/p95 = **77 / 201 / 474** (min 49) → frame nào cũng có xe.
- Độ sạch: **99,1 %** điểm `label==1` nằm trong BEV human box (p5 96,4 %), 98,3 % trong 3D box
  ⇒ nhãn bám đúng xe, nhưng 1–2 % còn lại là **spray bị gán nhầm class 1**.
- Mặt nào thấy (đo trong hệ box human): **mặt sau** rõ nhất — mép sau cụm điểm nằm **0,15 m
  bên trong** mặt sau human box (p5 0,01/p95 0,28; fiducial ổn định theo class Car 0,13/Van 0,21).
  **Chiều dài không đo được**: depth nhìn thấy = 46 % length (Car, hatch/roof nghiêng) nhưng
  chỉ **6 %** (Van, mặt sau phẳng); `u_max − front face` p50 = −1,47 m (Car) / −2,08 m (Van).
  **Width** phủ 80 %/75 % ⇒ cần prior. **z**: điểm thấp nhất cao hơn đáy box 0,35 m (bumper),
  điểm cao nhất thấp hơn nóc 0,16 m ⇒ đáy box phải lấy từ ground plane.
- Tight-fit min/max điểm: BEV IoU p50 = **0,31**, **0 %** ≥ 0,7 ⇒ bắt buộc dùng class prior.
- **Failure mode**: spray giữa ego và xe bị gán class 1; có frame 640 điểm `label==1` nhưng
  cụm "xe" chỉ 64 % (Golf `0084` f28), cụm spray nằm gần ego hơn xe 1–11 m. DBSCAN 2D (BEV)
  bị "cầu spray" nối vào xe → min-x sai tới 4 m; **DBSCAN 3D** (eps 0,7 m) tách được:
  frame > 2 % contamination giảm 1,2 % → **0,3 %**.

## 3. Rule dựng pseudo box (chỉ dùng thứ có trong scene không box)

Input hợp lệ: `labels/*.label`, `velodyne/*.bin`, `metadata.txt` (`object_name`→class) + hằng
số per-class học từ 36 scene có box (campaign constant, không tune per-scene):

1. `m = (label==1)`, lấy `p = pts[m, :3]`.
2. **DBSCAN 3D** `eps=0,7 m, min_samples=8` trên `p`; giữ **cluster lớn nhất**; `purity = n_primary/n1`.
3. **Rear anchor** `a = percentile_2(x)` của cluster; `cx = a − δx + size_x/2`; `cy = median(y) + δy`.
4. `dims` theo class (bảng §1); **yaw = 0**.
5. **z_bottom**: fit plane `z = a + b·x + c·y` từ điểm `label==0` (road) trong
   `|y|<2, x∈[4, cx+8], z∈[−2,5;0,6]`, robust-refit ±0,35 m, eval tại `(cx,cy)`, cộng δz.
   Fallback: hằng số class.
6. **Gate**: chỉ nhận box khi `purity ≥ 0,7` và `n_primary ≥ 50`; fail → không có box (drop, không bịa).

| hằng số | Car | Van |
|---|---:|---:|
| `δx` (fiducial rear, m) | 0,134 | 0,206 |
| `δy` (lateral, m) | 0,015 | 0,080 |
| `δz` (đáy so với ground plane, m) | +0,005 | +0,089 |

Hằng số ổn định: 3-fold scene CV (fit 24 scene, test 12) cho δx Car **0,126–0,147**,
Van **0,200–0,212**; δz Van ≈ 0,08–0,10. Không tham số nào phụ thuộc scene. Runtime
≈ 45 ms/frame ⇒ dựng box cho 14.832 frame không box mất ~11 phút (1 lần).

## 4. Validate trên 36 scene có box (2.587 frame)

**Held-out 3-fold scene CV** (hằng số fit trên 24 scene, đo 12 scene còn lại): BEV IoU
**p5 = 0,844 / p50 = 0,929 / p95 = 0,976; ≥ 0,7 = 99,9 %; ≥ 0,5 = 100 %** (all-36:
0,847/0,931/0,977 — dims sd 0,003 m nên leakage không đáng kể).

| metric | p5 | p50 | p95 | ≥0,7 | ≥0,5 | <0,3 |
|---|---:|---:|---:|---:|---:|---:|
| BEV IoU | 0,847 | **0,931** | 0,977 | **99,8 %** | 100 % | 0,0 % |
| 3D IoU | 0,744 | **0,872** | 0,949 | 98,3 % | 99,9 % | — |

| nhóm | n | BEV p50 | BEV ≥0,7 | 3D p50 | 3D ≥0,7 |
|---|---:|---:|---:|---:|---:|
| Car / Van | 1362 / 1225 | 0,930 / 0,932 | 99,8 / 99,9 % | 0,869 / 0,874 | 98,2 / 98,4 % |
| 20 m / 30 m | 1321 / 1266 | 0,931 / 0,931 | 99,7 / 100 % | 0,875 / 0,867 | 98,6 / 97,9 % |
| 50–110 km/h | 2051 | 0,917–0,947 | 99–100 % | 0,844–0,890 | 96,6–100 % |
| 120 km/h | 242 | 0,912 | 99,2 % | 0,844 | **88,8 %** |
| 130 km/h | 248 | 0,913 | 100 % | 0,848 | 99,6 % |

**Bias hệ thống (pseudo − human)** — để biết model học lệch gì:

| thành phần | p5 | p50 | p95 | mean | sd |
|---|---:|---:|---:|---:|---:|
| centre_x | −0,104 | −0,000 | +0,083 | −0,016 | 0,40\* |
| centre_y | −0,124 | +0,000 | +0,134 | +0,002 | 0,08 |
| z_bottom | −0,175 | +0,000 | +0,143 | −0,006 | 0,098 |
| size_x / size_y / size_z | — | 0 | — | 0 | 0,003 / 0,029 / 0,002 |
| yaw | luôn 0 | | | human p5/p95 = −0,053/+0,068 | |

\* sd 0,40 do 1 frame catastrophic; bỏ frame đó sd ≈ 0,08. Tức **không có bias dịch chuyển**;
model "học lệch" chỉ là (i) đáy box ±0,15 m, (ii) yaw lượng tử hoá về 0, (iii) dims = class-mean
— mà chính human box cũng vậy (sd 0,003 m) nên (iii) **không phải bias** so với eval.

**10 frame tệ nhất** (trước gate): 1 frame catastrophic (Golf `0084` f28: cluster lớn nhất là
spray, purity 0,64 → **gate loại**); 9 frame còn lại IoU 0,50–0,76 do tàn dư spray dính cụm
(centre lệch −0,5…−1,4 m) hoặc cua 120 km/h |yaw| ≈ 0,1 rad. **Sau gate** `purity≥0,7 &
n_primary≥50` (giữ **99,7 %** frame): **99,9 %** frame còn lại ≥ 0,7, **0 frame < 0,3**.
Trên 171 scene không box: gate pass **99,7 %** frame, **170/171 scene** usable.

## 5. Verdict: dùng được cho TRAIN, không dùng được cho EVAL

**Ý tưởng sống, sống thoải mái.** BEV IoU p50 = 0,93 / 99,8 % ≥ 0,7 ngang một "second
annotator", không phải pseudo-label rác. Ba lý do:

1. Vị trí **không bịa**: rear face đo trực tiếp từ point cloud, sai số p5/p95 −0,10/+0,08 m —
   nhỏ hơn 2 % chiều dài xe.
2. Dims lấy từ prior per-class mà campaign chỉ có **một** xe/class ⇒ prior = truth (sd 0,003 m),
   không có domain gap hình học giữa pseudo và human.
3. Eval dùng human box của 36 scene **khác scene id** và ở `itr_1`; pseudo chỉ vào train ⇒
   target noise ±0,1 m ≪ sai số detector thật ở 20–30 m (hàng chục cm → mét).

**Được phép:** train detector (cls + box regression), tăng diversity water level/tốc độ, làm
ablation "more data". **Điều kiện:** (a) mỗi frame mang cờ `pseudo=True`, code eval **assert**
không thấy nó; (b) gate bật mặc định, frame fail drop chứ không nội suy; (c) giữ run
**human-only** làm baseline; (d) khai trong Limitations train là hỗn hợp human + pseudo.

**Cấm:** (i) test/val dưới mọi hình thức — 3D IoU 0,87 nghĩa là metric trên pseudo box bị chính
label noise chi phối, vô nghĩa; (ii) đo yaw/curvature (yaw luôn 0; 480 frame |yaw| > 0,05 sẽ dạy
model "xe luôn thẳng"); (iii) claim "207 scene có 3D box" — chỉ 36 scene có human box.

**Không sửa được bằng pseudo box:** 171 scene pseudo là `itr_after_water = 2…6`, eval là `itr 1`.
Spray level lệch: `label==2`/frame p50 của pseudo = 128–223 so với **378** (train human) và
**142** (test); p95 = 926–1.910 so với 2.502 / 2.111. Tức train pseudo **khô hơn** train human
hiện tại nhưng p50 gần test — covariate shift phải khai, không phải blocker. Nếu kết luận của
experiment là "spray gây FP" thì phải báo cáo riêng run human-only vs +pseudo.

Nếu IoU p50 < 0,5 thì ý tưởng chết; thực đo **0,93** nên không cần phương án cứu.

## 6. Payoff và split đề xuất

**Số frame thực có:** 207 scene / 17.419 frame. 36 scene human = 2.587 frame; 171 scene pseudo
= **14.832 frame**, trong đó ở tốc độ train {60,80,100,120} là **76 scene / 6.081 frame**
(60→20 scene/1.788 f; 80→16/1.343; 100→20/1.308; 120→20/1.642). Gate pass 99,7 % ⇒
**≈6.060 frame pseudo dùng được**.

**Split đề xuất (giữ tinh thần ADR-0005: test speed chưa từng thấy trong train):**

| vai | scene | frame | box nguồn |
|---|---:|---:|---|
| test | 12 human (50/90/130) | 954 | **human only** |
| val | 8 human (70/110) | 509 | **human only** |
| train | 16 human (60/80/100/120) | 1.124 | human |
| train | +76 pseudo (60/80/100/120, itr 2–6) | +≈6.060 | pseudo, gate bật |
| **train tổng** | **92 scene** | **≈7.180** | 6,4x frame, 5,8x scene |

**Không** đưa 55 scene không box ở 50/90/130 (5.066 frame) vào train — làm vậy train thấy đúng
3 tốc độ test ⇒ mất claim "unseen speed", chính là biến số của experiment. Không đưa 40 scene
70/110 (3.685 frame) vào train nếu muốn val còn ý nghĩa. Nếu chấp nhận đổi claim thành "cùng
lưới tốc độ, khác water iteration" thì dùng được cả 170/171 scene (14.786 frame, **14x**) —
nhưng đó là protocol khác, phải ghi rõ.

**Guardrail:** (1) `pseudo` flag + `scene_id` trong info dict, assert `pseudo == False` cho
val/test; (2) scene-level split đã disjoint sẵn (unboxed ∩ boxed = ∅); (3) log gate diagnostics
(`purity`, `n_primary`, `zsrc`) để audit; (4) báo cáo 2 run human-only (1.124 f) và human+pseudo
(≈7.180 f) — chênh lệch là câu trả lời cho "thiếu data có phải vấn đề không".
