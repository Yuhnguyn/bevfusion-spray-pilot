# Paper A có protocol validation nào cho kịch bản ego chạy? (đọc lại arXiv 2212.08558)

Mục đích: trả lời câu hỏi phương pháp còn lại của A3 — **calibration ở RoadSpray static (ego đỗ) nhưng
production chạy following**. Chỉ đọc paper, không đo. Nguồn: `~/.hermes/cache/scratch/spray2212.txt`
(arXiv 2212.08558v1; `L…` = dòng trong file) và `ssp2305.txt` (Paper B).

Nhãn: `[TRÍCH]` = quote nguyên văn; `[SUY LUẬN]` = suy ra, không có câu chữ tương ứng trong paper.

---
## 0. TL;DR (6 câu)
1. Paper A **fit** tham số trên calibration data set (test track, ego đỗ, 25 m cho cụm/bán kính/P_det;
   50 m cho attenuation) rồi **validate mô hình trên cùng bộ dữ liệu đó**, giữ lại các "object distances
   and values" chưa dùng để fit (Fig. 10–12: 40–50 m). Không có bộ validation độc lập cho plume.
2. Paper **không** so simulated vs measured ở kịch bản ego chạy/dynamic. Kiểm tra dynamic duy nhất là
   **end-task**: augment STF (ego chạy highway) rồi đo AP trên spray test set thật (xe bị bám theo).
3. **Không có tiền lệ "fit static → verify plume trên dynamic"**. Tiền lệ gần nhất là "fit trên chiến dịch
   calibration → verify *hữu dụng* bằng detector AP trên dữ liệu following thật" (mức task, không phải
   mức phân bố plume).
4. Paper **không** có câu nào so ảnh hưởng của cảm biến đứng yên vs chuyển động lên phân bố detection.
   Chỉ có cảnh báo near-field/resolution ở §V (`L1520-1527`) — chính là vùng rủi ro của ta.
5. Paper B **không** so spray mô phỏng với spray thật. Họ dùng spray thật (nhãn tay) để train/test
   detection; "simulated data" trong abstract là **fog simulation** (NuScenes-Fog), không phải spray.
6. ⇒ **D2-chặt một mình không đủ**: nó chỉ trả lời "tham số lấy từ đâu", không trả lời "kiểm chứng mô
   hình ở kịch bản dùng thật bằng cách nào". Phải thêm một bước verification following, pre-registered,
   không tune — đề xuất ở §6.

---
## 1. Paper A tách "calibration" và "validation" thế nào?
**Fit** — §III-A/§III-B, test-track (ego **đỗ** hoặc bám theo, 3 mức nước, Golf/Crafter):
- `[TRÍCH]` §III-A `L260-261`: *"To calibrate the model, extensive experiments are conducted to capture
  sufficient amount of reference data."*
- `[TRÍCH]` §III-A `L289-293`: *"In the first scenario, the ego vehicle is stationary on the right lane and
  an object vehicle is passing on the left lane. … In the second scenario, the ego vehicle is following the
  object vehicle with constant speed."* — paper **có thu** kịch bản following trong campaign calibration.
- `[TRÍCH]` §III-A `L298-305`: speed 50–130 km/h bước 10, *"a VW Golf representing a compact car and a VW
  Crafter as a large van"*.
- `[TRÍCH]` §III-B `L361-364`: cụm/bán kính/P_det fit ở *"An object distance of 25 m from the sensor is
  chosen, since here distinct and stable clusters are observed with high resolution in the sensor."*
  (Fig. 4 số cụm; Fig. 5 lognormal; Fig. 7 P_det tại 25 m — `L713-714`).
- `[TRÍCH]` attenuation fit bằng target 50 m: *"This value was found iteratively as an optimization to match
  the decrease in intensity on the simulated target to the measurements shown in Fig. 8."* (`L739-742`);
  Fig. 8 = *"intensities … recorded when the rear of the passing VW Crafter is next to the target"* (`L707-711`).

**Validate** — §IV-A: cùng bộ dữ liệu, giữ điều kiện **chưa dùng để fit**:
- `[TRÍCH]` §IV-A `L1043-1047`: *"To evaluate the model, object distances and values, which were not
  utilized for the model calibration, are used on the same data set. This is done to evaluate and verify
  the model and its calibration."*
- `[TRÍCH]` Fig. 10 caption `L1037-1041`: *"… the simulation of a VW Crafter passing by the stationary ego
  vehicle. … at around 40 m."* → validation qualitative ở **passing/ego đỗ**.
- `[TRÍCH]` Fig. 11 caption `L1186-1187`: *"Comparison of simulated and measured numbers of detections and
  numbers of clusters … from a Crafter at 50 m distance."*
