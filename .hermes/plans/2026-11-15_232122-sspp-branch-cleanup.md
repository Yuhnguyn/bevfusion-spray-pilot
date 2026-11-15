# Kế hoạch: tách nhánh `sspp` và dọn repo về đúng hướng SemanticSpray++

**Mục tiêu:** tạo nhánh `sspp` từ `main` @ `f3fb7d2`, cắt bỏ mọi thứ thuộc hướng cũ
(nuScenes + plume inject), giữ lại đúng những gì hướng mới cần, để hai hướng phát triển
song song mà không giẫm lên nhau.

**Không làm trong plan này:** không train, không sửa generator, không viết adapter SSPP.
Plan này chỉ tạo nhánh + dọn. Code của hướng mới là plan riêng
(`2026-11-13_171500-sspp-plan-ngan.md`).

---

## 0. Nguyên tắc dọn

1. **`main` không bị chạm.** Mọi thao tác trên nhánh `sspp`. `main` giữ nguyên `f3fb7d2`
   làm bản đối chứng của hướng cũ.
2. **Xoá bằng `git rm`, không xoá file trên đĩa.** Lịch sử còn nguyên, `git checkout main -- <path>`
   lấy lại được bất cứ lúc nào.
3. **Mỗi bước một commit.** 6 commit, mỗi commit đúng một loại việc. Nếu bước sau sai,
   `git reset --hard` về commit trước, không phải gỡ tay.
4. **Cổng chặn sau mỗi commit:** `pytest` phải xanh và **số test không được giảm quá số test
   đã xoá có chủ ý**. Test đỏ = commit đó sai, không được đi tiếp.
5. **Không sửa nội dung file được giữ.** Nếu một file cần sửa để chạy được trên nhánh mới,
   đó là dấu hiệu file đó thuộc hướng cũ → xoá, đừng sửa.

---

## 1. Hiện trạng đo được (trước khi dọn)

| Hạng mục | Số | Ghi chú |
|---|---|---|
| Commit gốc | `f3fb7d2` | `main`, đã push `origin/main` |
| Test baseline | **318 passed, 4 skipped** | 4 skip = `test_pipeline_e2e` cần mmcv |
| File tracked | 330 | |
| `spray/*.py` | 18 module (+`__init__`) | |
| `proxy_eval/*.py` | 3 module (+`__init__`) | |
| `tests/test_*.py` | 38 file | |
| `scripts/*.py` | 25 file | |
| `kaggle/` | 53 file, 5 kernel | |
| `.scratch/` | 130 file | board 48 ticket |
| `docs/` | 50 file | |
| `data/` | 31 GB | gitignored, **không đụng** |
| `third_party/` | 102 MB | gitignored, **không đụng** |

**Ràng buộc môi trường:** `pytest` phải chạy bằng
`CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python -m pytest -q tests/`.
Không có `env -u PYTHONPATH` thì numpy 2.5.4 của venv Python 3.14 bị nạp vào Python 3.11
và toàn bộ test lỗi import.

---

## 2. Ranh giới hai hướng — cái gì giữ, cái gì bỏ

Hướng mới (SSPP) cần đúng **12 module** (10 trong `spray/` + 2 trong `proxy_eval/`),
tính bằng đóng bắc cầu import thật:

```
spray.semantic_stats → spray.spray_stats
spray.semantic_split
spray.plume_context, spray.plume_state, spray.plume, spray.plume_transform
spray.raycast → spray.beam_model
spray.wet_ground
proxy_eval.matcher, proxy_eval.bootstrap
```

| Nhóm | Giữ trên `sspp` | Bỏ khỏi `sspp` |
|---|---|---|
| Sinh plume | `plume.py`, `plume_state.py`, `plume_context.py`, `plume_transform.py`, `raycast.py`, `beam_model.py`, `wet_ground.py` | – |
| Đo spray thật | `semantic_stats.py`, `semantic_split.py`, `spray_stats.py` | – |
| Đánh giá | `proxy_eval/matcher.py`, `proxy_eval/bootstrap.py` | `proxy_eval/mit_adapter.py` |
| Dây chuyền nuScenes | – | `mini_split.py`, `ab_config.py`, `config_merge.py`, `pipeline.py`, `model_routing.py`, `spray_context_transform.py`, `denoise.py`, `freeze.py` |
| Kernel Kaggle | – | toàn bộ `kaggle/` (5 kernel) |
| Script | 3 script semantic | 23 script còn lại |

