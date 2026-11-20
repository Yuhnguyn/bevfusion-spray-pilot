# RoadSpray có dùng được cho repo này không

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S5.
> Phần còn đúng: Đánh giá độ phù hợp RoadSpray vẫn đúng; 'fit' ở đây đã được thi hành ở D2.

Phân tích 2026-11-18 · nhánh `sspp` @ `064f1c1` · trả lời hai câu: *RoadSpray là bộ calibration hay
bộ spray-road test, và có áp được vào thí nghiệm hiện tại không?*

Nhãn số: `[PAPER]` paper · `[DATASET-DOC]` trang công bố dataset · `[ĐO]` đo trên máy này ·
`[CHỌN]` tự chọn · `[SUY LUẬN]` suy ra, không có câu gốc trong nguồn nào.

---

## Trả lời ngắn

1. **RoadSpray là bộ calibration của Paper A**, công bố chính thức, không phải bộ test. `[DATASET-DOC]`
   Paper A (Linnhoff 2022, arXiv 2212.08558) có footnote `3 https://www.fzd-datasets.de/spray/`
   (dòng 159 của bản text). Trang đó là **trang công bố dataset của chính paper**: phần *Citation*
   ghi *"If you find this data set useful for your research, please consider citing the publication:
   (Currently under review at IEEE) C. Linnhoff, D. Scheuble, M. Bijelic, L. Elster, P. Rosenberger,
   W. Ritter, D. Dai, H. Winner: 'Simulating Road Spray Effects in Automotive Lidar Sensor Models'
   in IEEE Sensors, 2022"* — và nó link thẳng sang tudatalib. Nội dung trang khớp §III-A từng mục:
   2 xe (VW Golf, VW Crafter), 9 tốc độ 50–130 km/h, 3 mức nước, 2 kịch bản (*"1) The ego vehicle is
   positioned stationary next to the watered lane. The object vehicles are driving past the ego…
   2) The ego vehicle is following the object vehicles in different distances…"*), ego là Mercedes
   S-Class. Không có G-Class/CLA/Smart, không có 1.463 frame.
   (Đọc qua Wayback `web.archive.org/web/20221219055215/https://www.fzd-datasets.de/spray/` — snapshot
   3 ngày sau khi arXiv lên; trang sống chặn Cloudflare. Lưu ý: trang **không dùng chữ "calibration"**
   — nhãn đó là kết luận từ hai việc: trang tự nhận là dataset của paper, và mọi hình kết quả của
   model (Fig. 4, 5, 7, 8, 10, 11, 12) đều đo trên campaign này.)

2. **Bộ spray-road test của paper chưa từng được công bố.** `[PAPER + DATASET-DOC]`
   §V-D: 1.463 frame (324+248+170+149+319+253), G-Class / CLA / Smart, đường cao tốc đóng, ego
   80/100/120 km/h, 0–50 m, nhãn do auto-label pipeline. Trang fzd-datasets và tudatalib không có
   bộ này; tudatalib chỉ có 1 item về spray. **Muốn có test đúng protocol paper thì không có đường tải.**

3. **Repo đã có một nửa của RoadSpray, ở dạng tốt hơn: có nhãn.** `[ĐO]`
   `data/SemanticSprayDataset` = 207 recording following + nhãn tay 3 lớp (Paper B §IV khai đúng
   chuỗi này): 108/108 Crafter khớp 1:1, Golf 99/108 dòng following trong xlsx.

4. **Nửa còn lại — 333 recording "passing", ego đỗ yên — repo chưa có, và đây đúng là nửa
   Paper A dùng để calibrate.** `[ĐO]` `meta_data_measurement.xlsx`: 162 Crafter + 171 Golf,
   `ego_velocity = 0` toàn bộ, `distance_to_object = None`, `object_velocity` 50–130 km/h.

