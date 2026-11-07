# Trạng thái dự án — spray plume augmentation cho BEVFusion

**Cập nhật:** 2026-11-07 09:10 · **PM:** Hermes (chốt phạm vi, tiêu chí, nghiệm thu) · **Thi công:** CommandCode
**Đọc file này trước khi mở bất kỳ ticket nào.** Ticket là chi tiết; file này là thứ tự và phạm vi.

## Mục tiêu một câu

Chứng minh bằng thí nghiệm paired A/B rằng augment spray plume vào nhánh LiDAR của BEVFusion làm giảm
khoảng cách giữa mAP trên frame sạch và frame có spray — đo trên nuScenes, không train trên SemanticSpray.

## Trạng thái hiện tại

**02b đã xong; preconditions 1–6 PASS.** Ticket 02 ALL_PASS (582/582, forward finite), dataset gate 04 xong
(infos 120/120 + load sample), ticket 06 adapter evaluator xong (mAP 0.298 trên frame thật), ticket 07
`PlumeTransform` pass 12/12 check. Spec đã flip `ready-for-agent`.

Việc tiếp theo: **08 (model routing)** → 09 → 10 → 11 → 13; 14 chạy song song; 16 → 17 độc lập với
pipeline (chỉ chạm `scripts/`, `spray/`, `tests/`, `docs/`).

Lịch sử fix môi trường: thiếu `numba` → uv không resolve được torch → escape `%` trong `git log --format`
→ thiếu CUDA dev headers → `gcc-13` không hợp CUDA 11.8 → tên package apt sai. Chi tiết trong
`02b-numba-fix.md`.

## Bảng ticket

| # | Việc | Trạng thái | Phụ thuộc | Next action |
|---|---|---|---|---|
| 01 | Working copy MIT + pin `da93b27` | **done** | — | — |
| 02 | Smoke test checkpoint + 1 sample | **done** | 02b | — |
| 02b | Sửa môi trường Kaggle, chạy lại smoke test | **done** | 01 | — |
| 03 | Velocity frame + ObjectPaste | **done** | 01 | — |
| 04 | Dataset gate trên Kaggle (infos pkl, mini split) | **done** | 02b | — |
| 05 | Evaluator core + synthetic tests | **done** | — | — |
| 06 | Adapter evaluator cho output MIT | **done** | 02, 05 | mAP 0.298 trên frame thật |
| 07 | Pipeline transform + `points_clean` | **done** | 03, 05 | 12/12 check |
| 08 | Model forward routing | **done** `16517f1` | 07 | subclass + plumbing, 49 test, vendor giữ `da93b27` |
| 19 | Kaggle code sync (dataset + kernel) | **ready-for-agent** | — | repo private ⇒ dataset private 2 MB |
| 09 | End-to-end pipeline test | blocked | 07, 08, **19** | cần `mmdet3d` ⇒ phải chạy trên Kaggle |
| 10 | Train/eval config A/B | blocked | 04, 09 | config theo arm A/B/B0 |
| 11 | Mini A/B run + report | blocked | 06, 10 | chạy 1 seed T4, ghi report |
| 12 | SemanticSpray statistics | **done** | — | — |
| 13 | Gate review sau mini A/B | blocked | 11 | quyết định đi tiếp hay dừng |
| 14 | Arm B0 — lọc spray rồi detect | ready-for-agent | 02, 05 | filter + frame list chốt với PM |
| 16 | Đo hình học plume thật theo cự ly (SemanticSpray) | **done** `08f6715` | — | số: `docs/plume-geometry-vs-real.md` |
| 17 | Sửa generator theo số đo của 16 (count theo cự ly + bẹp 0,64) | **done** `5d7c478` | — (16 xong) | S hiệu dụng **0,885**; 35 test |
| 18 | Quét lại eligibility nuScenes (ego speed, scene count, bảng 2 chiều) | **done** — 3 lần push | — | số: `docs/nuscenes-eligibility.md` |

## Thứ tự hiện tại (2026-11-07, sau khi 16/18 xong)

Nguyên tắc: **việc quyết định thiết kế làm trước, việc cơ học làm sau.**

| Bước | Ticket | Trạng thái |
|---|---|---|
| 1 | **18** đo khả thi | ✅ xong → eval set = val, d≤50 m, 196 frame / 16 scene |
| 2 | **16** đo hình học | ✅ xong → 17,0 điểm/cụm trung bình, giảm 3,0× theo cự ly, `r_range/r_extent` = 1,28 |
| 3 | **17** sửa generator theo số | ✅ xong `5d7c478` — count theo cự ly, bẹp ×0,885 |
| 4 | **08 → 09** | cơ học, không bị lật bởi 16/17 |
| 5 | **10 → 11 → 13** | chốt eval set + generator final → mới sinh số |

`14` (B0) chạy song song được với `10–11`. `15` xong.

## Critical path

`07` → `08` → `09` → `10` → `11` → `13`

`14` (B0) chạy song song được với `10–11`; chỉ cần evaluator + model.

`16 → 17` **độc lập với pipeline**: chỉ chạm `scripts/`, `spray/`, `tests/`, `docs/` — không cần GPU,
không cần checkpoint. Có thể làm song song với `08`.

