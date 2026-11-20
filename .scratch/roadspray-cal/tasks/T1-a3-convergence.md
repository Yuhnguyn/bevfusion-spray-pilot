# T1 — A3 hội tụ: bán kính Δ=1,0 m + hiệu chuẩn spawn_scale

> Worker: `plume-calibrator` (subagent). Lead review + commit. Viết 2026-11-19.

## Bối cảnh
Dự án kiểm chứng: augmentation **plume spray** tổng hợp có làm detector **3DOD** (BEVFusion
LiDAR-only) tốt hơn trên SemanticSpray++ (SSPP) không. Generator `spray/` lấy tham số từ
paper Linnhoff 2022 (arXiv 2212.08558) + đo trên **RoadSpray `*_static`**.

Bước A3 = làm thống kê cụm spray của generator khớp dữ liệu thật, đo bằng
`scripts/measure_plume_size_tail.py` (raycast VLP-32C → DBSCAN góc eps 0,7° / minPts 3 →
so dải đích).

Hiện trạng: 50 km/h PASS; 100 km/h det 1097 (đích 476–523); 130 km/h det 1102 (đích 408–456).

## Quyết định của Lead (đã chốt — KHÔNG bàn lại, không xin phép)
Bảng bán kính trong `spray/plume_state.py::_CLUSTER_RADIUS_MEDIAN_BY_SPEED` đang lấy từ cột
bề dày lát **Δ=2,5 m**, cột đó bị thổi phồng do chain-merging dọc tia. Cột **Δ=1,0 m** là
chuẩn thức. Nguồn số: `.scratch/roadspray-cal/tmp/a3_targets_static.json`, key `"{speed}_{Δ}"`,
field `r50` / `rsig` / `cpf` / `ppf` / `share` / `p95` / `p50` / `mean`.

| km/h | r50 Δ=1,0 | r50 Δ=2,5 | r50 Δ=6,0 | paper median e^-1,2 |
|---|---:|---:|---:|---:|
| 50 | 0,349 | 0,702 | 0,938 | 0,301 |
| 100 | 0,292 | 0,478 | 0,581 | 0,301 |
| 130 | 0,311 | 0,657 | 0,772 | 0,301 |

Ba nguồn độc lập trùng nhau (Δ=1,0; SSPP cũ 0,31; paper 0,30) ⇒ Δ=1,0 đúng.

## Việc phải làm
1. Dựng lại **toàn bộ 9 tốc độ (50→130)** của `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` từ cột Δ=1,0.
2. `RADIUS_SIGMA`: 0,97 (từ Δ=2,5) → theo `rsig` cột Δ=1,0 (≈0,71–0,75). Ghi rõ cách quy đổi.
3. Hiệu chuẩn `spawn_scale` / `streak_scale` (và cột cluster-count nếu cần) để cả 3 tốc độ PASS.
   Cách làm: sweep bằng CLI flag trước (`--spawn-scale`, `--streak-scale`, `--radius-sigma`),
   tìm giá trị rồi mới bake vào default của `PlumeStateConfig` / module constant.
4. Nếu phải dùng `spawn_scale` phụ thuộc tốc độ: được, nhưng phải **đơn điệu, có lý do vật lý**,
   và ghi nhãn "giả định kỹ thuật" (không phải số từ paper/static).

### Dự đoán của Lead — kiểm chứng, đừng tin mù
Bán kính 0,48→0,29 làm diện tích cầu giảm ~2,7×, nên det/frame @100 km/h có thể tự rơi về
400–600. Nếu KHÔNG như vậy, báo lại ngay kèm số.

## Đích (nằm trong `REAL` của script — KHÔNG được sửa để "cho vừa")
| km/h | det | share % | p95 | p50 |
|---|---:|---:|---:|---:|
| 50 | 229–242 | 77,9–92,3 | 172–329 | 5–7 |
| 100 | 476–523 | 39,2–71,2 | 43–156 | 6–8 |
| 130 | 408–456 | 34,7–75,1 | 36–181 | 5–7 |

## RÀNG BUỘC
- **D2-chặt:** mọi tham số generator phải từ RoadSpray `*_static` hoặc paper. SSPP (`label==2`)
  chỉ để báo cáo/kiểm chứng, TUYỆT ĐỐI không dùng chọn tham số.
- Không sửa ngưỡng PASS; không sửa `scripts/measure_plume_size_tail.py` ngoài comment/nhãn nguồn.
- Không ghi vào `scripts/sspp_infer.py`, `kaggle/`, `scripts/visualize_plume_vs_real.py`.
- Giữ chữ ký public API: `inject_plume_stateful`, `PlumeConfig`, `PlumeStateConfig`
  (worker khác đang code theo chúng).
- **KHÔNG `git commit`.** Không xoá file ngoài workspace. Không dùng lệnh `timeout` (macOS).
- File chưa track của user: `scripts/{audit_*,diag_*,probe_*}.py` — đừng sửa, đừng xoá.
- Python: `CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python <script>`

## ACCEPTANCE
1. `scripts/measure_plume_size_tail.py` in **PASS cho 50 / 100 / 130 km/h với default config**
   (không truyền flag).
2. `python -m pytest tests -q` xanh (hiện **207** test).
3. `docs/measurements/plume-a3-diagnosis.md` cập nhật: bảng trước/sau, lý do Δ=1,0, mọi tham
   số kèm nguồn (static / paper / giả định kỹ thuật).
4. `docs/measurements/roadspray-static-clusters-by-speed.md` thêm ghi chú: cột Δ=1,0 là cột
   chuẩn thức, các cột Δ khác là artifact chain-merge.

## BÁO CÁO CHO LEAD (<150 dòng, không dán log dài)
1. Bảng 3 tốc độ: det / share / p95 / p50 generator vs dải → PASS/FAIL.
2. Tham số đã đổi: tên, cũ → mới, **nguồn**.
3. `pytest` pass/fail count. 4. Chỗ còn phải đoán + rủi ro. 5. Đường dẫn doc đã sửa.
