Bạn làm ticket 23 trong repo /Users/huynguyen/projects/bevfusion-spray-pilot (branch main).

ĐỌC THEO THỨ TỰ, không đọc file khác:
1. AGENTS.md (nếu có) — quy ước repo.
2. .scratch/spray-augmentation/issues/23-radius-cap-and-naming.md — NGUỒN ĐÚNG, 4 mục.
3. spray/plume.py (phần PlumeConfig + hàm sinh cụm).
4. docs/plume-model-provenance.md (để biết chèn mục mới vào đâu).

PHẠM VI — chỉ 4 mục trong ticket, không làm thêm:

1. `cluster_radius_bounds_m`: (0.10, 1.50) → (0.10, 1.00). Thêm 1 test mới: rút 20.000 lần,
   assert max(r) <= 1.0 và tỉ lệ chạm trần trong khoảng [0.05, 0.09].
2. Đổi tên field/cột 5 `time_lag` → `ring` trong spray/plume.py (cả chỗ khai báo và chỗ gán).
   Giá trị vẫn 0.0. Comment ghi: "điểm tổng hợp gán ring 0; không dùng cho occlusion".
   Sau khi sửa, `grep -rn time_lag spray/` phải rỗng.
3. docs/plume-model-provenance.md: thêm đúng 2 mục (a) và (b) như ticket mô tả, kèm nhãn
   [CHỌN] cho (a) và [CODE] cho (b). Không viết lại các mục đang có.
4. docs/plume-model-provenance.md: thêm mục hạn chế "self-spray chưa mô phỏng" như ticket mô tả.

RÀNG BUỘC:
- KHÔNG đổi bất kỳ tham số nào khác của PlumeConfig (points_per_cluster_median, cluster_radius_median_m,
  wfh, K, lifetime, ngưỡng tốc độ). Muốn đổi thì DỪNG, báo lại kèm số.
- KHÔNG sửa mit/bevfusion, third_party/, data/.
- KHÔNG sửa STATUS.md — PM tự cập nhật board.
- Không bịa số. Mọi số trong docs phải là số đã đo hoặc số đã có trong ticket.

KIỂM TRA TRƯỚC KHI COMMIT:
- CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/  → phải >= 57 passed
  (hiện tại 56). Nếu giảm hoặc fail: sửa, không commit.
- python3 -c script in ra 5 giá trị cluster_radius mẫu + tỉ lệ chạm trần (đo thật, ~20.000 lần rút).
- grep -rn "time_lag" spray/ → rỗng.

COMMIT đúng 1 commit, message đúng dòng này:
fix(plume): cap cluster radius at 1.0 m per dee.cpp:528; rename col5 to ring; document K/T

BÁO CÁO CUỐI (ngắn): đã sửa gì, số đo tỉ lệ chạm trần, pytest bao nhiêu passed, commit sha, có gì bất thường.
Nếu bị chặn: dừng, báo rõ lý do + log, không tự đổi pin/version.