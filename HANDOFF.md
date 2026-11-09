# HANDOFF — Spray plume pilot (BEVFusion MIT)

Cập nhật: **2026-11-09 22:45** · nhánh `main` · HEAD `88770b5` · https://github.com/Yuhnguyn/bevfusion-spray-pilot
**Nguồn sự thật về tiến độ: `.scratch/spray-augmentation/STATUS.md`.**
File này nói: đang ở đâu, làm gì tiếp, và dựng lại máy mới trong 5 phút.

---

## 1. Đọc gì khi mở session mới (theo thứ tự, đừng đọc thêm)

1. `HANDOFF.md` (file này) — 3 phút.
2. `.scratch/spray-augmentation/STATUS.md` — board + mục **"Dừng shift 2026-11-09 22:45"**.
3. `.scratch/spray-augmentation/issues/11-mini-ab-run.md` — toàn bộ kết quả + chẩn đoán (mục 11-h, 11-i).
4. Chỉ khi cần: `docs/PROJECT.md` §5, `docs/plume-model-provenance.md`.

Không đọc lại toàn repo. Không đọc log `/tmp` trừ khi ticket yêu cầu.

## 2. Đang ở đâu — một đoạn

Toàn bộ dây chuyền A/B **đã chạy end-to-end trên Kaggle**: train 2 arm × 2.000 bước (kernel v9) → eval
4 ô trên 196 frame/16 scene (kernel v13). Kết quả **null**, và đã chẩn đoán được **vì sao** null (mục 11-i):
plume chỉ thêm ~0,4 % số điểm nên hộp dự đoán dịch trung vị **3 mm**, số hộp không đổi, mAP chỉ nhúc nhích
khi hộp sát ngưỡng IoU 0,5 bị lật. Toàn bộ delta −0,0031 ≈ **6 hộp lật ròng / 3.609 GT box**.

| Ô | mAP | recall |
|---|---|---|
| A clean | 0,5458 | 0,5896 |
| A spray | 0,5449 | 0,5871 |
| B clean | 0,5459 | 0,5903 |
| B spray | 0,5419 | 0,5857 |

`EVAL_OK delta_A=-0.0009 delta_B=-0.0040 interaction=-0.0031 ci95=[-0.0140, 0.0017]`

**Được phép viết:** "pipeline A/B chạy, tạo 4 ô eval + paired CI; với 2.000 bước, plume ~0,4 % điểm,
16 scene, không phát hiện khác biệt."
**Không được viết:** "spray augmentation không có tác dụng", "plume không ảnh hưởng detector".

## 3. Việc tiếp theo

**Ticket 13 (gate review) là việc kế tiếp** — đóng gói null result + phân tích power, rồi mới quyết hướng.
Ba hướng mở rộng, chi phí GPU tính từ số đo thật (boot ~11 phút + eval ~10 phút/lượt):

| Hướng | Chi phí | Trả lời được gì |
|---|---|---|
| **A. Tăng liều plume 5–10×**, giữ 2.000 bước | ~1,2 h | Tác dụng có vượt nhiễu khi mật độ tăng? (rẻ nhất, kiểm tra đúng nghi phạm) |
| **B. Đổi thước đo** (đếm hộp lật TP↔FP, AP theo dải cự ly gần) | ~0 GPU (chạy lại scoring trên output v13 đã tải) | Tín hiệu có bị thước đo thô che mất? |
| **C. Train 10.000 bước/arm** | ~6,7 h | Tác dụng có xuất hiện khi train đủ lâu? |

Thứ tự khuyến nghị: **B (miễn phí) → A (~1,2 h) → C (chỉ khi A vẫn null)**.
Hướng A/B là **thay đổi mô hình hoặc thước đo**, phải ghi `[CHỌN]` vào `docs/plume-model-provenance.md`
và chốt tham số **trước** khi xem kết quả; không trộn với A/B cũ.

## 4. Dựng lại máy trên PC (copy nguyên khối)

```bash
# 0. công cụ
uv venv /tmp/kc && uv pip install --python /tmp/kc/bin/python "kaggle==2.2.5"
    # CLI 2.2.4 bỏ qua hậu tố version của kernel → luôn dùng /tmp/kc/bin/kaggle
cp ~/.kaggle/kaggle.json  # ← copy tay từ máy cũ, KHÔNG nằm trong git

# 1. repo
git clone https://github.com/Yuhnguyn/bevfusion-spray-pilot.git && cd bevfusion-spray-pilot

# 2. MIT tree (gitignored, pin bắt buộc)
git clone https://github.com/mit-han-lab/bevfusion.git mit/bevfusion
git -C mit/bevfusion checkout da93b27

# 3. test local (không cần mmcv; 4 test e2e tự skip)
CONDA_NO_PLUGINS=true python -m pytest -q tests/     # kỳ vọng: 192 passed, 4 skipped
```

Checkpoint **không cần chuyển máy**: đã có trên Kaggle dataset `nguynhuy9669/bevfusion-spray-ckpt`
(2 file × 163.723.893 byte). Output eval cũng lấy lại được bằng
`/tmp/kc/bin/kaggle kernels output nguynhuy9669/bevfusion-spray-train/13 -p /tmp/kv13out`
(chậm và hay 502 — tải theo lô, đừng tải cả 1.568 file một lượt).

## 5. Kaggle — trạng thái cloud

