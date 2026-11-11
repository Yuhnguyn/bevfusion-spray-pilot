# Hỏi đáp paper qua NotebookLM — Linnhoff et al. 2212.08558

Nguồn: notebook `Mô Phỏng Hiệu Ứng Bụi Nước Trên Cảm Biến Lidar Ô Tô`
(id `f2c09ee8-1c5c-45d3-869d-e62559073f1c`), source duy nhất là PDF arXiv
2212.08558. Câu hỏi soạn theo 5 nhóm, chỉ thị bắt buộc trả lời nguyên văn +
số hiệu mục/hình, và trả lời đúng chữ `NOT STATED IN PAPER` khi paper không nói.

Mục đích: tách **cái paper thật sự nói** khỏi **cái code tham chiếu
(`dee.cpp`) tự đặt**, để mọi tham số của generator v2 có nguồn rõ ràng.

---

## 1. Vùng đặt cụm (spray region)

| Câu hỏi | Kết quả | Trích dẫn / vị trí |
|---|---|---|
| Kích thước vùng có trong paper? | **KHÔNG** | §III-B: chỉ nói "region behind every moving object" |
| Điểm neo? | Không nêu cản sau/tâm/cảm biến, nhưng có ràng buộc mạnh hơn | *"The initialization of clusters is restricted to the vehicle trajectory and no clusters are spawned randomly in the scene."* (§III) |
| Chiều cao / độ cao thẳng đứng? | **KHÔNG** | `NOT STATED IN PAPER`; §V chỉ nói cần nghiên cứu thêm lốp và tải |
| Chiều rộng 3,4 m, dài `v·Δt`? | **KHÔNG** | chỉ có trong `dee.cpp:559-561` |
| Ai sinh spray? | **ego + mọi vật thể di chuyển** | *"The model requires knowledge of the trajectories of the ego vehicle and all surrounding vehicles that cause spray."* (§III-3); *"spray clusters are generated for each individual moving object in the scene, there is no interaction"* (§V) |

Fig. 3b: hộp nét đứt nhãn "Spray detection filter region", vẽ **sau** xe Object,
dài cỡ 2–3 lần chiều dài xe, **không vẽ theo tỉ lệ**, không kèm số đo.

## 2. Xoá cụm / vòng đời

| Câu hỏi | Kết quả |
|---|---|
| Quy tắc xoá cụm theo tuổi/quãng đường/ra khỏi vùng | **KHÔNG có trong paper** |
| Ngưỡng `4T` | **KHÔNG có trong paper** — chỉ có ở `dee.cpp:445-450` |
| Nói gì về cụm ở sau cảm biến ego / cụm mà ego đã vượt qua | **KHÔNG có** |
| Giới hạn khoảng cách sinh detection | **KHÔNG có**; chỉ có phạm vi **đánh giá** 0–50 m (*"the test set is labeled up to 50 m"*) |

Hệ quả: "vệt plume dài" **không mâu thuẫn paper** — paper không đặt luật cắt nào.
Mọi ngưỡng cắt là quyết định của mình, phải khai báo là `[CHỌN]`.

## 3. `P_det`, eq. (7)

Trích nguyên văn: *"A beam generates only a detection in a certain cluster with a
detection probability given as `P_det = n / n_max(r_cl, p_cl)`, with the number of
detections `n` in a given cluster and the number of beams `n_max(r_cl, p_cl)`
intersecting the spherical representation of the cluster. The maximum number of
possible detections in a spherical cluster representation depends on the cluster
radius and the cluster position with respect to the beam pattern of the sensor."*