5. **Kết luận:** RoadSpray **không** áp được vào thí nghiệm A/B (không nhãn điểm, không box, không
   thêm frame). Nó chỉ có một giá trị thật: làm **nguồn calibration độc lập với tập eval**, đúng
   scenario mà Paper A dùng. Giá trị đó chỉ cần khi chạm lại generator, không nằm trên đường tới
   kết quả A/B. **Đừng đưa vào critical path.**

---

## 1. Release thực sự có gì

`[ĐO]` Item `tudatalib/3537` (DOI `10.48328/tudatalib-930`) có **9 file**, không phải 5 như trang
HTML render:

| File | Byte |
|---|---:|
| `Crafter_dynamic.zip` | 6.127.018.713 |
| `Crafter_static.zip` | 7.924.255.130 |
| `Golf_dynamic.zip` | 6.009.340.245 |
| `Golf_static.zip` | 5.460.144.118 |
| `meta_data_measurement.xlsx` | 26.774 |
| `meta_data_dataset-schema.json` · `meta_data_dataset.json` | 6.349 · 2.517 |
| `Experiment_Setup.zip` · `sprayImage.png` | 8.223.416 · 4.266.192 |

Local `data/roadspray` có 2 zip Crafter **đúng từng byte** với release, cộng `Experiment_Setup.zip`
và `meta_data_dataset.json`. **Thiếu:** `Golf_dynamic.zip` (bản trong `~/.hermes/cache/scratch/roadspray/`
chỉ 1,0 GB / 6,0 GB, `zipfile` báo "not a zip file") và `Golf_static.zip` (không có).

Mỗi zip chỉ chứa `.bag`. Trong bag không có topic nhãn/annotation nào. `[ĐO]`

### Bảng recording — `meta_data_measurement.xlsx` `[ĐO]`

549 dòng, 11 cột (`file_name, object_name, object_velocity, object_direction, ego_velocity,
distance_to_object, amb_tmp, unimog_direction, measurement_itr, itr_after_water, comment`):

| Nhóm | `ego_velocity` | `distance_to_object` | Crafter | Golf | Có trong SSPP? |
|---|---|---:|---:|---:|---|
| following (`*_dynamic`) | 50…130 bằng `object_velocity` | 20 hoặc 30 m | 108 | 108 | **216 → 207** |
| passing (`*_static`) | **0** | `None` | 162 | 171 | **0** |
| tổng | | | 270 | 279 | 207 |

Ba điều đáng chú ý:

- **`static` = ego đỗ yên, xe đối tượng chạy qua** — không phải "xe đứng yên". `[ĐO]`
  `ego_velocity = 0` cả 333 dòng; `/adma/twist` của bag static cho `0.000 m/s`; `distance_to_object
  = None` vì kịch bản passing không có cự ly đặt trước, cự ly biến thiên trong lần chạy qua
  (`[SUY LUẬN]` phần cự ly — không có cột nào ghi).
- **`static` nhiều gấp 1,5 lần `dynamic`**: 18 recording mỗi tốc độ = 6 mức `itr_after_water` ×
  3 lần chạy; following là 12 mỗi tốc độ = 2 cự ly × 6 mức nước, 1 lần. Khớp `[DATASET-DOC]`
  "every individual scenario is recorded 3 times".
- **xlsx không phủ đủ zip**: `Crafter_static.zip` có 163 bag, xlsx có 162 dòng (thiếu đúng bag lớn
  nhất `2021-09-09-13-24-38_0.bag`, 579,7 MB). xlsx có 108 dòng Golf following trong khi SSPP chỉ
  có 99 scene Golf — 9 recording đó **chưa kiểm chứng được** vì `Golf_dynamic.zip` chưa có bản đúng.

---

## 2. Paper A dùng ba bộ, và RoadSpray là bộ nào

