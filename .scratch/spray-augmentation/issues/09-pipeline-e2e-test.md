# 09: End-to-end pipeline test

**What to build:** Một test chạy config thật qua transform chain đến collection với stub model ghi lại input, chứng minh hai stream cùng frame và đúng routing.

**Blocked by:** 07, 08

**Status:** ready-for-agent

## PM note 2026-11-07

Dependency ẩn đã phát hiện ở ticket 08: `points_clean` không tự tới `forward` (`DefaultFormatBundle3D`
chỉ wrap `points`/`radar`). Ticket 08 nhận luôn phần plumbing; ticket 09 chỉ **chứng minh e2e** trên config
thật. Nếu 09 thấy `points_clean` vẫn rỗng ⇒ đó là bug của 08, không phải lý do bỏ qua test.


- [ ] Cả hai stream tồn tại và cùng frame sau augmentation.
- [ ] Inverse `lidar_aug_matrix` trên một điểm đã biết cho đúng tọa độ.
- [ ] Spray off thì hai stream tương đương.
- [ ] Test chạy được trên CPU.
