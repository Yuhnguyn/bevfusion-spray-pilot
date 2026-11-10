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