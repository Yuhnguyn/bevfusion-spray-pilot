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
| `spray/plume.py` | vỏ generator + `inject_plume` / `inject_plume_stateful`; khối sau đuôi | v2 (ticket 28) |
| `spray/plume_state.py` | `PlumeState`, `SprayCluster`: sinh cụm, advection hệ ground, tan theo `T`, xoá `age > 4T` | v2 (28b–28d) |
| `spray/plume_context.py` | `PlumeContext`: tốc độ ego/vật thể, `wfh_mm`, hình học box | v2 (26) |
| `spray/plume_transform.py` | `PlumeTransform` — bọc generator vào pipeline mmdet3d | xong (07) |
| `spray/raycast.py` | cast beam × cầu, `P_det`, attenuation, strongest-return | 29b; **còn sửa ở 29c** |
| `spray/beam_model.py` | lưới tia đều 0,333° × 0,197° | 29a; **`beam_elevation.yaml` bị bác bỏ, xoá ở 29c** |
| `spray/wet_ground.py` | Snell eq. 12–19, chỉ `set_intensity`, mặc định tắt | xong (27a/b) |
| `spray/spray_stats.py` | thống kê trên SemanticSpray | xong (12) |
| `proxy_eval/` | matcher + AP/mAP, adapter cho output MIT | xong (05, 06) |
| `mit/bevfusion` | working copy MIT pinned `da93b27` (**gitignored**) | — |
| `kaggle/smoke_test/`, `kaggle/eligibility/` | kernel build env + đo eligibility nuScenes | xong (02b, 04, 18, 19) |
| `tests/` | chạy trên laptop không cần GPU | **239 passed, 4 skipped** (2026-11-11); 4 test e2e chỉ chạy trên kernel |
| `.scratch/spray-augmentation/` | spec v2, STATUS, ticket | nguồn sự thật của tiến độ |

---

## 3. Một sample đi qua đâu

```
nuscenes_infos_{train,val}.pkl
   ▼ LoadPointsFromFile        points (N,5) = x,y,z,intensity,ring       N ≈ 34.720 [ĐO]
   ▼ GlobalRotScaleTrans       xoay/scale, ghi lidar_aug_matrix
   ▼ RandomFlip3D              lật trái/phải
   ▼ PlumeTransform (26–29)    context → state.spawn/advance → raycast → points (N+K,5) + points_clean (N,5)
   ▼ DefaultFormatBundle3D     tensor, gom batch
   ▼ BEVFusion.forward (08)
       ├── camera branch: 6 ảnh + points_clean → sparse depth → BEV camera
       └── lidar  branch: points              → voxel        → BEV LiDAR
       ▼ fuse → head → boxes_3d, scores_3d, labels_3d
   ▼ proxy_eval/matcher.py     TP/FP/FN → AP từng class → mAP
```

Sơ đồ chi tiết từng bước + công thức: `docs/walkthrough-tickets.md` §0–§3.

---

## 4. Plume được sinh ra thế nào (v2)

Năm tầng, theo đúng thứ tự trong `spray/plume_transform.py`:

| # | Tầng | Việc | Công thức / giá trị | Nguồn |
|---|---|---|---|---|
| 1 | `plume_context.py` | dựng ngữ cảnh một frame | `object_speed_mps` (`v_abs`), `object_velocity_ego_mps`, `wfh_mm`, kích thước box | [CODE] 26 |
| 2 | `plume_state.spawn` | sinh cụm mỗi `Δt = 0,1 s` | `round(max(0,(0,2·wfh+0,1)·(v−50)))`; tâm **uniform** trong khối sau đuôi: dài `|v|·Δt`, rộng `3,4 m`, cao `1,5 m`; `r = min(1,0; lognormal(−1,2; 0,8))` | công thức [PAPER] §III-B; kích thước khối [CODE] `dee.cpp:559–561` (**paper không cho số**) |
| 3 | `plume_state.advance` | trôi + tan | advection hệ **ground**, `v ← C·v̂_rel·|v_rel|²·Δt + v`, `C = −0,15 m⁻¹`, gió 208°/2 m/s; `P_t = e^{−t/T}`, `T = 0,02·wfh·(v−50)+0,2`; xoá khi `age > 4T` | `C`, `P_t`, `T` [PAPER]; `4T` [CODE] `dee.cpp:445–450` (**paper không có luật xoá**) |
| 4 | `raycast.py` | sinh detection | lưới tia đều **0,333° × 0,197°**; `P_det = n/n_max(r_cl, p_cl)` với lognormal `µ=−2,3 σ=1,09` bốc **mỗi cụm**, Bernoulli **mỗi tia**; attenuation `e^{−2·0,02·L}`; mỗi beam giữ echo mạnh nhất | [PAPER] eq. (7), Fig. 7; attenuation [CODE] |
| 5 | `wet_ground.py` | ướt mặt đường | Snell eq. 12–19, **chỉ** `set_intensity`, không xoá điểm; mặc định **tắt** | [CODE] `dee.cpp:305–380` |

