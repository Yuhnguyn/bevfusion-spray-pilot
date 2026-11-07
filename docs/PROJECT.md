# Dự án spray plume augmentation cho BEVFusion — tài liệu tổng

Cập nhật 2026-11-07. Đây là **cửa vào**: đọc file này trước, nó trỏ tới chỗ chi tiết.
Nhãn số: `[ĐO]` đo trong repo · `[PAPER]` Linnhoff et al. arXiv 2212.08558 · `[CODE]` đọc từ code ·
`[CHỌN]` quyết định của dự án, không có nguồn ngoài.

---

## 1. Câu hỏi, và phạm vi

**Một câu:** BEVFusion (LiDAR + 6 camera) mất bao nhiêu mAP khi có plume nước sau xe phía trước, và
augmentation plume có làm giảm mức mất đó không?

**Trả lời bằng:** một bảng paired A / B / B0 trên cùng bộ frame eval, cùng seed, cùng số update.

**Không trả lời** (và phải ghi trong report):
- Không chứng minh giúp được spray **thật** — thí nghiệm chạy trên plume tự sinh.
- Không nói gì về đường ướt, suy giảm tín hiệu sau plume (attenuation), nước bắn lên camera.
- Không nói gì ở tốc độ < 50 km/h hoặc trời mưa.
- 1 seed trên T4 → **tín hiệu định hướng**, không phải kết luận thống kê.
- Camera nhận `points_clean` còn LiDAR nhận `points` — trên xe thật hai nhánh không thể khác nhau.
  Nên kết quả dương là **cận trên lạc quan**.

---

## 2. Kiến trúc repo

| thư mục | làm gì | trạng thái |
|---|---|---|
| `spray/plume.py` | bộ sinh plume (thuần numpy, không phụ thuộc mmdet3d) | xong, kể cả `_thin_radial` (ticket 17) |
| `spray/plume_transform.py` | `PlumeTransform` — bọc generator vào pipeline mmdet3d | xong (ticket 07) |
| `spray/spray_stats.py` | thống kê trên SemanticSpray | xong (ticket 12) |
| `proxy_eval/` | matcher + AP/mAP, adapter cho output MIT | xong (ticket 05, 06) |
| `mit/bevfusion` | working copy MIT pinned `da93b27` (**gitignored**) | — |
| `kaggle/smoke_test/` | kernel build env + checkpoint + ticket 04/06/07 | xong |
| `kaggle/eligibility/` | kernel đo eligibility nuScenes (CPU, không checkpoint) | xong (ticket 18) |
| `tests/` | 56 test, chạy được trên laptop không cần GPU | 56 passed |
| `.scratch/spray-augmentation/` | spec, STATUS, 18 ticket | nguồn sự thật của tiến độ |

---

## 3. Một sample đi qua đâu

```
nuscenes_infos_{train,val}.pkl
   ▼ LoadPointsFromFile        points (N,5) = x,y,z,intensity,ring       N ≈ 34.720 [ĐO]
   ▼ GlobalRotScaleTrans       xoay/scale, ghi lidar_aug_matrix
   ▼ RandomFlip3D              lật trái/phải
   ▼ PlumeTransform  (07)      points (N+K,5)  +  points_clean (N,5)
   ▼ DefaultFormatBundle3D     tensor, gom batch
   ▼ BEVFusion.forward (08)
       ├── camera branch: 6 ảnh + points_clean → sparse depth → BEV camera
       └── lidar  branch: points              → voxel        → BEV LiDAR
       ▼ fuse → head → boxes_3d, scores_3d, labels_3d
   ▼ proxy_eval/matcher.py     TP/FP/FN → AP từng class → mAP
```

Sơ đồ chi tiết từng bước + công thức: `docs/walkthrough-tickets.md` §0–§3.

---

## 4. Plume được sinh ra thế nào

Tám bước, theo đúng thứ tự trong `spray/plume.py::inject_plume`. Công thức + ví dụ đầy đủ:
`docs/walkthrough-tickets.md` §3.

| # | Bước | Công thức / giá trị | Nguồn |
|---|---|---|---|
| a | tốc độ box | `speed_kmh = hypot(vx,vy) × 3.6` | [CODE] |
| b | cổng tốc độ | bỏ box `< 50 − 1e-3` km/h (epsilon chống lỗi float32 đúng 50,0) | [PAPER] §III-A |
| c | số cụm | tuyến tính `2` @50 km/h → `8` @130 km/h | dạng [PAPER] Fig. 4, hằng số [CHỌN] neo SemanticSpray |
| d | bán kính cụm | lognormal median **0,30 m**, σ 0,8, kẹp [0,10; 1,50] | [PAPER] Fig. 5 (μ=−1,2) |
| e | số điểm/cụm | median **theo cự ly**: 30 / 20 / 14 / 10 / 10 cho `0–5 / 5–10 / 10–20 / 20–30 / >30 m`, σ 0,67, kẹp [3; 200] | [ĐO] ticket 16 (median **gộp = 17,0**, đúng hằng số cũ) |
| f | đặt cụm | sau đuôi box `1–10 m` theo `−v/|v|`, lệch ngang `N(0;0,5)`, cao `U(0,2;2,0)` | [PAPER] định tính, khoảng cách [CHỌN] |
| g | rải điểm | đều trong khối cầu `u^(1/3)`, rồi **bẹp theo phương tia ×0,885** | dạng [CHỌN], hệ số [ĐO] ticket 17 → `r_range/r_extent` = 1,28 |
| h | lọc | bỏ điểm ngoài `±54 m`, bỏ điểm trong GT box nới `0,2 m`, cap `2.000` điểm/frame | [CHỌN] |

