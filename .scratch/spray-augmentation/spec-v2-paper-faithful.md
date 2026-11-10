# Spec v2 — spray plume theo cơ chế Linnhoff (phương án đầy đủ)

Trạng thái: **nháp chờ duyệt** · Ngày: 2026-11-10 · Người viết: PM
HEAD khi viết: `829f253` · Nhánh: `main`
Quyết định phạm vi: user chốt **phương án 1 — đầy đủ 6 bước, gồm ray casting + wet ground**.

Tag bằng chứng: `[PAPER]` Linnhoff et al. 2022 · `[CODE]` openMSL
`sl-1-2-reflection-based-lidar-object-model` · `[ĐO]` đo trên máy này ·
`[CHỌN]` quyết định của PM/user, không suy ra từ nguồn.

> **Cập nhật 2026-11-11 — bốn điều chỉnh so với bản nháp này.** Nguồn: `docs/paper-qa-notebooklm.md`
> (hỏi đáp nguyên văn trên PDF paper) và `docs/plume-geometry-measurements.md`.
>
> 1. **`P_det`**: paper dùng `n/n_max` với `n` = số detection đo được, `n_max` = số tia cắt ⇒
>    lognormal Fig. 7 bốc **một lần mỗi cụm**, Bernoulli **mỗi tia**, nhân `P_t`. Code 29b đã đúng.
> 2. **Không** đặt ngưỡng cắt cụm theo mét. Paper **không có** luật xoá nào (`age > 4T` là `[CODE]`);
>    p5 của `x` dao động −40,6…+3,7 m giữa hai nửa scene nên không thể là hằng số. Đuôi tự tắt vì
>    `n_max ∝ 1/d²` (cụm 0,3 m còn 3 ô góc ở ~61 m).
> 3. **Chiều cao khối**: paper không cho; `dee.cpp` để `1,5 m`. Đo 939.803 điểm ⇒ phủ **5–92 % chiều
>    cao box**. `3,4 m` bề ngang **giữ nguyên** (khớp `|y|` p95 thật 2,31 m).
> 4. **Nghiệm thu tách hai vai**: `cal` để khớp tham số, `held-out` để báo cáo, chia theo scene
>    (1 scene = 1 lần ghi). SemanticSpray **không** dùng để train/eval detector (ADR-0003).
>
> Ngoài ra `intensity` của detection sinh ra phải là **0** (`[PAPER]`), và `spray/config/beam_elevation.yaml`
> **bị bác bỏ** — cast trên lưới tia đều.

---

## 0. Định nghĩa "theo paper" — 6 bước kiểm được

| # | Cơ chế | Nguồn | v1 hiện tại | v2 |
|---|---|---|---|---|
| 0 | Wet ground: mặt đường ướt làm mất điểm phản xạ gương | `[PAPER]` §III-A dùng mô hình `[9]`; code `dee.cpp:305–380` (MPL-2.0) | **không có** (ADR-0002 bỏ) | **port** `dee.cpp` vào `spray/wet_ground.py` — không vendor `LiDAR_snow_sim` (CC BY-NC); mặc định tắt |
| 1 | Vùng phun sau đuôi xe, dài theo `v·Δt` | `[CODE]` `dee.cpp:559–561` — paper §III-C chỉ nói "region behind" và **không cho kích thước** | hộp quanh tâm box | khối sau đuôi `v·Δt × 3,4 × (5–92 % chiều cao box)` `[CODE]`+`[ĐO]` |
| 2 | Sinh cụm: `mean = (0,2·wfh_mm + 0,1)·(v_kmh − 50)` | `[CODE]` `profile_VLP32.hpp.in:32–34` | có (hằng số đúng) | giữ, chốt đơn vị `wfh` |
| 3 | Vòng đời: `T`, drag `C`, `P_t = e^(−t/T)` | `[PAPER]` §III-C | **không có trạng thái thời gian** | có, state theo frame |
| 4 | Ray casting beam × sphere, `P_det` lognormal | `[PAPER]` §III-C | **không có** (phát điểm trực tiếp) | có |
| 5 | Attenuation `0,02 m⁻¹` + giữ strongest return | `[CODE]` `dee.cpp:271–281` | **không có** | có |