`points_clean` là bản sao byte-equal trước khi chèn, dùng cho nhánh camera. RNG dựng từ
`seed` + hash(`token`) ⇒ cùng sample, cùng seed, cùng kết quả.

**Đang sai, sửa ở 29c** `[ĐO]`:

- `raycast.py:256–261` xuất `intensity ≈ 72–166` trên thang 255. Paper: *"the final intensity
  value of the simulated spray detections are set to 0"* ⇒ phải là **0**.
- `plume.py:104` còn trần `max_injected_points = 2000`; hình học đúng cho 807–1.555 điểm/frame nên trần này cắt oan.
- `plume.py:115–116` khối cao `1,5 m` hardcode, trong khi nhãn thật phủ **6–90 % chiều cao box**.
- Latency **266–476 ms/frame** với 100 cụm ⇒ phải < 100 ms.

**Lịch sử v1 (không còn dùng):** v1 đặt `points_per_cluster` theo cự ly (30/20/14/10/10) và bẹp
điểm theo phương tia `×0,885`. Cả hai đã bỏ vì điểm phải **nổi lên từ ray casting**. Con số
"17,06 cụm/frame" của v1 là artifact của single-linkage (bán kính 0,5 m, `dense-min 5`), không
so được với `minPts = 3` của paper.

---

## 5. Khác biệt so với paper — và căn cứ để chọn như vậy

Chi tiết từng tham số: `docs/plume-model-provenance.md`. Mục này là **bảng quyết định**: mỗi chỗ repo làm khác
paper đều phải trả lời được "dựa vào đâu".

### 5.1 Thứ tự ưu tiên nguồn (khi hai nguồn lệch nhau)

1. **Code publish của paper** (`openMSL/sl-1-2`, MPL-2.0) — paper viết bằng lời và có chỗ viết tắt; code là
   bản chạy được, đọc được từng dòng. Ví dụ: "loại xe" có trong paper nhưng **không** có trong code.
2. **Số đo trên dữ liệu của chính mình** — dùng khi paper/code không nói, hoặc nói về cảm biến & xe của họ
   (VW Golf/Crafter, VLP-32C) chứ không phải nuScenes. Nguồn: ticket 16, `docs/semantic-spray-stats.md`.
3. **Quyết định của repo** — không có nguồn ngoài, nhưng phải ghi lý do **và** điều kiện mở lại (ADR-0002
   ghi phần bị cắt là "v2", không phải "không bao giờ").

**Tiêu chí loại bỏ đứng trên cả ba:** cơ chế nào có tác động **đo được** nhỏ hơn ngưỡng nhiễu của phép đo
thì không vào v1 — vì nó thêm biến thí nghiệm mà không thêm tín hiệu. ADR-0002 chốt: *"một biến duy nhất
thay đổi giữa hai arm, nên phép so sánh paired còn hiệu lực"*.

### 5.2 Bảng khác biệt

