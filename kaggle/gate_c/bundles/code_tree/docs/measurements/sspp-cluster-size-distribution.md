# Đuôi phân bố điểm/cụm của spray thật (SSPP, theo fold) — 2026-11-18

Người đo: lead. Script: `scripts/sspp_cluster_size_dist.py`. JSON/CSV đầy đủ:
`.scratch/roadspray-cal/tmp/sizes.{json,md}` (không commit).
Nhãn: `[ĐO]` trên máy này · `[CHỌN]` tự chọn.

Mục đích: chốt **đích** cho A3. Sau A1, generator khớp **cụm/frame** (29,1 vs thật 28,5) nhưng chỉ sinh
**~140 điểm/frame** trong khi `label == 2` có **1 050–2 220** ⇒ thiếu 8–16×. Câu hỏi: thiếu **đều** (mọi
cụm nhỏ đi) hay thiếu **đuôi** (chỉ thiếu các cụm khổng lồ)?

## Phương pháp

- Recipe **y nguyên** bảng cụm/frame: chỉ `label == 2`; DBSCAN trên `(azimuth, elevation)`,
  `eps = 0,7°`, `minPts = 3`, elevation snap `0,333°`, azimuth wrap; 15 frame cách đều mỗi scene.
- **Không leak**: mỗi scene đo một lần, nhưng khi gộp cho fold `k` thì loại 12 scene test của fold `k`
  (`fold_test_scenes` của `scripts/sspp_cluster_table_folds.py`).
- CI95 = bootstrap percentile **ở mức scene**, B = 2000, seed cố định.
- 207 scene / ~3 100 frame; 6–12 scene và 90–180 frame mỗi ô.

## Kết quả `[ĐO]` (Crafter, gộp 3 fold — 3 fold lệch nhau ≤ 15 %, xem JSON)

| km/h | scene | frame | cụm/frame | điểm/frame | **điểm/cụm p50** | **mean [CI95]** | p95 | max | **% điểm trong cụm ≥50 đ** |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 50 | 10–12 | 150–180 | 4,8 | 43 | **6** | **8,8** [7,6; 10,3] | 17 | 144 | **15 %** |
| 60 | 10–12 | 150–180 | 8,2 | 83 | **5** | **9,9** [8,2; 13,6] | 22 | 453 | **36 %** |
| 70 | 10–12 | 150–180 | 12,5 | 199 | **5** | **15,9** [13,1; 19,5] | 54 | 732 | **56 %** |
| 80 | 10–12 | 120–180 | 16,4 | 454 | **6** | **27,6** [23,5; 32,0] | 138 | 1222 | **75 %** |
| 90 | 10–12 | 105–180 | 18,8 | 615 | **6** | **32,7** [25,4; 39,7] | 163 | 1708 | **78 %** |
| 100 | 10–12 | 150–180 | 21,6 | 875 | **6** | **40,4** [32,2; 47,9] | 182 | 2241 | **82 %** |
| 110 | 10–12 | 150–180 | 17,9 | 800 | **6** | **44,7** [37,1; 52,1] | 210 | 1732 | **84 %** |
| 120 | 10–12 | 150–180 | 12,8 | 607 | **7** | **47,7** [42,1; 54,3] | 183 | 2937 | **85 %** |
| 130 | 10–12 | 150–180 | 13,1 | 592 | **6** | **45,3** [38,7; 50,8] | 158 | 2485 | **83 %** |

Golf cùng dạng, nhẹ hơn ~1,3–1,5× (điểm/cụm mean 8,4 → 33,4; share ≥50 đ 11 % → 78 %).

## Ba kết luận

**① Phân bố là **hai đỉnh**, không phải một họng lognormal.** `điểm/cụm p50 = 5–7` ở **mọi** tốc độ
(gần như hằng số), nhưng `mean` tăng **8,8 → 47,7** vì tỉ lệ điểm nằm trong các cụm ≥ 50 điểm tăng
**15 % → 85 %**. Nói cách khác: plume thật = **rất nhiều cụm nhỏ (5–6 điểm) + một ít chuỗi khổng lồ**.

**② Generator hiện tại đúng ở phần nhỏ và thiếu hẳn phần chuỗi.** Đo sau A1 (100 km/h): cụm/frame 29,1
✓, `điểm/cụm` median 5–6 ✓ **khớp chính xác p50 thật**, nhưng cụm lớn nhất chỉ **~91 điểm** so với thật
**p95 = 182, max = 2 241**, và share điểm trong cụm ≥ 50 đ là **0 %** so với thật **82 %**.

⇒ Vấn đề của A3 **không phải** "mọi cụm nhỏ đi 8–16×" mà là **thiếu cơ chế tạo chuỗi**.

**③ Vì vậy T1 và T2 không còn xung đột như bảng cũ trình bày.** T1 (dùng số paper: ~200–500
detection/frame) và T2 (`label == 2`: 600–900 điểm/frame) chỉ khác nhau **hệ số 2**; cả hai đều đòi
**thêm chuỗi**, không đòi phóng to cụm nhỏ. Chọn T2 vì: (a) đó là khối lượng detector thật sự gặp lúc
eval; (b) `điểm/cụm` có **CI95 hẹp ±5–10 %** (khác hẳn bảng cụm ±30–40 %), nên đích này **xác định tốt**.

## Giả thuyết cơ chế (để A3 kiểm)

Chuỗi hình thành khi nhiều cụm nhỏ **chồng nhau trong không gian góc** — DBSCAN nối chúng. Generator
của repo rải cụm **đều** trong cả hộp plume dài, nên mật độ thấp và **không có chỗ chồng** ⇒ không
chuỗi. Kiểm nhanh (0 GPU): so **mật độ cụm theo thể tích** giữa sinh và thật; nếu sinh thấp hơn nhiều
thì sửa bằng cách **tập trung cụm vào lõi plume** (hoặc tăng số cụm đồng thời giảm bán kính), chứ
không cần bịa thêm cơ chế mới.

Đây là chỗ gặp **paper**: Paper A §III-B nói cụm đặt *"with a uniform distribution in the region behind
every moving object"* — nếu vùng của paper ngắn (`length = |v|·Δt` trong `define_spray_volumes()`) thì
mật độ cao, chồng nhau nhiều, chuỗi tự sinh. Port hiện tại có thể đang rải trên vùng **dài hơn**.

## Hệ quả cho plan

- **A3 đích = T2, cài theo cấu trúc**: giữ phân bố nhỏ (median 5–6 điểm — đang đúng), thêm thành phần
  chuỗi để tổng điểm/frame và `share ≥50 đ` khớp bảng trên.
- Tiêu chí xong của A3 (thay "cụm lớn nhất ≥ 500 điểm" cũ, vốn chỉ là một điểm của đuôi):
  `% điểm trong cụm ≥ 50 đ` ∈ **±10 điểm %** so với bảng, và `p95 điểm/cụm` trong khoảng thật.
- Không cần đổi `_CLUSTER_VISIBLE_BY_SPEED` vì cụm/frame đã khớp.
