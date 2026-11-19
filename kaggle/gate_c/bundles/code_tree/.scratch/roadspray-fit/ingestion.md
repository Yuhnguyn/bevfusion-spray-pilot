# Ingestion spike — RoadSpray raw bags: đo được gì, dùng được không

Phạm vi: chỉ đọc `data/roadspray/*.zip` (stream-extract **một** bag mỗi lần), đọc `data/SemanticSprayDataset`
(read-only), tải 2 file metadata nhỏ. Không giải nén cả zip, không sửa file tracked. Tmp: `.scratch/roadspray-fit/tmp/`.

Cách chạy python (bắt buộc): `CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python`.
Script dùng trong spike: `tmp/probe.py`, `tmp/probe_full.py`, `tmp/probe_count.py`, `tmp/convert_test.py`,
`tmp/compare_exact.py`, `tmp/inspect_diff.py`, `tmp/fit_tf.py` (mỗi script tự extract 1 bag rồi `unlink`).

## 0. Sự thật về bản release (quan trọng, khác giả định ban đầu)

Item = **tudatalib/3537** (DOI `doi.org/10.48328/tudatalib-930`). Trang HTML chỉ render 5 file, **nhưng release có 9**.
Danh sách chuẩn lấy qua REST (`curl`):

```
UUID=2894756f-1316-4a4e-a25e-92db5f0d5b8e
curl -sS ".../server/api/core/items/$UUID/bundles"            # -> ORIGINAL bundle
curl -sS ".../server/api/core/bundles/6c038db5-a833-43c2-909a-58e8f5bffca2/bitstreams?size=100"
```

| file | bytes |
|---|---|
| Crafter_dynamic.zip | 6 127 018 713 |
| Crafter_static.zip | 7 924 255 130 |
| Golf_dynamic.zip | 6 009 340 245 |
| Golf_static.zip | 5 460 144 118 |
| meta_data_dataset.json | 2 517 |
| meta_data_dataset-schema.json | 6 349 |
| **meta_data_measurement.xlsx** | **26 774** |
| Experiment_Setup.zip | 8 223 416 |
| sprayImage.png | 4 266 192 |

URL tải: `https://tudatalib.ulb.tu-darmstadt.de/server/api/core/bitstreams/<bitstream-uuid>/content`
(đường `/bitstreams/<uuid>/download` bị chặn bởi Anubis proof-of-work page; REST `.../content` trả file thật —
đã verify bằng `curl -o file -w '%{http_code} %{content_type}'` → `200 application/vnd.openxmlformats-...`,
26 774 B, `file` = "Microsoft Excel 2007+").

Local: `data/roadspray` **đủ** 2 zip Crafter (đúng byte-size với release). `~/.hermes/cache/scratch/roadspray/
Golf_dynamic.zip` chỉ 1.0 GB / 6.0 GB và `zipfile` báo *"File is not a zip file"* → **bản tải dở, hỏng**.
`Golf_static.zip` không có ở local.

## 1. Topics & message types — giống hệt nhau giữa dynamic và static

Lệnh: `python tmp/probe.py data/roadspray/Crafter_dynamic.zip Crafter_dynamic/2021-09-08-16-06-27_0.bag --decode`
và biến thể cho `Crafter_static/2021-09-09-10-15-04_0.bag`. Cả hai bag có **đúng 20 topic, cùng tên, cùng type**;
không có topic nào chỉ xuất hiện ở một bên. `/velodyne_points` = `sensor_msgs/msg/PointCloud2` ở **cả hai**.

```
/velodyne_points                        sensor_msgs/PointCloud2          50 (dyn) / 65 (static)
/adma/twist|pose|imu|status|delta|nav_sat_fix  TwistStamped|PoseStamped|Imu|ADMAStatus|ADMADelta|NavSatFix
/front_mono/image/compressed            sensor_msgs/CompressedImage      87 (dyn) / 114 (static)
/front_mono/camera_info                 sensor_msgs/CameraInfo
/delphi_esr_detection_visu              sensor_msgs/PointCloud2          209 / 271
/delphi_esr_object_visu                 visualization_msgs/MarkerArray   105 / 136
/front_ibeo_lux/as_tx/point_cloud|objects|object_contour_points   66/66/66  (static 85)
/rear_ibeo_lux/as_tx/point_cloud|objects|object_contour_points    63/63/54  (static 82/83/83)
/tf_static, /velodyne_nodelet_manager_cloud/parameter_descriptions
```

