# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-09 00:25 (dừng shift) · **PM:** Hermes (chốt phạm vi, tiêu chí, nghiệm thu) · **Thi công:** CommandCode
**Đọc file này trước khi mở bất kỳ ticket nào.** Ticket là chi tiết; file này là thứ tự và phạm vi.

## Mục tiêu một câu

Chứng minh bằng thí nghiệm paired A/B rằng augment spray plume vào nhánh LiDAR của BEVFusion làm giảm
khoảng cách giữa mAP trên frame sạch và frame có spray — đo trên nuScenes, không train trên SemanticSpray.

## Trạng thái hiện tại

**Generator đã khớp code tham chiếu Linnhoff** (ticket 21–22): kích hoạt `v > 40 km/h` + `wfh > 0`,
số cụm `(0,2·wfh + 0,1)·(v−50) × K` với `K = 2,51`, `T ≈ 0,20 s`, σ = 1,1, trần bán kính sắp sửa 1,0 m
(ticket 23). Ở 80 km/h sinh **8 cụm/frame** (trước ticket 22: 0,73; đo thật SemanticSpray: 17,06).

**Môi trường Kaggle đã giải xong 2/3 lớp** (ticket 02b + 19): venv Python 3.8.20 + torch 1.10.1+cu113 +
`mmcv-full 1.4.0` + compile 12 CUDA extension; code repo lên bằng dataset private 2 MB. Kernel
`bevfusion-e2e` chạy **COMPLETE 516 s / 49 passed** (log tải trực tiếp từ Kaggle). Lớp còn lại: quota GPU T4.

## Dừng shift 2026-11-09 00:25 — bắt đầu lại từ đây

**Đang ở:** smoke của ticket 11-b **đã PASS** (kernel v6 `COMPLETE`, `SMOKE_OK`, 2026-11-09 11:4x).
Số đo [ĐO]: `s_per_step = 1,4546 s` (batch 2, T4), `peak_gb = 4,251 / 16`,
mini split `n=4000 scenes=698 gt_boxes=137737 val_scenes=150`, `MINI_SPLIT_NOSWEEPS n=4000`
(dataset keyframes-only — xem ticket 20). Kernel chạy 2086 s, trong đó ~10–11 phút là boot venv + build CUDA ext.

**Việc tiếp theo — 11-c (train A/B thật):** chưa có entrypoint train; `kaggle/train/` mới có `main.py` (orchestrator),
`smoke.py`, `probe.py`. Cần script train 2 arm × 2.000 bước + lưu checkpoint + eval trên eval set 196 frame.
Ngân sách thời gian từ số đo trên: 4.000 bước × 1,4546 s ≈ **1 h 37 m** compute, cộng boot ~11 phút.
`peak_gb` chỉ 4,25/16 nên batch 4 khả thi (≈50 phút) nhưng phải chỉnh lr theo batch — chỉ đổi nếu user đồng ý.

**Việc đầu tiên của shift sau:**
```bash
kaggle kernels status nguynhuy9669/bevfusion-spray-train
kaggle kernels output nguynhuy9669/bevfusion-spray-train -p /tmp/ksmoke
grep -E "SMOKE_DEVKIT_OK|MINI_SPLIT_OK|SMOKE_STEP|SMOKE_OK|SMOKE_FAILED|MINI_SPLIT_FAILED" /tmp/ksmoke/bevfusion-spray-train.log
```
Cần đọc được 2 số: **`s_per_step`** và **`peak_gb`**. Nếu kernel fail: đọc 30 dòng cuối, sửa, push lại
(không hủy lượt chờ của kernel đang có).

**Ngân sách đã chốt:** 2000 bước × batch 2 × 2 arm, lr 1e-4, AdamW, freeze chỉ camera. VRAM đã loại khỏi
rủi ro (param state 0,254 GB / 16 GB). Cách xử lý nếu thiếu VRAM, theo thứ tự: gradient accumulation →
batch 1 + tăng bước → DDP.

