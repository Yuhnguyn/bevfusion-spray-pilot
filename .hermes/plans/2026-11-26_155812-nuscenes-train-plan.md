# Kế hoạch: train BEVFusion trên nuScenes với plume augmentation, eval trên SSPP

> **PM note:** File này là plan, không phải brief. Task nào giao CommandCode sẽ được tách thành
> `.scratch/<feature>/issues/<NN>-<slug>.md` theo `coding-agent-cli-handoff`.

**Mục tiêu (một câu):** fine-tune BEVFusion LiDAR-only trên **nuScenes** với spray plume tổng hợp
chèn vào lúc train, để detector **chịu được nhiễu bụi nước**; đo lợi ích bằng **paired A/B** và
eval chuyển domain trên **SSPP thật**.

**Khác với `main`:** bên `main` train + eval đều trên nuScenes (val 196 frame). Plan này train
nuScenes nhưng **eval chuyển domain trên 36 scene SSPP có box** — vì đó là nơi có spray thật để
chấm. Không restore dây train cũ; dựng lại theo nhu cầu, bám `spray/` hiện tại (A8/A9/A10).

---

## 0. Ba số đo chặn đường — đọc trước khi làm bất cứ gì

Đây là các phát hiện tôi đo trên máy này hôm nay. Chúng quyết định thứ tự công việc.

### 0.1 Generator hiện tại sinh **0 cụm** ở mọi tốc độ dưới 50 km/h `[ĐO]`

Chạy `spray.plume.visible_cluster_count_for_speed` với `PlumeConfig()` mặc định:

| v (km/h) | 0–40 | 45 | 49 | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cụm/frame | **0** | 0 | 0 | 9 | 14 | 25 | 36 | 33 |

Nguyên nhân: bảng `_CLUSTER_VISIBLE_BY_SPEED` bắt đầu ở mốc **50 km/h** và
`cluster_visible_target_for_speed` trả `0.0` dưới mốc đầu (`spray/plume.py:176`).
`PlumeConfig.min_speed_kmh = 40.0` là cửa thứ hai, cũng chặn.

**Hệ quả cho nuScenes:** nuScenes là đô thị, tốc độ ego trung vị thấp. Nếu dùng nguyên generator
này trên nuScenes thì **đa số frame không được augment gì**, và arm B ≈ arm A ⇒ thí nghiệm null
ngay từ thiết kế, không phải vì augmentation vô dụng.

Đây không phải bug cần "sửa cho đúng paper" — paper chỉ định lượng 50–130 km/h. Đây là **quyết
định miền** phải chốt trước khi train.

### 0.2 Miền hình học sinh plume không khớp `point_cloud_range` của nuScenes `[ĐO/CODE]`

| | giá trị | nguồn |
|---|---|---|
| `PlumeStateConfig.min_range_m` | **2.5** | `spray/plume_state.py:136` |
| `PlumeStateConfig.max_range_m` | **50.0** | `spray/plume_state.py:137` |
| `PlumeConfig.point_cloud_range` | ±54 m | `spray/plume.py:89` |
| nuScenes `point_cloud_range` | **±51.2 m** | `mit/bevfusion/configs/nuscenes/default.yaml:9` |
| nuScenes `voxel_size` | 0.1 × 0.1 × 0.2 | cùng file |

Plume sinh tới 50 m, voxel grid nuScenes cắt ở 51.2 m ⇒ **vừa trong**. Không cần đổi, nhưng phải
assert chứ không để ngầm.

### 0.3 Quy ước box nuScenes **khác** adapter SSPP — nếu dùng nguyên sẽ đặt plume sai chỗ `[ĐO]`

`PlumeTransform`/`inject_plume_stateful` đọc box theo quy ước **adapter SSPP**
(`spray/plume.py:307` docstring, `spray/sspp_adapter.py:117-141`):

```
box = [x, y, z_ĐÁY, DÀI(dọc yaw), RỘNG(ngang yaw), CAO, yaw, vx, vy]
```

nuScenes converter của pin `da93b27` sinh ra theo quy ước mmdet3d:

