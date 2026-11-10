# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-10 11:52 · **PM:** Hermes · **Thi công:** CommandCode

> **Quyết định 2026-11-10 (user chốt):** hướng **(c)** — khối nước **sinh từ `metadata.txt` +
> `poses.txt`**, **nghiệm thu bằng nhãn spray thật** (`label == 2`, 24–44 điểm/frame).
> `boxes` thành tham số optional (`None` ⇒ dùng metadata). Chi tiết: `spec-v2-paper-faithful.md` §2.
> Việc kế tiếp sau restart: **ticket 25** (đo 0 GPU, không cần train).
**Đọc file này trước khi mở bất kỳ ticket nào.** Ticket là chi tiết; file này là thứ tự và phạm vi.

## Mục tiêu một câu

Chứng minh bằng thí nghiệm paired A/B rằng augment spray plume vào nhánh LiDAR của BEVFusion làm giảm
khoảng cách giữa mAP trên frame sạch và frame có spray — đo trên nuScenes, không train trên SemanticSpray.

## Trạng thái hiện tại

**v1 đã đóng, không sửa nữa** — v2 dựng lại theo `spec-v2-paper-faithful.md` (ticket 25–31).

**Đính chính 2026-11-10 (đọc lại code openMSL):** dòng cũ ở đây ghi
`số cụm = (0,2·wfh + 0,1)·(v−50) × K` với `K = 2,51` là **sai**. `grep -rn "2\.51"` trên toàn repo
openMSL → **0 hit**. Số cụm là `round(max(0, mean))`, **tất định**, không nhân hệ số
(`dee.cpp:509–512`). `K ≈ 2,5` trong paper là **số detection trung bình mỗi cụm**, tức đầu ra của
ray casting, không phải tham số sinh. Đơn vị `wfh` cũng phải là **mm** mới khớp Fig. 11b
(24 cụm @130 km/h); config v1 đang để `0.001` m ⇒ chỉ ra 8 cụm @130.

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
| D2 | neo từ **tâm box** thay vì mặt đuôi, không có bề dài `v·Δt` | p50 **3,32 m**, p90 **7,02 m** sau đuôi @80 km/h; tham chiếu 1,39–2,78 m; **loãng 4,7× @80 (16,9× @60, 2,3× @100)** | **P0** |
| D3 | điểm sinh rơi vào thân xe; `rejected_box` hiện **gần như không xoá** (≤2 %) vì D1 đẩy cụm lên trên nóc **và** D6 làm hộp khử mỏng theo trục vệt | hôm nay **0,0–2 %**; sửa D6 một mình → **30,2 / 63,6 %**; sửa cả D1+D6 → **≈14 / 45 / 63 %** | **P1 (tiềm ẩn, sửa cùng D1 + D6)** |
| D6 | `_inside_box` dùng `width` làm nửa trục **dọc theo yaw** ⇒ hộp khử xoay 90° so với dữ liệu production (`dims = wlh`) | test của repo theo quy ước ngược nên không bắt được; sửa quy ước → mất 30–64 % liều | **P0 (khi sửa D1)** |
| D4 | stateless mỗi frame ⇒ không có vệt | trung vị sau đuôi dao động **1,16 → 5,84 m** (std 1,33 m) giữa các frame | **P1** |
| D5 | thiếu visibility / occlusion / attenuation / thay return yếu | 0/5 cơ chế; xe ngược chiều **100 %** điểm plume nằm sau thân xe | **P1** |
| D7 | trần `max_injected_points = 2000` là global, cắt ngẫu nhiên | 16 xe @80 km/h → 2.340 điểm/frame, **cắt 14,2 %**; regime heavy ~4.000 **bất khả thi** | **P1** |
| D8 | can thiệp **đông cứng** qua epoch; `intensity = 0` toàn bộ điểm plume | seed luôn 0, RNG chỉ theo token ⇒ hình học plume giống hệt mọi epoch | **P1** |

**Kiểm chứng độc lập (2026-11-10):** PM đo lại cả 5 lỗi trên generator thật (20–60 seed) và tải `dee.cpp` bản gốc
đối chiếu: **D1/D4/D5 đúng**, **D2 sai p50 (4,01 → 3,32 m)**, **D3 sai bản chất** (`rejected_box` thật 0,03–2,1 %,
không phải 13,9–63,1 % — đã sửa trong bảng trên). Thêm **D7** (trần 2000 điểm global) và **D8** (seed đông cứng
qua epoch + `intensity = 0`); **D6** (thứ tự `w`/`l` của box production) còn là câu hỏi mở. Chi tiết: `docs/plume-v1-defects.md` §7.