**Test:** `105 passed, 4 skipped` local (`CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/`);
trong kernel Kaggle: **68 passed, 0 skipped**. 12 file test.

**Việc tiếp theo:** `11-b` (chờ smoke kernel) → `11-c` (train A/B thật) → `13` (gate review). Ticket `10` đã xong.

## Bảng ticket

| # | Việc | Trạng thái | Bằng chứng / next |
|---|---|---|---|
| 01 | Working copy MIT + pin `da93b27` | **done** | `mit/PIN.md` |
| 02 | Smoke test checkpoint + 1 sample | **done** | 582/582, forward 0,6 s, mọi stage finite |
| 02b | Sửa môi trường Kaggle, chạy lại smoke test | **done** | v15 ALL_PASS |
| 03 | Velocity frame + ObjectPaste | **done** | `docs/velocity-contract.md` |
| 04 | Dataset gate trên Kaggle | **done** | infos 120/120, load 1 sample |
| 05 | Evaluator core + synthetic tests | **done** | `proxy_eval/matcher.py`, 8 test |
| 06 | Adapter evaluator cho output MIT | **done** | mAP 0,298 (P 0,512 / R 0,524) |
| 07 | Pipeline transform + `points_clean` | **done** | 12/12 check; scene-0796 +127 điểm |
| 08 | Model forward routing | **done** `16517f1` | subclass `spray/`; param 16 → 16 |
| 09 | End-to-end pipeline test | **done** `c66e867` | kernel `68 passed, 0 skipped`, `E2E_OK`; 2 stream + matrix roundtrip |
| 10 | Train/eval config A/B | **done** `fcaa4f9` + `2ed78b3` | probe `PROBE_OK`: ckpt 0 missing, trainable 9,08M/40,80M, chỉ camera frozen, 0,25 GB param state |
| 11 | Mini A/B run + report | **in-progress** | 11-b smoke PASS v6 `d76eb46`; sweeps probe PASS v8 `c364174` (`SWEEPS_OK ratio=0,9879`, +53 % s/step); chốt `sweeps_num: 0`. 11-c1 `322e26a`, 11-c2 `9e3b4dd`, 11-c3a `a60b78b`, 11-c3b `1c24d9a` (176 passed). Kernel **v9 đang train** (`scriptVersionId=367214655`); v10 push nhầm đã huỷ |
| 12 | SemanticSpray statistics | **done** | `docs/semantic-spray-stats.md` |
| 13 | Gate review sau mini A/B | blocked | chờ 11 |
| 14a | B0: module lọc | **done** `ed92cf8` | `spray/denoise.py` · `ror_filter` · 60 passed |
| 14b | B0: DROR thích nghi theo cự ly | **done** `60092a1` | `dror_filter(alpha=0,03)` giữ 100% điểm ở 10/20/40/50 m; 23 ms/2.272 điểm |
| 15 | Provenance của `PlumeConfig` | **done** `bc0da86`+`d1bf9bf` | `docs/plume-model-provenance.md` |
| 16 | Đo hình học plume thật theo cự ly | **done** `08f6715` | 17,06 cụm/frame; 30/20/14/10/10 điểm/cụm |
| 17 | Sửa generator theo số đo của 16 | **done** `5d7c478` | count theo cự ly; bẹp `S = 0,885` |
| 18 | Quét lại eligibility nuScenes | **done** | eval set: 196 frame / 16 scene |
| 19 | Kaggle code sync (dataset + kernel) | **done** `feb0a9e` | dataset private v3; kernel COMPLETE 516 s |
| 20 | Visualize plume (ảnh + clip) | **done** `6143875` | 3 ảnh + 2 clip + `docs/figs/plume/index.html` |
| 21 | Port cơ chế từ code thật | **done** `a4fdf24` | 40 km/h, offset 50 km/h, `T`, σ 1,1 |
| 22 | Sửa lỗi tính hai lần + docs | **done** `75d210c` | `K = 2,51`; 8 cụm @80 km/h; 56 test |
| 23 | Trần bán kính 1,0 m + tên cột 5 + docs `K`/`T` | **done** `da996ff` | chạm trần đo thật 6,51%; 57 test |
| 24 | `build_kanban.py` sinh board từ nguồn thật | **done** `8da032a` | bỏ hard-code; 25 ticket, 18 done, nguồn STATUS.md |