```
gt_boxes = [x, y, z_TÂM, w, l, h, yaw]      nuscenes_converter.py:250,276
```

Tôi tính thử một box xe 4,60 × 1,90 × 1,75 m ở 10 m:

| | plume tính ra | đúng phải là | lệch |
|---|---|---|---|
| `length` (= `box[3]`) | 1,90 m (chiều **rộng**) | 4,60 m | khối sinh ngắn 2,7 m |
| `z` (= `box[2]`) | 0,900 m (tâm) | 0,025 m (đáy) | cao hơn **0,87 m** |
| tâm khối sinh | lùi 0,95 m sau tâm | lùi 2,30 m sau tâm | **1,35 m** |

Hệ quả nếu không đổi: plume phun **vào trong thân xe** và **lơ lửng trên mặt đường 0,87 m** —
đúng hai thứ làm hỏng cả thí nghiệm mà không có lỗi nào bật ra.

Thêm nữa `yaw` của nuScenes là `-rots - π/2` (mmdet3d), còn adapter SSPP dùng thẳng `rotation3D.z`.
Phải kiểm bằng một frame thật (Task 3), không suy từ công thức.

### 0.4 Chưa có gì để train trên máy này `[ĐO]`

```
torch 2.2.2 (CPU, x86_64, 4 core, 8.6 GB RAM)   ← không có CUDA, không có MPS
nuscenes / mmdet3d / mmcv / spconv              ← MISSING cả 4
data/  = SemanticSprayDataset 16G + roadspray 18G + 2 checkpoint
         nuScenes: KHÔNG có
đĩa trống: 28 GiB   ← full nuScenes ~300 GB không vừa; mini ~4 GB vừa
```

⇒ Train **phải chạy trên Kaggle**, không chạy local. Local chỉ dùng để unit test + build config.

---

## 1. Quyết định phải chốt trước khi viết code (PM + user)

Ba câu hỏi dưới đây đổi hẳn khối lượng công việc. Đề xuất của tôi ở cột "mặc định".

### QĐ-A. Xử lý chuyện "nuScenes toàn tốc độ thấp" thế nào?

| phương án | việc phải làm | rủi ro |
|---|---|---|
| **A1 (mặc định)** Lọc frame train theo tốc độ ego ≥ 45 km/h | thêm 1 filter vào dataset; mất phần lớn nuScenes | nuScenes urban hiếm khi >45; có thể chỉ còn vài nghìn frame |
| A2 Nới bảng cụm/frame xuống dưới 50 km/h bằng ngoại suy | thêm mốc vào `_CLUSTER_VISIBLE_BY_SPEED`, đánh dấu `[CHỌN]` | bịa số ngoài miền đo; mọi con số downstream mất nguồn paper |
| A3 Train nuScenes ở mọi tốc độ, chấp nhận augment thưa | không sửa gì; đo `% frame được augment` | arm B chỉ khác arm A ở phần nhỏ frame ⇒ effect bị pha loãng |

**Đo trước khi chọn:** đếm phân bố tốc độ ego trong nuScenes val (196 frame đã lọc d≤50 m bên
`main`) và trong mini. Nếu p50 < 30 km/h thì A1 gần như vô nghĩa ⇒ phải chọn A2 hoặc A3. Task 1
làm phép đo này **trước** mọi thứ khác.

### QĐ-B. Eval chính đặt ở đâu?

| phương án | trả lời câu hỏi gì | chi phí |
|---|---|---|
| **B1 (mặc định)** 3-fold leave-speed-out trên 36 scene SSPP | "train có spray tổng hợp → bớt FP trên spray **thật** không" | đã có sẵn split + protocol (ADR-0006) |
| B2 nuScenes val 196 frame (như `main`) | "có mất gì trên domain gốc không" | chỉ 196 frame, CI rất rộng |
| B1 + B2 | cả hai | +1 lần eval mỗi checkpoint |

Đề xuất: **B1 là hàng quyết định, B2 là chốt chặn** (giống `docs/PROJECT.md` §5 bên `sspp`).

### QĐ-C. Có dùng camera branch không?

