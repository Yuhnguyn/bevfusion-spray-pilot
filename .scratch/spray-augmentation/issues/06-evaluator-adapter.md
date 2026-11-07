# 06: Adapter evaluator cho output MIT

**What to build:** Đưa prediction thật của BEVFusion (MIT) vào evaluator core: class mapping, box format conversion, score threshold, range filter. Kết quả là **proxy mAP** trên một frame thật, kiểm tra được bằng tay.

**Blocked by:** 02, 05

**Status:** done

- [x] Class order lấy từ định nghĩa dataset MIT, không từ raw index.
- [x] Box prediction được convert đúng sang format evaluator.
- [x] Một frame MIT chạy qua evaluator và cho kết quả hợp lý.
- [x] Score threshold và range filter được ghi lại.

## Kết quả (Kaggle latest + evaluator local, 2026-11-07)

- Adapter: `proxy_eval/mit_adapter.py`; class order `MIT_CLASSES` = 10 class của
  `NuScenesDataset`; score threshold **0.05**, range **54 m**, IoU **0.5**.
- Raw output lấy từ kernel (cell 18, `TICKET06_OK`):
  - primary `f56a5440…`: 42 GT trong range, 200 prediction (43 giữ sau threshold),
    max score 0.7825.
  - secondary `88a090c5…`: 2 GT, cả hai ngoài 54 m; 0 prediction giữ lại.
- Evaluator local trên chính 2 frame đó (`evidence/mit_eval_result.json`):
  - primary: TP 22 / FP 21 / FN 20, precision 0.512, recall 0.524, **mAP 0.298**;
    recall theo range 0–10 m 1.00, 10–20 m 0.50, 20–30 m 0.50, 30–40 m 0.67, 40–54 m 0.36.
  - secondary: 0 TP/FP/FN, 2 GT ngoài range → range filter hoạt động đúng.
- Test: `tests/test_mit_adapter.py` (2 test) + full suite 33 passed.
- Lưu ý: adapter chạy local, không nằm trong Kaggle; raw tensors là bằng chứng từ kernel.
