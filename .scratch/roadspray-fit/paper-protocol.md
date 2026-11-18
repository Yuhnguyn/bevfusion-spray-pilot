# RoadSpray fit protocol — Paper archaeology (task-1)

Người làm: `paper-archaeologist`; ngày 2026-11-18. Nguồn local: `~/.hermes/cache/scratch/spray2212.txt` (Paper A, arXiv 2212.08558v1),
`ssp2305.txt` (Paper B, arXiv 2305.16129v3), PDFs cùng thư mục; repo docs. Nguồn web: tudatalib (DOI 10.48328/tudatalib-930),
fzd-datasets.de qua Wayback, SemanticSpray project page/GitHub.

Nhãn: `[PAPER-A]` / `[PAPER-B]` / `[DATASET-DOC]` (trang dataset chính thức) / `[ĐO]` (đo trên file đã tải) / `[SUY LUẬN]`.
Mọi quote verbatim; số dòng của Paper A/B là dòng trong file text local.

---

## 0. Verdict (câu trả lời thẳng)

**RoadSpray LÀ bộ calibration/validation của Paper A, KHÔNG phải spray test set.** RoadSpray = chiến dịch đo trên
August-Euler-Airfield (VW Golf + VW Crafter, 50–130 km/h, 3 mức nước, 2 kịch bản) — đúng chiến dịch được mô tả ở §III-A
và được dùng để calibrate model ở §III-B. Paper A **không** cite tudatalib và **không** dùng chữ “RoadSpray”
(`[PAPER-A]` grep = 0 lần), nhưng footnote `3` của paper chính là trang phát hành RoadSpray, và trang đó dẫn ngược lại paper.

Bộ **1463-frame spray test set** (G-Class/CLA/Smart, closed highway, §V-D) là bộ **thứ ba, riêng biệt, KHÔNG được công bố**
— không có trên fzd-datasets, không có trên tudatalib, không có URL nào trong paper.

Mạnh hơn cho repo: **mọi hình calibration/validation có gắn kịch bản trong Paper A đều là “ego đỗ + xe chạy qua” (passing)**.
Kịch bản ego following (`*_dynamic`) chỉ xuất hiện ở định nghĩa §III-A + caption Fig. 3b, **không** xuất hiện trong bất kỳ
con số/hình kết quả nào của paper.

---

## 1. Paper A dùng dataset nào cho việc gì

| Vai trò | Dataset | Bằng chứng verbatim |
|---|---|---|
| Calibration | test track August-Euler-Airfield, Golf/Crafter | §III-A: *“To calibrate the model, extensive experiments are conducted to capture sufficient amount of reference data.”* (§III-A, L260–261); *“tests are conducted on an isolated test track with a watering vehicle preparing the test track equally for each iteration. The scene is watered by a Unimog … the test vehicle, equipped with a Velodyne VLP32 on top of its roof”* (L263–268); Fig. 3 caption: *“Experimental setup on August-Euler-Airfield test track in Darmstadt, Germany”* (L323) |
| Training | STF (SeeingThroughFog) | §III-C: *“The training is performed on the SeeingThroughFog [26] (STF) data set. … Hence, 3469 clear weather point clouds are available for training. However, the spray augmentation is only applied to samples where the ego-velocity exceeds 60 km/h. Furthermore, only highway and suburban scenarios are considered for augmentation.”* (L778–785) |
| Test | spray test set tự thu, 1463 frame | §V-D: *“In total, 1463 frames are collected and labeled.”* (L831–832); abstract: *“…a diverse real world spray test set consisting of 1463 frames”* (L117–119) |

Paper A tự nói nó dùng **hai** bộ đo riêng: §II: *“our method investigates the introduced disturbance patterns of spray
plumes in detail through two specifically captured data sets … analyzed and modeled by clustering of the point cloud in a
first data set with isolated spray effects and the overall model validation is performed using object detection algorithms
on a second data set.”* (L175–181).

