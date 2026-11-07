# 17: Đặt điểm plume trên vỏ cầu phía cảm biến

**Type:** task
**Status:** ready-for-agent
**Blocked by:** 16
**Chủ:** CommandCode. PM: Hermes.

## Vì sao có ticket này

`_ball()` (`spray/plume.py:266–273`) lấy mẫu đều trong **khối** cầu:

```python
scale = radius * rng.random((count, 1)) ** (1.0 / 3.0)   # phân bố đều theo thể tích
```

Với cảm biến LiDAR, điểm chỉ có thể nằm ở giao của tia với **bề mặt** cụm phía cảm biến. Hệ quả
của cách hiện tại:

- một phần điểm nằm ở nửa sau quả cầu — vị trí vật lý **không thể** có return;
- 17 điểm lơ lửng trong quả cầu 0,6 m đường kính, không có texture vòng quét.

Nghĩa là nhánh LiDAR nhìn "plume giả" khác "plume thật" về **cấu trúc**, không chỉ khác về mật độ —
mà mục tiêu của augmentation là dạy model bỏ qua đúng cấu trúc đó.

Ticket 16 đo `r_range / r_extent` trên dữ liệu thật; ticket này dùng con số đó làm độ dày vỏ.
**Ticket này không đổi mật độ** — số điểm/cụm giữ nguyên median 17.

## Việc phải làm

1. Thay `_ball()` bằng `_shell(rng, count, radius, *, center_xy, thickness)`:
   - lấy mẫu phương ngẫu nhiên, **chỉ trên nửa cầu hướng về phía cảm biến** (ego ở gốc toạ độ
     trong LiDAR frame: giữ điểm có tích vô hướng `(p − center)·(0 − center) ≥ 0`);
   - bán kính mỗi điểm = `radius − thickness·u`, `u ~ Uniform(0,1)`, tức nằm trong lớp vỏ
     `[radius − thickness, radius]` — không nằm trong lòng cầu.
2. Thêm một tham số vào `PlumeConfig`:
   ```python
   # Độ dày lớp vỏ theo phương bán kính, tính theo [ĐO] ticket 16:
   # median r_range / r_extent = <số đo>. Xem docs/plume-geometry-vs-real.md.
   shell_thickness_ratio: float = <số đo từ 16>
   ```
   kẹp hiệu dụng vào `[0,02; 0,5]·radius` trong code, không kẹp bằng cách sửa giá trị config.
   Nếu ticket 16 kết luận "quá ít dữ liệu để đo" thì dùng **0,1** và ghi `[CHỌN]` + lý do.
3. **Không đổi** `points_per_cluster_median`, `cluster_radius_median_m`, hay bất kỳ tham số nào khác.
4. Test mới trong `tests/test_plume.py`:
   - mọi điểm chèn có khoảng cách tới tâm cụm trong `[radius·(1−0,5), radius·1,001]`;
   - không điểm nào ở nửa sau: `(p − center)·(center) < 0` phải rỗng (ego ở gốc, nên hướng
     "về phía cảm biến" là `−center`);
   - vẫn giữ test cũ `test_same_seed_and_token_are_reproducible` xanh.
5. Cập nhật `docs/plume-model-provenance.md`: thêm dòng `hình học điểm trong cụm` →
   `vỏ cầu phía cảm biến`, nguồn `[ĐO]` (ticket 16), trạng thái "khớp cơ chế".

## Xong khi

- `pytest -q tests/` xanh, có **≥ 2 test mới**, tổng ≥ 35 passed (baseline 33 ngày 2026-11-07).
- **Số điểm/frame không đổi** so với trước (ticket này chỉ đổi hình dạng): chạy `inject_plume` trên
  cùng 1 frame thật, cùng seed, trước và sau; ghi cả hai số vào comment của PR/commit. Lệch quá ±10%
  là có gì sai, dừng và báo PM.
- `git diff` chỉ chạm `spray/plume.py`, `tests/test_plume.py`, `docs/plume-model-provenance.md`.
- Commit: `feat(plume): sample detections on sensor-facing shell instead of ball volume`

## Không làm

- **Không** thêm beam grid, ray casting hay `P_det`. Nếu ticket 16 nói mật độ phải giảm theo cự ly
  thì đó là **ticket 18** — PM mở riêng, không làm kèm ở đây.
- **Không** thêm attenuation/occlusion (ADR-0002).
- Không đổi `points_per_cluster_median` dù thấy "có vẻ chưa đúng".
- Không sửa `scripts/semantic_spray_stats.py`.

## Comments

- PM: nếu làm đúng thì ticket này gần như miễn phí về rủi ro — số điểm không đổi, chỉ vị trí đổi.
  Nếu phát hiện phải đổi cả mật độ thì dừng, đó là quyết định của PM, không phải của agent.