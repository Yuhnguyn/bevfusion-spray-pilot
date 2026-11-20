# Cụm/frame SSPP theo fold — không leak, có CI95 (2026-11-18)

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S3, S5.
> Phần còn đúng: Bảng fold vẫn dùng được làm KIỂM CHỨNG CHÉO, không còn là nguồn chọn tham số.

Người đo: teammate `sspp-table-auditor` (task 7), Lead review. Nhánh `sspp`.
Script: `scripts/sspp_cluster_table_folds.py` · Test: `tests/test_sspp_cluster_table_folds.py`.
Nguồn dữ liệu: `data/SemanticSprayDataset` (**207 scene / 17 419 frame**).
Nhãn: `[ĐO]` đo trên máy này · `[CHỌN]` tự chọn · `[TÍNH]` suy ra từ số đo ·
`[GIẢ ĐỊNH]` giả định phải khai.

Mục đích: **sửa chẩn đoán V2** (bảng `_CLUSTER_VISIBLE_BY_SPEED` trong
`spray/plume.py` đo trên `cal`, mà `cal` chứa 6/12 scene test) bằng một bảng
cụm/frame SSPP **không leak** theo protocol 3-fold leave-speed-out của
ADR-0006 D1 — dùng làm **kiểm chứng chéo** cho bảng calibration RoadSpray
`*_static` (ADR-0006 **D2**), **không** thay bảng calibration.

---

## 0. TL;DR

1. **3 bảng fold** (mỗi bảng 9 tốc độ × Crafter/Golf; 10–12 scene/ô,
   150–180 frame/ô, trừ Golf 80/90 chỉ có 8/7 scene toàn dataset; CI95 bootstrap
   ở mức scene B = 2000): bảng của fold k
   **không chứa** bất kỳ scene test nào của fold k — `--check` chứng minh,
   54/54 ô sạch leak.
2. **Bảng gộp 3 fold `[ĐO]`**: Crafter đỉnh **21,63** cụm/frame @100 km/h
   [17,16; 26,38], thấp nhất **4,84** @50; Golf đỉnh **14,76** @100
   [13,34; 16,50], thấp nhất **3,78** @50. CI95 half-width của 18 ô: median
   **15,3 %**, max **29,1 %**.
3. **Bảng 45-frame cũ lệch bao nhiêu `[ĐO]`**: so với bảng gộp, |Δ| trung bình
   **24,7 %** (Crafter, max 37,3 %) và **11,3 %** (Golf, max 21,7 %); bảng cũ
   **cao hơn** ở 8/9 tốc độ Crafter (tỉ lệ mới/cũ 0,63–0,91). Không phải vì
   recipe: dựng lại đúng protocol cũ (`cal`, ô 20 m, 3 scene/ô, 45 frame) khớp
   số commit tới **5,6 % / 3,3 %** (Crafter/Golf).
4. **Nguyên nhân lệch là chọn mẫu, không phải fold**: ô `cal` 20 m của bảng cũ
   là mẫu "gần + nước khác"; bảng gộp không leak buộc phải có 10 scene không
   box `itr 2–6` (khô hơn trung bình **1,40×**, 0,84–2,16×). Ở **đúng điều kiện
   eval** (2 scene/ô `itr = 1`) SSPP khớp bảng cũ **12,2 %** (Crafter) → độ lớn
   của bảng cũ không sai, cái sai là **45 frame + leak**.
5. **3 fold ổn định**: nơi 2 fold dùng cùng bộ scene, giá trị **trùng khít**
   (cùng dữ liệu, không phải bằng chứng thống kê); chỗ thực sự khác là fold
   test đúng tốc độ đó chỉ còn 10 scene không box — spread trung bình **6,6 %**,
   median **5,8 %**, max **16,2 %**.
6. **Không tồn tại bảng SSPP 9 tốc độ hợp lệ cho một fold ở điều kiện eval**:
   mỗi fold chỉ có **6/9 mốc** có scene `itr = 1`; 3 mốc held-out **không còn
   scene `itr = 1` nào ngoài test set**. Nếu buộc dùng SSPP-only và nội suy 3
   mốc đó, sai số |Δ| trung bình **16,7 %** (median 7,0 %, max 103,3 % ở 50 km/h
   của fold 1, nơi `spray/plume.py` sẽ trả **0,0** vì dưới mốc đầu). Đây đúng
   là lỗ hổng D2 mà bảng RoadSpray `*_static` lấp.
7. **Kết luận `[CHỌN]`**: giữ bảng RoadSpray static làm nguồn calibration
   (D2); dùng bảng fold này làm kiểm chứng chéo (cùng hình dạng: r = 0,95 với
   bảng cũ, r = 0,77 với static); **không** thay `_CLUSTER_VISIBLE_BY_SPEED`
   bằng bảng gộp 12 scene vì bảng đó là "scene trung bình", thấp hơn điều kiện
   eval ~1,2–1,4× tuỳ lớp/tốc độ.

---

## 1. Vì sao phải tính lại (V2)

`_CLUSTER_VISIBLE_BY_SPEED` (`spray/plume.py:24-47`) đo trên SSPP `cal` với
**15 frame/scene × 3 scene/ô = 45 frame/ô**. V2 của dự án: `cal` chứa scene
test, nên tham số generator được chọn trên chính điều kiện sẽ chấm.

`[ĐO]` Kiểm lại trên dữ liệu hiện tại (split model cũ test = 50/90/130 km/h,
12 scene có box): **6/12 scene test là `cal` = 503/954 frame (52,7 %)**; mỗi
tốc độ test có 2/4 scene là `cal`. Khớp `docs/adr/0006` và
`.scratch/roadspray-cal/spec.md` §0.

Vì vậy cần một bảng cụm/frame SSPP:
- **không leak**: bảng dùng để chấm fold k không được chứa scene test của fold k;
- **cùng recipe đo** với bảng cũ để so sánh được (§3);
- **đủ mẫu**: ≥ 10 scene và ≥ 150 frame mỗi ô, thay vì 3 scene / 45 frame.