**Lưu ý**: `meta_data_dataset.json` khai `ros_topic: "/adma"` — topic đó **không tồn tại**; thực tế là 6 topic
`/adma/*` như trên. Raw bag **không có** topic label/annotation nào → labels của SSPP do pipeline riêng tạo (mục 7).

## 2. Frame count: bag vs SSPP — SSPP KHÔNG cắt bớt

So khớp theo basename bag ↔ scene `<NNNN>_<basename>` (strip `.bag`), đếm `*.bin` trong `velodyne/`.

| scene | bag | frames trong bag | frames trong SSPP | tỉ lệ |
|---|---|---|---|---|
| 0053_2021-09-08-16-06-27_0 | 66.4 MB | 50 | 50 | 1.000 |
| 0100_2021-09-08-17-53-31_0 | 92.7 MB | 71 | 71 | 1.000 |
| 0082_2021-09-08-17-25-45_0 | 704.3 MB | **492** | **491** | 0.998 |

Bag dài: SSPP bỏ **đúng 1 frame** (index 217 của bag, 37 812 pts); từ đó về sau lệch 1
(`bag[i+1] == ssp[i]` đúng cho cả 274 frame còn lại), tổng điểm lệch **đúng 37 812**
(17 277 575 − 17 239 763). Vậy đây là **drop lẻ từng frame**, không phải cửa sổ cố định, không phải truncate.

Toàn bộ 108 scene Crafter_dynamic: 8 930 frame velodyne. `r(bag MB, SSPP frames) = 0.9979` trên 108 cặp
→ kích thước bag giải thích 99.6% phương sai số frame ⇒ không có scene nào bị cắt cụt.
Kết luận: raw bag **không chứa nhiều frame hơn** đáng kể; tỉ lệ giữ được 612/613 = **99.84%**.

Một khác biệt thật: SSPP **subsample camera** về đúng nhịp lidar. Bag 66 MB có 87 ảnh / 50 lidar;
scene tương ứng có đúng 50 ảnh (= 50 frame). Scene 0082: 491 ảnh / 491 velodyne.

## 3. Bag static (không có counterpart trong SSPP)

Median-size bag `Crafter_static/2021-09-09-10-15-04_0.bag` (91.8 MB): **65 velodyne frames**, duration **6.79 s**,
**9.95 Hz**, 20 topic, 114 ảnh. Bag lớn nhất `2021-09-09-13-24-38_0.bag` (579.7 MB): **441 frames / 44.65 s**.

8 bag static lấy mẫu trải đều 58.5–579.7 MB (`tmp/probe_count.py`, chỉ đọc header/index nên rất rẻ):
frames/MB = 0.701–0.761 (mean 0.726), Hz = 9.23–9.88 (mean 9.55).
Fit `frames = 0.7547 × MB` (rms 3.3) → áp lên 163 bag / 15 976 MB (zip entries) = **≈ 12 058 frames ≈ 1 212 s ≈ 20.2 phút**
(ước lượng chặn dưới theo fit có intercept: 11 581 frames). Kiểm chứng ngược trên Crafter_dynamic: fit dự đoán
8 913 vs thực đo 8 930 (**−0.2%**).

## 4. Ego velocity — lấy được, và static đúng là đứng yên

Topic: `/adma/twist` (`geometry_msgs/TwistStamped`), 527–686 msg/bag ≈ 100 Hz. Script `tmp/probe_full.py`
decode toàn bộ rồi lấy median `|twist.linear.x|`:

| bag | median speed | so với xlsx (`ego_velocity`) |
|---|---|---|
| dynamic 2021-09-08-16-06-27_0 | 24.175 m/s = 87.0 km/h | 90 |
| dynamic 2021-09-08-17-53-31_0 | 36.312 m/s = 130.7 km/h | 130 |
| static 2021-09-09-10-15-04_0 | **0.000 m/s** (p10=p90=0) | 0 |

