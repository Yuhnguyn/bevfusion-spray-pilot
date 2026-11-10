# BEVFusion spray pilot (MIT)

Mục tiêu: đo **BEVFusion (LiDAR + 6 camera) mất bao nhiêu mAP khi có spray plume** từ xe phía trước
trên đường ướt, và **augmentation plume có làm giảm mức mất đó không**. Đây không phải bài toán
robustness dưới lỗi cảm biến.

Cách làm: train hai arm A/B trên cùng frame — A train sạch, B train sạch + plume — rồi đo paired
trên cùng eval set; thêm arm B0 (lọc spray rồi detect, không train) làm mốc. Detection chạy trên
**nuScenes**; **SemanticSpray chỉ dùng để hiệu chỉnh simulator** (`docs/adr/0003`).

## Trạng thái (2026-11-11)

- **Generator đang ở v2**, chưa quay lại A/B. v1 đã đóng sau khi audit tìm ra 8 lỗi cấu trúc
  (`docs/history/plume-v1-defects.md`) và kết quả A/B của v1 là **null** với chẩn đoán rõ cơ chế
  (`STATUS.md` mục "Dừng shift 2026-11-09").
- Code hiện có: `spray/plume.py` (vỏ + khối sau đuôi), `plume_state.py` (sinh/trôi/tan cụm),
  `plume_context.py`, `plume_transform.py` (pipeline + `points_clean`), `raycast.py` (cast beam,
  `P_det`, attenuation, strongest-return), `beam_model.py`, `wet_ground.py` (mặc định tắt),
  `spray_stats.py`, `proxy_eval/` (matcher + adapter output MIT).
- Test: **239 passed, 4 skipped** trên laptop CPU (không cần GPU, không cần mmcv).
- Đang làm **29c** (sửa `intensity = 0`, bỏ trần 2.000, khối theo phân số chiều cao box, hạ latency
  < 100 ms/frame), sau đó **29d** là cổng nghiệm thu. Chi tiết: `.scratch/spray-augmentation/STATUS.md`.
- Nguồn sự thật của tiến độ: `.scratch/spray-augmentation/STATUS.md`.
- Bản đồ tài liệu: **`docs/README.md`** (reference / measurements / history / audit); cửa vào: `docs/PROJECT.md`.
- ADR: `docs/adr/0001` pin MIT `da93b27`, `0002` plume-only (đã bị `0004` thay), `0003` SemanticSpray
  chỉ để hiệu chỉnh, `0004` v2 mở wet-ground + attenuation + state.

## Cấu trúc

- `mit/bevfusion` — working copy, pin `da93b27` (`mit/PIN.md`).
- `third_party/` — clone tham chiếu BEVFusion + devkit SemanticSpray, read-only.
- `data/` — nuScenes mirror info + SemanticSpray 31 GB, gitignore.
- `spray/`, `proxy_eval/`, `scripts/`, `tests/`, `kaggle/`, `docs/`.

## Legacy (local only)

`kernel/`, `interactive/`, `results/phase-b1-nuscenes-mini/` là harness cũ chạy BEVFusion của
OpenMMLab. Giữ local, không commit, **không phải bằng chứng cho pilot** và nằm ngoài phạm vi.