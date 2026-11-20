# Bản đồ đọc hiểu generator plume (nhánh `sspp`)

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S1, S2, S5.
> Phần còn đúng: Số chuỗi rate×K ở §5 còn đúng; §4 và §6 mô tả hành vi generator TRƯỚC QĐ11/QĐ12.

Tài liệu cho người mới: đọc theo thứ tự nào, mỗi file làm gì, con số nào lấy từ đâu.
Mọi khẳng định trích `file:dòng`. Nhãn số theo `docs/PROJECT.md:181`:
`[ĐO]` đo trên máy này · `[PAPER]` paper nói · `[CODE]` code tham chiếu · `[CHỌN]` tự chọn.
Số trong bảng có nhãn `[TÍNH]` là kết quả chạy chính hàm trong repo (không phải comment).

---

## 1. Luồng chạy — 6 dòng

```
frame sạch (points N×5, boxes M×9)
   │
   ├─(1) wet ground ......... apply_wet_ground()        wet_ground.py:97   [CÓ gọi: plume.py:483]
   ├─(2) sinh cụm ........... PlumeState.spawn()        plume_state.py:257 [CÓ gọi: plume.py:534]
   ├─(3) trôi + tan ......... PlumeState.advance/prune  plume_state.py:371 / :417 [CÓ gọi: plume.py:496-499]
   ├─(4) raycast ............ raycast_frame()           raycast.py:102     [CÓ gọi: plume_transform.py:130]
   └─(5) points + detections  real_points ⧺ detections  plume_transform.py:139-142
```

- `inject_plume_stateful` là **đường đang sống**: `plume_transform.py:118` gọi nó, rồi `:130` gọi raycast.
- `inject_plume` (stateless) **mồ côi trong pipeline**: chỉ `spray/__init__.py:1` export và
  `scripts/probe_sspp_plume.py:129` + test gọi; không có transform nào dùng (xem §4).
- `raycast_frame` **không** nhận `injected` của `inject_plume_stateful` mà nhận `state.all_alive()`
  (`plume_transform.py:132`), tức cụm dạng **hình cầu**, không phải điểm đã materialise.
- `PlumeTransform` không được khai báo trong file config nào của repo (grep `PlumeTransform` chỉ ra
  `spray/plume_transform.py:58`, test và doc) — nó chỉ tự đăng ký qua `PIPELINES` nếu mmdet3d có mặt
  (`plume_transform.py:45-54`).

## 2. Sáu file và vai trò

| File | Vai trò | Dòng chính |
|---|---|---|
| `spray/plume.py` (740) | `PlumeConfig`, bảng đo, chuỗi rate×K, `inject_plume` + `inject_plume_stateful` | config `:61-153`; bảng `:24-47`; rate `:214`; K `:283-314`; stateless `:317`; stateful `:445` |
| `spray/plume_context.py` (314) | Hợp đồng dữ liệu mỗi frame: tốc độ, `wfh_mm`, `road_z_m`, seed | dataclass `:24`; `from_sample` `:106`; `seed_for` `:204`; validate `:259-265` |
| `spray/plume_state.py` (465) | Trạng thái qua frame: `SprayCluster`, spawn/advect/prune, gió, drag | hằng số `:61-101`; `spawn` `:257`; `advance` `:371`; `prune` `:417` |
| `spray/beam_model.py` (197) | Lưới tia đều + giao tia–cầu | lưới `:36-42`; `load_beam_table` `:57`; `ray_sphere_intersect` `:160` |
| `spray/raycast.py` (514) | `P_det`, suy hao, occlusion, giữ echo mạnh nhất | `P_det` `:47-52`; `raycast_frame` `:102`; suy hao `:251-253`; occlusion `:315-320` |
| `spray/wet_ground.py` (231) | Giảm cường độ mặt đường ướt (Fresnel/Snell) | config `:62-77`; `apply_wet_ground` `:97`; `_attenuate` `:175` |

Đọc theo thứ tự: `plume_context` → `plume_state` → `plume` → `beam_model` → `raycast` → `wet_ground`.

## 3. `PlumeConfig` nhóm theo nguồn