| Bộ | Vai trò | Xe / điều kiện | Công bố? |
|---|---|---|---|
| **RoadSpray** = fzd-datasets `/spray` `[DATASET-DOC]` | **calibration + validation** của model plume | Golf, Crafter · đường thử August-Euler · ego Mercedes S-Class · 2 kịch bản · 50–130 km/h | **có** |
| STF (SeeingThroughFog) | **train** detector | Mercedes, weather thật | dataset của người khác |
| Spray test set §V-D `[PAPER]` | **test** detector | G-Class / CLA / Smart · cao tốc đóng · 1.463 frame · auto-label | **không** |

Nguyên văn phần *Statistics* của trang dataset — đây cũng là danh sách tham số bị biến thiên trong
chiến dịch calibration: *"9 different object velocities (50 - 130 km/h) · 3 water levels (Fully
covered, partially covered, moist) · 2 object vehicles (VW Golf, VW Crafter) · 2 distances for
dynamic scenarios · Every individual scenario is recorded 3 times"*. `[DATASET-DOC]`

Hai kịch bản trên trang **chính là** `*_static` và `*_dynamic` trong tên bag: *"1) The ego vehicle is
positioned stationary next to the watered lane. The object vehicles are driving past the ego…"*
= `*_static` (ego đỗ, không có cự ly đặt trước); *"2) The ego vehicle is following the object vehicles
in different distances"* = `*_dynamic` (20 m / 30 m). `[DATASET-DOC + ĐO]`

### Bên trong bộ calibration, paper chia theo **cự ly**, không chia scene `[PAPER]`

- **25 m** dùng để đặt tham số: số cụm + bán kính cụm + `P_det` (Fig. 4, 5, 7; §III-B dòng 358–362,
  dòng 714). `P_det` fit lognormal `µ = −2,3`, `σ = 1,09` (Fig. 7 caption).
