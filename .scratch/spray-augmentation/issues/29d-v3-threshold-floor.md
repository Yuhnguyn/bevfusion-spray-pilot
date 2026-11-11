# 29d-v3 — Ngưỡng cổng phải là sàn đóng băng, không được tự nới

Trạng thái: `ready-for-agent`
Liên quan: 29d (gate cal vs held-out), 29d-v2 (`09cd650`)
Tạo: 2026-11-11, sau khi gate v2 PASS 7/7 nhưng PM phát hiện ngưỡng hiệu dụng bị nới.

## 1. Triệu chứng [ĐO]

Lần đo v2 (`/tmp/m29dv2.log`, 12.080 frame, 3.117 s) in ra bảng gate với cột
"ngưỡng" **khác** sàn đóng băng:

| id | Δ cal vs held-out | sàn đóng băng [CODE] | ngưỡng v2 in ra | bị nới |
|---|---:|---:|---:|---:|
| G1 noise/frame | −2,1 % | 15 % | **67,0 %** | 4,5× |
| G2 cụm/frame | −0,8 % | 20 % | 27,3 % | 1,4× |
| G3 điểm/cụm | 0,0 % | 20 % | 20,0 % | — |
| G4 `r_range/r_extent` | +0,002 | 0,10 | 0,10 | — |
| G5 p95\|y\| | +4,0 % | 15 % | 15,0 % | — |
| G6 chiều cao p50 | −0,014 m | 0,20 m | 0,358 m | 1,8× |
| G7 elevation | −0,160° | 0,50° | 0,876° | 1,8× |

Verdict v2 (`PASS` 7/7) **không sai** vì mọi Δ đều dưới sàn thật, nhưng con số
in ra khiến báo cáo không còn so sánh được với v1 và che mất regression trong
tương lai.

## 2. Nguyên nhân gốc [CODE]

Hai lỗi cộng lại:

1. `spray/semantic_split.py:565, 572, 585` tính
   `threshold = max(sàn, 2 × Δ_halfsplit)` ⇒ **nhiễu càng lớn thì ngưỡng càng
   rộng**, tức cổng tự nới để dễ qua.
2. `scripts/semantic_spray_split.py:148-150` chia `cal` thành `cal_a`/`cal_b`
   bằng `index % 2` trên danh sách `cal_paths` — danh sách này **đã sắp theo
   `itr_after_water`** sau 29d-v2. Với 3 scene/ô (`w = 1,3,5` hoặc `2,4,6`),
   parity cho `cal_a = {w1, w5}` và `cal_b = {w3}` ⇒ hai nửa lệch nhau về độ
   tươi nước. Hệ quả: `Δ_halfsplit` không đo nhiễu lấy mẫu mà đo **gradient
   nước**, phình từ **5,4 % (v1) lên 33,5 % (v2)**.
3. `halves()` ở `spray/semantic_split.py:427` là **dead code** — không nơi nào
   gọi, và nó cũng chia xen kẽ trên danh sách đã sắp.

## 3. Yêu cầu sửa

### 3.1 `halves()` thành hàm thật, stratify theo `(group, itr_after_water)`

- Một cài đặt duy nhất, ở `spray/semantic_split.py`; script gọi lại, **không**
  để bản thứ hai inline.
- Vào: danh sách scene kèm metadata (`group`, `itr_after_water`, `rel_path`).
- Trong từng stratum `(group, itr_after_water)`: sort theo `rel_path`, chia xen
  kẽ vào A/B.
- Ra: hai danh sách `cal_a`, `cal_b`; **không RNG**, kết quả không phụ thuộc
  thứ tự đầu vào.
- Hệ quả kỳ vọng: `Counter(itr_after_water)` của A và B bằng nhau trong từng
  group (lệch ≤ 1 scene toàn cục cho mỗi mốc, do tổng lẻ).

### 3.2 Ngưỡng luôn là sàn đóng băng

- `threshold = spec.floor_rel` hoặc `spec.floor_abs` — **bỏ hẳn `max(...)`**.
- `Δ_halfsplit` vẫn tính và vẫn in, nhưng chỉ là **chẩn đoán**; đổi tiêu đề cột
  thành `Δ_halfsplit (chẩn đoán)`.
- Nếu `observed > 2 × Δ_halfsplit` thì thêm note `vượt sàn nhiễu nội tại`
  — **không đổi verdict**.
- Verdict chỉ phụ thuộc `observed <= threshold`; `gate` (thiếu dữ liệu) vẫn
  ép FAIL như hiện tại.

### 3.3 Text trong báo cáo

`scripts/semantic_spray_split.py:497` và `:550` đang viết "Ngưỡng hiệu dụng =
max(sàn, 2 × Δ_halfsplit)" — sửa thành: ngưỡng = sàn đóng băng, `Δ_halfsplit`
chỉ để tham khảo. Không được đổi bất kỳ con số sàn nào.

## 4. Test bắt buộc (≥ 4 test mới)

1. `halves` cân bằng: dựng 3 scene/ô cho 2 group ⇒ `Counter(w_itr | cal_a) ==
   Counter(w_itr | cal_b)` trong từng group; tổng lệch ≤ 1.
2. `halves` deterministic: `reversed`, xoay vòng, `shuffled` đầu vào ⇒ cùng
   kết quả.
3. **Ngưỡng không nới**: metrics giả có `cal_a` lệch `cal_b` rất lớn
   (`Δ_halfsplit = 50 %`), `cal` vs `held-out` lệch 1 % ⇒ `threshold == 0.15`
   (sàn G1), verdict PASS.
4. **Chống tái phát**: `observed = 3 × sàn` với `Δ_halfsplit` khổng lồ ⇒
   verdict **FAIL** (nếu code còn `max(...)` thì test này đỏ).

## 5. Cấm

- Đổi 7 con số sàn, đổi luật chia `cal`/`held-out`, đổi `cluster_angular`,
  đổi `frames_per_scene` mặc định.
- Chạy `--measure` full (PM chạy, ~52 phút).
- Tự commit.

## 6. Smoke bắt buộc (agent tự chạy, dán nguyên output)

```
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/semantic_spray_split.py --build
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/semantic_spray_split.py --verify
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/semantic_spray_split.py --measure --limit-scenes 6 --frames-per-scene 5
```

Kỳ vọng: `SPLIT_BUILT cal=104 heldout=103`, `SPLIT_VERIFY_OK`, và bảng gate có
`ngưỡng` **đúng bằng sàn** (G1 15,0 %, G6 0,200, G7 0,500).

## 7. Nghiệm thu của PM

- `pytest -q tests/` ≥ **264 passed, 4 skipped** (260 + ≥4).
- Bảng gate trong báo cáo: cột ngưỡng khớp sàn từng dòng.
- `Δ_halfsplit` sau khi stratify phải **giảm mạnh** so với 33,5 % — nếu vẫn
  > 20 % thì báo lại, không tự sửa tiếp.