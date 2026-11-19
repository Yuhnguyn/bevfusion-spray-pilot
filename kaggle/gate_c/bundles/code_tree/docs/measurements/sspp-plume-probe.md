# Probe generator plume trên SemanticSpray++ — đo thật vs sinh

Báo cáo do `scripts/probe_sspp_plume.py` sinh. **Không sửa generator**; đây là phép đo hiện trạng.

## Phạm vi mẫu

| Mục | Giá trị |
|---|---|
| Dataset | `/Users/huynguyen/projects/bevfusion-spray-pilot/data/SemanticSprayDataset` |
| Split | `train` |
| Scene | 16 |
| Frame | 160 |
| Frame/scene | tối đa 10, cách đều |
| Toán tử cụm | `spray.semantic_stats.cluster_angular` (DBSCAN góc, eps = 0,7°, minPts = 3) |
| Điểm thật | `labels & 0xFFFF == 2` |
| Điểm gen | `inject_plume(points[labels != 2], gt_boxes, seed=0, token=<scene/scan>)`, đếm trên `result.injected` |
| Mặt đường | `road_z` = trung vị z-đáy của box GT trong frame |

## Bảng thật-vs-generator theo (group, tốc độ) `[ĐO]`

`real` = điểm noise thật; `gen` = điểm `inject_plume` chèn vào cùng frame. `points` = số điểm mỗi frame. `det/cụm` = số điểm mỗi cụm. `height p5` = percentile 5 chiều cao trên mặt đường. Mọi số trong bảng này là `[ĐO]` trên máy này.

| group | km/h | frame | cụm/frame real `[ĐO]` | cụm/frame gen `[ĐO]` | điểm/frame real `[ĐO]` | điểm/frame gen `[ĐO]` | det/cụm p50 real `[ĐO]` | det/cụm p50 gen `[ĐO]` | det/cụm mean real `[ĐO]` | det/cụm mean gen `[ĐO]` | height p5 real `[ĐO]` | height p5 gen `[ĐO]` | capped gen `[ĐO]` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 60 | 20 | 10,30 | 6,95 | 222,2 | 165,8 | 5,00 | 12,00 | 18,88 | 22,15 | 0,23 | 0,52 | 0 |
| Crafter_dynamic | 80 | 20 | 21,75 | 6,90 | 793,5 | 296,5 | 6,00 | 11,00 | 33,53 | 41,67 | 0,24 | 0,55 | 0 |
| Crafter_dynamic | 100 | 20 | 30,45 | 6,20 | 1702,6 | 387,9 | 6,00 | 17,50 | 53,11 | 60,45 | 0,22 | 0,55 | 0 |
| Crafter_dynamic | 120 | 20 | 22,80 | 6,60 | 1085,5 | 249,6 | 6,00 | 17,00 | 44,73 | 36,33 | 0,25 | 0,50 | 0 |
| Golf_dynamic | 60 | 20 | 8,70 | 6,35 | 185,2 | 158,3 | 5,00 | 15,00 | 17,89 | 24,17 | 0,29 | 0,65 | 0 |
| Golf_dynamic | 80 | 20 | 12,35 | 8,45 | 361,1 | 345,1 | 7,00 | 14,00 | 26,46 | 38,85 | 0,30 | 0,60 | 0 |
| Golf_dynamic | 100 | 20 | 14,40 | 6,95 | 475,9 | 432,1 | 6,00 | 12,00 | 30,38 | 59,73 | 0,30 | 0,61 | 0 |
| Golf_dynamic | 120 | 20 | 15,90 | 8,90 | 673,2 | 290,6 | 6,00 | 14,00 | 39,55 | 30,41 | 0,27 | 0,39 | 0 |

## Thống kê `PlumeStats` phía generator `[ĐO]`

`injected` = `stats.injected`; `eligible box·frame` = số box đủ điều kiện cộng dồn qua các frame. `skipped_*` lấy nguyên từ `PlumeStats`.

| group | km/h | frame | eligible box·frame `[ĐO]` | injected `[ĐO]` | capped `[ĐO]` | skipped_no_velocity `[ĐO]` | skipped_low_speed `[ĐO]` |
|---|---:|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 60 | 20 | 20 | 3317 | 0 | 0 | 0 |
| Crafter_dynamic | 80 | 20 | 20 | 5930 | 0 | 0 | 0 |
| Crafter_dynamic | 100 | 20 | 20 | 7757 | 0 | 0 | 0 |
| Crafter_dynamic | 120 | 20 | 20 | 4992 | 0 | 0 | 0 |
| Golf_dynamic | 60 | 20 | 20 | 3166 | 0 | 0 | 0 |
| Golf_dynamic | 80 | 20 | 20 | 6902 | 0 | 0 | 0 |
| Golf_dynamic | 100 | 20 | 20 | 8643 | 0 | 0 | 0 |
| Golf_dynamic | 120 | 20 | 20 | 5813 | 0 | 0 | 0 |

## Cái còn sai

| Hiện tượng | Bằng chứng |
|---|---|
| Số cụm/frame của generator lệch so với frame thật | gen/thật = 0,20–0,73× trên 8 ô (group, tốc độ) |
| Số điểm mỗi cụm khác giữa hai phía | p50 điểm/cụm: thật 5,88 so với gen 14,06 |
| Độ cao p5 của điểm trên mặt đường khác nhau | p5 cao: thật 0,22–0,30 m, gen 0,39–0,65 m |
| Golf dùng chung bảng cụm của Crafter | inject_plume không nhận vehicle_class; cụm/frame gen khác nhau ở cùng tốc độ |

## Đối chiếu Fig. 4 @25 m `[PAPER-graph]`

Các số 4,5 / 9 / 11 / 12,3 / 16,4 / 20,4 / 26 cụm/frame ở 70→130 km/h là **đọc từ đồ thị** Fig. 4 của paper tại cự ly 25 m, `[PAPER-graph]`. Chỉ dùng để đối chiếu, **không dùng để fit** generator. Paper chỉ định lượng Crafter, nên Golf để tham khảo.

| km/h | Fig. 4 @25 m `[PAPER-graph]` | Crafter thật `[ĐO]` | Crafter gen `[ĐO]` | Golf thật `[ĐO]` | Golf gen `[ĐO]` |
|---:|---:|---:|---:|---:|---:|
| 70 | 4,5 | — | — | — | — |
| 80 | 9,0 | 21,75 | 6,90 | 12,35 | 8,45 |
| 90 | 11,0 | — | — | — | — |
| 100 | 12,3 | 30,45 | 6,20 | 14,40 | 6,95 |
| 110 | 16,4 | — | — | — | — |
| 120 | 20,4 | 22,80 | 6,60 | 15,90 | 8,90 |
| 130 | 26,0 | — | — | — | — |

Split train chỉ chứa tốc độ 60/80/100/120 km/h, nên các mốc 70/90/110/130 để trống (`—`). Đây là giới hạn của split, không phải lỗi của phép đo.

## Cách chạy lại

```bash
CONDA_NO_PLUGINS=true env -u PYTHONPATH /opt/anaconda3/bin/python scripts/probe_sspp_plume.py
```

