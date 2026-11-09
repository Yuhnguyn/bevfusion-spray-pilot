**Vai:** PM điều phối. Brief → giao agent → verify bằng bằng chứng → commit. Code sản phẩm do agent viết, PM không tự viết.
§
**Agent CLI:** commandcode `-p "$(cat brief)" --yolo --max-turns 40 --output-format json`; `--skill` lặp được, tối đa 2/brief (trỏ cả thư mục 46 skill = loãng). 10 skill Matt `disable-model-invocation: true` → brief phải nêu tên; ponytail tự áp dụng, mức ghi bằng chữ. EXIT=8 = cạn turn → commit phần đúng rồi giao brief nối. opencode: `--model alibaba-token-plan/deepseek-v4.1-flash-1017`.
§
**Verify bắt buộc:** `git show --stat HEAD` → `git diff` → `pytest -q tests/` → grep marker; rồi `ponytail-review` trên diff. Agent báo "done/uploaded" mà không có handle kiểm được = chưa xảy ra.
§
**Job dài:** `background=true` + `notify_on_complete=true`; KHÔNG sleep/poll thủ công.
§
**Tooling PM:** `~/.hermes/scripts/kernel_card.py` (nén log Kaggle → card PASS/FAIL, ~3s), `watch_spray_train.sh` (poll có hạn ~20 phút), `parse_klog.py`, `find_sweeps.py`, `check_mini_meta.py`. Draft/brief ở `~/.hermes/drafts/`.
§
**Projects:** spray pilot `~/projects/bevfusion-spray-pilot` (board `.scratch/spray-augmentation/STATUS.md`, kernel Kaggle `nguynhuy9669/bevfusion-spray-train`, log bằng `kaggle kernels logs` vì `kernels output` timeout 120s); P-135 DriverGuard (skill `driverguard-project`, nhánh `huyng`, worktree `~/orca/workspaces/P-135/gurnard`); VinUni labs `~/Documents/VinUni_Lab/`; KLTN VAR/VECM (skill `var-vecm-kltn-pipeline`).
§
**Env:** script python ngoài cần `CONDA_NO_PLUGINS=true`; `/tmp` dọn ~12h → artifact quan trọng để `~/.hermes/drafts/`; đĩa local chỉ còn ~14 GB (không giải nén blob lớn).
§
**Bài học kernel Kaggle:** mỗi lần push phải boot lại venv + build CUDA ~10–11 phút → gộp nhiều fix một lần push, audit import tĩnh trước. Script kernel là một file, không import sibling.
§
**Dọn/xoá file:** ping duyệt trước; so mtime + `git log`.
§
**Định tuyến skill:** PM tự chạy wayfinder/to-spec/to-tickets/triage/ponytail-review/ponytail-audit/ponytail-debt/retro. Worker chỉ nhận ponytail, tdd, diagnosing-bugs, implement. Cấm triage/to-tickets/to-spec cho worker; cấm ponytail cho boot chain. Recipe: playbook §3 + templates/skill-recipes.md.