Dataset SSPP không có calib 6 view ⇒ eval SSPP **buộc** LiDAR-only. Nếu train nuScenes có camera
thì checkpoint lệch kiến trúc với lúc eval. Đề xuất: **train LiDAR-only** (`voxelnet_0p075`,
`lidar-only-det.pth`), khớp `scripts/sspp_infer.py:88`.

→ Cần user chốt. Nếu chọn dùng camera thì phải bỏ eval SSPP hoặc chấp nhận bỏ nhánh camera lúc
eval, và phải nói rõ trong báo cáo.

---

## 2. Kiến trúc thí nghiệm

```
nuScenes mini/full ──┐
  gt_boxes + ego_pose│
  + velocity         ├─→ SprayContextTransform (dựng mới cho nuScenes)
                     │      ↓ plume_context
                     ├─→ PlumeTransform (ĐÃ CÓ, không sửa)
                     │      ↓ points (có plume) + points_clean
                     ├─→ BEVFusion voxelnet_0p075 (lidar-only)
                     │
                     └─→ 3-fold eval trên 36 scene SSPP (không augment)
```

Hai arm, khác đúng **một** đường trong `train_pipeline`:

| | Arm A (đối chứng) | Arm B |
|---|---|---|
| frame nền | nuScenes, **không** bỏ gì (không có label spray) | giống hệt |
| plume | **không** | **có**, `p = 0.5`/frame |
| steps / lr / batch / seed | 2000 / 1e-4 / 2 / 0 | giống hệt |

Khác `main` ở chỗ: bên `main` nền là `points[labels != 2]` của SSPP; ở đây nền là nuScenes nguyên
bản (không có spray thật để bỏ) ⇒ **arm A sạch theo nghĩa nuScenes**, còn arm B có plume tự sinh.

---

## 3. Task breakdown (theo thứ tự, mỗi task một commit)

Task 1–2 là **đo**, phải xong trước khi viết dòng code nào. Task 3+ mới là code.

### Task 1 — Đo phân bố tốc độ ego trong nuScenes [chặn QĐ-A]

**Objective:** biết bao nhiêu % frame nuScenes có ego speed ≥ 45 km/h.

**Files:**
- Create: `scripts/measure_nuscenes_ego_speed.py`
- Output: `.scratch/nuscenes-train/ego_speed_stats.json`

**Cách làm:** đọc `samples/LIDAR_TOP` + `ego_pose` của nuScenes **mini** (4 GB, tải ở Task 0).
Tính `v = ‖p_t − p_{t−1}‖ / Δt` trong cùng scene, lấy histogram.

**Xong khi:** in được p10 / p50 / p90 + `% frame ≥ 45 km/h`, và kết luận bằng một dòng:
nếu `%(≥45) < 20` thì A1 chết, phải chọn A2/A3.

### Task 2 — Đo điện năng: plume sinh ở tốc độ thấp thực sự ra bao nhiêu điểm

**Objective:** kiểm chứng 0.1 bằng **số điểm**, không chỉ số cụm — vì raycast mới là thứ tạo điểm.

**Files:**
- Create: `scripts/measure_plume_at_low_speed.py`
- Output: `.scratch/nuscenes-train/low_speed_plume.json`

**Cách làm:** dựng `PlumeContext` tổng hợp (ego 20/30/40 km/h, 1 box cách 20 m), gọi thẳng
`raycast_frame` với `state.select_alive()` sau vài bước `spawn`, đếm `detections`.

**Xong khi:** bảng `v → det/frame`; nếu 0 ở mọi vận tốc dưới 50 thì QĐ-A không thể chọn A3.

### Task 3 — `SprayContextTransform` cho nuScenes

**Objective:** sinh `plume_context` + **chuẩn hoá box** từ info dict nuScenes rồi mới giao cho
`PlumeTransform`.

**Files:**
- Create: `spray/nuscenes_context_transform.py`
- Test: `tests/test_nuscenes_context_transform.py`