`meta_data_measurement.xlsx` (549 dòng, xem mục 0) có `ego_velocity` + `object_velocity` + `distance_to_object`
+ `amb_tmp` + `unimog_direction` + `measurement_itr` + `itr_after_water` + `comment` cho **từng recording**.
Cụ thể: Crafter_dynamic 108/108 dòng, `ego_velocity == object_velocity` ∈ {50,60,…,130} km/h (12 bag mỗi mức);
Crafter_static 162/163 dòng, `ego_velocity = 0` toàn bộ, `object_velocity` 50–130 (18 bag mỗi mức),
`distance_to_object = None`, `amb_tmp` 18–26. Thiếu đúng 1 dòng: bag **lớn nhất** `2021-09-09-13-24-38_0.bag`.
⇒ Static **có** speed label (ego = 0, object = 50–130 km/h) — "blocker thiếu metadata" coi như hết.

## 5. Point format: 5 cột f32 khớp SSPP, nhưng phải áp extrinsic

Message `/velodyne_points`: `fields = x@0, y@4, z@8, intensity@16 (FLOAT32), ring@20 (UINT16)`,
`point_step = 32` → 14 byte không dùng (offset 12–15 và 22–31), tức bag tốn 1.6× băng thông so với SSPP.
`height=1`, `width≈31 381`, `is_dense=true`. SSPP = đúng 5 cột float32, 20 B/point (`583 560 B / 29 178 pts`).

So sánh **từng byte** frame-0 bag 2021-09-08-16-06-27_0 vs `0053_.../velodyne/000000.bin`
(`tmp/compare_exact.py`, 50/50 frame cùng shape):

- `intensity`: **giống hệt từng phần tử** (50/50 frame) → SSPP ship **raw driver intensity**, không normalize.
  Dải giá trị 0–243 (bag) vs 0–242 (SSPP), mean 16.84 vs 16.84.
- `ring`: giống hệt từng phần tử, 0–27/0–28 (VLP-32C dùng 29 ring), SSPP lưu as float32.
- `x,y,z`: **khác** — vì SSPP đã transform sang rear-axle frame. Fit affine `tmp/fit_tf.py`:
  residual max **7.06e-06 m** trên 31 381 điểm với
  `R(roll=-0.0183, pitch=-0.0100, yaw=-1.5847)`, `t=(1.33334, 0.00935, 1.68467)` — trùng khớp
  `tf_from_reference_point` của sensor Velodyne trong `meta_data_dataset.json` (−0.017 / −0.010 / −1.587,
  x=1.333, y=0.009, z=1.686). Nghĩa là converter chỉ cần `p_sspp = R @ p_bag + t`, giữ nguyên intensity/ring.

## 6. Cost đọc/convert (số thực đo)

| phép đo | kết quả |
|---|---|
| extract 1 bag 92.7 MB từ zip (warm) | 0.5–1.4 s |
| extract bag 704.3 MB từ zip (cold) | **27.9 s** → 25 MB/s |
| `Reader.open()` + parse index | 0.16 s |
| decode + tính stats 492 frame (552.9 MB points) | **14.0 s** = 28 ms/frame |
| decode + ghi 5×f32 50 frame (`tmp/convert_test.py`) | **0.32 s** = 6.4 ms/frame = 157 frame/s |
| bytes/point | 32 B (bag) → 20 B (SSPP) = **0.625×**; 984 947 B/frame → 615 592 B/frame (30 780 pts) |

Projection cho **163 bag static** (ước lượng 12 058 frame, 15.98 GB uncompressed):
extract 15.98 GB @25 MB/s ≈ **640 s**, convert 12 058 × 6.4 ms ≈ **77 s**, ghi ra **7.4 GB**.
→ **≈ 12 phút** lý thuyết, thực tế 15–20 phút (I/O + overhead). Crafter_dynamic tương tự: 5.5 GB output.