---

## 2. Fold của protocol (ADR-0006 D1) — dựng mới trong script này `[ĐO]`

ADR-0006 D1 chốt: **3-fold leave-speed-out trên 36 scene có human box**;
rule tất định `fold = rank(speed) mod 3 + 1` trên 9 tốc độ 50…130 km/h, với
`rank` đếm từ 0. `[ĐO]` Trước task này **rule fold chưa tồn tại trong code**
(`grep -rn "fold" spray/ scripts/` không có), nên nó được dựng trong
`scripts/sspp_cluster_table_folds.py` (`fold_for_speed`) và **kiểm chứng
ngược** với bảng E1 của `.scratch/roadspray-cal/plan.md`:

| fold | tốc độ held-out | test scene | test frame `[ĐO]` | E1 ghi | khớp |
|---:|---|---:|---:|---:|:---:|
| 1 | 50, 80, 110 | 12 | 886 | 886 | ✅ |
| 2 | 60, 90, 120 | 12 | 893 | 893 | ✅ |
| 3 | 70, 100, 130 | 12 | 808 | 808 | ✅ |

Trong 207 scene của dataset: **36 scene có human box** (2 scene mỗi
group/tốc độ: 1 ở cự ly 20 m + 1 ở 30 m, đều `itr_after_water = 1`);
**171 scene không box** là dữ liệu train (`itr 2–6`). Khi đánh giá fold k, test
set = 12 scene có box ở 3 tốc độ held-out; bảng của fold k được phép dùng
**mọi scene của dataset trừ 12 scene đó** ⇒ mỗi ô còn **12 scene** (tốc độ không
held-out) hoặc **10 scene** (tốc độ held-out, vì 2 scene có box đều là test).
`[CHỌN]` Đây là cách duy nhất đạt ≥ 10 scene/ô: nếu chỉ dùng 24 scene train có
box thì mỗi ô chỉ có 2 scene / 30 frame.

**Phải khai `[GIẢ ĐỊNH]`:** ô ở tốc độ held-out của fold k chỉ có scene
**không box** — các scene này *không* thuộc test set (đúng nghĩa "không leak"
theo scene) nhưng **cùng tốc độ, cùng chiến dịch**. Đây là non-leak ở mức
scene, **không** phải non-leak ở mức tốc độ. Vì vậy bảng fold không được dùng
làm nguồn calibration cho chính fold đó; §8 đọc chặt hơn và đo sai số nội suy.

---

## 3. Dữ liệu + recipe đo `[ĐO]` / `[CHỌN]`

| fold | tốc độ held-out | scene test | frame test | scene train có box | frame train có box | scene dùng được |
|---:|---|---:|---:|---:|---:|---:|
| 1 | 50, 80, 110 | 12 | 886 | 24 | 1701 | 195 |
| 2 | 60, 90, 120 | 12 | 893 | 24 | 1694 | 195 |
| 3 | 70, 100, 130 | 12 | 808 | 24 | 1779 | 195 |

Recipe: `label == 2`; DBSCAN `(azimuth, elevation)` eps = 0,7°, minPts = 3, elevation snap 0,333°, azimuth wrap; 15 frame cách đều/scene; bootstrap mức scene B = 2000, seed = 20261118.

**Recipe giữ y nguyên bảng cũ `[CHỌN]`** (để so sánh được): chỉ điểm
`label == 2`; DBSCAN trên mặt phẳng `(azimuth, elevation)` với `eps = 0,7°`,
`minPts = 3`, elevation snap `0,333°`, azimuth wrap — gọi thẳng
`spray.semantic_stats.cluster_angular` đúng như bảng gốc; **15 frame cách đều
mỗi scene** (cùng độ dày mẫu/scene với bảng cũ); mỗi frame bị bỏ nếu
`labels.size != points.shape[0]` (**0** frame bị bỏ `[ĐO]`).

Hai điểm khác bảng cũ, đều là `[CHỌN]` có khai:
1. **Số scene/ô 10–12** thay vì 3 — để CI95 đủ hẹp và đạt ngưỡng mẫu của task.
2. **CI95 = percentile bootstrap ở mức scene** (B = 2000, seed = 20261118,
   resample scene có hoàn lại, giữ nguyên toàn bộ frame của scene được bốc) —
   không resample frame, vì frame trong cùng scene không độc lập
   (ICC 0,14 cho clusters/frame — `.scratch/roadspray-cal/power-design.md` §1).
   Point estimate là **mean gộp theo frame** (giống bảng cũ 45 frame), không
   phải trung bình per-scene.

Ghi chú thêm `[ĐO]`: 15 frame/scene ⇒ mỗi scene đóng góp đều như nhau (mọi
scene ≥ 39 frame); 36 scene eval đều `itr = 1`, 171 scene còn lại `itr 2–6` —
ảnh hưởng của nước được tách riêng ở §6 và §9.

---

## 4. Bảng 3 fold `[ĐO]`

Mỗi bảng dưới là bảng **mà fold đó được phép dùng**: dòng có dấu **†** là tốc
độ held-out của fold — 4 scene test bị loại, ô chỉ còn 10 scene không box.

### Fold 1 — test 50, 80, 110 km/h [ĐO]

| km/h | Crafter scene/frame | Crafter cụm/frame [CI95] | Golf scene/frame | Golf cụm/frame [CI95] |
|---:|---:|---:|---:|---:|
| 50 † | 10/150 | 4,75 [3,98; 5,71] | 10/150 | 3,35 [2,43; 4,35] |
| 60 | 12/180 | 8,48 [7,06; 10,07] | 12/180 | 8,12 [6,76; 9,57] |
| 70 | 12/180 | 12,90 [11,29; 15,15] | 12/180 | 10,85 [9,87; 11,89] |
| 80 † | 10/150 | 15,66 [12,40; 18,39] | 6/90 | 12,76 [11,66; 13,86] |
| 90 | 12/180 | 19,03 [17,11; 21,09] | 7/105 | 11,84 [10,67; 12,98] |
| 100 | 12/180 | 22,21 [17,86; 26,95] | 12/180 | 14,73 [13,31; 16,36] |
| 110 † | 10/150 | 16,00 [10,29; 20,80] | 10/150 | 12,63 [10,37; 14,89] |
| 120 | 12/180 | 13,37 [10,45; 16,73] | 12/180 | 14,31 [12,82; 15,72] |
| 130 | 12/180 | 13,44 [11,34; 15,65] | 12/180 | 13,97 [11,93; 16,01] |

