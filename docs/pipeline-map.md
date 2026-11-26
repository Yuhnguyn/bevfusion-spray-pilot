# Bản đồ công thức pipeline spray chuẩn

> Bản đồ graph tương tác: [`docs/pipeline-graph.html`](pipeline-graph.html) — rebuild bằng `python scripts/build_pipeline_graph.py`.

> Phạm vi: đường chạy chuẩn `PlumeTransform` trong code hiện tại. Trang này lần theo dữ liệu đầu vào và các bước mô phỏng spray; không mô tả huấn luyện detector. Khi code và tài liệu cũ khác nhau, lấy code được liên kết dưới đây làm chuẩn.

## Luồng tổng quát

```text
results: points + gt_bboxes_3d + plume_context
  → PlumeTransform.__call__
  → inject_plume_stateful
      → (nếu bật) apply_wet_ground (nhánh hiện không đổi points_clean)
      → advance cụm đang sống
      → prune cụm đã tan
      → warm_start khi bắt đầu cảnh
      → spawn cụm mới phía sau xe
  → raycast_frame(points_clean, state.select_alive())
      → tia cắt cầu bụi? → xác suất phản hồi → suy hao / giữ echo mạnh nhất
  → points = raycast.real_points + raycast.detections
```

`PlumeTransform` là điểm vào của đường chuẩn. Nó cần `points` dạng N×5, hộp xe trong `gt_bboxes_3d`, và một `PlumeContext`. Thiếu context thì transform báo lỗi, không tự chuyển sang đường khác. Xem [`PlumeTransform.__call__`](../spray/plume_transform.py#L85).

Transform không tự đọc nhãn từng điểm và không tự bỏ `label == 2`; caller phải đưa đúng point cloud vào. `points_clean` ở đây có nghĩa là bản sao điểm đầu vào trước raycast, không đồng nghĩa với “đã lọc spray theo nhãn”.

## 1. Hợp đồng dữ liệu đầu vào

| Cần tra cứu | File / hàm | Ý nghĩa |
|---|---|---|
| Dữ liệu của một frame | [`PlumeTransform.__call__`](../spray/plume_transform.py#L85) | Điểm LiDAR `points (N,5)`, hộp `gt_bboxes_3d (M,≥9)`, metadata/seed và `plume_context`. |
| Trường context | [`PlumeContext`](../spray/plume_context.py#L24) | Cảnh, frame, epoch, gốc cảm biến, tốc độ ego/vật thể, độ ướt và cao độ mặt đường. |
| Tái lập ngẫu nhiên | [`seed_for`](../spray/plume_context.py#L204) | Tạo seed ổn định theo cảnh, frame, epoch và seed gốc. |
| Cách dựng context trong SSPP evaluator | [`build_context`](../scripts/sspp_infer.py#L492) | Nguồn tốc độ, mặt đường và vận tốc tương đối xe dẫn. Đây là caller của evaluator, không phải transform tự đọc dataset. |

Hộp theo adapter SSPP có thứ tự `[x, y, z_đáy, dài, rộng, cao, yaw, vx, vy]`; công thức chuyển hộp ở [`read_frame_boxes`](../spray/sspp_adapter.py#L90) và đóng gói mảng ở [`_boxes_to_arrays`](../spray/sspp_adapter.py#L128). Đường chuẩn generic không tự chuyển hộp: nó nhận hộp đã được pipeline phía trước chuẩn bị.

## 2. Mức ướt mặt đường (tuỳ chọn)

`inject_plume_stateful()` chỉ gọi `apply_wet_ground()` nếu caller truyền cấu hình bật. Hàm ở [`spray/wet_ground.py`](../spray/wet_ground.py#L140); cấu hình mặc định trong `PlumeTransform` là `wet_ground=None`. Khi bật, generator hiện chỉ giữ `wet_stats`; raycast vẫn nhận `points_clean`, nên bước này không đổi điểm đầu ra.

> Cần phân biệt: code có phép mô phỏng mặt đường ướt, nhưng điều đó không có nghĩa mọi lần chạy `PlumeTransform` đều áp dụng nó.

## 3. Chu kỳ cụm: cũ trước, mới sau

Điểm vào generator là [`inject_plume_stateful`](../spray/plume.py#L307). Mỗi frame, generator cập nhật các cụm đã có bằng `state.advance(dt, ego_velocity=...)`, rồi gọi `state.prune(...)`; rồi mới lấy mức ướt, warm-start nếu sang cảnh mới và sinh cụm của frame hiện tại. Chu kỳ mặc định `Δt = 0,1 s` được khai báo tại [`_UPDATE_CYCLE_TIME_S`](../spray/plume.py#L69).

### 3a. Tuổi thọ trung bình (T)

\[
T = 0{,}02\,wfh_{mm}\,(v_{km/h}-50)+0{,}2\quad [s]
\]

Hàm [`lifetime_mean_s`](../spray/plume_state.py#L260); hệ số được khai báo ở [`LIFETIME_WFH_COEFF`, `LIFETIME_BASE_S`](../spray/plume_state.py#L62). `wfh_mm` là màng nước tính bằng milimét; `v` là tốc độ xe dẫn tính bằng km/h. Đây là công thức port từ mã tham chiếu. Trong cấu hình hiện tại `lifetime_sigma_s=0`, vì vậy `ttl=T` (không bốc nhiễu quanh T).

### 3b. Hệ số tích lũy (K) và nhịp sinh

Xác suất một cụm sống thêm một bước:

\[
p=e^{-\Delta t/T}
\]

Các lứa cũ đóng góp (1,p,p^2,\ldots) cụm trung bình, do đó:

\[
K=1+p+p^2+\cdots=\frac{1}{1-e^{-\Delta t/T}}
\]

Hàm [`steady_state_factor`](../spray/plume.py#L256). Bảng calibration chứa số cụm nhìn thấy mỗi frame; nhịp sinh là `visible_ref / K`, trong [`cluster_rate_for_speed`](../spray/plume.py#L181). Bảng theo tốc độ/loại xe là [`_CLUSTER_VISIBLE_BY_SPEED`](../spray/plume.py#L26), giá trị là số đo RoadSpray static; các mốc giữa được nội suy.

### 3c. Vị trí vùng sinh

Trong [`inject_plume_stateful`](../spray/plume.py#L307), hộp xe xác định đuôi xe theo hướng `yaw`; vùng sinh là tấm ngay sau đuôi:

\[
L=|v_{object}|\Delta t,\qquad W=3{,}4\,m,\qquad H=1{,}5\,m
\]

Chiều cao bắt đầu từ `road_z_m`. Kích thước cố định nằm ở [`SPAWN_BOX_WIDTH_M`, `SPAWN_BOX_HEIGHT_M`](../spray/plume.py#L63). Bài báo nói rải đều phía sau vật thể; kích thước cụ thể là từ mã tham chiếu/thiết lập repo.

## 4. Khởi động trạng thái và sinh cụm

Khi sang cảnh mới, [`needs_warm_start`](../spray/plume_state.py#L298) khiến generator gọi [`warm_start`](../spray/plume_state.py#L307): chạy các chu kỳ giả để bắt đầu với vệt bụi đã hình thành. Sau đó [`spawn`](../spray/plume_state.py#L349) cộng nhịp dạng số thực vào `_spawn_credit`, lấy phần nguyên làm số cụm khung này và giữ phần lẻ cho khung sau.

Mỗi cụm mới có vị trí rải đều trong vùng sinh, vận tốc ban đầu theo xe dẫn, `age=-dt`, bán kính log chuẩn và `ttl=T`. Công thức rải đều cùng phần lấy mẫu ở [`spawn`](../spray/plume_state.py#L349).

Bán kính lấy theo phân bố log chuẩn của paper, với trung vị đo/đặt cho repo là 0,31 m, độ lệch log `σ=0,72`, rồi chặn trên ở 2 m:

\[r=\min(2{,}0,\ 0{,}31\,e^{0{,}72Z}),\qquad Z\sim\mathcal N(0,1)\]

Các tham số tại [`PlumeStateConfig`](../spray/plume_state.py#L117), phép lấy mẫu trong [`PlumeState.spawn`](../spray/plume_state.py#L349). Bài báo đưa phân bố log chuẩn; trung vị 0,31 m và chặn 2 m là cấu hình/đo đạc của repo.

## 5. Trôi cụm: gió, lực cản, vị trí

### Gió

\[
v_{wind,x}=-s\sin(\theta_{from}),\qquad
v_{wind,y}=-s\cos(\theta_{from}),\qquad v_{wind,z}=0
\]

[`wind_vector`](../spray/plume_state.py#L268). Mặc định `s=2 m/s`, gió từ `208°`; quy ước khí tượng đảo hướng “from” thành hướng gió thổi tới. Hằng số ở [`WIND_SPEED_MPS`, `WIND_FROM_DEG`](../spray/plume_state.py#L108).

### Lực cản và cập nhật vị trí

Vận tốc tương đối với không khí: \(\mathbf v_{air}=\mathbf v_{cluster}-\mathbf v_{wind}\). Với \(u=\|\mathbf v_{air}\|\), bước cập nhật rời rạc là:

\[
\mathbf v'_{cluster}=\mathbf v_{cluster}+C\,\frac{\mathbf v_{air}}{u}\,u^2\Delta t,
\qquad C=-0{,}15\;m^{-1}
\]

Sau đó đổi vị trí trong hệ gắn với xe cảm biến:

\[
\mathbf p'_{ego}=\mathbf p_{ego}+(\mathbf v'_{cluster}-\mathbf v_{ego})\Delta t
\]

Cả hai công thức nằm trong [`PlumeState.advance`](../spray/plume_state.py#L491), phép tính vận tốc tương đối và lực cản ở dòng 546–556, vị trí ở dòng 557–559. Hệ số `C` theo bài báo; quy ước hai hệ tọa độ và việc trừ vận tốc ego là triển khai của repo.

### Cụm tan — `prune()`

[`PlumeState.prune`](../spray/plume_state.py#L530) gieo một số ngẫu nhiên cho mỗi cụm ở mỗi chu kỳ:

\[
P_{survive}=e^{-\Delta t/ttl},\qquad P_{expire}=1-P_{survive}
\]

Số ngẫu nhiên nhỏ hơn `P_survive` thì giữ cụm; ngược lại loại cụm. Tuổi lớn hơn `12×ttl` bị loại để chặn phần đuôi xác suất gần bằng 0 (dòng 603–619). Luật mũ là [PAPER] Eq. 1; ngưỡng `12×ttl` chỉ là chốt tính toán.

## 6. Tia LiDAR và phản hồi spray

### Lưới tia và giao cầu

[`load_beam_table`](../spray/beam_model.py#L55) tạo lưới góc tia; [`build_beams`](../spray/beam_model.py#L75) đổi góc thành vectơ hướng. Mỗi tia \(t\mathbf d\) cắt cầu tâm \(\mathbf c\), bán kính \(r\), bằng cách giải:

\[
\|t\mathbf d-\mathbf c\|^2=r^2
\]

[`ray_sphere_intersect`](../spray/beam_model.py#L157) giải phương trình bậc hai và trả khoảng cách vào/ra cầu; raycast chỉ kiểm tra những tia trong vùng góc của cầu ở [`_collect_hits`](../spray/raycast.py#L462).

### Xác suất phản hồi

Paper lấy \(P_{det,0}\) theo log chuẩn với \(\ln P_{det,0}\sim\mathcal N(-2{,}3,1{,}1^2)\); mã lấy một giá trị cho mỗi cụm, rồi dùng chung cho các tia cắt cụm. Mặc định xác suất theo cự ly tắt (`b=0`):

\[
P_{hit}=\min(1,P_{det,0}\,scale)\,P_t
\]

Mã thực thi ở [`raycast_frame`](../spray/raycast.py#L332), cấu hình paper ở [`RaycastConfig`](../spray/raycast.py#L99). Nếu biến môi trường/cấu hình bật số mũ cự ly, bổ sung \((R/25m)^b\); đây là hiệu chỉnh theo dữ liệu, không phải công thức paper.

### Suy hao và echo mạnh nhất

Với tổng chiều dài đường đi trong bụi \(L\), cường độ phản hồi suy giảm:

\[
A=e^{-2\mu L},\qquad \mu=0{,}02\;m^{-1}
\]

Áp dụng cho điểm thật phía sau bụi ở [`raycast_frame`](../spray/raycast.py#L315) và điểm spray ở dòng 350–360. Sau đó [`_keep_strongest_per_beam`](../spray/raycast.py#L600) chỉ giữ echo mạnh nhất trên từng tia; điểm bụi cường độ xuất ra là 0.

## 7. Ghép đầu ra

`PlumeTransform.__call__` raycast trên `result.points_clean` và các cụm còn trong miền (`state.select_alive()`). Hàm này lọc theo mặt cầu không gần hơn 2,5 m và tâm không xa hơn 50 m, trong [`PlumeState.select_alive`](../spray/plume_state.py#L586). Sau đó nó ghép:

\[
points_{out}=real_{remaining}+detections_{spray}
\]

Đoạn ghép ở [`spray/plume_transform.py`](../spray/plume_transform.py#L129). Generator giữ cụm ở dạng hình cầu; raycast sinh điểm phản hồi trên các tia trúng cụm.

## Bảng tra nhanh theo công thức

| Muốn tìm | Hàm | File |
|---|---|---|
| Từ tốc độ và độ ướt ra tuổi thọ (T) | `lifetime_mean_s` | [`plume_state.py`](../spray/plume_state.py#L260) |
| Từ (T,\Delta t) ra hệ số tích lũy (K) | `steady_state_factor` | [`plume.py`](../spray/plume.py#L256) |
| Nhịp sinh cụm từ số cụm mục tiêu | `cluster_rate_for_speed` | [`plume.py`](../spray/plume.py#L181) |
| Cộng phần lẻ nhịp sinh thành số nguyên cụm | `PlumeState.spawn` | [`plume_state.py`](../spray/plume_state.py#L349) |
| Gió | `wind_vector` | [`plume_state.py`](../spray/plume_state.py#L268) |
| Lực cản và cập nhật vị trí | `PlumeState.advance` | [`plume_state.py`](../spray/plume_state.py#L491) |
| Xác suất sống / tan | `PlumeState.prune` | [`plume_state.py`](../spray/plume_state.py#L530) |
| Tia cắt cầu | `ray_sphere_intersect` | [`beam_model.py`](../spray/beam_model.py#L157) |
| Xác suất echo, suy hao, occlusion | `raycast_frame` | [`raycast.py`](../spray/raycast.py#L166) |
| Ghép điểm đầu ra | `PlumeTransform.__call__` | [`plume_transform.py`](../spray/plume_transform.py#L85) |

## Cập nhật bản đồ

Khi đổi cơ chế hoặc hằng số pipeline, agent cập nhật phần bước tương ứng trong file Markdown này, kiểm tra link dòng mã và nhãn nguồn, sau đó chạy:

```sh
python scripts/render_pipeline_map.py
```

Không sửa HTML sinh ra trực tiếp. Script renderer chỉ chuyển Markdown thành HTML offline, không tải tài nguyên bên ngoài.