**Chi tiết + bảng tham số v2 + tiêu chí nghiệm thu:** `docs/plume-v1-defects.md`.
**Bằng chứng trực quan:** `docs/figs/plume/v1-audit/compare.mp4` (10 s) và `compare_still.png`.
**Issue GitHub:** [#1](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/1) z · [#2](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/2) neo · [#3](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/3) rejected_box · [#4](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/4) stateless · [#5](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/5) tương tác phép đo · [#6](https://github.com/Yuhnguyn/bevfusion-spray-pilot/issues/6) umbrella Ticket 25.
**Kết luận:** null của ticket 11 là **hệ quả của thiết kế can thiệp**, không phải của augmentation; sửa
generator trước, train lại sau. Ba việc phải làm trước khi sửa code (0 GPU) ở §5 của tài liệu audit.

## Đo 0 GPU xong (ticket 25) — 5 phát hiện đổi thiết kế v2

Chi tiết + bảng số: `docs/plume-v2-measurements.md` (5 section, sinh bởi 4 script, idempotent).
Nghiệm thu: `issues/25-measure-zero-gpu.md` §PM nghiệm thu.

| # | Phát hiện `[ĐO]` | Hệ quả cho ticket 26–31 |
|---|---|---|
| 1 | `poses.txt` **toàn bộ 207 scene** có cột tịnh tiến = `0,000000 m`, chỉ rotation (orthogonality `2,2e-16`) | Tốc độ ego **chỉ** lấy từ `metadata.txt`; `poses.txt` dùng cho yaw, không dùng cho dịch chuyển. Tiêu chí <10 % của ticket 25 **KHÔNG ĐẠT** vì dữ liệu thiếu, không phải code sai |
| 2 | `object_velocity == ego_velocity` ở **207/207** scene; `distance_to_object` chỉ **20,0 / 30,0 m**; `itr_after_water` ∈ 1…6 | Dataset là **ma trận thí nghiệm có kiểm soát**, không phải lái tự nhiên. Vệt spray gần như đứng yên trong frame ego (vận tốc tương đối ≤ 6,26 km/h) |
| 3 | Box 3D thật chỉ có ở **36/207 scene** (`object_labels/lidar/`, 1 instance/frame, `Van`) | Hướng (c) **bắt buộc** cho 171 scene còn lại. `size3D = (6,83 dài, 2,42 rộng, 2,62 cao) m` ⇒ `x` là **chiều dài**, xác nhận lỗi **D6** |
| 4 | Cột 4 = ring id `0…31`, nhưng lệch bảng VLP-32C median `|Δ| = 3,49°`, `27/32` ring `≥ 0,5°` | Ray casting **phải** tính `atan2(z, √(x²+y²))` từ toạ độ; **không** dùng ring làm góc. Cảm biến là **VLP-32C**, không phải HDL-32E |
| 5 | `z` mặt đường SemanticSpray = **`−0,411 m`** (p1), khớp đáy box thật `−0,4113 m` trong `0,0003 m` | Số này **khác** `−1,84 m` của nuScenes: ticket 28 phải đọc mặt đường **theo từng dataset** |

**Trần dữ liệu:** `0 %` frame dưới 50 km/h, nhưng **16,33 % (2.844 frame) đúng 50 km/h** ⇒ `mean = 0` cụm,
tức 0 điểm spray dù vượt ngưỡng kích hoạt 40 km/h. Báo riêng hoặc loại khỏi mẫu dose–response.

**Đã chốt `[CHỌN 2026-11-10 — user]`:** `wfh` dùng **mm cho cả hai công thức** (`count` và `T`), không trộn
đơn vị. Hệ quả chấp nhận: `T = 1,80 s @130 km/h` ⇒ vệt `65 m`, xoá khi `age > 4T = 7,2 s`;
`T = 0,80 s @80 km/h` ⇒ vệt `17,8 m`. Ticket 28 dùng một hằng `wfh_unit: mm`.

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
| 25 | Đo 0 GPU: tốc độ ego/xe dẫn, beam angles, quỹ đạo, hằng số | **done** | 4 script + `docs/plume-v2-measurements.md` (5 section, idempotent sha `3085a237`); 192 passed, 4 skipped. Nghiệm thu: `issues/25-measure-zero-gpu.md` §PM |
| 26 | Hợp đồng dữ liệu `PlumeContext` + state theo scene | **done** | 3 file; **200 passed, 4 skipped** (+8 test); `inject_plume` không đổi chữ ký. Nghiệm thu: `issues/26-plume-context-contract.md` §PM |
| 27 | Bước 0 — wet ground (port `dee.cpp`, không vendor CC BY-NC) | **next (27a)** | `issues/27-wet-ground.md` |
| 28 | Bước 1–3 — vùng sau đuôi, sinh cụm, vòng đời | **done** (28a/b/c) | **217 passed, 4 skipped**. Vệt trong tầm **73,7 m @130 km/h** (trước 7,3 m); marker `PLUME_STATE` 7 khoá; D6 đã sửa. Còn tồn sang 30/31: trần 2.000 cắt 45–82 %, điểm/cụm lệch 6× so với paper. Nghiệm thu: `issues/28-plume-volume-lifetime.md` §PM |
| 29 | Bước 4–5 — ray casting, attenuation, strongest return | blocked by 27, 28 | `issues/29-ray-casting-attenuation.md` |
| 30 | Intensity, ring, seed theo epoch, cap | blocked by 29 | `issues/30-intensity-ring-seed-cap.md` |
| 31 | Nghiệm thu thống kê + render + audit độc lập | blocked by 25–30 | `issues/31-acceptance-v2.md` |

### Quyết định 2026-11-10: v2 đi phương án đầy đủ

User chốt **phương án 1** — làm đủ 6 bước theo paper, gồm **ray casting + wet ground**.
Spec: `spec-v2-paper-faithful.md`. Chi phí **5–6,5 ngày agent + review**; GPU chỉ dùng ở A/B sau ticket 31.
Khác paper: ta tách được `plume-only` vs `plume+wet` (paper gộp cả hai thành một dòng "spray" trong Bảng II),
nên giải thích được vì sao ticket 11 null.

## Thứ tự hiện tại

Nguyên tắc: **việc quyết định thiết kế làm trước, việc cơ học làm sau.**

| Bước | Ticket | Trạng thái |
|---|---|---|
| 1 | **25** đo 0 GPU | ✅ **done 2026-11-10** — chặn 26–31 đã gỡ |
| 2 | **26 → 27 → 28 → 29 → 30** | ⏭ **next = 26** — hình học → wet ground → động học → ray casting → trường dữ liệu |
| 3 | **31** nghiệm thu + render + audit | trước khi train lại |
| 4 | A/B `plume-only` vs `plume+wet` | chỉ sau 31, cần GPU |
| 5 | **13** gate review | dùng kết quả null của 11 + chẩn đoán 11-i |

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