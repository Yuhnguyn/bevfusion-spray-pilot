# 17: Sửa generator theo số đo của ticket 16

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (ticket 16 đã xong, commit `08f6715`, `docs/measurements/plume-geometry-vs-real.md`)
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
LiDAR tới tâm cụm) với hệ số `S`:

```
u        = hướng đơn vị từ gốc tới tâm cụm
offset   = offset − (1 − S) · (offset·u) · u
```

**Chọn S sao cho tái lập đúng thống kê mà ticket 16 đã đo**: median **per-cluster** của
`r_range/r_extent` = **1,28**.

- Công thức liên tục cho `S = 1,28/2 = 0,64`, nhưng đó là cho khối cầu đặc vô hạn điểm. Với **17 điểm
  rời rạc**, `S = 0,64` chỉ cho median thực nghiệm **0,98** (đã đo) — quá mỏng.
- Vì vậy **hiệu chỉnh thực nghiệm**: quét S để median per-cluster (≥200 cụm, nhiều seed) bằng 1,28.
  Kỳ vọng `S ≈ 0,87`. **Ghi cả hai số vào docstring**: 0,64 là suy ra giải tích, S hiệu dụng là số dùng,
  kèm lý do lệch (điểm rời rạc làm `r_extent` hụt so với `R`).

## Xong khi

- Test mới trong `tests/test_plume.py` (≥2 test):
  - **(a)** median **per-cluster** của `r_range/r_extent`, đo trên **≥200 cụm** (nhiều seed, `d` từ 8–30 m),
    nằm trong **[1,22; 1,34]**. Không dùng trung bình gộp — ticket 16 đo median của tỉ lệ từng cụm.
  - **(b)** median `n_points` ở **d = 4,0 m / 15 m / 25 m** (bucket `[0,5) / [10,20) / [20,30)` → kỳ vọng
    30 / 14 / 10) khớp bảng trong **±25%**, mỗi mốc ≥100 cụm. **Không dùng d = 5,0 m** — nó rơi vào
    bucket `[5,10)` với kỳ vọng 20.
- `pytest -q tests/` → **≥ 35 passed** (baseline hiện tại 33).
- **Số điểm/frame KHÔNG có ngưỡng "phải giảm".** Thay đổi này làm count phụ thuộc cự ly, nên cụm rơi vào
  bucket gần (<5 m) sẽ **tăng** (kỳ vọng 30 > 17), cụm xa **giảm** (10 < 17). Phải báo số theo **một
  kịch bản cố định**: 3 box ở 12 / 22 / 38 m, 80 km/h, seed 0–4, cùng frame — bảng trước → sau cho từng
  seed — và giải thích chiều tăng/giảm theo bucket.
- `docs/history/plume-model-provenance.md` cập nhật 3 dòng: count theo cự ly `[ĐO]`, hệ số bẹp `S` hiệu dụng +
  công thức 0,64 `[ĐO/CHỌN]`, radius giữ 0,30 + lý do cận trên.
- Commit: `feat(plume): range-dependent cluster density and radial thinning per ticket 16`

### 3. KHÔNG đổi `cluster_radius_median_m`

Giữ **0,30**. Số đo 0,755 m là **cận trên** vì single-linkage nối chuỗi các cụm gần nhau
(`docs/measurements/plume-geometry-vs-real.md` §Caveats), còn paper Fig. 5 cho đúng 0,30. Ghi lý do này vào
docstring của `PlumeConfig`.

## Không làm

- Không thêm beam grid, ray casting hay `P_det` đầy đủ. Không dựng OSI.
- Không thêm attenuation/occlusion (ADR-0002).
- Không đổi ngưỡng 50 km/h, không đổi số cụm theo tốc độ, không đổi vị trí đặt cụm.
- Không dùng số đo ngoài 30 m để tạo đường cong mới.

## Comments

- **PM chốt phương án B** (2026-11-07). Lý do: ticket 16 đo **median của tỉ lệ từng cụm**, nên generator
  phải tái lập đúng **thống kê đó**, không phải công thức liên tục. Vì vậy hiệu chỉnh `S` bằng thực nghiệm
  để median per-cluster = 1,28 (kỳ vọng `S ≈ 0,87`), và ghi **cả** 0,64 (giá trị suy ra giải tích) lẫn `S`
  hiệu dụng vào docstring, kèm lý do lệch.
- PM: **bỏ** ngưỡng "số điểm/frame phải giảm" ở bản ticket trước — sai hướng. Thay bằng báo cáo theo
  kịch bản cố định 12 / 22 / 38 m × seed 0–4.
- PM: test (b) dùng **d = 4,0 m**, không dùng 5,0 m (5,0 rơi vào bucket `[5,10)` với kỳ vọng 20).
- PM: bản ticket trước của ticket này đòi "điểm nằm trên vỏ cầu phía cảm biến". **Sai**, đã bỏ. Số đo
  ticket 16 cho `r_range/r_extent = 1,28 > 1`, tức cụm có bề dày theo tia.
- PM: thứ tự thi công nếu hai thay đổi 1 và 2 ảnh hưởng nhau: làm **2 trước, 1 sau**, báo số sau mỗi bước.