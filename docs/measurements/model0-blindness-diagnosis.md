# Model 0 mù trên SSPP — lỗi harness hay domain gap?

2026-11-19 · subagent chẩn đoán · nhánh `sspp` · §0–§6 chỉ đọc, không sửa code.
Nguồn số: `gate_c_detections.jsonl` + `_summary.json` của kernel v4
(`/tmp/gate_c_out/gate_c_out/`), 954 frame × 3 nhánh, τ = 0,20.
Script đo tạm: `.scratch/tmp/diag_{a2,geom,det,stats,near}.py`.
**Cập nhật 2026-11-19 (subagent verify):** đã sửa `detect()` và **verify trên Kaggle**
— kết quả ở §7 (TP 0/5 → 5/5). Các số §1–§6 là *trước khi sửa*, giữ nguyên làm
bằng chứng chẩn đoán.

---

## 0. Kết luận

**(i) Có lỗi hệ thống cụ thể — không phải domain gap thuần.**

Kênh thứ 5 (index 4) của point cloud bị nạp sai ngữ nghĩa:

| | Giá trị đúng lúc train/eval nuScenes | Harness nạp |
|---|---|---|
| Cột 4 | **time-lag** `t_keyframe − t_point`, ∈ [−0,5; 0] giây (keyframe = 0) | **ring index**, ∈ [0; 30], trung bình 8,58 |
| Nguồn | `loading.py:182` `points.tensor[:, 4] = 0`; `loading.py:223` `points_sweep[:, 4] = ts - sweep_ts` | `sspp_infer.py:668-672` `points[:, :POINT_DIM]` |

`sspp_infer.py` bỏ qua pipeline `LoadPointsFromMultiSweeps` và đưa thẳng 5 cột
của file `.bin` (`x, y, z, intensity, ring`) vào model. Config dùng
`use_dim: 5` (`configs/nuscenes/default.yaml:5-6`) nên **cả 5 cột đều vào
model** — cột ring thay chỗ time-lag.

Đây là lỗi "rẻ tiền" đúng loại Lead nghi ngờ, và nó đủ mạnh để giải thích TP=0.

**(ii) Đã verify trên Kaggle sau khi sửa: đúng là nguyên nhân.** 5 frame
`Crafter_dynamic` 90/130 km/h, cùng seed, cùng kernel: trước sửa TP 0/5, max
score 0,146; sau sửa **TP 5/5, recall@τ=0,20 = 1,00, max score 0,563** (§7).

---

## 1. Bảng kiểm A1–A7

