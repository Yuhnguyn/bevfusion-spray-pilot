# Ticket 10-ii — probe trên T4: build model + load checkpoint + freeze list thật

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · HEAD `fcaa4f9` · 1 lần push kernel.

## Mục tiêu (đúng phạm vi, không mở rộng)

Chứng minh trên GPU thật:

1. model dựng được từ model config đã pin;
2. checkpoint load được, **không** thiếu/thừa weight đáng kể;
3. freeze list áp lên **model thật** đúng như thiết kế (camera đóng băng, phần còn lại mở);
4. bộ nhớ cần cho train (params + grad + AdamW state) — con số [ĐO], không phải suy đoán.

**Không** làm trong ticket này: dataloader nuScenes, forward/backward, đo s/step. Thời gian mỗi step sẽ
đo ở đầu ticket 11 khi đã có batch thật; ghi rõ vào report là "đo ở 11".

## File 1 — `kaggle/train/probe.py` (mới, chạy trong venv Python 3.8 của kernel)

Cấu trúc:

```python
import json, os, pathlib, sys, time
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CKPT_URL = "https://huggingface.co/SCU-VIP-Lab/Pretrained_BEVFusion/resolve/main/bevfusion-det.pth"
CKPT_SHA256 = "ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122"   # ticket 06
CKPT_PATH = pathlib.Path("/kaggle/working/bevfusion-det.pth")
```

Các bước, mỗi bước in một dòng `PROBE_STEP <tên> <kết quả>`:

1. **download** nếu chưa có (`urllib.request.urlretrieve`), in byte + `sha256` và **assert khớp**
   `CKPT_SHA256`; nếu lệch ⇒ in `PROBE_FAILED ckpt_sha` rồi `sys.exit(1)`.
2. **register pipelines**: `import spray.pipeline` (module tự gọi `install()`), rồi đăng ký mmdet3d transforms
   đúng như `tests/test_pipeline_e2e.py::_register_mmdet3d_pipelines` (chép nguyên ý tưởng: stub
   `mmdet3d.datasets` trong `sys.modules` rồi import `mmdet3d.datasets.pipelines.transforms_3d`).
3. **build model**: `mmcv.Config.fromfile(MODEL_CONFIG)` với
   `MODEL_CONFIG = "mit/bevfusion/configs/nuscenes/det/transfusion/secfpn/camera+lidar/swint_v0p075/default.yaml"`,
   rồi `from mmdet3d.models import build_model; model = build_model(cfg.model, train_cfg=..., test_cfg=...)`.
   Nếu vendor cần `train_cfg`/`test_cfg` thì lấy từ cfg, đừng tự bịa.
4. **load checkpoint**: `torch.load(..., map_location="cpu")`; state dict có thể nằm ở key `state_dict`/`model`.
   Gọi `model.load_state_dict(sd, strict=False)` rồi in:
   `missing=<n>` `unexpected=<n>` và **20 tên đầu** của mỗi loại.
   Điều kiện đạt: `missing == 0` và `unexpected` chỉ chứa key không phải tham số học
   (ví dụ `_metadata`, buffer của optimizer). Nếu `missing > 0` ⇒ vẫn in hết nhưng **không** coi là đạt,
   in `PROBE_FAILED ckpt_load`.
5. **freeze**: `from spray.freeze import apply_freeze; report = apply_freeze(model)`; in
   `n_total_params`, `n_trainable_params`, `n_frozen`, `len(unmatched)` và **toàn bộ** `unmatched`
   (viết ra `probe.json`, không in hết ra log nếu > 40 dòng).
   In thêm 8 tên trainable đầu và 8 tên frozen đầu để PM đối chiếu bằng mắt.
6. **bộ nhớ**: tính bằng số tham số thật:
   - weights: `n_total_params * 4` bytes (fp32);
   - grad: `n_trainable_params * 4`;
   - AdamW state (exp_avg + exp_avg_sq): `2 * n_trainable_params * 4`;
   - in cả `GB` và **tổng** `weights + grad + adam`.
   (KHÔNG dùng `torch.cuda.max_memory_allocated` ở bước này — chưa có forward nên con số sẽ vô nghĩa.)
