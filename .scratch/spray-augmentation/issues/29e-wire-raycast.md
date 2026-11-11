# 29e: nối `raycast_frame` vào `PlumeTransform` — A/B có attenuation thật

**Type:** task
**Status:** ready-for-agent
**Blocked by:** 29c (xong một phần, commit `1d3d3e2`)
**Chủ:** CommandCode. PM: Hermes.

## Vì sao có ticket này

Ticket 29c sửa generator nhưng khi nghiệm thu PM phát hiện: **`raycast_frame` chưa được nối vào
pipeline**. `grep -rn raycast_frame --include=*.py` chỉ ra định nghĩa (`spray/raycast.py:90`) và
test; `PlumeTransform` (`spray/plume_transform.py:99–122`) chỉ gọi `inject_plume` hoặc
`inject_plume_stateful`, và **không file nào set `results["plume_context"]`** ⇒ mọi lần chạy A/B
đều rơi vào nhánh stateless.

Hệ quả với thí nghiệm: attenuation `e^(−2·0,02·L)` **không** áp lên điểm thật (paper §III-B: tia
đi qua plume bị yếu đi, điểm thật phía sau bị giảm intensity), `P_det = n/n_max` mỗi tia không chạy,
strongest-return mỗi beam không chạy, marker `PLUME_RAYCAST` không in. Nghĩa là A/B v2 vẫn đo một
augmentation "chỉ thêm điểm", không phải cơ chế paper mô tả — đó là một phần lý do v1 cho kết quả
null.

## Hợp đồng đã có (không viết lại)

```python
# spray/raycast.py
raycast_frame(points, clusters, *, table, road_z_m, rng, config=None, capped=0) -> RaycastResult
#   RaycastResult(detections: (K,5), real_points: (N,5), stats: RaycastStats)
#   real_points = điểm thật đã bị attenuation + bị occlusion bỏ đi
#   detections  = x, y, z, intensity(=0), ring(=beam id)

# spray/plume_context.py
PlumeContext.from_sample(sample, *, epoch, wfh_mm, road_z_m, frame_index, ego_speed_mps=None)
#   cần các key: scene_token, timestamp, (ego_pose | ego2global),
#                (sensor_origin | lidar2ego), ego_speed_mps, object_speed_mps
#   trả PlumeContext hoặc raise PlumeContextError liệt kê key thiếu
```

`raycast_frame` hiện đã: lưới đều `0,333° × 0,197307°` (30 × 1.825 = 54.750 tia), lọc cụm theo
hộp góc trước khi cast, `intensity = 0` cho detection, in marker 6 khoá
(`PLUME_RAYCAST beams= hit= det= att_m= capped= ms=`). **Không sửa các phần này** trừ khi test đỏ.

## Việc phải làm

### E1 — dựng context + nối raycast (plumbing)

1. **Nguồn tốc độ.** Infos nuScenes (chuẩn MIT `create_data.py`) có `scene_token`, `timestamp`,
   `ego2global_translation/rotation`, `lidar2ego_translation/rotation`, `lidar_path`; **không** có
   `ego_speed_mps` / `object_speed_mps`. Ba cách, chọn **cách A**:
   - **A (chọn): sidecar index offline.** Script `scripts/build_plume_speed_index.py` đọc infos
     `.pkl`, gom theo `scene_token`, sắp theo `timestamp`, tính
     `ego_speed_mps = |t_{k+1} − t_k| / Δt` từ `ego2global_translation`; ghi
     `{lidar_path: {"ego_speed_mps": …, "object_speed_mps": …}}` ra JSON. Key là `lidar_path`
     nên **an toàn với shuffle** (không phụ thuộc thứ tự frame lúc train).
   - B (không chọn): cache theo `scene_token` trong transform — sai khi `ShuffleDataset` đảo thứ tự.
   - C (không chọn): suy tốc độ trong transform từ `can_bus` — config A/B không bật `can_bus`.
   `object_speed_mps = ego_speed_mps` là **có căn cứ**: ticket 25 đo ego speed = object speed trên
   cả 207 scene SemanticSpray. Ghi comment nêu rõ nguồn này.
   Frame cuối của mỗi scene không có `k+1` ⇒ lấy tốc độ của frame trước đó (không để trống).
2. **`wfh_mm` và `road_z_m` là tham số của thí nghiệm, không phải của scene.** Lấy từ config
   (`PlumeConfig.water_film_height_m`, `road_z_m` truyền vào transform), mặc định `wfh = 1,0 mm`.
   Không suy từ dữ liệu.
3. **Transform mới** `SprayContextTransform` (đặt trong `spray/plume_transform.py` hoặc file mới
   `spray/spray_context_transform.py`, đăng ký vào `PIPELINES` như `PlumeTransform`):
   - đọc `results` → `PlumeContext.from_sample(...)` với `frame_index = results["sample_idx"]`,
     `epoch = results.get("epoch", 0)`, `ego_speed_mps` lấy từ sidecar theo `results["lidar_path"]`;
   - ghi `results["plume_context"] = ctx`; trả `results`.
   - thiếu key nào ⇒ **raise** kèm tên key (không im lặng bỏ qua).
