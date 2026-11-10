# Provenance của từng tham số `PlumeConfig`

> ⚠️ **File này mô tả `PlumeConfig` của v1** (2026-11-07). v2 dùng `PlumeStateConfig` +
> `PlumeContext`, không còn `points_per_cluster`, `K = 2,51`, `points_per_cluster` theo cự ly
> hay hệ số bẹp `0,885`. Các con số "17,06 cụm/frame", "thiếu 2,13×" trong file đến từ
> clustering **single-linkage** nên **không dùng làm mốc**.
> Trạng thái hiện hành: `docs/PROJECT.md` §4 và `spec-v2-paper-faithful.md` §1.

Mục đích: mỗi con số trong `spray/plume.py` phải trả lời được "lấy từ đâu". File này là bản đồ đó.
Viết lại sau khi PM nói sai rằng "số cụm tăng theo tốc độ không có trong paper Linnhoff" — **sai**,
xem dòng "số cụm" trong bảng dưới. Đừng lặp lại lỗi này.

Nguồn viết tắt: **[PAPER]** = Linnhoff et al., *Simulating Road Spray Effects in Automotive Lidar Sensor
Models*, arXiv 2212.08558 (§ và hình ghi kèm). **[CODE]** = code tham chiếu đã publish
(`openMSL/sl-1-2-reflection-based-lidar-object-model`, MPL-2.0; số dòng ở §Code tham chiếu).
**[ĐO]** = đo trên SemanticSpray release local (`docs/semantic-spray-stats.md`).
**[CHỌN]** = quyết định của repo, không có nguồn ngoài.

| Tham số trong code | Giá trị | Nguồn | Vị trí chính xác | Trạng thái |
|---|---|---|---|---|
| `min_speed_kmh` | 40 | [CODE] | `DetectionEnvironmentalEffects.cpp:502,:554` — `object_velocity > 40/3.6` **và** `water_film_height > 0` | **port đúng** — đây là ngưỡng *kích hoạt*, không phải offset số cụm |
| `water_film_height_m` | 0,001 m (1 mm) | [CHỌN] | OSI không cho default; dataset không khai báo độ ướt | **giả định** — phải ghi rõ ở mọi báo cáo |
| số cụm | `mean = (0,2*wfh + 0,1) * (v_kmh - 50)` (sinh mỗi chu kỳ 0,1 s); số cụm/frame = `round(mean × K)` | [CODE] | `dee.cpp:509–512`; profile `num_clusters_velocity_offset_kmh = 50.0`; `K` từ lifetime (ticket 22) | **port đúng** — offset là **50 km/h**, không phải 40; `K ≈ 2,51` không phải tham số bịa |
| lifetime | `T = wfh*0,02*(v_kmh - 50) + 0,2` s; cụm sống với `p = exp(-age/T)`, xoá khi `age > 4T`. Generator per-frame dùng trạng thái dừng `K = Σ_{k=0}^{4T/Δt} exp(-k·Δt/T)`, `Δt = 0,1 s` | [CODE] | `dee.cpp:530` (T), `:262` (p), `:446` (xoá); `Δt` từ profile `update_cycle_time` | **port đúng** — số cụm/frame = `round(mean × K)`, không còn dropout per-frame (ticket 22). `T = 0,2 s` chỉ đúng ở `v = 50 km/h` |
| `_POINTS_MEDIAN_BY_RANGE` (thay cho hằng số 17) | 30 / 20 / 14 / 10 / 10 cho cự ly **0–5 / 5–10 / 10–20 / 20–30 / >30 m** (sigma 0,67; bounds 3–200) | [ĐO] | ticket 16, `docs/plume-geometry-vs-real.md`: median `n_points` theo cự ly, n=11.607 cụm (base) và 23.989 (expanded). Median **gộp = 17,0** — đúng bằng hằng số cũ — nhưng giảm **3,0×** từ 0–5 m xuống 20–30 m | **thay thế** hằng số 17; `>30 m` là **ngoại xuy phẳng**, không có cụm dày nào đo được ngoài 50 m |
| `radial_squash` | 0,885 | [ĐO] để calibrate, [CHỌN] dạng ellipsoid | ticket 16: median **per-cluster** `r_range/r_extent` = **1,28**. Công thức liên tục cho khối cầu đặc: S = 1,28/2 = 0,64; nhưng với ~17 điểm rời rạc, S = 0,64 chỉ ra **0,98** → hiệu chỉnh thực nghiệm (quét S trên ≥900 cụm) chọn **0,885** để khớp đúng thống kê đo | **mới** (ticket 17) |
| `cluster_radius_median_m` | 0,30 (sigma 0,8) | [PAPER] | Fig. 5: lognormal μ=−1,2 σ=0,8 → median 0,30 m | **giữ nguyên** — ticket 16 đo median `r_extent` = **0,755 m**, nhưng đó là **cận trên**: single-linkage trên `(x,y)` nối chuỗi các cụm gần nhau, và 0,755 m ≈ 2,5× giá trị paper. Đổi theo số đo sẽ phóng to cụm mà không có căn cứ |
| vị trí cụm | sau xe dẫn đường, cách 1–10 m | [PAPER] định tính | §III: cụm đặt **uniform trong vùng sau mỗi vật thể đang di chuyển**, không spawn ngẫu nhiên trong scene | **đơn giản hoá** |
| attenuation | không có | [PAPER] | §III: `exp(−2×0,02×d)` = **0,04 m⁻¹** | **thiếu** (ADR-0002) |
| occlusion điểm thật | không có | [CODE] | `dee.cpp:250–300` + `add_max_detection` (`:781`): điểm spray thắng theo `power = intensity / distance²`; xe thật intensity 4–40 nên gần như không bị che | **thiếu** (ADR-0002) |
| `P_det` per-tia | không có | [CODE] | `dee.cpp:250–300`: `min(1, lognormal(−2,3; σ=1,1))`, median **0,10**, trung bình sau chặn **≈0,19** | **thiếu** — repo sinh cụm trực tiếp thay vì mô phỏng tia |
| mức nước / lớp xe | 1 mm, gộp 1 regime | [CHỌN] | profile có 0,5 mm ẩm / 0,75 phủ một phần / 1,0 phủ hoàn toàn; 2 lớp xe (VW Golf, VW Crafter) | **gộp thành 1 regime** — `water_film_height_m` là giả định |