| Tham số | Giá trị | Nhãn + nguồn |
|---|---|---|
| `min_speed_kmh` | 40,0 | `[CODE]` `DetectionEnvironmentalEffects.cpp:502,:554` — `plume.py:96-99` |
| `cluster_count_velocity_offset_kmh` | 50,0 | `[CODE]` profile `num_clusters_velocity_offset_kmh` — `plume.py:103-105` |
| `lifetime_water_film_coeff` / `lifetime_base_s` | 0,02 / 0,2 | `[CODE]` `dee.cpp:530` — `plume.py:106-108` |
| `lifetime_max_age_factor` | 4,0 | `[CODE]` `dee.cpp:446` — `plume.py:109-110` |
| `cluster_radius_median_m` / `_sigma` | 0,30 / 0,8 | `[PAPER]` Linnhoff Fig. 5 (μ=−1,2, σ=0,8) — `plume.py:118-122` |
| `cluster_radius_bounds_m` | (0,10; 1,00) | `[CODE]` `dee.cpp:528` `std::min(1.0f, …)` — `plume.py:123-124` |
| `lateral_half_width_m` | 2,34 | `[ĐO]` p95 2,22 m trên 1.022 frame `cal`; đều ±a ⇒ a=2,34 — `plume.py:135-138` |
| `points_per_cluster_sigma` | 0,67 | `[CHỌN]` "chọn để p90 ~ 40" — `plume.py:111-116` (median 17 `[ĐO]` không còn dùng) |
| `radial_squash` | 0,885 | `[CHỌN]` hiệu chỉnh thực nghiệm để `r_range/r_extent`=1,28 `[ĐO]` ticket 16 — `plume.py:125-132` |
| `distance_range_m` / `height_range_m` | (1;10) / (0,2;2,0) | `[CHỌN]` — không có comment nguồn tại `plume.py:133-134` |
| `water_film_height_m` | 0,001 | `[CHỌN]` dataset không khai báo độ ướt — `plume.py:100-102` |
| `tail_block_width_m` | 3,4 | `[ĐO]` ticket 28b/29c — `plume.py:143-153` |
| `tail_block_height_frac` | (0,05; 0,92) | `[ĐO]` ticket 29e-c — `plume.py:143-153` |
| `_CLUSTER_VISIBLE_BY_SPEED` | xem §5 | `[ĐO]` DBSCAN 0,7°/minPts 3 trên `cal` — `plume.py:21-47` |
| `_POINTS_MEDIAN_BY_RANGE` | 30/20/14/10 | `[ĐO]` ticket 16 — `plume.py:11-19` |

## 4. Hai đường: stateless vs stateful

| Điểm | `inject_plume` (`plume.py:317`) | `inject_plume_stateful` (`plume.py:445`) |
|---|---|---|
| State qua frame | Không: dựng lại từ đầu mỗi frame — `plume.py:330-332` | Có: `PlumeState` giữ cụm, key `(scene_token, object_id)` — `plume_state.py:239` |
| Vệt sau xe | Không có; cụm rải quanh `box[:2]` theo `distance_range_m` — `plume.py:370-377` | Khối đuôi cố định sau đuôi xe — `plume.py:501-532` |
| Chiều cao | `rng.uniform(*height_range_m)` = 0,2–2,0 m — `plume.py:372` | 5–92 % chiều cao box, tính từ đáy box — `plume.py:513-516` |
| Số cụm | `round(rate×K)` mỗi frame — `plume.py:359` | `rate` cộng dồn qua `_spawn_credit` — `plume_state.py:300-302` |
| Raycast | Không đi qua raycast | Đi qua `raycast_frame(clean, state.all_alive(), …)` — `plume_transform.py:130-137` |

Khác phụ: stateful nhận `vehicle_class` (`plume.py:456`) và `wet_ground` (`plume.py:455,482`); stateless
không có cả hai (`plume.py:320-324`). Stateful in marker `PLUME_STATE` (`plume.py:611-620`).

## 5. Chuỗi đếm cụm: bảng → rate → ×K → visible

`visible_ref(v)` = nội suy tuyến tính bảng `cal`, dưới 50 km/h = 0 (`plume.py:199-211`).
`rate(v) = visible_ref(v) / K(T_ref)` với `T_ref` tại 1 mm, **không chứa `wfh`** (`plume.py:214-231`, `:49-54`).
`K = Σ_{k=0}^{⌊4T/Δt⌋} exp(−k·Δt/T)`, `Δt`=0,1 s `[CODE]` profile VLP-32 (`plume.py:56-58`, `:283-298`).

| v (km/h) | T (s) | K | rate | rate×K | visible Crafter | visible Golf |
|---|---|---|---|---|---|---|
| 50 | 0,20 | 2,513 | 1,663 | 4,180 | 4 | 4 |
| 60 | 0,40 | 4,456 | 2,538 | 11,310 | 11 | 9 |
| 80 | 0,80 | 8,373 | 2,630 | 22,020 | 22 | 13 |
| 100 | 1,20 | 12,278 | 2,382 | 29,240 | 29 | 18 |
| 130 | 1,80 | 18,184 | 0,973 | 17,690 | 18 | 17 |