| # | Hạng mục | Kết quả | Bằng chứng |
|---|---|---|---|
| A1 | Harness nạp gì | **Khớp**, trừ cột 4 | `load_points` đọc raw `.bin` (N,5) float32, không lọc/không chuẩn hoá (`spray/sspp_adapter.py:218-231`). `detect()` dựng tensor `points[:, :5]` (`sspp_infer.py:668-672`). pcr/voxel lấy từ config: `[-54,-54,-5,54,54,3]`, `[0.075,0.075,0.2]`, lưới 1440×1440×41; Voxelization CUDA tự lọc điểm ngoài range. Box ra: `outputs[0]["boxes_3d"]` → `.tensor` (N,9), **z = đáy** (`LiDARInstance3DBoxes` origin z=0), khung LiDAR, không qua biến đổi ngược |
| A2 | Khung toạ độ GT | **Khớp** | 40 frame test: **99,4 %** điểm `label==1` nằm trong BEV box; z trung vị trong box = **44,5 %** chiều cao (0=đáy, 1=đỉnh); đáy box `z=−0,38±0,05` ≈ mặt đường đo được. Box và điểm cùng khung, `z=đáy` đúng |
| A3 | Chiều trục | **Khớp** | Xe dẫn ở `x≈20–30`, `y≈0`, yaw≈0 → +x là tiến, +y trái, +z lên, đúng quy ước nuScenes. Box 6,83×2,42×2,62 chứa 240 điểm trung vị (min 94) — không có dấu hiệu đảo/ mirror trục |
| A4 | Thứ tự kênh & chuẩn hoá | **LỆCH — lỗi chính** | nuScenes dùng `(x, y, z, intensity, time_lag)`; harness nạp `(x, y, z, intensity, ring)`. Không có chuẩn hoá nào bị thiếu (cả hai đều raw), nhưng **ngữ nghĩa cột 4 sai** |
| A5 | Clip range / độ cao | **Không phải nguyên nhân chính**, nhưng là covariate | 87,1 % điểm nằm trong pcr xyz; **0,012 %** điểm có `z < −1,84`; mặt đường p50 `z=−0,38` (20 frame) ⇒ voxel-z 23,1/41, còn nuScenes 15,8/41 (lệch ~7,3 voxel ≈ 1,45 m). Không có GT nào ngoài range (đều 20–30 m) |
| A6 | Class mapping | **Không thể gây TP=0** | Matching cố ý label-agnostic: `EvalConfig(class_names=("object",))` và `score_detection` truyền `zeros` cho cả pred lẫn GT (`sspp_infer.py:697-730`). Nhãn 0–9 của model không tham gia so khớp |
| A7 | Cách tính TP/IoU | **Đúng**; tái lập được | Chạy lại matcher trên jsonl: clean @τ=0,2 → **TP 0, FP 4, FN 954** (khớp runbook). Best IoU/frame: p50 0,0000 · p95 0,0000 · p99 0,048 · max **0,301** (1 frame plume). Tâm gần GT nhất p50 **23,7 m**. `bev_corners` xoay `(dx,dy,yaw)` đúng quy ước mmdet |

---

## 2. Vì sao lỗi cột 4 giải thích được TP=0

**a) Trọng số của checkpoint cho kênh 4 lớn bất thường** — dấu hiệu của một kênh
có biên độ nhỏ (time-lag ∈ [−0,5; 0]) chứ không phải ring ∈ [0; 30]:

`heads... encoders.lidar.backbone.conv_input.0.weight`, shape (3,3,3,5,16),
RMS theo từng kênh vào:

| kênh | 0 (x) | 1 (y) | 2 (z) | 3 (intensity) | **4** |
|---|---:|---:|---:|---:|---:|
| RMS | 0,096 | 0,097 | 0,146 | 0,135 | **0,874** |
| max \|w\| | 0,74 | 0,91 | 0,75 | 1,34 | **15,15** |

Kênh 4 có RMS **gấp 7,4×** và max **gấp 16,6×** các kênh hình học. Nếu model
được train với ring (0–30) thì trọng số phải cùng cỡ các kênh khác; cỡ này chỉ
hợp với một tín hiệu 0,1–0,5 đơn vị.

**b) Độ lệch đưa vào lớp conv đầu tiên:** tổng trọng số kênh 4 theo mỗi output
= 6,05 (mean \|·\|), max 27,7 — so với 0,14–0,73 của các kênh xyz/intensity.
Với ring trung bình 8,58, riêng kênh 4 đóng góp **~50 (tới ~170 khi ring=28)**
vào pre-BN activation, trong khi BN có σ ≈ 10 (`running_var` mean 121,7). Tức
**5–17 σ**, và thành phần này **thay đổi theo không gian** (ring nền đất p50=5,
ring điểm xe p50=14) nên nó áp đảo tín hiệu hình học thay vì chỉ là một bias.

**c) Hành vi đo được khớp với "feature bị phá":** model không tắt hẳn, nhưng
mất khả năng định vị:

- 954 frame clean: **1.694 box** (1,78/frame), **98,5 % nằm trong bán kính 5 m**
  quanh ego; `x` p50 **1,24 m**, `y` p50 **0,04 m**;