v1 không phải "sinh điểm ngẫu nhiên": `spray/plume.py:60–120` đã có ngưỡng 40 km/h, `wfh`,
công thức số cụm, và mật độ điểm theo cự ly `[ĐO đọc code]`. v2 **giữ** phần đúng,
**thay** phần thiếu cơ chế.

---

## 1. Hằng số — nguồn và trạng thái

| Đại lượng | Giá trị | Đơn vị | Nguồn | v1 dùng |
|---|---|---|---|---|
| Ngưỡng kích hoạt | `40/3.6` | m/s | `[CODE]` `DetectionEnvironmentalEffects.hpp:48` | 40 km/h ✔ |
| Offset tốc độ trong công thức cụm | `50` | km/h | `[CODE]` `profile_VLP32.hpp.in:34` | 50 ✔ |
| Hệ số `wfh` khi sinh cụm | `0,2` | — | `[CODE]` `profile_VLP32.hpp.in:32` | ✔ |
| Hằng số nền khi sinh cụm | `0,1` | — | `[CODE]` `profile_VLP32.hpp.in:33` | ✔ |
| Bán kính cụm | lognormal `μ=−1,2` `σ=0,8` → median **0,30 m** | m | `[CODE]` `profile_VLP32.hpp.in:35–36` | ✖ (dùng `radius_m` riêng) |
| `P_det` mỗi beam × cụm | lognormal `μ=−2,3` `σ=1,1` → median **0,10** | — | `[CODE]` `profile_VLP32.hpp.in:28–29` | ✖ |
| Attenuation trong cụm | `mean = 0,02`, hệ số `e^(−2·mean·L)` | 1/m | `[CODE]` `profile_VLP32.hpp.in:30`, `dee.cpp:271–272` | ✖ |
| Hằng số thời gian nền | `0,2` | s | `[CODE]` `DetectionEnvironmentalEffects.hpp:47` | ✖ |
| Chu kỳ cập nhật | `0,1` | s | `[CODE]` `profile_VLP32.hpp.in:49–50` | ✖ |
| Công thức thời gian sống | `T = 0,02·wfh·(v−50) + 0,2` | s | `[PAPER]` §III-C | ✖ |
| Drag | `−0,15` (paper) / `N(−0,12; 0,04)` (code) | — | `[PAPER]`/`[CODE]` | ✖ |
| Số detection mỗi cụm | **không phải tham số** — nổi lên từ ray casting | detection | `[CODE]` `dee.cpp:251–290` | ✖ (v1 đặt `points_per_cluster = 17`) |
| Mức nước khi augment | `wfh ~ exp(0,1 … 1,2)` | mm | `[PAPER]` §IV | ✖ |

**Khối phun — số chính xác `[CODE]` `dee.cpp:571–591`:**
dài `= |v|·Δt` (`Δt = 0,1 s`), rộng **3,4 m** cố định, cao **1,5 m** cố định.
Tâm đặt tại `pos_box − (L_box/2 + L_khối/2)` theo yaw; `z` = đáy box + `h_khối/2`
(tức mặt đáy khối trùng đáy box, không phải mặt đường).

**Sinh cụm — số chính xác `[CODE]` `dee.cpp:509–542`:**
- Số cụm **tất định**: `round(max(0, mean))` — dòng `normal_distribution` bị comment out `dee.cpp:510–511`. **Không phải Poisson.**
- Tâm: uniform trong khối (3 trục độc lập).
- `radius = min(1,0 m, lognormal(−1,2; 0,8))`.
- `age` khởi tạo **−0,1 s** (âm, để cụm chưa hoạt động ở frame sinh).
- `T ~ N(wfh·0,02·(v_kmh−50) + 0,2 ; σ=0,2)` — cộng nhiễu chuẩn, không phải hằng `T`.
- `v_cụm = v_vật`, `v_z = v_z,vật + 5·U(0,1)`.
- `drag ~ N(−0,12; 0,04)`.
- Cập nhật: `v += drag·v̂_rel·|v_rel|²·Δt` với `v_rel = v_cụm + gió(208°, 2 m/s)`; `pos += v·Δt`.
- Xoá khi `age > 4·T` `[CODE] dee.cpp:453`.

