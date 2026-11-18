# Detector choice: PointPillars vendored vs BEVFusion-heavy (task-4)

Cập nhật 2026-11-18 · read-only audit · pin `mit/bevfusion@da93b27` (working copy sạch) · không sửa tracked file, không train.
Ký hiệu: `[ĐO]` = đo được (số trong repo/Kaggle log cũ), `[ƯT]` = ước tính suy ra từ config + code, `[ĐỌC]` = suy từ đọc code.

## TL;DR — trả lời thẳng 2 câu lead cần

1. **Có chạy được `pointpillars.yaml` trên `sspp_infos*.pkl` mà không cần framework mới.** Nhưng câu "chỉ cần trỏ config vào data" là **sai**: file đó là **fragment 46 dòng** (không phải config hoàn chỉnh), có **3 lỗi cứng** nếu dùng nguyên, và data section nó thừa hưởng là nuScenes thuần. Cần đúng 5 thứ: (i) resolver chuỗi `default.yaml` kiểu torchpack (đã có bản recoverable trong git history `main:kaggle/train/probe.py`), (ii) dict override ~20 dòng, (iii) `sspp_infos` dataset subclass ~35 dòng + pipeline LiDAR-only, (iv) training loop + eval script (**không tồn tại trong tree**, phải viết lại), (v) env bootstrap (recover từ `main:kaggle/e2e/main.py`, 791 dòng, proven). Không sửa file nào trong `mit/bevfusion`.
2. **Wall-clock (b) — con số quyết định plan 6 hay 30 runs:** nếu giữ `point_cloud_range` 102.4×102.4 m của vendor thì **0.9–1.6 s/step** batch-8 T4 → 1 run 1.700 frame/50 epoch = **2,5–4,8 h** → 12 runs không fit. Nếu **crop corridor** `[0,64]×[-16,16]×[-5,3]` m (đủ chứa toàn bộ box + spray) thì **0.25–0.5 s/step** → 1 run **45–80 phút**. Hệ quả: **12 run (3 fold × 2 arm × 2 seed) ≈ 10–17 h GPU quota — vừa; 18 run ≈ 14–24 h — vừa nhưng sát; 30 run ≈ 24–40 h — KHÔNG fit 30 h/tuần.**
3. **Motivation khoa học mạnh hơn motivation compute.** Model hiện tại là fine-tune 2.000 step của một checkpoint nuScenes (gần như frozen feature extractor; nhánh `main` đã đo: augment chỉ làm hộp dự đoán dịch **3 mm**). From-scratch trên 1.124 frame là model *thực sự học từ distribution này* → augmentation mới có cửa tác động. Đây là lý do đổi xe, không phải "cho rẻ".

## 1. Hai config vendored — đọc hết, resolve hết

Cả 3 file `lidar/*.yaml` đều nằm trong commit duy nhất `da93b27 [Major] Code release` → **không có dấu vết file nào từng được chạy**. README chỉ trỏ `voxelnet_0p075.yaml` (LiDAR-only baseline, có checkpoint). `pointpillars.yaml` **không được tham chiếu ở đâu** → coi là config chưa được upstream kiểm chứng.

Config không load bằng `mmcv.Config.fromfile` (không có `_base_`): torchpack `configs.load(..., recursive=True)` merge **toàn bộ `default.yaml` của các thư mục tổ tiên, root-first**, rồi eval `${...}`. Tôi đã chép lại `_chain/_merge/_resolve` của `main:kaggle/train/probe.py` và resolve thật (không cần torchpack), kết quả merge:

