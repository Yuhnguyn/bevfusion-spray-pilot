# 06: Adapter evaluator cho output MIT

**What to build:** Đưa prediction thật của BEVFusion (MIT) vào evaluator core: class mapping, box format conversion, score threshold, range filter. Kết quả là **proxy mAP** trên một frame thật, kiểm tra được bằng tay.

**Blocked by:** 02, 05

**Status:** ready-for-agent

- [ ] Class order lấy từ định nghĩa dataset MIT, không từ raw index.
- [ ] Box prediction được convert đúng sang format evaluator.
- [ ] Một frame MIT chạy qua evaluator và cho kết quả hợp lý.
- [ ] Score threshold và range filter được ghi lại.