**Vì sao giữ `plume_transform.py` mà bỏ `spray_context_transform.py`:** cái đầu là chỗ chèn
plume vào pipeline, hướng mới vẫn dùng để sinh spray tổng hợp trên frame SSPP. Cái sau đọc
sidecar `data/plume_speed_index.json` sinh từ **nuScenes infos** — hướng mới lấy tốc độ từ
`metadata.txt` của SSPP, nên nó là dây nuScenes, không phải dây plume.

---

## 3. Ba thứ giữ lại nhưng hướng mới chưa dùng

Ghi rõ ở đây để người đọc sau không tưởng chúng còn sống:

| File | Vì sao vẫn ở `sspp` | Trạng thái thật |
|---|---|---|
| `spray/wet_ground.py` | `plume_transform` import nó; bỏ thì import gãy | Mặc định **tắt** (`wet_ground=None`) |
| `proxy_eval/matcher.py` | `evaluate_frame` + `average_precision` dùng được cho box 7 chiều | `class_names` là tham số bắt buộc của `EvalConfig`, **không** hard-code 10 class → truyền `("car","van")` là chạy được ngay |
| `spray/plume.py` hàm `inject_plume` (không trạng thái) | `spray/__init__.py` export nó | v1, đã bị `inject_plume_stateful` thay; chỉ `test_plume.py` còn gọi |

**`proxy_eval/matcher.py` là module sạch nhất trong 12 module** — `class_names` là tham số,
`range_m` mặc định 54 nhưng truyền được. Nó chạy được cho SSPP mà không phải sửa dòng nào
(đã kiểm: `tests/test_matcher.py` dùng `EvalConfig(class_names=("car","truck"))`). Điều duy nhất
phải làm khi viết adapter là truyền đúng 2 class.

---

## 4. Bảng số test theo từng bước (đã đo, dùng làm cổng chặn)

| Sau bước | Việc | Test còn | Đo bằng |
|---|---|---|---|
| 0 | baseline `main` | **318 passed + 4 skipped** | `pytest -q tests/` |
| 1 | bỏ 9 module + 18 test dây nuScenes | **180** | chạy đúng 20 file còn lại |
| 2 | bỏ `kaggle/` + `test_task_args.py` | **167** | chạy đúng 19 file |
| 3 | bỏ 23 script + 3 test của chúng | **151** | chạy đúng 16 file |
| 4–6 | chỉ xoá doc + viết lại 5 file | **151** | `pytest -q tests/` |

Nếu một bước ra số khác bảng này, dừng lại: hoặc có test bị xoá nhầm, hoặc có test mới
phụ thuộc file vừa xoá.

---

## 5. Sáu bước

### Bước 0 — Tạo nhánh, chốt mốc

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
git status --porcelain          # phải rỗng, ngoài .hermes/ và graphify-out/
git switch -c sspp main
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python -m pytest -q tests/ | tail -1
```

**Kỳ vọng:** `318 passed, 4 skipped`. Ghi số này vào commit đầu tiên. Nếu khác, dừng —
môi trường đã đổi, mọi so sánh sau đó vô nghĩa.

`.hermes/` và `graphify-out/` đang untracked. Thêm `graphify-out/` vào `.gitignore` ở bước này
(một dòng), để `git status` sạch cho 6 commit sau.

---

### Bước 1 — Bỏ dây chuyền nuScenes (9 module + 18 test)

**Xoá:**

```
spray/mini_split.py
spray/ab_config.py
spray/config_merge.py
spray/pipeline.py
spray/model_routing.py
spray/spray_context_transform.py
spray/denoise.py
spray/freeze.py
proxy_eval/mit_adapter.py