## Quyết định đã chốt — không mở lại

- Pin MIT BEVFusion `da93b27`; không dùng HEAD. (`docs/adr/0001`)
- v1 chỉ plume, không mô phỏng wet-ground/attenuation. (`docs/adr/0002`)
- Lý do **định lượng** để bỏ attenuation ở v1: hệ số tắt hiệu dụng **0,04 m⁻¹** = `exp(−2×0,02×d)`
  [PAPER §III] × quãng xuyên thực tế 0,5–0,8 m (1–2 cụm r = 0,3 m) → intensity còn **98,0–96,9%** →
  dưới ngưỡng lượng tử hoá intensity của nuScenes. Chỉ đáng làm nếu chuyển sang regime fully-watered
  của paper (500–1.500 điểm/frame).
- v1 đặt điểm plume trên **vỏ cầu phía cảm biến**, không trong khối cầu; không dựng beam grid/OSI
  (ticket 16–17). Mật độ vẫn neo SemanticSpray, **không** phụ thuộc cự ly — nếu ticket 16 chứng minh
  điều đó sai thì PM mở ticket 18.
- Không train/eval detection trên SemanticSpray; chỉ dùng để calibrate + point-wise sanity check. (`docs/adr/0003`)
- Velocity của box đã ở LiDAR frame của keyframe hiện tại; plume phải chèn **sau** `GlobalRotScaleTrans`
  và `RandomFlip3D`, **trước** `PointShuffle`; box do `ObjectPaste` set velocity = 0. (`docs/velocity-contract.md`)
- Ba arm: A = clean baseline, B = có plume, B0 = lọc spray rồi detect.
- **Eval set (chốt 2026-11-07, ticket 18):** val split, box vehicle ≥50 km/h **phía trước** (`x>0`),
  `d ≤ 50 m`, **không lọc vận tốc ego** → **196 frame / 16 scene**; báo per-range 0–30 m (117 frame) và
  30–50 m (79 frame). Nguồn: `docs/nuscenes-eligibility.md`.
  - **Bỏ lọc ego** vì paper §III-A có kịch bản ego **đứng yên** (xe khác chạy ngang vẫn sinh plume);
    lọc ego ≥50 km/h làm val còn **0 frame**.
  - **Không dùng scene highway**: 0 scene highway trong val, chỉ 2 scene trên toàn bộ nuScenes.
  - **Không tự chia lại trainval** để lấy thêm frame: checkpoint pretrained đã thấy 700 scene train →
    eval trên đó là rò rỉ, kể cả khi không train thêm.
  - Rủi ro đã biết: 16 scene → CI rộng; nếu G3#1 fail thì kết luận là "không đo được gap với n=16 scene",
    **không** phải "augment vô dụng".
- **Số cũ 34.029 frame / 697 frame / 2,0% là toàn bộ trainval** (850 scene / 34.149 keyframe), không phải
  val split (150 / 6.019). Hàng đối chứng tái lập đúng (957 box / 698 frame, +0,53%) nên phép đo cũ đúng,
  chỉ nhãn sai. Đã đính chính `docs/velocity-contract.md`.
- Kết quả dương trên plume tổng hợp là **cận trên lạc quan**, không chứng minh giúp spray thật. Camera branch
  nhận `points_clean` nên lợi ích nếu có chỉ đến từ LiDAR.

## Non-goals (không làm trong dự án này)

- Không port model C++ ray-based của Linnhoff (occlusion, drag, beam/ray-sphere); không dựng OSI/beam angles.
- Code tham chiếu của Linnhoff 2022 **đã publish** trên GitHub `openMSL/sl-1-2-reflection-based-lidar-object-model`
  (MPL-2.0). v1 port 3 cơ chế: kích hoạt 40 km/h, số cụm theo 50 km/h (nhân hệ số trạng thái dừng `K`),
  lifetime `T = wfh·0,02·(v−50) + 0,2` (không phải hằng 0,2 s) — chi tiết giá trị và số dòng ở
  `docs/plume-model-provenance.md` §Code tham chiếu. Phần **không** port: occlusion, drag, ray-sphere/beam.
  Occlusion trong model thật chỉ **thay thế các return yếu** (mặt đường, vật tối ở xa); xe thật intensity
  4–40 gần như không bị che, nên v1 chỉ **thêm** điểm. Xếp lại nguồn lạc quan:
  **(1) camera branch sạch, (2) số cụm, (3) lifetime, (4) drag, (5) occlusion.**
- Không tune hyperparameter, không multi-seed ở v1 (1 seed T4, kết quả chỉ mang tính hướng).
- Không hứa hẹn cải thiện trên spray thật.

## PM nghiệm thu một ticket thế nào

1. Có số thật, không có ô `null`, không có "ước tính" ghi như số đo.
2. Mọi con số mới truy được nguồn: `[ĐO] / [PAPER] / [CODE] / [CHỌN]`.
3. Test liên quan pass, `git status` sạch, commit message nêu rõ đã làm gì.
4. Không mở rộng phạm vi: việc ngoài ticket thì ghi thành ticket mới, không làm kèm.
5. Nếu bị chặn: dừng, báo PM kèm log + giả thuyết, không tự đổi pin hay version đã chốt.