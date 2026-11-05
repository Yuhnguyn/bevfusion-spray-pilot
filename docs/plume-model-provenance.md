# Provenance của từng tham số `PlumeConfig`

Mục đích: mỗi con số trong `spray/plume.py` phải trả lời được "lấy từ đâu". File này là bản đồ đó.
Viết lại sau khi PM nói sai rằng "số cụm tăng theo tốc độ không có trong paper Linnhoff" — **sai**,
xem dòng 1 bảng dưới. Đừng lặp lại lỗi này.

Nguồn viết tắt: **[PAPER]** = Linnhoff et al., *Simulating Road Spray Effects in Automotive Lidar Sensor
Models*, arXiv 2212.08558 (§ và hình ghi kèm). **[ĐO]** = đo trên SemanticSpray release local
(`docs/semantic-spray-stats.md`). **[CHỌN]** = quyết định của repo, không có nguồn ngoài.

| Tham số trong code | Giá trị | Nguồn | Vị trí chính xác | Trạng thái |
|---|---|---|---|---|
| `min_speed_kmh` | 50 | [PAPER] | §III-A: spray bắt đầu ~50 km/h, khảo sát 50–130 km/h | **khớp** |
| `clusters_at_speed_bounds` | (2, 8) tuyến tính theo tốc độ | **[PAPER] về cấu trúc**, [ĐO] về hằng số | §III *Cluster Generation*: "the number of clusters that are generated in each simulation time step are calculated as a function of the object speed, class, and water film height"; Fig. 4 vẽ mean clusters/timestep + **đường tuyến tính xấp xỉ** làm expected value, đo cho VW Crafter, DBSCAN eps 0,7°, minPts 3, chuẩn hoá theo quãng đường đi được trong 1 scan | **xấp xỉ có chủ ý** — xem dưới |
| `points_per_cluster_median` | 17 (sigma 0,67; bounds 3–200) | [ĐO] | SemanticSpray: dense cluster size median 17 điểm | **thay thế** cơ chế khác (xem dưới) |
| `cluster_radius_median_m` | 0,30 (sigma 0,8) | [PAPER] | Fig. 5: lognormal μ=−1,2 σ=0,8 → median 0,30 m | **khớp** |
| vị trí cụm | sau xe dẫn đường, cách 1–10 m | [PAPER] định tính | §III: cụm đặt **uniform trong vùng sau mỗi vật thể đang di chuyển**, không spawn ngẫu nhiên trong scene | **đơn giản hoá** |
| tuổi cụm / decay | không có | [PAPER] | §III: mỗi cụm có *time since generation*, cụm tan dần; Fig. 4 có *time constant* 0,5–1,5 s | **thiếu** |
| attenuation | không có | [PAPER] | §III: 0,02 m⁻¹ | **thiếu** (ADR-0002) |
| occlusion điểm thật | không có | [PAPER] | §III: mỗi tia cộng hưởng ứng của **tất cả** cụm nó đi qua → tia thật bị yếu/che | **thiếu** (ADR-0002) |
| `P_det` per-tia | không có | [PAPER] | lognormal μ=−2,3 σ=1,09, median 0,10 | **thiếu** — repo sinh cụm trực tiếp thay vì mô phỏng tia |
| mức nước / lớp xe | không có | [PAPER] | 0,5 mm ẩm / 0,75 phủ một phần / 1,0 phủ hoàn toàn; 2 lớp xe (VW Golf, VW Crafter) | **gộp thành 1 regime** |

## Vì sao (2, 8) không phải "bịa"

Paper cho **dạng hàm** (tuyến tính theo tốc độ, tham số hoá thêm theo lớp xe và độ dày màng nước) và
**giá trị mean** đọc từ Fig. 4 trên KITTI/VLP-32C ở khoảng cách 25 m. Repo dùng đúng dạng hàm đó, nhưng
lấy hằng số neo theo dữ liệu mình có: SemanticSpray median **5 dense clusters/frame**, nên chọn 2 cụm ở
50 km/h → 8 cụm ở 130 km/h để dải giữa rơi vào ~5. Đây là **xấp xỉ có chủ ý**, không phải tham số không
nguồn — và cũng không phải "replicate Fig. 4".

Hai chiều bị gộp: **lớp xe** và **độ dày màng nước**. v1 chạy một regime duy nhất (xe cỡ trung, mặt đường
phủ nước hoàn toàn). Nếu cần đúng paper hơn thì phải tách 2×3 = 6 đường tuyến tính, và mỗi đường cần
bảng số đọc từ Fig. 4 (plot, phải số hoá).

## Vì sao `points_per_cluster` không lấy từ paper

Paper không có khái niệm "số điểm mỗi cụm": nó mô phỏng **từng tia**, mỗi tia có xác suất `P_det` sinh
detection. Số điểm/cụm là hệ quả của `P_det` × số tia cắt khối cầu. Repo sinh cụm trực tiếp nên phải
neo vào đại lượng đo được (dense cluster size median 17). Hai cách khác bản chất, không thay thế nhau
bằng một con số.

## Hệ quả cho claim

Vì thiếu attenuation + occlusion + `P_det`, repo **không tái lập** Linnhoff và **không nên** so trực tiếp
với +17,39 AP của họ. Claim đúng phạm vi: *plume augmentation calibrated theo thống kê spray đo được,
cho bài toán fusion trên nuScenes*. Muốn tiến gần paper thì mở ticket riêng cho attenuation + occlusion
(ADR-0002 đã ghi là để v2).