## Thứ tự hiện tại

Nguyên tắc: **việc quyết định thiết kế làm trước, việc cơ học làm sau.**

| Bước | Ticket | Trạng thái |
|---|---|---|
| 1 | **23** dọn 3 chỉnh nhỏ | ✅ `da996ff` — trần 1,0 m, cột 5 = `ring`, docs `K`/`T` + self-spray |
| 2 | **09** e2e trên Kaggle | ✅ `c66e867` — `68 passed`, 0 skipped, 5 lần push |
| 3 | **10 → 11 → 13** | config A/B → mini run → gate review |
| // | **14** (B0) | chạy song song được |

## Critical path

`07` → `08` → `09` ✅ → `10` → `11` → `13`

`14` (B0) chạy song song được với `10–11`; chỉ cần evaluator + model.
`16 → 17` **đã xong** — độc lập với pipeline, chỉ chạm `scripts/`, `spray/`, `tests/`, `docs/`.

## Quyết định đã chốt — không mở lại

- Pin MIT BEVFusion `da93b27`; không dùng HEAD. (`docs/adr/0001-mit-bevfusion-pin.md`)
- v1 chỉ plume, không mô phỏng wet-ground/attenuation. (`docs/adr/0002-plume-only-first.md`)
- Lý do **định lượng** để bỏ attenuation ở v1: hệ số tắt hiệu dụng **0,04 m⁻¹** = `exp(−2×0,02×d)`
  [PAPER §III] × quãng xuyên thực tế 0,5–0,8 m (1–2 cụm r = 0,3 m) → intensity còn **98,0–96,9%** → dưới
  ngưỡng lượng tử hoá intensity của nuScenes. Chỉ đáng làm nếu chuyển sang regime fully-watered của paper
  (500–1.500 điểm/frame).
- ~~v1 đặt điểm plume trên **vỏ cầu phía cảm biến**~~ — **SAI, đã bác bỏ ở ticket 16–17.** Đo thật:
  `r_range/r_extent` median **1,266** (n=690, p25 1,07 / p75 1,41) ⇒ cụm có bề dày theo tia, không phải vỏ
  mỏng. v1 rải điểm **trong khối cầu** rồi bẹp theo phương tia `S = 0,885` để tái lập
  `r_range/r_extent ≈ 1,28`. **Mật độ phụ thuộc cự ly** — bảng `30/20/14/10/10` điểm/cụm ở
  0–5/5–10/10–20/20–30/30–50 m [ĐO ticket 16]; giả thuyết "mật độ không phụ thuộc cự ly" đã bị bác bỏ.
  Không dựng beam grid/OSI.
- Không train/eval detection trên SemanticSpray; chỉ dùng để calibrate + point-wise sanity check.
  (`docs/adr/0003-semantic-spray-eval-only.md`)
- Velocity của box đã ở LiDAR frame của keyframe hiện tại; plume phải chèn **sau** `GlobalRotScaleTrans`
  và `RandomFlip3D`, **trước** `PointShuffle`; box do `ObjectPaste` set velocity = 0.
  (`docs/velocity-contract.md`)
- Ba arm: A = clean baseline, B = có plume, B0 = lọc spray rồi detect.
- **Eval set (chốt 2026-11-07, ticket 18):** val split, box vehicle ≥50 km/h **phía trước** (`x>0`),
  `d ≤ 50 m`, **không lọc vận tốc ego** → **196 frame / 16 scene**; báo per-range 0–30 m (117 frame) và
  30–50 m (79 frame). Nguồn: `docs/nuscenes-eligibility.md`.
  - **Bỏ lọc ego** vì paper §III-A có kịch bản ego **đứng yên** (xe khác chạy ngang vẫn sinh plume);
    lọc ego ≥50 km/h làm val còn **0 frame**.
  - **Không dùng scene highway**: 0 scene highway trong val, chỉ 2 scene trên toàn bộ nuScenes.
  - **Không tự chia lại trainval** để lấy thêm frame: checkpoint pretrained đã thấy 700 scene train → eval
    trên đó là rò rỉ, kể cả khi không train thêm.
  - Rủi ro đã biết: 16 scene → CI rộng; nếu G3#1 fail thì kết luận là "không đo được gap với n=16 scene",
    **không** phải "augment vô dụng".
