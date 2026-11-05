# 12: SemanticSpray statistics

**What to build:** Từ SemanticSpray đã tải, tính phân bố intensity, số điểm mỗi plume, khoảng cách plume, và so với simulator. Mục tiêu là phát hiện simulator lệch rõ ràng, không dùng dataset này để train/eval BEVFusion.

**Blocked by:** None

**Status:** done

- [x] Download hoàn tất và extract được.
- [x] Thống kê intensity, point count, distance được tính.
- [x] So sánh với tham số simulator được ghi lại.
- [x] Khác biệt lớn được nêu rõ, không suy diễn quá mức.

## Comments

- Report: `docs/semantic-spray-stats.md`, sinh bởi `scripts/semantic_spray_stats.py`
  trên 207 scenes / 2070 frames (10 frame đều mỗi scene).
- Code: `spray/spray_stats.py` (single-linkage clustering, dense cluster >= 5 điểm),
  test trong `tests/test_spray_stats.py`.
- Số liệu chính (dense cluster, median): 144 điểm/frame, 5 plume/frame,
  17 điểm/plume; intensity median 0, p99 3.
- Khác biệt so với `PlumeConfig`: simulator 32 điểm/cluster so với thật 17.
  Extent p90 3.75 m so với cầu 0.70 m, nhưng đây là cận trên vì single-linkage
  nối chuỗi điểm, nên không dùng để kết luận.
- Khoảng cách không so trực tiếp được: thật đo centroid tới điểm foreground,
  simulator đo từ tâm box; điểm foreground thưa nên giá trị thật thiên lớn.
- Chưa so với đường cong trong paper. Ticket này là stage 4 của evidence ladder,
  chạy sớm vì rẻ và local; không dùng làm bằng chứng cho pilot A/B.