- **50 m** là cự ly của target dùng cho attenuation/intensity (Fig. 8: *"the rear of the passing VW
  Crafter is next to the target"*) và cho phần kiểm (Fig. 11, 12).
- Kiểm ở cự ly **không dùng để calibrate**, trên **cùng bộ dữ liệu**: §IV-A *"object distances and
  values, which were not utilized for the model calibration, are used on the same data set"* →
  Fig. 10 (Crafter, 100 km/h, ~40 m), Fig. 11 (50 m), Fig. 12 (phân bố theo range 0–50 m).
- DBSCAN: `eps 0,7°`, `minPts 3`, elevation `0,333°`, toạ độ cầu; đếm trong "spray filter region"
  sau xe rồi chia cho tỉ lệ `chiều dài vùng / quãng đường vật đi trong một scan`. **Không dùng nhãn
  nào** — đây là phép đo label-free theo thiết kế.

### Calibrate trên kịch bản nào — cái gì nói chắc, cái gì là suy luận

Paper §III-A định nghĩa 2 kịch bản (dòng 289–293): (1) ego **đứng yên** làn phải, xe đối tượng chạy
qua làn trái, tia từ cảm biến tới target đi xuyên plume; (2) ego **bám theo** xe đối tượng ở tốc độ
không đổi.

**Nói chắc — có câu gốc:** Fig. 8 *"…when the rear of the **passing** VW Crafter is next to the
target"*; Fig. 10 *"…the simulation of a VW Crafter **passing by the stationary ego vehicle**"*.
Và chữ "following" **chỉ xuất hiện** ở phần định nghĩa kịch bản (dòng 293) + caption Fig. 3b —
không có figure, bảng hay số kết quả nào của kịch bản following. Thêm một khớp chéo: phần
Conclusion nói *"three measurements for every parameter combination"*, đúng bằng `measurement_itr`
= 1…3 của toàn bộ 333 recording static trong xlsx, còn dynamic chỉ có `measurement_itr = 1`. `[PAPER + ĐO]`

**Suy luận — không có câu gốc:** Fig. 4/5/7 ở 25 m và Fig. 11/12 ở 50 m không ghi scenario. Nhưng
lưới following chỉ có **20 m và 30 m** (2 distances, `[DATASET-DOC + ĐO]`), nên 25 m và 50 m chỉ
đo được khi cự ly biến thiên — tức kịch bản passing. `[SUY LUẬN]`
Hệ quả hình học: ego đỗ, xe chạy qua ⇒ cự ly quét liên tục qua 25 m rồi 50 m trong một lần chạy
qua. Cự ly **không** có trong metadata (`distance_to_object` trống cho toàn bộ static) — phải suy
từ quỹ đạo xe đối tượng, không lấy được từ cột nào. `[SUY LUẬN + ĐO]`

⇒ Paper A calibrate model plume **trên dữ liệu của kịch bản passing (ego đỗ)**, ở cự ly biến thiên.
RoadSpray release đúng tập đó: `*_static` = 333 recording. Nửa `*_dynamic` (following) là nửa Paper B
mới dùng để gán nhãn, và cũng là nửa repo này đang dùng.

---

## 3. Repo đang làm khác paper ở đâu

| | Paper A | Repo (`semantic-spray-clusters-by-speed.md`, `plume.py:21-47`) |
|---|---|---|
| Data để chọn tham số cụm | RoadSpray `*_static`, 25 m | SSPP `cal`, scene **following** |
| Toán tử đếm | DBSCAN trên toàn điểm trong spray filter region, chia tỉ lệ | DBSCAN trên `label == 2` |
| Cự ly | cự ly biến thiên trong lần chạy qua: 25 m đặt tham số, 50 m kiểm | chỉ 20 m và 30 m |
| Tách calibration khỏi eval | tách theo cự ly trên cùng bộ dữ liệu; test là **chiến dịch khác** | `cal`/`held-out` 1:1 theo scene, trên **cùng** bộ dữ liệu mà test lấy ra |

Hai hệ quả:

**(a) Con số `75` vs `17,69` không phải bug.** `~75 cụm/frame @130 km/h` là Fig. 11b, đo ở **50 m,
ego đỗ**; `17,69` là SSPP **20–30 m, following, label==2**. Khác scenario, khác cự ly, khác toán tử.
`docs/reference/two-papers-distinction.md` đã cảnh báo không so được; nay biết được *vì sao*.

**(b) Repo có leak cal → test.** `[ĐO]` `scripts/diag_split_structure.py` + `diag_split_options.py`:
6/12 test scene là scene `cal` = **503/954 frame test (52,7 %)**; ở cả 3 tốc độ test (50/90/130) đều
có 2 scene `cal` là test scene. Nghĩa là tham số plume được chọn trên chính ô tốc độ sẽ chấm điểm.
Đây là lỗ hổng protocol thật, nhưng **nó không phải câu hỏi RoadSpray** — xem §5.

---

## 4. RoadSpray cho thêm được gì, và không cho được gì

### Không cho được

| Thứ thiếu | Hệ quả |
|---|---|
| nhãn điểm (`label` 0/1/2) | không tính được FP/frame, recall, SPF proxy, cũng không tính lại được 7 ngưỡng G1–G7 (`semantic-spray-cal-vs-heldout.md`), vốn định nghĩa trên `label == 2` |
| 3D box | detection trên static **không chấm được**; box SSPP là annotation per-frame (UUID mới mỗi frame), bag chỉ có tracker Ibeo/radar — không phải GT |
| frame thừa | `[ĐO]` SSPP giữ **612/613 frame = 99,84 %** (50→50, 71→71, 492→491; 1 frame bị bỏ lẻ, không truncate). "Lấy lại frame" là option chết. |
| modality mới | SSPP **đã ship** `delphi_radar`, `ibeo_front`, `ibeo_rear`, `image_2`; bag thô không thêm gì ngoài 6 topic `/adma/*`, `tf_static`, `camera_info` |
| camera cho fusion | bag chỉ có **1** camera trước; ADR-0005 đòi 6 camera 360° + calib → không mở lại được |

### Cho được — đúng một thứ

**Nguồn calibration độc lập với tập eval, theo đúng protocol Paper A.** Và nó rẻ hơn tưởng:

- `[ĐO]` ingest 163 bag `Crafter_static` ≈ **15–20 phút** (giải nén 16 GB là chi phí chính; decode
  28 ms/frame, ghi 6,4 ms/frame), output **7,4 GB** velodyne-only. Đĩa còn ~27 GiB → vừa.
- `[ĐO]` format khớp: bag `point_step = 32` (`x@0, y@4, z@8, intensity@16 f32, ring@20 u16`);
  intensity và ring **giống hệt từng byte** với SSPP; xyz chỉ cần `p_sspp = R·p_bag + t` với đúng
  `tf_from_reference_point` trong `meta_data_dataset.json` (residual `7e-6 m`). Converter không phải
  đoán gì.
- `[ĐO]` metadata **đã có sẵn** (`meta_data_measurement.xlsx`): tốc độ xe đối tượng 50–130 km/h,
  mức nước `itr_after_water` 1–6, 3 lần chạy lặp. Nghĩa là làm lại Fig. 4 (số cụm theo tốc độ, có
  variance giữa 3 lần) được ngay, không phải suy tốc độ từ tracker.
- `[ĐO]` hình học thuận: ego đứng yên → plume không bị ego-motion làm nhiễu; xe chạy qua ⇒ cự ly
  quét qua 25 m rồi 50 m trong mỗi lần chạy, nên bin được cả hai mốc của paper trên cùng dữ liệu.
  `[SUY LUẬN]` phần cự ly: `distance_to_object` trống cho toàn bộ static, phải suy cự ly từ quỹ đạo
  xe đối tượng chứ không đọc được từ cột metadata nào.

Cái phải làm thêm: `spray/semantic_stats.cluster_angular` đã có recipe DBSCAN của paper (dùng lại
được), nhưng cần (i) lấy quỹ đạo xe đối tượng từ `/front_ibeo_lux/as_tx/objects`, (ii) dựng "spray
filter region" sau xe, (iii) chia theo tỉ lệ chiều dài vùng / quãng đường trong một scan. Ước **8–16 h**
kể cả đối chiếu Fig. 4/5/7. Không có sẵn script nào trong repo làm được việc này.

---

## 5. Các phương án, xếp theo thứ tự nên làm

| # | Phương án | Giờ | Được gì | Kết luận |
|---|---|---:|---|---|
| **R1** | **Chạy `audit_cal_only.py` hai lần**: đúng như hiện tại, và loại 6 scene `cal` nằm trong test (lọc theo `data/sspp_split.json`) | 2–4 | biết leak là vấn đề **số** hay chỉ là câu chữ; quyết định có phải tái cấu trúc split | **làm trước**, không cần RoadSpray |
| **R2** | Nếu R1 cho thấy lệch lớn: cắt `cal` về `cal ∩ (train ∪ val)` (hoặc test = `held-out` only) | 2–6 | generator chưa từng thấy scene test | rẻ hơn RoadSpray nhiều; đánh đổi: mất hiệu chuẩn đúng tại 50 và 130 km/h, hoặc nới CI test ~√2 |
| **R3** | Ingest `*_static` + dựng lại Fig. 4/5/7 theo §III-B (label-free, 25 m cal / 50 m kiểm) | 8–16 | nguồn calibration **độc lập hoàn toàn** với SSPP; kiểm chứng độc lập lỗi "ngân sách cụm 4×" (`plume-root-cause.md:41-62`, đang mở); trả lời được "17,69 có đúng không" | **option duy nhất có giá trị thật** — nhưng chỉ khi chạm lại generator, không phải bây giờ |
| ✗ | Static làm "held-out test" | 16–24 | — | không chấm được gì: không nhãn, không box. Muốn có phải tự gán nhãn 333 recording = đúng công sức Paper B đã bỏ ra |
| ✗ | Lấy Fig. 11b `~75 cụm/frame` làm target generator | — | — | calibrate sang **scenario khác** (50 m, ego đỗ) trong khi detector chạy following 20–30 m. Đây là cái bẫy dễ sập nhất |
| ✗ | Coi static là "frame sạch / không spray" | — | — | static **có** spray: xe đối tượng chạy 50–130 km/h trên đường ướt |
| ✗ | RoadSpray làm test set | — | — | không nhãn, không box, và cùng một chiến dịch đo với train → không phải held-out |

**Điều kiện đổi ý (khi nào R3 đáng làm):** bạn chạm lại generator vì lỗi 4×, hoặc cần một chương
"port có đúng paper không" cho luận văn, hoặc R1 cho thấy leak làm tham số dịch > 5–10 %. Ngoài ba
điều đó, 8–16 h đó nên dành cho 3 bước còn thiếu của plan (`sspp_arms.py`, `sspp_eval.py`) — hiện
**chưa có file nào**, trong khi đó mới là thứ đứng giữa repo và kết quả đầu tiên.

---

## 6. Tài liệu trong repo cần sửa

| File | Chỗ sai | Đúng |
|---|---|---|
| `docs/reference/two-papers-distinction.md:43-50` | "RoadSpray (tudatalib-930) là bộ **thứ tư** — không nằm trong Paper A"; "RoadSpray ≈ calibration set… không phải cùng file" | RoadSpray **là** bản phát hành của đúng chiến dịch đo §III-A: fzd-datasets/spray là footnote `3` của chính paper, trang đó tự ghi "consider citing the publication … Simulating Road Spray Effects in Automotive Lidar Sensor Models", rồi link sang tudatalib/3537. Không phải "bộ thứ tư". |
| `docs/reference/two-papers-distinction.md:49-50, 71` | RoadSpray có 3 subset, `Crafter_static` là "extra"/"bản công bố đầy đủ hơn" | release có **4** subset (`Golf_static` 5,46 GB bị bỏ sót); `*_static` **không phải extra** — nó là kịch bản 1 của campaign, tức nửa calibration của paper |
| `docs/reference/two-papers-distinction.md:126` | "`~75 cụm/frame @130 km/h` — Fig. 11b" + dòng 33 gán Fig. 11 cho "100 km/h" | 130 km/h đúng là Fig. 11b; **100 km/h là Fig. 10** (Crafter chạy qua ego đỗ, ~40 m). Fig. 11 không có mốc 100 km/h riêng |
| `docs/reference/two-papers-distinction.md:74` | "SemanticSpray = RoadSpray + nhãn tay → 16.565 dynamic scene" | thêm: SSPP ship **207** scene = **207/216** recording following (thiếu 9 Golf), và **0** recording static |
| `README.md:49`, `HANDOFF.md:63` | dataset 31 GB | `[ĐO]` 16 GB (`du`), 17.419 frame / 207 scene |
| `data/roadspray` | thiếu `Golf_*.zip` | `Golf_dynamic.zip` trong cache bị cắt (1,0/6,0 GB); `Golf_static.zip` chưa tải |

---

## 7. Tái lập

```bash
# 549 dòng metadata (xlsx tải qua REST vì trang /bitstreams/<uuid>/download bị Anubis chặn)
curl -sS "https://tudatalib.ulb.tu-darmstadt.de/server/api/core/bitstreams/<uuid>/content" -o meta_data_measurement.xlsx
# frame count bag ↔ SSPP, ego velocity từ /adma/twist, format điểm: xem .scratch/roadspray-fit/ingestion.md
# leak cal→test:
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python scripts/diag_split_structure.py
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python scripts/diag_split_options.py
```

Số đo gốc của đợt phân tích này: `.scratch/roadspray-fit/` — `ingestion.md` (bag/format/cost),
`repo-fit.md` (audit phía repo), `tmp/xlsx_recs.json` (549 dòng đã parse).