† = tốc độ held-out của fold này: 4 scene test (2 scene/group) bị loại, ô chỉ còn 10 scene không box (`itr_after_water` 2–6) — trừ Golf 80/90 của dataset chỉ có 8/7 scene nên ô còn 6/5 scene.

### Fold 2 — test 60, 90, 120 km/h [ĐO]

| km/h | Crafter scene/frame | Crafter cụm/frame [CI95] | Golf scene/frame | Golf cụm/frame [CI95] |
|---:|---:|---:|---:|---:|
| 50 | 12/180 | 4,88 [4,16; 5,73] | 12/180 | 3,99 [2,77; 5,39] |
| 60 † | 10/150 | 7,88 [6,35; 9,23] | 10/150 | 7,91 [6,43; 9,58] |
| 70 | 12/180 | 12,90 [11,29; 15,15] | 12/180 | 10,85 [9,87; 11,89] |
| 80 | 12/180 | 16,78 [13,57; 19,79] | 8/120 | 12,40 [11,46; 13,41] |
| 90 † | 10/150 | 18,25 [16,38; 20,35] | 5/75 | 12,40 [10,92; 13,53] |
| 100 | 12/180 | 22,21 [17,86; 26,95] | 12/180 | 14,73 [13,31; 16,36] |
| 110 | 12/180 | 18,78 [12,76; 24,34] | 12/180 | 13,29 [11,17; 15,22] |
| 120 † | 10/150 | 11,51 [9,44; 13,97] | 10/150 | 13,76 [12,43; 14,95] |
| 130 | 12/180 | 13,44 [11,34; 15,65] | 12/180 | 13,97 [11,93; 16,01] |

† = tốc độ held-out của fold này: 4 scene test (2 scene/group) bị loại, ô chỉ còn 10 scene không box (`itr_after_water` 2–6) — trừ Golf 80/90 của dataset chỉ có 8/7 scene nên ô còn 6/5 scene.

### Fold 3 — test 70, 100, 130 km/h [ĐO]

| km/h | Crafter scene/frame | Crafter cụm/frame [CI95] | Golf scene/frame | Golf cụm/frame [CI95] |
|---:|---:|---:|---:|---:|
| 50 | 12/180 | 4,88 [4,16; 5,73] | 12/180 | 3,99 [2,77; 5,39] |
| 60 | 12/180 | 8,48 [7,06; 10,07] | 12/180 | 8,12 [6,76; 9,57] |
| 70 † | 10/150 | 11,82 [10,67; 13,09] | 10/150 | 10,55 [9,55; 11,47] |
| 80 | 12/180 | 16,78 [13,57; 19,79] | 8/120 | 12,40 [11,46; 13,41] |
| 90 | 12/180 | 19,03 [17,11; 21,09] | 7/105 | 11,84 [10,67; 12,98] |
| 100 † | 10/150 | 20,47 [15,90; 25,75] | 10/150 | 14,81 [13,29; 16,69] |
| 110 | 12/180 | 18,78 [12,76; 24,34] | 12/180 | 13,29 [11,17; 15,22] |
| 120 | 12/180 | 13,37 [10,45; 16,73] | 12/180 | 14,31 [12,82; 15,72] |
| 130 † | 10/150 | 12,30 [10,55; 14,11] | 10/150 | 13,02 [10,97; 14,83] |

† = tốc độ held-out của fold này: 4 scene test (2 scene/group) bị loại, ô chỉ còn 10 scene không box (`itr_after_water` 2–6) — trừ Golf 80/90 của dataset chỉ có 8/7 scene nên ô còn 6/5 scene.

---

## 5. Bảng gộp 3 fold + CI95 `[ĐO]`

Bảng gộp = trung bình 3 giá trị bảng fold của cùng ô (2 fold dùng cả 12 scene,
fold test đúng tốc độ đó dùng 10 scene không box); CI95 được tính bằng bootstrap
ở mức scene **dùng cùng một lần resample cho cả 3 fold** để giữ tương quan.
Cột "tất cả scene" và "bỏ scene boxed" là hai thành phần để audit.


#### Crafter

| km/h | n scene | n frame | gộp 3 fold [CI95] | tất cả scene [CI95] | bỏ scene boxed [CI95] |
|---:|---:|---:|---:|---:|---:|
| 50 | 12 | 180 | 4,84 [4,14; 5,75] | 4,88 [4,16; 5,73] | 4,75 [3,98; 5,71] |
| 60 | 12 | 180 | 8,28 [6,89; 9,68] | 8,48 [7,06; 10,07] | 7,88 [6,35; 9,23] |
| 70 | 12 | 180 | 12,54 [11,19; 14,21] | 12,90 [11,29; 15,15] | 11,82 [10,67; 13,09] |
| 80 | 12 | 180 | 16,41 [13,29; 19,23] | 16,78 [13,57; 19,79] | 15,66 [12,40; 18,39] |
| 90 | 12 | 180 | 18,77 [16,87; 20,59] | 19,03 [17,11; 21,09] | 18,25 [16,38; 20,35] |
| 100 | 12 | 180 | 21,63 [17,16; 26,38] | 22,21 [17,86; 26,95] | 20,47 [15,90; 25,75] |
| 110 | 12 | 180 | 17,85 [12,43; 22,63] | 18,78 [12,76; 24,34] | 16,00 [10,29; 20,80] |
| 120 | 12 | 180 | 12,75 [10,26; 15,46] | 13,37 [10,45; 16,73] | 11,51 [9,44; 13,97] |
| 130 | 12 | 180 | 13,06 [11,14; 14,94] | 13,44 [11,34; 15,65] | 12,30 [10,55; 14,11] |