| thứ | giá trị |
|---|---|
| Kernel | `nguynhuy9669/bevfusion-spray-train` — v9 train COMPLETE, **v13 eval COMPLETE** (mới nhất) |
| Dataset code | `nguynhuy9669/bevfusion-spray-pilot-code` (private, ~5,75 MB, 172 file) |
| Dataset ckpt | `nguynhuy9669/bevfusion-spray-ckpt` (ready, 322 MB) |
| Dataset nuScenes | `sahangunasekara92/nuscenes-v1-0-full-keyframes` (~28.000 keyframe, **không sweeps**) |
| Dataset phụ | `aadimator/nuscenes-mini` (5,37 GB, 404 keyframe, 3.531 sweeps thật — chỉ để probe) |
| GPU quota | **6,35 h đã dùng / 30 h**, còn **23,65 h**, reset `2026-11-14T00:00:00Z` |
| `task_args.txt` | `--task=ab-eval --ckpt-dir=/kaggle/input/bevfusion-spray-ckpt --limit=0` |

Vòng lặp làm việc:

```bash
python scripts/kaggle_code_sync.py                        # sync code TRƯỚC khi push
/tmp/kc/bin/kaggle kernels push -p kaggle/train            # chạy đúng TASK trong task_args.txt
/tmp/kc/bin/kaggle kernels status nguynhuy9669/bevfusion-spray-train
/tmp/kc/bin/kaggle kernels logs nguynhuy9669/bevfusion-spray-train/13 > /tmp/kv13.log
```

Script hỗ trợ (đã copy vào `.scratch/hermes-tools/`): `poll_kernel_version.sh <ver>` tự chờ + tải log khi
xong; `kernel_card.py <log>` in card nén; `quota_watch.sh` xem quota.

## 6. Cách làm việc (giữ nguyên, đừng đổi)

- **PM không tự code.** Việc thi công giao CommandCode: brief trong `.scratch/spray-augmentation/dispatch/`,
  chạy `commandcode -t -p "$(cat dispatch-XX.md)" --yolo --max-turns N`, log `/tmp/tXX.log`.
- **Brief phải có dòng `Skill: <đường dẫn tuyệt đối>`** — CommandCode không tự chọn skill (đo trên 4 log: 0 lần).
  Hạ tầng/boot chain: không gán skill. Viết test trước: `~/.agents/skills/tdd/SKILL.md`.
- **Một agent tại một thời điểm** — cùng worktree, `git add -A` của agent này nuốt file agent kia.
- Mỗi ticket: brief → chạy → **PM tự verify** (`git show --stat`, `git status`, pytest, grep marker) → ghi
  nghiệm thu vào ticket + `STATUS.md` → commit. Không tin báo cáo của agent.
- `EXIT=8` = cạn `--max-turns`, **không** phải fail: kiểm `git log`/`git status` trước khi kết luận.
- Job dài: chạy background + `notify_on_complete=true`; không `sleep`/poll tay.
- Trước mỗi lần đổi đường code eval: chạy `--limit=5` trước (bài học v11/v12: ~56 phút GPU cho 2 lỗi nối tiếp).

## 7. Bẫy đã gặp (đừng lặp lại)

1. **Đọc tên file config rồi suy ra nội dung** — sai 2 lần: `point_cloud_range` ±54 (thật ±51,2); `swint_v0p075/default.yaml` có `fuser = None` (file đúng `convfuser.yaml`). Luôn mở file.
2. **Hardcode ±54** — đó là model config; dataset dùng ±51,2.
3. **Tin marker xanh một mình** — từng có `E2E_OK` giả vì 4 test bị skip; phải thấy đúng số test kỳ vọng.
4. **`timeout` không tồn tại** trên shell macOS mặc định.
5. **`kaggle kernels output`** hay timeout (exit 124) hoặc 502 → dùng `kernels logs`, tải output theo lô.
6. **`wfh` đơn vị mét** (0,001), không phải mm.
7. **Script kernel một file**: `main.py` phải tự chứa; đường dẫn không được suy từ `__file__` (kernel chạy ở `/kaggle/src`, code ở `/kaggle/working/repo`) — dùng `resolve_args_file()`.
8. **`task_args.txt`**: mỗi token bắt đầu bằng `-`, dạng `--key=value`.
9. **Push version mới KHÔNG huỷ lượt đang chạy** — tạo session song song (2 lần ăn GPU). Muốn dừng phải bấm Stop trên web UI; CLI 2.2.4/2.2.5 không có `cancel`.
10. **`sweeps_num: 9` trên dataset keyframes-only** chỉ nhân bản điểm trùng (90 % trùng toạ độ), không phải sweep thật; đã chốt `sweeps_num: 0`.
11. **Sửa file trong repo (kể cả `task_args.txt`) phải sync code dataset TRƯỚC khi push**, không thì kernel chạy bản cũ.
12. **Bootstrap theo scene, không theo frame** — thêm frame trong cùng 16 scene không thu hẹp CI.

## 8. Nơi chứa

| thứ | đường dẫn |
|---|---|
| Board + trạng thái | `.scratch/spray-augmentation/STATUS.md` |
| Ticket | `.scratch/spray-augmentation/issues/*.md` |
| Brief giao việc (45 file) | `.scratch/spray-augmentation/dispatch/` |
| Script hỗ trợ Kaggle | `.scratch/hermes-tools/` |
| Persona PM (SOUL + skill + memory) | `.scratch/hermes-pm/` |
| Quyết định + khác biệt paper | `docs/PROJECT.md` §5, `docs/adr/` |
| Kanban HTML | `docs/kanban.html` (sinh bằng `scripts/build_kanban.py`) |
| Provenance plume | `docs/plume-model-provenance.md` |
| Ảnh/clip plume | `docs/figs/plume/` |
| Code kernel | `kaggle/train/{main.py,smoke.py,ab_run.py,ab_eval.py}` |
| Eval/scoring | `proxy_eval/`, `scripts/make_eval_split.py` |