Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc đúng hai file, theo thứ tự:
1. .scratch/spray-augmentation/STATUS.md
2. .scratch/spray-augmentation/issues/15-plume-provenance.md

Làm đúng toàn bộ ticket 15 rồi commit. Đây là việc **chỉ sửa docstring/comment**, PM cần nó xong để
agent sau không đọc phải thông tin sai trong `spray/plume.py`.

Ràng buộc cứng:
- KHÔNG đổi bất kỳ giá trị số nào, không đổi logic, không đổi test. `git diff` chỉ được chạm
  comment/docstring trong `spray/plume.py`.
- Nguồn đúng để trích là `docs/plume-model-provenance.md` (đọc file đó, đừng tự suy).
- `docs/plume-model-provenance.md` chưa chắc đúng 100% — nếu bạn thấy nó mâu thuẫn với code, DỪNG và
  báo PM, đừng tự sửa file đó.
- Chạy: CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/ → phải vẫn **33 passed**.
- Commit message: lấy đúng dòng cuối mục "Việc phải làm" của ticket 15.

Báo lại ngắn: file/dòng đã sửa, số test, commit hash. Nếu không làm được vì lý do gì, nói rõ lý do và
đừng commit.