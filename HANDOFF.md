# HANDOFF — nhánh `sspp` (BEVFusion trên SemanticSpray++)

Cập nhật: **2026-11-18 17:00** · nhánh `sspp` @ `2652f26` · tách từ `main` @ `f3fb7d2`.

## Đọc gì khi mở session mới (theo thứ tự, đừng đọc thêm)

1. `README.md` — 2 phút, biết dự án hỏi gì.
2. `docs/PROJECT.md` — câu hỏi, phạm vi, số đo, sổ quyết định, chốt chặn.
3. `.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md` — 5 bước thi công.
4. Chỉ file đang làm, không đọc lại toàn repo.

## Nhánh này là gì

`main` = hướng cũ: detection trên **nuScenes** + plume tổng hợp, kết quả **null**, đóng lại làm
bản đối chứng. `sspp` = hướng mới: detection trên **SemanticSpray++** (spray thật, box thật),
chỉ LiDAR-only.

Lý do đảo ngược: `docs/adr/0005-sspp-as-detection-domain.md`. Bản ADR cũ nói ngược lại
(`0003`) đã xoá khỏi nhánh này nhưng còn trong lịch sử: `git show main:docs/adr/0003-*`.

## Trạng thái

- Test: **203 passed** (không cần GPU).
- **Chưa có kết quả detector nào.** Mọi số trong `docs/measurements/*.md` là đo trên dataset.
- Đổi protocol xong (`docs/adr/0006-…`): eval = **3-fold leave-speed-out trên 36 scene** (pooled n=36);
  calibration từ **RoadSpray `*_static`**; criterion = effect size + CI95 thay vì pass/fail.
  Kế hoạch thi công hiện hành: **`.scratch/roadspray-cal/plan.md`** (6 giai đoạn A–F).
- **Giai đoạn A:** A1 ✅ (`8cc9207` — sửa lỗi 4× ngân sách cụm, test
  `tests/test_plume_cluster_budget.py`) · A2 ✅ (`f9c8b44` — wet ground viết lại theo Hahner 2022,
  test `tests/test_wet_ground_hahner.py`) · **A3 ⚠️ chưa xong** (đuôi phân bố điểm/cụm) ·
  **A4 chưa làm** (test tích hợp dùng box đúng quy ước adapter).
- **V2 (calibration leak) — XONG cả đo lẫn code:**
  - `_CLUSTER_VISIBLE_BY_SPEED` đã thay bằng bảng **RoadSpray static** cho cả Crafter và Golf
    (9 bag/lớp/tốc độ; đối chứng âm phía trước xe = 0,0 cụm/frame):
    Crafter 6,0 / 13,2 / 19,0 / 26,7 / 24,8 / 25,7 / 27,4 / 20,6 / 22,2 (50→130 km/h);
    Golf 4,7 / 8,8 / 13,2 / 17,8 / 20,9 / 22,6 / 22,0 / 25,8 / 25,2.
  - Kiểm chứng chéo: Crafter tỉ lệ **1,15×**, **r = 0,94** so với bảng SSPP cũ; bảng per-fold không
    leak khớp r = 0,77 → `docs/measurements/{roadspray-static-clusters-by-speed,sspp-cluster-table-folds}.md`.
  - Dải bất định **±30–40 %** (do định nghĩa vùng, không do mẫu) — cổng B phải đọc cùng dải này.

## Đang dừng ở đâu (cập nhật 2026-11-18 23:45)

`Golf_static.zip` (5 460 144 118 B, 171 bag) **đã có** trong `data/roadspray/` — không cần tải gì nữa.
Cả hai lớp đã đo xong và bảng đã vào code.

Việc tiếp theo:

1. **A3 — đã chốt đích, chưa sửa code.** Đích = **T2 theo cấu trúc** (xem plan §2 A3 +
   `docs/measurements/sspp-cluster-size-distribution.md`): phân bố thật **hai đỉnh** — điểm/cụm p50 =
   5–7 ở mọi tốc độ (generator đã khớp) nhưng tỉ lệ điểm trong cụm ≥50 điểm tăng 15 % → 85 % khi tốc
   độ 50 → 130 (generator: **0 %**). Thiếu **cơ chế chuỗi**, không phải thiếu cụm to. Tiêu chí xong:
   `% điểm trong cụm ≥50 đ` lệch ≤10 điểm %, `p95` trong khoảng thật, `cụm/frame` không đổi.
2. **A4** (test tích hợp box convention) → cổng B (`sinh/thật ∈ [0,7; 1,5]`) → **cổng C (quan trọng
   nhất: plume phải làm tăng FP của detector; 0 GPU, có thể giết cả hướng train)** → D/E/F.

## Việc kế tiếp (đã rút gọn — chi tiết ở §"Đang dừng ở đâu")

