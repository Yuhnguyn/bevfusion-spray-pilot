Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`
2. `.scratch/spray-augmentation/issues/22-fix-count-and-docs.md` ← **nguồn đúng, làm đúng ticket này**
3. `spray/plume.py` (hàm `inject_plume` dòng ~152–280, `cluster_count_for_speed` ~123, `lifetime_time_constant` ~139)

Làm đúng 3 việc trong ticket, không lan rộng.

Tóm tắt việc 1 (quan trọng nhất): số cụm hiện bị **tính hai lần** suy giảm. Công thức
`(0,2*wfh+0,1)*(v_kmh-50)` là số cụm **sinh mỗi chu kỳ 0,1 s**; code lại dropout thêm
`age ~ U(0,4T)` → ở 80 km/h chỉ còn 0,73 cụm/frame, trong khi đo thật 17,06.
Sửa: nhân hệ số tích luỹ `K = sum_{k=0..4T/dt} exp(-k*dt/T)`, với `dt = 0,1`, `T = 0,2` → `K = 2,51`,
và **bỏ hẳn** bước dropout khỏi `inject_plume`. `K` phải tính từ hằng số, không hard-code nếu
`T` đổi theo tốc độ (ở v lớn `T` hơi tăng nên `K` hơi lớn hơn 2,51 — tính đúng công thức).

CẤM:
- không nâng `wfh` hay hệ số nào để khớp đúng 17,06 — chênh còn lại ghi vào docs là do `wfh` chưa biết
- không đụng `mit/`, `third_party/`
- không đổi `PlumeConfig` ngoài `lifetime_*`
- không xoá test cũ; test nào đổi hành vi thì sửa đúng kỳ vọng kèm comment lý do
- không bịa số: nếu đo khác ticket thì báo, không sửa ticket

Test chuẩn: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥55 passed**

Commit message đúng dòng cuối ticket. Xong thì in: bảng 6 tốc độ (sinh / K / visible), bảng mật độ
3 box, và số test passed.