# Team A3 — hiến chương

> Lập 2026-11-19 bởi Lead. Mọi thành viên **phải đọc file này trước khi làm bất cứ gì**.
> Cập nhật lần cuối: 2026-11-19 12:20 (Asia/Saigon).

## 0. Định nghĩa "xong A3"

1. `scripts/measure_plume_size_tail.py` in **PASS cho 50 / 100 / 130 km/h** với **default config** (không truyền flag).
2. `python -m pytest tests -q` xanh (hiện **207** test).
3. `docs/measurements/a3-parameter-provenance.md` có, mọi tham số có nguồn.
4. Kiểm chứng độc lập (R3) phán `PASS BỀN`.
5. Clip v5 + contact sheet để user duyệt bằng mắt.

---

## 1. SỰ THẬT CHUNG — đọc kỹ, đây là toàn bộ hiểu biết hiện tại

### 1.1 Số hiện tại (Lead đo 2026-11-19, **default config**, tái lập được)

| km/h | det/frame | cụm/frame | p50 | mean | p95 | max | %≥50đ | A3 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 50 | 342 | 6,8 | 5 | 45,6 | 303 | 517 | 86,6 % | PASS |
| 100 | **1477** | 24,2 | 6 | 59,7 | **297** | 2974 | **87,0 %** | FAIL |
| 130 | **1541** | 12,9 | 9 | 118,8 | **689** | 3513 | **92,9 %** | FAIL |

Đích (dải static, nằm trong `REAL` của script — **cấm sửa cho vừa**):

| km/h | det/frame | cụm/frame (Δ=1,0) | p50 | p95 | %≥50đ |
|---|---:|---:|---:|---:|---:|
| 50 | 229–242 | 9,0 | 5–7 | 172–329 | 77,9–92,3 |
| 100 | 476–523 | 35,9 | 6–8 | 43–156 | 39,2–71,2 |
| 130 | 408–456 | 33,1 | 5–7 | 36–181 | 34,7–75,1 |

### 1.2 Chẩn đoán: lỗi nằm ở **kích thước đám**, không phải số đám

`det/frame ≈ (cụm/frame) × (điểm/cụm)`

| km/h | Thật | Ta | Kết luận |
|---|---|---|---|
| 50 | 236 = 9 × 26 | 342 = 7 × **50** | đám to gấp 1,9× |
| 100 | 500 = 36 × 14 | 1477 = 24 × **61** | đám to gấp **4,4×** |
| 130 | 432 = 33 × 13 | 1541 = 13 × **119** | đám to gấp **9×** |

### 1.3 Hai nguyên nhân đã xác định

**(a) Bán kính lấy sai cột.** `_CLUSTER_RADIUS_MEDIAN_BY_SPEED` đang dùng cột cắt lát **Δ=2,5 m**.
Cắt lát dày làm nhiều đám thật dính thành một chuỗi dọc tia ⇒ phình 1,6–2,1×.

| km/h | r50 Δ=1,0 | r50 Δ=2,5 | r50 Δ=6,0 | paper median e^−1,2 |
|---|---:|---:|---:|---:|
| 50 | 0,349 | 0,702 | 0,938 | 0,301 |
| 100 | 0,292 | 0,478 | 0,581 | 0,301 |
| 130 | 0,311 | 0,657 | 0,772 | 0,301 |

**QUYẾT ĐỊNH (Lead đã ký): cột Δ=1,0 m là chuẩn thức.** Ba nguồn độc lập hội tụ: Δ=1,0 (0,29–0,35);
SSPP cũ (0,31); paper (0,30). Diện tích ∝ r² ⇒ 0,48→0,29 giảm điểm/đám ~2,7×.

**(b) `streak` — cơ chế KHÔNG có trong paper.** Tôi tự thêm để nối các đám thành băng liên tục.
Ở 130 km/h xe đi 3,6 m/frame; `streak_scale=1,0` làm đám dài 3,6 m ⇒ `max = 3513` điểm/đám.
Dữ liệu thật @100 km/h **không** có đám dài vậy (`p95` = 43–156). ⇒ Phải thử **tắt streak (0,0) trước**,
chỉ bật lại nếu dữ liệu static chứng minh cần.

### 1.4 Ba lỗi dụng cụ đã phát hiện (phải sửa trước khi tin bất kỳ số nào)

| # | Lỗi | Hệ quả |
|---|---|---|
| 1 | `--radius-sigma` default **0,8** (config 0,97); `--streak-scale` default **1,0** (config 0,5) | "chạy default" không đo đúng config ⇒ mọi kết luận mặc định đều lệch |
| 2 | Caption in tiêu chí *"cụm/frame không đổi"* nhưng code **không kiểm tra** | bỏ qua một tiêu chí mà dụng cụ tuyên bố có |
| 3 | Số cũ 1097 vs mới 1477 khác nhau chỉ vì flag `--streak-scale 0,15` | dễ đọc nhầm là "kết quả đổi" |

### 1.5 QUYẾT ĐỊNH của Lead về `cụm/frame`

`cụm/frame` **không** thành tiêu chí PASS cứng (vì phụ thuộc `minPts=3` và cách merge của DBSCAN —
là artifact đo), mà thành **cờ cảnh báo**: lệch ngoài `[0,5×; 2,0×]` so với thật thì in `WARN`.
Caption phải sửa cho khớp code.

---

## 2. NHỮNG GÌ ĐÃ RÚT LẠI — đừng lặp lại