- `n` = số detection **đo được** trong cụm; `n_max` = số **tia cắt** khối cầu ⇒ **hình học**, tính được.
- `P_det` là tỉ lệ theo **cặp (tia, cụm)**: mỗi tia cắt cụm bốc Bernoulli với xác suất đó.
- Phương sai giữa các cụm đến từ **Fig. 7**: lognormal `µ = −2,3 σ = 1,09` (trung bình `e^{µ+σ²/2} ≈ 0,18`) — bốc **một lần cho mỗi cụm**, rồi áp lên từng tia.
- Kết hợp thời gian: *"As the cluster dissolves, the detection probability decreases by the time factor T introduced in equation (1)."* ⇒ `P_eff = P_det · P_t`.
- Range: *"the range is set to a normal distribution around the middle of the cluster"*.
- Intensity: *"the final intensity value of the simulated spray detections are set to 0"*; `N(0,5; 0,05)` chỉ để **so sánh giữa nhiều detection trong một tia**.

## 4. Số cụm, WFH, tham số

- Số cụm là hàm của **tốc độ vật thể** (không phải ego), class, và `wfh`: *"the number of clusters that are generated in each simulation time step are calculated as a function of the object speed, class, and water film height."*
- Cách đếm: đếm cụm thật trong "spray filter region" của **dữ liệu đo** ở khoảng cách vật thể **25 m**, rồi chia cho **tỉ lệ chiều dài vùng / quãng đường vật thể đi trong một scan**. Không có công thức in rời trong paper.
- `wfh` calibration: 0,5 / 0,75 / 1,0 mm. Augmentation: *"the water level is sampled from an **exponential distribution** from the interval 0.1 − 1.2 mm during training."*
- Augmentation **chỉ áp lên mẫu có ego-velocity > 60 km/h**.
- Cảm biến: Velodyne VLP32 trên nóc xe đo; DBSCAN `minPts = 3`, neighborhood `0,7°`, elevation discretisation `0,333°`.

## 5. Giao thức đánh giá — chống leakage

- **Ba bộ dữ liệu tách rời:** (1) calibration set có spray cô lập, vật thể ở 25 m → khớp tham số mô hình; (2) **training trên SeeingThroughFog (STF)**; (3) **spray test set riêng 1.463 frame**, 6 kịch bản (Table I: G-Class 79,9; Smart 118,3; CLA 97,4; Smart 97,6; CLA 121,0; CLA+2×G-Class 96,2 km/h), nhãn tới 50 m.
- *"To evaluate the model, object distances and values, which were not utilized for the model calibration, are used on the same data set."*
- Metric: KITTI eval, **AP tại 40 điểm recall**, chia dải 0–30 m và 30–50 m; detector PV-RCNN và Voxel-RCNN (OpenPCDet).
- Mô hình được đánh giá lại trên **clear-weather test set** của STF.

⇒ Paper **không** calibrate trên chính tập eval. Bản port của mình phải giữ đúng
nguyên tắc đó: tham số đo trên **train scenes**, eval trên **scene giữ riêng**.

## 6. Hạn chế tác giả tự nêu (dùng cho Limitations của luận văn)

1. Đặt cụm theo uniform là *"a first estimate"*, chưa kiểm chứng phân bố thật.
2. Gió giả định giống nhau cho mọi cụm, bỏ qua gió giật.
3. Cụm chồng lấp **không bị cấm** trong mô hình.
4. **Biểu diễn khối cầu ở khoảng cách gần: "can become especially pronounced in close proximity to the sensor"** ⇒ đúng vùng plume thật của mình (range median 3,8–9,1 m).
5. Chỉ mô hình **một echo** (single echo).
6. Không mô hình vật cản không sinh detection (gương, vật tối) ⇒ spray vẫn sinh điểm phía sau chúng.
7. Chưa có tương tác giữa các xe; mới có 2 loại vật thể; lốp và tải chưa được khảo sát.
8. Chạy tuần tự trên CPU Intel i9, không tăng tốc.

## 7. Việc mình phải tự quyết (paper không cho)

