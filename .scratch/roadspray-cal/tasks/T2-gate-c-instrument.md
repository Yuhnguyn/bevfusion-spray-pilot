# T2 — Dụng cụ Cổng C: `scripts/sspp_infer.py` + bundle Kaggle

> Worker: `gate-c-runner` (subagent). Lead review + commit. Viết 2026-11-19.

## Vì sao cổng C tồn tại
Cổng C là cổng **duy nhất có thể giết** hướng "train detector với plume". Câu hỏi: bơm plume
vào frame SSPP **sạch** thì detector (zero-shot) có sinh **false positive** (báo xe ma) nhiều
hơn không? Nếu không tăng ⇒ hướng train vô nghĩa ⇒ dừng. Phải dựng dụng cụ đo **trước** khi
tốn GPU.

## Sản phẩm 1 — `scripts/sspp_infer.py` (file mới)
- BEVFusion LiDAR-only, repo pin `da93b27`, checkpoint `data/lidar-only-det.pth` ("Model 0",
  zero-shot, **không train**), chạy trên frame SSPP.
- Hai nhánh paired, cùng seed: `--arm clean` (không bơm) và `--arm plume` (bơm qua
  `spray/plume.py::inject_plume_stateful` / `PlumeTransform`).
- `--limit N` chạy thử; `--dry-run` kiểm tra plumbing.
- Output `detections.jsonl`, mỗi dòng:
  `{"scene_token","frame_idx","arm","boxes":[{"x","y","z","dx","dy","dz","yaw","score","label"}]}`
- **Bắt buộc:** `--dry-run` chạy được trên máy local **không có mmcv/mmdet/mmdet3d** ⇒ mọi
  import nặng phải nằm trong hàm. `--dry-run` in kế hoạch: số scene, số frame, đường dẫn
  config + checkpoint, crop, ngưỡng score, số mẫu mỗi nhánh.
- Cấu hình đã chốt: `pointpillars` config vendored, crop `[0,64] × [−16,16] m`,
  `with_velocity: false` (**bắt buộc**), sensor VLP-32C.
- **3 bug đã biết** (tìm trong `HANDOFF.md` + `.scratch/roadspray-cal/plan.md`, mục detector /
  Kaggle). Ghi rõ đã xử lý bug nào, ở đâu, thế nào.

## Sản phẩm 2 — `kaggle/gate_c/`
- `kernel.py` + `kernel-metadata.json` (+ `dataset-metadata.json` nếu cần).
- `kaggle` CLI có sẵn: `/Users/huynguyen/.local/bin/kaggle`, token `~/.kaggle/access_token`.
- Kernel phải: cài mmcv/mmdet/mmdet3d đúng pin, có input SSPP, chạy 2 nhánh, ghi
  `detections.jsonl` ra `/kaggle/working`.
- Nếu push bị chặn (auth / quota / internet / 2FA): **báo chính xác lệnh + thông báo lỗi** +
  các bước user phải làm tay. **Không được giả vờ đã chạy.**

## Sản phẩm 3 — `docs/measurements/gate-c-runbook.md`
Lệnh chính xác từng bước (local dry-run → push → lấy output), thời gian ước tính, dung lượng
output, cách biết thành công/thất bại, tiêu chí quyết định cổng C.

## RÀNG BUỘC
- **KHÔNG ghi** vào `spray/`, `tests/`, `scripts/measure_plume_size_tail.py`,
  `scripts/visualize_plume_vs_real.py`, `docs/adr/` (worker khác sở hữu — chỉ đọc).
- Write-scope của bạn: `scripts/sspp_infer.py`, `kaggle/`, `docs/measurements/gate-c-runbook.md`.
- Worker `plume-calibrator` đang sửa `spray/plume_state.py` (bảng bán kính, spawn_scale); chữ ký
  public API giữ nguyên. Đọc được, đừng ghi.
- **KHÔNG `git commit`.** Không xoá file ngoài workspace. Không dùng `timeout` (macOS).
- File chưa track của user: `scripts/{audit_*,diag_*,probe_*}.py` — đừng sửa, đừng xoá.
- Python: `CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python ...`
- Không bịa số. Thiếu dữ liệu/checkpoint thì báo Lead kèm bằng chứng (`ls`, `find`).

## ACCEPTANCE
1. `--dry-run` exit 0 trên local, in kế hoạch hợp lý.
2. `python -m pytest tests -q` vẫn xanh (không được làm hỏng test).
3. Kaggle: push thành công HOẶC báo cáo lỗi + bước thủ công rõ ràng.
4. Runbook đủ để Lead/user chạy lại mà không cần hỏi.

## BÁO CÁO CHO LEAD (<150 dòng)
1. Output `--dry-run` (N scene/frame, config, checkpoint). 2. Trạng thái Kaggle (push được?
lỗi gì?). 3. 3 bug: xử lý cái nào, ở đâu. 4. `pytest` result. 5. Việc còn lại + ai làm.
