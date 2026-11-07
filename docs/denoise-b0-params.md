# Arm B0 — tham số filter lọc spray

## Quyết định: DROR

- Filter của B0 là **DROR** (Dynamic Radius Outlier Removal): `k = 8`, `alpha = 0,03`,
  bán kính riêng cho từng điểm `r_i = alpha × ||xyz_i||`. Đây là `ARM_B0_FILTER = "dror"`
  + `ARM_B0_DROR_CONFIG = DrorConfig()` trong `spray/denoise.py`; ticket 10 nối thẳng vào
  pipeline, không phải chọn lại.
- `k = 8`, `alpha = 0,03` là **[CHỌN]**. Paper (Linnhoff et al.) không công bố tham số
  DROR/DSOR họ dùng; hai giá trị này chốt trước khi xem A/B, không tune trên eval set.

### Vì sao DROR: ROR cố định xoá sạch điểm xa

PM đo 2026-11-07 trên lưới tia HDL-32E (32 vòng dọc, 1,33° dọc, 0,17° ngang) cho mặt
phẳng hướng về cảm biến, dùng `ror_filter(k=8, r=0,5)` và `dror_filter(k=8, alpha=0,03)`:

| cự ly | hàng xóm median (r=0,5 m) | % điểm giữ, ROR | % điểm giữ, DROR |
|---:|---:|---:|---:|
| 10 m | 116 | 100% | 100% |
| 20 m | 30 | 100% | 100% |
| 40 m | 8 | 88,7% | 100% |
| 50 m | 6 | **0%** | **100%** |

**[ĐO]** Ở 50 m, ROR cố định chỉ còn 6 hàng xóm < `k=8` nên xoá 100% điểm — B0 dùng ROR sẽ
là "người rơm" ngoài ~45 m, thua A/B vì filter hỏng chứ không phải vì ý tưởng lọc spray sai.
DROR nới bán kính theo cự ly nên giữ 100% ở cả 10/20/40/50 m, vẫn bỏ điểm cô lập, vẫn giữ
cụm spray dày 14 điểm @25 m. Ba tính chất này được khoá bằng test trong
`tests/test_denoise.py` (`test_dror_keeps_flat_surface_at_50m`,
`test_dror_removes_isolated_points`, `test_dror_keeps_dense_cluster_at_25m`).

## ROR cố định: đã thử và bị loại

- `ror_filter(k=8, r=0,5)` vẫn có trong `spray/denoise.py` (giữ nguyên hành vi) để so sánh,
  nhưng **không** dùng cho B0. Lý do loại: bảng đo ở trên — ROR xoá 100% điểm ở 50 m và
  11,3% ở 40 m chỉ vì lưới tia thưa dần, không phải vì điểm đó là spray.
- Ghi chú lịch sử: trước khi có số đo, ROR từng được chọn vì đơn giản hơn và vì paper báo
  DROR làm AP **−5,52** (52,45 so với 57,97) **[PAPER]**. Số đo cục bộ cho thấy lựa chọn đó
  biến B0 thành baseline hỏng, nên đã đổi sang DROR.

## Precision/recall của filter theo paper

- Paper chỉ báo kết quả lọc trên SemanticSpray: DROR precision **50,68%** / recall
  **64,24%**; DSOR precision **51,57%** / recall **56,58%** **[PAPER]**. Tức là filter
  bỏ đúng khoảng nửa số điểm bị gắn cờ, và bắt được 56–64% điểm spray thật.

## Thời gian/frame

- DROR: **~378 ms** cho 35.000 điểm uniform trong ±54 m (dựng KD-tree + query với bán kính
  từng điểm, CPU; median 7 lần, dao động 352–406 ms; một lần chạy nguội 513 ms). [ĐO]
- ROR (đã loại): ~361 ms cho cùng đầu vào, median 7 lần. [ĐO]
- Giới hạn: filter chỉ xử lý từng điểm, không học ngữ cảnh; B0 âm là kết quả hợp lệ.
