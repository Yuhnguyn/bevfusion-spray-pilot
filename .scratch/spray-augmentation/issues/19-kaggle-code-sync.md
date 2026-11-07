# 19: Kaggle code access (private dataset + script kernel)

**What to build:** Đường đưa code repo lên Kaggle không cần GitHub token: đóng gói file **tracked** của repo
thành Kaggle Dataset **private**, và một script kernel mount dataset đó để chạy `pytest` trên image có
`mmcv/mmdet3d`.

**Blocked by:** — (hạ tầng)

**Status:** done

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

- [x] `scripts/kaggle_code_sync.py` chạy được, in ra dataset slug + version, không upload `data/`.
- [x] Dataset private tồn tại, liệt kê được bằng `kaggle datasets list -m`.
- [x] Kernel `nguynhuy9669/bevfusion-e2e` chạy `COMPLETE`, log có `pytest` chạy **49 passed**
      (baseline 2026-11-07; nếu khác thì báo số thật, đừng sửa test).
- [x] Log có dòng xác nhận `mit/bevfusion` đúng `da93b27`.
- [x] Không commit file rác; commit message:
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

## Kết quả (Kaggle latest, 2026-11-07)

**Dataset** `nguynhuy9669/bevfusion-spray-pilot-code` — private.

- `scripts/kaggle_code_sync.py` stage đúng `git ls-files`: **110 file**, **1,899,601 B (1.81 MB)**.
  Chặn cứng `data/`, `third_party/`, `results/`, `archive/`, `kernel/`, `interactive/`,
  `notebook-kernel/`, mọi path `mit/*` trừ `mit/PIN.md`, và mọi file tracked > 50 MB.
- Payload `code.tar` **2,099,200 B (2.00 MB)**. Kaggle tự extract archive và giữ nguyên cây
  thư mục; dataset page báo 460,387 B (đã nén).
- `datasets create` → v1; các lần sau `datasets version -m "<short sha>"` → v2 (kernel run),
  v3 sau commit này. Idempotent nhờ `kaggle datasets status <ref> --format json` trước khi ghi;
  create fail (title đã dùng) thì fallback sang version, không tạo dataset trùng.
- Không bao giờ truyền `--public`; metadata có `isPrivate: true`.

**Kernel** `nguynhuy9669/bevfusion-e2e` (private, script, GPU T4), version 2 = `COMPLETE`,
elapsed **516 s**:

```
MIT_PIN_OK da93b27 da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea
PINNED_WHEELS_OK 1.10.1+cu113 1.4.0 2.20.0
OPS_OK                      # 12/12 extension + bev_pool + voxelize (49,984 voxel)
49 passed, 1 warning in 9.93s
PYTEST_PASSED 49
E2E_OK
```

- Toolchain: apt ubuntu2204 `cuda-nvcc-11-8` (nvcc 11.8.89) + `gcc-11`;
  `TORCH_CUDA_ARCH_LIST=7.5`; `cuda_guard_bypassed=false`.
- Run #1 (`ERROR`) chỉ vì mount path: Kaggle mount ở `/kaggle/input/datasets/<owner>/<slug>`,
  không phải `/kaggle/input/<slug>`. `find_mount()` giờ thử cả hai layout rồi fallback dò
  `pytest.ini` đệ quy trong `/kaggle/input`.

**Đối chiếu recipe với các cell đã chứng minh** (03, 04, 06, 07):

| Hạng mục | Cell gốc | `kaggle/e2e/main.py` |
|---|---|---|
| venv | `uv python install 3.8.20` + `uv venv --python 3.8.20`, fallback `--python 3.8` | giống |
| setuptools | `setuptools==59.5.0 wheel packaging==21.3 ninja` | giống |
| torch | cu113 index + `unsafe-best-match`, `torch==1.10.1+cu113 torchvision==0.11.2+cu113 numpy==1.22.4` | giống |
| mmcv | `-f .../mmcv/dist/cu113/torch1.10.0/index.html mmcv-full==1.4.0` | giống |
| mmdet | `mmdet==2.20.0 matplotlib terminaltables pycocotools six scipy pyyaml numpy==1.22.4 numba==0.58.1` | giống |
| probe | `1.10.1+cu113 1.4.0 2.20.0` | giống |
| CUDA | ubuntu2204 repo, 3 lần apt riêng (nvcc/cudart, cusparse+cublas+curand, cusolver), gcc-11 | giống |
| build env | `FORCE_CUDA=1`, `MAX_JOBS=min(4,cpu)`, `TORCH_CUDA_ARCH_LIST`, `CXXFLAGS=-O2 -include limits -include cstdint`, `NVCC_PREPEND_FLAGS=--allow-unsupported-compiler ...` | giống |
| ops check | 12 extension + `bev_pool` + hard voxelize, `OPS_OK` | giống |
| pytest install | không có | **thêm** `uv pip install pytest` (bắt buộc để chạy `pytest`) |
| reinstall | skip nếu venv đã đúng pin | luôn cài (kernel là máy mới) |
| ops artifact | ghi `artifacts/ops.json` | chỉ in JSON ra log, không ghi file |
| clone path | `/root/bevfusion_smoke/bevfusion` | `/kaggle/working/repo/mit/bevfusion` (theo ticket) |
| cleanup | không | xoá `mit/bevfusion/build` sau khi verify để output kernel nhỏ |
