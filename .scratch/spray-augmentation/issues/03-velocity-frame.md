# 03: Xác minh velocity frame và ObjectPaste

**What to build:** Câu trả lời có bằng chứng cho hai câu hỏi: velocity của box nằm ở ego frame hay global frame; và box do `ObjectPaste` tạo có velocity hợp lệ hay phải fallback. Kết quả quyết định cách đặt spray plume.

**Blocked by:** 01

**Status:** done

Bằng chứng: `docs/velocity-contract.md` (commit `47fc600`). Velocity ở LiDAR frame của keyframe hiện tại,
đi qua `nuscenes_converter.py:264–268` → `nuscenes_dataset.py:305–309` → `lidar_box3d.py:152–154`.
Plume phải chèn sau `GlobalRotScaleTrans` + `RandomFlip3D`; box `ObjectPaste` set velocity = 0.

- [x] Velocity frame được xác nhận từ loader và ghi lại.
- [x] Box từ database sampler được kiểm tra có velocity hay không.
- [x] Fallback policy được chốt: bỏ qua plume hay dùng giá trị mặc định.
- [x] Có số đếm box eligible với velocity hợp lệ trên một sample. (quét 120 val infos + full val 34k)

## Số đo eligible (2026-11-05)

- Trên 3 scene val đầu (120 frame): 2,338 box; 1,468 box vehicle; 0 box ≥ 50 km/h;
  max 43.5 km/h. Các scene này là phố đông, không đại diện.
- Trên **toàn bộ val (34,029 frame, 1,160,875 box)**:

| Ngưỡng | Box vehicle | Box front ≤30 m | Frame có ≥1 box | Tỷ lệ frame |
|---|---|---|---|---|
| ≥30 km/h | 44,537 | 7,152 | 4,690 | 13.8% |
| ≥40 km/h | 18,552 | 2,927 | 1,924 | 5.7% |
| ≥50 km/h | 5,514 | 952 | 697 | **2.0%** |
| ≥60 km/h | 950 | 193 | 173 | 0.5% |

- Phân bố tốc độ (finite): p50 0.21, p90 10.72, p95 26.14, p99 44.46, p99.9 58.98 km/h;
  max 175.71 (outlier annotation).
- **Hệ quả:** ngưỡng 50 km/h chỉ cho ~2% frame có plume (697 frame val), và 3 scene
  subset có 0%. Cần chọn scene highway hoặc hạ ngưỡng (30 km/h → 13.8%) trước ticket 07/10/11.