## Code tham chiếu

Code của Linnhoff et al. 2022 **đã publish**: GitHub
[`openMSL/sl-1-2-reflection-based-lidar-object-model`](https://github.com/openMSL/sl-1-2-reflection-based-lidar-object-model),
giấy phép MPL-2.0. File chính:
`src/model/strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp`
(833 dòng) + header `DetectionEnvironmentalEffects.hpp` + `profile_VLP32.hpp.in`.

| việc | code thật | dòng |
|---|---|---|
| kích hoạt | `object_velocity > 40/3.6` **và** `water_film_height > 0` | `dee.cpp:502`, `:554`; `dee.hpp:48` |
| số cụm | `mean = (0.2*wfh + 0.1) * (v_kmh - 50.0)`, rồi `round(max(0, mean))` | `:509–512`; profile `num_clusters_velocity_offset_kmh = 50.0` |
| hằng thời gian | `time_constant = wfh*0.02*(v_kmh - 50) + 0.2` | `:530` |
| sống sót | `existence_probability *= exp(-age/time_constant)` | `:262` |
| xoá | `age > 4 * time_constant` | `:446` |
| `P_det` mỗi tia | `min(1, lognormal(−2,3; 1,1))` — median **0,10**, trung bình sau chặn **≈0,19** | `:250–300` |
| thay detection | điểm spray thắng nếu `power = intensity / distance²` lớn hơn điểm thật đã suy giảm (`add_max_detection`) | `:781` |
| suy giảm | `exp(-2.0 * 0.02 * d)` = **0,04 m⁻¹** | profile `mean_attenuation_in_cluster` |

`40/3.6` **không** phải ngưỡng số cụm. Ngưỡng số cụm là **50 km/h**.

## v1 khác code thật chỗ nào

| cơ chế | code thật | v1 | hệ quả |
|---|---|---|---|
| occlusion | thay return yếu theo `power = intensity / distance²`; xe thật intensity 4–40 gần như không bị che | **không có** — chỉ **thêm** điểm | thay thế các return yếu (mặt đường, vật tối ở xa), **không phải** "xe biến mất" |
| drag | hạt nước bị kéo theo dòng khí sau xe; phân bố phụ thuộc vận tốc | **không có** | hình học plume bị đơn giản hoá |
| beam / ray-sphere | mô phỏng từng tia VLP-32C cắt khối cầu, xác suất `P_det` | **không có** — sinh cụm trực tiếp | không tái lập được thống kê `P_det` per-tia |

Occlusion **không phải** nguồn lạc quan lớn nhất. Trong code thật (`dee.cpp:250–300`,
`add_max_detection` `:781`): mỗi tia cắt cụm mới sinh điểm spray với xác suất
`min(1, lognormal(−2,3; 1,1))` — median **0,10**, trung bình sau chặn **≈0,19**. Nếu sinh, điểm spray
vẫn phải **thắng** theo `power = intensity / distance²` so với điểm thật đã suy giảm: spray intensity
≈ `0,5/255×100 = 0,196` ở 25 m → `3,1e−4`; điểm xe ở 40 m thắng khi `I_xe > 0,5` (thang 0–100) — xe thật
**4–40**, nên xe gần như **không bao giờ bị che**. Nói cách khác occlusion trong model tham chiếu là
**thay thế các return yếu** (mặt đường, vật tối ở xa), không phải "xe biến mất".

Xếp lại nguồn lạc quan: **(1) camera branch sạch, (2) số cụm, (3) lifetime, (4) drag, (5) occlusion.**
Hai chiều vẫn bị gộp: **lớp xe** và **độ dày màng nước** (v1 chạy một regime, wfh = 1 mm).

## Hạn chế: self-spray chưa mô phỏng

Trong spray **thật** (clip A), ngoài cụm sau xe dẫn đường (`x ≈ 19–21 m`) còn có cụm **ngay sau chính
ego** (`x ≈ −4,5 m`, `y ≈ 0`) — bụi nước do bánh xe ego hất lên. Generator chỉ sinh sau **xe phía trước**,
không có self-spray. Không ảnh hưởng eval set A (box phía trước, `x > 0`) nhưng phải ghi vào danh sách
hạn chế để không bị hỏi khó.

## Vì sao số cụm vẫn lệch 17,06 cụm/frame

Công thức tham chiếu với wfh = 1 mm, `Δt = 0,1 s`. `mean` là số cụm sinh mỗi chu kỳ; số cụm/frame
là `round(mean × K)` (ticket 22):

| v_kmh | 40 | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|---:|
| cụm sinh / chu kỳ (`round(mean)`) | 0 | 0 | 1 | 3 | 5 | 8 |
| `K` (trạng thái dừng) | — | 2,513 | 2,515 | 2,519 | 2,522 | 2,528 |
| cụm nhìn thấy / frame (`round(mean × K)`) | 0 | 0 | 3 | 8 | 13 | 20 |

Ticket 16 đo **35.305 cụm / 2.070 frame = 17,06 cụm/frame** trên spray thật. Sau ticket 22, ở 80 km/h
generator tạo **8** cụm/frame → thiếu **2,13×**; ở 130 km/h tạo **20** → cao hơn 17,06 **1,17×**. Đây là
cùng bậc và **không còn frame rỗng** ở dải ≥60 km/h. Chênh còn lại (nhất là ở 80 km/h) là do `wfh` giả
định 1 mm cho **một** box, không phải lỗi port. **Không** tự nâng `wfh` hay hệ số nào để khớp đúng 17,06;
muốn khớp phải tách lớp xe/mức nước hoặc hiệu chỉnh `wfh` theo dữ liệu (việc của ticket khác).

## Sai lệch đã biết: `K` và đơn vị `water_film_height`

**(a) `K = 2,51` là cận dưới nhẹ so với code gốc — [CHỌN].** Code rút `T ~ N(T; 0,2)` (std bằng chính
mean) ⇒ **15,9%** cụm có `T ≤ 0` (chết ngay chu kỳ đầu), nhưng đuôi `T` lớn sống lâu hơn tuyến tính,
nên `E[K] = 2,76` so với `K = 2,51` khi `T` cố định (**+10%**). Ta chọn `T` cố định vì tái lập được —
ghi rõ đây là sai lệch đã biết, không phải lỗi port.

**(b) `water_film_height` tính bằng MÉT — [CODE]; paper tính bằng MM — [PAPER].**
Đính chính 2026-11-10 (user xác nhận): paper dùng **mm** cho `wfh` và cho ba lớp `h`
(moist 0,5 / partially 0,75 / fully 1,0 mm). Câu "tính bằng MÉT" dưới đây là **cách code OSI truyền giá trị**,
không phải đơn vị paper. Hệ quả: cùng một `wfh` cho **hai kết quả khác nhau tuỳ đơn vị**, vì cả công thức
số cụm và công thức thời gian sống đều nhân với `wfh`.

| v (km/h) | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|
| `T = 0,02·wfh·(v−50)+0,2`, `wfh = 0,001` (m, v1) | 0,20 | 0,20 | 0,20 | 0,20 | 0,20 |
| cùng công thức, `wfh = 1` (mm, paper) | 0,20 | 0,40 | 0,80 | 1,20 | 1,80 |

v1 chạy nhánh mét ⇒ `T ≈ 0,20 s` ở mọi tốc độ, `K ≈ 2,51` coi như hằng. Đó là **hệ quả của đơn vị**, không
phải hằng số vật lý: nếu đọc `wfh = 1 mm` là số `1,0` thì `T(130 km/h) = 1,80 s`, tức **sai 9×** so với v1.
Phải ghi đơn vị bên cạnh **mọi** chỗ dùng `wfh`.

**`[CHỌN 2026-11-10 — user chốt]`:** v2 dùng **mm cho cả `count` và `T`**, không trộn đơn vị. Hệ quả chấp
nhận: `T = 1,80 s @130 km/h` ⇒ vệt `v·T = 65 m`, xoá khi `age > 4T = 7,2 s`. v1 chạy nhánh mét nên
**không có vệt dài** — đây là một phần vì sao can thiệp v1 yếu, không chỉ vì mật độ cụm.

**`[CHỌN 2026-11-10 — user chốt]` Hai tốc độ, hai vai.** `count` và `T` dùng **tốc độ tuyệt đối** (xe dẫn so
với mặt đường, `object_speed_mps`); vận tốc đầu của cụm và advection dùng **tốc độ tương đối** so với ego
(`object_speed_mps − ego_speed_mps`). Lý do: lượng nước bắn lên tỉ lệ với quãng mặt đường ướt bánh lăn qua
mỗi giây; còn chuyển động nhìn thấy được trong point cloud là chuyển động trong hệ ego. Bằng chứng loại
phương án "dùng `v_rel` cho tất cả": SemanticSpray có `v_rel ≈ 0` ở 207/207 scene nhưng vẫn có spray thật.

## Mật độ 3 box (12 / 22 / 38 m, 80 km/h, seed 0–4)

Tái lập bằng `scripts/plume_density_table.py`. Frame nền tổng hợp 1.000 điểm, 3 box phía trước,
cùng frame cho 5 seed:

| seed | điểm trước | điểm sau | thêm | cụm |
|---:|---:|---:|---:|---:|
| 0 | 1.000 | 1.392 | 392 | 24 |
| 1 | 1.000 | 1.368 | 368 | 24 |
| 2 | 1.000 | 1.390 | 390 | 24 |
| 3 | 1.000 | 1.572 | 572 | 24 |
| 4 | 1.000 | 1.613 | 613 | 24 |
| **tổng** | **5.000** | **7.335** | **2.335** | **120** |

Bảng cũ, **công thức trước ticket 21–22** (ticket 17) — chỉ để đối chiếu, **không** dùng làm kết quả:
`1.330 → 1.057` điểm (`−21%`).

## Vì sao `points_per_cluster` không lấy từ paper

Paper không có khái niệm "số điểm mỗi cụm": nó mô phỏng **từng tia**, mỗi tia có xác suất `P_det` sinh
detection. Số điểm/cụm là hệ quả của `P_det` × số tia cắt khối cầu. Repo sinh cụm trực tiếp nên phải
neo vào đại lượng đo được (dense cluster size median 17). Hai cách khác bản chất, không thay thế nhau
bằng một con số.

Hệ quả là số điểm/cụm **phải giảm theo cự ly**: `P_det` giữ nguyên nhưng số tia cắt khối cầu giảm theo
góc khối. Ticket 16 đo được đúng như vậy (30 → 10 điểm, **3,0×**), nên ticket 17 thay hằng số 17 bằng
bảng `_POINTS_MEDIAN_BY_RANGE`. Hằng số 17 chỉ đúng ở mức **trung bình gộp** — dùng nó cho mọi cự ly là
sai hình học, dù con số trung bình khớp.

## Hệ quả cho claim

Vì thiếu attenuation + occlusion + `P_det`, repo **không tái lập** Linnhoff và **không nên** so trực tiếp
với +17,39 AP của họ. Claim đúng phạm vi: *plume augmentation calibrated theo thống kê spray đo được,
cho bài toán fusion trên nuScenes*. Muốn tiến gần paper thì mở ticket riêng cho attenuation + occlusion
(ADR-0002 đã ghi là để v2).