#### Golf

| km/h | n scene | n frame | gộp 3 fold [CI95] | tất cả scene [CI95] | bỏ scene boxed [CI95] |
|---:|---:|---:|---:|---:|---:|
| 50 | 12 | 180 | 3,78 [2,74; 4,94] | 3,99 [2,77; 5,39] | 3,35 [2,43; 4,35] |
| 60 | 12 | 180 | 8,05 [6,66; 9,53] | 8,12 [6,76; 9,57] | 7,91 [6,43; 9,58] |
| 70 | 12 | 180 | 10,75 [9,80; 11,77] | 10,85 [9,87; 11,89] | 10,55 [9,55; 11,47] |
| 80 | 8 | 120 | 12,52 [11,50; 13,52] | 12,40 [11,46; 13,41] | 12,76 [11,66; 13,86] |
| 90 | 7 | 105 | 12,03 [10,72; 13,10] | 11,84 [10,67; 12,98] | 12,40 [10,92; 13,53] |
| 100 | 12 | 180 | 14,76 [13,34; 16,50] | 14,73 [13,31; 16,36] | 14,81 [13,29; 16,69] |
| 110 | 12 | 180 | 13,07 [10,90; 15,11] | 13,29 [11,17; 15,22] | 12,63 [10,37; 14,89] |
| 120 | 12 | 180 | 14,12 [12,77; 15,40] | 14,31 [12,82; 15,72] | 13,76 [12,43; 14,95] |
| 130 | 12 | 180 | 13,65 [11,65; 15,52] | 13,97 [11,93; 16,01] | 13,02 [10,97; 14,83] |

CI95 half-width của 18 ô gộp: median **15,3 %**, max **29,1 %** (ô hẹp nhất 8,0 %).

---

## 6. Điều kiện eval: chỉ scene có box (`itr = 1`) `[ĐO]`

Đây là phần quan trọng nhất khi so với bảng cũ và bảng RoadSpray static: cả hai
đều đo ở điều kiện `itr = 1` (nước đầy), còn 10 scene không box của dataset
là `itr 2–6` (**khô hơn**, xem §9). Ô "eval" = 2 scene có box mỗi
(group, tốc độ) = 30 frame/ô — dùng được ở fold **không** test tốc độ đó
(2 scene này là scene train của fold), và **không có** ở fold test đúng tốc độ
đó (dấu —). Đây là **lỗ hổng D2**: mỗi fold chỉ có 6/9 mốc tốc độ đúng điều
kiện eval.

Cột "dải 2 scene" là min–max của 2 giá trị per-scene, không phải CI95 — n = 2
thì bootstrap không có nghĩa.

36 scene eval đều `itr = 1`. Bảng dưới là ô 2 scene/ô (30 frame) — đúng điều kiện eval nhất, dùng được ở fold **không** test tốc độ đó (2 scene có box đều là scene train của fold). Ở fold test đúng tốc độ đó, không còn scene `itr = 1` nào ngoài test set ⇒ dấu **—** (đây là lỗ hổng D2 mà bảng RoadSpray static lấp). Cột "dải" là 2 giá trị per-scene, không phải CI.

#### Crafter

| km/h | bảng cũ 45-frame | fold 1 | fold 2 | fold 3 | cả 12 scene | dải 2 scene | static (D2) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 4,18 | — | 5,57 | 5,57 | 5,57 | 5,33–5,80 | — |
| 60 | 11,31 | 11,50 | — | 11,50 | 11,50 | 8,80–14,20 | — |
| 70 | 17,42 | 18,30 | 18,30 | — | 18,30 | 14,33–22,27 | 19,80 |
| 80 | 22,02 | — | 22,37 | 22,37 | 22,37 | 18,07–26,67 | 29,30 |
| 90 | 20,69 | 22,90 | — | 22,90 | 22,90 | 20,53–25,27 | 31,40 |
| 100 | 29,24 | 30,93 | 30,93 | — | 30,93 | 29,47–32,40 | 28,10 |
| 110 | 28,49 | — | 32,67 | 32,67 | 32,67 | 29,07–36,27 | 30,20 |
| 120 | 17,58 | 22,67 | — | 22,67 | 22,67 | 18,40–26,93 | 15,00 |
| 130 | 17,69 | 19,13 | 19,13 | — | 19,13 | 18,60–19,67 | 24,20 |

#### Golf

| km/h | bảng cũ 45-frame | fold 1 | fold 2 | fold 3 | cả 12 scene | dải 2 scene |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 3,62 | — | 7,23 | 7,23 | 7,23 | 5,07–9,40 |
| 60 | 8,84 | 9,17 | — | 9,17 | 9,17 | 8,07–10,27 |
| 70 | 11,36 | 12,37 | 12,37 | — | 12,37 | 10,33–14,40 |
| 80 | 12,87 | — | 11,33 | 11,33 | 11,33 | 10,60–12,07 |
| 90 | 10,51 | 10,43 | — | 10,43 | 10,43 | 10,20–10,67 |
| 100 | 18,07 | 14,30 | 14,30 | — | 14,30 | 11,80–16,80 |
| 110 | 16,69 | — | 16,63 | 16,63 | 16,63 | 15,93–17,33 |
| 120 | 15,27 | 17,03 | — | 17,03 | 17,03 | 14,60–19,47 |
| 130 | 16,64 | 18,70 | 18,70 | — | 18,70 | 17,07–20,33 |

---

## 7. Bảng 45-frame cũ lệch bao nhiêu `[ĐO]`

