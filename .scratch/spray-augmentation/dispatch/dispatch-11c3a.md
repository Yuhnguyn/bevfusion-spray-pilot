# 11-c3a: build pkl từ danh sách token có sẵn

HEAD: 9e3b4dd  Nhánh: main  Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
Skill: tdd (/Users/huynguyen/.agents/skills/tdd/SKILL.md)

## Mục tiêu

`scripts/make_mini_split.py` hiện chỉ chọn token ngẫu nhiên theo seed. Cần thêm đường
"tôi đã có danh sách token, chỉ dựng pkl" để kernel eval chấm đúng 196 frame mà
`scripts/make_eval_split.py` vừa chọn ra.

## Việc phải làm

1. Thêm cờ `--tokens-json <path>`: file JSON do `make_eval_split.py` ghi, dạng
   `{"frames": [{"sample_token": ..., "scene": ...}, ...]}` — đọc key `frames`, lấy
   `sample_token`, giữ nguyên thứ tự.
   - Khi có cờ này: bỏ qua bước chọn ngẫu nhiên, dựng info cho đúng các token đó.
   - Token không tồn tại trong `nusc.sample` ⇒ in `TOKENS_MISSING n=<số>` và exit 1.
   - Không đụng hành vi cũ khi cờ vắng mặt.
2. Tách phần dựng info thành hàm thuần nhận danh sách token, để test được mà không cần
   devkit: `build_infos_for_tokens(tokens, build_info)` (dependency injection).
3. In `MINI_SPLIT_TOKENS n=<số> splits=<json đếm theo split>` sau khi dựng xong, và vẫn
   in `MINI_SPLIT_OK n=<số>` như cũ để `main.py` không phải sửa.
4. Test mới trong `tests/test_make_mini_split_tokens.py`:
   - đọc đúng thứ tự và số lượng token từ JSON mẫu
   - thiếu token ⇒ trả danh sách missing, không im lặng
   - hàm dựng info gọi `build_info` đúng số lần, đúng token
   KHÔNG viết test cần torch/nuscenes.

## Ràng buộc

- Chỉ sửa `scripts/make_mini_split.py`, thêm `tests/test_make_mini_split_tokens.py`.
- Không chạm `kaggle/`, `spray/`, `third_party/`, `kaggle/train/task_args.txt`.
- Chạy `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/pytest -q tests/` phải xanh toàn bộ
  (hiện 165 passed, 4 skipped) rồi commit một commit duy nhất.
- Không push kernel, không sync dataset.