| key (sau resolve) | pointpillars.yaml | voxelnet.yaml | voxelnet_0p075.yaml |
|---|---|---|---|
| voxel_size | `[0.2, 0.2, 8]` | `[0.1,0.1,0.2]` (inherit) | `[0.075,0.075,0.2]` |
| point_cloud_range | `[-51.2,-51.2,-5, 51.2,51.2,3]` (inherit) | same | `[-54,-54,-5, 54,54,3]` |
| lidar encoder | `PointPillarsEncoder`: `PillarFeatureNet` in 5→10 feat `[64,64]` + `PointPillarsScatter` output `[512,512]` | `SparseEncoder` out 128, sparse_shape `[1024,1024,41]`, max_vox `[90k,120k]` | same, `[1440,1440,41]`, `[120k,160k]` |
| decoder backbone | `SECOND` in **64**, out `[64,128,256]`, layers `[3,5,5]`, strides `[2,2,2]` | `SECOND` in **256**, out `[128,256]`, `[5,5]`, `[1,2]` (inherit) | same |
| decoder neck | `SECONDFPN` in `[64,128,256]` out `[128,128,128]` up `[0.5,1,2]` | in `[128,256]` out `[256,256]` up `[1,2]` | same |
| head | `TransFusionHead` in **384**, 10 class, 200 proposals, 1 decoder layer, 8 heads | `TransFusionHead` in **512** | same |
| bbox coder | `TransFusionBBoxCoder` code_size **10**, out_factor 4, pc_range ±51.2 | out_factor 8 | out_factor 8 |
| train_cfg | grid `[512,512,1]`, out_factor 4, dataset `nuScenes` | `[1024,1024,1]`, 8 | `[1440,1440,41]`, 8 |
| test_cfg | grid **`[1024,1024,1]`** (kế thừa, leaf quên override) out_factor 4 | `[1024,1024,1]` | `[1440,1440,41]` |

- **Head = `TransFusionHead`, không phải CenterHead** (common_heads có `vel: [2,2]`, HungarianAssigner3D + IoU3D cost). "Light" ở đây = PointPillars encoder + TransFusion-L head, không phải PointPillars+CenterHead của KITTI.
- **LiDAR-only thật**: `lidar/default.yaml` set `encoders.camera: null`; `det/default.yaml` set `fuser: null` → model không có nhánh camera/fuser. Nhưng **`forward()` vẫn khai báo 9 tham số camera không có default** (dùng `None` được vì nhánh camera không tồn tại — xem §2.3).
- **Model chain pointpillars tự nhất quán về channel**: 64 (PillarFeatureNet) → scatter 64 → SECOND 64/128/256 → FPN 3×128 = **384** = head in 384; grid 512 / out_factor 4 = heatmap 128² = neck output 128². `[ĐỌC]`
- **Params `[ƯT]`**: pointpillars **5,27 M / ~21 MB** (PFN 4,6k + SECOND 4,21M + neck 181k + head 0,88M); so với `data/lidar-only-det.pth` = **8.315.898 params / 33.362.653 byte** `[ĐO]` (ckpt: decoder `blocks.0.0 (128,256,3,3)`, head `shared_conv (128,512,3,3)`, `heatmap (10,128,3,3)` → khớp chain voxelnet_0p075, **không khớp pointpillars**). ⇒ chuyển sang pointpillars = **mất checkpoint khởi tạo**, đúng nghĩa from-scratch.

## 2. Chạy trên SSPP — sửa gì, cụ thể

### 2.1 Patch config (dotted-path dict; KHÔNG sửa `mit/bevfusion`)

```python
# kaggle/train/sspp_config.py — resolve leaf vendored rồi patch, giữ pin nguyên vẹn
LEAF = "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/lidar/pointpillars.yaml"
OVERRIDES = {
  "point_cloud_range": [0.0, -16.0, -5.0, 64.0, 16.0, 3.0],  # box [ĐO]: x 18.6–39.3, y −2.6…+0.8, zbottom −0.82…+0.17
  "voxel_size": [0.2, 0.2, 8.0],                    # (3−(−5))/8 = 1 z-bin → giữ pillar 2D
  # max_voxels giữ nguyên vendor [30000, 60000]: 320×160 = 51.200 cell, ~28.9k điểm/frame ⇒ ~10–20k pillar non-empty, không bị cắt
  "model.encoders.lidar.backbone.pts_middle_encoder.output_shape": [320, 160],  # PHẢI tay: vendored hard-code [512,512]
  "model.heads.object.num_classes": 2,               # Car, Van
  "model.heads.object.num_proposals": 100,           # vendored 200; heatmap 80×40 = 3.200 cell
  "model.heads.object.train_cfg.grid_size": [320, 160, 1],   # vendored [512,512,1]
  "model.heads.object.train_cfg.dataset": "SSPP",    # vendored "nuScenes" → IndexError, xem §2.4
  "model.heads.object.test_cfg.grid_size": [320, 160, 1],    # VENDORED QUÊN → bev_pos sai 2×
  "model.heads.object.test_cfg.dataset": "SSPP",
  "model.heads.object.bbox_coder.post_center_range": [-1.0, -17.0, -5.0, 65.0, 17.0, 3.0],
  "object_classes": ["Car", "Van"],
  "input_modality.use_camera": False,
  "train_pipeline": SSPP_TRAIN_PIPELINE,   # dưới đây
  "test_pipeline": SSPP_TEST_PIPELINE,
  "data": SSPP_DATA,                       # dưới đây
}
# Lưu ý bắt buộc: convert dict→mmcv.ConfigDict trước khi build (head đọc train_cfg.assigner
# bằng attribute); pass một file `mmcv.Config.fromfile` là hỏng.
```