Đầu ra: `points` (đã chèn), `points_clean` (bản sao byte-equal trước khi chèn), `injected` (chỉ điểm mới),
`stats` (đếm từng nhánh). RNG dựng từ `seed` + hash(`token`) → cùng sample cùng seed cho cùng kết quả.

**Ví dụ số [ĐO]:** frame 34.720 điểm, box 50 km/h → 2 cụm → **76 điểm** (0,22%); 130 km/h → 8 cụm →
**174 điểm** (0,50%). Trên scene-0796 qua pipeline thật: **+127 điểm**, 12/12 check pass.

**Vì sao phải chèn sau `GlobalRotScaleTrans` + `RandomFlip3D`, trước `PointShuffle`:** velocity của box đã ở
LiDAR frame của keyframe và được xoay/flip cùng box (`lidar_box3d.py:152`); chèn sớm hơn thì plume trôi
khỏi vị trí hình học. Chi tiết: `docs/velocity-contract.md`.

**Đã sửa ở ticket 16–17 (2026-11-07):** số điểm/cụm nay **phụ thuộc cự ly** (30 điểm ở 0–5 m → 10 ở
20–30 m, đo được giảm **3,0×**), và cụm được **bẹp theo phương tia ×0,885** để `r_range/r_extent` = **1,28**
như số đo. Giả thuyết cũ "cảm biến chỉ thấy bề mặt cụm" là **sai**: paper cũng lấy range quanh **tâm** cụm,
và số đo cho cụm có bề dày theo tia.

**Còn biết là thiếu:** attenuation/occlusion (ADR-0002), `P_det` per-tia, cụm tan dần theo thời gian.
Bán kính giữ **0,30** theo paper dù đo được 0,755 m — số đo là cận trên do single-linkage chaining.

---

## 5. Đối chiếu với paper

| khối trong paper (Fig. 2) | repo | ghi chú |
|---|---|---|
| Cluster generation | có, nhưng 2–8 cụm (paper tới ~30) | repo chủ động chọn regime "ẩm/ướt một phần" |
| Update cụm theo thời gian (bay, tan dần) | **không có** | hợp lý: chỉ dùng keyframe, không có chuỗi thời gian |
| Ray casting + `P_det` mỗi tia | **không có** | repo đặt thẳng số điểm; đây là chỗ lệch lớn nhất |
| Attenuation `0,04 m⁻¹` (`exp(−2×0,02×d)`) | **không có** | ở `d = 0,5–0,8 m` intensity còn 98,0–96,9% → dưới ngưỡng lượng tử hoá |

**Không được so trực tiếp với +17,39 AP của paper.** Cùng bảng đó Voxel-RCNN chỉ +0,62 → hiệu ứng phụ
thuộc detector rất mạnh.

---

## 6. Số liệu dữ liệu

### nuScenes [ĐO 2026-11-07, `kaggle/smoke_test/evidence/eligibility.json`]

| tập | scene | keyframe |
|---|---|---|
| trainval | 850 | 34.149 |
| train | 700 | 28.130 |
| val | 150 | 6.019 |

Eligibility — box vehicle ≥50 km/h, **phía trước** (`x>0`), không lọc ego:

| điều kiện | trainval | val |
|---|---|---|
| d ≤ 10 m | 187 frame / 34 scene | 47 / 9 |
| d ≤ 30 m | 753 / 78 | **117 / 13** |
| d ≤ 50 m | 1.091 / 107 | **196 / 16** |
| d ≤ 50 m, ego ≥50 km/h | 175 / 15 | **2 / 2** |

- **Highway: 2 scene / 81 frame trên toàn bộ nuScenes, 0 scene trong val.** nuScenes là đô thị → hướng
  "chỉ dùng scene highway" không khả thi.
- Hàng đối chứng tái lập bảng cũ: **957 box / 698 frame** so với 952/697 (+0,53%) → định nghĩa mới tương
  đương định nghĩa cũ. Bảng cũ ghi "34.029 val frame" là **nhầm nhãn**: đó là toàn bộ trainval.

### SemanticSpray [ĐO, `docs/semantic-spray-stats.md`]

