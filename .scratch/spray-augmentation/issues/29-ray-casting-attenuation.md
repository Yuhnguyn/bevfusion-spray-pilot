# 29c: sửa 7 lỗi — ray casting + liều (dose)

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (29a/29b đã xong)
**Chủ:** CommandCode. PM: Hermes.

## Hiện trạng (đã kiểm bằng code và số đo)

| Hạng mục | Trạng thái |
|---|---|
| 29a — bảng `ring → elevation` | **BỊ BÁC BỎ.** ring id không phải beam id trên bản release này. Quyết định thay thế: cast trên lưới tia đều **0,333° × 0,197307°**, FOV −4,06…+5,88° ⇒ ~30 × 1.826 ≈ 54.800 tia. `docs/history/plume-beam-table.md` §ĐÍNH CHÍNH. `spray/config/beam_elevation.yaml` **phải xoá** |
| 29b — `spray/raycast.py` | Xong: cast beam × cầu, `P_det = n/n_max`, attenuation `e^(−2·0,02·L)`, strongest-return mỗi beam. 239 passed, 4 skipped |
| Latency | **266–476 ms/frame** với 100 cụm (~2,4 ms/cụm) ⇒ 4–7 s/frame ở 1.794 cụm @130 km/h |
| `intensity` | Xuất **72–166** trên thang 255 (`raycast.py:256–261`) |
| Marker | `PLUME_RAYCAST` **chưa tồn tại** |
| Trần điểm | `plume.py:104` `max_injected_points = 2000` (lỗi D7) |
| Khối sau đuôi | `plume.py:115–116` cao `1,5 m` cứng |
| **Số cụm/chu kỳ (MỚI)** | `(0,2·wfh+0,1)·(v−50)` [CODE, dee.cpp] cho **9/15/24** cụm mỗi 0,1 s ⇒ **184 cụm/frame** @100, **436** @130; đo thật trên `cal` là **29,2** @100 và **17,7** @130 ⇒ vượt **6×** và **25×**, và gán phụ thuộc ẩm vào sai biến |
| **det/cụm (MỚI)** | 807–1.555 điểm ÷ 436 cụm ≈ **2–3,5** det/cụm; đo thật `cal` = **19,4** @100 km/h, **36,2** @130 km/h |
| **Phân bố ngang (MỚI)** | `plume.py:255` `lateral = rng.normal(0, 0,5)` ⇒ `p95(|lateral|) ≈ 0,98 m`; paper dùng **phân bố đều**, số thật `p95(|y|) = 2,31 m` ⇒ plume bám trục hẹp **~2,4×**, che vật thể nhiều hơn thực |

## Việc phải làm

1. **`intensity` của detection sinh ra = 0.** `[PAPER]`: *"Over 80 % of spray detections from the
   VLP32 have an intensity value of 0 and 16 % are 1. Therefore, the final intensity value of the
   simulated spray detections are set to 0."* `N(0,5; 0,05)` **chỉ** dùng để xếp hạng giữa nhiều
   detection trong **một** beam (strongest-return) — không được nhân `255`, không được xuất ra.
   Điểm **thật** bị attenuation thì giữ nguyên cơ chế: nhân `e^(−2·0,02·L)` vào intensity thật.
2. **Bỏ trần tuyệt đối.** Thay `max_injected_points = 2000` bằng ngân sách theo frame:
   `max_injected = max(500, round(0,05 × số điểm thật))`, vẫn báo `capped=<n>` trong marker.
   Lý do: hình học đúng cho **807–1.555 điểm/frame**; trần 2.000 hiện tại cắt 45–82 % ở frame dày.
3. **Chiều cao khối theo phân số box.** `tail_block_height_m` thành
   `tail_block_height_frac = (0,05; 0,92)` của chiều cao object; đáy khối = mặt đường + `0,05·h`
   (`z` đáy box SemanticSpray = `−0,411 m`). Bề rộng giữ `3,4 m` (`|y|` p95 thật 2,31 m — khớp).
   Kiểm: elevation median của điểm sinh ra phải vào **8,9–11,0°** ở 70/100/130 km/h (thật 9,2–9,5°).
4. **Hạ latency xuống < 100 ms/frame.** Hai luật lấy từ chính code tham chiếu
   (`dee.cpp:232–238`): (a) lọc beam theo cửa sổ `min/max_azimuth` của từng cụm trước khi cast;
   (b) bỏ qua cụm đã ra sau mặt phẳng cảm biến khi không beam nào phủ tới. **Không** dùng
   vector hoá bằng cách tăng bộ nhớ vượt 2 GB; đo lại bằng `time.perf_counter` và in số.