- `[TRÍCH]` Fig. 12 caption `L1249-1250`: *"Cumulative distribution of number of detections over range in
  spray plume from a Crafter with different speeds at 50 m distance."*
- `[SUY LUẬN]` Cả 3 hình validation đều ở kịch bản **ego đỗ + xe chạy qua**: Fig. 10 ghi thẳng
  "stationary ego vehicle"; Fig. 11/12 đo ở 50 m, còn following trong campaign ở 20/30 m (metadata
  RoadSpray) ⇒ 50 m không thể là following. Split calibration↔validation là **theo distance/values
  trong cùng bộ static**, không theo scenario.

## 2. Paper có kiểm tra mô phỏng ở kịch bản EGO CHẠY không?
**Không, ở mức phân bố plume.** `[TRÍCH]` §II `L177-181`: *"… two specifically captured data sets … The
disturbance is analyzed and modeled by clustering of the point cloud in a first data set with isolated spray
effects and the overall model validation is performed using object detection algorithms on a second data
set."* — "second data set" là **spray test set 1463 frame**, kiểm tra bằng AP của detector, không phải
so point/cụm simulated-vs-real.

Dynamic chỉ có **end-task**:
- `[TRÍCH]` §III-C `L763-770`: *"a viable method to verify the realism of simulation methods is its
  application as data augmentation method for downstream object detection tasks. … the additional training
  data alone is enough to significantly improve the performance of lidar-based object detectors in
  real-world spray scenarios."*
- `[TRÍCH]` §III-C `L782-785`: augmentation chỉ áp cho STF khi *"ego-velocity exceeds 60 km/h"*, *"only
  highway and suburban scenarios"*. STF = ego **chạy**.
- `[TRÍCH]` §V-D `L833-857`: test set thu trên *"a closed highway test track"*, *"Measurement runs consist
  of following other vehicles on wet roads"*, xe bị bám *"in distances from 0-50 m"*, ego speed 80/100/120.
- `[TRÍCH]` Tab. II (`L1251-1255`, `L1074-1078`) báo AP trên **wet/watered spray test set thật** — đây là
  kiểm chứng "mô hình giúp detector" ở kịch bản following, **không** phải kiểm chứng phân bố plume.
- `[SUY LUẬN]` Không có hình/bảng nào so **số điểm/cụm/phân bố range của plume simulated** với plume
  thật khi ego chạy.

## 3. Có tiền lệ "fit static → verify dynamic" không?
- **Mức plume: KHÔNG.** Toàn bộ validation phân bố (Fig. 10–12) nằm trong bộ static, ego đỗ.
- **Mức task: CÓ, khác bậc.** Fit trên calibration static → augment STF (ego chạy) → verify bằng AP trên
  spray test set thật (following). Chuỗi này chỉ chấp nhận chuyển kịch bản ở mức "mô hình có ích cho
  detector", không chứng minh phân bố plume đúng trong following.
- `[SUY LUẬN]` Protocol repo **không sai hướng** (paper cũng chuyển static→dynamic để đánh giá hữu dụng)
  nhưng **thiếu bước** kiểm chứng *phân bố plume* ở following — paper không làm, ta phải tự định nghĩa.

## 4. Paper có nói gì về cảm biến đứng yên vs chuyển động (góc khối, near-field)?
`[TRÍCH]` Không có câu trực tiếp. Các câu gần nhất:
- `L1520-1527` (§V): *"with higher resolutions, a problem with the spherical cluster representation might
  appear. The problem can become especially pronounced in close proximity to the sensor and is to be
  evaluated in future work."*
- `L366-368` (§III-B): DBSCAN chạy trong *"spherical coordinates to account for the change in Cartesian
  resolution over distance"* — resolution theo cự ly, không theo chuyển động ego.
- `L835-838` (§V-D): dùng *"the same acquisition vehicle as for the STF data set … differences regarding
  sensor makes and mounting positions … eliminated"* — paper coi **cấu hình cảm biến** là biến quan
  trọng, nhưng không nói ego motion.
- `L788-796` (§III-C): model cần *"trajectories of the ego vehicle and all surrounding vehicles"* —
  ego motion được đưa vào qua trajectory/world frame.
`[SUY LUẬN]` Hệ quả: paper **không có cơ sở lý thuyết** cho việc phân bố góc/near-field đo khi ego đỗ
truyền nguyên sang ego chạy; đây là giả định của ta, phải kiểm chứng bằng số. Câu `L1520-1527` còn cảnh
báo đúng vùng near-field (<10 m) — nơi kịch bản following tạo nhiều detection hơn.