207 scene (mẫu 2.070 frame / 17.419 scan): **28.546 điểm/scan**, spray median **144 điểm/frame**, 14 cụm,
**17 điểm/cụm** (median **gộp**; theo cự ly là 30 → 10, xem ticket 16), **82% điểm intensity = 0**.
Chỉ dùng để calibrate — không train/eval trên đó (ADR-0003).

---

## 7. Thiết kế thí nghiệm

Ba arm, cùng checkpoint gốc, cùng split, cùng seed, cùng optimizer, cùng số update. **Chỉ dữ liệu train khác:**

| arm | train | eval | trả lời |
|---|---|---|---|
| **A** | sạch | sạch + plume | model không biết plume thì mất bao nhiêu |
| **B** | sạch + plume | sạch + plume | augment có thu hẹp khoảng mất không |
| **B0** | không train; lọc điểm nghi spray rồi chạy model A | sạch + plume | chỉ cần lọc, khỏi train, có đủ không |

**Eval set đã chốt (quyết định 2026-11-07, phương án A):** val split, box ≥50 km/h phía trước, `d ≤ 50 m`,
**không lọc vận tốc ego** → **196 frame / 16 scene**; báo per-range 0–30 m (117 frame) và 30–50 m (79 frame).
Rủi ro đã biết: 16 scene → khoảng tin cậy rộng, cổng G3#1 có thể fail **vì thiếu mẫu**, không phải vì
augment vô dụng. Nếu fail thì kết luận đúng là "không đo được gap với n=16 scene".

Hai chi tiết bắt buộc khi đo:
- **Held-out spray:** tham số plume lúc eval khác lúc train (khác mật độ, khác seed). Trùng thì model chỉ
  học thuộc.
- **Bootstrap theo scene**, không theo frame: mỗi scene 40 keyframe gần giống nhau.

Năm điều kiện để được nói "thành công" — chốt trước, không sửa sau khi thấy số: xem
`.scratch/spray-augmentation/STATUS.md` và `docs/walkthrough-tickets.md` §9 (5 điều kiện).

---

## 8. Sổ quyết định

| ngày | quyết định | lý do / bằng chứng |
|---|---|---|
| 11-04 | pin MIT `da93b27`, không dùng HEAD | tái lập được (ADR-0001) |
| 11-04 | v1 chỉ plume, không wet-ground/attenuation | attenuation ở `d = 0,5–0,8 m` ~2–3% intensity (ADR-0002) |
| 11-04 | không train/eval detection trên SemanticSpray | chỉ để calibrate (ADR-0003) |
| 11-05 | chèn plume **chỉ** vào nhánh LiDAR, camera nhận `points_clean` | cần đúng một biến thay đổi; đổi lại kết quả là cận trên |
| 11-05 | ngưỡng 50 km/h | paper §III-A; hạ xuống 30 làm mất tính chính danh |
| 11-07 | giữ 50 km/h, **bỏ lọc vận tốc ego** | paper có kịch bản ego đứng yên; lọc ego làm val còn 0 frame |
| 11-07 | eval set = val, `d ≤ 50 m` → 196 frame / 16 scene | trần cứng của val ở 50 km/h; tự chia lại train sẽ rò rỉ từ checkpoint pretrained |
| 11-07 | không dùng scene highway | 0 scene highway trong val, 2 scene trên toàn dataset |

---

## 9. Bản đồ tài liệu

| file | nội dung |
|---|---|
| `HANDOFF.md` | trạng thái + môi trường + chạy tiếp ở máy khác |
| `.scratch/spray-augmentation/STATUS.md` | **board**: ticket, thứ tự, quyết định đã chốt, rubric nghiệm thu |
| `.scratch/spray-augmentation/spec.md` | spec implementation-ready (interface contract, DoD từng ticket) |
| `docs/walkthrough-tickets.md` | giải thích từng ticket, công thức từng bước, chỗ dễ sai |
| `docs/plume-model-provenance.md` | từng tham số `PlumeConfig` lấy từ đâu |
| `docs/velocity-contract.md` | velocity ở frame nào; số đo eligible + đính chính nhãn val |
| `docs/semantic-spray-stats.md` | thống kê spray thật để calibrate |
| `docs/nuscenes-eligibility.md` | bảng đo eligibility đầy đủ (ticket 18) |
| `docs/adr/0001..0003` | ba quyết định nền |
| `docs/kanban.html` | board tự sinh (`scripts/build_kanban.py`) |

---

## 10. Trạng thái ngắn

Xong: 01, 02, 02b, 03, 04, 05, 06, 07, 08, 12, 15, 16, 17, 18, 19, 20, 21, 22. Test: **56 passed**.
Tiếp theo: **23** (3 chỉnh nhỏ) → **09** (e2e trên Kaggle) → **10 → 11** (chạy 3 arm) → **13** (cổng kết luận).
Chi tiết thứ tự và lý do: `STATUS.md`.