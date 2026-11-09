# 11-c3b: runner eval A/B trên kernel (4 ô: 2 arm × 2 điều kiện)

HEAD: a60b78b  Nhánh: main  Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
Skill: tdd (/Users/huynguyen/.agents/skills/tdd/SKILL.md)

## Bối cảnh

- 11-c1 đã có `kaggle/train/ab_run.py` lưu `ckpt_armA.pth`, `ckpt_armB.pth`.
- 11-c2 đã có `scripts/make_eval_split.py`: lọc đúng 196 frame / 16 scene, ghi JSON
  `{"frames": [{"sample_token": ..., "scene": ...}, ...]}`.
- 11-c3a đã có `scripts/make_mini_split.py --tokens-json <json>`: dựng pkl cho đúng
  danh sách token đó.
- `proxy_eval.evaluate_files(pred_path, info_path)` trả dict có `map`, `recall`,
  `precision`, `recall_by_range`.
- `proxy_eval.bootstrap`: `per_scene_metric`, `paired_delta`, `scene_bootstrap`.

Thiếu mảnh cuối: chạy 2 checkpoint trên cùng 196 frame, mỗi checkpoint ở 2 điều kiện
(sạch / có plume), rồi tính Δ theo scene.

## Việc phải làm: `kaggle/train/ab_eval.py`

1. `prepare_eval_split(repo, workdir)`:
   - gọi `scripts/make_eval_split.py --out <workdir>/eval_196.json` (subprocess, dùng
     `sys.executable`), fail nếu marker `EVAL_SET_FAILED` hoặc file không tồn tại;
   - gọi `scripts/make_mini_split.py --tokens-json <json> --out <workdir>/eval_196.pkl`;
   - log `EVAL_SPLIT_OK frames=196 scenes=16`.
2. `build_eval_loader(pkl_path, plume: bool)`: dùng lại `smoke.build_loader` với
   `arm="B"` khi `plume=True`, `arm="A"` khi `plume=False`, `batch_size=1`,
   `shuffle=False`, `sweeps_num=0`. Không viết lại pipeline.
3. `run_cell(model, loader, out_dir)`: mỗi frame ghi 2 file
   `<out>/<sample_token>.pred.json` (`boxes_3d`, `scores_3d`, `labels_3d`, `class_names`)
   và `<out>/<sample_token>.gt.json` (`gt_boxes`, `gt_names`). Lấy GT từ batch
   `gt_bboxes_3d` / `gt_labels_3d` và tên lớp của dataset, không lấy từ `nusc` lần nữa.
   Log `EVAL_FRAME n=<i>/196` mỗi 20 frame.
4. `score_cell(pred_dir, gt_dir)` → `proxy_eval.evaluate_files` từng frame, trung bình
   `map`, `recall`, `precision` trên 196 frame, log
   `EVAL_CELL arm=<A|B> cond=<clean|spray> map=<4 số lẻ> recall=<4 số lẻ>`.
5. Tổng hợp: `EVAL_DELTA arm=<A|B> dmap=<B_spray − B_clean>` và
   `EVAL_OK delta_A=<..> delta_B=<..> interaction=<delta_B − delta_A> ci95=<lo,hi>`.
   CI lấy từ `scene_bootstrap` trên **16 scene**, paired (cùng scene, cùng frame).
6. `main(argv)` nhận `--steps` không cần; nhận `--ckpt-dir`, `--out-dir`,
   `--limit N` (mặc định 0 = đủ 196; dùng để chạy thử 5 frame trên kernel).
7. `kaggle/train/main.py`: thêm nhánh `--task ab-eval` → script `ab_eval.py`, thêm
   `EVAL_OK` vào `TASK_MARKERS`.

## Test (không cần torch, không cần devkit)

`tests/test_ab_eval.py`, tối thiểu 6 test, dùng hàm thuần:
- `score_cell` trên 2 thư mục JSON giả (dựng bằng tay) ra đúng số frame và giá trị map;
- `summarize_cells` trả đúng thứ tự khóa và đúng `interaction = delta_B − delta_A`;
- thiếu 1 file `.pred.json` ⇒ raise `FileNotFoundError` có tên token trong message;
- `parse_args` đọc `--limit`, `--ckpt-dir`, `--out-dir` đúng;
- `main.py` route `--task=ab-eval` sang `ab_eval.py` (test đã có sẵn kiểu này, mở rộng);
- `EVAL_OK` được `verdict()` chấp nhận.

## Ràng buộc

- Chỉ tạo `kaggle/train/ab_eval.py`, `tests/test_ab_eval.py`; sửa `kaggle/train/main.py`.
- Không chạm `third_party/`, `spray/plume*.py`, `kaggle/train/task_args.txt`,
  `scripts/make_eval_split.py`, `scripts/make_mini_split.py`.
- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/pytest -q tests/` phải xanh toàn bộ
  (hiện 169 passed, 4 skipped), rồi commit một commit duy nhất.
- Không push kernel, không sync dataset.