# 09: End-to-end pipeline test

**What to build:** Một test chạy config thật qua transform chain đến collection với stub model ghi lại input, chứng minh hai stream cùng frame và đúng routing.

**Blocked by:** 07, 08

**Status:** ready-for-agent

- [ ] Cả hai stream tồn tại và cùng frame sau augmentation.
- [ ] Inverse `lidar_aug_matrix` trên một điểm đã biết cho đúng tọa độ.
- [ ] Spray off thì hai stream tương đương.
- [ ] Test chạy được trên CPU.
