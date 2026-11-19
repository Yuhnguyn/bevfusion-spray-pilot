# Gate C runbook — synthetic plume vs detector FP/recall (SSPP, Model 0 zero-shot)

Cập nhật 2026-11-19 · worker `gate-c-builder` (task-9) · chỉ đọc code repo, ghi
`scripts/sspp_infer.py`, `kaggle/gate_c/`, file này.

## 1. Cổng C hỏi gì và tại sao nó có thể giết cả hướng train

Bơm plume tổng hợp (đường production: `PlumeTransform` → stateful clusters → raycast →
attenuation/occlusion) vào **frame SSPP sạch** (`label == 2` đã bỏ) thì detector 3DOD zero-shot
có báo **xe ma (FP) nhiều hơn** không, và **recall có tụt** không?

Nếu plume **không** làm tăng FP ⇒ augmentation không thể giúp detector trên spray thật ⇒ dừng
hướng train (đúng chốt chặn C trong `plan.md` §"Giai đoạn C"). Đây là cổng **duy nhất** chặn
trước khi đốt 10–17 h GPU, nên nó phải chạy trên **đúng kịch bản production** (following), không
phải kịch bản static của A3.

## 2. Thiết kế đã chốt (pre-registered — không đổi sau khi nhìn số)

| Hạng mục | Giá trị | Vì sao |
|---|---|---|
| Detector | Model 0 zero-shot: `data/lidar-only-det.pth` (33.362.653 byte, sha256 `7f3f1f83…`), pin `da93b27`, **không train** | cổng C đo cơ chế, không đo học |
| Config | `--config model0` = chain `voxelnet_0p075.yaml` (SparseEncoder 0,075 m, SECOND, TransFusionHead 10 lớp) — **Lead chốt 2026-11-19** | spec T2 ban đầu ghi `pointpillars` + crop `[0,64]×[−16,16]`: **SAI** vì `lidar-only-det.pth` là checkpoint voxelnet_0p075 (8,32M params, decoder in 256, head in 512); pointpillars (decoder 64, head 384) không load được — `strict=False` sẽ là **model random**. `pointpillars` path trong script chỉ dùng cho **F2 với checkpoint train từ đầu** |
| Kịch bản | **following**: ego chạy 50–130 km/h, object 20–30 m phía trước, `PlumeContext` dựng từ `sspp_infos` (`object_velocity_ego_mps = 0`) | đúng thứ train arm B sẽ gặp; A3 static không đại diện |
| Nhánh | `clean` (bỏ `label==2`) · `plume` (clean + inject) · `real` (giữ spray thật) — **cùng frame, cùng seed** | paired; `real` là mốc diễn giải "spray thật làm gì" |
| Split | `test`: 12 scene / **954 frame** = 374 @50 + 332 @90 + 248 @130 km/h | theo split đã đóng băng (`data/sspp_split.json`) |
| Ngưỡng score τ | **0,20** (primary) — **Lead đã CHỐT 2026-11-19**, đúng pre-registration. Sweep 0,10/0,30/0,50 chỉ là độ nhạy, **không** dùng để chọn τ | detections jsonl giữ mọi box ≥ 0,05 để tính lại offline |
| Matching | BEV IoU ≥ 0,5, **label-agnostic** (SSPP có 2 lớp, checkpoint 10 lớp nuScenes) | câu hỏi là "có hộp ma không", không phải phân lớp |
| Plume | `PlumeTransform` gọi **trực tiếp** (không config nào trong repo khai báo nó — R3 xác nhận), `seed=0`, `epoch=0`, `wfh_mm=1,0` `[CHỌN]`, `road_z=-0,411`, wet-ground BẬT (arm B bật) | production path; ghi rõ đây là giả định của worker |
| Nguồn hồi quy | paired theo scene: `FP_plume − FP_clean`/frame; bootstrap scene-level B=2000 | đơn vị độc lập là **scene**, không phải frame |

**Tiêu chí quyết định (Lead chốt, runbook chỉ ghi lại):**

1. **Plume phải làm TĂNG FP** đáng kể — CI95 của paired delta `FP_plume − FP_clean` **không chứa 0**
   và cận dưới > 0 (pooled theo scene), **và**
2. **Recall không được giảm quá 0,02** so với `clean` (CI95 của recall delta không vượt `−0,02`).
3. Nếu plume **không** tăng FP ⇒ **dừng hướng train**, quay lại A (không phải "train thử xem").
4. Báo **riêng theo nhóm tốc độ** (ADR-0006 §5.3): `90` và `130` km/h là miền tin cậy;
   **`50` km/h ngoài miền** — không dùng để kết luận, chỉ báo kèm.
5. CI rộng ở n = 12 scene ⇒ đây là **direction check**, không phải claim effect size. Muốn effect
   size phải dùng protocol 3-fold (giai đoạn E/F).