```yaml
# pipeline LiDAR-only (thay toàn bộ train_pipeline nuScenes; test_pipeline bỏ Phần augment)
train_pipeline:
  - {type: LoadPointsFromFile, coord_type: LIDAR, load_dim: 5, use_dim: 5, reduce_beams: 32, load_augmented: null}
  - {type: LoadAnnotations3D, with_bbox_3d: true, with_label_3d: true, with_attr_label: false}
  - {type: SSPPLoadPointsClean}            # xoá điểm labels==2 (viết 1 file riêng, hoặc precompute .bin sạch)
  - {type: GlobalRotScaleTrans, resize_lim: [0.95, 1.05], rot_lim: [-0.10, 0.10], trans_lim: 0.0, is_train: true}
  # Arm B chèn PlumeTransform ở đây (sau GlobalRotScaleTrans, trước range filter), Arm A không có bước này.
  # KHÔNG dùng RandomFlip3D: nó lật cả x→−x, object văng ra khỏi corridor x≥0 → frame 0 box
  - {type: PointsRangeFilter, point_cloud_range: [0.0, -16.0, -5.0, 64.0, 16.0, 3.0]}
  - {type: ObjectRangeFilter, point_cloud_range: [0.0, -16.0, -5.0, 64.0, 16.0, 3.0]}
  - {type: PointShuffle}
  - {type: DefaultFormatBundle3D, classes: [Car, Van]}
  - {type: Collect3D, keys: [points, gt_bboxes_3d, gt_labels_3d]}
data:
  samples_per_gpu: 8
  workers_per_gpu: 4
  train: {type: SSPPDataset, dataset_root: data/SemanticSprayDataset, ann_file: data/sspp_infos_train.pkl,
          pipeline: ${train_pipeline}, object_classes: ${object_classes}, modality: ${input_modality},
          box_type_3d: LiDAR, test_mode: false, with_velocity: false, use_valid_flag: true, filter_empty_gt: false}
```

### 2.2 Dataset subclass (~35 dòng, không cần framework mới)

`sspp_infos_*.pkl` là **list trần** `[ĐO]`, không phải `{"infos": …, "metadata": …}`; `NuScenesDataset.load_annotations` đòi dict, `get_ann_info` đòi `info["gt_velocity"]` khi `with_velocity=True`, `get_data_info` không join `dataset_root` vào `lidar_path`. Tối thiểu:

```python
@DATASETS.register_module()
class SSPPDataset(NuScenesDataset):
    def load_annotations(self, ann_file):
        self.metadata = {"version": "sspp"}; self.version = "sspp"
        self.data_infos = mmcv.load(ann_file); return self.data_infos   # list trần
    def get_data_info(self, index):
        data = super().get_data_info(index)                            # ann_info dùng gt_boxes/valid_flag
        data["lidar_path"] = osp.join(self.dataset_root, self.data_infos[index]["lidar_path"])
        return data
# config: with_velocity: false  → box_dim 9 (7 hình học + vx,vy) đi thẳng vào head/coder, không bị concat thêm 2 cột
```

### 2.3 Gọi model trong training loop

`Base3DFusionModel.train_step` gọi `self(**data)` → với batch LiDAR-only sẽ `TypeError` (thiếu 9 kwarg camera). Không dùng mmcv runner; dùng loop thủ công (mẫu `main:kaggle/train/ab_run.py`):

```python
losses = model(points=b["points"], img=None, camera2ego=None, lidar2ego=None, lidar2camera=None,
               lidar2image=None, camera_intrinsics=None, img_aug_matrix=None, lidar_aug_matrix=None,
               metas=b["metas"], gt_bboxes_3d=b["gt_bboxes_3d"], gt_labels_3d=b["gt_labels_3d"])
```
`forward` chỉ dùng `points/metas/gt_*` khi không có camera encoder; `return_loss` bị nuốt bởi `**kwargs` nên loop cũ truyền được. `[ĐỌC]` — phải xác nhận bằng smoke 20 step.

### 2.4 Bảng giả định code-level: cái gì vỡ nếu không sửa

