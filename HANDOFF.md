# HANDOFF — nhánh `sspp` (BEVFusion trên SemanticSpray++)

Cập nhật: **2026-11-18** · nhánh `sspp` @ `064f1c1` · tách từ `main` @ `f3fb7d2`.

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

- Dọn nhánh **xong**: 6 commit. Test hiện **178 passed** (không cần GPU).
- **Chưa có kết quả detector nào.** Mọi số trong `docs/measurements/semantic-spray-*.md` là đo
  trên dataset, không phải kết quả model.
- **2026-11-18 — đổi protocol** (`docs/adr/0006-…`): eval = 3-fold leave-speed-out trên 36 scene
  (pooled n=36); calibration chuyển sang RoadSpray `*_static`; criterion = effect size + CI95 thay
  vì pass/fail. Kế hoạch thi công hiện hành: **`.scratch/roadspray-cal/plan.md`** (6 giai đoạn A–F).
- **Generator CHƯA đúng**: `docs/measurements/plume-root-cause.md` §"Thứ tự sửa đề xuất" — 3 lỗi
  quy ước box đã sửa (`3a971b8`), **lỗi 4× ngân sách cụm chưa sửa**, wet ground đang sửa dở
  (`spray/wet_ground.py` diff 340 dòng chưa commit), đuôi phân bố điểm/cụm chưa khớp.
  `178 passed` **không** chứng minh generator đúng — xem plan §2 A4.

## Việc kế tiếp — giai đoạn A của plan mới

Đọc `.scratch/roadspray-cal/plan.md` §2. Giai đoạn A (0 GPU, 2–3 ngày): sửa generator.

1. **A1 — lỗi 4× ngân sách cụm** (chưa sửa): `alive = rate × 4T/Δt = 4 × visible`, chọn một hướng
   (`rate = visible/(4T/Δt)` **hoặc** thinning trong `prune()`). Test mới: `alive/visible ∈ [0,9; 1,1]`
   ở 60/100/120 km/h.
2. **A2 — commit + test wet ground** đang sửa dở: test khẳng định `mean_ratio < 1`.
3. **A3 — đuôi phân bố**: cụm lớn nhất sinh ra ≥ 500 điểm (thật 982–1.238).
4. **A4 — test tích hợp** dùng box đúng quy ước adapter (9 cột, `box[2]` = đáy).

Chốt chặn A: `pytest -q tests/` xanh **và** A1/A2/A4 có test mới. Không sang B khi chưa đạt.

Thứ tự sau đó: B (sinh vs thật) → **C (plume vs detector, cửa chặn quan trọng nhất)** → D (cal từ
RoadSpray) → E (CV + pseudo-box) → F (train). Cần GPU chỉ ở F.

Ba thứ dễ sai khi làm adapter/split, đã đo sẵn:

1. `z' = center3D.z − size3D.z/2` — đáy hộp, không phải tâm. Kiểm: box đầu `Crafter_dynamic/0000`
   cho `−0,4113`, đúng mặt đường.
2. `box_dim` phải là **9** (7 hình học + 2 vận tốc), không phải 7.
3. `poses.txt` **không có tịnh tiến** → tốc độ ego đọc từ `metadata.txt` cột `ego_velocity`.

Dữ liệu đã có sẵn cho giai đoạn D: `~/Downloads/Crafter_static (1).zip` = 7.924.255.130 byte
(khớp release, 163 bag) và `~/Downloads/Golf_dynamic.zip` = 6.009.340.245 byte (108 bag — chứa 9
recording Golf mà SSPP thiếu). `Golf_static.zip` vẫn chưa có.

## Lệnh chạy test

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python -m pytest -q tests/
# 178 passed
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
tests/        16 file, 151 test, không cần GPU
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
