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
- **V2 (calibration leak) — phần ĐO đã xong, phần CODE chưa:**
  - Bảng cụm/frame từ RoadSpray `*_static` cho **Crafter**: 54 bag / 1558 frame, 8 tốc độ,
    CI95 ±10 % → `docs/measurements/roadspray-static-clusters-by-speed.md`.
  - Kiểm chứng chéo với bảng SSPP cũ: tỉ lệ **1,13×** (0,91–1,32), Pearson **r = 0,79**, cùng chạm
    đáy ở 120 km/h.
  - Bảng SSPP **per-fold không leak** + CI95 → `docs/measurements/sspp-cluster-table-folds.md`.
  - **`_CLUSTER_VISIBLE_BY_SPEED` trong `spray/plume.py` VẪN là bảng SSPP `cal` cũ** (chưa thay).

## Đang dừng ở đâu (2026-11-18 17:00, lý do: mạng chậm)

Việc duy nhất còn thiếu của bảng calibration là **lớp Golf**. `Golf_static.zip` mới tải được
**85 102 592 / 5 460 144 118 byte**, đã đổi tên thành `data/roadspray/Golf_static.zip.part` để
không ai nhầm là file xong (thư mục `data/` gitignored).

Về nhà **tải tiếp, không tải lại từ đầu**:

```bash
cd ~/projects/bevfusion-spray-pilot
curl -sS -L -C - -o data/roadspray/Golf_static.zip.part \
  "https://tudatalib.ulb.tu-darmstadt.de/server/api/core/bitstreams/4d48e6df-6e7b-42e4-a267-10a5a5c73b95/content"
stat -f%z data/roadspray/Golf_static.zip.part      # phải đúng 5460144118
mv data/roadspray/Golf_static.zip.part data/roadspray/Golf_static.zip
```

Đo Golf bằng đúng pipeline của Crafter (~15 phút cho ~85 bag `direction=+1`):

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python -u \
  scripts/roadspray_static_plume_box.py --zip data/roadspray/Golf_static.zip \
  --out .scratch/roadspray-cal/tmp/plume_golf.jsonl
```

Rồi làm 3 việc theo thứ tự:

1. **Đưa bảng vào code**: thay `_CLUSTER_VISIBLE_BY_SPEED` (`spray/plume.py:24-47`) bằng bảng
   static (Crafter + Golf); cập nhật ADR-0006 ghi nguồn + dải bất định **±30–40 %** (chủ yếu do
   định nghĩa vùng, xem doc §5). Giữ bảng SSPP cũ trong docs để đối chiếu, không xoá.
2. **A3** — đuôi phân bố điểm/cụm. Ba mục tiêu T1/T2/T3 vẫn chưa chốt, xem plan §2 "A3 — phát hiện
   sau A1". Số liệu mới nhất: sinh 29,1 cụm/frame vs thật 28,5 ✅ nhưng điểm/frame sinh 140 vs
   thật 1050–2220 ⚠️; đuôi cụm lớn nhất sinh ~91 điểm vs thật 982–1238.
3. **A4** → cổng B (`sinh/thật ∈ [0,7; 1,5]`) → **cổng C (quan trọng nhất: plume phải làm tăng FP
   của detector; 0 GPU, có thể giết cả hướng train)** → D/E/F.

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