| Giả định trong config vendored | Trên SSPP | Xử lý |
|---|---|---|
| `test_cfg.grid_size [1024,1024,1]` (leaf quên) trong khi train `[512,512,1]` | `bev_pos` = (1024/4)² = 65.536 vị trí, feature map thật 128² (của ta 80×40) → positional embedding sai 2–4×; **không crash** nhưng train sai | override `[320,160,1]` (bắt buộc) |
| `train_cfg.dataset / test_cfg.dataset: nuScenes` | `forward_single` chạy **cả lúc train**: `local_max[:, 8]` với `num_classes=2` → **IndexError mỗi step** | đổi sang chuỗi khác (`"SSPP"`); `nms_type: null` nên `self.tasks` không dùng → an toàn |
| `num_classes: 10` (thừa hưởng) | 2 lớp | `num_classes: 2`; `class_encoding`/heatmap tự co |
| `PillarFeatureNet.in_channels: 5` + 5 offset | point 5 chiều `x,y,z,intensity,ring` `[ĐO]` | không đổi |
| `PointPillarsScatter.output_shape [512,512]` hard-code | range của ta 320×160 | override, nếu không canvas sai shape |
| `pc_range/voxel_size` trong coder dùng `${point_cloud_range}`, `${voxel_size}` | tự theo override | không đổi tay (nhưng `test_cfg.grid_size`/`post_center_range` **không** tự theo) |
| `box_dim 9` với `vx,vy`; coder `code_size 10` | `LiDARInstance3DBoxes(box_dim=9, origin=(0.5,0.5,0))`; coder encode đọc `dst[:,7:]` → **hỗ trợ velocity** | giữ; **bắt buộc** `with_velocity: false` (nếu không thành 11-dim) |
| `z` bottom convention (đáy box, ground −0.411) | adapter đã ghi z đáy; coder tự đổi bottom→center (`dst[:,2] + dst[:,5]/2`) | không đổi |
| data section nuScenes (`LoadMultiViewImageFromFiles`, `LoadPointsFromMultiSweeps`, `ObjectPaste`+db sampler, `ImageAug3D`, `LoadBEVSegmentation`, `CBGSDataset`) | không có camera, không sweeps, không map, không `nuscenes_dbinfos_train.pkl` | thay toàn bộ pipeline/data như §2.1; bỏ `CBGSDataset` (duplicate sample làm A/B khó tái lập) |
| `evaluation.pipeline` + `NuScenesDataset.evaluate` | cần devkit + nuScenes submission format | không dùng; eval bằng `proxy_eval/matcher.py` + `bootstrap.py` có sẵn trong repo |
| `reduce_beams: 32` | `reduce_LiDAR_beams` chỉ hỗ trợ 16/4/1, 32 là **no-op** | vô hại; đặt `null` cho rõ |
| `encoders.camera: null` + `fuser: null` | không có calib camera trên SSPP | đúng ý; nhưng `forward` vẫn cần 9 kwarg `None` (§2.3) |

### 2.5 Env (đều đã có recipe cũ, không phải rủi ro mới)

- `import mmdet3d.datasets` kéo `loading.py` → `nuscenes.map_expansion` ⇒ **phải cài `nuscenes-devkit`** (dù SSPP không dùng) hoặc bypass package `__init__` như `probe.register_mmdet3d_pipelines()`. `[ĐỌC]`
- `pipelines/utils.py` import `numba.errors`, đã bị xoá từ numba 0.58 → shim `sys.modules["numba.errors"]=numba.core.errors` (recipe cũ trong `main:kaggle/train/probe.py`). `[ĐỌC]`
- `Voxelization` là CUDA op ⇒ phải build 12 extension (`setup.py develop`, ~10–11 phút/kernel `[ĐO]`).
- Không có `mmdet3d/models/detectors/` trong tree: **không có PointPillars/SECOND detector classic**, chỉ có `BEVFusion` + `TransFusionHead`. Không thể "dùng model khác" mà không thêm code.

## 3. Verify tĩnh — môi trường này làm được gì

