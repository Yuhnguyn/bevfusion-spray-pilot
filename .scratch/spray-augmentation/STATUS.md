# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-09 22:45 (dừng shift) · **PM:** Hermes (chốt phạm vi, tiêu chí, nghiệm thu) · **Thi công:** CommandCode
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

## Dừng shift 2026-11-09 22:45 — bắt đầu lại từ đây

**Đang ở:** thực nghiệm ticket 11 **đã chạy xong**, kết quả **null** và đã chẩn đoán được cơ chế.
Việc còn lại: **ticket 13 (gate review)** và quyết định có tăng liều plume / đổi thước đo hay không.

**Kết quả A/B cuối (kernel v13, COMPLETE 22:06, 196 frame / 16 scene):**

| Ô | mAP | recall |
|---|---|---|
| A clean | 0,5458 | 0,5896 |
| A spray | 0,5449 | 0,5871 |
| B clean | 0,5459 | 0,5903 |
| B spray | 0,5419 | 0,5857 |

`EVAL_OK delta_A=-0.0009 delta_B=-0.0040 interaction=-0.0031 ci95=[-0.0140, 0.0017]`
— CI chứa 0 ⇒ **không kết luận được tác dụng của augmentation**.

**Chẩn đoán cơ chế (11-i, đo trên output v13):** plume thêm ~0,4 % số điểm; hộp dự đoán dịch trung vị
**3 mm**; **số hộp dự đoán không đổi** (22,00/frame ở ngưỡng 0,05); 1,9 % hộp nằm sát IoU 0,5 nên chỉ
cần dịch milimét là lật TP→FP. Toàn bộ delta −0,0031 ≈ **6 hộp lật ròng trên 3.609 GT**. Precision giảm
(0,3092 → 0,3023) mạnh hơn recall ⇒ đúng cơ chế false positive, nhưng dưới độ phân giải của thước đo.
Kết luận: **null không phải do eval hỏng**; muốn thấy tín hiệu phải tăng liều plume hoặc đổi thước đo.

**Chuỗi lỗi đã sửa trong shift này:** v11 ERROR do regex đọc `splits.py` (sửa `84ce10b`, parse bằng AST);
v12 ERROR do `gt_labels_3d` là list tensor CUDA (sửa `4ac0a57`); v13 chạy sạch.

**Test local:** 192 passed, 4 skipped (`CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/`).

**Việc đầu tiên của shift sau:** đọc `HANDOFF.md` mục "Việc tiếp theo" — có 3 hướng kèm chi phí GPU.

## Audit generator v1 — 2026-11-10 (trước khi planning v2)

Sau khi đọc **code tham chiếu đã publish** (`openMSL/.../DetectionEnvironmentalEffects.cpp`) và đo trực tiếp
`spray.plume.inject_plume`, tìm được **5 lỗi cấu trúc** giải thích vì sao can thiệp A/B quá yếu:

| # | Lỗi | Số đo | Mức |
|---|---|---|---|
| D1 | `z` sai frame: cụm ở **2,0–3,8 m trên mặt đường** (trên nóc xe 1,7 m) | `height_range_m [0,2;2,0]` gán tuyệt đối; mặt đường ≈ −1,84 m | **P0** |
| D2 | neo từ **tâm box** thay vì mặt đuôi, không có bề dài `v·Δt` | trung vị **4,01 m** sau đuôi (p90 6,93); tham chiếu 1,39–2,78 m; mật độ 3,6 vs 14,0 điểm/m³ | **P0** |
| D3 | tự triệt tiêu: điểm sinh trong box bị `rejected_box` xoá | **13,9 %** xe con · **45,7 %** truck · **63,1 %** trailer | **P1** |
| D4 | stateless mỗi frame ⇒ không có vệt | trung vị sau đuôi dao động **1,57 → 7,33 m** giữa các frame | **P1** |
| D5 | thiếu visibility / occlusion / attenuation / thay return yếu | 0/5 cơ chế của code tham chiếu | **P1** |

**Chi tiết + bảng tham số v2 + tiêu chí nghiệm thu:** `docs/plume-v1-defects.md`.
**Bằng chứng trực quan:** `docs/figs/plume/v1-audit/compare.mp4` (10 s) và `compare_still.png`.
**Issue GitHub:** [#1](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/1) z · [#2](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/2) neo · [#3](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/3) rejected_box · [#4](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/4) stateless · [#5](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/5) tương tác phép đo · [#6](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/6) umbrella Ticket 25.
**Kết luận:** null của ticket 11 là **hệ quả của thiết kế can thiệp**, không phải của augmentation; sửa
generator trước, train lại sau. Ba việc phải làm trước khi sửa code (0 GPU) ở §5 của tài liệu audit.

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
| 11 | Mini A/B run + report | **done** `88770b5` | Train v9 (2×2.000 bước) → eval v13: `interaction=-0,0031`, CI95 [−0,0140; 0,0017] ⇒ **null**. Chẩn đoán 11-i: dịch tâm 3 mm, 6 hộp lật/3.609 GT. Sửa lỗi: `84ce10b` (parse splits), `4ac0a57` (CUDA tensor). 192 passed |
| 12 | SemanticSpray statistics | **done** | `docs/semantic-spray-stats.md` |
| 13 | Gate review sau mini A/B | **next** | Dùng kết quả null + chẩn đoán 11-i; quyết định hướng đi trước khi làm tiếp |
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
| 25 | **Plume simulator v2** (4 tầng: hình học → khả kiến → tương tác → thời gian) | **planning** | `docs/plume-v1-defects.md` §4–5; chờ audit CPU + xác nhận D1 |

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