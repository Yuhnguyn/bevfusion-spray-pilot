# 15: Sửa provenance của `PlumeConfig` (docstring + trích dẫn)

**Trạng thái:** ready-for-agent
**Chủ:** CommandCode. PM: Hermes.
**Loại:** chỉ sửa comment/docstring và một dòng trích dẫn. **Không đổi hành vi, không đổi tham số.**

## Vì sao có ticket này

PM từng nói "số cụm tăng theo tốc độ không có trong paper Linnhoff". **Sai.** Paper có, ở §III
*Cluster Generation*: số cụm sinh ra mỗi timestep là hàm tuyến tính của tốc độ, lớp xe và độ dày màng
nước (Fig. 4, đo cho VW Crafter). Code hiện tại đúng là theo cấu trúc đó, chỉ khác hằng số. Docstring
trong `spray/plume.py` đang xếp `clusters_at_speed_bounds` vào nhóm "[CHỌN]" không nguồn, gây hiểu sai.

Bản đồ nguồn đầy đủ: `docs/plume-model-provenance.md` (đã viết, là nguồn đúng).

## Việc phải làm

1. Trong `spray/plume.py`, sửa docstring của `PlumeConfig` (khoảng dòng 11–24) và comment của
   `clusters_at_speed_bounds` (khoảng dòng 34–38):
   - Ghi rõ: **dạng hàm tuyến tính theo tốc độ lấy từ Linnhoff §III + Fig. 4**; hằng số (2→8) neo theo
     SemanticSpray median 5 dense clusters/frame.
   - Ghi rõ hai chiều bị gộp ở v1: lớp xe, độ dày màng nước.
   - Thêm dòng `Xem docs/plume-model-provenance.md` ở đầu docstring.
2. Không sửa bất kỳ giá trị số nào, không sửa logic, không đổi test.
3. Chạy `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` — phải vẫn 29 passed.
4. Commit: `docs(plume): correct provenance of cluster count (Linnhoff Fig. 4), link provenance map`.

## Xong khi

- `git diff` chỉ chạm comment/docstring trong `spray/plume.py`.
- Test vẫn 29 passed.
- Không có chỗ nào trong repo còn nói cluster count "không có nguồn paper".

## Không làm

- Không parameterize theo lớp xe / màng nước (đó là ticket riêng nếu PM quyết định tiến gần paper).
- Không thêm attenuation/occlusion (ADR-0002, để v2).
- Không sửa `docs/plume-model-provenance.md` trừ khi phát hiện sai số — báo PM trước.