**Phần 1 — box (mục 0.3):** hàm `nuscenes_boxes_to_plume(gt_boxes)` đổi
`[x,y,z_tâm,w,l,h,yaw] → [x,y,z_tâm−h/2,l,w,h,yaw,vx,vy]`, cộng vận tốc từ `gt_velocity`.
Test bằng một box xe thật: assert `box[2] == z_tâm − h/2`, `box[3] == l` (không phải `w`), và
`yaw` khớp hướng xe khi so với 2 keyframe liên tiếp.

**Phần 2 — context:**

| trường `PlumeContext` cần | nuScenes có ở đâu | ghi chú |
|---|---|---|
| `scene_token` | `info["scene"]` | ok |
| `ego_speed_mps` | **không có sẵn**; tính `‖t_{k+1}−t_k‖/Δt` từ `ego2global_translation` của 2 keyframe cùng scene (sort theo `timestamp`), frame cuối dùng lại frame trước | đúng công thức `scripts/build_plume_speed_index.py` bên `main` |
| `object_speed_mps` | `info["gt_velocity"]` (2 cột, đã ở LiDAR frame) | `nuscenes_converter.py:265-273` |
| `object_velocity_ego_mps` | cùng nguồn, thêm `z = 0` | để hết cờ `velocity_assumed` |
| `wfh_mm` | **không có** | `sample_wfh_mm(scene_token, ...)` như SSPP |
| `road_z_m` | **không có** | phải **đo** từ điểm mặt đất từng frame (percentile thấp của z trong annulus 8–15 m), không dùng hằng số |
| `ego_pose` | `ego2global` (đảo dấu như `PlumeContext.from_sample`) | có sẵn |
| `sensor_origin` | `lidar2ego_translation` | có sẵn |

**Xong khi:** test dựng context + box từ một info dict nuScenes thật (đóng gói fixture nhỏ), gọi
`PlumeTransform` được, `points_clean` đúng bằng input, và **plume nằm sau đuôi xe + sát mặt đường**
(assert bằng số: tâm cụm `x < rear_x`, `z − road_z < 1,5 m`).

### Task 4 — Wire vào `train_pipeline` (arm builder)

**Objective:** một hàm `build_cfg(arm)` trả config mmdet3d, và một hàm `diff_paths()` chứng minh
hai arm khác **đúng một** đường.

**Files:**
- Create: `spray/nuscenes_ab_config.py`
- Test: `tests/test_nuscenes_ab_config.py`

**Xong khi:** `diff_paths(cfg_A, cfg_B) == ["train_pipeline.<i>.type"]`, i là vị trí `PlumeTransform`.
Test phải FAIL nếu ai xoá `PlumeTransform` khỏi arm B.

### Task 5 — Tải nuScenes mini + chạy smoke trên Kaggle

**Objective:** chứng minh dây chạy end-to-end trước khi tốn GPU cho train thật.

**Files:**
- Create: `kaggle/train_nuscenes/smoke.py`, `kernel-metadata.json`, `task_args.txt`

**Dataset nguồn:** `aadimator/nuscenes-mini` (đã có trong metadata cũ bên `main`).
Bootstrap môi trường: **dùng lại `kaggle/e2e/main.py` bên `main`** (Python 3.8 + mmcv-full 1.4.0 +
mmdet3d `da93b27`), đóng gói thành Kaggle dataset code như `gate_c` đang làm — không viết lại.

**Xong khi:** kernel log có `SMOKE_OK`, và in ra `n_points` arm A vs arm B cho cùng frame:
arm B **lớn hơn**.

### Task 6 — Chạy A/B trên Kaggle (GPU)

**Objective:** hai checkpoint `arm_a.pth`, `arm_b.pth`, cùng ngân sách 2000 bước.

**Xong khi:** cả hai kernel `COMPLETE`, mỗi cái log `n_points` mỗi 50 bước, và
`AB_TRAIN_OK arm=A|B steps=2000`.

### Task 7 — Eval chuyển domain trên 36 scene SSPP

**Objective:** chạy 3-fold leave-speed-out cho **cả 3** checkpoint (Model 0, Arm A, Arm B).

**Files:**
- Modify: `scripts/sspp_infer.py` (thêm `--checkpoint` nhận file ngoài `data/`)