- Máy laptop: `torch 2.2.2` (CPU), `numpy 1.26.4`, `numba 0.59.0`; **không có `mmcv`, `mmdet`, `mmdet3d`, `torchpack`, `nuscenes-devkit`** ⇒ **không build/không import-level check được**; toàn bộ §1–§2 là static trace chứ không phải "đã chạy".
- Static trace đã làm: mọi `type:` của config cần dùng đều resolve — vendored: `BEVFusion`, `PointPillarsEncoder`, `PillarFeatureNet`, `PointPillarsScatter`, `SECOND`, `SECONDFPN`, `TransFusionHead`, `TransFusionBBoxCoder`, `HungarianAssigner3D`, `BboxOverlaps3D`, `BBoxBEVL1Cost`, `IoU3DCost`, `PointsRangeFilter`, `ObjectRangeFilter`, `GlobalRotScaleTrans`, `RandomFlip3D`, `PointShuffle`, `LoadAnnotations3D`, `DefaultFormatBundle3D`, `Collect3D`; từ mmdet 2.20 (không kiểm được local): `FocalLoss`, `GaussianFocalLoss`, `L1Loss`, `VarifocalLoss`, `FocalLossCost`, `build_assigner`. Cả 3 backbone đều đăng ký ở `mmdet.models.BACKBONES` qua `backbones/__init__.py`. `[ĐỌC]`
- Kết luận verify: **ràng buộc thật nằm ở data/pipeline/harness, không ở model graph**. Model graph pointpillars tự nhất quán; rủi ro còn lại phải trả bằng **1 kernel smoke 20 step** (~20–25 phút GPU) trước khi mua matrix.

## 4. Effort + wall-clock Kaggle (câu trả lời cho quyết định 6 hay 30 runs)

**Neo đo được trên T4 (nhánh `main`, log cũ):** full fusion model (Swin camera + voxelnet 0.075 + SECOND + TransFusionHead), batch 2: **1,208–1,455 s/step**; 4.000 step (2 arm × 2.000) = **5.919,9 s ≈ 98,7 phút**, peak **4,2/16 GB**; kernel smoke tổng 2.086 s trong đó **~10–11 phút** dựng venv + build CUDA ext. `[ĐO]`

**Ước FLOP → s/step cho pointpillars `[ƯT]`:** full range 512²: backbone 36,2 GMAC + neck 3,0 + head 10,5 ≈ **50 GMAC/sample fwd** (~150 GMAC fwd+bwd). Từ neo trên suy ra hiệu suất thực ~1–1,5 TFLOPS ⇒ **0,9–1,6 s/step** batch 8. Crop corridor 320×160 (5,1× ít cell hơn, head cũng nhỏ hơn): **~10 GMAC/sample** ⇒ **0,25–0,5 s/step**.

| run (1.700 frame, batch 8 → 213 step/epoch) | s/step | phút/epoch | 40 epoch | 50 epoch | 60 epoch |
|---|---|---|---|---|---|
| pointpillars **crop** `[0,64]×[-16,16]` | 0,25–0,5 | 0,9–1,8 | 36–72' | 45–89' | 53–107' |
| pointpillars **full range** vendor | 0,9–1,6 | 3,2–5,7 | 128–228' | 160–285' | 192–343' |
| voxelnet 0.075 fine-tune 2.000 step (batch 2, status quo) | ~1,2 s `[ĐO]` | — | — | ~40–50' /run | — |

Cộng thêm: bootstrap env **12–18 phút/kernel**; eval 954 frame test ~2–5 phút/fold; checkpoint save ~10–30 s. Quota **30 h/tuần**, kernel tối đa 12 h (checkpoint sau mỗi run để không mất).

**Matrix theo ngân sách (crop range, 40–60 epoch):**
- **12 run** = 3 fold × 2 arm (A/B) × 2 seed → **10–17 h** ✅ (chừa 13–20 h cho rerun/fail).
- **18 run** (3 seed) = **14–24 h** ✅ nhưng sát trần, cần 3 kernel ~4–8 h mỗi cái.
- **30 run** (5 arm/seed) = **24–40 h** ❌ không fit quota; muốn đạt phải hạ còn 30 epoch/run hoặc giảm resolution nữa (voxel 0.25–0.3 → grid 256×128, thêm ~1,5–2× rẻ).
- Nếu **giữ full range**: 12 run = 32–57 h ❌ → **crop corridor là điều kiện cần**, không phải tối ưu hoá.
- Khuyến nghị vận hành: 1 kernel = 1 seed × (3 fold × 2 arm) = 6 run (~4–8 h) → 2 kernel cho 2 seed; mỗi kernel tự log `SSPP_STEP/ARM_OK` và lưu checkpoint từng fold-arm, giết kernel vẫn giữ được kết quả.