tests/test_mini_split.py
tests/test_mini_split_ast.py
tests/test_make_mini_split_tokens.py
tests/test_ab_config.py
tests/test_ab_run.py
tests/test_ab_eval.py
tests/test_config_merge.py
tests/test_pipeline_plumbing.py
tests/test_pipeline_e2e.py
tests/test_routing.py
tests/test_spray_context_transform.py
tests/test_denoise.py
tests/test_freeze.py
tests/test_eval_split.py
tests/test_smoke_sweeps.py
tests/test_kaggle_devkit_install.py
tests/test_plume_config_yaml.py
tests/test_mit_adapter.py
```

**Vì sao `test_plume_config_yaml.py` đi cùng nhóm này:** nó kiểm `spray/config/plume_default.yaml`
khớp với `ab_config.SPRAY_PARAMS`. `ab_config` mất thì test mất chỗ dựa.

**Kiểm trước khi xoá** — phải rỗng **sau khi trừ chính các file sắp xoá**. Nếu không rỗng thì
có file khác đang dùng và phải xử lý file đó trước:

```bash
grep -rn "mini_split\|ab_config\|config_merge\|model_routing\|spray_context_transform\|spray.denoise\|spray.freeze\|from spray.pipeline" \
  --include=*.py spray/ proxy_eval/ \
  | grep -v -E "spray/(mini_split|ab_config|config_merge|model_routing|spray_context_transform|denoise|freeze|pipeline)\.py"