- kích thước box lại rất "xe": `dx` 1,78 · `dy` 4,52 · `dz` 1,73 · `yaw` ±90°
  ⇒ hộp 4,5 m dọc trục đường, đúng hướng ego — tức **prior "xe ở ego"**, không
  phải box ngẫu nhiên;
- score rất thấp: p50 0,068; **max score/frame p50 = 0,075**, chỉ **4/954**
  frame có box ≥ 0,20. Muốn có TP thì model phải đạt ~0,5–0,9 tại ô của xe.
- model vẫn phản ứng với input (plume làm FP 0,004 → 0,080), nên điểm **có**
  vào model — chỉ là đặc trưng bị kênh ring chi phối.

**d) Đối chứng dương trong repo:** harness legacy trên nuScenes-mini
(`results/phase-b1-nuscenes-mini/`) đạt car AP 0,694 / recall 0,708 với cùng
kiểu chấm BEV — chứng minh matcher và khái niệm "zero-shot vẫn bắt được xe" là
đúng; khác biệt nằm ở đường nạp điểm.

---

## 3. Cách sửa (1 dòng) và mức ảnh hưởng

Trong `detect()` (`scripts/sspp_infer.py:668-672`), trước khi dựng tensor:

```python
array = np.ascontiguousarray(points[:, :POINT_DIM], dtype=np.float32).copy()
array[:, 4] = 0.0          # cột 4 = time-lag (loading.py:182), KHÔNG phải ring
tensor = torch.as_tensor(array, dtype=torch.float32, device=device)
```

Đúng về mặt toán học, không phải hack: với frame không có sweep, pipeline chuẩn
đặt time-lag = 0 cho **mọi** điểm keyframe. Nên thêm assert
`np.abs(array[:, 4]).max() <= 0.6` để lần sau không tái diễn.

**Ước lượng ảnh hưởng:** đây là điều kiện *cần*; chưa chứng minh là *đủ*.
Van dẫn có 240–300 điểm nằm gọn trong box, ở 20–30 m, hoàn toàn trong pcr —
sau khi sửa, input khớp 100 % ngữ nghĩa 5 kênh với lúc train. Kỳ vọng TP > 0,
recall quay về cỡ **0,2–0,6** (không dám chắc hơn khi chưa chạy GPU). **Toàn bộ
kết luận FP của cổng C hiện tại phải bỏ** — nó đo một model đã bị phá đặc trưng,
không đo tác dụng của plume.

---

## 4. Covariate còn lại (không phải lỗi, phải khai khi báo cáo)

1. **Gốc z lệch ~1,45 m.** Mặt đường SSPP `z=−0,38`, nuScenes `z≈−1,84`; sau
   khi sửa cột 4, nếu TP vẫn thấp thì đây là nghi phạm số 2 (dịch `z −= 1,45`
   cho cả điểm, BEV IoU không đổi vì bỏ z).
2. **Mật độ:** 1 sweep ~29 k điểm; nuScenes eval dùng 10 sweep (~10×). Lưu ý
   `pad_empty_sweeps` nhân bản keyframe nên về mặt voxel-mean gần như no-op —
   khác biệt thật là 10× số **return khác nhau**.
3. **Cảm biến:** VLP-32C (SSPP) vs HDL-32E (nuScenes); ring 0–30 vs 0–31,
   intensity 0–242 (median 10).
4. **pcr z dùng phí:** [-5, 3] nhưng mọi điểm > −0,7 ⇒ 4,3 m dưới mặt đường
   trống (57 % chiều cao voxel).

---

## 5. Kế hoạch test trên Kaggle (đã chạy 2026-11-19 — kết quả ở §7)

1. Patch tạm trong `.scratch/tmp/` (không sửa `scripts/`): bản `detect()` đặt
   `array[:,4]=0`, in thêm `ring mean/max` và `max score` mỗi frame.
2. Chạy `--split test --limit 5 --arms clean` với patch và không patch, cùng
   5 frame (đã có sẵn bundle code/data của kernel v4).
