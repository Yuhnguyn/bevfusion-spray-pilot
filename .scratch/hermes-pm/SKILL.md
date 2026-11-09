---
name: pm-orchestration-playbook
description: Use when orchestrating coding agents (CommandCode/opencode/Codex) as PM — route skills, write briefs, dispatch background, verify evidence, commit. Includes pitfalls from real sessions.
---

# PM orchestration playbook

Vai trò: PM viết brief, agent viết code, PM nghiệm thu. Skill này là phần "làm sao" của SOUL.

## 1. Trước khi viết brief (5 phút, không bỏ)

```bash
cd <repo> && git log --oneline -5 && git status --porcelain
```
- Đọc đúng file sẽ sửa, không đoán theo tên.
- Nếu là lỗi runtime: lấy log thật trước (`kaggle kernels logs`, `docker logs`, file log của job).
- Viết ra **một câu nguyên nhân gốc**. Không có câu đó thì chưa được giao việc.

## 2. Giao việc

```bash
commandcode -p "$(cat brief.md)" --yolo --max-turns 40 --output-format json \
  --skill /Users/huynguyen/.agents/skills/<tên-1> \
  [--skill /Users/huynguyen/.agents/skills/<tên-2>] > /tmp/t<id>.log 2>&1
```
- Chạy `background=true` + `notify_on_complete=true`. Không `sleep`, không poll.
- `--skill` là **bắt buộc** nếu muốn agent dùng skill: CommandCode không tự chọn. Cờ này **lặp lại được**, nhưng dùng **tối đa 2** — xem §3.
- Agent cạn turn → exit code 8. Khi đó: đọc phần đã làm, tự commit phần đúng, rồi giao tiếp phần còn lại bằng brief mới.

## 3. Định tuyến skill (ai dùng cái gì)

Kho: `/Users/huynguyen/.agents/skills/` (46 skill). Chia hai làn, không trộn.

**Làn PM (PM tự chạy trong Hermes, không giao):**

| Skill | Khi nào |
|---|---|
| `wayfinder` | Việc mờ, lớn hơn 1 phiên agent. Ra decision ticket trên tracker trước khi giao việc. |
| `to-spec` / `to-tickets` | Đã bàn xong, cần chốt spec rồi cắt thành ticket tracer-bullet. |
| `triage` | Ticket mới vào, cần phân loại + viết brief agent-ready. |
| `grill-me` | Người dùng muốn phản biện kế hoạch trước khi chốt. |
| `ponytail-review` | **Bắt buộc** trước khi accept diff. Trả về "cắt gì", một dòng một phát hiện. |
| `ponytail-audit` | Theo tháng, quét cả repo tìm chỗ phì. |
| `ponytail-debt` | Gom comment `ponytail:` thành sổ nợ, tránh deferral thành vĩnh viễn. |
| `retro` | Cuối phiên khó → đề xuất vá chính playbook này. |
| `handoff` | Chuyển phiên sang agent/máy khác. |

**Làn worker (giao qua `--skill`):**

| Skill | Khi nào | Không dùng khi |
|---|---|---|
| `ponytail` | Mặc định cho mọi việc code: feature, fix, refactor. Ghi mức bằng chữ: `ponytail full` / `lite` / `ultra`. | Hạ tầng, boot chain, migration dữ liệu — nó cắt bước đang cần. |
| `tdd` | Logic có rẽ nhánh, tiền, parse, hoặc bug cần test tái hiện. | Fix 1 dòng, sửa config, đổi text. |
| `diagnosing-bugs` | Bug khó, regression, "chậm từ lúc nào không rõ". | Đã biết nguyên nhân gốc. |
| `implement` | Đã có spec/ticket sẵn, chỉ cần thi công. | Ticket còn mơ hồ. |

**Cấm giao cho worker**: `triage`, `to-spec`, `to-tickets` — chúng ghi ticket, tranh quyền PM. Nếu worker cần bối cảnh thì PM dán đoạn ticket vào brief.

**Bẫy đã kiểm**: 10 skill Matt có `disable-model-invocation: true` (`ask-matt`, `wayfinder`, `to-spec`, `to-tickets`, `grill-me`, `handoff`, `implement`, `retro`, `triage`) — nạp vào thì nội dung có, nhưng agent không tự gọi. Brief phải viết đúng câu: "Theo skill `implement`, ...". Ponytail thì ngược lại: tự áp dụng mọi response khi đã nạp.