Zip đọc trực tiếp? `rosbags` 0.11.9 cần path thật (`Reader.__init__` gọi `path.exists()`, `open('rb')`).
Đã **thử** wrapper `RPath`-like bọc `ZipFile.open()`: **chạy được** (20 topic) nhưng open 6.7 s + đọc 50 frame
5.4 s = **12.1 s/bag 66 MB**, chậm ~2.5× so với extract+đọc (≈4.9 s) vì seek lùi phải giải nén lại.
`rosbags-convert` chuyển sang rosbag2 — không dùng được cho layout .bin của SSPP.
Đĩa: còn **28 GiB**; 7.4 GB output (chỉ velodyne) là vừa; nếu kèm `image_2` (+~5 GB) thì sát ngưỡng.

## 7. Blocker dùng static trong experiment hiện tại (đã kiểm tra, không suy đoán)

Adapter `spray/sspp_adapter.py` cần: `velodyne/*.bin` (5 cột), `labels/*.label`, `metadata.txt`
(object_velocity, ego_velocity), `object_labels/lidar/*.json` (3D box). Không đọc `image_2`.

| # | blocker | Kết luận | Bằng chứng |
|---|---|---|---|
| 1 | point-wise spray label | **THẬT** | bag chỉ có 20 topic, không có topic label; `.label` do pipeline SSPP tạo (`third_party/semantic_spray_dataset`), raw bag không mang |
| 2 | 3D boxes | **THẬT** | `object_labels/lidar` = 1 `3D_BOX`/frame, **UUID mới mỗi frame** → annotation per-frame. Bag chỉ có tracker của Ibeo (`/front_ibeo_lux/as_tx/objects` MarkerArray) và marker radar — không phải GT format |
| 3 | metadata per-scene (speed/distance/water) | **HẾT** (đã gỡ) | `meta_data_measurement.xlsx` phủ 162/163 bag static, đủ 11 cột; chỉ thiếu bag lớn nhất |
| 4 | poses | **KHÔNG** (không phải blocker) | `/adma/pose` 686 msg/bag static; ego đứng yên (twist=0); `poses.txt` của SSPP vốn không có translation |
| 5 | alignment frame index | **KHÔNG** | bag msg i ↔ frame i, đúng 1:1, y như dynamic |
| 6 | camera | **KHÔNG** | adapter không đọc ảnh → không cần convert 5 GB ảnh |
| 7 | 1 bag static thiếu metadata | **THẬT nhưng nhỏ** | `2021-09-09-13-24-38_0.bag` (441 frame) không có dòng trong xlsx → loại hoặc tự suy |

Không xác định được (và lý do):
- Tổng frame static **chính xác** — chỉ ngoại suy từ 8 bag mẫu (sai số ~±4%); đếm đủ 163 bag đòi extract 16 GB.
- Có thể dựng lại 3D box từ `/front_ibeo_lux/as_tx/objects` hay không — chưa thử (cần decode MarkerArray
  + so khớp hình học với box SSPP trên scene dynamic).
- Nội dung `Golf_static` / `Golf_dynamic` thật: Golf_static không tải; bản cache Golf_dynamic bị hỏng.
- Tỉ lệ drop frame của SSPP có hệ thống không: chỉ quan sát 1 frame/613 ⇒ chưa đủ để nói quy luật.

## Verdict

**Ingest cost = cheap.** Chi phí lớn nhất: **giải nén 16 GB `Crafter_static.zip` (~11–13 phút ở 25 MB/s)**, cộng
7.4 GB output; convert thuần chỉ ~1–2 phút. **Static subset hiện KHÔNG dùng được ngay** trong experiment đang có:
nó **không có point-wise labels và không có 3D boxes** (2 blocker đã verify bằng topic list + nội dung
`object_labels`); blocker metadata thì **đã gỡ** nhờ `meta_data_measurement.xlsx`. Muốn dùng static phải chạy
(pipeline gán nhãn spray + annotate/track box) — tức chi phí thật không nằm ở ingest mà ở labelling.
Giá trị tăng thêm của raw bag so với SSPP gần như bằng 0 về frame (99.84% frame SSPP đã có sẵn, có nhãn).