**Cập nhật 2026-11-10 sau khi đọc lại code:** `K = 2,51` **không tồn tại** trong repo openMSL
(`grep -rn "2\.51"` → 0 hit). Nó là **số detection trung bình mỗi cụm** mà paper báo cáo, tức
**đầu ra** của ray casting. Docstring trong repo này ghi `K = 2,51` là chỗ dễ hiểu nhầm: nếu v2
ép `K` thành hằng số thì ray casting vô nghĩa. **Bỏ `K` khỏi tham số sinh.**

**Đơn vị `wfh` — `[PAPER]` mm (user xác nhận 2026-11-10):**
Trong paper, `wfh` tính bằng **mm**, và ba lớp nước `h` (moist / partially / fully) cũng là **mm**
(moist 0,5 / partially 0,75 / fully 1,0). Không phải suy ra từ hình — đây là đơn vị paper dùng.

Kiểm chéo bằng số, khớp:
- `wfh` tính bằng **mm**: `v=130` → `mean = (0,2·1+0,1)·80 = 24` cụm — khớp Fig. 11b (24 cụm @130).
- `wfh` tính bằng **m**: `mean = (0,2·0,001+0,1)·80 = 8` cụm — **không khớp**.

**Hệ quả BẮT BUỘC xử lý — công thức `T` cũng ăn `wfh`, nên đơn vị đổi kết quả 9×:**
`T = 0,02·wfh·(v − 50) + 0,2`. Đọc `wfh` theo mm (paper) thay vì mét (v1):

| v (km/h) | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|
| `T` với `wfh = 0,001 m` (v1) `[ĐO]` | 0,20 | 0,20 | 0,20 | 0,20 | 0,20 |
| `T` với `wfh = 1 mm` (paper) `[ĐO]` | 0,20 | 0,40 | 0,80 | 1,20 | 1,80 |

Với mm, `T` **phụ thuộc tốc độ** (1,8 s @130 ⇒ vệt dài `v·T = 65 m`, xoá khi `age > 4T` = 7,2 s);
với mét, `T ≈ 0,20 s` ở mọi tốc độ và vệt gần như đứng yên. v1 vô tình chọn nhánh "mét" nên
**không có vệt dài**.

**`[CHỌN 2026-11-10 — user chốt]` = mm cho CẢ HAI công thức.** Không trộn đơn vị: `wfh` là một đại lượng,
dùng mm ở chỗ sinh cụm thì dùng mm ở chỗ tính `T`. Hệ quả đã biết và được chấp nhận:

| v (km/h) | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|
| `T` (s), `wfh = 1` mm | 0,20 | 0,40 | 0,80 | 1,20 | 1,80 |
| vệt `v·T` (m) | — (0 cụm) | 6,7 | 17,8 | 33,3 | **65,0** |
| xoá khi `age > 4T` (s) | 0,8 | 1,6 | 3,2 | 4,8 | 7,2 |

Với `wfh ~ exp(0,1…1,2)` mm `[PAPER]` §IV, `T(130)` nằm trong `0,36 … 2,12 s` tuỳ cụm. Ticket 28 dùng
**một** hằng `wfh_unit: mm` cho cả `count` và `T`; ticket 31 đối chiếu độ dài vệt sinh ra với vệt thật
(36/207 scene có box + nhãn spray).

Code tham chiếu đọc `surface_water_film()` của OSI `[CODE]` `dee.cpp:181`, mà OSI quy định đơn vị
**mét**; repo **không kèm file scenario** nào đặt giá trị này (`grep surface_water_film` ngoài `.cpp/.hpp`
→ 0 hit), nên **không kiểm được** họ truyền `0,001` hay `1,0`. Vì vậy "paper dùng mm" và "code OSI dùng mét"
là hai dữ kiện cùng đúng — ta theo paper vì đó là chuẩn của dự án, và ghi rõ khác biệt này.

Ghi trong config: `wfh_unit: mm`. Ticket 31 đối chiếu lại bằng số cụm **và** độ dài vệt thực sinh.

