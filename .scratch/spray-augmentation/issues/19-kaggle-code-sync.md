# 19: Kaggle code access (private dataset + script kernel)

**What to build:** Đường đưa code repo lên Kaggle không cần GitHub token: đóng gói file **tracked** của repo
thành Kaggle Dataset **private**, và một script kernel mount dataset đó để chạy `pytest` trên image có
`mmcv/mmdet3d`.

**Blocked by:** — (hạ tầng)

**Status:** ready-for-agent

## Vì sao cần

- Repo `github.com/Yuhnguyn/bevfusion-spray-pilot` là **private** (HTTP 404 từ ngoài) ⇒ kernel Kaggle
  không clone được, trừ khi thêm PAT vào secrets.
- `data/` là 16 GB (SemanticSpray) + tổng working dir 32 GB ⇒ **không** upload repo như một khối.
- File **tracked** chỉ **2.092 KB** ⇒ upload làm dataset private là rẻ và không cần credential ngoài.
- Ticket 09 (e2e trên class vendor thật), 10 (memory/time probe T4), 11 (A/B) đều cần image có
  `mmcv/mmdet3d` mà laptop không có.

## Phải làm

### 1. `scripts/kaggle_code_sync.py`

- Staging dir trong temp (ngoài repo), copy **chỉ `git ls-files`** — không `data/`, không `mit/`
  (vendor pinned clone riêng), không `results/` nặng nếu lớn.
- Ghi `dataset-metadata.json`: `id = nguynhuy9669/bevfusion-spray-pilot-code`, title rõ, `isPrivate: true`.
- Tạo mới nếu chưa có (`kaggle datasets create -p ...`), nếu có thì `kaggle datasets version -p ... -m "<git sha>"`.
- In ra: số file, tổng bytes, dataset slug + version sau khi xong.
- Chạy lại nhiều lần phải **idempotent** (không tạo 2 dataset trùng tên lạ).

### 2. `kaggle/e2e/` — script kernel

- `kernel-metadata.json`: `id = nguynhuy9669/bevfusion-e2e`, `code_file = main.py`, `kernel_type = script`,
  `enable_gpu = true`, `enable_internet = true`, `is_private = true`,
  `dataset_sources = ["nguynhuy9669/bevfusion-spray-pilot-code"]`.
- `main.py` phải: (a) copy code từ `/kaggle/input/bevfusion-spray-pilot-code/` sang `/kaggle/working/repo`;
  (b) clone `https://github.com/mit-han-lab/bevfusion.git` vào `repo/mit/bevfusion`, checkout **`da93b27`**
  và **assert** `git rev-parse --short HEAD == da93b27`; (c) cài `mmcv`/`mmdet`/`mmdet3d` theo đúng
  recipe mà `kaggle/smoke_test` đã dùng (đọc file đó, đừng tự nghĩ version mới); (d) chạy
  `pytest -q tests/` trong `repo/`; (e) in rõ `PASSED/FAILED` + exit code khác 0 nếu test fail.
- Không hard-code model checkpoint; ticket này chỉ cần import + test chạy.

### 3. Chạy thật một lần

`kaggle kernels push` → chờ `COMPLETE` → `kaggle kernels output` lấy log → dán 20 dòng cuối vào báo cáo.

## Xong khi

- [ ] `scripts/kaggle_code_sync.py` chạy được, in ra dataset slug + version, không upload `data/`.
- [ ] Dataset private tồn tại, liệt kê được bằng `kaggle datasets list -m`.
- [ ] Kernel `nguynhuy9669/bevfusion-e2e` chạy `COMPLETE`, log có `pytest` chạy **49 passed**
      (baseline 2026-11-07; nếu khác thì báo số thật, đừng sửa test).
- [ ] Log có dòng xác nhận `mit/bevfusion` đúng `da93b27`.
- [ ] Không commit file rác; commit message:
      `chore(kaggle): sync tracked code to private dataset and add e2e script kernel`

## Ràng buộc cứng

- **Không** upload `data/`, không upload checkpoint, không upload `mit/` (vendor).
- **Không** push gì lên GitHub.
- Không sửa test, không sửa `spray/`.
- Không tạo dataset public. Nếu `kaggle` CLI báo thiếu quyền ⇒ DỪNG báo PM kèm nguyên văn lỗi.
- Kernel phải **private**.

## Báo lại

1. dataset slug + version + số file + tổng MB
2. kernel status + 20 dòng log cuối
3. nếu image Kaggle thiếu gì (mmcv build fail…) thì báo rõ bước nào, không tự đổi sang bản khác