Doc cũ ghi mỗi ô "15 frame/scene × 3 scene/ô" nhưng **không commit script đo**,
và không ghi rõ "ô" là gì. `[ĐO]` Dựng lại 3 cách đọc bằng đúng recipe và đúng
15 frame/scene (dùng lại cache đo của 207 scene):

| cách dựng lại | Δ trung bình so với số commit | max |
|---|---:|---:|
| `cal`, **ô 20 m**, 3 scene × 15 frame | **5,6 %** (Crafter) / **3,3 %** (Golf) | 13,3 % / 11,1 % |
| `cal`, ô 30 m, 3 scene × 15 frame | 40,1 % / 23,2 % | 54,9 % / 37,8 % |
| `cal`, cả 2 cự ly (6 scene) | 22,6 % / 12,2 % | 30,3 % / 20,8 % |

⇒ `[TÍNH]` Bảng cũ thực chất là **ô 20 m của `cal`** (3 scene/ô), không phải
trung bình 2 cự ly; phần dư 5,6 % là do script gốc chọn frame hơi khác (không
còn trong repo) — cùng bậc dao động lấy mẫu của 45 frame.

`[ĐO]` So sánh với bảng mới:

Bảng cũ = số commit trong `docs/measurements/semantic-spray-clusters-by-speed.md` Bảng 1 (đo trên `cal`, 45 frame/ô). Script đo bảng cũ không có trong repo; cột "dựng lại cal 20 m" là phép dựng lại trung thực nhất theo phần Phương pháp của doc cũ — 15 frame/scene, 3 scene `cal` của **ô 20 m** (đúng 45 frame/ô), cùng recipe đo.

#### Crafter

| km/h | bảng cũ (commit) | dựng lại cal 20 m | Δ dựng lại/cũ | gộp 3 fold (10–12 scene) | Δ gộp/cũ | eval itr = 1 (2 scene) | Δ itr/cũ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 4,18 | 4,62 | +10,6 % | 4,84 | +15,7 % | 5,57 | +33,2 % |
| 60 | 11,31 | 11,40 | +0,8 % | 8,28 | −26,8 % | 11,50 | +1,7 % |
| 70 | 17,42 | 15,11 | −13,3 % | 12,54 | −28,0 % | 18,30 | +5,1 % |
| 80 | 22,02 | 21,53 | −2,2 % | 16,41 | −25,5 % | 22,37 | +1,6 % |
| 90 | 20,69 | 20,98 | +1,4 % | 18,77 | −9,3 % | 22,90 | +10,7 % |
| 100 | 29,24 | 27,33 | −6,5 % | 21,63 | −26,0 % | 30,93 | +5,8 % |
| 110 | 28,49 | 27,60 | −3,1 % | 17,85 | −37,3 % | 32,67 | +14,7 % |
| 120 | 17,58 | 17,09 | −2,8 % | 12,75 | −27,5 % | 22,67 | +28,9 % |
| 130 | 17,69 | 15,98 | −9,7 % | 13,06 | −26,2 % | 19,13 | +8,2 % |

- dựng lại cal 20 m: |Δ%| mean **5,6 %**, max 13,3 %
- gộp 3 fold: |Δ%| mean **24,7 %**, max 37,3 %, r = 0,95, ρ = 0,95
- eval itr = 1: |Δ%| mean **12,2 %**, max 33,2 %, r = 0,98, ρ = 0,90

#### Golf

| km/h | bảng cũ (commit) | dựng lại cal 20 m | Δ dựng lại/cũ | gộp 3 fold (10–12 scene) | Δ gộp/cũ | eval itr = 1 (2 scene) | Δ itr/cũ |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 3,62 | 3,51 | −3,0 % | 3,78 | +4,4 % | 7,23 | +99,8 % |
| 60 | 8,84 | 8,89 | +0,6 % | 8,05 | −8,9 % | 9,17 | +3,7 % |
| 70 | 11,36 | 11,58 | +1,9 % | 10,75 | −5,4 % | 12,37 | +8,9 % |
| 80 | 12,87 | 13,27 | +3,1 % | 12,52 | −2,7 % | 11,33 | −11,9 % |
| 90 | 10,51 | 10,67 | +1,5 % | 12,03 | +14,4 % | 10,43 | −0,7 % |
| 100 | 18,07 | 16,07 | −11,1 % | 14,76 | −18,3 % | 14,30 | −20,9 % |
| 110 | 16,69 | 16,04 | −3,9 % | 13,07 | −21,7 % | 16,63 | −0,3 % |
| 120 | 15,27 | 15,07 | −1,3 % | 14,12 | −7,5 % | 17,03 | +11,5 % |
| 130 | 16,64 | 16,07 | −3,4 % | 13,65 | −18,0 % | 18,70 | +12,4 % |

- dựng lại cal 20 m: |Δ%| mean **3,3 %**, max 11,1 %
- gộp 3 fold: |Δ%| mean **11,3 %**, max 21,7 %, r = 0,95, ρ = 0,92
- eval itr = 1: |Δ%| mean **18,9 %**, max 99,8 %, r = 0,89, ρ = 0,83

**Đọc số:** bảng cũ **cao hơn** bảng gộp ở 8/9 tốc độ Crafter
(tỉ lệ mới/cũ 0,63–0,91; riêng 50 km/h +15,7 %) và ở 7/9 tốc độ Golf
(0,78–1,14). Lý do **không** phải recipe (dựng lại chỉ lệch 5,6 %/3,3 %) mà là
**thành phần mẫu**:
- bảng cũ = 3 scene `cal` ở **20 m** (gần hơn, và chỉ 3/6 mức nước của ô
  theo parity);
- bảng gộp = **cả 20 m + 30 m, cả itr 1…6**, trong đó 10/12 scene là `itr 2–6`
  khô hơn. Hệ quả: bảng gộp là **"scene SSPP trung bình"**, không phải "điều
  kiện eval".
- Ở đúng điều kiện eval (2 scene itr = 1/ô), SSPP khớp bảng cũ **12,2 %**
  (Crafter, max 33,2 %, r = 0,98) và **18,9 %** (Golf, max 99,8 % do 50 km/h
  chỉ có 2 scene — mẫu quá nhỏ, xem caveats).