## 5. Paper B (SemanticSpray++) có so spray mô phỏng với thật không?
`[TRÍCH]` **Không.** Paper B dùng spray **thật** để train/test:
- `L605-617`: *"The data is based on the recently released RoadSpray [3] dataset … To create the
  SemanticSpray dataset, we manually label each point … background, vehicle, and spray."*
- `L643-646`: *"We use 7898 scans for training and 8667 for testing."*
- "simulated" trong Paper B chỉ là **fog simulation**: `L94-97` *"we show that our method performs better
  … on real and simulated data"*; `L1017-1018` *"form well when training and testing with simulated fog
  data (NuScenes-Fog)"*. Không có spray simulation, không so simulated spray vs real spray.
`[SUY LUẬN]` ⇒ Paper B chỉ cung cấp **nhãn thật** làm ground truth, không có protocol validation generator.

---
## 6. Hệ quả cho protocol của repo (đề xuất bổ sung vào ADR-0006)
**[SUY LUẬN] Kết luận: D2-chặt là điều kiện cần, không đủ.** D2 chỉ ràng buộc *nguồn tham số* (RoadSpray
static + paper; SSPP để kiểm chứng). Nó không quy định *cách kiểm chứng mô hình ở kịch bản production*.
Paper cũng không có protocol đó (chỉ có validation static + end-task AP), nên ta phải viết protocol riêng.

**Đề xuất "A3-V — following-scenario verification" (pre-registered, một lần, không tune):**
1. **Dữ liệu**: các scene SSPP **không có human box** (171 scene; D1 eval chỉ 36 scene có box); chưa bao
   giờ nằm trong eval ⇒ hợp lệ để **kiểm chứng** theo ADR-0006 ("SSPP chỉ để báo cáo/kiểm chứng"). Chọn
   ≥20–30 scene/nhóm tốc độ, cả Crafter/Golf.
2. **Dựng điều kiện following**: lấy `ego_speed`/`object_velocity`/`distance_to_object` từ
   `metadata.txt`, đặt box xe dẫn đúng distance/class (20/30 m), `road_z` từ RANSAC; chạy **đúng
   production path** `inject_plume_stateful` + `raycast_frame(load_beam_table())`, seed theo frame (paired).
3. **Đại lượng pre-register**: chính = **tỉ lệ det/frame sinh ÷ det/frame thật `label == 2`** trong vùng
   sau box xe dẫn 0–60 m (mask ±5 m, 0–3 m), median + CI95 bootstrap **theo scene**; phụ = depth profile
   2 m/bin, % near-field <10 m và <4 m, phân bố điểm/cụm.
4. **Ngưỡng pass/fail ghi vào ADR trước khi đo** (ví dụ [0,5; 2,0] và CI không vắt qua biên); **cấm tune
   sau khi thấy kết quả** — fail thì mở lại ADR, không sửa generator để pass.
5. **Caveat**: (a) SSPP `label == 2` gồm cả spray của ego/nguồn khác ⇒ giới hạn vùng sau xe dẫn,
   range > ~10 m; (b) SSPP là **dynamic subset của RoadSpray** (cùng campaign/rig với static) ⇒
   consistency check, **không** phải out-of-distribution; (c) không dùng 36 scene eval.

**171 scene có "tương đương paper" không?** `[SUY LUẬN]` **Không tương đương, nhưng mạnh hơn ở điểm
paper thiếu**: paper validate phân bố plume chỉ trên static + validate hữu dụng bằng AP trên following
thật; hướng 171 scene kiểm tra **phân bố plume trong following trên dữ liệu thật ngoài eval**. Vì paper
không có bước này, đây là protocol **riêng của repo**, ghi `[CHỌN]`, không được trình bày như "paper
nói". Hợp lệ vì (i) không dùng chọn tham số, (ii) tách eval, (iii) pre-registered. Muốn bám paper sát hơn
thì thêm tầng end-task AP — nhưng đó là cổng C, không phải A3.

---
## 7. Nguồn
- Paper A: arXiv 2212.08558v1, local `~/.hermes/cache/scratch/spray2212.txt` (dòng trích ở trên).
- Paper B: arXiv 2305.16129v3, local `~/.hermes/cache/scratch/ssp2305.txt`.
- ADR-0006 (`docs/adr/0006-…`): D1 36 scene, D2 nguồn calibration, D4 pseudo-box, §5.6 khoảng trống.
- `docs/measurements/roadspray-static-depth-profile.md` (T4: trail90/depth profile) và
  `docs/measurements/a3-parameter-provenance.md` (nguồn tham số; không có dòng paper nào về validation following).