Release: intro: *“The simulation model¹, the augmentation² as well as the recorded data set³ are all open-source and publicly
available.”* (L120–121), với footnote `3 https://www.fzd-datasets.de/spray/` (L159). [Đối chiếu §4: URL này = trang RoadSpray.]

---

## 2. “Calibration” trong Paper A nghĩa là gì (params, đo từ đâu, cự ly/tốc độ)

Parameter cần fit (§III-B, L334–340): *“• the generation and distribution of clusters • the update of cluster locations and
their movement over time • the generation of spray detections in the lidar • the attenuation of other objects behind spray
plumes.”* Cụ thể:

- **Số cluster/frame** — DBSCAN trên detections, **object distance 25 m**: *“An object distance of 25 m from the sensor is
  chosen, since here distinct and stable clusters are observed with high resolution in the sensor.”* (L361–363); *“Over
  84 % of the detections in Fig. 1 are sorted into clusters”* (L353–355). Fig. 4 = số cluster đo theo speed 50–130,
  3 water levels; *“The dashed lines represent linear approximations of the mean used for model calibration.”* (Fig. 4).
- **DBSCAN operator** — *“applied to the point cloud in spherical coordinates … three points is defined as the minimum number
  of points that can form a cluster. In the central elevation field of view, the Velodyne VLP32 has an elevation angle
  discretization of 0.333°. To ensure possible clustering in vertical direction, the search neighborhood of DBSCAN is set to
  0.7° to cover at least two scan lines”* (L365–374) → `eps=0.7°`, `minPts=3`, mặt phẳng `(azimuth,elevation)`.
- **Cluster radius** — lognormal, Fig. 5: *“The parameters of the distribution are µ = −1.2 and σ = 0.8 as an example.”* (L524–525).
- **Time constant T (dissolve)** — *“the time constant T is defined as the time required to reduce the detection count to 36 %
  of the maximum”*, fit từ detections trong constant-volume filter (L548–552); *“The watering levels are parameterized in the
  simulation with 0.5 mm, 0.75 mm and 1.0 mm for moist, partially covered, and fully covered”* (L555–557); Fig. 6.
- **Cluster velocity/drag** — *“yields a factor of C = −0.15 m⁻¹ … has to be re-calibrated for sensors with different scanning
  frequencies. The here applied step size according to the sensors frequency is ∆t = 100 ms.”* (L634–644).
- **Detection probability** — lognormal, Fig. 7: *“µ = −2.3 and σ = 1.09”*; đo *“with a vehicle distance of 25 m”* (L713–714).
- **Intensity** — *“Over 80 % of spray detections from the VLP32 have an intensity value of 0 and 16 % are 1. Therefore, the
  final intensity value of the simulated spray detections are set to 0.”*; variation normal mean 0.5, std 0.05 (L724–730).
- **Extinction/attenuation** — *“yields a mean extinction coefficient of 0.02 m⁻¹. This value was found iteratively as an
  optimization to match the decrease in intensity on the simulated target to the measurements shown in Fig. 8.”* (L739–742);
  Fig. 8 = *“intensities … recorded when the rear of the passing VW Crafter is next to the target”* (L707–711).
- Golf dùng chung radius/Pdet/intensity với Crafter; khác *“number of clusters and the dissolve time constant”* (L755–761).

**Cự ly/speed**: campaign 50–130 km/h, step 10 km/h, Golf + Crafter, 3 water classes (§III-A, L294–313; Fig. 3–8, 50–130 km/h).
**Calibration↔validation tách theo distance** (và “values”): §IV-A *“To evaluate the model, object distances and values, which
were not utilized for the model calibration, are used on the same data set.”* (L1044–1046). Calibration dùng 25 m (Fig. 4/5/7);
validation dùng ~40–50 m (Fig. 10 @~40 m; Fig. 11/12 @50 m). Lưu ý: attenuation được fit *trên* measurement ở target 50 m
(Fig. 8), nên không phải “mọi thứ calibrate ở 25 m”; nhưng mọi hình đều thuộc kịch bản passing (§3).