**Bẫy thứ hai**: `to-spec`/`to-tickets`/`triage`/`wayfinder` đọc `docs/agents/issue-tracker.md`. Repo thiếu file này thì chúng dừng và bảo chạy `setup-matt-pocock-skills` — mất một vòng. Kiểm trước khi giao.

## 4. Nghiệm thu (bắt buộc, theo thứ tự)

```bash
git log --oneline -3
git show --stat HEAD            # file đúng? có file lạ?
git show HEAD -- <file chính>   # sửa đúng chỗ?
pytest -q tests/                # số test không giảm
grep -n "<MARKER>" <log>        # có dấu vết chạy thật
```
Rồi chạy `ponytail-review` trên `git diff` trước khi accept: nó chỉ ra phần thừa mà `git show` không thấy.

Không có handle kiểm được (sha, URL, file, dòng log) ⇒ **chưa xảy ra**, dù agent nói gì.

Ghi biên bản vào ticket: ngày, HEAD, số đo, marker, kết luận accept/reject. Rồi `git commit`.

## 5. Pitfalls đã dính thật (đừng dẫm lại)

| Pitfall | Cách đúng |
|---|---|
| `uv venv` không có `pip` → `No module named pip` | `uv pip install --python <venv>/bin/python ...` |
| Kernel Kaggle là **script kernel một file** → sibling import chết | inline helper vào `main.py`; không `from .x import` |
| `numba.errors` không còn trong numba 0.58.1 | shim `sys.modules['numba.errors'] = numba.core.errors` **sau** khi cài devkit |
| Shim chạy quá sớm (probe import `mmdet3d.datasets` trước) | đặt shim ngay trước import đầu tiên cần nó, sau bước cài |
| `kaggle kernels output` timeout 120 s | dùng `kaggle kernels logs <slug> > /tmp/k.log` |
| Log 900–4.000 dòng làm ngập context | `CONDA_NO_PLUGINS=true python3 ~/.hermes/scripts/kernel_card.py /tmp/k.log` |
| Dataset thiếu `sweeps/` → validate chết 4.000 dòng | log giới hạn 5 dòng + `MISSING_TOTAL n=`, cho `sweeps=[]` hợp lệ |
| Config `sweeps_num: 9` + `pad_empty_sweeps: true` + sweeps rỗng | loader **nhân bản keyframe** 9 lần → 10× điểm trùng; dataset keyframe-only thì đặt `sweeps_num: 0` |
| Push kernel lặp lại: mỗi version boot lại venv + build CUDA ~10–11 phút | gộp nhiều fix vào một lần push; audit import tĩnh trước khi push |
| Nạp cả thư mục 46 skill cho worker | tối đa 2 skill/brief; còn lại dán vào brief bằng chữ |
| Giao `ponytail` cho boot chain | loại ticket đó không gán ponytail |
| Agent báo "done" | luôn `git show --stat` + `pytest` + `ponytail-review` trước khi tin |

## 6. Tooling PM đã dựng

- `~/.hermes/scripts/kernel_card.py` — nén log Kaggle thành card PASS/FAIL + marker + số đo (3 giây).
- `~/.hermes/scripts/watch_spray_train.sh` — poll kernel có hạn (~20 phút/lần), ghi `card-latest.md`, tự thoát.
- `~/.hermes/scripts/parse_klog.py` — parse marker `SMOKE_*`, `MINI_SPLIT_*`.
- `~/.hermes/scripts/find_sweeps.py`, `check_mini_meta.py` — quét file listing dataset Kaggle.

## 7. Board và trạng thái

- Board: `.scratch/<project>/STATUS.md` — bảng ticket + mục "Đang ở" + "Việc tiếp theo".
- Ticket chi tiết: `.scratch/<project>/issues/<NN>-<slug>.md` (một file một ticket, trạng thái ở dòng `**Status:** <label>` gần đầu file).
- Cập nhật board **sau mỗi nghiệm thu**, không dồn cuối ngày.
- Báo cáo cho người dùng: số đo + nguồn (`[ĐO]`, `[CODE]`, `[PAPER]`, `[CHỌN]`), nêu giới hạn, không tô hồng.

## 8. File kèm

- `templates/skill-recipes.md` — 4 recipe copy-paste (feature / bug / refactor / 1 dòng) + checklist setup repo 10 phút.