```

Đã chạy thử: chỉ còn `spray/ab_config.py` tự import `spray.config_merge` — tức là tham chiếu
nội bộ trong nhóm bị xoá, không phải phụ thuộc ngoài. An toàn.

**Kỳ vọng sau commit:** `180 passed` — đã đo bằng cách chạy đúng 20 file test còn lại
(`180 passed in 2.78s`). Con số giảm tiếp ở bước 2 (13 test) và bước 3 (16 test).

---

### Bước 2 — Bỏ toàn bộ kernel Kaggle

**Xoá:** `kaggle/` (53 file, 5 kernel: `train`, `e2e`, `smoke_test`, `eligibility`, `dataset_gate`).

**Lý do, kiểm từng kernel:** `train` và `e2e` boot bằng `kaggle/e2e/main.py` để dựng venv
Python 3.8 + mmcv-full 1.4.0 + mmdet3d `da93b27`. `eligibility` cần `nuscenes-devkit 1.1.11`
để quét 850 scene nuScenes. `dataset_gate` chấm dataset nuScenes. `smoke_test` là 20+ cell
notebook của dây cũ. Cả 5 đều là nuScenes — không cái nào dùng được cho SSPP.

Hướng mới cần một kernel khác: dataset SSPP (31 GB, đã có local), không cần devkit nuScenes,
không cần 6 camera. Viết mới rẻ hơn sửa 53 file.

**Xoá kèm:** `scripts/kaggle_code_sync.py` (sync code lên dataset Kaggle của dây cũ) và
`tests/test_task_args.py` (13 test).

**Vì sao `test_task_args.py` phải đi ở bước này, không phải bước 1:** nó đọc
`kaggle/train/main.py` để lấy hàm `task_args`. Đã thử `mv kaggle /tmp` rồi chạy: **13 failed**
(`FileNotFoundError`). `kaggle/` mất thì test này mất đối tượng, không có cách sửa.

**Kỳ vọng sau commit:** `167 passed` — đã đo (`167 passed in 4.60s`).

**Giữ:** `mit/PIN.md`. `mit/bevfusion` là gitignored nhưng `PIN.md` ghi commit pin — hướng mới
vẫn cần clone đúng commit đó.

---

### Bước 3 — Bỏ script của hướng cũ (23 file)

**Giữ 3 script:**

| Script | Vì sao giữ |
|---|---|
| `fetch_semantic_spray.py` | tải dataset SSPP từ Oparu |
| `semantic_spray_split.py` | build/verify split cal–held-out |
| `semantic_spray_stats.py` | đo thống kê spray |

**Xoá 23 script:** `build_kanban.py`, `build_plume_speed_index.py`, `make_eval_split.py`,
`make_mini_split.py`, `measure_29ec.py`, `measure_29ed.py`, `measure_29ed2.py`,
`measure_29ed3.py`, `measure_29f.py`, `measure_beam_angles.py`, `measure_beam_table.py`,
`measure_ego_motion.py`, `measure_plume_geometry.py`, `measure_speeds.py`,
`measure_spray_height.py`, `plume_density_table.py`, `plume_v2_measure_common.py`,
`serve_range.py`, `verify_frame_geometry.py`, `visualize_plume.py`, `render_clips.py`,
`kaggle_code_sync.py`, `kanban_template.html`.

**Ba quyết định đã chốt cho nhóm này:**

| File | Quyết định | Lý do |
|---|---|---|
| `plume_density_table.py` + `tests/test_plume_density_table.py` | **xoá cả hai, cùng commit** | Bảng mật độ của generator cũ; hướng mới không dùng |
| `visualize_plume.py` + `render_clips.py` | **xoá cả hai** | `render_clips.py:36` import 13 hàm từ `visualize_plume` → một cặp. Cả hai vẽ plume generator cũ cạnh spray thật — phép so sánh hướng mới không làm |
| `measure_29*.py` | **xoá** | Đọc `data/SemanticSprayDataset` (đúng dữ liệu hướng mới) nhưng đo generator cũ. Giữ lại thì người đọc sau tưởng còn sống |

**Kỳ vọng:** `151 passed` — đã đo. Ba test của script bị xoá đi cùng commit này:
`test_measure_29ed_overlap` (10 test), `test_measure_29f_render` (4), `test_plume_density_table` (2).
167 − 16 = **151**, và đây là con số chuẩn của nhánh `sspp` từ bước 3 trở đi.

Nếu sau này cần lại clip BEV của spray thật (clip 76 frame đó vẫn có giá trị), viết lại ~20 dòng
chỉ dùng `spray_stats.load_scan` + `NOISE_LABEL`, không cần 200 dòng của `visualize_plume`.

---

### Bước 4 — Bỏ tài liệu của hướng cũ

**Xoá:**

```
docs/PROJECT.md                    ← viết lại cho hướng mới ở bước 6
docs/README.md                     ← xoá hẳn; bản đồ tài liệu chuyển vào mục 9 của PROJECT.md mới
docs/adr/0002-plume-only-first.md
docs/adr/0003-semantic-spray-eval-only.md   ← ADR này nói "KHÔNG train trên SemanticSpray"
docs/adr/0004-v2-wet-ground-attenuation-state.md
docs/agents/                       ← quy ước agent của board cũ
docs/audit/
docs/board/
docs/figs/                         ← 19 file ảnh/clip của plume cũ
docs/history/                      ← 6 file: v1 defects, walkthrough, provenance
docs/measurements/29ec-range-buckets.md
docs/measurements/29ed-real-distributions.md
docs/measurements/29ed2-overlap.md
docs/measurements/29ed3-gen-overlap.md
docs/measurements/29f-cluster-visibility.md
docs/measurements/plume-geometry-measurements.md
docs/measurements/plume-geometry-vs-real.md
docs/measurements/plume-v2-measurements.md
docs/reference/nuscenes-eligibility.md
docs/reference/velocity-contract.md
```

**Giữ 5 file — đây là tài sản của hướng mới:**

| File | Vì sao giữ |
|---|---|
| `docs/adr/0001-mit-bevfusion-pin.md` | pin `da93b27` vẫn đúng cho hướng mới (lý do: HEAD `326653d` có `add_depth_features`/`height_expand` làm sai shape). Chỉ có chữ "checkpoint fused" là lỗi thời — sửa 1 dòng ở bước 6 |
| `docs/measurements/semantic-spray-stats.md` | thống kê spray thật, nguồn của mọi tham số |
| `docs/measurements/semantic-spray-cal-vs-heldout.md` | cổng 7 tiêu chí của split |
| `docs/measurements/semantic-spray-clusters-by-speed.md` | cụm/frame theo tốc độ |
| `docs/reference/paper-qa-notebooklm.md` | hỏi đáp nguyên văn với paper — **quan trọng nhất**, đừng xoá |

**`docs/adr/0003` là chỗ dễ sai nhất.** ADR đó đang ghi "SemanticSpray chỉ dùng để hiệu chỉnh,
không train/eval" — đúng với hướng cũ, **ngược** với hướng mới. Không được xoá rồi để trống:
hướng mới cần một ADR mới nói rõ "train/eval trên SSPP, chấp nhận 1 box/frame và không có
frame sạch". Ghi ADR đó ở bước 6.

---

### Bước 5 — Bỏ `.scratch/` của board cũ

**Xoá:** `.scratch/spray-augmentation/` (121 file: 48 ticket, dispatch, STATUS, spec v2).

**Giữ:** `.scratch/hermes-tools/` (9 file: script parse log, fetch ckpt — công cụ, không phải hướng).

**Vì sao xoá board cũ:** 48 ticket đó là lịch sử của generator v2 và cổng nghiệm thu 29d–29h.
Hướng mới có board riêng. Để lại board cũ trên nhánh `sspp` thì `STATUS.md` sẽ nói dự án đang
làm ticket 29h — sai hoàn toàn.

**Lấy lại khi cần:** `git checkout main -- .scratch/spray-augmentation/`.

---

### Bước 6 — Viết lại 5 file gốc + sửa 1 dòng ADR

Đây là commit duy nhất có nội dung mới. Năm file viết lại + một dòng trong `docs/adr/0001`:

**`README.md`** — 25 dòng, trả lời 4 câu: bài toán là gì, đo cái gì, dữ liệu nào, trạng thái.
Điểm khác biệt so với `main`: detection chạy trên **SSPP**, không phải nuScenes.

**`docs/PROJECT.md`** — câu hỏi, phạm vi, sổ quyết định. Phải ghi rõ ba số đo ở §6 dưới,
vì chúng quyết định kết luận nào được phép viết.

**`docs/adr/0005-sspp-as-detection-domain.md`** — thay `0003`. Nội dung: chuyển domain
detection từ nuScenes sang SSPP; chấp nhận 1 box/frame, 2 class, không có frame sạch,
không có calib camera; đổi lại có spray thật và box thật. Ghi rõ điều gì khiến ADR này
mở lại (SSPP++ release bản có 6 camera + calib, hoặc có dataset spray thật khác có frame sạch).

**Sửa 1 dòng trong `docs/adr/0001`:** câu "Checkpoint fused load được mà không phải sửa code
hay shape" → "Checkpoint LiDAR-only load được…". Lý do pin (`da93b27`) không đổi, chỉ đổi
checkpoint được nhắc tới.

**`HANDOFF.md`** — thay bằng bản 40 dòng: nhánh `sspp`, plan hướng mới, việc kế tiếp là bước 2
của plan SSPP (adapter).

**`GLOSSARY.md`** — rà 45 dòng, bỏ mục chỉ thuộc nuScenes, thêm Car/Van, cal/held-out.

**`docs/README.md` không viết lại — xoá hẳn.** Bản đồ tài liệu chỉ còn 5 file thì một bảng
trong mục 9 của `PROJECT.md` mới là đủ; giữ file riêng chỉ tạo thêm một chỗ phải cập nhật.

---

## 6. Ba số đo mới phải ghi vào `docs/PROJECT.md`

Đo hôm nay trên `data/SemanticSprayDataset`, không lấy từ tài liệu cũ:

**a) Split theo tốc độ — plan cũ ghi đúng, xác nhận lại:**

| Split | Tốc độ | Scene | Frame | Box | Spray p50/frame |
|---|---|---|---|---|---|
| train | 60, 80, 100, 120 | 16 | 1.124 | 1.124 | 378 |
| val | 70, 110 | 8 | 509 | 509 | 499 |
| test | 50, 90, 130 | 12 | 954 | 962 | 142 |

36 scene có box / 207 scene; 2.587 frame; 2.595 box. Lớp: Car 1.362, Van 1.225,
Other Vehicle 8 (bỏ).

**b) `z` đáy box = −0,411 m — xác nhận bằng số, không bằng tài liệu:**
box đầu tiên của `Crafter_dynamic/0000`: `center3D.z = 0,899`, `size3D.z = 2,6206`
→ `0,899 − 2,6206/2 = −0,4113`. Trung bình toàn bộ 2.595 box: **−0,362 (train) / −0,375 (val)
/ −0,376 (test)**. Chênh 0,04 m giữa hai cách tính là do box khác cao độ; dùng công thức
`center3D.z − size3D.z/2` cho từng box, không dùng hằng số.

**c) `poses.txt` không có tịnh tiến — đã kiểm lại:** 3 cột đầu là ma trận xoay, cột 4 toàn `0.0`.
Nghĩa là **không lấy được ego displacement** từ pose. Tốc độ ego phải đọc từ
`metadata.txt` cột `ego_velocity`. Đây là lý do `PlumeContext.from_sample` có tham số
`ego_speed_mps` tường minh.

---

## 7. Bốn chốt chặn trước khi coi là xong

| Kiểm | Lệnh | Giá trị đúng |
|---|---|---|
| Test xanh | `pytest -q tests/` | `151 passed` |
| Không còn import chết | `grep -rn "mini_split\|ab_config\|model_routing\|spray_context_transform\|spray\.freeze\|spray\.denoise" --include=*.py spray/ proxy_eval/ scripts/` | rỗng |
| `main` không đổi | `git diff main --name-status -- . ':!.hermes'` | chỉ có dòng `D`, và đúng 6 dòng `M`/`A` của bước 6 (5 file viết lại + `docs/adr/0001`) |
| Nhánh đúng gốc | `git merge-base --is-ancestor f3fb7d2 sspp && echo OK` | `OK` |

**Kiểm thứ ba là quan trọng nhất.** Nếu `git diff main` hiện một file bị **sửa** mà không nằm
trong danh sách bước 6, nghĩa là đã có ai đó sửa nội dung thay vì xoá — vi phạm nguyên tắc 5.

---

## 8. Sau khi xong

```bash
git push -u origin sspp
```

Hai nhánh sống độc lập:

| | `main` | `sspp` |
|---|---|---|
| Domain detection | nuScenes | SemanticSpray++ |
| Dữ liệu có spray thật | không | có |
| Frame sạch để đối chứng | có | **không** |
| Camera branch | có (6 view) | **không** (thiếu calib) |
| Box / frame | ~34 (1,17 M annotation / 34.149 keyframe) | 1 |
| Trạng thái | đóng, giữ làm đối chứng | phát triển |

**Điều plan này không giải quyết:** hướng mới mất khả năng đo "sạch vs có spray" trên cùng
frame, vì SSPP không có frame sạch. Đó là hạn chế của dữ liệu, không phải của việc dọn nhánh.
Cách duy nhất lấy lại phép so sánh đó là tự tạo frame sạch bằng cách xoá điểm `label == 2` —
và đó chính là việc plan SSPP đang làm (Arm A nền `points[labels != 2]`).

---

## 9. Rủi ro

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Xoá nhầm file hướng mới cần | `pytest` đỏ ở bước 1–3 | `git reset --hard HEAD~1`, thêm file vào danh sách giữ |
| 10 module giữ lại vô tình import module bị xoá | `pytest` đỏ ở bước 1 | Đã kiểm: cả 10 module giữ lại **không** import module nào trong 8 module bị xoá. Nếu đỏ thì là lỗi mới, không phải do bước 1 |
| Mất số đo cũ cần dẫn lại | cần trích `29f-cluster-visibility.md` | `git show main:docs/measurements/29f-cluster-visibility.md` |
| `main` bị sửa nhầm | `git diff main --stat` có file sửa lạ | chưa push thì `git reset`, đã push thì `git revert` |

**Thời gian ước tính:** 6 commit, mỗi commit 3–8 phút, tổng **40–60 phút**, không cần GPU.
