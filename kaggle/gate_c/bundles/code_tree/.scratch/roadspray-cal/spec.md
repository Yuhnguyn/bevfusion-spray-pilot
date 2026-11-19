# Spec: dùng RoadSpray làm nguồn calibration cho plume generator

Trạng thái: **đề xuất, chưa làm** · 2026-11-18 · nhánh `sspp` @ `064f1c1`
Bối cảnh: repo đang dùng **cùng một bộ SSPP** cho cả ba vai calibration / train / test.
Spec này định nghĩa cách tách vai **calibration** ra khỏi SSPP bằng RoadSpray; train/test
**không thể** tách (không có bộ nào khác có nhãn + box).

Phân tích nền: `docs/reference/roadspray-fit-for-repo.md`. Số đo bag: `.scratch/roadspray-fit/ingestion.md`.

---

## 0. Vấn đề, đo lại bằng số

`[ĐO]` `scripts/diag_split_structure.py`, `diag_split_options.py` + đếm `cal` theo tốc độ:

| Đại lượng | Số |
|---|---:|
| scene `cal` (dùng chọn tham số generator) | 104 / 207 |
| frame `cal` | 1.321 |
| test scene là `cal` | **6 / 12** = 503/954 frame test (52,7 %) |
| scene `cal` **ở đúng 3 tốc độ test** (50/90/130) | **34** |
| … trong đó là test scene | 6 |
| … trong đó **không** phải test scene | **28** |

Hàng cuối là chỗ then chốt: **bỏ scene test khỏi `cal` vẫn còn 28 scene `cal` ở đúng điều kiện
tốc độ của test** (cùng group, cùng cự ly, cùng mẻ nước, chỉ khác `itr_after_water`). Đó là lý do
"cắt cal" rẻ tiền **không** đóng được lỗ hổng — chỉ một bộ dữ liệu khác mới đóng được.

---

## 1. Giao thức đích

```
RoadSpray *_static (333 recording, ego ĐỖ, KHÔNG nhãn)
   │  recipe Paper A §III-B: DBSCAN cầu eps 0,7° / minPts 3, elevation 0,333°,
   │  trong "spray filter region" sau xe, cự ly 25 m
   ▼
clusters/frame(v, class, water)   ← thay _CLUSTER_VISIBLE_BY_SPEED
   │  × K(T_ref) (lifetime model, giữ nguyên [CODE])
   ▼
rate(v) ──► generator plume (Arm B)           ── cal KHÔNG chạm scene SSPP nào
                                                   │
SSPP 207 scene ──► train 16 / val 8 / test 12 ─────┘  (giữ nguyên, split theo tốc độ)
   ▼
Model 0 / Arm A / Arm B → FP/frame, recall, SPF proxy
```