Đọc `.scratch/roadspray-cal/plan.md` §2. Thứ tự: **đưa bảng calibration vào code** → **A3** (đuôi
phân bố) → **A4** (test tích hợp box convention) → chốt chặn A → B (sinh vs thật) →
**C (plume phải làm tăng FP của detector — cửa chặn quan trọng nhất, 0 GPU)** → D → E → F (chỉ F cần GPU).

Chốt chặn A: `pytest -q tests/` xanh **và** A1/A2/A4 có test mới. Không sang B khi chưa đạt.

Ba thứ dễ sai khi làm adapter/split, đã đo sẵn:

1. `z' = center3D.z − size3D.z/2` — đáy hộp, không phải tâm. Kiểm: box đầu `Crafter_dynamic/0000`
   cho `−0,4113`, đúng mặt đường.
2. `box_dim` phải là **9** (7 hình học + 2 vận tốc), không phải 7.
3. `poses.txt` **không có tịnh tiến** → tốc độ ego đọc từ `metadata.txt` cột `ego_velocity`.

Dữ liệu RoadSpray đã có trong `data/roadspray/` (gitignored):

| File | Byte | Trạng thái |
|---|---:|---|
| `Crafter_static.zip` | 7 924 255 130 | ✅ khớp release, 163 bag |
| `Crafter_dynamic.zip` | 6 127 018 713 | ✅ khớp release, 108 bag |
| `meta_data_measurement.xlsx` | 26 774 | ✅ 549 dòng — **có tốc độ + mức nước từng bag, không cần decode ADMA** |
| `meta_data_dataset.json` | 2 517 | ✅ transform tĩnh của 5 cảm biến |
| `Experiment_Setup.zip` | 8 223 416 | ✅ |
| `Golf_static.zip.part` | 85 102 592 / 5 460 144 118 | ⏸ **dở** — xem §"Đang dừng ở đâu" |
| `Golf_dynamic.zip` | 6 009 340 245 | 📦 còn ở `~/Downloads/`, chưa copy vào `data/` |

`Golf_dynamic` là **kịch bản following** (ego bám sau 20/30 m) — **không** dùng để calibrate (paper
calibrate ở kịch bản passing = `*_static`). Nó chỉ cần cho việc dựng lại SSPP và kiểm tra chéo.

## Lệnh chạy test

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python -m pytest -q tests/
# 203 passed
```

Thiếu `env -u PYTHONPATH` thì numpy của venv Python 3.14 bị nạp vào Python 3.11 và toàn bộ test
lỗi import.

## Dựng lại máy khác

```bash
git clone https://github.com/Yuhnguyn/bevfusion-spray-pilot.git && cd bevfusion-spray-pilot
git checkout sspp
git clone https://github.com/mit-han-lab/bevfusion.git mit/bevfusion   # gitignored, pin bắt buộc
git -C mit/bevfusion checkout da93b27                                   # mit/PIN.md
```

Dataset SemanticSpray++ (31 GB) tải bằng `scripts/fetch_semantic_spray.py`, đặt vào
`data/SemanticSprayDataset`. Checkpoint `lidar-only-det.pth` (33.362.653 byte) tải theo
`docs/PROJECT.md` §7.

## Cấu trúc còn lại

```
spray/        10 module sinh plume + 3 module đo spray thật
proxy_eval/   matcher (BEV IoU) + bootstrap (theo scene)
scripts/      3 script: fetch / split / stats
docs/         PROJECT.md + ADR 0001, 0005 + 3 measurement + 1 reference
tests/        23 file, 203 test, không cần GPU
mit/          working copy pin da93b27 (gitignored, PIN.md tracked)
data/         SemanticSprayDataset 31 GB (gitignored)
```

## Bẫy đã trả giá (giữ từ nhánh cũ, còn đúng)

1. **Đọc tên file config rồi suy ra nội dung** — sai 2 lần ở nhánh cũ. Luôn mở file.
2. **Tin marker xanh một mình** — `E2E_OK` từng xanh giả vì 4 test bị skip. Phải thấy đúng số test.
3. **`timeout` không tồn tại** trên shell macOS mặc định.
4. **Bootstrap theo scene, không theo frame** — thêm frame trong cùng scene không thu hẹp CI.
5. **Median ≠ mean** khi đặt tiêu chí. Trên spray thật: p50 = 6 điểm/cụm nhưng mean = 43,3.
   Dùng p50 làm ngưỡng, đừng dùng mean.
6. **`z` đáy box không phải tâm** — nhầm một lần là hộp lơ lửng trên nóc xe.

## Lấy lại thứ đã xoá

```bash
git checkout main -- <path>                        # một file
git checkout main -- .scratch/spray-augmentation/  # board 48 ticket cũ
git show main:docs/adr/0003-semantic-spray-eval-only.md
git show main:kaggle/train/ab_eval.py              # eval A/B cũ
```
