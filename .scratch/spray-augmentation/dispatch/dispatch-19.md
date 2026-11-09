Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`
2. `.scratch/spray-augmentation/issues/19-kaggle-code-sync.md` ← nguồn đúng, làm đúng ticket này
3. `kaggle/eligibility/main.py` + `kaggle/eligibility/kernel-metadata.json` — mẫu script kernel đã chạy
   `COMPLETE` trước đó, copy cách làm
4. `kaggle/smoke_test/bevfusion-smoke-test.ipynb` + `kaggle/smoke_test/cells/` — **recipe cài
   mmcv/mmdet/mmdet3d** đã từng chạy được trên Kaggle. Dùng lại, đừng tự nghĩ version mới.

## Nhiệm vụ

Dựng đường đưa code lên Kaggle **không cần GitHub token**, vì repo private (404 từ ngoài) và `data/` 16 GB.

Phần 1: `scripts/kaggle_code_sync.py` — stage **chỉ file `git ls-files`** (2 MB, KHÔNG `data/`, KHÔNG `mit/`),
ghi `dataset-metadata.json` id `nguynhuy9669/bevfusion-spray-pilot-code`, `isPrivate: true`, rồi
`kaggle datasets create` (lần đầu) / `kaggle datasets version -m "<git sha>"` (các lần sau). Idempotent.

Phần 2: `kaggle/e2e/` script kernel `nguynhuy9669/bevfusion-e2e` mount dataset đó, clone
`mit-han-lab/bevfusion` @ `da93b27` (assert đúng sha), cài deps theo recipe smoke_test, chạy `pytest -q tests/`.

Phần 3: **chạy thật** — `kaggle kernels push` → chờ `COMPLETE` → `kaggle kernels output` lấy log.

## Xong khi

- [ ] Sync script in ra slug + version + số file + MB; dataset private tồn tại (`kaggle datasets list -m`).
- [ ] Kernel `COMPLETE`, log có **49 passed** (baseline 2026-11-07 — số khác thì báo số thật, KHÔNG sửa test)
- [ ] Log xác nhận `mit/bevfusion` = `da93b27`
- [ ] Commit: `chore(kaggle): sync tracked code to private dataset and add e2e script kernel`

## Ràng buộc cứng

- Không upload `data/`, checkpoint, hay `mit/` (vendor clone riêng). Không tạo dataset public.
- Không push gì lên GitHub. Không sửa `tests/`, không sửa `spray/`.
- Kernel phải private. `kaggle` CLI đã auth sẵn trong env này.
- Nếu cài `mmcv` fail trên image Kaggle: đọc lại đúng cell smoke_test đã từng chạy; nếu vẫn fail thì DỪNG,
  báo bước nào + nguyên văn lỗi, **không** tự hạ version hay đổi sang `mmcv-lite` mà không hỏi.

## Báo lại

1. dataset slug + version + số file + tổng MB
2. kernel status + 20 dòng log cuối (thấy `49 passed`)
3. bước nào tốn thời gian nhất / chỗ nào dễ vỡ lần sau