Kiểm chứng nội bộ của calibration (không dùng SSPP): đo lại cùng bộ static ở **50 m** rồi so
mô phỏng vs đo — đúng cách Paper A §IV-A kiểm (`[PAPER]` *"object distances and values, which were
not utilized for the model calibration, are used on the same data set"*).

**Cái gì được sửa:** vai `cal` rời SSPP hoàn toàn ⇒ `cal ∩ test = 0`, `cal ∩ train = 0`, và
generator không còn thấy thống kê spray ở 50/90/130 km/h của SSPP. Protocol thành hình dạng paper:
cal = scenario ego đỗ, label-free, 25 m; kiểm 50 m.

**Cái gì KHÔNG được sửa:** train/val/test vẫn cùng một campaign, cùng lưới, cùng rig. Test vẫn chỉ
là "tốc độ chưa thấy trên cùng rig". Câu đó phải giữ nguyên trong Limitations — RoadSpray không
mua được bộ test của paper (§V-D 1.463 frame **chưa công bố**).

**Giả định phải khai:** tham số vật lý của plume (số cụm sinh ra, bán kính, `P_det`, attenuation)
**không phụ thuộc ego đang chạy hay đỗ**, chỉ phụ thuộc tốc độ/class/mức nước/cự ly của vật thể.
Đây đúng là giả định của Paper A (calibrate ở passing, áp lên STF và lên bộ test cao tốc) `[PAPER]`.

---

## 2. Việc phải làm

### W0 — Dọn metadata (30 phút, làm ngay được)

- Copy `meta_data_measurement.xlsx` vào `data/roadspray/` (hiện chỉ có ở `.scratch/roadspray-fit/tmp/`;
  tải lại bằng REST `.../server/api/core/bitstreams/<uuid>/content` — đường `/download` bị Anubis chặn).
- Ghi vào `data/roadspray/README.md`: release có **9 file / 4 zip**, xlsx phủ 549/550 recording
  (thiếu dòng cho `Crafter_static/2021-09-09-13-24-38_0.bag`), `Golf_dynamic.zip` local bị cắt
  (1,0/6,0 GB), `Golf_static.zip` chưa tải.
- Chưa cần `Golf_*` để làm W1–W2: bảng `crafter` là bảng duy nhất paper định lượng (Fig. 4/5/7).

### W1 — Adapter (2–3 h)

Tạo `spray/roadspray_adapter.py` + `scripts/build_roadspray_static.py`.

- Vào: `data/roadspray/Crafter_static.zip` (163 bag) + xlsx.
- Ra: `data/RoadSprayStatic/Crafter_static/<NNNN>_<bag>/velodyne/*.bin` (5×f32) + `metadata.txt`.
  **Không** ghi `labels/`, `object_labels/`, `image_2` — không có và không cần.
- Biến đổi điểm: `p_sspp = R·p_bag + t` với `R(roll −0,0183, pitch −0,0100, yaw −1,5847)`,
  `t = (1,33334; 0,00935; 1,68467)` `[ĐO]`, residual `7e-6 m`. `intensity` và `ring` **giữ nguyên
  từng byte** (đã đối chiếu với SSPP).
- `metadata.txt` sinh từ xlsx: `object_velocity`, `itr_after_water`, `measurement_itr`, bỏ
  `distance_to_object` (trống cho static).
- Đọc zip bằng cách stream-extract **một bag một lần** rồi xoá (đừng giải nén cả 16 GB; đĩa còn ~27 GiB).
- **Tiêu chí đạt:** `ROADSPRAY_OK scenes=163 frames≈12058`; ít nhất 2 bag kiểm chéo số frame với
  `unzip -l`; 1 frame của bag dynamic biến đổi ra đúng frame 0 của scene SSPP tương ứng (sai ≤ 1e-5 m).

### W2 — Đo calibration theo §III-B (3–5 h, **phần khó nhất**)

Tạo `scripts/measure_roadspray_cal.py`. Bốn bước:

1. **Quỹ đạo vật thể.** Topic `/front_ibeo_lux/as_tx/objects` (MarkerArray, id ổn định).
   Lấy track có tốc độ ≈ `object_velocity` trong xlsx. **Đây là ground truth miễn phí:** nếu tracker
   đúng, median speed của track phải khớp xlsx trong ±5 km/h ở ≥90 % recording; sai thì dừng và
   sửa tracker trước khi đo cụm. (Đây chính là việc `scripts/probe_static_speeds.py` đang mò —
   giờ có đường đối chiếu nên không cần mò nữa.)
2. **Chọn frame theo cự ly.** `r = ‖p_obj‖` (mặt phẳng ngang). Calibration: `24 ≤ r ≤ 26 m`
   (paper chọn 25 m). Kiểm: `45 ≤ r ≤ 55 m`. Mỗi lần xe chạy qua cho ~1–2 frame ở mỗi bin; tổng
   theo (class, vận tốc, mức nước) là đủ.
3. **Spray filter region** `[CHỌN]` — paper **không** cho kích thước (`paper-qa-notebooklm.md` §1).
   Đề xuất: box trong hệ vật thể, `s ∈ [−(2,5·L); 0]` sau đuôi xe, `|t| ≤ W/2 + 1,0 m`,
   `z ∈ [0; 2,0] m` trên mặt đường (`L, W` theo box class: Crafter 6,83 m). **Bắt buộc** báo
   độ nhạy với `2,0·L` và `3,0·L` — nếu chênh >20 % thì kết luận không được phép tự tin.
4. **Đếm cụm** bằng `spray.semantic_stats.cluster_angular` (eps 0,7°, minPts 3, elevation snap
   0,333°, azimuth wrap) — **dùng lại đúng toán tử paper**, không viết mới.

**Hai đại lượng phải đo và báo riêng, đừng lẫn:**

| Ký hiệu | Cách tính | Dùng cho |
|---|---|---|
| `clusters_visible` | số cụm trong region, **không** chuẩn hoá | thay trực tiếp `_CLUSTER_VISIBLE_BY_SPEED` (cùng nghĩa "cụm/frame") |
| `clusters_per_scan` | `clusters_region × (v·Δt) / L_region`, `Δt = 0,1 s`, đúng công thức paper §III-B | đối chiếu Fig. 4 của paper |

Đây là **bẫy lớn nhất của cả spec**: bảng hiện tại là `visible`, còn `rate(v) = visible / K(T_ref)`
(`plume.py:214-231`) có `K` từ 2,51 (50 km/h) tới 18,2 (130 km/h). Đem `clusters_per_scan` của paper
gán vào chỗ `visible` là lệch **~K lần** (tới 18× ở 130 km/h). Phải chọn một nghĩa và ghi vào doc.

**Mức nước:** paper gộp `itr_after_water` 1–6 thành 3 lớp (moist / partially / fully covered).
Đề xuất `[CHỌN]`: 1–2 → fully, 3–4 → partially, 5–6 → moist (nước vơi dần sau mỗi lượt).

**Tiêu chí đạt:**
- Xu hướng **tăng** theo tốc độ 50→130 cho fully covered, khớp hình dạng Fig. 4.
- Giá trị 130 km/h nằm trong dải paper vẽ (Fig. 4: trục cụm 0–30).
- Độ nhạy region length (2·L vs 3·L) < 20 %.
- Báo cả mean và sd giữa 3 lần chạy lặp (`measurement_itr` 1–3) — đây là thứ SSPP không cho.

**Bonus (chỉ làm nếu W2 nhanh):** bán kính cụm (Fig. 5) và `P_det = n/n_max` (Fig. 7). `P_det` cần
`n_max` = số tia cắt khối cầu — `spray/raycast.py` đã có phần hình học đó.

### W3 — Báo cáo số đo (2–3 h)

`docs/measurements/roadspray-static-calibration.md`: bảng `clusters_visible` và `clusters_per_scan`
theo (class × tốc độ × mức nước), sai số, độ nhạy region, so với Fig. 4/5/7 (dạng hình, không so số
tuyệt đối vì khoảng cách đo khác), và **tuyên bố rõ bảng nào thay bảng nào**. Mọi số mang nhãn
`[ĐO]`/`[PAPER]`/`[CHỌN]`.

### W4 — Nối vào generator (1–2 h)

`spray/plume.py`:

- Thêm bảng `_CLUSTER_VISIBLE_BY_SPEED_ROADSPRAY` (giữ bảng SSPP cũ) + field
  `PlumeConfig.calibration_source: str = "sspp_cal" | "roadspray_static"`.
  **Không** xoá bảng cũ: cần cho ablation B1/B2 (§4) và để tái lập kết quả cũ.
- Ghi `calibration_source` vào metadata checkpoint + mọi báo cáo đo.
- Sửa luôn lỗi đã biết: `inject_plume` gọi `cluster_count_for_speed(speed_kmh, cfg)` **không truyền
  `vehicle_class`** ⇒ luôn dùng bảng `crafter` (`plume.py:359`, `generator-reading-map.md` §5).
  Có bảng Golf từ RoadSpray thì phải truyền.
- **Cảnh báo thời điểm:** W4 làm đổi ngân sách cụm của Arm B ⇒ phải quyết **trước khi chạy 3 arm**,
  không phải sau. Chạy arm rồi mới đổi là phải train lại.

### W5 — Thay cổng (1 h)

Cổng 7 tiêu chí `cal`/`held-out` hiện tại (`semantic-spray-cal-vs-heldout.md`) **không còn là cổng
chống leak** khi cal đã rời SSPP. Thay bằng:

1. Assertion cứng: `cal ∩ test = 0` và `cal ∩ SSPP = 0` (chạy trong `build_sspp_split.py`).
2. Kiểm provenance: nếu `calibration_source == "roadspray_static"` thì bảng SSPP không được đọc
   (fail fast, không im lặng).
3. Bảng so sánh "RoadSpray cal vs SSPP cal" — **báo cáo, không pass/fail**. Nếu hai nguồn lệch >2×
   thì đó là phát hiện, không phải lỗi.

**Tổng: 9–14 h.**

---

## 3. Rủi ro, xếp theo mức thiệt hại

| # | Rủi ro | Thiệt hại | Giảm thiểu |
|---|---|---|---|
| 1 | Lẫn `clusters_visible` với `clusters_per_scan` | generator lệch tới 18× ⇒ Arm B vô nghĩa | đo cả hai, chọn một, unit test chuỗi `visible == round(rate×K)` |
| 2 | Spray filter region là `[CHỌN]` nhưng quyết định con số | kết luận phụ thuộc tham số tự chọn | báo độ nhạy 2·L vs 3·L, ghi `[CHỌN]` |
| 3 | Tracker Ibeo kém ⇒ cự ly/region sai | cả W2 sai hệ thống | đối chiếu tốc độ tracker với xlsx trước khi đo cụm |
| 4 | Mỗi lần chạy qua chỉ 1–2 frame ở 25 m | ô (speed × water) chỉ 3–6 frame ⇒ mean nhiễu | gộp 3 mức nước, báo sd giữa 3 lần lặp |
| 5 | Đổi bảng sau khi đã train | phải train lại | W4 trước khi train; hoặc ablation B1/B2 |
| 6 | 163 bag × ~12k frame → 7,4 GB | sát đĩa (còn ~27 GiB) | chỉ Crafter trước; không convert ảnh |

---

## 4. Cách biến nghi ngờ thành kết quả (khuyến nghị)

Đừng chọn một nguồn cal rồi hy vọng. Chạy **4 arm** thay vì 3:

| Arm | Cal source | Trả lời |
|---|---|---|
| Model 0 | – | mức hỏng gốc |
| Arm A | – | đối chứng |
| Arm B1 | SSPP `cal` (hiện tại) | augment, cal in-sample |
| **Arm B2** | **RoadSpray static** | augment, cal độc lập |

Nếu `B1 ≈ B2` (chênh < sai số CI) ⇒ **leak không ảnh hưởng kết luận**, trích dẫn được là đã kiểm.
Nếu `B2` yếu hơn hẳn `B1` ⇒ leak thật, và bạn có một phát hiện đáng báo cáo. Cách này biến một
điểm yếu protocol thành một phép đo, và chỉ tốn thêm **1 lần train** (2000 steps) — rẻ hơn nhiều so
với việc hậu kiểm bằng lý lẽ.

---

## 5. Phương án rẻ hơn nếu chưa muốn 9–14 h

| Phương án | Giờ | Sửa được | Không sửa được |
|---|---:|---|---|
| **R1.** Chạy `audit_cal_only.py` 2 lần (có/không 6 test scene) để đo tham số dịch bao nhiêu | 2–4 | biết leak có phải vấn đề số | không xoá 28 scene `cal` ở tốc độ test |
| **R2a.** Cal chỉ trên tốc độ train+val (60–120), ngoại suy 50 và 130 | 1–2 | `cal` không còn chứa tốc độ test | ngoại suy ở **hai đầu** dải; vẫn cùng campaign |
| **R2b.** Cắt `cal` = `cal ∩ (train ∪ val)` scene | 2–6 | `cal ∩ test = 0` ở mức scene | còn 28 scene cùng điều kiện tốc độ |
| **R3 = spec này** | 9–14 | cal rời SSPP hoàn toàn, đúng protocol paper | train/test vẫn cùng campaign |
| **R4.** Không làm gì, ghi Limitations | 0 | – | mọi thứ trên |

**Khuyến nghị thứ tự:** R1 (2–4 h) → quyết định → nếu R1 cho thấy tham số dịch lớn thì R3 + ablation
B1/B2; nếu dịch nhỏ (<5 %) thì ghi caveat, chạy 3 arm, và để R3 cho v2 của luận văn.
Nếu chọn R3 thì **W1 làm được ngay** (2–3 h, không phụ thuộc quyết định nào) để mở đường.

---

## Phụ lục A — Protocol P2: train trên STF (như Paper A)

Đề xuất "dùng STF để train, SSPP để test" là **đúng protocol của Paper A**, nhưng nó là một
protocol *khác* chứ không phải bản vá cho leak. Ghi lại đây để quyết định có chủ ý.

### Paper A thật sự làm gì với STF `[PAPER]` (spray2212.txt dòng 778–800, 826–838)

- Train: STF, **chỉ split clear-weather gốc** ⇒ **3.469 point cloud**; chỉ lớp vehicle; detector
  (PV-RCNN, Voxel-RCNN) **train from scratch**; augment chỉ ở frame `ego_velocity > 60 km/h` và chỉ
  highway/suburban; `wfh` sample exponential 0,1–1,2 mm; **3 lần chạy, lấy trung bình**.
- Test: (a) spray test set riêng 1.463 frame, (b) **STF clear-weather test set**.
- Lý do test set dùng "same acquisition vehicle as STF": *"Since this data set is used during
  training, differences regarding sensor makes and mounting positions between the training and newly
  created test set are eliminated."* ⇒ cùng rig là **hệ quả của việc chọn STF làm train**, không
  phải tiêu chuẩn độc lập.
- **STF không có quỹ đạo vật thể** ⇒ paper phải xấp xỉ vận tốc xe xung quanh **từ radar** rồi tích
  phân ngược 5 s. Đây là workaround phải viết lại nếu dùng STF.
- Lưu ý ngược trực giác: **STF adverse-weather KHÔNG dùng để train** — chỉ dùng split clear.

### STF là gì `[DATASET-DOC]` (github princeton-computational-imaging/SeeingThroughFog)

- 12.000 sample ngoài đường thật + 1.500 trong buồng sương; ~100k object; 2D+3D box theo KITTI +
  cột rotation; 4 lớp (PassengerCar, Pedestrian, RidableVehicle, LargeVehicle + fallback).
- Sensor: **Velodyne HDL-64E S3** (`lidar_hdl64_*`) **và Velodyne VLP-32** (`lidar_vlp32_last`,
  `lidar_vlp32_strongest`) — tức cùng họ VLP-32 với SSPP, nên khoảng cách domain **nhỏ hơn lo ngại
  ban đầu**; nhưng mounting/ngày/đường vẫn khác.
- Release: nhiều file zip chia phần, đăng ký tài khoản, kèm cảnh báo server hay downtime;
  README yêu cầu `comment` bớt sensor trong `extract.sh` để tiết kiệm chỗ.

### So sánh hai protocol

| | **P1 (pilot, đang làm) + cal RoadSpray** | **P2 (replicate paper) + cal RoadSpray** |
|---|---|---|
| Train | SSPP 16 scene sạch / 1.124 frame | STF clear 3.469 cloud (3,1×) |
| Test | SSPP 12 scene / 954 frame (50/90/130) | SSPP 12 scene + STF clear test |
| Clean control | nuScenes val 196 frame (**hiện không có trên máy**) | STF clear test (có sẵn trong STF) |
| Cal | RoadSpray `*_static` | RoadSpray `*_static` |
| Train ↔ test cùng rig? | **có** (cùng campaign) | **không** (STF vs SSPP) |
| Compute | fine-tune 2.000 step × 4 arm | **train from scratch** × 3 arm × 3 lần chạy |
| Dữ liệu phải tải | 0 | STF lidar-only (chục GB) + đăng ký |
| Cần viết thêm | adapter RoadSpray | adapter STF + format box KITTI/camera + **radar-velocity workaround** |

### Kết luận phụ lục

1. **P2 không sửa leak.** Leak là `cal → test`; `train ∩ test = 0` đã đúng từ đầu. Đổi train sang
   STF mà vẫn cal trên SSPP thì leak y nguyên.
2. **P2 đổi câu hỏi**: P1 hỏi "augment có giúp trên **cùng domain** không"; P2 hỏi "train trên corpus
   ngoài domain + augment có chuyển sang SSPP không". P2 trả lời được nhiều hơn nhưng đắt hơn
   khoảng một bậc, và absolute FP/frame bị domain gap chi phối ⇒ ngưỡng "B < A ≥ 30 %"
   (`PROJECT.md:129`) khó diễn giải.
3. **Chỗ STF đáng dùng ngay với chi phí nhỏ**: làm **clean control** — vì bộ clean control hiện tại
   (nuScenes val 196 frame) **không có dữ liệu trên máy** (`data/` chỉ có SSPP + roadspray;
   `results/phase-b1-nuscenes-mini/` chỉ là log cũ). Nếu chỉ tải `lidar_vlp32_strongest` +
   `gt_labels` + `labeltool_labels` của **split clear test**, STF làm được vai đó.

---

## Phụ lục B — Ít data, mô hình nào, và hai con số đo được (2026-11-18)

Ba báo cáo đi kèm (cùng thư mục), đọc khi cần chi tiết:

| File | Nội dung | Số quyết định |
|---|---|---|
| `power-design.md` | power analysis trên 36 scene + thiết kế CV | CV theo scene 0,483 (clusters) / 0,761 (noise); CI95 half-width n=12 = **28,4 % / 44,5 %**, n=36 = **15,7 % / 24,1 %** ⇒ effect 30 % **không** kết luận được ở n=12 |
| `detector-choice.md` | đường rẻ nhất sang detector nhẹ | `pointpillars.yaml` có sẵn, 5,27M params; **crop corridor `[0,64]×[−16,16] m` là điều kiện cần**: 0,25–0,5 s/step ⇒ 45–80 phút/run ⇒ 12 run = 10–17 h (full range: 2,5–4,8 h/run, 12 run không fit) |
| `pseudo-boxes.md` (đang hoàn tất) | box 3D dựng từ semantic label cho 171 scene không có box | 3D IoU **p50 0,861 / p5 0,709**, 95,6 % frame ≥ 0,7; BEV IoU p50 0,923 ⇒ thêm **14.832 frame** dùng được cho TRAIN |

**Ba kết luận rút ra:**

1. **Test nhỏ mới là vấn đề, không phải train.** Ở 12 scene, CI95 ≈ effect size đang nhắm (30 %) ⇒ không
   thể tuyên bố "giảm ≥30 %". Sửa bằng 3-fold leave-speed-out (pooled n=36), không cần thêm dữ liệu.
2. **Train thiếu box chứ không thiếu frame.** SSPP gán nhãn điểm cho cả 207 scene; dựng box từ `label==1`
   đạt 3D IoU trung vị 0,861 ⇒ train từ 1.124 frame lên ~13.000 frame (dùng **chỉ cho train**; eval vẫn
   phải là box người). Đánh đổi: mỗi run dài hơn, nên phải chọn giữa "nhiều epoch trên ít frame" và
   "ít epoch trên nhiều frame" trong quota 30 h/tuần.
3. **Không bỏ BEVFusion, nhưng thêm một detector nhẹ làm pilot.** Claim cuối vẫn là BEVFusion LiDAR-only;
   detector nhẹ (`pointpillars.yaml` + crop) là nơi đủ ngân sách để chạy fold × seed và để phát hiện sớm
   generator có tác dụng hay không — trước khi đốt 5–10 h GPU cho BEVFusion.

**Cổng chặn phải làm trước mọi lần train (0 GPU-giờ):** chạy Model 0 trên (a) frame sạch SSPP,
(b) frame sạch + plume tổng hợp, (c) frame spray thật. Nếu (b) không làm tăng FP trong khi (c) làm
tăng mạnh ⇒ plume tổng hợp **vô hình** với detector ⇒ augment không thể dạy được gì, phải sửa generator
trước. Đây là bảo hiểm rẻ nhất chống lại việc đốt toàn bộ ngân sách GPU vào một can thiệp vô hiệu.