| # | Paper / code tham chiếu | Repo | Căn cứ |
|---|---|---|---|
| 1 | **Không có khái niệm "số điểm mỗi cụm"**: điểm rơi ra từ tia cắt khối cầu × `P_det` | **Đã bỏ ở v2** — không còn `points_per_cluster` | Bảng `30/20/14/10/10` của v1 đo bằng single-linkage (radius 0,5 m, `dense-min 5`), không phải `minPts = 3` ⇒ số **17,0 không dùng** |
| 2 | **Ray casting + `P_det` mỗi tia** (lognormal `µ=−2,3 σ=1,09`, bốc **mỗi cụm**, Bernoulli **mỗi tia**) | **Đã có** (`raycast.py`, 29b) | Trước đây repo cho rằng "áp thêm `P_det` là đếm hai lần" — **sai**: `17 điểm/cụm` của v1 đến từ single-linkage chứ không phải từ detect. Paper: `P_det = n/n_max`, `n` = detection đo được, `n_max` = số tia cắt khối cầu |
| 3 | Paper: số cụm phụ thuộc tốc độ **và loại xe**. Code: chỉ `(0,2·wfh + 0,1)·(v−50)` | Theo **code** | [CODE] `dee.cpp:509–512` + `profile_VLP32.hpp.in`: tham số spray nằm trong profile **loại cảm biến**, không có biến loại xe ⇒ divergence paper ↔ code |
| 4 | Code rút `T ~ N(T; 0,2)` (std bằng chính mean) | `T = 0,02·wfh·(v−50)+0,2`, **không** cộng nhiễu | Bỏ nhiễu vì **15,9 %** lần rút cho `T ≤ 0` (cụm chết ngay) ⇒ không tái lập giữa seed, A/B mất hiệu lực |
| 5 | Code cắt `std::min(1.0f, …)` | Trần **1,00 m** | [CODE] `dee.cpp:528`; trần 1,5 m cũ chỉ bóp 2,2% cụm, trần 1,0 bóp **6,7%** — đo lại **6,51%** (ticket 23) |
| 6 | Attenuation `exp(−2×0,02×d)` = **0,04 m⁻¹** | **Đã có** (`raycast.py`, 29b) | Áp lên cả điểm thật nằm sau plume: đo được **631 điểm thật bị giảm intensity** mỗi frame |
| 7 | Occlusion: điểm spray thắng theo `power = intensity/d²` (`add_max_detection`) | Không có | Spray 25 m: `3,1×10⁻⁴`; xe 40 m thắng khi `I_xe > 0,5`, mà `I_xe` thật **4–40** ⇒ xe thắng **8–80×**, **81%** tia xuyên ⇒ ảnh hưởng **<3%** |
| 8 | `simulate_wet_pavement` (Fresnel, `\|z−ground\| < 0,2 m`) | **Đã có** (`wet_ground.py`, 27a/b), mặc định **tắt** | Chỉ `set_intensity`, không xoá điểm; giữ tắt để hai arm A/B chỉ khác đúng một biến |
| 9 | Drag `C = −0,15 m⁻¹`, cụm trôi & tan theo thời gian | **Đã có** (`plume_state.py`, 28b–28d) | State sống trong scene; advection hệ ground, xoá `age > 4T` (**paper không có luật xoá**, đây là `[CODE]`) |
| 10 | Paper §III: cụm đặt **uniform trong vùng sau vật thể**, paper **không cho kích thước** | khối `\|v\|·Δt × 3,4 × 1,5 m` sau đuôi; chiều cao **sẽ đổi thành 5–92 % chiều cao box** ở 29c | kích thước [CODE] `dee.cpp:559–561`; chiều cao [ĐO] trên 939.803 điểm: p5 0,16 / med 1,51 / p95 2,36 m (`plume-geometry-measurements.md` §A) |
| 11 | `water_film_height` là **input** của OSI | `wfh ~ exp(0,1…1,2) mm` **mỗi frame** | [PAPER] §IV. Ba mức cố định khi calibration: 0,5 / 0,75 / 1,0 mm. Con số `17,06 cụm/frame` của v1 **không dùng** (xem dòng 1) |
| 12 | Paper sinh cho **ego và mọi vật thể di chuyển** | Chỉ sinh sau **xe phía trước** | Nhãn thật: **62–93 %** điểm spray nằm ở `x < 0` (median `x ≈ −5 m`) ⇒ một phần là self-spray của ego. Chưa làm; ticket riêng sau 29c |

### 5.3 Hệ quả cho claim

- **Không được so trực tiếp với +17,39 AP của paper.** Cùng bảng đó Voxel-RCNN chỉ +0,62 → hiệu ứng phụ thuộc
  detector rất mạnh. Claim đúng phạm vi: *plume augmentation calibrated theo thống kê spray **đo được**, cho
  bài toán fusion trên nuScenes*.
- Sau 29b, repo **đã tái lập** ray casting + `P_det` + attenuation; **chỉ còn occlusion** là thiếu.
  Hướng lạc quan còn lại, xếp theo mức ảnh hưởng: (1) camera branch nhận `points_clean` →
  (2) `intensity` đang xuất sai giá trị (phải **0**) → (3) self-spray của ego chưa có → (4) occlusion.
- Dòng **10** (vị trí + chiều cao cụm) **không còn mù**: đã đo trên **939.803 điểm** — chiều cao
  6 / 58 / 90 % chiều cao box, `|y|` p95 **2,31 m**, `x` trải **−35 … +25 m**. Xem
  `docs/plume-geometry-measurements.md`.