---

## 8. Độ ổn định giữa 3 fold `[ĐO]`

Cấu trúc fold làm phần lớn bảng **giống hệt nhau**: ở tốc độ không held-out,
cả 3 fold cùng dùng 12 scene đó ⇒ giá trị trùng khít (không phải bằng chứng
thống kê mà là cùng dữ liệu). Chỗ thực sự khác là ô tại tốc độ held-out: fold
đó chỉ còn 10 scene không box (Golf 80/90: 6/5). Vì vậy "spread giữa 3 fold"
dưới đây = **mức dịch chuyển khi bỏ 2 scene có box của ô** — vừa là độ ổn định
fold, vừa là proxy cho ảnh hưởng của nước/điều kiện eval.

| class | km/h | fold test đúng tốc độ này (10 scene không box) | 2 fold còn lại (12 scene) | spread % |
|---|---:|---:|---:|---:|
| crafter | 50 | 4,75 | 4,88 | 2,8 |
| crafter | 60 | 7,88 | 8,48 | 7,1 |
| crafter | 70 | 11,82 | 12,90 | 8,4 |
| crafter | 80 | 15,66 | 16,78 | 6,7 |
| crafter | 90 | 18,25 | 19,03 | 4,1 |
| crafter | 100 | 20,47 | 22,21 | 7,9 |
| crafter | 110 | 16,00 | 18,78 | 14,8 |
| crafter | 120 | 11,51 | 13,37 | 13,9 |
| crafter | 130 | 12,30 | 13,44 | 8,5 |
| golf | 50 | 3,35 | 3,99 | 16,2 |
| golf | 60 | 7,91 | 8,12 | 2,6 |
| golf | 70 | 10,55 | 10,85 | 2,8 |
| golf | 80 | 12,76 | 12,40 | 2,9 |
| golf | 90 | 12,40 | 11,84 | 4,7 |
| golf | 100 | 14,81 | 14,73 | 0,6 |
| golf | 110 | 12,63 | 13,29 | 5,0 |
| golf | 120 | 13,76 | 14,31 | 3,8 |
| golf | 130 | 13,02 | 13,97 | 6,8 |

Spread trung bình = **6,6 %**, median = 5,8 %, max = 16,2 %.

Cách đọc chặt của ADR-0006 D2: ngoài 12 scene test, mọi scene **cùng tốc độ** cũng thuộc chiến dịch/điều kiện của test nên không được dùng để calibration. Khi đó bảng của fold k chỉ có 6 mốc tốc độ; 3 tốc độ held-out phải nội suy tuyến tính từ 6 mốc đó. Bảng dưới so giá trị nội suy với số đo trực tiếp (cả 12 scene) để thấy sai số của cách làm SSPP-only — chính là lỗ hổng D2.

| fold | class | km/h held-out | nội suy từ 6 mốc | đo trực tiếp | Δ % |
|---:|---|---:|---:|---:|---:|
| 1 | crafter | 50 † | 8,48 | 4,88 | +73,7 % |
| 1 | crafter | 80 | 15,96 | 16,78 | −4,9 % |
| 1 | crafter | 110 | 17,79 | 18,78 | −5,3 % |
| 1 | golf | 50 † | 8,12 | 3,99 | +103,3 % |
| 1 | golf | 80 | 11,34 | 12,40 | −8,5 % |
| 1 | golf | 110 | 14,52 | 13,29 | +9,2 % |
| 2 | crafter | 60 | 8,89 | 8,48 | +4,8 % |
| 2 | crafter | 90 | 19,49 | 19,03 | +2,5 % |
| 2 | crafter | 120 | 16,11 | 13,37 | +20,5 % |
| 2 | golf | 60 | 7,42 | 8,12 | −8,6 % |
| 2 | golf | 90 | 13,56 | 11,84 | +14,6 % |
| 2 | golf | 120 | 13,63 | 14,31 | −4,7 % |
| 3 | crafter | 70 | 12,63 | 12,90 | −2,1 % |
| 3 | crafter | 100 | 18,90 | 22,21 | −14,9 % |
| 3 | crafter | 130 | 13,37 | 13,44 | −0,5 % |
| 3 | golf | 70 | 10,26 | 10,85 | −5,4 % |
| 3 | golf | 100 | 12,57 | 14,73 | −14,7 % |
| 3 | golf | 130 | 14,31 | 13,97 | +2,4 % |

|Δ%| trung bình = **16,7 %**, median = 7,0 %, max = 103,3 %.

† 50 km/h của fold 1 nằm dưới mốc thấp nhất của bảng (60): `np.interp` kẹp về giá trị 60, còn `cluster_visible_target_for_speed` trong `spray/plume.py` trả **0,0** khi tốc độ dưới mốc đầu — tức plume biến mất ở 50 km/h nếu chỉ dùng bảng SSPP của fold 1.

**Kết luận ổn định `[ĐO]`:** 3 fold nhất quán ở nơi dùng chung dữ liệu
(spread 6,6 % median 5,8 %); cái không ổn định là **khả năng nội suy** 3 tốc độ
held-out (median 7,0 %, mean 16,7 %, max 103,3 % ở 50 km/h cận dưới). Nói cách
khác: vấn đề không phải fold nào "xui", mà là **SSPP không có dữ liệu eval ở
tốc độ held-out** — đúng lý do D2 phải lấy calibration từ RoadSpray static.

---

## 9. So với bảng RoadSpray `*_static` `[ĐO]`

Nguồn: `docs/measurements/roadspray-static-clusters-by-speed.md` (Crafter,
`itr_after_water = 1`, 18 bag / 295 frame, Δ = 2,5 m).

`static` = calibration độc lập, ego đỗ, `itr_after_water = 1` (ADR-0006 D2). Chỉ Crafter có số.

