# DISPATCH 29e — nối raycast vào PlumeTransform (A/B có attenuation thật)

**Cho:** CommandCode, `--yolo`, skill `tdd`.
**HEAD:** `1d3d3e2` (nhánh `main`).
**Ticket nguồn:** `.scratch/spray-augmentation/issues/29e-wire-raycast.md` — **đọc hết**, brief này chỉ
là thứ tự thi công + ranh giới. Ticket 29c
(`.scratch/spray-augmentation/issues/29-ray-casting-attenuation.md`, mục "Biên bản nghiệm thu PM")
chứa số đo PM vừa lấy — đọc phần đó để biết cái gì đã đạt, cái gì còn nợ.

## 0. Bối cảnh

`spray/raycast.py` đã có `raycast_frame` (lưới đều 54.750 tia, `P_det = n/n_max`, attenuation
`e^(−2·0,02·L)`, strongest-return, marker `PLUME_RAYCAST`) nhưng **không ai gọi**. `PlumeTransform`
rơi vào nhánh stateless `inject_plume` vì `results["plume_context"]` không bao giờ được set. Kết quả:
A/B v1/v2 không có attenuation lên điểm thật — mất đúng cơ chế paper mô tả.

Nhiệm vụ: dựng context trong pipeline, nối raycast, rồi calibrate nhánh stateful cho khớp bảng đo
`cal`. Hai checkpoint E1 (plumbing) → E2 (calibration). Sau mỗi checkpoint `pytest -q tests/` phải
xanh; ghi lại số passed.

## 1. Số bàn giao (đích, `[ĐO]` trên `cal`)

| km/h | 50 | 70 | 100 | 130 |
|---|---:|---:|---:|---:|
| Crafter cụm/frame | 4,18 | 17,42 | 29,24 | 17,69 |
| Golf cụm/frame | 3,62 | 11,36 | 18,07 | 16,64 |
| det/cụm (Crafter) | 7,8 | 5,1 | **19,4** | **36,2** |

Chiều cao detection trên mặt đường: p5/med/p95 = **0,111 / 1,197 / 2,264 m** (±0,20 m).
Tổng điểm spray/frame: **570–1.555**. p95\|y\| của điểm sinh ra: **2,308 m** (±10 %).
Latency: **< 100 ms/frame** ở 100 cụm.

Số đo PM hiện tại trên nhánh stateless (để so): cụm/frame 4/17/29/18 ✓, điểm/cụm 12,8–15,2 ✗,
h p5 0,64–0,72 ✗, p95\|y\| 2,12–2,29 ✓, 17–60 ms/frame.

## 2. E1 — plumbing (làm đúng thứ tự này)

1. `scripts/build_plume_speed_index.py`: đọc `nuscenes_infos_*.pkl`, gom theo `scene_token`, sắp theo
   `timestamp`, `ego_speed_mps = ‖t_{k+1} − t_k‖ / Δt` từ `ego2global_translation`; frame cuối lấy
   giá trị frame trước; ghi JSON `{lidar_path: {ego_speed_mps, object_speed_mps}}`.
   `object_speed_mps = ego_speed_mps` — **có căn cứ**: ticket 25 đo ego = object trên cả 207 scene
   SemanticSpray. Comment ghi rõ nguồn.
2. `SprayContextTransform` (file mới `spray/spray_context_transform.py`, đăng ký `PIPELINES`):
   `results["plume_context"] = PlumeContext.from_sample(results, epoch=…, wfh_mm=cfg, road_z_m=cfg,
   frame_index=results["sample_idx"], ego_speed_mps=sidecar[results["lidar_path"]])`.
   Thiếu key ⇒ raise nêu tên key. Không bắt buộc `results` có `ego_pose` nếu có `ego2global`.
3. `PlumeTransform` (`spray/plume_transform.py:99–122`): có context ⇒ **luôn** stateful rồi
   `raycast_frame(...)`; `points = concat(real_attenuated, detections)`; `points_clean` = bản gốc
   byte-equal; `spray_stats` cộng `det/beams_hit/att_m_total/att_real_points`; context None ⇒
   `RuntimeError`. Bỏ nhánh rơi im lặng về stateless.
4. `spray/ab_config.py` + `kaggle/train/ab_run.py`: arm B thêm `SprayContextTransform` **trước**
   `PlumeTransform`, kèm đường dẫn sidecar.
5. `docs/PROJECT.md:53`: sửa sơ đồ cho khớp code sau khi nối.

Test E1: marker đủ 6 khoá; `points_clean` byte-equal; có `att_real_points > 0`; context None ⇒
`RuntimeError`; `grep raycast_frame` thấy call site.

## 3. E2 — calibrate stateful

6. `cluster_count_for_speed_abs` (`spray/plume_state.py:149`) dùng bảng `cal` như
   `plume.py:176–252` (`rate = visible_ref/K(T_ref)`, `visible = round(rate·K(T))`), bảng riêng
   Crafter/Golf; `T` giữ nguyên.
7. Đo lại trên stateful: cụm/frame 9 mốc × 2 lớp (±20 %), det/cụm @100 và @130, chiều cao
   p5/med/p95, tổng điểm/frame, latency. Đo trên **30 frame/scene × 3 scene** mỗi tốc độ (đừng đo
   1 frame — PM đã bị nhiễu vì vậy).
8. Cụm trôi xa làm h p95 vượt trần (worker đo 3,216 m, range median 27,7/48,0 m): xử lý bằng
   `ttl`/prune/block, **không** bằng `initial_vz` tuỳ tiện; ghi số đo dẫn tới quyết định.
9. Chỉ được chỉnh median `points_per_cluster`/`_POINTS_MEDIAN_BY_RANGE` và bán kính cụm để khớp
   điểm/cụm; **không** đổi dạng `P_det`.

## 4. Cấm

- Không đụng code cổng 29d (`spray/semantic_split.py`, `scripts/semantic_spray_split.py`,
  `spray/config/semantic_spray_split.yaml`, `tests/test_semantic_split.py`,
  `docs/measurements/semantic-spray-cal-vs-heldout.md`).
- Không dùng `held-out` chọn tham số. Không đổi `T`, `C`, `age > 4T`, `wfh = 1 mm`.
- Không đổi dạng `P_det`. Không nới/xoá test cũ (mâu thuẫn ⇒ báo).
- Không train, không chạy Kaggle, **không commit**.

## 5. Lệnh smoke

```bash
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/test_plume_transform.py tests/test_raycast.py tests/test_plume.py
grep -rn "raycast_frame" --include=*.py spray/
```

Script đo đặt ở `/tmp`, không thêm file đo vào repo trừ khi ticket yêu cầu.

## 6. PM sẽ nghiệm thu độc lập

`git diff --stat` đúng phạm vi; pytest ≥280; tự chạy một frame thật đọc marker + đếm `att_real_points`;
tự đo lại cụm/frame × 9 mốc, det/cụm, ba phân vị chiều cao, latency; đối chiếu bảng. Chỗ lệch ghi
thành mục "chưa khớp", không tự sửa code.