| Đã rút lại | Vì sao |
|---|---|
| Dùng SSPP (`label == 2`) làm **nguồn chọn tham số** | Vi phạm D2-chặt (ADR-0006). SSPP chỉ để **báo cáo/kiểm chứng**. Nguồn chọn tham số: paper + RoadSpray `*_static` |
| Đo trên `PlumeResult.injected` | Điểm `ring=-1` bị `spray/raycast.py:117` loại khỏi mọi tính toán ⇒ đo con số không tồn tại với detector. Phải đo `RaycastResult.detections` |
| `source_count = 2` (hai bánh xe) | Tôi tự bịa, **không có trong paper**. Đã tắt (`0`) |
| Mọi phán quyết "PASS" trước 2026-11-19 | Đo bằng dụng cụ sai ⇒ vô hiệu |

---

## 3. Vai

| Vai | Member | Task | Quyền ghi | Trạng thái |
|---|---|---|---|---|
| **R1 — instrument-fixer & converger** | `sspp-table-auditor` | **task-8** | `spray/`, `tests/`, `scripts/measure_plume_size_tail.py`, `docs/measurements/plume-a3-diagnosis.md` | ▶ **chạy ngay** |
| **R2 — provenance-auditor** | `paper-archaeologist` | **task-11** | `docs/measurements/a3-parameter-provenance.md`, `.scratch/` | ▶ **chạy ngay** |
| **R3 — independent-verifier** | `power-analyst` | **task-12** (chờ) | `.scratch/roadspray-cal/tasks/R3-verification.md`, `.scratch/tmp/` | ◐ prep ngay, chấm điểm sau khi R1 freeze |
| **R4 — visual-renderer** | `visual-inspector` | **task-10** (chờ) | `scripts/visualize_plume_vs_real.py`, `.scratch/` | ◐ prep ngay, render sau khi R1 freeze |
| **Lead** | `lead` | task-8 (review) | ADR, commit, quyết định | ▶ |

**Ranh giới ghi là tuyệt đối.** R1 và R4 cùng đụng `.scratch/` → R1 dùng `.scratch/tmp/`, R4 dùng
tiền tố `.scratch/plume_vs_real_*`.

---

## 4. Trình tự A3 (R1) + cửa kiểm

| # | Việc | Cửa kiểm |
|---|---|---|
| 1 | Sửa 3 lỗi dụng cụ (§1.4) + thêm cờ cảnh báo `cụm/frame` (§1.5) | chạy default = chạy config; chạy 2 lần cùng seed ra cùng số |
| 2 | Dựng bảng bán kính 9 tốc độ từ cột Δ=1,0; `RADIUS_SIGMA` theo `rsig` Δ=1,0 | điểm/đám @100 giảm ~2,7× |
| 3 | Đo lại → **BÁO LEAD** (điểm quyết định, chưa được đụng `spawn_scale`) | — |
| 4 | Nếu `det` còn >1,5×: **tắt streak (0,0)** trước; chỉ sau đó mới chỉnh `spawn_scale`/số đám | `det ∈ [0,7; 1,5]×`; `cụm/frame` trong `[0,5×; 2,0×]` |
| 5 | Cập nhật `docs/measurements/plume-a3-diagnosis.md` (bảng trước/sau + nguồn mọi tham số) | 207 test xanh |

**Bước 3 là điểm báo cáo bắt buộc.** Sau bước 4 nếu vẫn không hội tụ ⇒ **DỪNG, báo Lead**, không tự
thêm cơ chế mới (bài học: 100 % cơ chế tôi tự thêm đều bị user bắt lỗi).

---

## 5. Luật giao tiếp

- **Claim task trước khi làm**: `team_task_get` → `team_task_update(action="claim", expected_revision=<rev>)`.
- **KHÔNG `git commit`.** Lead review + commit. Cứ để thay đổi trong working tree.
- Báo Lead (`send_message target="lead"`) khi: (a) xong, (b) bị chặn >20 phút, (c) phát hiện spec/Lead sai.
- Báo cáo **<150 dòng**, kèm **số cụ thể + lệnh đã chạy**. Không dán log dài, không nói "có vẻ ổn".
- Không sửa file ngoài quyền ghi của mình. Không xoá file ngoài workspace.
- Không dùng lệnh `timeout` (macOS không có).
- Python: `CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python <script>`
  (máy **không** có mmcv/mmdet/mmdet3d; torch 2.2.2 CPU, numpy 1.26).
- File chưa track của user (`scripts/{audit_*,diag_*,probe_*}.py`) — **đừng sửa, đừng xoá**.
- Trung thực tuyệt đối: không suy ra kết quả chưa đo. Nếu phải chọn một số không có nguồn, ghi nhãn
  `giả định kỹ thuật` và báo Lead.

## 6. Ghi chú cho kiểm định bằng MẮT (bài học 2026-11-19)

Agent vision dùng model `zai-glm-5-3-flash` qua provider mistral, và provider này **từ chối request
có > 8 ảnh** (`Total number of images exceeds the maximum allowed of 8`). Một subagent kiểm định
bằng mắt đã chết vì gửi 12 PNG một lượt.

⇒ Sản phẩm cho mắt người/máy phải là **một ảnh contact sheet duy nhất** (grid nhiều ô trong 1 file),
không phải 12 ảnh rời. Nếu buộc phải gửi rời thì chia ≤ 8 ảnh mỗi request.

## 7. Bối cảnh dự án (1 đoạn)

Dự án kiểm chứng: augmentation **plume spray** tổng hợp có làm detector **3DOD** (BEVFusion, LiDAR-only)
tốt hơn trên SemanticSpray++ (SSPP) không. A3 là cổng đầu tiên trong 6 cổng A→F: generator phải khớp
thống kê spray **thật** thì kết quả train sau này mới diễn giải được. A3 PASS **không** chứng minh
augmentation có ích — việc đó là cổng C. Chi tiết: `docs/adr/0006-*.md`, `.scratch/roadspray-cal/plan.md`.