## 3. Chạy local (không cần GPU, không cần mmcv/mmdet/mmdet3d) — cổng kiểm

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    scripts/sspp_infer.py --dry-run
```

Kỳ vọng (exit 0) — các dòng then chốt:

```
GATE_C_DRY_RUN split=test scenes=12 frames=954 arms=clean,plume,real per_arm=2862
GATE_C_MODEL encoder=SparseEncoder fuser=None decoder=SECOND(in 256) head=TransFusionHead head_in=512 classes=10 test_grid=[1440, 1440, 41]
GATE_C_CHECKPOINT ... bytes=33362653 sha256=7f3f1f83… matches_expected=1
GATE_C_CHECKPOINT_CONFIG variant=sparse_voxel decoder_in=256 head_in=512 classes=10 ok=1
GATE_C_SCORING score_thresh=0.2 iou_thresh=0.5 range_m=54.0 sweep=[0.10,0.20,0.30,0.50]
GATE_C_SPEED 50km/h frames=374 in_domain=NO (<=60 km/h, out of domain)   # 90/130 in_domain=yes
GATE_C_PLUMB_OK scene=… injected=64 real_before=29131 real_after=29129 removed=2 attenuated=301 clean_unchanged=1
GATE_C_DRY_RUN_OK runtime_s=… expected_inference_s=7.2min
```

`GATE_C_PLUMB_OK` là phần quan trọng nhất: nó chạy **một frame thật** qua
`PlumeTransform` (numpy only) và chứng minh plume có detections, real points bị occlusion/
attenuation, và `points_clean` không bị đổi (pairing còn nguyên). Nếu dòng này thiếu ⇒ chưa
được đẩy Kaggle.

Dry-run 20 giây (`--limit 20`), toàn bộ 954 frame ~7 s vì chỉ chạy 1 frame qua plume.

## 4. Chạy trên Kaggle (GPU T4) — các bước

### 4.1 Bundle (một lần; chạy lại khi code đổi)

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
    kaggle/gate_c/make_bundles.py --stage          # tạo kaggle/gate_c/bundles/{code,data}
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
    kaggle/gate_c/make_bundles.py --upload         # tạo/version 2 dataset private
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python \
    kaggle/gate_c/make_bundles.py --push           # push kernel nguynhuy9669/bevfusion-gate-c
```

- `bundles/code` ≈ **34 MB** (tracked tree + `scripts/sspp_infer.py` + `kaggle/e2e/main.py`
  lấy từ lịch sử `main` + checkpoint 33 MB) → đóng gói thành **một `code.tar`** vì Kaggle files
  mode **bỏ qua thư mục**. **Kaggle tự giải nén** archive khi upload, nên mount cuối cùng là
  **cây thư mục** (kernel hỗ trợ cả hai dạng).
- `bundles/data` ≈ **356 MB** (`sspp_test.tar.gz`: 954 velodyne + 954 label + infos + split).
- **Đã upload 2026-11-19** (đo thật): code dataset ~**24 s** (35 MB), data dataset ~**3 m 25 s**
  (356 MB ≈ 1,9 MB/s). Dataset id: `nguynhuy9669/sspp-gate-c-code` (version 2),
  `nguynhuy9669/sspp-gate-c-data` (version 1, ready). Sửa code về sau chỉ cần `--upload` lại
  code dataset (~30 s), **không** đụng data.
- **Đã push**: kernel `nguynhuy9669/bevfusion-gate-c-plume-vs-detector` (title "BEVFusion gate C -
  plume vs detector"; slug phải khớp title, đừng đổi id về `.../bevfusion-gate-c` — Kaggle sẽ
  từ chối đính dataset). Version 4 · trạng thái lúc báo cáo (2026-11-19 14:30): `RUNNING` (đã qua
  mount + clone + dry-run, đang ở bootstrap env). **Kết quả chưa có.**
  → **Cập nhật 16:22:** kernel đó đã COMPLETE nhưng **INVALID** (§7b); bản chạy lại sau khi sửa
  kênh 4 là kernel riêng `nguynhuy9669/bevfusion-gate-c-full-ch4fix` **version 1 = COMPLETE**,
  kết quả hợp lệ ở **§7c**.
- Hai lần push đầu đỏ **trước khi tốn GPU**, đã sửa:
  · v2 `step=mount` (~10 s): kernel cũ tìm `sspp_test.tar.gz`, nhưng Kaggle **tự giải nén** tar.gz
    thành cây `Crafter_dynamic/...` + `sspp_infos_test.pkl` ở mount root → `find_data_mount()`.
  · v3 `step=dry_run` (~60 s): dry-run chạy trước khi clone `mit/bevfusion` nên thiếu config leaf
    → thứ tự mới là extract code → **clone pin** → dry-run → venv → toolchain → ops → inference.
  Nếu lại đỏ, đọc dòng `GATE_C_KERNEL_FAILED step=…` đầu tiên trong log.