---

## 3. Toàn bộ hình calibration/validation thuộc kịch bản passing (ego đỗ)

Paper A định nghĩa đúng **hai** kịch bản (§III-A, L289–293): *“In the first scenario, the ego vehicle is stationary on the right
lane and an object vehicle is passing on the left lane. The direct line of sight from the sensor to the reference target is
going through the spray plume. In the second scenario, the ego vehicle is following the object vehicle with constant speed.”*
Fig. 3b: *“(b) Scenario sketches for passing (left) and following (right)”* (L321). Reference target: *“a reference lidar and radar
target are placed next to the watered road in 50 m distance”* (L285–286).

- Fig. 8: **passing** — caption L707–711 (quote ở §2).
- Fig. 10: **passing, ego stationary** — *“the simulation of a VW Crafter passing by the stationary ego vehicle. The VW Crafter is
  driving at a speed of 100 km/h and is located in this scan at around 40 m.”* (L1037–1041).
- Fig. 11/12: đo **@50 m** (*“from a Crafter at 50 m distance”* L1186–1187; *“with different speeds at 50 m distance”* L1249–1250).
  `[SUY LUẬN]`: following scenario chỉ có 20 m và 30 m (`[ĐO]` xlsx/SSPP metadata, §5), nên 50 m không thể là following → passing.
- Fig. 4/5/7: đo ở **25 m** (quote §2); `[SUY LUẬN]` mạnh: 25 m không phải 20/30 m của following → frame 25 m lấy từ lúc xe chạy qua
  ego đỗ (distance quét liên tục 0–50 m). Paper **không** ghi verbatim “hình này đo ở passing” cho Fig. 4/5/7 — chỉ suy ra từ cự ly.
- Con số “3 measurements per parameter combination” (Conclusion, L1564–1567: *“…taking three measurements for every parameter
  combination”*) khớp `measurement_itr = 1..3` của static subset (`[ĐO]`, §5); dynamic subset chỉ có `measurement_itr = 1`.
  Đây là bằng chứng độc lập rằng **calibration dùng static subset**, không dùng dynamic.

**Following scenario trong Paper A**: chỉ có ở §III-A (định nghĩa campaign) và Fig. 3b (sketch). Không có figure, bảng, hay con số
kết quả nào được gán cho following; các đoạn Fig. 4–12 chỉ nói “Crafter/Golf … measurements” với cự ly 25/50 m. `[SUY LUẬN]`:
following được thu (và phát hành trong `*_dynamic`) nhưng **không được dùng** trong calibration/validation của paper.

---

## 4. Spray test set 1463 frame: có release không? → KHÔNG

Chi tiết §V-D: 1463 frame (*“In total, 1463 frames are collected and labeled”*); campaign riêng trên **closed highway test track**,
*“The same acquisition vehicle as for the STF data set is used”* (L833–838); 3 xe *“a Mercedes-Benz G-Class … a Mercedes-Benz
CLA-Class … and a Smart”* (L844–847); ego speed hằng 80/100/120 km/h; 2 road condition wet/watered; *“the followed vehicles are
close to the ego vehicle in distances from 0-50 m”* (L856–857). Tab. I: 6 tổ hợp, frames 324+248+170+149+319+253 = **1463**
`[ĐO]` (số học). Label bằng auto-label pipeline (lidar detector + AB3DMOT + radar, *“after the label generation, each scenario is
assessed by a human annotator and it is found that no manual corrections had to be performed”* L1009–1011); test set *“labeled up
to 50 m”* (L819–821). Không có câu nào nói bộ này được phát hành.

