# 11-c1: entrypoint train A/B trên kernel (2 arm × 2000 bước)

HEAD: c364174  Nhánh: main
Skill: tdd (/Users/huynguyen/.agents/skills/tdd/SKILL.md)

## Bối cảnh đã có bằng chứng

- Kernel v8 `COMPLETE`, `SWEEPS_OK n_single=34720 n_multi=273637 ratio=0.9879` — đường sweeps chạy thật, nhưng **dataset train là keyframe-only**, nên A/B chốt `sweeps_num = 0`.
- Kernel v6: `s_per_step = 1,4546 s`, `peak_gb = 4,251/16`, `MINI_SPLIT_OK n=4000 scenes=698 val_scenes=150`.
- `kaggle/train/smoke.py` đã có sẵn các hàm dùng lại được: `find_dataroot`, `ensure_splits_file`, `run_mini_split`, `build_pipeline_steps`, `build_loader`, `prepare_model`, `run_arm`, `load_weights`, `log/fail`, `_set_sweeps_num`.

## Việc phải làm

### 1. `kaggle/train/main.py` — chọn script theo `--task`

Hiện `TASK = "smoke"` là hằng số, nên chỉ chạy được `smoke.py`. Đổi thành:

- `task_args.txt` có thể chứa `--task ab-run` ở bất kỳ vị trí nào.
- `parse_task(args)` tách token đó ra, trả `(task, rest)`; mặc định `task = "smoke"` khi không có.
- `--task` **không** được truyền xuống script con.
- `TASK_SCRIPT = "kaggle/train/%s.py" % task.replace("-", "_")` ⇒ `ab_run.py`.
- `TASK_MARKERS = ("SMOKE_OK", "SWEEPS_OK", "AB_TRAIN_OK")`.
- Log thêm `TASK_NAME <task>`.
- Nếu script không tồn tại ⇒ `TASK_FAILED script_missing` (rc khác 0), không traceback.
- `resolve_args_file`/`task_args`/`verdict` giữ nguyên hành vi.

### 2. `kaggle/train/ab_run.py` — train 2 arm

Một file tự chứa, chạy trong venv pinned với `cwd=e2e.REPO`. Tham số dòng lệnh:

```
--dataroot PATH        (mặc định: find_dataroot())
--steps 2000           số bước mỗi arm
--batch 2
--lr 1e-4
--weight-decay 0.01
--seed 0
--sweeps-num 0         ghi đè sweeps_num cho cả 2 arm
--out /kaggle/working  nơi ghi checkpoint + summary
--arms A B
--time-budget-s 9000   tự dừng và ghi checkpoint nếu sắp hết giờ
```

Yêu cầu hành vi:

1. Dựng mini split giống smoke (`ensure_splits_file` + dùng lại file nếu có), `n=4000`.
2. Với mỗi arm: `build_pipeline_steps(arm, vendor_pipeline)` → `build_loader(...)` **với `sweeps_num=args.sweeps_num`**; `prepare_model` nạp checkpoint pretrained `SCU-VIP-Lab/Pretrained_BEVFusion` như smoke.
3. Train đúng `steps` bước, `AdamW(lr, weight_decay)`, cùng seed cho cả 2 arm (`torch.manual_seed`, `np.random.seed`, `random.seed` đặt **trước** khi tạo loader từng arm).
4. Log mỗi 100 bước: `AB_STEP arm=A i=100 loss=… s=…`; mỗi 20 bước vẫn ghi được để dễ chẩn đoán lỗi hội tụ (dùng `--log-every`).
5. Cuối mỗi arm:
   - lưu `ckpt_arm<A|B>.pth` = `{"state_dict": model.state_dict(), "arm": …, "steps": …, "lr": …, "sweeps_num": …}`;
   - log `AB_ARM_OK arm=A steps=2000 s_per_step=… loss_first=… loss_last=… loss_mean_last100=… peak_gb=…`.
6. Cuối cả hai: ghi `ab_train_summary.json` (per-step times/losses + cấu hình + seed) và log `AB_TRAIN_OK arms=2 steps=2000 time_s=…`.
7. Mọi lỗi phải log marker rõ: `AB_FAILED <reason> [detail]` rồi `sys.exit(1)`. Bắt buộc có nhánh cho: thiếu dataroot, thiếu checkpoint, loss non-finite, hết `--time-budget-s`.
8. Không sửa `smoke.py` ngoài việc thêm `if __name__ == "__main__"` guard nếu thiếu; `ab_run.py` được phép `import smoke` (cùng thư mục, `cwd=e2e.REPO` nên thêm `sys.path.insert(0, os.path.dirname(__file__))`).

### 3. Test (không cần GPU, không cần torch)

Thêm `tests/test_ab_run.py`:

- `parse_task`: có `--task ab-run` ở đầu/giữa/cuối; không có ⇒ `("smoke", args)`; `--task` bị loại khỏi `rest`.
- `task_script("ab-run") == "kaggle/train/ab_run.py"`; `("smoke") == "kaggle/train/smoke.py"`.
- `arm_specs(["A","B"])` trả đúng 2 spec, mỗi spec `steps/lr/seed` giống nhau.
- `summarize_records` trên list giả: tính đúng `s_per_step`, `loss_first`, `loss_last`, `loss_mean_last100` (so với `statistics.mean`).
- `checkpoint_payload` có đủ key `state_dict/arm/steps/lr/sweeps_num` (dùng dict rỗng thay cho state_dict thật).
- `time_budget_exceeded(started, budget)` đúng ở biên.
- `ab_run.py` phải import được mà **không** cần torch: mọi `import torch` nằm trong hàm.

Yêu cầu: `pytest -q tests/` phải xanh toàn bộ (**130 passed, 4 skipped** hiện tại + test mới).

## Cấm

- Không sửa `mit/`, `third_party/`, pin `da93b27`.
- Không đổi `DEVKIT_PINS`, không đổi `BATCH/LR` của `smoke.py`.
- Không push kernel, không sửa `kaggle/train/task_args.txt`.
- Không commit; PM sẽ review và commit.

## Nghiệm thu PM sẽ kiểm

```bash
git diff --stat
pytest -q tests/
grep -n "AB_TRAIN_OK\|AB_FAILED\|AB_ARM_OK" kaggle/train/ab_run.py
grep -n "parse_task\|TASK_MARKERS" kaggle/train/main.py
```