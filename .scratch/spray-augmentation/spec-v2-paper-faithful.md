# Spec v2 — spray plume theo cơ chế Linnhoff (phương án đầy đủ)

Trạng thái: **nháp chờ duyệt** · Ngày: 2026-11-10 · Người viết: PM
HEAD khi viết: `829f253` · Nhánh: `main`
Quyết định phạm vi: user chốt **phương án 1 — đầy đủ 6 bước, gồm ray casting + wet ground**.

Tag bằng chứng: `[PAPER]` Linnhoff et al. 2022 · `[CODE]` openMSL
`sl-1-2-reflection-based-lidar-object-model` · `[ĐO]` đo trên máy này ·
`[CHỌN]` quyết định của PM/user, không suy ra từ nguồn.

---

## 0. Định nghĩa "theo paper" — 6 bước kiểm được

| # | Cơ chế | Nguồn | v1 hiện tại | v2 |
|---|---|---|---|---|
| 0 | Wet ground: mặt đường ướt làm mất điểm phản xạ gương | `[PAPER]` §III-A dùng mô hình `[9]` | **không có** (ADR-0002 bỏ) | tích hợp `tools/wet_ground/` của `SysCV/LiDAR_snow_sim`, có công tắc |
| 1 | Vùng phun sau đuôi xe, dài theo `v·Δt` | `[PAPER]` §III-C | hộp quanh tâm box | khối sau đuôi, dài `v·Δt`, `Δt = 0,1 s` `[CODE]` |
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

**Đơn vị `wfh` — chốt theo số:**
- `wfh` tính bằng **mm**: `v=130` → `mean = (0,2·1+0,1)·80 = 24` cụm — khớp Fig. 11b (~30) `[PAPER]`.
- `wfh` tính bằng **m** (OSI): `mean = (0,2·0,001+0,1)·80 = 8` cụm — **không khớp** Fig. 11b.

Code đọc `surface_water_film()` của OSI `[CODE] dee.cpp:181`, mà OSI quy định đơn vị **mét**;
nhưng repo **không kèm file scenario** nào đặt giá trị này (grep `surface_water_film` ngoài `.cpp/.hpp` → 0 hit),
nên không kiểm được họ truyền `0,001` hay `1,0`.

⇒ `[CHỌN]` v2 dùng **wfh tính bằng mm** trong công thức cụm, vì chỉ cách đó mới khớp Fig. 11b
(24 cụm @130 km/h so với ~30 đọc từ hình). Ghi rõ trong config: `wfh_unit: mm`.
Đây là **giả định kiểm được** — ticket 31 đối chiếu lại bằng số cụm thực sinh.

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
> `[CHỌN]` đề xuất **(c)** — API không vỡ, và (a) là đường chạy được ngay trên dữ liệu này.

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