Audit release (không tải lại paper):
1. `[DATASET-DOC]` Trang `https://www.fzd-datasets.de/spray/` (footnote 3) qua Wayback **2022-12-19** (`http://web.archive.org/web/20221219055215/https://www.fzd-datasets.de/spray/`),
   **2024-03-02** (`https://web.archive.org/web/20240302042753/https://www.fzd-datasets.de/spray/`), **2025-09-18**
   (`http://web.archive.org/web/20250918100432/https://www.fzd-datasets.de/spray/`): cả ba chỉ mô tả chiến dịch test-track
   (Golf/Crafter, Unimog, 3 water levels, 2 scenarios, 9 speeds, Mercedes S-Class) và link *“Download Dataset from TUdatalib”*.
   **Không** có G-Class/CLA/Smart, không 1463 frame, không closed highway, không labels.
2. `[DATASET-DOC]` tudatalib item `https://tudatalib.ulb.tu-darmstadt.de/items/2894756f-1316-4a4e-a25e-92db5f0d5b8e` (full page)
   có đúng 9 file: `Crafter_dynamic.zip` 5.71 GB, `Crafter_static.zip` 7.38 GB, `Golf_dynamic.zip` 5.6 GB, `Golf_static.zip` 5.09 GB,
   `Experiment_Setup.zip` 7.84 MB, `meta_data_dataset.json` 2.46 KB, `meta_data_dataset-schema.json` 6.2 KB,
   `meta_data_measurement.xlsx` 26.15 KB, `sprayImage.png` 4.07 MB. **Không có** test set.
3. `[DATASET-DOC]` tudatalib REST `https://tudatalib.ulb.tu-darmstadt.de/server/api/discover/search/objects?query=%22Road%20Spray%22`
   → `totalElements: 1` (chỉ item trên). Trang fzd overview (`web.archive.org/web/20250119104624/https://www.fzd-datasets.de/overview/`)
   chỉ liệt kê 3 dataset: Tire Spray, adverse weather, RCS.
4. `[SUY LUẬN]` Test set dùng acquisition vehicle của STF (dữ liệu Mercedes nội bộ) + auto-label pipeline; không có dấu hiệu phát hành.
   **CHƯA XÁC MINH**: có thể tồn tại bản nội bộ/benchmark khác (Walz et al. ITSC 2021, ref [10]) nhưng **không có URL nào** trong paper
   hay trang dataset; coi như không tải được.

---

## 5. RoadSpray release: nội dung thật, static vs dynamic, metadata

`[DATASET-DOC]` Item: **“Road Spray in Lidar and Radar Data for Individual Moving Objects”**, Linnhoff/Elster/Rosenberger/Winner,
`dc.date.created = 2022-04`, `dc.date.issued = 2022-08-04`, license **CC BY 4.0**, DOI `10.48328/tudatalib-930`,
handle `tudatalib/3537`. Description: *“This data set is designed to systematically analyze the influence of road spray on lidar
and radar sensors. It consists of sensor measurements of two vehicle classes driving over asphalt with three water levels to
differentiate multiple influence factors.”*

`[DATASET-DOC]` Trang fzd (Wayback 2022-12-19; nội dung giữ nguyên 2024/2025, chỉ đổi citation từ “IEEE Sensors 2022” sang
“IEEE IV 2024”): **“Road Spray in Radar and Lidar Data”** — *“One lane is watered by a distribution system on a Unimog. The water film
dissipates over time enabling three water film levels: Fully covered, partially covered, moist. Reference targets for lidar and
radar are placed on the other side of the lane. There are two different kinds of logical scenarios: 1) The ego vehicle is
positioned stationary next to the watered lane. The object vehicles are driving past the ego with different velocities and
different water film heights. 2) The ego vehicle is following the object vehicles in different distances with different
velocities.”* Statistics: *“9 different object velocities (50 - 130 km/h)”, “3 water levels (Fully covered, partially covered,
moist)”, “2 object vehicles (VW Golf, VW Crafter)”, “2 distances for dynamic scenarios”, “Every individual scenario is recorded 3
times.”* Sensors: *“The ego vehicle is a Mercedes S-Class equipped with … 1 Velodyne VLP32C Lidar … 1 Ibeo LUX 2010 Lidar … 1 Aptiv
ESR 2.5 Radar … 1 Genesys ADMA G-Pro+ RTK-GNSS & IMU in each vehicle.”* Citation section dẫn đúng paper *“Simulating Road Spray Effects
in Automotive Lidar Sensor Models”*.

