# 16: Đo hình học plume thật theo cự ly

**Type:** research
**Status:** ready-for-agent
**Blocked by:** — (không phụ thuộc 02b, chạy được ngay cả khi Kaggle còn đỏ)
**Chủ:** CommandCode. PM: Hermes.

## Vì sao có ticket này

`spray/plume.py` đang làm hai việc chưa ai kiểm bằng dữ liệu:

1. **Mật độ không phụ thuộc cự ly.** Mỗi cụm được gán `points_per_cluster_median = 17` như nhau ở
   mọi khoảng cách. Nhưng điểm LiDAR là giao của tia với bề mặt cụm — số tia cắt một quả cầu giảm
   theo bình phương khoảng cách. Nếu đúng vậy thì cụm ở 5 m và cụm ở 25 m không thể cùng 17 điểm.
2. **Điểm nằm trong thể tích.** `_ball()` (dòng 266–273) rải đều trong **khối** cầu, nên có điểm ở
   nửa sau quả cầu — nơi tia không tới được.

PM đã tính tay và ra con số khác 17, nhưng **tính tay không phải bằng chứng**. Ticket này đo trên
dữ liệu thật để trả lời. Nếu dữ liệu nói 17 là đúng thì generator không có lỗi và ticket 17 sẽ bị
đóng lại. **Không sửa generator trong ticket này.**

## Đo trên cái gì

Mở rộng `scripts/semantic_spray_stats.py` — script đã có, đang sinh `docs/semantic-spray-stats.md`;
sample hiện tại: 207 scene × 10 frame = 2.070 frame, clustering single-linkage r = 0,5 m,
dense cluster ≥ 5 điểm, đọc trực tiếp `velodyne/*.bin` (có cả kênh `ring`).

Với **mỗi** dense cluster, ghi thêm:

| đại lượng | tính thế nào | trả lời câu |
|---|---|---|
| `d_sensor` | ‖tâm cụm‖ trong LiDAR frame | cự ly tới cảm biến |
| `n_points` | số điểm trong cụm | mật độ |
| `r_extent` | max ‖p − center‖ (định nghĩa bán kính hiện tại) | so với `cluster_radius_median_m` = 0,30 |
| `r_range` | max‖p‖ − min‖p‖ | độ dày theo phương bán kính |
| `n_rings` | số giá trị `ring` khác nhau | cấu trúc vòng quét |
| `ring_span` | max(ring) − min(ring) | như trên |

Gom theo bucket cự ly: **0–5 / 5–10 / 10–20 / 20–30 / 30–50 / >50 m**.

## Ba câu phải trả lời bằng số

1. **`median n_points` theo bucket cự ly.** Có giảm không, giảm bao nhiêu lần từ 0–5 m xuống 20–30 m?
2. **`r_range / r_extent`.** Nếu ≪ 1 thì cụm thật là **vỏ mỏng**, đặt điểm trong khối cầu là sai hình
   dạng. Báo median tỉ lệ này theo bucket.
3. **`n_rings`.** Cụm thật trải trên bao nhiêu vòng quét? (~1–3 thì "vài cung" là đúng, nhiều hơn thì
   giả thuyết cấu trúc vòng quét của PM sai.)

## Ra cái gì

- Section mới trong `docs/semantic-spray-stats.md`. Nếu dài hơn 40 dòng thì tách
  `docs/plume-geometry-vs-real.md` và link từ file cũ.
- Gồm 3 bảng (mỗi bucket: `n_clusters`, `median n_points`, `p25/p75`, `median r_extent`,
  `median r_range`, `median r_range/r_extent`, `median n_rings`).
- Script chạy lại được bằng **một lệnh**, có cờ chọn sample, ghi rõ trong docstring.

## Xong khi

- 3 bảng có số thật: không ô trống, không "ước tính", bucket nào < 30 cụm thì ghi rõ
  **"quá ít, không kết luận"** thay vì báo số.
- Kết luận viết dạng số, không viết định tính. Ví dụ đúng:
  *"median n_points giảm từ 21,4 (0–5 m) xuống 1,8 (20–30 m), tỉ lệ 11,9×"*.
  Ví dụ sai: *"n_points có vẻ giảm theo cự ly"*.
- Mọi số mới gắn nhãn `[ĐO]`.
- `pytest -q tests/` vẫn **33 passed** (baseline 2026-11-07, sau khi ticket 07 xong; không chạm `spray/`).
- Commit: `docs(spray): measure real plume geometry vs range on SemanticSpray`

## Không làm

- Không sửa `spray/plume.py`, không sửa `PlumeConfig`, không sửa `tests/`.
- Không đổi clustering radius 0,5 m (giữ để so được với số cũ trong doc).
- Không kết luận gì về attenuation hay occlusion.
- Không đề xuất tham số mới cho generator trong ticket này — chỉ báo số, PM quyết.