| Tham số | Trạng thái | Cách xử |
|---|---|---|
| Chiều cao vùng đặt cụm | paper NOT STATED, code `1,5 m` | đo nhãn thật: p5 0,16 / med **1,51** / p95 **2,36 m** trên mặt đường = 6 / 58 / 90 % chiều cao box 2,62 m ⇒ dùng `0,87 × chiều cao vật thể`, đáy = mặt đường + `0,05 × h` |
| Chiều rộng vùng | paper NOT STATED, code `3,4 m` | giữ, hợp lệ với `|y|` p95 thật 2,31 m; khai báo `[CODE]` |
| Chiều dài vùng | paper NOT STATED, code `v·Δt` | giữ `[CODE]` |
| Xoá cụm | paper NOT STATED, code `age > 4T` | giữ `4T` `[CODE]`, **không** thêm ngưỡng mét |
| Cụm sau cảm biến (62–93 % nhãn thật) | paper NOT STATED; paper có nói **ego cũng là nguồn spray** | quyết định: có sinh spray sau ego hay không |

## 8. Bổ sung 2026-11-11 — hỏi lại notebook cho ticket 29d/29c

Hỏi qua CLI `notebooklm -p phk4` (Edge cookies, tài khoản `huynguyen.phk4@gmail.com` — tài khoản này
là **owner** của notebook; profile `default` của `huy7a2004@gmail.com` đã hết hạn token).

### 8.1 Recipe đếm cụm — §III-B, trích nguyên văn

| Điều | Nguyên văn |
|---|---|
| Thuật toán | *"To quantify this effect, a DBSCAN algorithm is applied to the detections."* |
| Không gian | *"The DBSCAN algorithm is applied to the point cloud in spherical coordinates to account for the change in Cartesian resolution over distance."* |
| Lân cận | *"To ensure possible clustering in vertical direction, the search neighborhood of DBSCAN is set to 0.7° to cover at least two scan lines of the sensor."* |
| `minPts` | *"As small clusters are observed in the recorded data, three points is defined as the minimum number of points that can form a cluster."* |
| Độ phân giải góc | *"In the central elevation field of view, the Velodyne VLP32 has an elevation angle discretization of 0.333°."* |
| Hộp hay tròn trong mặt phẳng góc | **NOT STATED IN PAPER** |
| Lân cận có ràng buộc cả khoảng cách `r` | **NOT STATED IN PAPER** |

⇒ Toán tử của mình: DBSCAN trên `(azimuth, elevation)`, `eps = 0,7°` Euclid, elevation snap lưới
`0,333°`, `minPts = 3`, azimuth wrap modulo 360. Hai chỗ paper không nói ⇒ `[CHỌN]`.
**Toán tử `0,5 m` Euclid của `spray/spray_stats.py` KHÔNG phải recipe paper** — vẫn dùng được như số cũ
để so, nhưng không được gọi là "khớp paper".

### 8.2 Số neo để so (Fig. 1 text box, Fig. 11) — [PAPER]

| Đại lượng | Giá trị | Nguồn |
|---|---|---|
| Cụm/frame, Crafter 50 m, **100 km/h** | **33** cụm | Fig. 1 text box |
| Detections/cụm (trung bình) | **14,3** | Fig. 1 text box |
| Clustered/total | **84,1 %** | Fig. 1 text box |
| Cụm/frame @130 km/h, mặt đường ướt đẫm | **~75** đo, **~110** mô phỏng | Fig. 11b |
| Bán kính cụm `r_cl` | lognormal `µ = −1,2`, `σ = 0,8` ⇒ median **0,30 m**, mean **0,42 m** | Fig. 5, §III-B |

⚠️ **Mâu thuẫn phải sửa**: `docs/measurements/semantic-spray-stats.md` ghi **17,06 cụm/frame** và ticket 31
đang lấy số đó làm mốc "khớp Fig. 11a". Paper nói **33** cụm ở 100 km/h và **~75** ở 130 km/h. Con số
17,06 sinh ra bởi single-linkage `0,5 m` + `dense_min = 5` ⇒ đếm thiếu. Ticket 31 **không** được dùng
`17,06` làm mốc cho tới khi đo lại bằng toán tử §8.1.