**Xong khi:** bảng `FP/frame` + `SPF proxy/frame` cho 3 checkpoint × 3 fold, paired theo scene,
kèm effect size + CI95 theo ADR-0006 D3. **Không** báo pass/fail.

---

## 4. File dự kiến đổi

| file | mới/sửa | ghi chú |
|---|---|---|
| `scripts/measure_nuscenes_ego_speed.py` | mới | Task 1, chỉ đo |
| `scripts/measure_plume_at_low_speed.py` | mới | Task 2, chỉ đo |
| `spray/nuscenes_context_transform.py` | mới | Task 3 |
| `spray/nuscenes_ab_config.py` | mới | Task 4 |
| `kaggle/train_nuscenes/*` | mới | Task 5–6 |
| `scripts/sspp_infer.py` | sửa nhỏ | Task 7, chỉ thêm `--checkpoint` |
| `docs/PROJECT.md` | sửa | thêm §"miền nuScenes" khi có số |

**Không** đụng: `spray/plume.py`, `spray/plume_state.py`, `spray/raycast.py`, `spray/beam_model.py`.
Nếu thấy cần sửa generator ⇒ dừng, báo PM (đó là quyết định miền, không phải bug).

---

## 5. Test / verify

| task | lệnh | kỳ vọng |
|---|---|---|
| baseline | `/opt/anaconda3/bin/python -m pytest -q` | **200 passed** (đo hôm nay) |
| 3 | `pytest tests/test_nuscenes_context_transform.py -q` | pass, và test FAIL nếu xoá `points_clean` |
| 4 | `pytest tests/test_nuscenes_ab_config.py -q` | `diff_paths` trả đúng 1 path |
| 5 | Kaggle kernel log | `SMOKE_OK`, `n_points_B > n_points_A` |
| 7 | `sspp_infer.py --dry-run` | in bảng ước lượng phút trước khi tốn GPU |

---

## 6. Rủi ro

| # | rủi ro | dấu hiệu | xử lý |
|---|---|---|---|
| R1 | nuScenes quá chậm ⇒ plume gần như không xuất hiện | Task 1 ra `%≥45 < 20` | chọn QĐ-A2 (ngoại suy bảng, ghi `[CHỌN]`) hoặc bỏ hướng nuScenes |
| R1b | **box quy ước sai** ⇒ plume phun vào thân xe, lơ lửng 0,87 m | test Task 3 không assert được `box[3]==l` | Task 3 Phần 1 làm **trước** phần context, test bằng box thật |
| R2 | Train nuScenes 2000 bước không đủ để thấy effect | arm A vs Model 0 gần như bằng nhau | tăng steps, hoặc giảm kỳ vọng và báo cáo effect size thay vì pass/fail |
| R3 | `road_z_m` của nuScenes khác SSPP (mặt đường phẳng vs dốc) | plume lơ lửng hoặc chìm | Task 3 phải **đo** `road_z_m` từng frame, không dùng hằng số |
| R4 | Checkpoint lệch kiến trúc (camera vs lidar-only) | `sspp_infer.py` raise `GATE_C_FAILED` | QĐ-C: chốt LiDAR-only từ đầu |
| R5 | Kaggle quota GPU | kernel không start | chạy mini trước, full sau (đã có skill `kaggle-kernel-gpu-jobs`) |

---

## 7. Câu hỏi mở — cần user trả lời trước Task 1

1. **QĐ-A**: chọn A1 (lọc ≥45 km/h), A2 (ngoại suy bảng xuống thấp), hay A3 (chấp nhận thưa)?
   Đề xuất: làm Task 1 trước, rồi quyết bằng số.
2. **QĐ-B**: eval chính là 36 scene SSPP (B1), nuScenes val (B2), hay cả hai?
   Đề xuất: B1 + B2 làm chốt chặn.
3. **QĐ-C**: train LiDAR-only (khớp eval SSPP) hay fusion (mất eval SSPP)?
   Đề xuất: LiDAR-only.
4. Dùng **mini** (4 GB) hay **full** (300 GB) — full thì phải dùng Kaggle dataset có sẵn, không
   tải về máy.
