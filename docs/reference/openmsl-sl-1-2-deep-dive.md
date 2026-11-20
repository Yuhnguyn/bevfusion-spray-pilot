# openMSL/sl-1-2 — đọc sâu repo mô hình LiDAR phản xạ

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S1.
> Phần còn đúng: Tài liệu này mô tả CODE THAM CHIẾU (`dee.cpp`), không mô tả repo — đọc kèm cảnh báo này.

Đọc ngày 2026-11-17, tại `main` @ `72323af` (2023-09-06). Repo: <https://github.com/openMSL/sl-1-2-reflection-based-lidar-object-model>.

Tài liệu này là bản đọc-hiểu, **không phải** bản port. Mục đích: biết chính xác cái gì trong
`spray/plume.py`, `spray/plume_state.py`, `spray/raycast.py`, `spray/wet_ground.py` là
`[CODE]` lấy từ đây, và cái gì **không** lấy được vì code này làm khác paper.

Nhãn nguồn giữ theo `GLOSSARY.md`: `[ĐO]` đo trên máy này · `[PAPER]` paper nói ·
`[CODE]` code tham chiếu quy định · `[CHỌN]` tự chọn.

---

## 0. Tóm tắt một đoạn

Đây là **mô hình cảm biến cấp hệ thống**, không phải mô hình quang học. Nó không bắn tia. Nó
nhận **reflection đã được ray-trace sẵn** từ công cụ mô phỏng (mỗi tia một `path_length` +
`signal_strength`), rồi làm bốn việc: (1) gom tia siêu lấy mẫu thành **echo** theo từng beam,
(2) chèn nhiễu môi trường — mưa/sương/tuyết/mặt trời/**spray nước đường** — vào chính các echo đó,
(3) biến detection thành point cloud, (4) gán điểm vào box GT rồi chạy một **tracker giả lập**.
Nó đóng gói thành **FMU 2.0** nói **OSI 3.0** qua khung **OSMP**.

Với dự án này, phần đáng đọc chỉ có **một file**: `DetectionEnvironmentalEffects.cpp`, hàm
`add_spray_detections` + `append_spray_cluster` + `update_spray_cluster`. Đó là nguồn `[CODE]`
duy nhất của generator plume. Phần còn lại (detection sensing, segmentation, tracking, OSMP)
**không dùng được** cho SemanticSpray++ vì nó đòi `SensorView` có reflection từ ray-tracer, còn
ta có point cloud thật.

---

## 1. Bản đồ repo

174 file, ~10.100 dòng C++/CMake/config. Ba tầng rõ rệt:

```
CMakeLists.txt                    # đọc model_name.conf → tên FMU
lib/                              # 3 git submodule
  eigen/                          #   gitlab.com/libeigen/eigen
  fmi2/                           #   github.com/modelica/fmi-standard
  open-simulation-interface/      #   gitlab.setlevel.de/open/osi   ← OSI *của SETLevel*, không phải ASAM
src/
  model/
    model_name.conf               # "sl-1-2-reflection-based-lidar-object-model"
    include/                      # Strategy (interface), Sequence (runner) — không sửa
    profiles/                     # profile.hpp.in (khai báo) + profile_<SENSOR>.hpp.in (giá trị)
    strategies/                   # ★ toàn bộ logic nằm ở đây
      sequence.conf               #   thứ tự 5 strategy lõi
      csv_output_sequence.conf    #   thứ tự strategy xuất .csv
      pcd_output_sequence.conf    #   .pcd
      bin_output_sequence.conf    #   .osi nhị phân
      ros_output_sequence.conf    #   ROS (rỗng)
      transformation-functions/   #   TF:: — hình học, dùng chung
      lidar-detection-sensing-strategy/       # ① reflection → echo
      lidar-environmental-effects-strategy/   # ② ★ mưa/sương/tuyết/mặt trời/SPRAY
      lidar-pointcloud-fusion-strategy/       # ③ detection → point cloud
      lidar-segmentation-strategy/            # ④ gán điểm vào box GT
      lidar-tracking-strategy/                # ⑤ tracker giả lập
      {csv,pcd,ros,binary}-output-*-strategy/ # xuất file
  osmp/                           # đóng gói FMI 2.0: modelDescription.in.xml + FrameworkPackaging.cpp
sl-1-2-*.srmd                     # metadata SETLevel (SRMD)
```

**Điều quan trọng nhất về kiến trúc:** `src/model/strategies/sequence.conf` là **danh sách
strategy được biên dịch vào FMU**. CMake đọc file này, `add_subdirectory` từng thư mục, và
`configure_file` sinh ra `sequence.cpp` từ template `sequence.cpp.in`. Muốn bỏ tracking khỏi
FMU thì xoá một dòng trong `sequence.conf`, không phải sửa code.

---

## 2. Khung OSMP / FMI — giao diện với thế giới ngoài

### 2.1 Hợp đồng dữ liệu

FMU **không có input scalar**. Toàn bộ trao đổi là protobuf nhị phân, truyền qua con trỏ bị
chẻ thành hai số nguyên 32-bit:

| Biến | Vai trò | Kiểu | valueReference |
|---|---|---|---|
| `OSMPSensorViewIn.base.lo/.hi/.size` | vào | `SensorView` | 0/1/2 |
| `OSMPSensorDataOut.base.lo/.hi/.size` | ra | `SensorData` | 3/4/5 |
| `OSMPSensorViewInConfigRequest.*` | FMU hỏi ngược master | `SensorViewConfiguration` | 6/7/8 |
| `OSMPSensorViewInConfig.*` | master trả lời | `SensorViewConfiguration` | 9/10/11 |
| `profile` | chọn profile | String | 0 |
| `switch_for_csv_output` / `pcd` / `ros` | bật xuất file | Boolean | 0/1/2 |

`decode_integer_to_pointer` trong `FrameworkPackaging.cpp` dùng `union { struct{int lo,hi;} base;
unsigned long long address; }` — tức là giả định little-endian. Đây là mẹo chuẩn của OSMP, không
phải bug, nhưng nó là lý do FMU này không chạy được trên kiến trúc big-endian.

### 2.2 Vòng đời một bước

```
fmi2Instantiate → doInit()          : zero toàn bộ biến, set profile mặc định
fmi2ExitInitializationMode
    → doExitInitializationMode()    : set_output_switches(); load_profile_or_complain(fmi_profile())
fmi2DoStep → doCalc()
    get_fmi_sensor_view_in(currentIn)          // ParseFromArray
    currentOut.Clear(); currentOut.add_sensor_view() = currentIn   // ← copy nguyên SensorView
    sequence_of_strategies.apply(currentOut)   // ★ toàn bộ model ở đây
    set_fmi_sensor_data_out(currentOut)        // SerializeToString
```

Hai chi tiết dễ bỏ qua:

1. **`SensorView` được copy nguyên vào `SensorData.sensor_view`.** Đó là lý do README nói "all
   information on model input is passed to the output" — không phải model cố ý, mà là
   `add_sensor_view()->CopyFrom(currentIn)`.
2. **`refresh_fmi_sensor_view_config_request()`** cho phép master hỏi "mày cần cấu hình gì" trước
   khi chạy. Nếu master không hỏi, `doExitInitializationMode` nói rõ "Config request was not
   queried, therefore default profile's config will be loaded".

### 2.3 Profile — hệ thống tham số hai tầng

Đây là chỗ dễ đọc sai nhất trong repo. Cơ chế:

```
profiles/profile.hpp.in            struct Profile { ... @PROFILE_STRUCTS@ ... }
profiles/profile_VLP32.hpp.in      Profile generate() { Profile VLP32; VLP32.no_of_layers = 32; ... }
strategies/*/profile_struct.hpp.in struct det_envir_effects { ... }     ← khai báo thêm field
strategies/*/profile_VLP32.hpp.in  VLP32.det_envir_effects.calibrated_spray = true;  ← gán giá trị
```

`CMakeLists.txt` của mỗi strategy có `add_profile_part(${PROFILES})`: nó **append** nội dung
`profile_<SENSOR>.hpp.in` của strategy vào cuối file `profile_<SENSOR>.hpp` đã sinh, và append
`profile_struct.hpp.in` vào biến `PROFILE_STRUCTS` để nội suy vào `profile.hpp`.

Hệ quả: **một profile là hợp của 5 file rời** (main + 4 strategy có profile: detection-sensing,
environmental-effects, segmentation, tracking). Không có file nào chứa toàn bộ tham số của VLP32.

Năm profile: `VLP32` (mặc định, `profile_list.conf` dòng đầu), `SCALA_1`, `Ibeo_LUX_2010`,
`VLP16`, `Blickfeld`.

| Profile | layer | rays/beam (v×h) | FoV H×V | chu kỳ | `calibrated_spray` |
|---|---:|---|---|---:|---|
| **VLP32** | 32 | 3×3 = 9 | 180°×170° | 100 ms | **true** |
| VLP16 | 16 | 3×3 = 9 | 180°×170° | 100 ms | false |
| SCALA_1 | 3 | 49×5 = 245 | 180°×170° | 40 ms | false |
| Ibeo_LUX_2010 | 4 | 41×9 = 369 | 180°×170° | 80 ms | false |
| Blickfeld | 32 | 11×11 = 121 | 72°×20° | 119 ms | false |

**Chỉ VLP32 có spray được hiệu chỉnh.** Bốn profile còn lại có `calibrated_spray = false` và
**không có** các field `distance_distr_in_cluster_mu` … `cluster_radius_dist_sigma` — chúng dùng
giá trị khởi tạo mặc định của struct (0.0). Nếu ai đó chạy profile VLP16 với spray bật, cụm sẽ có
bán kính lognormal(0,0) = 1.0 m, `time_constant` = 0, `mean_attenuation` = 0. Đây là bẫy thật.

### 2.4 Có một chỗ hỏng trong repo

`src/model/strategies/lidar-segmentation-strategy/` có `profile_ReflectionRadar.hpp.in`, và
`lidar-tracking-strategy/` có ba file `profile_{ReflectionRadar,LongRange_Radar,MidRange_Radar}.hpp.in`.
Nhưng `src/model/profiles/profile_list.conf` **không** liệt kê `ReflectionRadar` hay hai profile
radar kia. Vì `add_profile_part(${PROFILES})` chỉ lặp trên `PROFILES`, ba file đó **không bao giờ
được đọc**. Đây là tàn dư của một mô hình radar dùng chung khung (đúng như description repo:
"radar or lidar sensor system model, depending on parametrization"), đã bị bỏ dở.

---

## 3. ① Detection Sensing — reflection → echo

File: `strategies/lidar-detection-sensing-strategy/src/DetectionSensing.cpp` (411 dòng).

Đây là tầng **vật lý của cảm biến**, và là tầng duy nhất trong repo thực sự thú vị về mặt tín hiệu.

### 3.1 Đầu vào

Với mỗi `lidar_sensor_view.rendering_result()` (một reflection):

- `emitted_signal_idx` — tia nào trong `sensor_view_configuration.lidar_sensor_view_configuration.emitted_signal`
- `path_length` — quãng đường **khứ hồi** (code chia 2 để lấy range)
- `received_signal.signal_strength` — **dBm**

### 3.2 Thuật toán, từng bước

```
1. bỏ reflection nếu path_length/2 < min_range
2. beam_idx = floor(emitted_signal_idx / rays_per_beam)          ← gom tia siêu lấy mẫu về beam
   dist_cell_idx = ceil((path_length/2 - min_range) / distance_resolution_adc)
   signal_strength_in_mW = 10^(dBm/10)                            ← đổi sang mW để CỘNG được
3. sort theo beam_idx
4. với mỗi beam:
   a. sort các cell theo dist_cell_idx
   b. cộng mW của các reflection rơi cùng dist_cell_idx           ← đây là tích phân năng lượng
   c. threshold_summed_beam_cell(): dBm = 10*log10(mW); nếu range_comp_threshold và
      range > thres_distance_m: threshold *= (thres_distance_m/range)^2
      → giữ cell nếu dBm >= threshold
   d. tìm peak: cell mới nếu dist_cell_idx vượt cell trước > echo_separation_distance/resolution
      trong một peak: epw = số cell × resolution; distance & strength lấy cell MẠNH NHẤT
   e. giới hạn max_echos_per_beam
5. với mỗi peak, sinh một osi3::LidarDetection:
   distance = echo_pulse_start (mode "start") hoặc peak.distance (mode "peak")
   + noise N(0, distance_stddev), rồi round về distance_resolution
   azimuth/elevation = góc của BEAM (không phải của tia)
   intensity: nếu range_compensate_intensity:
       I = round(mW * r² / (π d²/4) / emitted_mW * π * 100) / 255 * 100
     ngược lại: I = (dBm - threshold_dBm)/(max_emit_dBm - threshold_dBm) * 100
```

### 3.3 Ba điểm cần hiểu đúng

**(a) "Super-sampling" nằm ở đâu.** `rays_per_beam_vertical × rays_per_beam_horizontal` tia được
bắn cho **mỗi beam** (VLP32: 3×3 = 9 tia). Công cụ mô phỏng trả về 9 reflection; model gom chúng
về một beam rồi tìm peak theo trục cự ly. Đó chính là cơ chế cho phép **hai echo trên một beam**
khi một phần tia trúng vật phía trước và một phần trúng vật phía sau — đúng như README mô tả và
như hình `doc/img/over_sampling.png`.

**(b) `distance_resolution_adc` là thùng chứa năng lượng, `distance_resolution` là lượng tử hoá
đầu ra.** VLP32: 0,05 m cả hai. Nhưng chúng là hai khái niệm khác nhau — một cái là độ phân giải
của bộ chuyển đổi tương tự-số (quyết định có cộng dồn hay không), một cái là độ phân giải của giá
trị xuất ra.

**(c) Range-compensated threshold là mô hình "suy hao theo 1/r²".** Với `range > 30 m`, ngưỡng bị
nhân `(30/r)²`. Nghĩa là ở 120 m, ngưỡng thực tế thấp hơn 12 dB so với ngưỡng danh nghĩa −70 dBm.
Nếu không có cơ chế này, mọi thứ xa hơn ~50 m đều bị cắt.

### 3.4 Nhiễu ngẫu nhiên — và tại sao nó không tái lập được

```cpp
std::knuth_b generator(std::rand());   // rand used for Windows compatibility
```

`std::rand()` **không được seed** trong repo. Trạng thái global của `rand()` là trạng thái ẩn;
kết quả phụ thuộc thứ tự gọi và thư viện chuẩn. Có **nhiều** chỗ trong repo dùng
`std::random_device generator;` (environmental effects) — cái này là **nguồn ngẫu nhiên thật của
hệ điều hành**, không tất định ngay cả khi seed. Hệ quả: **FMU này không tái lập được bit-exact
giữa hai lần chạy**. Đây là điều phải biết nếu ai định dùng nó làm reference cho test.

`generator` (plume của dự án này) đã chọn đường ngược lại: seed tất định qua `seed_for()`.

---

## 4. ② ★ Environmental Effects — chỗ có spray

File: `strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp`
(833 dòng). Đây là file **duy nhất** trong repo mà `spray/` của dự án này port từ đó.

`apply()` chỉ làm một việc: nếu có `sensor_view` và có ít nhất một `lidar_sensor` và **bất kỳ**
cờ `calibrated_*` nào bật, thì lặp qua từng sensor và gọi ba hàm:

```cpp
add_hydrometeor_detections(...);   // mưa / tuyết / sương
add_spray_detections(...);         // ★ spray nước đường
add_sun_blinding_detections(...);  // chói mặt trời
```

### 4.1 Mưa / tuyết / sương — mô hình "detection giả trong không khí"

Nguồn: Linnhoff et al., *Measuring the Influence of Environmental Conditions on Automotive Lidar
Sensors*, MDPI Sensors 22(14):5266, 2022.

```
weather_intensity = class_mean[ precipitation_class ]      // mưa
                  = class_mean[ fog_class ]                // sương
atm_detection_probability = factor × weather_intensity
với mỗi beam:
    random_var > 1 - (prob × layer_comp_factors[layer])  → sinh một detection giả
    distance ~ lognormal(rain_detection_dist_distr_mu, _sigma), round về distance_resolution
    intensity ~ Poisson(intensity_distr_lambda)
```

`layer_comp_factors` là mảng dài bằng số layer, bù cho việc các layer nhận số detection khí quyển
không đều (VLP16 có giá trị thật như `0.49 … 1.85`; VLP32 toàn 1.0 vì chưa hiệu chỉnh).

**Đây là mô hình dạng "sinh detection rời rạc", không phải mô hình mật độ điểm.** Nó không sinh
điểm trong không gian 3D liên tục, không có cụm, không có lifetime. Khác hẳn spray.

### 4.2 ★ Spray — mô hình "cụm cầu có trạng thái thời gian"

Nguồn: Linnhoff et al., *Simulating Road Spray in Lidar Sensor Models*, IEEE Sensors Journal
(2022, khi đó under review). Đây là phần dự án này port.

#### 4.2.1 Điều kiện kích hoạt

```cpp
double water_film_height = sensor_view(0).global_ground_truth().lane(0)
                             .classification().road_condition().surface_water_film();
if (water_film_height <= 0.0) return;          // ← (A) không có nước thì không có spray
...
if (object_velocity > 40/3.6 m/s && water_film_height > 0)   // ← (B) ngưỡng 40 km/h
```

Hai điều kiện **độc lập**: (A) chặn toàn bộ hàm, (B) chặn từng vật thể. Ngưỡng 40 km/h nằm trong
`SprayProfile::object_velocity_threshold_in_m_s = 40 / 3.6`, hard-coded trong header, **không**
trong profile. Đây là `[CODE]` đã port thành `ACTIVATION_SPEED_KMH = 40.0` trong `plume_state.py`.

`water_film_height` đọc từ `lane(0)` — **chỉ một làn**, comment trong code nói rõ "currently only an
equal water film across all lanes is covered". SemanticSpray++ không khai báo độ ướt ⇒ dự án này
phải `[CHỌN]` 1 mm.

#### 4.2.2 Vùng spray: một hộp sau đuôi xe

`define_spray_volumes()` — với mỗi `moving_object` có `|v| > 40 km/h`:

```cpp
volume.dimension.length = |v| × update_cycle_time_s     // ← quãng đường đi trong một chu kỳ
volume.dimension.width  = 3.4                            // hard-coded
volume.dimension.height = 1.5                            // hard-coded
volume.orientation.yaw  = object.yaw
volume.position         = object.position − [cos(yaw), sin(yaw)] × (L_obj/2 + L_vol/2)
volume.position.z       = object.position.z − H_obj/2 + H_vol/2
```

Đọc kỹ: hộp nằm **ngay sau đuôi**, dài đúng bằng quãng đường vật thể đi trong một chu kỳ cảm
biến. Ở 100 km/h với Δt = 0,1 s: L = 2,78 m, W = 3,4 m, H = 1,5 m. Đó là một khối dẹt, rộng hơn
xe, cao 1,5 m tính từ mặt đường.

`width = 3.4` và `height = 1.5` là **magic number không có trong profile** — đây là một trong
những thứ ticket 12 ("Explain hardcoded values") của repo đã đụng tới nhưng vẫn để nguyên.

#### 4.2.3 Số cụm mỗi chu kỳ

```cpp
mean_num_clusters = (num_clusters_wfh_factor × wfh + num_clusters_wfh_offset)
                  × (object_velocity × 3.6 − num_clusters_velocity_offset_kmh);
num_spray_cluster = round(max(0.0, mean_num_clusters));
```

Với VLP32: `(0.2·wfh + 0.1) × (v_kmh − 50)`.

Kiểm tra số học — đây là chỗ **quan trọng nhất cho dự án này**:

| v (km/h) | wfh = 1 mm | cụm/chu kỳ | cụm/frame (Δt = 0,1 s) |
|---:|---:|---:|---:|
| 50 | 1 | 0,3 × 0 = **0** | 0 |
| 80 | 1 | 0,3 × 30 = **9** | 9 |
| 100 | 1 | 0,3 × 50 = **15** | 15 |
| 130 | 1 | 0,3 × 80 = **24** | 24 |

So với `docs/reference/paper-qa-notebooklm.md` §9.3: paper suy ra **2,5 / 3,5 / 4,1** cụm/chu kỳ ở
80/100/130 km/h ướt đẫm. Code cho **9 / 15 / 24** — **sai 4–6×**, và sai theo hướng *nhiều cụm
nhỏ* thay vì *ít cụm dày*. Đây chính là "kết luận 1" đã ghi trong tài liệu paper-QA. Xác nhận
bằng đọc code: công thức `(0,2·wfh + 0,1)·(v−50)` đúng là nguồn gốc con số sai.

Lưu ý thêm: hệ số `(0,2·wfh + 0,1)` làm số cụm **phụ thuộc độ ẩm**, trong khi paper nói độ ẩm tác
động qua **`T`** (cụm sống lâu hơn ⇒ thấy nhiều hơn), không qua tốc độ sinh. Đây là "kết luận 2".

#### 4.2.4 Sinh một cụm

```cpp
// vị trí: uniform trong hộp
vol_coord = [L·U(0,1) − L/2,  W·U(0,1) − W/2,  H·U(0,1) − H/2]
position_global = transform_position_from_object_to_world_coordinates(vol_coord, volume)

radius         = min(1.0, lognormal(cluster_radius_dist_mu, cluster_radius_dist_sigma))
                 // VLP32: μ = −1.2, σ = 0.8  → median = e^−1.2 = 0.301 m
age_in_s       = −update_cycle_time_s            // ← sinh ra ĐÃ ÂM một chu kỳ
time_constant  = N( wfh·0.02·(v_kmh − 50) + 0.2 ,  std_time_constant = 0.2 )
velocity       = object.velocity,  vz += 5.0 · U(0,1)     // ← có vận tốc lên
drag_factor    = N(−0.12, 0.04)
```

Bốn con số cần nhớ:

1. **`age = −Δt`** — cụm vừa sinh **chưa hoạt động** ở frame hiện tại. Trong `add_spray_detections`
   có `if (... || current_spray_cluster.age_in_s < 0) continue;`. Đây là `[CODE]` mà
   `plume_state.py` đã port ("clusters spawn with `age = -dt` so they are not active on their
   birth frame").
2. **`radius = min(1.0, lognormal(−1.2, 0.8))`** — median 0,301 m, nhưng **bị chặn trên ở 1,0 m**.
   `plume_state.py` giữ `RADIUS_MU = -1.2`, `RADIUS_SIGMA = 0.8`, `RADIUS_MAX_M = 1.0`.
3. **`time_constant` = `T`** trong `T = 0,02·wfh·(v−50) + 0,2` — đúng công thức paper §9.1 xác
   nhận. `plume_state.py`: `LIFETIME_WFH_COEFF = 0.02`, `LIFETIME_BASE_S = 0.2`,
   `LIFETIME_SIGMA_S = 0.2`.
4. **`vz += 5·U(0,1)`** — code C++ cho cụm bay lên. **Paper không có phương trình z và không có
   vận tốc ban đầu thẳng đứng.** `plume_state.py` đã chọn theo paper: `INITIAL_VZ_MAX_MPS = 0.0`,
   ghi rõ "``dee.cpp:540`` does draw a `vz`, but that is the reference code, not the paper". Đây
   là một **khác biệt có chủ ý** giữa dự án và code tham chiếu — phải nhớ khi so sánh kết quả.

#### 4.2.5 Cập nhật cụm mỗi frame

`update_spray_cluster()`:

```cpp
// gió hard-coded
wind_direction_deg = 208.0;   wind_speed = 2.0;
wind = [sin(208°), cos(208°), 0] × 2.0

với mỗi cụm, nếu age > −Δt:                     // tức là đã sống ít nhất một frame
    v_air = wind + v_cluster                     // ← cộng, không trừ
    v_cluster += drag_factor · (v_air/|v_air|) · |v_air|² · Δt
    position   += v_cluster · Δt
get_min_max_azimuth_of_cluster()                 // lọc thô theo góc phương vị
age += Δt
sort theo dist_to_sensor
xoá nếu age > 4 · time_constant
```

Ba điểm đáng chú ý:

- **`v_air = wind + v_cluster`** — dấu cộng. Về mặt vật lý, vận tốc tương đối của cụm so với không
  khí phải là `v_cluster − v_wind`. `plume_state.py` đã sửa: "drag acts in the ground frame:
  `v_air = v_ground - wind`" và ghi rõ đây là chỗ **cố ý khác** `dee.cpp`.
- **`drag_factor ~ N(−0.12, 0.04)`** — mỗi cụm có hệ số riêng. Paper dùng hằng số `C = −0.15 1/m`.
  `plume_state.py`: `DRAG_MEAN = -0.15`, `DRAG_STD = 0.0` — theo paper, giữ knob để test.
- **Ngưỡng xoá `age > 4·T`** — paper **không nói**, đây là `[CODE]` thuần.
  `plume_state.py`: `MAX_AGE_FACTOR = 4.0`.

#### 4.2.6 Bắn tia vào cụm — phần cốt lõi

`add_spray_detections()` lặp **từng beam** của `beam_center_config` (không phải từng tia siêu lấy
mẫu — spray được tính ở mức beam):

```cpp
existing_detection = detection của beam này từ tầng ① (hoặc "không có" → distance = max_range)
max_distance_to_spray_detection = existing_detection.distance      // ← (i)
distance_in_spray_cluster = 0.0

với mỗi cụm:
    if beam.azimuth ngoài [min_azimuth, max_azimuth] của cụm → skip
    if age < 0 → skip
    if cụm nằm TRÊN xe ego (kiểm tra hộp ego trong toạ độ cảm biến) → skip
    dist_to_intersect = intersection_with_sphere(center, radius, az, el)
    if 2 nghiệm và min(nghiệm) < max_distance_to_spray_detection:        // ← (ii)
        L = nghiệm[1] − nghiệm[0]                    // độ dài tia trong cụm
        distance_in_spray_cluster += L
        P_det = min(1, lognormal(mu=−2.3, sigma=1.1))        // ← (iii)
        P_det *= min(1, exp(−age / T))                        // ← (iv) cụm già khó thấy
        if U(0,1) > 1 − P_det:                                // ← (v) Bernoulli
            center_range = (t0 + t1)/2
            distance = N(center_range, L/6)                   // ← (vi)
            intensity = N(0.5, 0.05)/255 × 100                // ← (vii) chỉ để XẾP HẠNG
            att = exp(−2 · mean_attenuation · distance_in_spray_cluster)   // ← (viii)
            if distance < max_distance_to_spray_detection && above_ground:
                push (distance, att × intensity)

add_attenuated_existing_detection(...)      // làm yếu detection thật phía sau spray
add_max_detection(...)                      // giữ MỘT detection mạnh nhất mỗi beam
```

Tám điểm, đọc chậm:

**(i) `max_distance_to_spray_detection = existing_detection.distance`** — nếu beam đã có echo thật
ở 40 m, spray chỉ được sinh **gần hơn 40 m**. Đây là "occlusion" phiên bản đơn giản nhất: một
detection mỗi beam, nên spray không thể xuất hiện sau vật cản. Nó **không** mô hình hoá việc vật
cản chắn spray — chỉ chặn detection.

**(ii) `min(nghiệm) < max_distance`** — cụm phải có phần nằm gần hơn echo thật thì mới xét. Nhưng
`L = nghiệm[1] − nghiệm[0]` lấy **cả** độ dài tia trong cụm, kể cả phần nằm sau echo thật.

**(iii) `P_det = min(1, lognormal(−2.3, 1.1))`** — median = `e^−2.3` = **0,100**. Đây là xác suất
một tia đi qua cụm sinh ra detection. `raycast.py`: `PAPER_P_DET_MU = -2.3`,
`PAPER_P_DET_SIGMA = 1.1`, và paper-QA §9.3 xác nhận "paper là 14,3 det/cụm" — tức là paper nói
P_det cao hơn nhiều so với việc tạo nhiều cụm nhỏ. Với median 0,1 và 24 cụm/chu kỳ, ta được
~2,4 det/chu kỳ — gần với "2–3,5 det/cụm" mà paper-QA §9.3 kết luận là sai.

**(iv) `× min(1, exp(−age/T))`** — xác suất sống sót. Đây là lý do cụm sinh ra có `age = −Δt`:
frame sinh ra nó, `age < 0` nên bị `continue` ở trên; frame sau `age = 0`, `exp(0) = 1`, xác suất
đầy đủ.

**(v) `U(0,1) > 1 − P`** — tương đương `U(0,1) < P`. Viết ngược cho dễ đọc nhưng đúng.

**(vi) `distance ~ N(center_range, L/6)`** — `L/6` là một xấp xỉ "3σ nằm trong cụm". Không có
lý do vật lý, chỉ để detection rơi trong khoảng `[t0, t1]` phần lớn thời gian.

**(vii) `intensity = N(0.5, 0.05)/255 × 100`** — **đây là chỗ dễ hiểu sai nhất trong cả file.**
Giá trị này **không phải** cường độ vật lý của spray. Nó chỉ là **điểm xếp hạng** để
`add_max_detection` chọn detection mạnh nhất mỗi beam. Paper nói rõ: *"the final intensity value of
the simulated spray detections are set to 0"*. `raycast.py` đã port đúng điều này:
`intensity_mu = 0.5`, `intensity_sigma = 0.05` là "only a **ranking score**", và
`min_intensity = 0.0` ⇒ detection spray xuất ra có intensity **đúng bằng 0**.
Xác nhận bằng paper-QA §9.2 và §III: "over 80 % of real spray returns are 0".

**(viii) `att = exp(−2 · 0.02 · L_tích_luỹ)`** — hệ số tắt dần. Paper in ra **σ = 0,02 m⁻¹**, không
in dạng hàm mũ. Hệ số `2` là khứ hồi, `[CODE]`. `raycast.py`:
`mean_attenuation_per_m = 0.02`, ghi rõ `exp(-2 * mean * L)` là `[CODE] dee.cpp:279`.

#### 4.2.7 Làm yếu detection thật — `add_attenuated_existing_detection`

```cpp
if (attenuation_distance > 0) {
    att = exp(−2 · 0.02 · L)
    attenuated_power_mW = att · aperture_area · emitted_mW · I/100 · 255/100 / π / r²
    noise ~ N(attenuated_power_mW, std_attenuation_in_cluster)
    dBm = 10·log10(noise)
    threshold = signal_strength_threshold_in_dBm  (có range-comp nếu bật)
    if (dBm > threshold)
        push (r, I × att)                     // ← intensity bị nhân att, KHÔNG bị thay bằng giá trị từ noise
}
```

Điểm tinh tế: `noise` chỉ dùng để **quyết định có giữ detection hay không**; giá trị intensity
được ghi ra là `existing.intensity × att`. Với `std_attenuation_in_cluster = 2.85e−7` (VLP32),
`noise ≈ attenuated_power_mW` gần như chính xác, nên quyết định giữ/bỏ là tất định theo công thức.

#### 4.2.8 Chọn echo mạnh nhất — `add_max_detection`

```cpp
power_equivalent[i] = intensity[i] / distance[i]²
chọn argmax; nếu distance < max_range thì ghi ra
```

**Đây là quy tắc then chốt của toàn mô hình spray.** Mỗi beam **chỉ có một** detection. Spray
không thể "thêm điểm" — nó chỉ có thể **thay thế** echo thật bằng một detection spray gần hơn và
"mạnh" hơn (theo `I/r²`). Đó là lý do mô hình này tạo ra **false positive** chứ không tạo ra
**thêm mây điểm**: một beam trước đây trỏ vào xe phía trước, giờ trỏ vào cụm spray ở 3 m.

Với dự án này, đây là điểm khác biệt **cấu trúc** lớn nhất: SemanticSpray++ có point cloud 5 cột
`x, y, z, intensity, ring` với **nhiều điểm mỗi beam** (nhiều ring, nhiều tia). Generator của ta
(`plume.py` + `raycast.py`) sinh **điểm**, không thay detection. `raycast.py` có port
`add_max_detection` (`det_dropped_stronger_real`, `real_dropped_plume_stronger` trong
`RaycastStats`) nhưng module đó **chưa nối vào pipeline**.

#### 4.2.9 Mặt đường ướt — `simulate_wet_pavement`

Với mỗi detection có echo thật:

```cpp
z_det = sin(elevation) × distance
nếu |z_det + sensor_height_over_ground| < 0.2 m:          // detection nằm sát mặt đường
    y_det = sin(azimuth) × distance
    nếu 2.0 < y_det < 7.0:                                 // ← cửa sổ hard-coded
        // Hahner et al. 2022, eq. 12–19: Snell + Fresnel qua màng nước
        n_air = 1.0003, n_w = 1.33, pavement_depth = 0.0005 m
        a_in  = atan(r / h_sensor)
        a_aout = asin(sin(a_in)·n_air/n_w)                 // khúc xạ vào nước
        t_ap  = ...                                        // truyền qua mặt phân cách 1
        a_wout = asin(sin(a_aout)·n_w/n_air)
        r_wp, t_wp = ...                                   // phản xạ/truyền mặt phân cách 2
        t_p = t_ap · Γ · t_wp / (1 − Γ·r_wp)
        γ   = clip(wfh / 0.0005, 0, 1)                     // eq. 19
        I = ((1−γ)·Γ + γ·t_p) × 100 × 100/255 × 0.3
        existing.set_intensity(I)
    ngược lại:
        existing.set_intensity(existing.intensity + 2.0/255 × 100)   // ← TĂNG nhẹ
```

Ba điểm:

1. **Cửa sổ `y ∈ (2, 7) m`** là hard-coded, không có trong profile, không có trong paper được
   trích. Nó là "làn bên cạnh" của một cấu hình thử nghiệm cụ thể. `wet_ground.py` đã port
   nguyên `y_window_m = (2.0, 7.0)` và ghi rõ.
2. **`γ` bão hoà ở `wfh = 0,5 mm`** (`0.0005 / 0.0005 = 1`). Với `wfh = 1 mm` (giá trị `[CHỌN]`
   của dự án), `γ = 1` và intensity **giảm** — ngược trực giác "ướt hơn thì sáng hơn".
   `wet_ground.py` ghi rõ điều này: "increasing the water film *lowers* the surviving intensity".
3. **Nhánh `else` tăng intensity 0,78 đơn vị** — không có cơ sở vật lý, giữ nguyên verbatim.
   `wet_ground.py`: `_BOOST_INTENSITY = 2.0/255*100`.

`wet_ground.py` cũng ghi rõ một **khác biệt cố ý**: C++ chuẩn hoá `Γ = I/100` (thang 0–100 của
OSI), còn ta `clip(I/255, 0, 1)` vì cột 3 của SemanticSpray++ là 0–255 thô.

### 4.3 Chói mặt trời — `add_sun_blinding_detections`

Vị trí mặt trời **hard-code** trong code (`azimuth = 1.5°`, `elevation = 19.1°`), comment nói rõ
"Temporary sun definition until corresponding OSI message is defined". `is_sun` chỉ bật được bằng
tay. Công thức xác suất là một **parabol fit từ đo đạc**:

```cpp
detection_probability = brightness_factor × (−598.28·(Δangle − 0.05298)² + 0.281)
```

với `brightness_factor = 0.0000333 × intensity` nếu `intensity < 30000`. Comment trong code nói
thẳng: "calibrated to a Velodyne VLP16 lidar. They need to be adjusted for other lidar types."

**Không liên quan đến spray.** Ghi ở đây chỉ để đủ bản đồ.

---

## 5. ③ Point Cloud Fusion — detection → điểm

File: `lidar-pointcloud-fusion-strategy/src/PointcloudFusion.cpp` (85 dòng). Đơn giản:

```cpp
logical_detection_data.clear()
với mỗi sensor, mỗi detection:
    x = d·cos(el)·cos(az);  y = d·cos(el)·sin(az);  z = d·sin(el)      // cầu → Descartes
    transform_from_local_coordinates(point, mounting_orientation, mounting_position)
    → LogicalDetection{position, intensity | echo_pulse_width}
```

Hai chi tiết:

- Hệ toạ độ cảm biến là **x tiến, y trái, z lên** (chuẩn OSI). `az` quay quanh z, `el` nâng lên.
- Comment trong code cho thấy tác giả đã đổi từ `profile.sensor_view_configuration...mounting_position()`
  sang `sensor_data.feature_data().lidar_sensor(sensor_idx).header().mounting_position()` — tức là
  dùng mounting position mà **tầng ① đã ghi vào header**, không phải từ profile. Đây là chi tiết
  đúng: nếu master cấu hình vị trí khác profile, điểm vẫn đúng.

---

## 6. ④ Segmentation — gán điểm vào box GT

File: `lidar-segmentation-strategy/src/Segmentation.cpp` (109 dòng). Đây là **ground-truth
segmentation**, không phải clustering.

```cpp
với mỗi moving_object (trừ ego):
    corners = 8 góc của box GT
    x_min = corner[2].x − tol;  x_max = corner[0].x + tol     // tol = tolerance_for_segmentation
    y_min = corner[1].y − tol;  y_max = corner[0].y + tol
    z_min = corner[0].z − tol;  z_max = corner[4].z + tol
    với mỗi logical_detection:
        p_world  = ego → world
        p_object = world → object frame
        nếu p_object trong [min, max]: logical_detection.object_id = object.id
```

`tolerance_for_segmentation = 0.3 m` (VLP32) — nới box ra 30 cm mỗi phía.

**Đây là chỗ mô hình "gian lận":** nó dùng box GT để biết điểm nào thuộc vật nào. Không có
clustering, không có association, không có nhiễu gán nhầm. Vì vậy `tracking` bên dưới có thể tập
trung vào việc *ước lượng* hình học và *lọc theo thời gian*, không phải *phát hiện*.

Với dự án này, đây là lý do **không port được**: SemanticSpray++ có box GT, nhưng ta muốn đo
**detector** (BEVFusion), không muốn cho nó biết box. Port segmentation là cho model biết đáp án.

---

## 7. ⑤ Tracking — tracker giả lập

File: `strategies/lidar-tracking-strategy/src/Tracking.cpp` (828 dòng) + `Tracking.hpp` (123 dòng).
Dựa trên luận văn thạc sĩ của P. Aust, TU Darmstadt.

### 7.1 Ý tưởng

Tracker này **không** làm association. Nó lặp qua **từng object GT**, tìm segment điểm đã được
gán cho object đó ở tầng ④, rồi ước lượng trạng thái (vị trí, kích thước, hướng, vận tốc) từ
segment. Nếu segment rỗng, nó dự đoán từ lịch sử. Một `existence_probability` tăng/giảm theo việc
có thấy hay không, và quyết định object có được xuất ra không.

Nói cách khác: **đây là mô hình "cảm biến có thấy vật này không"**, không phải mô hình
"vật này là vật nào". Association được cho không.

### 7.2 Ba cờ profile quyết định hành vi

| Cờ | 0 | > 0 |
|---|---|---|
| `classification_flag` | lấy từ GT | `TYPE_UNKNOWN` |
| `orientation_flag` | lấy từ GT | từ segment điểm (**hàm rỗng — TODO**) |
| `dimension_and_position_flag` | lấy từ GT | 1/2/3/4 — các mức ước lượng khác nhau |
| `velocity_flag` | lấy từ GT | đạo hàm vị trí |
| `tracking_flag` | ideal: track mọi object GT, `p = 1` | realistic: có tăng/giảm `p` |

VLP32 đặt: `orientation_flag = 1`, `dimension_and_position_flag = 4`, `velocity_flag = 1`,
`tracking_flag = 1`.

**Nhưng `calculate_orientation_from_pcl()` là hàm rỗng:**

```cpp
void Tracking::calculate_orientation_from_pcl(Data&, DetectedMovingObject*)
{
    // TODO fill this function
}
```

Với `orientation_flag = 1`, hướng **không được ước lượng từ điểm** và cũng **không** được copy từ
GT (vì nhánh GT nằm trong `if (dimension_and_position_flag > 0)`). Kết quả: `orientation` giữ giá
trị mặc định 0. Đây là **bug thật** trong repo, không phải chỗ ta đọc sai. Cần biết nếu ai định
dùng output của tracking làm reference.

### 7.3 Bốn mức ước lượng kích thước/vị trí

```cpp
// luôn trước hết: hộp bao của segment trong hệ toạ độ VẬT THỂ (dùng orientation GT)
pcl_segment_dimension = (x_max−x_min, y_max−y_min, z_max−z_min)
pcl_segment_position  = tâm hộp bao

case 1: dùng nguyên
case 2: eliminate_ground_clearance() + calculate_dimension_with_lower_bounds()
case 3: eliminate_ground_clearance() + set_object_dimension_with_tracking()
case 4: eliminate_ground_clearance() + lower_bounds + historical mean
```

`eliminate_ground_clearance()` — nếu hộp bao điểm thấp hơn hộp GT, kéo đáy xuống mặt đường:

```cpp
height_diff  = H_gt − H_seg
ground_clear = z_seg + height_diff/2          // khoảng hở dưới
H_new        = H_seg + ground_clear
z_new        = z_seg − ground_clear/2
```

`calculate_dimension_with_lower_bounds()` — nếu segment nhỏ hơn `minimum_object_dimension`
(VLP32: 0,8 × 0,5 × 2,0 m), nới ra và dịch tâm để giữ nguyên một phía.

`set_object_dimension_with_tracking()` — trung bình cộng với `historical_limit_dimension = 3`
frame trước (VLP32).

`calculate_velocity_as_derivation_of_position()` — hiệu vị trí chia `counter × Δt`, `counter` tối
đa `historical_limit_velocity = 10`.

### 7.4 Máy trạng thái `existence_probability`

```cpp
// đang track (p >= threshold ở frame trước):
có điểm:  p += increment (0.2)
không điểm: p -= decrement (0.055)
            nếu p >= threshold (0.5): giữ candidate cũ, vẫn xuất
            ngược lại: age = 0 (track chết)

// chưa track:
có điểm và (size > min_detections(3) hoặc |v_gt| > 0):  p += increment
    nếu p >= threshold: age = 1
không:  p -= decrement
```

`write_data_back_to_osi()` chỉ ghi ra object có `p >= 0.5`.

Nhớ hai điều: (a) `p` tăng 0,2 / giảm 0,055 ⇒ cần **3 frame** để vào track (0,2 → 0,4 → 0,6) và
**~10 frame** để rơi khỏi track từ 1,0. (b) Điều kiện `|| |v_gt| > 0` nghĩa là **vật đang di
chuyển chỉ cần 1 điểm** là bắt đầu track, bất kể `min_detections_in_segment_for_tracking = 3`.

### 7.5 Vì sao không port được

Tracker này **giả định có GT và giả định association đã xong**. Nó không phát hiện gì cả. Port nó
vào dự án BEVFusion là thay detector bằng một bảng tra GT. Không dùng được.

Cái **dùng được** là ý tưởng: `existence_probability` như một bộ lọc thời gian cho FP/frame. Nếu
sau này ta muốn giảm FP bằng cách lọc theo thời gian (một hộp giả xuất hiện 1 frame thì bỏ), thì
cơ chế `increment/decrement/threshold` ở đây là một thiết kế tham khảo hợp lý. Nhưng nó **không**
nằm trong phạm vi hiện tại của dự án.

---

## 8. ⑥ Các strategy xuất file

Bốn nhóm, mỗi nhóm có file `*_output_sequence.conf` riêng, chỉ được biên dịch nếu file đó không
rỗng và (với ROS) nếu `CMAKE_SYSTEM_NAME` là Linux:

| Nhóm | Strategy | Ra gì |
|---|---|---|
| `csv` | `CsvOutputDetections`, `CsvOutputLogicalDetections`, `CsvOutputDetectedObjects`, `CsvOutputGTObjects` | `.csv` |
| `pcd` | `PcdOutputDetections`, `PcdOutputLogicalDetections` | `.pcd` ASCII |
| `bin` | `OSIBinSensorDataOutput`, `OSIBinSensorViewOutput` | `.osi` protobuf thô |
| `ros` | 4 strategy ROS | topic ROS — **`ros_output_sequence.conf` rỗng** |

`PcdOutputDetections` ghi PCD ASCII với `FIELDS x y z intensity`, một file mỗi timestamp
(`Detections_<timestamp>.pcd`), và **mở/đóng file cho từng điểm** (`write_2_pcd` mở `fstream` mỗi
lần gọi). Đây là lý do nó chậm; không phải chỗ cần học.

Điểm đáng biết: `CsvOutputDetections::apply` có một nhánh bug — khi `detection.has_echo_pulse_width()`
nó gọi `write_data_to_csv(file_path_detections + "\\Detections.csv", ...)` với dấu `\\` hard-code
kiểu Windows, trong khi nhánh `has_intensity()` dùng `file_path_detections` trực tiếp. Trên Linux
đường dẫn đó sẽ là tên file có backslash.

---

## 9. Transformation Functions — hình học dùng chung

`strategies/transformation-functions/TransformationFunctions.{hpp,cpp}` (82 + 296 dòng). Dùng Eigen.
Các hàm chính:

| Hàm | Việc |
|---|---|
| `calc_rotation_matrix_from_euler_angles` / ngược | Euler (roll, pitch, yaw) ↔ ma trận 3×3 |
| `transform_to_local_coordinates` / `from_local` | xoay + tịnh tiến |
| `transform_position_from_world_to_ego_coordinates` | world → ego (dùng `ego_base`) |
| `transform_position_from_world_to_sensor_coordinates` | world → sensor (ego + mounting) |
| `transform_position_from_object_to_world_coordinates` | object → world (dùng `BaseMoving`) |
| `transform_cartesian_to_spherical` / ngược | Descartes ↔ cầu |
| `get_ego_info` | tìm ego trong `moving_object` theo `host_vehicle_id` |
| `vector_translation`, `get_vector_abs`, `dot_product`, `cross_product` | tiện ích |

`get_ego_info` là hàm mà **mọi** strategy gọi đầu tiên. Nó trả `false` nếu không có
`host_vehicle_id`, hoặc ego không nằm trong `moving_object`, hoặc ego không có `base`. Ba strategy
lõi (environmental, segmentation, tracking) đều `alert(...)` khi nó fail — nhưng **không `return`**
trong environmental effects, nên code tiếp tục với `ego_data` rỗng. Đây là một chỗ dễ crash.

---

## 10. CI và "credibility assessment"

Repo dùng pipeline SETLevel chia hai cấp:

**CL0** (`cl0.yml`): build + SPDX license check.
**CL1** (`cl1.yml`): build → artifact FMU → **FMU Compliance Checker** (modelica-tools) →
**FMPy validate** → C++ linter (`clang-tidy` với `.clang-tidy`) → markdown linter →
**SRMD validator** → unit tests.

`unit-tests.yml` có một chi tiết đáng chú ý: bước đầu là `andstor/file-existence-action` kiểm tra
`test/unit`. **Repo này không có thư mục `test/`.** Nên toàn bộ job unit-test bị `if:` bỏ qua và
job "xanh" mà không chạy test nào. Đây đúng là cái bẫy số 2 trong `HANDOFF.md` của dự án ta:
"Tin marker xanh một mình — `E2E_OK` từng xanh giả vì 4 test bị skip." Cùng một loại lỗi, ở một
repo khác.

`.clang-tidy` bật `readability-*` + `cppcoreguidelines-*` nhưng tắt `*-magic-numbers`, và
`HeaderFilterRegex` trỏ vào `.*/src/(?:adp|build_system|legacy)/.*` — **các thư mục không tồn
tại** trong repo này. Nghĩa là linter thực tế không kiểm tra file nào.

---

## 11. Giá trị tham số spray — bảng đầy đủ

Từ `strategies/lidar-environmental-effects-strategy/profile_VLP32.hpp.in`:

| Tham số | Giá trị | Ý nghĩa |
|---|---:|---|
| `calibrated_spray` | true | chỉ VLP32 |
| `distance_distr_in_cluster_mu` | −2.3 | log-median của **P_det** = 0,10 |
| `distance_distr_in_cluster_sigma` | 1.1 | log-sigma của P_det |
| `mean_attenuation_in_cluster` | 0.02 | σ m⁻¹, dùng trong `exp(−2σL)` |
| `std_attenuation_in_cluster` | 2.85e−7 | nhiễu trên **công suất** (mW), không phải intensity |
| `num_clusters_wfh_factor` | 0.2 | hệ số wfh trong số cụm |
| `num_clusters_wfh_offset` | 0.1 | offset trong số cụm |
| `num_clusters_velocity_offset_kmh` | 50.0 | offset tốc độ trong số cụm |
| `cluster_radius_dist_mu` | −1.2 | log-median bán kính = 0,301 m |
| `cluster_radius_dist_sigma` | 0.8 | log-sigma bán kính |

Hard-code trong code, **không** trong profile:

| Giá trị | Vị trí | Ghi chú |
|---|---|---|
| ngưỡng 40 km/h | `DetectionEnvironmentalEffects.hpp` `SprayProfile` | `[CODE]` |
| `std_time_constant = 0.2` | `SprayProfile` | `[CODE]` |
| `volume.width = 3.4`, `height = 1.5` | `define_spray_volumes` | magic number |
| `vz += 5·U(0,1)` | `append_spray_cluster` | paper **không có** |
| `drag ~ N(−0.12, 0.04)` | `append_spray_cluster` | paper: −0.15 hằng số |
| `wind = 2 m/s từ 208°` | `update_spray_cluster` | `[CODE]` |
| `v_air = wind + v` | `update_spray_cluster` | dấu **sai** về vật lý |
| `age > 4T` để xoá | `update_spray_cluster` | `[CODE]` |
| `radius = min(1.0, …)` | `append_spray_cluster` | chặn trên |
| `distance ~ N(center, L/6)` | `add_spray_detections` | xấp xỉ |
| `intensity ~ N(0.5, 0.05)/255×100` | `add_spray_detections` | **chỉ xếp hạng** |
| `attenuation = 0.02` (tham số hàm) | `add_spray_detections` | trùng `mean_attenuation` |
| `y ∈ (2, 7) m` | `simulate_wet_pavement` | cửa sổ làn bên |
| `pavement_depth = 0.0005 m` | `simulate_wet_pavement` | |
| `n_air = 1.0003`, `n_w = 1.33` | `simulate_wet_pavement` | |
| `× 0.3` cuối | `simulate_wet_pavement` | hệ số giảm |
| `+ 2/255×100` nhánh else | `simulate_wet_pavement` | tăng nhẹ, không lý do |

---

## 12. Đối chiếu với dự án này — cái gì port, cái gì không

| Thành phần | Trong sl-1-2 | Trong dự án này | Trạng thái |
|---|---|---|---|
| Ngưỡng kích hoạt 40 km/h | `SprayProfile` | `plume_state.ACTIVATION_SPEED_KMH = 40.0` | ✅ port |
| Số cụm `(0.2·wfh+0.1)·(v−50)` | `append_spray_cluster` | **bỏ** — thay bảng `_CLUSTER_VISIBLE_BY_SPEED` `[ĐO]` | ⚠️ cố ý khác |
| `T = 0.02·wfh·(v−50)+0.2` | `append_spray_cluster` | `plume_state` `LIFETIME_*` | ✅ port |
| `age = −Δt` khi sinh | `append_spray_cluster` | `plume_state` | ✅ port |
| `age > 4T` để xoá | `update_spray_cluster` | `MAX_AGE_FACTOR = 4.0` | ✅ port |
| bán kính lognormal(−1.2, 0.8), max 1,0 | `append_spray_cluster` | `RADIUS_*` | ✅ port |
| `vz += 5·U(0,1)` | `append_spray_cluster` | `INITIAL_VZ_MAX_MPS = 0.0` | ❌ theo paper |
| `drag ~ N(−0.12, 0.04)` | `append_spray_cluster` | `DRAG_MEAN = −0.15`, `DRAG_STD = 0` | ❌ theo paper |
| `v_air = wind + v` | `update_spray_cluster` | `v_air = v − wind` | ❌ sửa dấu |
| gió 2 m/s từ 208° | `update_spray_cluster` | `WIND_SPEED_MPS = 2.0`, `WIND_FROM_DEG = 208` | ✅ port |
| `P_det = min(1, lognormal(−2.3, 1.1))` | `add_spray_detections` | `raycast.PAPER_P_DET_*` | ✅ port |
| `× exp(−age/T)` | `add_spray_detections` | `raycast` | ✅ port |
| `att = exp(−2σL)` | `add_spray_detections` | `raycast.mean_attenuation_per_m = 0.02` | ✅ port |
| intensity spray = 0 | paper, code dùng N(0.5,0.05) để xếp hạng | `raycast.min_intensity = 0.0` | ✅ port |
| `add_max_detection` (1 echo/beam) | `add_max_detection` | `raycast` có port, **chưa nối** | ⏸ chưa dùng |
| mặt đường ướt | `simulate_wet_pavement` | `wet_ground.py` | ✅ port, **mặc định tắt** |
| segmentation theo box GT | `Segmentation.cpp` | — | ❌ không port (sẽ cho model biết đáp án) |
| tracking giả lập | `Tracking.cpp` | — | ❌ không port (giả định association đã xong) |
| detection sensing | `DetectionSensing.cpp` | — | ❌ không port (cần reflection từ ray-tracer) |
| OSMP/FMI | `FrameworkPackaging.cpp` | — | ❌ không liên quan |

### 12.1 Ba điều rút ra cho dự án

**1. Code tham chiếu không phải paper.** Nó lệch paper ở bốn chỗ có ý nghĩa: số cụm (4–6×), `vz`,
drag, và dấu `v_air`. Dự án đã chọn theo paper ở cả bốn. Điều đó **đúng**, nhưng nghĩa là mọi
câu "theo Linnhoff et al." trong báo cáo phải nói rõ **theo paper hay theo code**. Nếu kết quả âm,
không được kết luận "paper sai" — chỉ được kết luận "cách hiện thực này không chuyển được".

**2. Mô hình spray của sl-1-2 là mô hình *detection*, không phải mô hình *điểm*.** Nó thay echo
trên mỗi beam, không thêm điểm. SemanticSpray++ có point cloud nhiều điểm/beam. Vì vậy
`raycast.py` (port `add_max_detection`) là một module **khác bản chất** với `plume.py` (sinh
điểm). Hiện `raycast.py` chưa nối vào pipeline — đó là một quyết định còn treo, và tài liệu này
cho thấy hai lựa chọn đó không phải "chi tiết kỹ thuật" mà là hai **mô hình khác nhau**.

**3. Không tái lập được là thuộc tính của sl-1-2, không phải của ta.** `std::random_device` ở
nhiều chỗ ⇒ hai lần chạy FMU cho hai kết quả. Nếu ai định dùng FMU làm oracle cho test, phải biết
trước. Ngược lại, generator của ta seed tất định (`seed_for`) — đó là một điểm mạnh cần giữ.

---

## 13. Đọc thêm

| Muốn hiểu | Đọc |
|---|---|
| Kiến trúc OSMP/FMI | `src/osmp/FrameworkPackaging.cpp`, `src/osmp/modelDescription.in.xml` |
| Cơ chế profile | `src/model/CMakeLists.txt` (macro `add_profile_part`), `src/model/profiles/profile.hpp.in` |
| Tín hiệu lidar | `strategies/lidar-detection-sensing-strategy/src/DetectionSensing.cpp` |
| ★ Spray | `strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp:179-301, 394-450, 487-620, 734-790` |
| Mặt đường ướt | cùng file, `:303-380` |
| Tracker | `strategies/lidar-tracking-strategy/src/Tracking.cpp` |
| Paper spray | Linnhoff et al., *Simulating Road Spray in Lidar Sensor Models*, IEEE Sensors J. 2022 (arXiv 2212.08558) |
| Paper môi trường | Linnhoff et al., *Measuring the Influence of Environmental Conditions on Automotive Lidar Sensors*, MDPI Sensors 22(14):5266, 2022 |
| Paper chuỗi | Rosenberger et al., *Sequential lidar sensor system simulation*, Automotive and Engine Technology 5(3-4):187–197, 2020 |
| Paper wet pavement | Hahner et al. 2022 — dùng trong `simulate_wet_pavement`, eq. 12–19 |

Trong repo này: `docs/reference/paper-qa-notebooklm.md` (hỏi đáp nguyên văn với paper spray),
`docs/measurements/sspp-plume-probe.md` (đo thật vs generator), `spray/plume_state.py` (docstring
đầu file là bản đồ provenance đầy đủ nhất).