### 8.3 Protocol chia dữ liệu — paper KHÔNG chia scene

| Điều | Nguyên văn |
|---|---|
| Hiệu chỉnh vs đánh giá | *"The disturbance is analyzed and modeled by clustering of the point cloud in a first data set with isolated spray effects and the overall model validation is performed using object detection algorithms on a second data set."* (§II) |
| Cách "held-out" của paper | *"To evaluate the model, object distances and values, which were not utilized for the model calibration, are used on the same data set. This is done to evaluate and verify the model and its calibration."* (§IV-1) |
| Tập kiểm thử riêng | *"the effectiveness of the spray augmentation is evaluated on a dedicated spray test set."* (§III-3) |

⇒ Paper **giữ lại điều kiện** (khoảng cách/giá trị chưa dùng khi hiệu chỉnh) **trên cùng bộ dữ liệu**,
không chia scene 1:1. Split `cal`/`held-out` của ticket 29d là quyết định riêng của mình ⇒ `[CHỌN]`,
không được trình bày như protocol của paper. Hệ quả: khi viết báo cáo, nêu rõ hai khác biệt
(1) paper giữ điều kiện, mình giữ scene; (2) paper có bộ dữ liệu thứ hai 1.463 frame, mình không có.

### 8.4 Hình học vùng spray — vẫn NOT STATED

Hỏi lại lần này: **chiều cao trên mặt đường, bề rộng ngang, chiều dài sau vật thể** — cả ba đều
**NOT STATED IN PAPER**. Fig. 1 chỉ vẽ trục `z in m` từ −2 đến 2 m, không có số đo; Fig. 3b là hộp
schematic, không có kích thước. Fig. 5 chỉ cho **bán kính cụm** (`r_cl` = khoảng cách xa nhất từ
detection tới tâm cụm), không cho kích thước vùng.

⇒ Nhãn đúng cho các giá trị đang dùng: `5–92 %` chiều cao box và `3,4 m` bề rộng là **`[ĐO]` trên
939.803 điểm nhãn thật + `[CHỌN]` khi quy ra tham số box** — **không** phải giá trị paper. Chỉ
`intensity = 0` và `P_det = n / n_max` là `[PAPER]`.

## 9. Bổ sung 2026-11-11 (đợt 2) — tuổi thọ cụm, tắt tín hiệu, số cụm theo tốc độ

### 9.1 Tuổi thọ cụm — §III-B, eq. (1)

> *"Clusters do not just disappear after a certain amount of time, but they dissolve gradually. This
> behavior is modeled by changing the detection probability of the clusters exponentially over time
> with a probability factor based on an exponential impulse response"* → `P_t(t) = exp(−t/T)`
>
> *"the time constant T is defined as the time required to reduce the detection count to 36 % of the
> maximum"*
>
> *"From Fig. 6, it becomes apparent that the time constants rise with respect to object speed, which
> is approximated by linear functions for the different watering levels."*
>
> *"The only differences between the two vehicles are the number of clusters and the dissolve time
> constant. These are set separately for the object classes."*

`T` theo Fig. 6 đọc được: `≈0,15–0,25 s` @50 km/h → `1,15 s` (ẩm) / `1,4 s` (phủ một phần) /
`1,8 s` (ướt đẫm) @130 km/h. **Ngưỡng xoá cứng: NOT STATED** ⇒ `age > 4T` vẫn là `[CODE]`.

✅ Code hiện tại: `T = 0,02·wfh·(v−50) + 0,2` cho `0,20 / 1,00 / 1,80 s` tại `50 / 130 ẩm / 130 ướt
đẫm` — **khớp paper**, không phải sửa.

### 9.2 Tắt tín hiệu do spray — §III-B "Attenuation"