5. **Marker mới** mỗi frame: `PLUME_RAYCAST beams=<n> hit=<n> det=<n> att_m=<L> capped=<n> ms=<t>`.
6. **Xoá** `spray/config/beam_elevation.yaml`; `beam_model.py` chỉ còn lưới đều.
7. **Số cụm hiển thị theo bảng đo của chính `cal`, KHÔNG theo Fig. 11b** `[ĐO]` + `[CHỌN]` dạng hàm.
   Đo lại dataset bằng đúng recipe paper (DBSCAN góc `0,7°`, `minPts = 3`) — bảng đầy đủ ở
   `docs/measurements/semantic-spray-clusters-by-speed.md`:

   | km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
   |---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
   | **Crafter** cụm/frame | 4,2 | 11,3 | 17,4 | 22,0 | 20,7 | **29,2** | 28,5 | 17,6 | **17,7** |
   | **Golf** cụm/frame | 3,6 | 8,8 | 11,4 | 12,9 | 10,5 | 18,1 | 16,7 | 15,3 | 16,6 |
   | Crafter det/cụm (median) | 7,8 | 5,6 | 5,1 | 14,6 | 15,3 | **19,4** | 16,5 | 53,8 | 36,2 |

   Vì sao không dùng Fig. 11b: figure đó đo ở **50 m**, dataset chỉ có **20 / 30 m**; số đo thực ở
   130 km/h là **17,7** chứ không phải 75, và cự ly xa cho **ít** cụm hơn (20 m > 30 m khoảng
   10–20 %) nên ngoại suy 30 → 50 m chỉ làm số **giảm**. Dùng 75 làm đích sẽ đẩy generator lên một
   con số không tồn tại trong dữ liệu mà nó phải khớp. Mốc paper giữ làm **kiểm tra chéo** ở 100 km/h
   (paper 33 vs đo 29,2 ✓) và 14,3 det/cụm (đo 19,4 — cùng bậc).

   Dạng hàm: **bảng tra theo lớp xe**, nội suy tuyến tính giữa các mốc 10 km/h — đường cong
   **không đơn điệu** nên không fit `rate = a·(v − v0)`:
   `rate(v) = visible_ref(v) / K(T_ref(v))`, `visible = round(rate × K(T(wfh, v)))`, `T_ref` là hằng
   số thời gian ở mức ẩm chuẩn của dataset. `rate` **không** chứa `wfh`; độ ẩm chỉ tác động qua `T`.
   Golf có bảng **riêng** (paper `NOT STATED` cho Golf). **Không** đổi `T`, không đổi `age > 4T`.
8. **Canvas điểm phải khớp lại sau khi giảm số cụm.** Ở 100 km/h: 29,2 cụm × 19,4 det ⇒ **~570
   điểm/frame** nằm trong cụm; cửa sổ đo thật (label 2) là **807–1.555** điểm/frame, phần dư là
   điểm rời mà DBSCAN bỏ qua. Generator chỉ sinh detection **trong** cụm ⇒ đích là **570–1.555
   điểm/frame**, không phải 1.070 như suy từ Fig. 11b. Nếu lệch thì hiệu chỉnh **median
   `points_per_cluster`** (`plume.py:78–88`, đang là `[CODE]`), **không** đổi dạng `P_det`
   (lognormal mỗi cụm Fig. 7 bốc `n`, Bernoulli mỗi tia `n/n_max`) và **không** nâng trần điểm.
9. **Phân bố ngang của tâm cụm: đều, không Gaussian** `[PAPER]` §III-B:
   *"spheres are positioned with a uniform distribution in the region behind every moving object
   according to the empirical values for the number of clusters and the distribution of cluster
   radii"*, *"A uniform distribution was chosen as a first estimate, as no other form of distribution
   was visible."* Và §III: *"The initialization of clusters is restricted to the vehicle trajectory
   and no clusters are spawned randomly in the scene."*

   Thay `rng.normal(0, lateral_sigma_m)` (`plume.py:255`) bằng phân bố **đều** trên `±half_width`.
   `half_width` **không chọn tay**: đo `p95(|y − y_tâm_box|)` của điểm nhiễu thật trên `cal` bằng
   `spray/semantic_stats.py` rồi đặt `half_width` sao cho phân bố đều cho cùng p95 (đều trên `±a`
   có `p95 = 0,95·a`). Số tham chiếu đang có: `p95(|y|) = 2,31 m` ⇒ `half_width ≈ 2,4 m`, nhưng
   **phải đo lại theo hiệu với tâm box**, không bê nguyên `2,31 m`. In cả hai số.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ **239 passed, 4 skipped** (không giảm).
- [ ] Marker `PLUME_RAYCAST` xuất hiện mỗi frame có plume, đủ 6 khoá.
- [ ] `intensity` của **100 %** detection sinh ra = **0** (assert trong test).
- [ ] Điểm thật sau plume có `intensity` giảm; `points_clean` **không đổi** (byte-equal).
- [ ] Chiều cao điểm sinh ra: p5/med/p95 = **0,16 / 1,51 / 2,36 m** trên mặt đường ±0,15 m.
- [ ] Latency **< 100 ms/frame** ở 100 cụm, đo trên laptop, in số thật.
- [ ] `spray/config/beam_elevation.yaml` không còn tồn tại; không file nào reference.
- [ ] **Cụm/frame khớp bảng đo `cal` trong ±20 %** tại **cả 9 mốc 50…130 km/h**, cho **cả
      `Crafter` và `Golf`**, ở mức ẩm chuẩn. In bảng đo-vs-code đủ 9 dòng × 2 lớp.
- [ ] **det/cụm** median ở 100 km/h Crafter trong **15–25** (đo 19,4); ở 130 km/h trong **29–43**
      (đo 36,2).
- [ ] Tổng điểm spray/frame trong **570–1.555**; `capped` không tăng.
- [ ] `p95(|lateral|)` của cụm sinh ra khớp `p95(|y − y_box|)` đo trên `cal` trong **±10 %**; phân bố
      là đều (test: histogram 10 bin, χ² không bác `p > 0,01`), không còn `rng.normal` cho `lateral`.
- [ ] Biên bản nghiệm thu ghi trong ticket này: số đo trước/sau, phần chưa khớp.

## Cấm

- Không đổi **dạng** `P_det` (lognormal Fig. 7 bốc `n` mỗi cụm, Bernoulli mỗi tia `n/n_max`).
  Được đổi **tốc độ sinh cụm** (mục 7) và **median `points_per_cluster`** (mục 8) — đó là hai lỗi.
- Không đổi `T`, `C = −0,15`, `age > 4T`.
- Không thêm ngưỡng cắt cụm theo mét — p5 của `x` dao động −40,6…+3,7 m giữa hai nửa scene.
- Không nâng `wfh` hay hệ số nào để khớp số điểm.
- Không train lại, không chạy Kaggle.