**Epochs-to-convergence:** KITTI PointPillars cần ~80 epoch / 3.712 frame (~300k crop) để converge; SSPP dễ hơn nhiều (1 box/frame, xe dẫn thẳng trục, cự ly cố định 20/30 m, 2 lớp) nhưng chỉ có 1.124–1.700 frame → guess **40–60 epoch**, nguy cơ overfit trước 80. Cách rẻ nhất để chốt: 1 run 60 epoch, eval + save checkpoint mỗi 10 epoch → có luôn sweep 40/50/60, chọn theo val 8 scene. Pilot trước matrix: **1 fold × 2 arm × 60 epoch ≈ 2–3,5 h**, xong rồi mới mua 12 run.

**Effort người (chưa train) `[ƯT]`:**
| việc | giờ |
|---|---|
| khôi phục & adapt env bootstrap từ `main:kaggle/e2e/main.py` + code/official dataset sync | 4–6 |
| dataset subclass + filter spray + unit test (laptop được) | 2–3 |
| config resolver + override + smoke import trên Kaggle (3–4 vòng fail) | 4–6 |
| payload Kaggle: chỉ 36 scene có box (~2,0 GB: 2.587 × 0,58 MB bin + labels 0,3 GB) thay vì 16–31 GB | 3–5 |
| train loop + eval/CP + SPF proxy (port từ `main:kaggle/train/ab_run.py|ab_eval.py`) | 8–12 |
| plume pipeline glue: port `main:spray/pipeline.py` + `spray_context_transform.py` (Arm B) | 2–4 |
| **tổng** | **24–35** |

## 5. Alternatives — xếp hạng cho regime "nhiều run ngắn"

| # | Phương án | Được | Mất / vỡ | Giờ setup | Rank |
|---|---|---|---|---|---|
| a | **Vendored `pointpillars.yaml` + crop range, from-scratch** | rẻ nhất/step (0,25–0,5 s), 5,3M params, many-run khả thi, không framework mới, augmentation có cửa tác động thật | config **chưa từng chạy** (3 lỗi §2.4), mất pretrain → mAP/recall tuyệt đối thấp, mất Model 0 & clean-control nuScenes, phải đổi τ sang frame sạch SSPP | 24–35 (chung 16–24 cho pipeline/harness) | **1** |
| b | **`voxelnet_0p075` fine-tune (status quo)** | checkpoint + chain proven (README baseline), giữ Model 0, so sánh được với nhánh `main` | 0,075 sparse ~3–6× compute/step ⇒ chỉ đủ ~2.000 step/run (đúng cái đang thiếu data); từ-scratch bất khả thi trong quota (7–12 h/run); vẫn là "fine-tune gần frozen" ⇒ ít nhạy với augment | 16–26 | 2 (fallback) |
| c | **OpenPCDet (PointPillars/SECOND/PV-RCNN, framework Paper A dùng)** | framework chín, PointPillars+CenterHead là bản tham chiếu KITTI, dễ tune, nhiều run ngắn rất hợp; cùng hệ paper để so | new framework + format data mới + port `PlumeTransform`/`spray/*` sang pipeline OpenPCDet; +2–4 ngày; không có sẵn trong repo; khó tái dùng harness cũ | 40–60 | 3 — chỉ đáng nếu pivot sang replication paper |

**Nếu (a) vỡ ở smoke:** sửa tại chỗ (lỗi sẽ khu trú ở encoder/scatter/head-target vì phần còn lại dùng chung voxelnet đã proven), KHÔNG nhảy OpenPCDet. Fallback rẻ nhất là (b) với 2.000-step fine-tune + tăng **số fold/seed** thay vì số epoch, và nếu cần thêm compute thì thử `voxelnet.yaml` (0,1 voxel, cùng họ, ít điểm hơn 0,075 ~2×) from-scratch — nhưng phải smoke trước vì cùng thuộc nhóm config "Code release chưa chạy".

**Cảnh báo thiết kế (đừng bỏ qua khi lên matrix):** đổi sang from-scratch **đổi câu hỏi khoa học**, không chỉ đổi chi phí: (i) Model 0 zero-shot biến mất → mốc so sánh thành "clean-frame SSPP model" (cùng arm A/B), (ii) "clean control nuScenes val" vô nghĩa với model SSPP-only → clean control phải là frame SSPP đã bỏ `labels==2`, (iii) τ phải quét lại trên frame sạch SSPP cho từng checkpoint, (iv) tuyệt đối không so số tuyệt đối với nhánh `main`/Model 0 cũ — chỉ đọc delta ghép cặp.