- Dòng **11** (`wfh`) đã chốt: `exp(0,1…1,2) mm` mỗi frame, dùng **mm** cho cả `count` và `T`
  (user, 2026-11-10). Hệ quả `T(130) = 1,8 s` ⇒ vệt `v·T = 65 m`; xem `spec-v2-paper-faithful.md` §1.
- Ba thứ paper **không** cho nên là quyết định của mình, phải ghi đúng nhãn: kích thước khối
  (`[CODE]`), luật xoá `age > 4T` (`[CODE]`), và có sinh self-spray hay không (`[CHỌN]`).

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

207 scene (mẫu 2.070 frame / 17.419 scan): **28.546 điểm/scan**, spray median **144 điểm/frame**,
**82 % điểm intensity = 0**, spray chỉ chiếm **0,25–0,5 %** số điểm mỗi scan.
Chỉ dùng để calibrate — không train/eval trên đó (ADR-0003).

> ⚠️ Các số **cụm** từng ghi ở đây (14 cụm/frame, 17 điểm/cụm) đo bằng **single-linkage**
> (bán kính 0,5 m, `dense-min 5`) nên bị chaining làm sai. Paper dùng DBSCAN `minPts = 3`.
> **Không dùng** các số đó làm mốc; phải đo lại theo recipe paper (ticket 29d).
> Hình học dùng được (đo trên 939.803 điểm, không phụ thuộc clustering) nằm ở
> `docs/plume-geometry-measurements.md`.

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
| 11-10 | v2 mở lại wet-ground + attenuation + state (thay ADR-0002) | ADR-0004 |
| 11-10 | `wfh` dùng **mm** ở cả `count` và `T`; sample `exp(0,1…1,2)` mỗi frame | paper §IV; xem `spec-v2-paper-faithful.md` §1 |
| 11-11 | **bỏ** bảng `ring → elevation`, cast trên lưới tia đều 0,333° × 0,197° | `docs/plume-beam-table.md` mục ĐÍNH CHÍNH |
| 11-11 | **không** đặt ngưỡng cắt cụm theo mét | p5 của `x` dao động **−40,6 … +3,7 m** giữa hai nửa scene ⇒ không phải hằng số; `n_max ∝ 1/d²` tự dập đuôi |
| 11-11 | kích thước khối lấy từ `dee.cpp` (`v·Δt × 3,4 × 1,5`), paper không cho số; chiều cao đổi thành **5–92 % chiều cao box** | paper QA §1; đo 939.803 điểm |
| 11-11 | SemanticSpray chia **2 vai** (cal / held-out) theo scene; detector vẫn train/eval trên nuScenes | 207 scene = 207 timestamp riêng ⇒ chia theo run; ADR-0003 |
| 11-11 | confidence 3 bộ của paper (cal / train / test) áp vào dự án: tham số generator đo trên `cal`, báo cáo trên `held-out` | paper QA §5 |

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
| `docs/adr/0001..0004` | bốn quyết định nền (0002 đã bị 0004 thay) |
| `docs/plume-v2-measurements.md` | số đo 0 GPU của v2 (tốc độ, beam, quỹ đạo, hình học frame) |
| `docs/plume-geometry-measurements.md` | hình học plume thật vs mô phỏng theo 9 mức tốc độ |
| `docs/paper-qa-notebooklm.md` | paper thật sự nói gì, tách khỏi cái `dee.cpp` tự đặt |
| `docs/plume-v1-defects.md` | 8 lỗi cấu trúc của v1 (D1–D8) |
| `docs/plume-beam-table.md` | bảng `ring → elevation` — **đã bị bác bỏ**, chỉ giữ làm phản chứng |
| `docs/DOC-AUDIT-2026-11-11.md` | audit tài liệu: chỗ lệch, chỗ trùng, việc phải sửa |
| `docs/kanban.html` | board tự sinh (`scripts/build_kanban.py`) |

---

## 10. Trạng thái ngắn

Xong: 01–24 (v1, đã đóng) và **25, 26, 27a/b, 28a–d, 29a, 29b** (v2).
Test: **239 passed, 4 skipped** (2026-11-11, laptop CPU).

Đang làm: **29c** — sửa `intensity = 0`, bỏ trần 2.000, khối theo phân số chiều cao box, tối ưu
`< 100 ms/frame`, marker `PLUME_RAYCAST`.
Tiếp: **29d** (cổng: đo detection/cụm theo recipe paper trên split `cal` / `held-out`) → **29c nối
`inject_plume_stateful`** → **30** (trần + intensity + ring) → **31** (nghiệm thu).
Chỉ sau đó mới mở lại A/B trên Kaggle. Chi tiết thứ tự: `STATUS.md`.