# CDF cự ly detection vs RoadSpray `*_static` — lần đo đầu (2026-11-25)

> ⚠️ **ĐÃ SỬA HAI LỖI SO VỚI BẢN COMMIT `91773bb`.** Bản đầu ghi CDF10 thật =
> 71,1 / 36,0 / **0,6** % và kết luận "generator sinh 12,8 % detection trước mặt đuôi xe,
> vi phạm vật lý". Cả hai **sai vì lỗi phương pháp** — chi tiết §0. Số đúng ở §1–§3.

## 0. Hai lỗi của bản đầu, và vì sao

### Lỗi 1 — gộp frame ở mọi cự ly xe rồi so CDF

Kịch bản static quét xe đích `car_range` từ **12,5 m → 169 m** trong cùng một bag. Vài
frame đầu (xe còn gần) chiếm phần lớn số điểm: bag 50 km/h có 1 679 điểm ở frame 11 nhưng
chỉ 41 điểm ở frame 16. Gộp mọi frame rồi tính CDF là **trộn những cự ly khác nhau** —
CDF10 = 71 % ở 50 km/h chỉ nói "frame xe còn gần thì điểm ở gần", không nói "plume thật nằm
sát cảm biến". Vế sinh có `car_x` tăng đều 20 → 203 m nên mỗi dải cự ly có số frame bằng
nhau ⇒ **so gộp là so hai thiết kế lấy mẫu khác nhau**.

### Lỗi 2 — "0 % trước mặt đuôi" của vế thật là **tautology**, không phải số đo

Trong `run_real_static` (`measure_cdf_over_range.py:270–271`):

```python
behind = (residual & spray_like & (depth >= 0.0) & (depth < 60.0))
masked = (behind & ...)
sel = np.nonzero(masked)[0]
```

`depth >= 0.0` được áp **trước** khi histogram hoá ⇒ `n_ahead_of_rear` của vế thật **luôn
bằng 0 theo cấu trúc**. Vế sinh tính `depth_hist` trên **toàn bộ** detection
(`measure_cdf_over_range.py:611`), không lọc trước. Vậy "thật 0 % vs sinh 12,8 %" là **so
một đại lượng đã lọc với một đại lượng chưa lọc**. Con số 12,8 % của vế sinh là thật, nhưng
chưa có vế thật cùng định nghĩa ⇒ **kết luận "vi phạm vật lý" rút lại**.

## 1. `[ĐO]` Độ dài đuôi plume — thước phân biệt được hai vế

Quantile của `depth` sau mặt đuôi xe đích (m), tách theo `car_range`:

| km/h | `car_range` | THẬT nfr / n_det | p50 | p90 | p95 | p99 | SINH nfr / n_det | p50 | p90 | p95 | p99 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | [20,40) | 32 / 3 193 | 0,5 | 4,5 | 6,5 | 10,5 | 30 / 1 539 | 0,5 | 1,5 | 1,5 | 2,5 |
| 100 | [20,40) | 14 / 14 070 | **17,5** | 24,5 | 26,5 | 29,5 | 14 / 1 605 | **2,5** | 8,5 | 9,5 | 12,5 |
| 130 | [20,40) | 5 / 7 279 | **20,5** | 27,5 | 29,5 | 32,5 | 10 / 614 | **3,5** | 8,5 | 9,5 | 11,5 |
| 50 | [40,80) | 61 / 37 | 45,5 | 57,5 | 59,5 | 59,5 | 56 / 893 | 1,5 | 1,5 | 2,5 | 3,5 |
| 100 | [40,80) | 28 / 11 003 | **34,5** | 50,5 | 54,5 | 58,5 | 28 / 1 370 | **8,5** | 21,5 | 25,5 | 34,5 |
| 130 | [40,80) | 25 / 23 139 | **38,5** | 53,5 | 56,5 | 58,5 | 22 / 582 | **14,5** | 29,5 | 35,5 | 42,5 |

**Đây là thước mà hai vế cùng định nghĩa và cùng lấy mẫu** (cả hai đều đo depth sau mặt
đuôi, đều tách theo dải `car_range`). Kết luận:

- Ở 100–130 km/h, đuôi plume thật dài **gấp 3–7 lần** generator: p95 = 26–56 m so với
  9,5–35,5 m. **Đuôi hụt là bệnh chính, và nó nặng hơn ở 100 km/h.**
- Ở 50 km/h thì ngược: thật p95 = 6,5 m (car 20–40) trong khi sinh 1,5 m — generator
  **ngắn hơn** cả ở tốc độ thấp.
- Trong dải [40,80), thật 100 km/h có p50 = 34,5 m — nghĩa là **nửa số điểm nằm xa hơn
  34 m sau đuôi xe**. Generator chỉ 8,5 m.

## 2. `[ĐO]` Vì sao CDF10 của vế sinh = 0 trong khi vế thật 27–54 %

Không phải bug raycast. Hai ràng buộc cộng lại:

- Vùng **sinh** cụm bắt đầu cách xe ≥ 18 m (`measure_plume_size_tail.py`).
- Miền paper cắt `‖pos‖ − r ≥ 2,5 m`.

`raycast_frame` sinh detection dọc **tia** trên quả cầu ⇒ cụm ở 20–25 m cho điểm ở 20–25 m.
Muốn có detection < 10 m thì **phải có cụm ở < 10 m** — tức đổi **vùng sinh**, không phải
đổi raycast. Đây là hệ quả thiết kế, không phải tham số sai.

## 3. `[ĐO]` Kịch bản following (A3-V) — CDF và KS

Từ `following_all` (360 frame, 12 scene), `|p|` 0–50 m:

| lớp | band | THẬT CDF10 | p50 | SINH CDF10 | p50 | KS |
|---|---|---:|---:|---:|---:|---:|
| crafter | 50–70 | 72,1 % | 7,9 | 18,5 % | 17,5 | **0,625** |
| crafter | 80–110 | 61,4 % | 8,7 | 71,0 % | 5,7 | 0,277 |
| crafter | 120–130 | 73,1 % | 7,3 | 81,5 % | 3,3 | 0,464 |
| golf | 50–70 | 52,2 % | 9,7 | **0,1 %** | 19,7 | **0,848** |
| golf | 80–110 | 52,4 % | 9,7 | 57,8 % | 8,4 | 0,202 |
| golf | 120–130 | 58,3 % | 8,9 | 82,6 % | 3,8 | 0,478 |

**Hướng lệch đảo theo tốc độ** — đây là điểm quan trọng nhất cho việc hiệu chuẩn:

- 50–70 km/h: generator **quá xa** (p50 17,5–19,7 m vs thật 7,9–9,7). KS 0,625–0,848.
- 120–130 km/h: generator **quá gần** (p50 3,2–3,8 m vs thật 7,3–8,9). KS 0,46–0,48.

⇒ Một hệ số vô hướng **không thể** sửa cả hai chiều. Đây là bằng chứng định lượng cho dự
đoán ở ADR-0006 §5.7 ("một hệ số vô hướng không thể phủ dải 0,86 → 16,92×").

## 4. Số thô

`%TEMP%/cdfprobe/{real_static,gen_static,following_all}.jsonl`, `summary_cdf.json`.