**Tốc độ — hai vai, không gộp** `[CHỌN 2026-11-10 — user chốt, SỬA 2026-11-10 sau khi đo]`:

| Vai | Dùng biến nào | Vì sao |
|---|---|---|
| Sinh bao nhiêu nước: `count`, `T` | **`v_abs`** — xe dẫn so với mặt đường | Lượng nước bắn lên tỉ lệ với số mét mặt đường ướt mà bánh lăn qua mỗi giây. 80 km/h quét gấp đôi 40 km/h |
| Chuyển động của cụm (advection) | **hệ GROUND**: vận tốc đầu = `v_object_ground`, drag tác động lên vận tốc tương đối với không khí | `[PAPER]` "the velocity of the moving object is set as an initial cluster velocity"; code gốc render bằng `transform_position_from_world_to_sensor_coordinates` |
| Vị trí hiển thị | **hệ EGO** | point cloud ở hệ ego; mỗi frame trừ đi quãng ego đã đi |

**Đính chính 2026-11-10 (PM viết sai ở bản trước):** bản đầu của bảng này ghi "advection dùng `v_rel`" — **SAI**.
Đo trên 28b: với `v_rel` (ego và xe dẫn cùng tốc độ ⇒ `v_rel = 0`), giọt không bao giờ trôi về phía sau, vệt chỉ
dài **7,3 m** ở 130 km/h thay vì `v·T = 65 m`, và 1.781 cụm dồn vào dải 7 m (trần 2.000 điểm cắt 75 %).
Đúng phải là: cụm mang vận tốc **ground**, drag làm giảm tốc trong hệ ground, ego chỉ là nơi render — nhờ vậy
giọt trôi ngược ~36 m/s trong hệ ego và vệt dài đúng cỡ `v·T`. Sửa ở ticket 28c.

Trong `PlumeContext` hai số này là hai trường riêng: `object_speed_mps` (`v_abs`) và
`object_velocity_ego_mps` (vector, để dựng vận tốc ground = vector đó + `[ego_speed, 0, 0]`).

