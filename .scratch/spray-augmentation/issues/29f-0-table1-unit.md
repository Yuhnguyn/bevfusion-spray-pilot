# 29f-0 — Câu hỏi phụ: Bảng 1 đếm gì, và A1 đang so cái gì

Type: research
Status: **closed — A1 là tiêu chí SAI, phải thay**
Owner: PM (không giao agent)

## Trả lời câu hỏi phụ

**Bảng 1 đếm cụm DBSCAN trên điểm thật.** Xác nhận từ `docs/measurements/semantic-spray-clusters-by-speed.md`
§Phương pháp:

> Toán tử cụm: DBSCAN trên mặt phẳng `(azimuth, elevation)`, `eps = 0,7°`, `minPts = 3`,
> elevation snap `0,333°`, azimuth wrap 360°. Điểm được đếm: `label == 2`.

## A1 đang so cái gì — và nó sai

`scripts/measure_29ec.py:387–417`, hàm `render_acceptance`:

```python
values = [visible_cluster_count_for_speed(speed, vehicle_class=...) for speed in LADDER_KMH]
table  = CAL_CLUSTERS_PER_FRAME[vehicle_class]     # Bảng 1 = DBSCAN trên điểm thật
lines.append(f"| {vehicle_class} mô hình | " + " | ".join(values) + " |")
lines.append(f"| {vehicle_class} bảng | {table} |")
```

⇒ A1 so **hai đại lượng khác nhau**, không phải hai phép đo cùng đại lượng:

| vế | đại lượng | nguồn |
|---|---|---|
| "mô hình" | `visible = round(rate × K)` — **số cụm lý thuyết còn sống** | `spray/plume.py:234` |
| "bảng" | **số cụm DBSCAN** dựng lại từ điểm thật | Bảng 1 |

Đây là **lỗi của PM khi viết tiêu chí A1 ở ticket 29c**, không phải lỗi agent. Nó khiến A1 "ĐẠT" mà
không chứng minh điều cần chứng minh: generator có thể sinh đúng số cụm lý thuyết trong khi model
**nhìn thấy ít cụm hơn hẳn** sau ray-cast + DBSCAN.

## Số thật của hai vế

| @100 km/h, Crafter | giá trị |
|---|---:|
| `visible_cluster_count_for_speed` (vế "mô hình") | 29 (khớp Bảng 1 29,24) |
| cụm DBSCAN từ detection sinh ra | **12,9** |
| cụm DBSCAN trên điểm thật | 21,8 |

⇒ Con số **29** là số lý thuyết, không phải số model nhìn thấy. Khoảng cách thật là **12,9 vs 21,8 =
0,59×**, và đó là con số 29f phải sửa.

## Hệ quả — A1 phải thay

A1 hiện tại **không được dùng làm tiêu chí nghiệm thu** nữa. Thay bằng:

| # | Tiêu chí mới | Ngưỡng |
|---|---|---|
| A1′ | cụm **DBSCAN dựng lại từ detection sinh ra** vs Bảng 1 | ±20 % ở 9 mốc × 2 lớp |

Đây chính là D3 của ticket 29f (≥ 0,85× ở @100 và @130). Giữ `visible_cluster_count_for_speed` như
**chẩn đoán** (in ra để đối chiếu), không phải tiêu chí.

## Việc phải làm ngay

1. Sửa `render_acceptance` trong `scripts/measure_29ec.py`: đổi hàng "mô hình" thành **cụm DBSCAN đo
   được**, giữ `visible` ở hàng chẩn đoán có nhãn rõ.
2. Sửa biên bản 29e-d closure: A1 chuyển từ **ĐẠT** sang **KHÔNG ĐẠT** (đúng bản chất: 0,59×).
3. Ghi vào 29f: D3 là tiêu chí thay thế A1.

## Không mở lại

- Không sửa Bảng 1 — nó đếm đúng đại lượng model nhìn thấy.
- Không đổi `eps`/`minPts` để "làm khớp" — đó là recipe paper.
- Không tính A1 đạt dựa trên `visible_cluster_count_for_speed`.