- Kaggle CLI có sẵn: `/Users/huynguyen/.local/bin/kaggle`; auth `~/.kaggle/access_token`
  (đã kiểm: `kaggle config view` → username `nguynhuy9669`).

### 4.2 Theo dõi + lấy output

```bash
/Users/huynguyen/.local/bin/kaggle kernels status nguynhuy9669/bevfusion-gate-c-plume-vs-detector
# khi status COMPLETE:
/Users/huynguyen/.local/bin/kaggle kernels output nguynhuy9669/bevfusion-gate-c-plume-vs-detector \
    -p /tmp/gate_c_out
ls -la /tmp/gate_c_out/gate_c_out/      # gate_c_detections.jsonl + *_summary.json
```

- Thời gian ước tính: clone pin ~1–2 phút · dry-run ~1 phút · venv 3.8 + pinned wheels ~5–7 phút ·
  CUDA toolkit + build 12 extension ~10–12 phút (**tổng bootstrap 15–20 phút**, dùng lại recipe
  `kaggle/e2e/main.py` đã chạy thành công trên nhánh `main`) · inference 954 × 3 nhánh ≈
  **10–15 phút** (0,1–0,2 s/forward T4). **Tổng 25–40 phút/kernel.**
- Kernel tự chạy `--dry-run` bằng python hệ thống **trước** khi build env (~1 phút) để chết sớm
  nếu data/config sai.
- Output: ~5–20 MB jsonl (min-score 0,05) + summary json.

### 4.3 Biết thành công / thất bại

| Dấu hiệu trong log | Nghĩa |
|---|---|
| `GATE_C_DRY_RUN_OK` | data + config + checkpoint ổn (trước khi build) |
| `PINNED_WHEELS_OK`, `OPS_OK`, `STACK_OK` | env pin + CUDA extension build ổn |
| `GATE_C_MODEL_OK … missing=0 unexpected=0` | checkpoint load strict vào đúng architecture |
| `GATE_C_ARM clean …`, `plume …`, `real …` | 3 bảng metric per arm |
| `GATE_C_PAIRED … fp_delta_mean=… fp_delta_ci95=[…] recall_delta_ci95=[…]` | **dòng quyết định cổng C** |
| `GATE_C_KERNEL_OK frames=954 arms=3` | kernel xong |
| `GATE_C_KERNEL_FAILED step=…` hoặc `GATE_C_FAILED …` | dừng; đọc dòng ngay sau để biết bước chết |

### 4.4 Nếu Kaggle push bị chặn

- `401/403` từ API ⇒ token hết hạn: tải lại `~/.kaggle/access_token` từ Kaggle → Settings → API.
- `403` khi push kernel ⇒ tài khoản cần xác minh **phone/2FA** trước khi chạy GPU; làm trên web
  Kaggle (Settings → Phone verification), sau đó chạy lại lệnh `--push`.
- Quota GPU tuần (30 h) cạn ⇒ chờ reset thứ Hai hoặc chạy CPU (không khả thi: Voxelization là
  CUDA op) — đừng đổi sang CPU.
- Nếu `kernels push` lỗi "dataset not found": chưa chạy `--upload` hoặc upload lỗi; kiểm
  `kaggle datasets list -m` phải thấy `nguynhuy9669/sspp-gate-c-code` + `-data`.

## 5. Đọc kết quả

`gate_c_detections.jsonl`: mỗi dòng 1 frame/arm:
`scene_token, frame_idx, arm, token, speed_kmh, n_real_points_before/after, n_real_points_removed,
n_real_points_attenuated, n_injected, n_noise_points, score_thresh, boxes[{x,y,z,dx,dy,dz,yaw,score,label}]`.

`gate_c_detections_summary.json`: `per_arm`, `per_speed_kmh`, `paired.plume_minus_clean`
(bootstrap FP + recall), `threshold_sweep`, cộng toàn bộ config/checkpoint/seed.

Đọc nhanh:

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python - <<'PY'
import json
s = json.load(open('/tmp/gate_c_out/gate_c_out/gate_c_detections_summary.json'))
for arm, a in s['summary']['per_arm'].items():
    print(arm, 'FP/frame', round(a['fp_per_frame'], 3), 'recall', round(a['recall'], 3),
          'real_removed', a['n_real_removed'], '/', a['n_real_before'])