7. **ghi** `/kaggle/working/probe.json` với tất cả số trên; in `PROBE_OK <json một dòng>` ở cuối.

Ràng buộc:
- Không sửa `spray/**`, `tests/**`, `mit/**`. Chỉ tạo `kaggle/train/*`.
- Không bật GPU bắt buộc: nếu `torch.cuda.is_available()` false thì vẫn chạy trên CPU và ghi
  `"device": "cpu"` — probe này không cần GPU để đúng.
- Mọi thứ in ra phải có tiền tố dễ grep: `PROBE_STEP`, `PROBE_OK`, `PROBE_FAILED`.

## File 2 — `kaggle/train/main.py` (mới, boot bằng code của e2e)

Không chép lại 700 dòng cài đặt. Tìm và import `kaggle/e2e/main.py` từ dataset mount:

```python
import importlib.util, pathlib, sys
boot = next(pathlib.Path("/kaggle/input").rglob("kaggle/e2e/main.py"))
spec = importlib.util.spec_from_file_location("e2e_boot", boot)
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)

e2e.extract_code()
e2e.clone_pin()
e2e.install_env()
toolchain = e2e.choose_toolchain()
ok, report = e2e.build_ops(toolchain)
ok = ok and e2e.verify_stack()[0]
rc, text = e2e.stream([str(e2e.PY), "kaggle/train/probe.py"], cwd=e2e.REPO, timeout=3600, log_name="probe.log")
sys.exit(0 if (rc == 0 and "PROBE_OK" in text) else 1)
```

Nếu `e2e.PY`/`e2e.REPO`/`e2e.stream` không tồn tại với tên đó, đọc file và dùng đúng tên thật — **không**
đoán. Nếu import thất bại vì `main.py` chạy gì đó ở module level, bọc bằng `runpy` hoặc copy riêng phần
hàm cần; ghi lại cách làm trong commit message.

## File 3 — `kaggle/train/kernel-metadata.json`

```json
{
  "id": "nguynhuy9669/bevfusion-spray-probe",
  "title": "BEVFusion spray probe",
  "code_file": "main.py",
  "language": "python",
  "kernel_type": "script",
  "is_private": true,
  "enable_gpu": true,
  "enable_tpu": false,
  "enable_internet": true,
  "keywords": [],
  "dataset_sources": ["nguynhuy9669/bevfusion-spray-pilot-code"],
  "kernel_sources": [],
  "competition_sources": [],
  "model_sources": []
}
```

## Chạy

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/     # 94 passed, 4 skipped (không đổi)
git add -A && git commit -m "feat(probe): T4 probe for checkpoint load, freeze list and memory"
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python scripts/kaggle_code_sync.py
kaggle kernels push -p kaggle/train
for i in $(seq 1 40); do s=$(kaggle kernels status nguynhuy9669/bevfusion-spray-probe); echo "$i $s"; case "$s" in *COMPLETE*|*ERROR*|*FAILED*|*CANCEL*) break;; esac; sleep 30; done
kaggle kernels output nguynhuy9669/bevfusion-spray-probe -p /tmp/kprobe
grep -n "PROBE_" /tmp/kprobe/*.log | tail -30
```

## Điều kiện ĐẠT

Log phải có:

- `PROBE_STEP ckpt_sha` khớp `ee0a389…`;
- `PROBE_STEP ckpt_load missing=0`;
- `PROBE_STEP freeze` với `n_trainable_params > 0` và **toàn bộ** frozen name bắt đầu bằng
  `encoders.camera.` / `img_` (kiểm bằng mắt, in ra rồi PM đọc);
- `PROBE_STEP memory` có 3 số GB;
- `PROBE_OK`.

Nếu `unmatched` khác rỗng: **không tự sửa** `spray/freeze.py`. Dán danh sách `unmatched` + `PROBE_OK` (nếu vẫn
in được) và dừng — PM sẽ quyết định tên prefix đúng.

## Báo cáo

- `git log --oneline -1`
- 6–10 dòng `PROBE_*` (dán nguyên)
- `PROBE_OK` JSON
- nếu fail: 30 dòng log cuối + mã lỗi `kaggle kernels status`