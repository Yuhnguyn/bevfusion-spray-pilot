# 11: Mini A/B run + report

**What to build:** Train hai arm trên mini, eval trên **held-out spray**, và báo paired delta với bootstrap theo scene, FP, recall theo range, clean retention. Kèm report và recipe bàn giao.

**Blocked by:** 06, 10

**Status:** ready-for-agent

- [ ] Arm A và B chạy cùng ngân sách và seed.
- [ ] Eval trên held-out spray với tham số không dùng khi train.
- [ ] Báo `G = mAP_clean - mAP_spray` cho từng arm và paired delta.
- [ ] Bootstrap theo scene; FP và recall theo range được báo.
- [ ] Report + recipe được lưu.