- **Số cũ 34.029 frame / 697 frame / 2,0% là toàn bộ trainval** (850 scene / 34.149 keyframe), không phải
  val split (150 / 6.019). Hàng đối chứng tái lập đúng (957 box / 698 frame, +0,53%) nên phép đo cũ đúng,
  chỉ nhãn sai. Đã đính chính `docs/velocity-contract.md`.
- Kết quả dương trên plume tổng hợp là **cận trên lạc quan**, không chứng minh giúp spray thật. Camera
  branch nhận `points_clean` nên lợi ích nếu có chỉ đến từ LiDAR.
- **`water_film_height` tính bằng MÉT.** `T = wfh·0,02·(v−50) + 0,2` với `wfh = 0,001 m` ⇒ số hạng tốc
  độ chỉ `0,0004 s` ⇒ `T ≈ 0,20 s` và `K ≈ 2,51` ở mọi tốc độ. Nếu đọc `wfh = 1 mm` thành số `1,0` thì
  `T(130 km/h) = 0,84 s`, `K ≈ 9` — **sai 3,6×**.

## Non-goals (không làm trong dự án này)

- Không port model C++ ray-based của Linnhoff (occlusion, drag, beam/ray-sphere); không dựng OSI/beam angles.
- Code tham chiếu của Linnhoff 2022 **đã publish** trên GitHub
  `openMSL/sl-1-2-reflection-based-lidar-object-model` (MPL-2.0), file
  `src/model/strategies/lidar-environmental-effects-strategy/src/DetectionEnvironmentalEffects.cpp` (833 dòng).
  v1 port 3 cơ chế: kích hoạt 40 km/h, số cụm theo offset 50 km/h (nhân hệ số trạng thái dừng `K`),
  lifetime `T = wfh·0,02·(v−50) + 0,2`. Phần **không** port: occlusion, drag, ray-sphere/beam.
  Occlusion trong model thật chỉ **thay thế các return yếu** (`power = intensity/d²`; xe nuScenes intensity
  4–40 thắng 8–80× so với spray ở 25 m) nên ảnh hưởng lên điểm của xe **<3%**; v1 chỉ **thêm** điểm.
  Xếp lại nguồn lạc quan: **(1) camera branch sạch, (2) số cụm, (3) lifetime, (4) drag, (5) occlusion.**
- Không mô phỏng wet pavement: cloud nuScenes là **đo thật**; code tham chiếu chỉ **gán lại intensity**
  điểm mặt đường trong dải ngang 2–7 m (`dee.cpp:345–377`), không xoá điểm.
- Không mô phỏng **self-spray** (bụi nước sau chính ego) — có thấy trong clip A ở x ≈ −4,5 m nhưng nằm
  ngoài eval set A (`x > 0`).
- Không tune hyperparameter, không multi-seed ở v1 (1 seed T4, kết quả chỉ mang tính hướng).
- Không hứa hẹn cải thiện trên spray thật.

## PM nghiệm thu một ticket thế nào

1. Có số thật, không có ô `null`, không có "ước tính" ghi như số đo.
2. Mọi con số mới truy được nguồn: `[ĐO] / [PAPER] / [CODE] / [CHỌN]`.
3. Test liên quan pass, `git status` sạch, commit message nêu rõ đã làm gì.
4. Không mở rộng phạm vi: việc ngoài ticket thì ghi thành ticket mới, không làm kèm.
5. Nếu bị chặn: dừng, báo PM kèm log + giả thuyết, không tự đổi pin hay version đã chốt.