# Arm B0 — tham số filter lọc spray

- `k = 8`, `r = 0,5 m` là **[CHỌN]**. Paper (Linnhoff et al.) không công bố tham số
  DROR/DSOR họ dùng; hai giá trị này chốt trước khi xem A/B, không tune trên eval set.
- Paper chỉ báo kết quả lọc trên SemanticSpray: DROR precision **50,68%** / recall
  **64,24%**; DSOR precision **51,57%** / recall **56,58%** **[PAPER]**. Tức là filter
  bỏ đúng khoảng nửa số điểm bị gắn cờ, và bắt được 56–64% điểm spray thật.
- Chọn ROR thay vì DROR: DROR cần khoảng cách tới cảm biến và hệ số α — thêm 2
  tham số không có nguồn để chốt. Paper cũng đo DROR làm AP **−5,52** (52,45 so
  với 57,97) **[PAPER]**. ROR đơn giản hơn và ít xoá điểm thật hơn.
- Thời gian/frame đo local: **~361 ms** cho 35.000 điểm uniform trong ±54 m
  (dựng KD-tree + query, CPU; median 7 lần, máy đang tải nên dao động 287–1861 ms).
- Giới hạn: filter chỉ xử lý từng điểm, không học ngữ cảnh; B0 âm là kết quả hợp lệ.