p = s['summary']['paired']['plume_minus_clean']
print('FP delta', p['fp_delta_bootstrap'], 'recall delta', p['recall_delta_bootstrap'])
print('by speed', json.dumps(s['summary']['per_speed_kmh'], indent=1))
PY
```

## 6. Giả định / giới hạn phải khai khi báo cáo

1. **Detector dùng là Model 0 thật** (`voxelnet_0p075` + checkpoint), **không** phải
   `pointpillars` + crop `[0,64]×[−16,16]`: không tồn tại checkpoint pointpillars ⇒ zero-shot là
   bất khả thi; script **từ chối** (không load random). Crop/`with_velocity`/`test_cfg` fixes đã
   cài sẵn trong `POINTPILLARS_OVERRIDES` cho F2 (xem §7).
2. **PlumeTransform gọi trực tiếp** vì repo không có config nào khai báo nó; đây là cùng class
   train arm B sẽ dùng, nhưng đường glue (SprayContextTransform) chưa được port.
3. `PlumeTransform` dùng `vehicle_class="crafter"` mặc định cho **mọi** scene (kể cả Golf) — nếu
   Lead muốn khớp lớp xe phải sửa `spray/` (ngoài scope worker này).
4. **Wet-ground chỉ có tác dụng thống kê:** `PlumeTransform` lấy `result.points_clean` (bản gốc) cho
   raycast chứ không lấy `base` đã qua wet-ground ⇒ attenuation của wet-ground **không** vào điểm
   thật. Đã ghi nhận, **KHÔNG sửa trong cổng C** (Lead: mở task riêng sau); không chặn kết quả cổng C.
5. `real` arm = frame gốc, không lọc spray. So sánh `clean ↔ plume` là chính; `real` chỉ để biết
   spray thật có làm detector sụp không.
6. n = 12 scene ⇒ CI rộng; chỉ direction check. Báo **riêng 90/130 km/h**; 50 km/h ngoài miền
   (ADR-0006 §5.3).
7. Không NMS trong head (nms_type null) ⇒ nhiều box/frame; FP đếm ở τ nên vẫn nhất quán giữa arms,
   nhưng không phải protocol chuẩn nuScenes.

### 6.1 Phát hiện ngoài scope, chưa xử lý (ghi nhận, **không** chặn cổng C)

- **Wet-ground bị bỏ trong production path** (mục 6.4): `spray/` — Lead sẽ mở task riêng, không sửa ở đây.
- **`vehicle_class` cứng `"crafter"`** (mục 6.3): `spray/` — limitation đã khai.

### 6.2 Covariate D2-v2 — phải nhớ khi đọc kết quả

User đã duyệt **D2-v2**: cho phép hiệu chỉnh **một** hệ số `following_density_scale` trên **171 scene
train-only** (fit 2/3, verify 1/3, assert `fit ∩ eval = ∅`), vì `label == 2` ở kịch bản following có
thể lệch. **Cổng C không làm việc này** — nó chạy generator hiện tại với Model 0 zero-shot. Hệ quả khi
đọc kết quả: plume hiện tại có thể **đậm/thưa hơn spray thật ở following**, tức **mật độ là covariate**,
không phải kết luận "generator đúng/sai". Nếu plume **không** tăng FP, phải loại trừ khả năng "plume
quá thưa do density scale" trước khi kết luận là vô hình.

**Quy mô kết luận:** n = **12 scene** (pooled 954 frame) ⇒ cổng C chỉ là **direction check**, KHÔNG
phải claim định lượng. Báo riêng **90** và **130 km/h** (in-domain); **50 km/h ghi "ngoài miền"**,
không dùng để kết luận (ADR-0006 §5.3). Mọi so sánh dùng paired delta theo scene + CI95 bootstrap.

## 7. Ba bug đã biết của `pointpillars.yaml` — xử lý ở đâu

| # | Bug | Xử lý trong `scripts/sspp_infer.py` |
|---|---|---|
| 1 | `with_velocity` phải `false` (box_dim 9 đã có vx,vy; nếu không → box 11 chiều) | `POINTPILLARS_OVERRIDES` đặt `data.{train,val,test}.with_velocity=False`; harness dựng ann trực tiếp từ `gt_boxes` 9 cột |
| 2 | `test_cfg.dataset: nuScenes` + `num_classes=2` ⇒ `IndexError` class 8/9 **mỗi step** (kể cả train) | override `dataset="SSPP"`; `validate_config_facts()` chặn nếu còn `nuScenes` với num_classes≠10 |
| 3 | `test_cfg.grid_size` kế thừa 1024² trong khi train 512²; `PointPillarsScatter.output_shape` hard-code `[512,512]` | override `grid_size=[320,160,1]`, `output_shape=[320,160]`; `validate_config_facts()` assert cả hai khớp pcr/voxel/out_factor |

Bug 4 (pointpillars **chưa từng được chạy**): script từ chối mọi checkpoint không khớp
architecture (`check_checkpoint_vs_config`), nên không thể vô tình đo model random. Gate C hiện
tại chạy `--config model0`; khi F2 có checkpoint pointpillars thì chạy lại với
`--config pointpillars --checkpoint <ckpt F2>`.

## 7b. Kết quả chạy thật — kernel v4, 2026-11-19 (Model 0 zero-shot, τ=0,20)

> ### ⛔ INVALID — 2026-11-19: model nạp sai kênh 4 (ring thay time-lag); **toàn bộ số FP/recall ở mục này phải bỏ.**
>
> `sspp_infer.py` đưa thẳng 5 cột của file `.bin` (`x, y, z, intensity, **ring**`) vào
> model, trong khi nuScenes/BEVFusion dùng cột 4 = **time-lag** ∈ [−0,5; 0]
> (`mmdet3d/.../loading.py:182`). Trọng số kênh 4 của checkpoint (RMS 0,874 /
> max|w| 15,15 — gấp 7,4× / 16,6× các kênh hình học) bị ring 0..31 đẩy 5–17 σ
> ⇒ model mù, bắn box quanh ego, **TP = 0/954 frame**. Chẩn đoán đầy đủ:
> `docs/measurements/model0-blindness-diagnosis.md` (§0–§6).
>
> **Verify sau khi sửa** (kernel `nguynhuy9669/bevfusion-gate-c-verify5-channel4-fix`,
> version 1 = COMPLETE 15:48, 5 frame `Crafter_dynamic` 90/130 km/h × 3 chế độ,
> cùng seed; số **[ĐO]**, nguồn `verify5_table.json` trong output kernel): trước sửa
> max score **0,146**, TP **0/5**, 100 % detection trong 5 m ego; sau sửa max score
> **0,563**, TP **5/5**, recall@τ=0,20 **1,00**, 7,3 % detection trong 5 m ego.
> Bảng đầy đủ: `model0-blindness-diagnosis.md` §7.
>
> Hệ quả: mọi diễn giải "plume tăng FP nhưng recall không tụt" ở §7b là **vô
> nghĩa** — cả ba nhánh đều chạy trên một detector đã bị phá đặc trưng. Muốn dùng
> cổng C phải **chạy lại 954 frame với bản đã sửa** (ước tính ~10 phút env +
> ~15 phút inference, xem §4).
>
> **→ Đã chạy lại xong 2026-11-19 16:22: kết quả hợp lệ ở §7c** (cùng 954 frame, cùng
> ba nhánh, cùng τ=0,20).

Kernel `nguynhuy9669/bevfusion-gate-c-plume-vs-detector` **version 4 = COMPLETE** (bắt đầu 14:23:56,
xong ~15:05; inference 907 s ≈ 15,1 phút; không có `GATE_C_KERNEL_FAILED`). 954 frame × 3 nhánh.

**Bảng chính (τ=0,20; FP/frame; recall; % frame có ≥1 FP):**

| Nhánh | FP/frame | recall | % frame có FP | dets/frame |
|---|---:|---:|---:|---:|
| clean | **0,004** | **0,000** | 0,4 % | 1,78 |
| plume | **0,080** | **0,000** | 7,1 % | 3,22 |
| real | **0,088** | **0,000** | 8,4 % | 2,01 |

**Paired theo scene (n=12, bootstrap 2.000):** FP delta `plume − clean` = **+0,079**, CI95
**[+0,030; +0,134]** (không chứa 0); recall delta = **0,000 [0,000; 0,000]**.
**Theo tốc độ:** 90 km/h clean 0,003 → plume 0,133 → real 0,117; 130 km/h clean 0,012 →
plume 0,129 → real 0,089; **50 km/h (ngoài miền)** clean 0,000 → plume **0,000** → real 0,061.
**Độ nhạy τ:** 0,10: 0,189 / 0,688 / 0,693 · 0,30: 0,000 / 0,020 / 0,015 · 0,50: 0,000 / 0,001 / 0,000.
**Cấu trúc plume:** 1.528 điểm chèn/frame (không frame nào 0); real points bị occlusion
45.171/28.256.007 = **0,16 %**; bị attenuation intensity 8.022.247 = **28,4 %**.

**CẢNH BÁO ĐỌC KẾT QUẢ — Model 0 mù trên domain SSPP:** TP = 0 **toàn bộ** 954 frame/3 nhánh
⇒ recall tuyệt đối bằng 0, không thể kiểm "recall không tụt". Chẩn đoán: best BEV IoU của mọi
detection với GT: p95 = 0,000–0,001, max 0,055 (clean/real) và 0,301 (plume, đúng 1 frame); tâm
detection gần tâm GT nhất p50 = 21–24 m, detection mẫu ở x≈1,5 m trong khi GT ở x≈23 m. Nghĩa là
Model 0 không định vị được xe SSPP (domain gap zero-shot), detection sinh ra nằm quanh ego.
Vì vậy: **kết luận "plume tăng FP" có** (và plume ≈ real ở τ=0,1: 0,688 vs 0,693; 90 km/h: 0,133
vs 0,117; 130: 0,129 vs 0,089), nhưng đây là **direction check trên một detector gần như mù**, chưa
phải bằng chứng rằng plume sẽ ảnh hưởng detector sau fine-tune. Muốn cổng C đủ lực cần detector có
recall ≠ 0 (Model 0 fine-tuned / Arm A) — hoặc chấp nhận cổng C chỉ phán "plume có tác dụng lên
detector hay không" chứ không phán "tác dụng đúng chiều khi detector đã nhìn thấy xe".
(Thêm: ở 50 km/h plume vô hình trong khi real có FP 0,061 — khớp A3 ngoài miền; D2-v2
`following_density_scale` là covariate, xem §6.2.)

## 7c. Kết quả sau khi sửa kênh 4 — kernel full v1, 2026-11-19 (954 frame, τ=0,20)

**Trạng thái: HỢP LỆ (VALID) — thay thế toàn bộ §7b.** Số dưới đây là **[ĐO]** trên
kernel `nguynhuy9669/bevfusion-gate-c-full-ch4fix` **version 1 = COMPLETE**
(push 15:58:56, xong **16:22:11**; `elapsed_s=1314` ≈ **21,9 phút** kernel (23,3 phút từ lúc
push): wheels ~1 phút, build 12 CUDA op 363 s, inference **687,6 s = 11,5 phút**; GPU Tesla T4
15.360 MiB; `GATE_C_KERNEL_OK frames=954 arms=3 channel4_fix=1`).

### 7c.1 Thiết lập và bằng chứng bản sửa có hiệu lực

- Code dataset `nguynhuy9669/sspp-gate-c-code` **version 4** (upload 15:57:59, `Ready`) =
  cây hiện tại. Harness trên GPU `sha256=946ec5bc…` (57.332 byte) **trùng** `scripts/sspp_infer.py`
  local; `GATE_C_HARNESS … channel4_fix=1 legacy_flag=1`.
- Cờ đúng pre-register: `legacy_channel4=0` (zero hoá cột 4), `z_shift_m=0,000`, `seed=0`,
  `--score-thresh 0,20`, `--min-score 0,05` (giữ mọi box ≥0,05 trong jsonl), IoU ≥0,5
  label-agnostic, range 54 m, following, wet-ground BẬT, `wfh_mm=1,0`, `road_z=-0,411`,
  `epoch=0`. `GATE_C_MODEL_OK config=model0 … chain=7 missing=0 unexpected=0`.
- **Model 0 không còn mù:** `recall_clean` = **0,821** (v4: 0,000), `tp_total` = **2.068**
  trên 3 nhánh (v4: 0), `GATE_C_SANITY … jsonl_lines=2862 … recall_clean=0.8208`.
  Verify5 (5 frame, 5/5 TP) đã dự báo đúng chiều.
- Ghi nhận provenance: bundle code staged từ **cây làm việc lúc 15:57** (trước commit
  `c0d7784` 16:15), trong đó `spray/raycast.py` đã có `pdet_range_exponent` — default **0,0**,
  biến môi trường `PLUME_PDET_RANGE_EXPONENT` **không** được set trong kernel ⇒ đường plume
  **giống hệt** bản đã đo ở A3-V (bit-for-bit; commit sau đó chỉ sửa docstring, không đổi default).
  `scripts/measure_pdet_vs_range.py` + `tests/test_raycast.py` không nằm trên đường inference.

### 7c.2 Bảng chính (τ=0,20; FP/frame · recall · % frame có ≥1 FP · dets/frame)

954 frame / 12 scene. "Frame có FP" đếm frame có **≥1 box không khớp GT nào** (BEV IoU ≥0,5).

| nhóm | nhánh | FP/frame | recall | % frame ≥1 FP | dets/frame | precision |
|---|---|---:|---:|---:|---:|---:|
| **gộp** | clean | **1,018** | **0,821** | 56,1 % (535/954) | 15,81 | 0,561 |
| **gộp** | plume | **1,288** | **0,570** | 66,0 % (630/954) | 17,57 | 0,361 |
| **gộp** | real | **1,243** | **0,777** | 63,1 % (602/954) | 17,71 | 0,491 |
| 90 km/h | clean | 1,003 | 0,864 | 56,3 % | — | — |
| 90 km/h | plume | 1,274 | 0,614 | 67,2 % | — | — |
| 90 km/h | real | 1,250 | 0,804 | 64,2 % | — | — |
| 130 km/h | clean | 1,250 | 0,794 | 62,1 % | — | — |
| 130 km/h | plume | 1,794 | 0,520 | 80,6 % | — | — |
| 130 km/h | real | 1,718 | 0,750 | 77,0 % | — | — |
| 50 km/h **(ngoài miền)** | clean | 0,877 | 0,799 | 51,9 % | — | — |
| 50 km/h **(ngoài miền)** | plume | 0,965 | 0,564 | 55,3 % | — | — |
| 50 km/h **(ngoài miền)** | real | 0,922 | 0,770 | 52,9 % | — | — |

**Cấu trúc plume** (tổng 954 frame): chèn **1.457.602** điểm = **1.528 điểm/frame**
(min 2 / max 7.512, **không frame nào 0**); occlusion bỏ **45.171/28.256.007 = 0,16 %** điểm thật;
attenuation đổi intensity **8.022.247 = 28,4 %**. `label==2` bị bỏ ở `clean`/`plume`:
**486.287** điểm (vẫn còn ở `real`).

**TP theo frame (paired, cùng frame):** `plume` **mất TP ở 255 frame**, chỉ **được thêm 16**
(528 frame giữ, 155 không có); `real` mất 66 / thêm 24. Tức plume không "thêm nhiễu rồi thôi" —
nó **xoá detection đúng** ở 27 % số frame, gấp **3,9×** spray thật.

### 7c.3 Paired theo scene (bootstrap 2.000, seed 0)

Đơn vị độc lập = scene. n = 12 (gộp) / 4 (mỗi nhóm tốc độ) ⇒ CI theo nhóm rất rộng; 50 km/h
ngoài miền, chỉ báo kèm.

| nhóm | so sánh | ΔFP/frame | CI95 ΔFP | Δrecall | CI95 Δrecall | n scene |
|---|---|---:|---|---:|---|---:|
| **gộp** | **plume − clean** | **+0,299** | **[+0,123; +0,494]** | **−0,268** | **[−0,372; −0,174]** | 12 |
| **gộp** | **real − clean** | **+0,268** | **[+0,147; +0,397]** | **−0,049** | **[−0,083; −0,019]** | 12 |
| gộp | plume − real *(tham khảo)* | +0,031 | [−0,126; +0,183] | −0,219 | [−0,301; −0,146] | 12 |
| 90 | plume − clean | +0,351 | [+0,024; +0,677] | −0,296 | [−0,497; −0,103] | 4 |
| 130 | plume − clean | +0,462 | [+0,081; +0,843] | −0,247 | [−0,361; −0,132] | 4 |
| 50 *(ngoài miền)* | plume − clean | +0,084 | [−0,014; +0,171] | −0,261 | [−0,453; −0,109] | 4 |
| 90 | real − clean | +0,290 | [+0,101; +0,499] | −0,079 | [−0,158; −0,000] | 4 |
| 130 | real − clean | +0,469 | [+0,384; +0,568] | −0,036 | [−0,072; 0,000] | 4 |
| 50 *(ngoài miền)* | real − clean | +0,045 | [−0,008; +0,104] | −0,031 | [−0,057; −0,007] | 4 |

**Độ nhất quán dấu:** plume−clean ΔFP **> 0 ở 11/12 scene**, Δrecall **< 0 ở 12/12 scene**;
real−clean ΔFP > 0 ở 11/12, Δrecall < 0 ở 8/12; **plume−real ΔFP > 0 chỉ ở 5/12 scene**
(không hệ thống) nhưng Δrecall < 0 ở **12/12**.

### 7c.4 Độ nhạy τ (gộp, FP/frame · recall)

| τ | clean | plume | real |
|---:|---|---|---|
| 0,10 | 5,152 · 0,893 | 5,786 · 0,726 | 5,894 · 0,852 |
| **0,20 (primary)** | **1,018 · 0,821** | **1,288 · 0,570** | **1,243 · 0,777** |
| 0,30 | 0,206 · 0,671 | 0,298 · 0,421 | 0,265 · 0,636 |
| 0,50 | 0,020 · 0,331 | 0,022 · 0,143 | 0,018 · 0,325 |

Chiều **không đổi theo τ**: plume ≈ real ở FP (chênh ≤ 0,11), nhưng recall của plume **thấp hơn
clean 0,17–0,25** và **thấp hơn real 0,13–0,22** ở **mọi** τ. Không có τ nào "cứu" được recall.

### 7c.5 Verdict theo tiêu chí pre-register (§2) — HƯỚNG TRAIN ĐÃ CHẾT

1. **Tiêu chí 1 — plume phải làm TĂNG FP: ĐẠT.** ΔFP = **+0,299**, CI95 **[+0,123; +0,494]**
   (không chứa 0, cận dưới > 0), 11/12 scene dương, và đúng ở cả 90 (+0,351) lẫn 130 (+0,462).
2. **Tiêu chí 2 — recall không được giảm quá 0,02: TRƯỢT NẶNG.** Δrecall = **−0,268**,
   CI95 **[−0,372; −0,174]**; cận dưới **−0,372 ≪ −0,02**, 12/12 scene âm. Recall tuyệt đối
   **0,821 → 0,570** (−32,6 % tương đối), tức 239 frame mất detection đúng.
3. ⇒ Theo đúng luật đã chốt **trước khi nhìn số**, cổng C trả lời **KHÔNG**: plume hiện tại
   **không dùng được làm augmentation**. Đây là **kiểu thất bại khác** với kịch bản §7b dự phòng
   ("plume không tăng FP"): plume **có** tăng FP, nhưng cái giá là **mất recall** — lớn gấp
   **5,5×** mức mất recall của spray thật (−0,049). Không được diễn giải lại thành "còn sống".

### 7c.6 Đọc kết quả: plume vs real + covariate mật độ

- **Trục FP: plume "giống spray thật".** ΔFP(plume−real) = **+0,031, CI95 [−0,126; +0,183]**
  (không khác 0; chỉ 5/12 scene dương) ⇒ ở τ=0,20 plume tạo **đúng mức FP như spray thật**,
  không phải "FP nhiều hơn real". Đây là điểm **ủng hộ** generator ở khía cạnh nhiễu.
- **Trục recall: plume "độc" hơn real.** Δrecall(plume−real) = **−0,219, CI95 [−0,301; −0,146]**,
  12/12 scene âm. Cơ chế khớp với cấu trúc: plume **attenuate 28,4 %** điểm thật + **occlude
  0,16 %** + chèn 1.528 điểm/frame, trong khi `real` chỉ có spray thật (không bị stage nào
  attenuate thêm). Detector mất tín hiệu của chính xe thật, không chỉ bị dụ thêm box.
- **Caveat mật độ (bắt buộc khi trích dẫn).** Phép đo độc lập
  `docs/measurements/following-scenario-density.md` cho thấy generator following hiện **đậm hơn
  dữ liệu thật 8–17× ở 120–130 km/h** (set B: Crafter 16,92 [13,88; 20,88], Golf 8,02
  [6,07; 11,64]) và **~4,5× trên chính các scene eval** dùng ở cổng C (set A: 4,61 / 4,51);
  near-field: **~81 % detection sinh ở <10 m, ~48 % ở <4 m** (B, 120–130). Vì vậy phần recall
  bị mất **có khả năng là do mật độ/near-field** (quá nhiều điểm gần cảm biến ⇒ che tín hiệu
  thật) **chứ không phải bản chất spray**. Nhưng theo pre-register, cổng C phán trên **generator
  hiện tại**: kết luận là **chết**. Muốn cứu phải sửa mật độ rồi **chạy lại cổng C với
  pre-register mới** — không được diễn giải lại run này.
- **Giới hạn:** n = 12 scene (4 scene/nhóm tốc độ) ⇒ direction check, không phải effect size;
  50 km/h ngoài miền (ADR-0006 §5.3); detector vẫn zero-shot Model 0 (không fine-tune), nên câu
  hỏi "sau fine-tune thì sao" vẫn mở, nhưng **augmentation hiện tại không qua được cổng**.

### 7c.7 Tái lập

```bash
# output kernel (jsonl 12 MB + summary) — kernel id ở trên, version 1
/Users/huynguyen/.local/bin/kaggle kernels output nguynhuy9669/bevfusion-gate-c-full-ch4fix \
    -p .scratch/tmp/gate_c_full_out
