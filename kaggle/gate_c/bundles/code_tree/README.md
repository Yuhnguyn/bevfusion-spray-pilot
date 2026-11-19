# BEVFusion trên SemanticSpray++ — hướng spray thật

Câu hỏi: **khi train BEVFusion LiDAR-only trên frame đã bỏ điểm spray, việc chèn thêm spray
tổng hợp lúc train có giảm số hộp dương tính giả trên spray thật không, và có mất recall xe
thật không?**

Đại lượng cần làm nhỏ: **số hộp dương tính giả mỗi frame** (FP/frame) trên tập test spray thật.
Đại lượng phải giữ: **recall xe thật**.

Detection chạy trên **SemanticSpray++** (spray thật, box thật), không phải nuScenes. Đây là
điểm khác biệt so với nhánh `main` — nhánh đó đo trên nuScenes với plume tổng hợp và đóng lại
làm bản đối chứng.

## Ba nhánh thí nghiệm

| Nhánh | Train trên | Trả lời |
|---|---|---|
| Model 0 | không train, dùng checkpoint `lidar-only-det.pth` | Mức hỏng gốc của model nuScenes với spray thật |
| Arm A | 16 scene sạch (đã bỏ điểm `label == 2`) | Chỉ fine-tune, không augment, được gì |
| Arm B | 16 scene sạch + spray tổng hợp, p = 0,5 | Augment thêm được gì so với Arm A |

Arm A là nhóm đối chứng: B so với A mới là so đúng, vì hai nhánh giống nhau mọi thứ trừ một
biến duy nhất.

## Dữ liệu

207 scene SemanticSpray++, **36 scene có box 3D** (2.587 frame, 2.595 box). Lớp: Car 1.362,
Van 1.225, Other Vehicle 8 (bỏ). Không có calibration 6 camera → chỉ chạy LiDAR-only.

Chia theo tốc độ để test là tốc độ chưa thấy:

| Split | Tốc độ (km/h) | Scene | Frame | Spray p50/frame |
|---|---|---|---|---|
| train | 60, 80, 100, 120 | 16 | 1.124 | 378 |
| val | 70, 110 | 8 | 509 | 499 |
| **test** | **50, 90, 130** | **12** | **954** | **142** |

## Trạng thái (2026-11-15)

- Nhánh `sspp` tách từ `main` @ `f3fb7d2`. Đã dọn sạch dây nuScenes; test còn **151 passed**.
- Kế hoạch đầy đủ: `.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md` (5 bước thi công).
- Việc kế tiếp: **bước 2 — dataset adapter** (`spray/sspp_adapter.py` + `scripts/build_sspp_split.py`).
- Chưa có kết quả nào. Mọi con số trong `docs/measurements/semantic-spray-*.md` là đo trên
  dataset, không phải kết quả detector.

## Cấu trúc

- `mit/bevfusion` — working copy, pin `da93b27` (`mit/PIN.md`). `third_party/` là clone read-only.
- `data/SemanticSprayDataset` — 31 GB, gitignore.
- `spray/` — sinh plume (`plume*`, `raycast`, `beam_model`, `wet_ground`) + đo spray thật
  (`semantic_stats`, `semantic_split`, `spray_stats`).
- `proxy_eval/` — matcher BEV IoU + bootstrap theo scene.
- `scripts/` — ba script: tải dataset, build/verify split, đo thống kê.
- `docs/measurements/` — bốn báo cáo số đo; `docs/reference/paper-qa-notebooklm.md` — hỏi đáp
  nguyên văn với paper.

## Hạn chế đã biết

1. **1 box/frame, 2 lớp.** mAP trên một object là nhiễu; báo FP/frame và recall làm thước chính.
2. **Không có frame sạch.** Mọi frame đều có spray; frame "sạch" chỉ tồn tại bằng cách xoá điểm
   `label == 2`.
3. **Không có calibration camera** → không chạy được nhánh fusion, chỉ LiDAR-only.
4. **Số tuyệt đối không chuyển sang nuScenes đô thị.** Chỉ delta ghép cặp là chuyển được.