3. Kỳ vọng pass: max score > 0,2 và ≥1 detection trong 3 m tâm GT ở ≥3/5 frame;
   in bảng `best IoU`, `nearest dist`, `max score` trước/sau.
4. Nếu vẫn 0: thêm biến thể dịch `z −= 1,45` (mục 4.1) rồi lặp lại 5 frame.
5. Nếu vẫn 0 sau cả hai: khi đó mới được kết luận domain gap, và phải kèm bằng
   chứng "đã sửa đúng kênh 4 + đã căn z".

---

## 6. Phụ lục — số đo thô

| Số đo | Giá trị |
|---|---|
| Điểm/frame (test) | ~28–31 k; 87,1 % trong pcr |
| Nhãn/frame | nền ~28,8 k · xe ~300 · spray ~510 |
| Ring toàn cục | min 0 · p50 8 · p95 18 · max 30 · mean 8,58 |
| Ring nền đất vs điểm xe (p50) | 5 vs 14 |
| Mặt đường z (mode 8–40 m, 20 frame) | p50 −0,38 (min −0,45, max −0,20) |
| Điểm có z < −1,84 | 0,012 % |
| Box GT: điểm xe nằm trong box | 99,4 % (40 frame) |
| Box GT: z trung vị / chiều cao | 0,445 |
| clean: box/frame @τ≥0,05 | 1,78 |
| clean: max score/frame | p50 0,075 · p99 0,176 · max 0,290 |
| clean @τ=0,2 | TP 0 · FP 4 · FN 954 |
| Best BEV IoU/frame | p95 0,0000 · max 0,301 (1 frame) |
| Tâm detection gần GT nhất | p50 23,7 m · p95 33,6 m |
| `conv_input` RMS theo kênh | 0,096 / 0,097 / 0,146 / 0,135 / **0,874** |
| BN1d `running_var` mean (lớp đầu) | 121,7 (σ ≈ 10,1) |

---

## 7. Verify trên Kaggle (2026-11-19) — đã chạy, PASS

Kernel `nguynhuy9669/bevfusion-gate-c-verify5-channel4-fix` **version 1 = COMPLETE**
(push 15:35, xong 15:48; `elapsed_s = 584` ≈ 9,7 phút GPU, nhanh hơn ước tính
26 phút — cùng recipe nhưng máy này tải wheel nhanh; `OPS_OK`, `mmdet3d` import
được, `chain=7`, `missing=0`, `unexpected=0`).
Nguồn số của §7: **[ĐO]** — log + `verify5_table.json` của kernel đó
(`.scratch/tmp/verify5_out/verify5_out/`).
Cùng một kernel chạy **3 chế độ × 5 frame × 1 nhánh (`clean`)** bằng chính CLI
`scripts/sspp_infer.py`, cùng seed, cùng frame:

| chế độ | cờ | nghĩa |
|---|---|---|
| `legacy_channel4` | `--legacy-channel4` | tái hiện lỗi cũ (cột 4 = ring) |
| `fixed` | (mặc định) | cột 4 = 0 — bản đã sửa |
| `fixed_z_m1p45` | `--z-shift-m -1.45` | biến thể covariate độ cao (§4.1), chốt trước |

Frame chốt trước khi xem số (vị trí đều trong scene, không chọn theo nội dung):
`Crafter_dynamic/0048_…` (90 km/h, 65 frame) ở vị trí 6/32/58 và
`Crafter_dynamic/0096_…` (130 km/h, 79 frame) ở vị trí 12/59. Mỗi frame có đúng
1 box GT (`Van`), 385–546 điểm GT trong box, tâm cách ego 21–26 m.

`n_det` = số detection ghi ra ở ngưỡng của cổng C (score ≥ 0,05);
`n_in3m` = số detection **score ≥ 0,20** trong 3 m tâm GT (ngưỡng chốt trước,
cùng τ với cổng C — ở score thấp hơn, box rải khắp 54 m nên "trúng 3 m" chỉ là ngẫu nhiên).