# bảng offline (paired theo scene, CI95, theo tốc độ, τ sweep) từ jsonl ≥0,05
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
    kaggle/gate_c_full/analyze.py \
    --jsonl .scratch/tmp/gate_c_full_out/gate_c_out/gate_c_detections.jsonl \
    --infos data/sspp_infos_test.pkl \
    --out-dir .scratch/tmp/gate_c_full_analysis
```

## 8. File liên quan

- `scripts/sspp_infer.py` — harness (dry-run + inference + metric).
- `kaggle/gate_c/kernel.py`, `kernel-metadata.json` — bundle đẩy Kaggle.
- `kaggle/gate_c/make_bundles.py` — tạo/upload dataset + push kernel.
- `kaggle/gate_c_verify5/kernel.py`, `kernel-metadata.json` — kernel verify 5 frame ×
  3 chế độ của bản sửa kênh 4 (`--legacy-channel4` / mặc định / `--z-shift-m -1.45`).
- `kaggle/gate_c_full/kernel.py`, `kernel-metadata.json` — kernel **chạy lại đầy đủ** sau khi
  sửa kênh 4 (954 frame × 3 nhánh; guard `step=harness` / `step=outputs`), kết quả ở §7c.
- `kaggle/gate_c_full/analyze.py` — phân tích offline từ `gate_c_detections.jsonl` (paired theo
  scene + bootstrap 2.000, tách 50/90/130, quét τ 0,10–0,50, kiểm lại tiêu chí §2).
- Tiêu chí pre-registration: `.scratch/roadspray-cal/plan.md` §"Giai đoạn C"; ADR-0006 §5.3.