**Chuỗi chứng minh “RoadSpray = bộ calibration của Paper A”**: Paper A footnote `3` = fzd page (§1) → fzd page = trang mô tả dataset
+ link *“Download Dataset from TUdatalib”* → tudatalib/3537 (RoadSpray) → trang tudatalib cùng mô tả + fzd page cite đúng paper.
**Lưu ý trung thực**: trang fzd **không** dùng chữ “calibration” và **không** nói “this is the calibration data set”; nó chỉ mô tả
chiến dịch đo và dẫn paper. Vì vậy câu chặt nhất có nguồn là: *“RoadSpray là bản phát hành của chiến dịch đo được mô tả ở §III-A
(tức chiến dịch calibration/validation của Paper A), không phải bộ test”*. Còn “bộ calibration chính thức” là cách gọi hợp lý nhưng
không phải câu trích được nguyên văn từ trang.

**static vs dynamic** (`[DATASET-DOC]` + `[ĐO]` từ `meta_data_measurement.xlsx`, xem dưới):
- `Crafter_static`/`Golf_static` = **scenario 1: ego ĐỖ, xe đối tượng chạy qua** (không phải xe đứng yên — tên “static” nói về ego).
- `Crafter_dynamic`/`Golf_dynamic` = **scenario 2: ego bám theo xe đối tượng ở khoảng cách cố định 20 m hoặc 30 m**.

**xlsx metadata (operational, quan trọng cho ingestion)**. File `meta_data_measurement.xlsx` 26.15 KB, 1 sheet, **549 dòng dữ liệu**
+ header, mỗi dòng = 1 `.bag`. Header verbatim: `file_name, object_name, object_velocity, object_direction, ego_velocity,
distance_to_object, amb_tmp, unimog_direction, measurement_itr, itr_after_water, comment` (dạng text của file; `[ĐO]` trích xuất
qua r.jina.ai vì tudatalib chặn tải binary — xem “CHƯA XÁC MINH”). `meta_data_dataset-schema.json` **chỉ** schema cho
`sensors` + `objects` của `meta_data_dataset.json`, **không** mô tả bảng measurement.
Cấu trúc dòng `[ĐO]`:
- static: `ego_velocity = 0`; `distance_to_object` **để trống**; `measurement_itr = 1..3`; `itr_after_water = 1..6`; `amb_tmp` 18–27;
  ví dụ `2021-09-09-08-56-39_0.bag Crafter 50 1 0 18 1 1 1` → ego đỗ, 50 km/h, amb 18, itr 1, water 1.
- dynamic: `ego_velocity = object_velocity = 50..130`; `distance_to_object ∈ {20, 30}`; `measurement_itr = 1`; `itr_after_water = 1..6`;
  ví dụ `2021-09-08-14-36-56_0.bag Crafter 50 1 50 20 26 1 1` → theo sau @20 m, 50 km/h, water 1.
- Số dòng theo block `[ĐO]`: Crafter_static 162 (9 speed × 3 measurement_itr × 6 water), Golf_dynamic 108 (9 × 2 distance × 6 water),
  Crafter_dynamic 108 (9 × 2 × 6), Golf_static 171 (162 + 9 dòng đo thêm; có `measurement_itr=4`, `itr_after_water=7/8`).
- Đối chiếu zip đã tải `[ĐO]`: `Crafter_static.zip` = **163** bag (xlsx 162 → lệch 1, **CHƯA XÁC MINH** lý do);
  `Crafter_dynamic.zip` = **108** bag (khớp). Golf_dynamic/Golf_static chưa tải đủ để đếm; repo docs `[ĐO]` ghi SemanticSpray release
  có 207 scene = Crafter_dynamic 108 + Golf_dynamic 99 → bản release Golf_dynamic **99** bag, trong khi xlsx có 108 dòng
  (**CHƯA XÁC MINH**: 9 recording bị loại khi làm SemanticSpray hay chưa có trong zip gốc).