### 7.1 Từng frame

| frame | km/h | n_det | max_score | best BEV IoU | nearest (m) | n_in3m |
|---|---:|---:|---:|---:|---:|---:|
| 0048/000006 — trước | 90 | 2 | 0,0994 | 0,236 | 0,20 | 0 |
| 0048/000006 — **sau** | 90 | 9 | **0,3494** | **0,738** | 0,16 | **1** |
| 0048/000032 — trước | 90 | 2 | 0,1460 | 0,000 | 12,28 | 0 |
| 0048/000032 — **sau** | 90 | 28 | **0,3002** | **0,761** | 0,32 | **1** |
| 0048/000058 — trước | 90 | 3 | 0,0775 | 0,060 | 3,79 | 0 |
| 0048/000058 — **sau** | 90 | 25 | **0,2491** | **0,598** | 0,83 | **1** |
| 0096/000012 — trước | 130 | 1 | 0,0608 | 0,217 | 1,96 | 0 |
| 0096/000012 — **sau** | 130 | 15 | **0,5629** | **0,503** | 1,91 | **1** |
| 0096/000059 — trước | 130 | 2 | 0,0598 | 0,301 | 0,96 | 0 |
| 0096/000059 — **sau** | 130 | 19 | **0,5066** | **0,722** | 0,15 | **1** |

### 7.2 Gộp 5 frame

| chế độ | n_det (≥0,05) | dets (≥0,001) | max_score | frame có ≥1 det trong 3 m | TP/5 @τ=0,20 | recall @τ=0,20 | FP/frame @τ=0,20 | det trong 5 m ego |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| trước (`legacy_channel4`) | 10 | 585 | 0,1460 | 0/5 | 0 | 0,00 | 0,00 | **100 %** (10/10) |
| **sau (`fixed`)** | 96 | 748 | **0,5629** | **5/5** | **5** | **1,00** | 1,20 | **7,3 %** (7/96) |
| sau + `--z-shift-m -1.45` | 54 | 725 | 0,6941 | 5/5 | 4 | 0,80 | 1,20 | 11,1 % (6/54) |

Độ nhạy τ của bản đã sửa (5 frame): τ=0,10 → recall 1,00, FP/frame 6,2;
τ=0,20 → 1,00 / 1,20; τ=0,30 → 0,80 / 0,00; τ=0,50 → 0,40 / 0,00.
Ở τ=0,20, detection/frame = 0 (trước) → 2,2 (sau), và chỉ **1/11** detection nằm
trong 5 m ego (trước: 98,5 % của 1.694 box trên 954 frame).

**Tiêu chí PASS chốt trước (§5, mục 3): max_score > 0,20 và ≥1 detection trong 3 m
tâm GT ở ≥3/5 frame.** Sau sửa: 0,563 > 0,20 ✓ và 5/5 ≥ 3 ✓ ⇒ **PASS**.
Trước sửa: 0,146 và 0/5 ⇒ FAIL đúng như dự đoán. Kernel in `VERIFY_VERDICT
fixed_pass=1 z_pass=1 legacy_frames_in3m=0 legacy_max_score=0.1460`.

**Biến thể z:** cũng "pass" kỹ thuật (max 0,694, 5/5 trong 3 m) nhưng TP 4/5 và
recall 0,80 — **không tốt hơn bản chỉ sửa kênh 4** (5/5, 1,00). Vì BEV backbone nén
chiều cao bằng max-pool và mọi điểm dịch cùng nhau, phép dịch z gần như bất biến
(score đổi ±0,1, mất 1 TP) ⇒ covariate độ cao không phải nút thắt.
**Không cần biến thể thứ ba.**

Kết luận: lỗi kênh 4 là **nguyên nhân đủ** của TP=0. Toàn bộ kết luận FP/recall
của cổng C v4 (runbook §7b) đo trên model bị phá đặc trưng và **phải bỏ**.
