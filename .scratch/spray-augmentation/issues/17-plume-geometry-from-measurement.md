# 17: Sửa generator theo số đo của ticket 16

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (ticket 16 đã xong, commit `08f6715`, `docs/plume-geometry-vs-real.md`)
**Chủ:** CommandCode. PM: Hermes.

## Số của ticket 16 — và nó bác bỏ giả thuyết của bản ticket cũ

Đo trên 873.457 điểm noise / 11.607 dense cluster (base) và 23.989 (sample mở rộng). Hai sample
**đồng ý với nhau**, nên số dùng được.

| đại lượng | đo được | generator hiện tại |
|---|---|---|
| `median n_points` toàn bộ cluster | **17,0** (cả hai sample) | 17 ✓ |
| `median n_points` theo cự ly | 30 (0–5 m) → 20 (5–10) → 14 (10–20) → 10 (20–30) → 10 (30–50) | **17 ở mọi cự ly** ✗ |
| `median r_range / r_extent` | **1,28** (0–5: 1,11; 5–10: 1,35; 10–20: 1,31; 20–30: 1,23) | **2,00** (khối cầu đầy) ✗ |
| `median n_rings` | 3–4 ở 5–30 m | không mô hình hoá |
| `median r_extent` | 0,755 m (cận trên) | 0,30 m |

Ba kết luận phải đọc kỹ trước khi sửa:

1. **Hằng số 17 đúng ở mức trung bình.** Bản ticket cũ của tôi giả định nó sai nghiêm trọng — **sai**.
   Sai thật nằm ở chỗ 17 **không đổi theo cự ly**, trong khi thực tế giảm **3,0×**.
2. **Cụm là thể tích, không phải vỏ mỏng.** `r_range/r_extent = 1,28 > 1` nghĩa là bề dày theo phương
   bán kính **lớn hơn** bán kính ngoài. Giả thuyết "điểm chỉ có thể nằm trên mặt cầu phía cảm biến"
   của tôi **sai** — và paper cũng không làm vậy: range của mỗi detection được lấy theo phân bố chuẩn
   quanh **tâm** cụm (§III *Generate Spray Detections*), không phải trên bề mặt.
3. **Cái sai thật của generator là hai thứ**: mật độ không đổi theo cự ly (3× sai) và bề dày theo tia
   quá lớn (2,0 so với 1,28).

## Việc phải làm — đúng 3 thay đổi, không làm gì thêm

### 1. Số điểm mỗi cụm phụ thuộc cự ly

```python
median_at = {  # d = ‖tâm cụm‖ trong LiDAR frame, đơn vị mét  [ĐO]
    (0, 5): 30, (5, 10): 20, (10, 20): 14, (20, 30): 10, (30, inf): 10,
}
count = round(median_at[d] * exp(sigma * z))   # z ~ N(0,1), sigma = 0.67 như hiện tại
count = clip(count, 3, 200)
```

Không nội suy đường cong, không bịa giá trị ngoài 30 m — dùng 10 cho mọi `d > 30` và ghi rõ là
**ngoại suy phẳng**.

### 2. Bẹp cụm theo phương bán kính

Sau khi lấy mẫu đều trong khối cầu như hiện tại, nhân thành phần **dọc theo tia** (hướng từ gốc toạ độ
LiDAR tới tâm cụm) với **0,64**:

```
u        = hướng đơn vị từ gốc tới tâm cụm
offset   = offset − (1 − 0,64) · (offset·u) · u
```

Kiểm: `r_range/r_extent` của các điểm sinh ra phải ≈ 1,28 (test ở dưới).

### 3. KHÔNG đổi `cluster_radius_median_m`

Giữ **0,30**. Số đo 0,755 m là **cận trên** vì single-linkage nối chuỗi các cụm gần nhau
(`docs/plume-geometry-vs-real.md` §Caveats), còn paper Fig. 5 cho đúng 0,30. Ghi lý do này vào
docstring của `PlumeConfig`.

## Xong khi

- Test mới trong `tests/test_plume.py` (≥2 test):
  - `r_range / r_extent` của điểm sinh ra (một cụm, nhiều seed) nằm trong **[1,15; 1,40]**;
  - `median n_points` ở cự ly ~5 m, ~15 m, ~25 m khớp bảng trên trong **±20%**.
- `pytest -q tests/` → **≥ 35 passed** (baseline hiện tại 33).
- **Số điểm/frame sẽ GIẢM** so với trước. Đây là thay đổi hành vi **có chủ ý** — **không** áp ngưỡng
  "lệch ≤10%" như bản ticket cũ. Ghi rõ số trước/sau (cùng frame, cùng seed) vào commit message.
- `docs/plume-model-provenance.md` cập nhật 3 dòng: count theo cự ly `[ĐO]`, squash `[ĐO]`,
  radius giữ 0,30 + lý do cận trên.
- Commit: `feat(plume): range-dependent cluster density and radial thinning per ticket 16`

## Không làm

- Không thêm beam grid, ray casting hay `P_det` đầy đủ. Không dựng OSI.
- Không thêm attenuation/occlusion (ADR-0002).
- Không đổi ngưỡng 50 km/h, không đổi số cụm theo tốc độ, không đổi vị trí đặt cụm.
- Không dùng số đo ngoài 30 m để tạo đường cong mới.

## Comments

- PM: bản ticket trước của ticket này đòi "điểm nằm trên vỏ cầu phía cảm biến". **Sai**, đã bỏ. Số đo
  ticket 16 cho `r_range/r_extent = 1,28 > 1`, tức cụm có bề dày theo tia. Sửa lại thành "bẹp 0,64".
- PM: nếu bạn thấy hai thay đổi 1 và 2 xung đột nhau (đổi mật độ làm đổi cả `n_points` lẫn hình học),
  làm đúng thứ tự 2 → 1 và báo lại số đo sau mỗi bước.