Hệ quả: xlsx cho biết **speed + static/dynamic + (dynamic: distance) + water iteration** cho từng bag **mà không cần decode ADMA**.
Nhưng static **không có** distance per-scene (cột trống) — muốn biết cự ly lúc xe chạy qua phải đo từ bag; nó chỉ cho tốc độ + thứ tự nước.

---

## 6. Paper B: SemanticSpray lấy từ RoadSpray thế nào

§IV: *“The data is based on the recently released RoadSpray [3] dataset, which performs large-scale testing of the effect of
vehicle spray on LiDAR, camera, and radar sensors. The RoadSpray dataset provides unlabeled scenes of vehicles driving on wet a
surface at different speeds in highway-like scenarios. … To create the SemanticSpray dataset, we manually label each point in a
LiDAR scan as one of three categories: background, vehicle, and spray.”* (L605–611); *“In total, we provide semantic labels for
16565 dynamic scenes, with approximately 6.23 · 10⁶ background, 4.84 · 10⁴ vehicle and 2.15 · 10⁴ spray points.”* (L615–617).
§V-A: *“We use 7898 scans for training and 8667 for testing.”* (L645–646) → 7898+8667 = 16565 `[ĐO]` số học.

Subset: paper chỉ nói **dynamic scenes**; project page `https://semantic-spray-dataset.github.io/` liệt kê cây dữ liệu chỉ có
`Crafter_dynamic` + `Golf_dynamic`; GitHub README cũng vậy. **Không** có câu verbatim “we excluded the static subset” —
`[SUY LUẬN]`: static bị loại (không có label/không nằm trong 16565). Ref [3] của Paper B = đúng item tudatalib ở §5 (L1370–1372).
Fig. 1 Paper B: *“a scene from the RoadSpray [3] dataset, where both a leading vehicle and the ego vehicle are driving on a wet
surface, generating trailing spray.”* (L36–37) → đúng kịch bản dynamic/following.
`[ĐO]` repo: SemanticSpray local 207 scene (Crafter_dynamic 108 + Golf_dynamic 99), 17.419 scan; mỗi scene có `metadata.txt` cùng
schema 11 cột với RoadSpray xlsx, ví dụ `2021-09-08-14-47-19_0.bag,Crafter,50,-1,50,30.0,26.0,nan,1,6,nan`.

---

## 7. Chỗ `docs/reference/two-papers-distinction.md` SAI / quá mạnh

1. Dòng 43–50: *“RoadSpray (tudatalib-930) là bộ thứ tư — không nằm trong Paper A”* → **SAI về bản chất**: đây là bản phát hành của
   chiến dịch calibration/validation ở §III-A (footnote 3). Đúng phần literal “Paper A không cite tudatalib/không dùng chữ RoadSpray”
   nhưng kết luận “không nằm trong Paper A” là misleading.
2. Dòng 49–50: liệt kê `Crafter_dynamic, Crafter_static, Golf_dynamic` → **thiếu `Golf_static`** (5.09 GB, có trên full item page).
3. Dòng 77–78: *“RoadSpray ≈ calibration set … bản công bố đầy đủ hơn (có cả static)”* → **SAI**: “static” là scenario 1 của chính
   chiến dịch calibration, không phải phần bổ sung; và quan hệ là “cùng chiến dịch/cùng file gốc”, không chỉ “≈”.
4. Dòng 41: *“Fig. 11 thuộc calibration set — VW Crafter @50 m, **100 km/h**”* → **SAI số**: 100 km/h là ví dụ của **Fig. 10**
   (passing, ~40 m, L1037–1041). Fig. 11 = so sánh simulated vs measured @50 m trên toàn dải 50–130 km/h (cả fully covered lẫn moist),
   không gắn với 100 km/h. Nên viết: “Fig. 11 = phần validation của calibration data set, @50 m, kịch bản passing”.