> *"Since a beam intersecting with a cluster generates only a detection with a certain detection
> probability, a beam can pass multiple clusters, before generating a detection. As water in the air
> not only reflects light back to the sensor but also scatters the light, an attenuation occurs."*
>
> *"The total distance a beam traveled through multiple clusters is calculated and an attenuation is
> applied. … yields a mean extinction coefficient of **0.02 m⁻¹**."*
>
> *"If a detection existed in a beam before the spray simulation, the attenuation due to the spray is
> also applied to its intensity. In the end, the detection intensities of all detections from a beam
> are compared and the strongest is added to the overall point cloud."*

⇒ Paper **có** mô hình tắt tín hiệu thật, và giữ **một** return mạnh nhất mỗi tia. Code có
`mean_attenuation_per_m = 0,02` ✓ nhưng dùng `exp(−2·σ·L)` (khứ hồi, `[CODE]`); paper **chỉ in ra
σ**, không in dạng mũ ⇒ `NOT STATED IN PAPER`, giữ `2` và khai `[CODE]`.

### 9.3 Số cụm theo tốc độ — Fig. 11b (đọc xấp xỉ trên đồ thị, `[PAPER-graph]`)

| km/h | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ướt đẫm (1,0 mm) | 4,5 | 21 | 28,5 | 43 | 49,5 | 56,5 | **74,5** |
| Ẩm (0,5 mm) | 3,5 | 10,5 | 23,5 | 29,5 | 31 | 32,5 | **41,5** |

(Fig. 1 text box cho một frame đơn @100 km/h: **33** cụm — khác Fig. 11b vì 11b là trung bình nhiều
frame; dùng 11b để hiệu chỉnh, 1 để sanity-check bậc độ lớn.)

Quy tắc của paper, §III-B nguyên văn:

> *"The number of clusters generated within one simulation time step is determined by first counting
> the number of clusters in a spray filter region behind the vehicle. This total number is then
> divided by the length ratio of the spray region to the distance the object traveled during one scan
> of the sensor."*

Suy ngược bằng `K(T) = Σ_{k=0}^{4T/Δt} exp(−k·Δt/T)` của chính code (`plume.py`):

| km/h | K (ướt đẫm) | cụm/chu kỳ suy ra | code hiện tại | K (ẩm) | cụm/chu kỳ suy ra | code hiện tại |
|---:|---:|---:|---:|---:|---:|---:|
| 80 | 8,37 | 2,5 | 9 | 5,43 | 1,9 | 6 |
| 100 | 12,28 | 3,5 | 15 | 7,37 | 4,0 | 10 |
| 130 | 18,18 | 4,1 | 24 | 10,33 | 4,0 | 16 |

⇒ Hai kết luận:

1. **Tốc độ sinh cụm hiện tại sai 4–6×** (`(0,2·wfh+0,1)·(v−50)` [CODE, dee.cpp] cho 24/chu kỳ ở
   130 km/h ướt đẫm, paper tương ứng **~4**).
2. **Độ ẩm gần như không đổi tốc độ sinh** (`3,5–4,1` ở mọi mức ẩm khi `v ≥ 100`); độ ẩm tác động
   qua **`T`** (cụm sống lâu hơn ⇒ thấy nhiều hơn). Nhân `(0,2·wfh+0,1)` vào tốc độ sinh là **sai
   chỗ**: nó vừa thừa 4–6×, vừa gán phụ thuộc ẩm vào sai biến.
3. Đường hiệu chỉnh đơn giản khớp bảng trên: `rate(v) = min(3,8 ; 0,107·(v−60))` cụm/chu kỳ, độc lập
   `wfh`; `visible = rate × K(T(wfh, v))`.
4. Hệ quả cấu trúc: 807–1.555 điểm/frame ÷ 436 cụm ≈ **2–3,5 det/cụm**, paper là **14,3** ⇒ đang tạo
   nhiều cụm nhỏ li ti thay vì ít cụm dày. Phải hiệu chỉnh `P_det` cùng lúc với số cụm.