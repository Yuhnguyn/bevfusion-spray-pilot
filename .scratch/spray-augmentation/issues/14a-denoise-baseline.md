# 14a/14b: Arm B0 — baseline lọc spray trước khi detect

**What to build:** Một arm tham chiếu không train: lọc điểm nghi là spray khỏi `points` bằng filter thống kê cố định, rồi chạy đúng model của arm A. Mục đích là để kết quả âm của arm B không bị quy cho "chưa thử cách rẻ hơn". Báo mAP/FP/recall của B0 trên cùng held-out spray, cùng evaluator, cùng frame list với A và B.

**Blocked by:** 02 (checkpoint + smoke test), 05 (evaluator core)

**Status:** ready-for-agent

- [x] Chọn filter: **DROR** (bán kính thích nghi theo cự ly), `k=8`, `alpha=0,03`; tham số ghi trong
  `docs/denoise-b0-params.md`. **[CHỌN]** — paper không công bố tham số của họ.
  *PM đo 2026-11-07:* ROR cố định `r=0,5 m, k=8` xoá **100%** điểm trên mặt phẳng ở 50 m (88,7% giữ ở 40 m,
  100% ở 10–20 m) trên lưới tia HDL-32E ⇒ B0 sẽ là "người rơm". DROR `alpha=0,03` giữ **100%** ở 10/20/40/50 m,
  vẫn bỏ điểm cô lập và vẫn giữ cụm spray dày 14 điểm @25 m. [ĐO]
- [ ] Lọc chỉ áp ở eval time trên `points`; `points_clean` và camera branch không đổi.
- [ ] Chạy B0 trên đúng frame list và held-out spray params của cặp A/B.
- [ ] Báo cáo bảng A / B / B0 với cùng metric và cùng scene-clustered bootstrap.
- [ ] Ghi rõ giới hạn: filter xử lý spray ở mức point, không học được ngữ cảnh; precision của filter thống kê trên spray thật theo paper chỉ 50–52%.

**Vì sao có ticket này:** paper báo DROR precision 50,68% / recall 64,24%, DSOR 51,57% / 56,58%
trên SemanticSpray, còn AWNet (học) đạt 87,49% / 99,32%. Nghĩa là hướng "lọc rồi detect" tồn tại,
rẻ, và có thể đủ. Không có B0 thì không phân biệt được "augmentation không giúp" với "chưa thử
cách khác".