| km/h | static (D2) | eval itr = 1 (2 scene) | tỉ lệ itr/static | gộp 3 fold (10–12 scene) | tỉ lệ gộp/static |
|---:|---:|---:|---:|---:|---:|
| 70 | 19,80 | 18,30 | 0,92 | 12,54 | 0,63 |
| 80 | 29,30 | 22,37 | 0,76 | 16,41 | 0,56 |
| 90 | 31,40 | 22,90 | 0,73 | 18,77 | 0,60 |
| 100 | 28,10 | 30,93 | 1,10 | 21,63 | 0,77 |
| 110 | 30,20 | 32,67 | 1,08 | 17,85 | 0,59 |
| 120 | 15,00 | 22,67 | 1,51 | 12,75 | 0,85 |
| 130 | 24,20 | 19,13 | 0,79 | 13,06 | 0,54 |

- eval itr = 1 vs static: |Δ%| mean **21,2 %**, max 51,1 %, r = 0,49, ρ = 0,57
- gộp 3 fold vs static: |Δ%| mean **35,1 %**, max 46,0 %, r = 0,77, ρ = 0,75
- bảng cũ 45-frame vs static: |Δ%| mean **17,8 %**, max 34,1 %, r = 0,64, ρ = 0,64

**Đọc số:** hai nguồn độc lập **cùng hình dạng** với bảng cũ (r = 0,64 giữa
bảng cũ và static — đúng số doc static ghi r/ρ = 0,64) và bảng gộp (r = 0,77).
Về **độ lớn**: bảng cũ vs static lệch 17,8 % (trung bình), eval itr = 1 vs
static lệch 21,2 % (r chỉ 0,49 vì 2 scene/ô quá ít), bảng gộp 12 scene vs static
lệch 35,1 % — bảng gộp **thấp hơn** static ~0,54–0,85× vì lý do nước đã nói ở
§7. Không được đọc là "static sai": static đo plume tươi (`itr = 1`), còn bảng
gộp đo **mọi mức nước**. Với mục đích "kiểm chứng chéo cho bảng static", so
sánh đúng là **eval itr = 1 vs static** (21,2 %, cùng bậc độ bất định ±30–40 %
mà chính doc static tự khai) và **bảng cũ vs static** (17,8 %, đúng như doc
static đã ghi 1,18× / r = 0,64).

---

## 10. Nước (`itr_after_water`) — vì sao bảng gộp khô hơn eval `[ĐO]`

36 scene eval đều `itr_after_water = 1`; 10 scene còn lại trong ô là `itr 2–6` (bể nước vơi dần). Bảng dưới tách 2 nhóm để thấy đại lượng lệch là do **nước**, không phải do tốc độ.

| class | km/h | cụm/frame (2 scene itr = 1) | cụm/frame (10 scene itr 2–6) | tỉ lệ |
|---|---:|---:|---:|---:|
| crafter | 50 | 5,57 | 4,75 | 1,17 |
| crafter | 60 | 11,50 | 7,88 | 1,46 |
| crafter | 70 | 18,30 | 11,82 | 1,55 |
| crafter | 80 | 22,37 | 15,66 | 1,43 |
| crafter | 90 | 22,90 | 18,25 | 1,25 |
| crafter | 100 | 30,93 | 20,47 | 1,51 |
| crafter | 110 | 32,67 | 16,00 | 2,04 |
| crafter | 120 | 22,67 | 11,51 | 1,97 |
| crafter | 130 | 19,13 | 12,30 | 1,56 |
| golf | 50 | 7,23 | 3,35 | 2,16 |
| golf | 60 | 9,17 | 7,91 | 1,16 |
| golf | 70 | 12,37 | 10,55 | 1,17 |
| golf | 80 | 11,33 | 12,76 | 0,89 |
| golf | 90 | 10,43 | 12,40 | 0,84 |
| golf | 100 | 14,30 | 14,81 | 0,97 |
| golf | 110 | 16,63 | 12,63 | 1,32 |
| golf | 120 | 17,03 | 13,76 | 1,24 |
| golf | 130 | 18,70 | 13,02 | 1,44 |

Tỉ lệ itr = 1 / itr 2–6: trung bình **1,40×**, min 0,84×, max 2,16× — đúng chiều ADR-0006 (pseudo scene khô hơn, 1,2–5,4× theo tốc độ).

---

## 11. Hệ quả và quyết định `[CHỌN]`

1. **Giữ D2**: nguồn calibration vẫn là RoadSpray `*_static`. Bảng SSPP per-fold
   này **không** dùng làm calibration, chỉ làm kiểm chứng chéo — đúng vai trò
   task giao.
2. **Không thay `_CLUSTER_VISIBLE_BY_SPEED` bằng bảng gộp 12 scene.** Bảng gộp
   là "scene SSPP trung bình" (10/12 scene `itr 2–6` khô hơn) nên thấp hơn
   điều kiện eval ~1,2–1,4×; dùng nó sẽ làm generator yếu đi so với hiện tại. Nếu
   muốn bảng SSPP sạch leak thay bảng cũ thì phải dùng **eval itr = 1** (2
   scene/ô) — nhưng mỗi fold chỉ có 6 mốc, không phủ được 3 tốc độ held-out,
   và mẫu 2 scene quá nhỏ (Golf 50 lệch 99,8 %).
3. **Số liệu nên trích**: bảng gộp 3 fold (§5) là bảng `cụm/frame` SSPP **không
   leak** tốt nhất có thể với mẫu 150–180 frame/ô; so với bảng cũ, |Δ| 24,7 %
   (Crafter) / 11,3 % (Golf) — **không** dùng để nói bảng cũ "sai 25 %", mà để
   nói bảng cũ thiên vị mẫu (20 m + nước) và mẫu nhỏ.
4. **Kiểm chứng chéo cho bảng static đạt**: r = 0,77 (gộp) / 0,64 (cũ) với
   static; ở điều kiện eval (itr = 1) độ lệch trung bình 21,2 %, nằm trong dải
   bất định ±30–40 % mà doc static tự khai. Không có mâu thuẫn hai nguồn.