Cột visible = `floor(rate×K + 0,5)` (`plume.py:247`); toàn bộ bảng là `[TÍNH]` từ `plume.py:263-314`.
`T = 0,02·wfh_mm·(v−50) + 0,2` (`plume.py:263-280`); tại `T`=0,2 s, `K` = 2,5133 ≈ **2,51** (`plume.py:304-309`).
Lưu ý: `inject_plume` gọi `cluster_count_for_speed(speed_kmh, cfg)` **không truyền** `vehicle_class`
(`plume.py:359`) ⇒ luôn dùng bảng `crafter` (`plume.py:250-260`); Golf sẽ sai số cụm — `scripts/probe_sspp_plume.py:349`.

## 6. Ba bẫy im lặng đã ghi trong code

| Bẫy | Hiện trạng | Trích |
|---|---|---|
| Dropout lifetime | Đã bỏ `age ~ U(0,4T)`; suy giảm nằm trong `K`; `clusters_dropped_lifetime` luôn 0 | `plume.py:162-163`, `:330-332` |
| `vz`=0 + bỏ trần chiều cao | `INITIAL_VZ_MAX_MPS = 0,0`; `prune(ceilings=…)` nhận tham số nhưng **bỏ qua** | `plume_state.py:86-92`, `:417-428` |
| Ngân sách điểm | `max(500, round(0,05·N_thật))`, thay trần tuyệt đối 2.000 (lỗi D7) | `plume.py:662-668` |

Hệ quả bẫy 2: chiều cao plume đến **thuần** từ khối đuôi (`plume.py:513-516`), không có luật xoá theo `z`.
Hệ quả bẫy 3: frame thưa (<10.000 điểm) luôn được ≥500 điểm plume; `stats.capped` báo số bị cắt (`plume.py:426-431`).

## 7. Còn nghi ngờ (mâu thuẫn — chưa tự quyết)

1. **Raycast "chưa nối"**: `raycast.py:4` viết "It is **not** wired into the generator yet", nhưng
   `plume_transform.py:130` đã gọi nó. Comment cũ, chưa cập nhật.
2. **`P_det` hai mô tả**: `plume_transform.py:15` nói `P_det = n/n_max`; `raycast.py:269-273` thực tế dùng
   `min(1, lognormal(−2,3; 1,1)) × exp(−age/T)`. Code là lognormal — docstring transform sai.
3. **`inject_plume_stateful` tạo điểm vô dụng**: `plume.py:551-571` materialise `injected` (hàng nghìn điểm),
   nhưng `plume_transform.py:129-142` chỉ dùng `points_clean` + `detections`, bỏ `result.points`/`injected`.
   Điểm này vẫn tốn CPU và vẫn bị ngân sách cắt, dù không đi ra output.
4. **Số điểm/cụm**: `plume_state.py:475-477` nói materialise theo `_POINTS_MEDIAN_BY_RANGE`, code gọi
   `_count_for_distance` (`plume.py:554`) — đúng, nhưng đây là đường output không dùng (xem #3).
5. **Khối đuôi cố định trong ego frame**: `inject_plume_stateful` lấy `box[:3]` mỗi frame và đặt khối sau
   đuôi (`plume.py:510-524`); `advance` trừ `ego_velocity` (`plume_state.py:407`). Đo thử 6 frame với box
   cố định x=23,2 m, ego=object=80 km/h: `x` của cụm sống tụt từ ~19,2 m xuống ~13,6 m — vệt đi **lùi** khỏi
   khối, không kéo dài phía sau xe. Cần người quyết định đây là hành vi mong muốn hay bug.
6. **`PlumeContext` không được dựng trong repo**: grep `PlumeContext.from_sample` chỉ thấy test
   (`tests/test_plume_context.py:63`); `plume_transform.py:99-103` đòi `results["plume_context"]` nhưng không
   có transform nào của repo tạo key này (`spray_context_transform.py` đã bị bỏ — `.hermes/plans/2026-11-15_232122-sspp-branch-cleanup.md:71`).
7. **`sensor_origin` trong `from_sample`**: lấy `lidar2ego[:3,3]` (`plume_context.py:148-157`), nhưng
   `sspp_adapter.build_info` đặt `lidar2ego = np.eye(4)` (`spray/sspp_adapter.py:202`) ⇒ origin = (0,0,0),
   không phải độ cao LiDAR. Chỉ ảnh hưởng nhánh placeholder `center=None` (`plume_state.py:343`).
8. **Docstring `test_plume_tail_block.py:3-4`** còn nói khối "height 1,5 m, bottom on the box bottom",
   trái với code `0,05–0,92` chiều cao box (`plume.py:153`) mà chính test `:87` khẳng định.