5. Dòng 33 (bảng): “Calibration set … 25 m (Fig. 4), 50 m (Fig. 11)” — đúng số nhưng nên ghi rõ 25 m = fitting, 50 m = validation
   (theo §IV-A “distances … not utilized for the model calibration”).
6. Dòng 33: “không nhãn — DBSCAN thủ công” → DBSCAN là tự động (paper §III-B), “thủ công” gây hiểu nhầm; ý đúng là “không có
   semantic labels, phải tự cluster”.
7. Dòng 127 (`~75 cụm/frame @130 km/h` = Fig. 11b) — **CHƯA XÁC MINH**: con số không có trong text paper (chỉ nằm trong figure),
   và Fig. 11b là simulated-vs-measured @50 m, không phải calibration target; không nên dùng làm số “chuẩn”.
8. Các mục đúng, giữ nguyên: 3 bộ dữ liệu khác nhau (calibration/STF/test); 1463 frame thuộc spray test set §V-D; 16.565 dynamic
   scene của Paper B; mô tả wet-ground lấy từ Hahner [9]; cảnh báo không so sánh Fig. 11b với bảng SemanticSpray.

---

## 8. Hệ quả cho repo (ngắn)

- **Dùng được RoadSpray để tái lập thống kê calibration của Paper A** (DBSCAN `eps=0.7°`, `minPts=3`, đếm cluster/frame theo speed
  & water level) — đặc biệt `*_static` chính là kịch bản paper dùng cho Fig. 4/5/7; đây là cách kiểm tra port `spray/plume.py` có
  trung thành với paper hay không. `*_dynamic` (following 20/30 m) khớp kịch bản detector của repo nhưng **paper không calibrate ở đó**.
- **Không dùng RoadSpray làm detector test set**: không nhãn; bộ test 1463 frame không có.
- **SemanticSpray (eval hiện tại của repo) = dynamic/following 20/30 m**, còn Fig. 11 của Paper A = passing @50 m → khác cả
  dataset, scenario, distance, cách đếm; không thể “khớp Fig. 11b” (repo docs đã cảnh báo distance, cần thêm **scenario**).
- Ingest RoadSpray: dùng `meta_data_measurement.xlsx` để lấy speed/scenario/water; **static không có distance per-scene**.

---

## 9. Nguồn

- Paper A: `https://arxiv.org/abs/2212.08558` (v1 2022-12-16, không có v2), local `~/.hermes/cache/scratch/spray2212.txt`.
- Paper B: `https://arxiv.org/abs/2305.16129v3`, local `ssp2305.txt`.
- RoadSpray: `https://tudatalib.ulb.tu-darmstadt.de/items/2894756f-1316-4a4e-a25e-92db5f0d5b8e` (full: `/full`), handle `tudatalib/3537`,
  DOI `10.48328/tudatalib-930`, REST search object URL ở §4.
- fzd-datasets: Wayback 2022-12-19 / 2024-03-02 / 2025-09-18 (URL ở §4); overview 2025-01-19.
- SemanticSpray: `https://semantic-spray-dataset.github.io/`, `https://github.com/aldipiroli/semantic_spray_dataset` (README),
  download `https://oparu.uni-ulm.de/xmlui/handle/123456789/48891`.
- Local RoadSpray pieces: `data/roadspray/{Crafter_static.zip 163 bag, Crafter_dynamic.zip 108 bag, Experiment_Setup.zip}` `[ĐO]`.

**CHƯA XÁC MINH còn lại**: (a) số dòng xlsx đọc qua text-extraction (không tải được binary vì tudatalib dùng Anubis/WAF; `web_fetch`
chỉ trả text, binary bị chặn content-type); (b) lý do lệch Crafter_static 163 vs 162 và Golf_dynamic 108 vs 99; (c) Golf_static chưa đếm;
(d) không chứng minh được tuyệt đối test set không tồn tại ở nơi khác — chỉ chứng minh không có trong kênh phát hành chính thức.