5. **Việc còn lại của E1**: `scripts/build_sspp_split.py` chưa được sửa để xuất
   split 3 fold (task này **cấm** sửa file có sẵn); script này đã có
   `fold_for_speed()` + `--check` để tái dùng. Khi làm E1, test kỳ vọng
   886/893/808 frame (đã kiểm `[ĐO]`).

---

## 12. Tái lập và kiểm tra không leak

```bash
# 1) Kiểm cấu trúc fold + no-leak (nhanh, không đọc point cloud — ~4 s)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/sspp_cluster_table_folds.py --check

# 2) Chạy đủ 207 scene × 15 frame, B = 2000 (cold ~3m48s; cache hit ~3 s)
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/sspp_cluster_table_folds.py \
    --json-out /tmp/sspp_folds.json --md-out /tmp/sspp_folds.md \
    --cache /tmp/sspp_folds_cache.json --compare-old

# 3) Kiểm chéo chính file đã đo: scene nào thực sự vào bảng mỗi ô
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/sspp_cluster_table_folds.py --check --measured /tmp/sspp_folds.json
```

`[ĐO]` Marker của bước 1/3:

```
INVENTORY scenes=207 boxed=36 frames=17419 frames_per_scene=15
FOLD fold=1 held_out_kmh=50,80,110 test_scenes=12 test_frames=886 train_scenes=24 train_frames=1701 used_scenes=195
FOLD_HELDOUT_CELL fold=1 class=crafter kmh=50 n_scene=10 n_frame=150 all_non_box=1 note=scene-level-only
...
FOLD_FRAMES fold=1 measured=886 expected=886 OK
FOLD_FRAMES fold=2 measured=893 expected=893 OK
FOLD_FRAMES fold=3 measured=808 expected=808 OK
FOLDS_CHECK_OK folds=3 scenes=207 boxed=36 cells=54
```

`--check` kiểm 4 bất biến: (a) rule fold khớp ADR-0006; (b) 36 scene box /
12 test + 24 train mỗi fold, mỗi scene test đúng một lần; (c) **mọi** ô của fold
k rời 12 scene test của fold k (đây là điều kiện không leak); (d) ô held-out chỉ
dùng scene không box (`all_non_box=1`). Với `--measured`, nó kiểm lại đúng
danh sách scene đã ghi trong JSON của từng ô, không tin vào lời khai của script.
Marker của bước 2: `FOLDS_MEASURE_OK`; JSON chứa `fold_rule`, `fold_speeds`,
`inventory`, `folds`, `tables` (scene list từng ô), `pooled`,
`old_table_reproduction`.

---

## Caveats

1. **Golf 80/90 thiếu mẫu — không thể đạt 10 scene/ô.** Dataset chỉ có **8/7
   scene** ở hai tốc độ này (toàn bộ 207 scene); ô held-out của Golf 80 còn 6
   scene/90 frame, Golf 90 còn 5 scene/75 frame. Đã ghi đúng số trong mọi
   bảng, không che. CI95 của hai ô này (Golf 80: ±8,1 %; Golf 90: ±9,9 %) lại
   **không rộng hơn** trung vị 15,3 % vì CV giữa scene thấp — nhưng 8/7 scene là
   giới hạn cứng của dataset, không tăng mẫu được.
2. **Nước**: 171 scene không box là `itr 2–6`, khô hơn eval (`itr = 1`) trung
   bình **1,40×** (0,84–2,16×). Mọi so sánh "bảng gộp vs bảng cũ/static" bị
   nhiễu bởi đại lượng này; đã tách riêng bảng eval itr = 1 để đọc.
3. **Bảng eval itr = 1 chỉ có 2 scene/ô**, không báo CI95 (không có nghĩa với
   n = 2); cột "dải 2 scene" là min–max per-scene. 50 km/h Golf lệch 99,8 % so
   bảng cũ vì đúng 2 scene và một scene có cụm rất cao — không dùng ô này để
   kết luận.
4. **Script đo bảng cũ không có trong repo**; phép dựng lại khớp 5,6 %/3,3 %
   nhưng không phải tuyệt đối (frame index khác). So sánh chính trong doc vẫn
   là **số commit** (đúng bảng đang dùng trong `spray/plume.py`), không phải
   số dựng lại.
5. **Fold chưa có trong code trước task này** — được dựng trong script theo
   rule ADR-0006 và đối chiếu frame count E1 (886/893/808). `build_sspp_split.py`
   chưa xuất 3 fold (task cấm sửa file có sẵn).
6. `label == 2` gồm cả nhiễu không phải spray (mưa/phản xạ) — giữ nguyên định
   nghĩa bảng cũ, không sửa recipe.
7. Bootstrap giả định scene là đơn vị độc lập có hoàn lại; với các ô có 2 scene
   không dùng. `cluster_angular` là O(n²) Python, chạy đơn luồng (3m48s cho
   3 105 frame) — đủ cho measurement 0 GPU.

---

## Liên quan

- `docs/adr/0006-detection-protocol-and-calibration-source.md` — D1 (fold),
  D2 (calibration từ RoadSpray static), D3 (CI95 theo scene), V2.
- `docs/measurements/semantic-spray-clusters-by-speed.md` — bảng 45-frame cũ
  (cal, 20 m, 3 scene/ô).
- `docs/measurements/roadspray-static-clusters-by-speed.md` — bảng static
  (nguồn calibration D2, `itr = 1`, ±30–40 %).
- `.scratch/roadspray-cal/power-design.md` §1 (bootstrap phải ở mức scene),
  §3 (bảng E1 886/893/808 frame).
- `.scratch/roadspray-cal/plan.md` — E1 (3-fold leave-speed-out), E4 (pseudo-box
  cho 171 scene, `itr 2–6`).
- `scripts/sspp_cluster_table_folds.py`, `tests/test_sspp_cluster_table_folds.py`.