**Mức nước mỗi frame** `[CHỌN 2026-11-10 — user chốt]`: lấy mẫu `wfh ~ exp(0,1 … 1,2) mm` mỗi frame, đúng như
paper dùng khi huấn luyện (`[PAPER]` arXiv 2212.08558: "sampled from an exponential distribution from the
interval 0,1−1,2 mm"). Ba mức nước cố định của paper là **0,5 / 0,75 / 1,0 mm** cho moist / partially / fully.
Hệ quả đã biết: plume có frame nhẹ (wfh 0,1 mm → 10 cụm/chu kỳ @130) và frame rất dày (wfh 1,2 mm → 28 cụm),
nên trần `max_injected_points` sẽ cắt mạnh ở frame dày — phải báo `capped` trong marker và xử lý trần ở ticket 30.

**Hằng cản `C`** `[CHỌN 2026-11-10 — user chốt]`: theo paper, `C = −0,15 m⁻¹` là **hằng số**, không lấy mẫu
(code gốc `dee.cpp:542` dùng `N(−0,12; 0,04)`; ta cố ý theo paper). Đơn vị `1/m` vì `C·|v|²·Δt` phải ra `m/s`.
Đo hệ quả: vệt @130 km/h đổi từ 73,7 m → **73,4 m** — hằng cản **không** phải đòn bẩy làm plume mạnh lên.

**Cổng tốc độ ego > 60 km/h — HOÃN** `[CHỌN 2026-11-10 — user]`. Paper nêu điều kiện này ở tầng
**data augmentation** (chỉ augment đường cao tốc/ngoại ô), khác với ngưỡng vật lý `object > 40 km/h` của model
(`[CODE]` `dee.cpp:502`). Ta giữ ngưỡng vật lý, **chưa** thêm cổng ego. Lý do: nó chỉ quyết định *frame nào được
augment*, tức thiết kế A/B, mà nghẽn hiện tại là **độ mạnh của generator**, không phải eval.
Số để mở lại khi cần: eval set hiện 196 frame / 16 scene, CI95 nửa rộng **±0,008 mAP**; v1 đo delta −0,0031
(6 hộp lật/3.609 GT) nên không phân giải được, nhưng hiệu ứng cỡ **2–3 mAP** thì eval hiện tại **đủ** phân giải.

**Kịch bản của paper — dùng làm kiểm chứng thiết kế:** paper hiệu chỉnh ở hai kịch bản, *passing* (ego đứng yên,
xe tạo bụi 50–130 km/h) và *following* (ego bám sau, cùng tốc độ). Suy ra: `v_rel` **không** phải biến sinh cụm —
ở *passing* `v_rel = 130` mà ở *following* `v_rel = 0`, cả hai đều có spray. Chỉ `v_abs` giải thích được cả hai.

**Số cụm — `mean` là phát mỗi time step** `[PAPER]`: paper hiệu chỉnh bằng "counting the number of clusters in a
spray filter region behind the vehicle … divided by the length ratio of the spray region to the distance the
object traveled during one scan" ⇒ Fig. 4 = "clusters generated … during one scan", ~24 @130 km/h fully covered.
Đã kiểm bằng text paper, không suy từ code. Số cụm **còn sống** = `mean × 4T/Δt` (xoá khi `age > 4T`) ⇒ 1.781
đo được @130 km/h, `wfh = 1,0 mm`.

---

## 2. Hợp đồng dữ liệu

> **Phát hiện 2026-11-10, chưa xử lý — chặn ticket 26.**
> Dataset trên đĩa **không có 3D box** (`labels/*.label` là nhãn semantic theo điểm, `int32`,
> dài bằng số điểm; không có `sample_annotation`, không có `.json` meta kiểu nuScenes).
> Nên chữ ký `boxes (M,9)` hiện tại không lấy được từ dữ liệu thật.
> Ba hướng, phải chọn trước khi làm ticket 26:
> **(a)** dựng khối phun từ `metadata.txt` (`object_velocity`, `distance_to_object`,
> `unimog_direction`) — không cần box, khớp đúng biến điều khiển của paper;
> **(b)** suy box từ nhãn: cụm điểm cùng `label` (xe) → AABB/oriented box, dùng luôn cho đường
> "real plume + synthetic plume";
> **(c)** giữ `boxes` là tham số API, nhưng coi là optional: nếu `None` thì rơi về (a).

**`[CHỌN 2026-11-10 — user chốt]` = hướng (c), chia hai vai:**
- **Sinh (a)**: khối nước dựng từ `metadata.txt` (`object_velocity`, `distance_to_object`,
  `unimog_direction`) + `poses.txt`. Không cần box, không cần suy box từ nhãn.
- **Nghiệm thu (b)**: nhãn `2` (spray thật, 24–44 điểm/frame) là thước đo. Sai lệch giữa plume
  sinh ra và plume thật là tiêu chí của ticket 31.
- API: `boxes` giữ là tham số optional, `None` ⇒ đi đường (a). Không xoá tham số để test cũ không vỡ.

`PlumeTransform` hiện nhận `points (N,5)` + `boxes (M,9)` `[ĐO đọc code]`. v2 cần thêm:

| Input | Nguồn | Bắt buộc | Dùng cho |
|---|---|---|---|
| `points` sau khi lọc ground? | pipeline | có | bước 0, attenuation điểm thật |
| `boxes` `(M,7+)` world | pipeline | có | bước 1 |
| `ego_pose` (ma trận 4×4 world→ego) | dataset | có | bước 3 ray casting, bước 0 |
| `sensor_origin` trong ego | config (nuScenes: `lidar` extrinsic) | có | gốc tia |
| `elevation_angles` (32 giá trị) | config, từ ticket 25 | có | bước 3 |
| `ego_speed`, `object_speed` | `sample_annotation.velocity` + ego pose | có | bước 1, 2 |
| `wfh` mỗi frame | `[CHỌN]` sample `exp(0,1–1,2)` mm | có | bước 1, 2 |
| `frame_index`, `scene_token`, `epoch` | dataset | có | seed, log |

`wfh` **không** phải đầu ra của mô hình mặt đường ướt: paper đo bằng cảm biến độ ướt rồi
phân 3 lớp (moist 0,5 / partially 0,75 / fully 1,0 mm), khi augment thì sample `exp(0,1–1,2)` `[PAPER]` §IV.

---

## 3. Kiến trúc

```
spray/
  wet_ground.py     # bước 0: bọc tools/wet_ground của LiDAR_snow_sim, bật/tắt, log điểm bị mất
  plume_state.py    # bước 2-3: SprayCluster + registry theo (scene_token, object_id), age/velocity/T
  beam_model.py     # bước 4: elevation angles HDL-32E, giao tia × cầu, P_det
  plume.py          # giữ API inject_plume(); điều phối 1→5; giữ code hình học đã đúng
  plume_transform.py# thêm ego_pose/speed/frame metadata vào __call__
  config/plume_default.yaml  # thêm khối wet_ground + ray_casting + lifetime
```

Ràng buộc: **không** port code C++; `tools/wet_ground` gọi như thư viện ngoài, ghim commit.

---

## 4. Thuật toán

**B0 — wet ground.** Trên scan gốc, ước lượng mặt phẳng đất (RANSAC trên điểm thấp), làm mất
điểm đất theo xác suất phản xạ gương ướt. Log `wet_ground_removed` + `wet_ground_pool_remaining`.
Công tắc `wet_ground.enabled`. Không đụng điểm ở `z > 1,0 m` trên mặt đất.

**B1 — vùng phun.** Với mỗi box có `speed > 40/3,6 m/s` và `wfh > 0`: khối sau đuôi
dài `|v|·0,1 s`, **rộng 3,4 m**, **cao 1,5 m**, đáy trùng đáy box, tâm lùi
`L_box/2 + L_khối/2` theo yaw `[CODE] dee.cpp:571–591`.

**B2 — sinh cụm.** `n = round(max(0, (0,2·wfh_mm + 0,1)·(v_kmh − 50)))` — **tất định, không Poisson**.
Mỗi cụm: tâm uniform trong khối; `r = min(1,0; lognormal(−1,2; 0,8))`;
`age = −0,1 s`; `T ~ N(wfh·0,02·(v_kmh−50)+0,2; σ=0,2)`; `v = v_vật`, `v_z += 5·U(0,1)`;
`drag ~ N(−0,12; 0,04)`.

**B3 — cập nhật state mỗi frame.** `v_rel = v_cụm + gió(208°, 2 m/s)`;
`v += drag·v̂_rel·|v_rel|²·0,1`; `pos += v·0,1`; `age += 0,1`;
xoá khi `age > 4·T` hoặc ra khỏi `point_cloud_range`. Số detection mỗi cụm **không đặt trước** —
nó là kết quả của B4 (đây là chỗ v1 sai: `points_per_cluster = 17` ép trước).

**B4 — ray casting.** Với mỗi beam thật của frame (azimuth lấy từ scan, 32 elevation từ config):
giao tia × cầu; nếu cắt và `dist_min < 80 m`: `P = min(1, lognormal(μ=−2,3; σ=1,1)) · e^(−age/T)`;
sample `u`; nếu `u < P` → sinh detection ở `N(giữa cung, dài_cung/6)`, intensity
`N(0,5)/255·100`. Cộng dồn `L` = tổng chiều dài tia nằm trong các cụm **trước** điểm đó.

**B5 — attenuation + strongest return.** Áp `e^(−2·0,02·L)` lên intensity của detection mới
và của điểm thật trên cùng beam. Trên mỗi beam giữ **một** detection mạnh nhất — đây chính là
cơ chế "plume che xe".

**Sai lệch của code gốc, cố ý sửa:** `dee.cpp:288–290` cộng dồn `L` của **mọi** cụm tia cắt,
không so cự ly cụm với cự ly điểm thật ⇒ điểm thật bị suy giảm cả khi plume nằm **sau** nó.
`[CHỌN]` v2 chỉ tính `L` của cụm có `dist_first_hit < range(điểm thật)`. Ghi vào doc, không sửa ngầm.

Công tắc `attenuation.enabled`, mặc định **bật ở v2**, tắt được để A/B tách đóng góp.

---

## 5. Việc phải đo trước (0 GPU) — chặn toàn bộ tham số

| # | Đại lượng | Cách đo | Ảnh hưởng |
|---|---|---|---|
| M1 | tốc độ ego + xe dẫn trên đúng 196 frame val | `ego_pose` + `sample_annotation.velocity` | mật độ mục tiêu 500–1.600 vs 144 |
| M2 | 32 góc elevation HDL-32E | spec + đối chiếu phân bố ring thật | bước 4 |
| M3 | quỹ đạo 5 s của xe phun | `sample_annotation` theo thời gian | bước 1 |
| M4 | `z` mặt đường thật + thứ tự `w`/`l` | 1 frame thật | bước 1, D6 |
| M5 | ~~`K` + phân bố số cụm~~ **xong 2026-11-10** | `dee.cpp:509–542` — tất định, `K` không tồn tại | — |

---

## 6. Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` xanh, số test **không giảm** so với 192 passed / 4 skipped.
- [ ] Mật độ điểm spray/frame khớp **Fig. 11a tại tốc độ đo được** ở M1, sai số **±50 detection**.
- [ ] Số cụm/frame khớp Fig. 11b (±3 cụm) ở 3 mốc tốc độ.
- [ ] `ring` phủ **0–31**, median **4** ring/frame `[ĐO]`; không còn hằng `ring = 0`.
- [ ] `intensity`: p50 = **0**, p90 = **1**, p99 = **3**, max ≈ **53** `[ĐO]`.
- [ ] Attenuation **đo được**: frame có plume dày → điểm thật phía sau giảm intensity, log `attenuated_real_points > 0`.
- [ ] `rejected_box` vẫn được log; hộp 4,6×1,9 và 13,7×1,9 đều không tự xoá 30–64 % điểm (D6 đã sửa).
- [ ] Không có `ring`, `intensity`, `seed` nào là hằng số theo frame.
- [ ] Render 1 frame có/không plume + 1 ảnh BEV, mắt người xác nhận plume nằm **sau đuôi**, không xuyên thân xe.

**Không** dùng "ra gain dương" làm tiêu chí. Paper có **+0,62 AP** tổng nhưng **−0,15 AP ở 0–30 m** `[PAPER]`;
null là kết quả hợp lệ.

---

## 7. Không làm (out of scope)

- Fluid dynamics, multi-echo, occlusion bởi vật phản xạ gương, lấy vận tốc từ radar — paper bỏ `[PAPER]`.
- Port C++ openMSL. Chỉ đối chiếu công thức.
- Sửa nhánh camera: depth camera dựng từ chính điểm LiDAR ⇒ nhánh camera sạch, kết quả dương là **cận trên lạc quan**, ghi trong report.
- Đổi ngân sách/tăng timeout để "cho qua" test.

---

## 8. Ticket

| # | Ticket | Phụ thuộc | Ước lượng |
|---|---|---|---|
| 25 | Đo 0 GPU: M1–M5 | — | 0,5 ngày |
| 26 | Hợp đồng dữ liệu + state theo scene | 25 | 0,5 ngày |
| 27 | Wet ground (bước 0) | 26 | 0,5–1 ngày |
| 28 | Vùng phun + sinh cụm + vòng đời (bước 1–3) | 26 | 1 ngày |
| 29 | Ray casting + attenuation + strongest return (bước 4–5) | 27, 28 | 1,5–2 ngày |
| 30 | Intensity + ring + seed theo epoch + cap | 29 | 0,5 ngày |
| 31 | Nghiệm thu thống kê + render + audit độc lập | 25–30 | 1 ngày |

Tổng **5–6,5 ngày agent + review**, GPU chỉ dùng ở A/B sau ticket 31.

## 9. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| 196 frame val toàn < 50 km/h ⇒ không kích hoạt | M1 đo trước; nếu đúng thì A/B phải mở rộng tập frame, không hạ ngưỡng |
| Ray casting làm chậm pipeline | vector hoá theo beam; đo ms/frame, ngân sách < 50 ms |
| Wet ground xoá quá nhiều điểm nền → detector vỡ vì lý do khác plume | công tắc + arm riêng `plume-only` vs `plume+wet` |
| Số liệu Fig. 11a đọc bằng mắt ±50 | ghi rõ sai số trong report, không làm tròn thành "khớp chính xác" |