4. **Nối raycast trong `PlumeTransform`** (`spray/plume_transform.py:99–122`):
   - khi có context ⇒ **luôn** đi nhánh stateful, sau đó gọi
     `raycast_frame(clean_points, state.all_alive(), table=<lưới đều>, road_z_m=ctx.road_z_m,
     rng=…, capped=stats.capped)`;
   - `points` = `concat(raycast.real_points, raycast.detections)` (đúng thứ tự này, điểm thật trước);
   - `points_clean` = **bản gốc byte-equal** (không bị attenuation, không bị bỏ điểm);
   - `spray_stats` cộng thêm `att_m_total`, `att_real_points`, `det`, `beams_hit`;
   - marker do `raycast_frame` in, mỗi frame gọi một lần — không in thêm marker thứ hai.
   - **Bỏ nhánh stateless im lặng**: nếu `context is None` thì raise
     `RuntimeError("PlumeTransform requires plume_context; enable SprayContextTransform")`.
     Giữ `inject_plume` cho test/script, nhưng transform không được tự rơi về đó.
5. **Cấu hình A/B**: arm B phải có `SprayContextTransform` **trước** `PlumeTransform` trong
   pipeline slice (`spray/ab_config.py` + `kaggle/train/ab_run.py` + test tương ứng); thêm tham số
   đường dẫn sidecar JSON. Cập nhật `docs/PROJECT.md:53` cho khớp code thật sau khi nối.

### E2 — calibrate nhánh stateful cho khớp `cal`

Sau E1, A/B chạy stateful. Nhánh này **chưa** được calibrate ở 29c (worker đã báo đúng) nên phải
làm, nếu không thì cụm/frame vọt lên 184–436 như v1:

6. `cluster_count_for_speed_abs` (`spray/plume_state.py:149`) đang là
   `(0,2·wfh+0,1)·(v−50)` [CODE dee.cpp] ⇒ thay bằng bảng đo `cal` như
   `cluster_count_for_speed` ở `plume.py:176–252`: `rate(v) = visible_ref(v)/K(T_ref)`,
   `visible = round(rate × K(T(wfh,v)))`, bảng riêng Crafter/Golf. `T` giữ nguyên.
7. **Hình học và độ cao**: block `frac = (0,05; 0,92)` chiều cao box đã có; kiểm phân vị chiều cao
   của **detection** trên 30 frame/scene × 3 scene/tốc độ, đích `p5/med/p95 = 0,111/1,197/2,264 m`
   (±0,20 m mỗi phân vị). Nếu lệch vì cụm trôi lên (worker đo range median 27,7/48,0 m,
   h p95 3,216 m) thì xử lý bằng **prune/`ttl` và block**, không bằng `initial_vz` tuỳ tiện:
   ghi số đo dẫn tới quyết định.
8. **Điểm/cụm và tổng điểm**: đích det/cụm median `15–25` @100 km/h và `29–43` @130 km/h (đo `cal`
   19,4 và 36,2); tổng điểm spray/frame `570–1.555`. Chỉ được chỉnh median
   `points_per_cluster`/`_POINTS_MEDIAN_BY_RANGE` và bán kính cụm; **không** đổi dạng `P_det`.
9. **Latency**: < 100 ms/frame ở 100 cụm, đo `time.perf_counter`, in số. Nếu vượt, dùng hai luật
   `dee.cpp:232–238` (lọc beam theo cửa sổ azimuth của cụm; bỏ cụm sau mặt phẳng cảm biến).

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ **280 passed, 4 skipped**.
- [ ] `grep -rn 'raycast_frame' --include=*.py` có **call site** trong `spray/plume_transform.py`.
- [ ] Test: frame có context ⇒ marker `PLUME_RAYCAST` in đúng 6 khoá; `det` khớp số detection.
- [ ] Test: `points_clean` **byte-equal** với input; `points` = real (đã attenuate) + det.
- [ ] Test: có ít nhất một điểm thật bị **giảm intensity** (`att_real_points > 0`) trong frame có plume.
- [ ] Test: `context is None` ⇒ `RuntimeError`, không rơi về stateless.
- [ ] Cụm/frame stateful khớp bảng `cal` trong **±20 %** ở 9 mốc × 2 lớp.
- [ ] det/cụm median trong `15–25` @100 và `29–43` @130; tổng điểm/frame `570–1.555`.
- [ ] Chiều cao detection p5/med/p95 = `0,111/1,197/2,264 m`, lệch ≤ `0,20 m` mỗi phân vị.
- [ ] Latency < 100 ms/frame @100 cụm, in số thật.
- [ ] Biên bản trong ticket: bảng đo trước/sau + mục "chưa khớp".

## Cấm

- Không sửa `spray/semantic_split.py`, `scripts/semantic_spray_split.py`,
  `spray/config/semantic_spray_split.yaml`, `tests/test_semantic_split.py`,
  `docs/measurements/semantic-spray-cal-vs-heldout.md` (cổng 29d đã đóng).
- Không dùng `held-out` để chọn tham số.
- Không đổi `T`, `C = −0,15`, ngưỡng `age > 4T`, `wfh` mặc định 1 mm.
- Không đổi dạng `P_det` (lognormal bốc `n` mỗi cụm, Bernoulli mỗi tia `n/n_max`).
- Không nới test cũ; mâu thuẫn thì báo, không tự xoá.
- Không train, không chạy Kaggle, không commit.