# Model 0 mù trên SSPP — lỗi harness hay domain gap?

2026-11-19 · subagent chẩn đoán · nhánh `sspp` · chỉ đọc, không sửa code.
Nguồn số: `gate_c_detections.jsonl` + `_summary.json` của kernel v4
(`/tmp/gate_c_out/gate_c_out/`), 954 frame × 3 nhánh, τ = 0,20.
Script đo tạm: `.scratch/tmp/diag_{a2,geom,det,stats,near}.py`.

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

## 5. Kế hoạch test trên Kaggle (~15–20 phút GPU, CHƯA chạy — chờ Lead duyệt)

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
