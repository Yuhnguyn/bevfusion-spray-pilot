# 05: Evaluator core + synthetic tests

**What to build:** Một evaluator thuần Python cho **proxy mAP**: nhận box dự đoán và box GT, lọc theo range, matching theo class, tính AP/recall/FP tại score threshold cố định. Test bằng box tổng hợp có kết quả biết trước, không phụ thuộc model.

**Blocked by:** None

**Status:** ready-for-agent

- [x] Box BEV được chuyển thành polygon và tính IoU.
- [x] Matching per class là greedy theo score.
- [x] AP, recall theo range bucket, và FP count được tính.
- [x] GT ngoài range được báo riêng và không vào mAP.
- [x] Test synthetic cho perfect match, duplicate, wrong class, range filter đều pass.
