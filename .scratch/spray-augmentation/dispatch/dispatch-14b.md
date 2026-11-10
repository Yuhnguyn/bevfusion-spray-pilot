# Ticket 14b — Arm B0: đổi từ ROR cố định sang DROR (bán kính theo cự ly)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · branch `main` · HEAD `211fce1`
Đọc trước: `spray/denoise.py` (bạn vừa viết ở 14a), `docs/history/denoise-b0-params.md`,
`.scratch/spray-augmentation/issues/14a-denoise-baseline.md` (checkbox 1 đã tick kèm số đo của PM).

## Vì sao phải sửa — số đo, không phải ý kiến

PM đo trên lưới tia HDL-32E (32 vòng, 1,33° dọc, 0,17° ngang) cho mặt phẳng hướng về cảm biến, dùng
`ror_filter(k=8, r=0,5)`:

| cự ly | hàng xóm median | % điểm được giữ |
|---:|---:|---:|
| 10 m | 116 | 100% |
| 20 m | 30 | 100% |
| 40 m | 8 | 88,7% |
| **50 m** | **6** | **0%** |

Nghĩa là B0 hiện tại **xoá sạch mọi thứ ngoài ~45 m**. Baseline như vậy là "người rơm": nó thua A/B vì
filter hỏng, không phải vì ý tưởng lọc spray sai. DROR `alpha=0,03` (bán kính = `alpha × khoảng cách`)
giữ **100%** ở cả 10/20/40/50 m, vẫn bỏ điểm cô lập, vẫn giữ cụm spray dày 14 điểm @25 m.

## Việc phải làm

1. **Thêm `dror_filter` vào `spray/denoise.py`** (giữ nguyên `ror_filter`, **không** đổi hành vi của nó):
   - `dror_filter(points, k=8, alpha=0.03, config: DrorConfig | None = None) -> (keep_mask, stats)`.
   - Bán kính riêng cho từng điểm: `r_i = alpha * norm(xyz_i)`.
   - Cùng contract với `ror_filter`: mask `bool (N,)`, giữ thứ tự, không sửa input.
   - `stats` thêm `alpha` (giữ `k`, `n_in`, `n_out`, `frac_removed`, `time_ms`).
   - `N == 0` không crash; tâm cảm biến `norm == 0` thì dùng `r = 0` (điểm đó tự bị bỏ) — ghi trong docstring.
   - Vector hoá, một `cKDTree` cho cả frame, không vòng lặp Python trên từng điểm nếu tránh được
     (`query_ball_point` nhận mảng bán kính).
2. **Chốt B0 dùng DROR:** thêm hằng số `ARM_B0_FILTER = "dror"` + `DrorConfig()` default, để ticket 10 nối
   vào pipeline không phải chọn lại.
3. **Thêm 3 test vào `tests/test_denoise.py`** (để nguyên 3 test cũ):
   - `test_dror_keeps_flat_surface_at_50m` — tự dựng lưới tia như bảng trên (hàm phụ trong file test), assert
     **≥ 95%** điểm ở 50 m được giữ. Đây là test chống tái phát cho đúng lỗi PM đo được.
   - `test_dror_removes_isolated_points` — cụm dày 30 điểm @10 m + 1 điểm lạc cách 5 m ⇒ điểm lạc bị bỏ.
   - `test_dror_keeps_dense_cluster_at_25m` — cụm 14 điểm bán kính 0,3 m @25 m (giống cụm spray thật) ⇒ giữ hết.
4. **Cập nhật `docs/history/denoise-b0-params.md`**: DROR `k=8, alpha=0,03` là filter của B0; dán **bảng số ở trên**
   (nhãn `[ĐO]`); giữ đoạn ROR như "đã thử và bị loại vì..."; ghi thời gian/frame mới đo được của DROR.

## Ràng buộc

- KHÔNG sửa `ror_filter` hành vi, KHÔNG sửa test cũ, KHÔNG đụng `spray/plume*.py`, `mit/**`, `third_party/**`.
- KHÔNG thêm dependency. KHÔNG bật background process.
- Chỉ `git add` đúng 2 file: `spray/denoise.py`, `tests/test_denoise.py`, và file doc (`docs/history/denoise-b0-params.md`).

## Nghiệm thu (tự chạy, dán output)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/
```
→ **63 passed** (60 cũ + 3 mới), 0 failed.

```bash
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np, time
from spray.denoise import dror_filter
rng=np.random.default_rng(0)
p=rng.uniform([-54,-54,-5],[54,54,3],(35000,3)).astype('float32')
p=np.hstack([p,np.zeros((len(p),2),'float32')])
m,s=dror_filter(p)
print('kept %.3f ms %.0f' % (s['n_out']/s['n_in'], s['time_ms']))
"
```
In ra `time_ms` thật của DROR trên 35.000 điểm.

## Commit

```
feat(denoise): use distance-adaptive radius (DROR) for arm B0
```

Cuối câu trả lời in `git log --oneline -1`, `git status --porcelain`, `passed`, và `time_ms`.