# Ticket 14a — Arm B0: filter lọc spray (phần implement, chạy local)

Repo: `/Users/huynguyen/projects/bevfusion-spray-pilot` · branch `main` · HEAD `bde2039`
Đọc trước khi làm: `.scratch/spray-augmentation/issues/14a-denoise-baseline.md`,
`.scratch/spray-augmentation/history/spec-v1.md` dòng 242 và dòng 274.

## Bối cảnh

Arm B0 là baseline **không train**: lọc bỏ điểm nghi là spray rồi cho model của arm A detect, để kết quả âm
của arm B không bị quy cho "chưa thử cách rẻ hơn".

Ticket 14 **chỉ làm phần implement + test** ở đây. Bảng A/B/B0 và phần chạy trên frame list **để sau**
(phải chờ ticket 11 có kết quả A/B). Đừng làm phần đó.

## Việc phải làm

1. **Tạo `spray/denoise.py`** (numpy + `scipy.spatial.cKDTree`; scipy 1.17.1 đã có sẵn, **không** thêm package):
   - Interface đúng như spec: `ror_filter(points, k=8, r=0.5) -> (keep_mask, stats)`.
   - `points`: array `(N,4)` hoặc `(N,5)` float32; chỉ dùng `x, y, z`, các cột sau giữ nguyên.
   - Luật: điểm bị bỏ nếu số hàng xóm trong bán kính `r` (không tính chính nó) **< k**.
   - `keep_mask`: `bool (N,)`. Không đổi thứ tự, không đổi giá trị các điểm còn lại.
   - `stats`: dict có `n_in`, `n_out`, `frac_removed`, `time_ms`, `k`, `r`.
   - Dataclass `RorConfig(k=8, r=0.5)` làm default; hàm nhận cả config.
   - Biên: `N == 0` trả mask rỗng + stats 0, không crash. `N < k` thì mọi điểm bị bỏ (ghi rõ trong docstring).

2. **Tạo `tests/test_denoise.py`**, có đúng 2 test mà spec yêu cầu (tên phải khớp):
   - `test_ror_removes_isolated_points` — 1 cụm dày 30 điểm bán kính 0,2 m + 1 điểm lạc cách 5 m → điểm lạc bị bỏ,
     cụm giữ đủ.
   - `test_ror_keeps_dense_structures` — 2 cụm dày cách nhau 3 m → cả hai giữ, `frac_removed == 0`.
   - Thêm 1 test biên: rỗng, 1 điểm, và kiểm shape/dtype/thứ tự cột.

3. **Tạo `docs/history/denoise-b0-params.md`** (≤ 20 dòng) ghi đúng:
   - `k = 8`, `r = 0,5 m` là **[CHỌN]** — paper không cho tham số của họ.
   - Paper chỉ báo kết quả: DROR precision **50,68% / recall 64,24%**, DSOR 51,57% / 56,58% **[PAPER]**.
   - Vì sao ROR chứ không DROR: DROR cần khoảng cách tới cảm biến + hệ số α (thêm 2 tham số, không có nguồn),
     và chính paper đo DROR cho **−5,52 AP**. ROR đơn giản hơn, ít xoá điểm thật hơn.
   - Thời gian/frame đo được (số thật từ lần chạy của bạn, trên ~35.000 điểm).

4. **Không wire vào pipeline.** Ticket 10 mới làm việc nối arm. Chỉ cần hàm + test + doc.

## Ràng buộc

- KHÔNG sửa: `spray/plume.py`, `spray/plume_transform.py`, `spray/model_routing.py`, `spray/pipeline.py`,
  `mit/**`, `third_party/**`, bất kỳ file test cũ nào.
- KHÔNG đổi `PlumeConfig`, KHÔNG thêm dependency, KHÔNG sửa `requirements*.txt`.
- KHÔNG bật background process; nếu chờ thì chờ trong foreground.
- Chỉ `git add` đúng 3 file bạn tạo.

## Nghiệm thu (tự chạy trước khi commit, dán output vào câu trả lời)

```bash
CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/
```
Phải ra **60 passed** (57 cũ + 3 mới), 0 failed.

```bash
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -c "
import numpy as np, time
from spray.denoise import ror_filter
rng=np.random.default_rng(0)
dense=rng.normal(0,0.2,(200,3)); dense[:,0]+=10
stray=np.array([[60.,60.,1.],[60.,60.,1.5],[60.,60.,2.]])
p=np.vstack([dense,stray]).astype('float32')
p=np.hstack([p,np.zeros((len(p),2),'float32')])
m,s=ror_filter(p)
print('removed', s['n_in']-s['n_out'], 'frac', round(s['frac_removed'],4), 'ms', round(s['time_ms'],1))
print('stray kept?', m[-3:])
"
```
Điểm lạc phải bị bỏ. Rồi đo thời gian trên 35.000 điểm uniform trong `±54 m` và in ra `time_ms`.

## Commit

Đúng một commit, message:

```
feat(denoise): add radius-outlier-removal filter for arm B0
```

Cuối câu trả lời in: `git log --oneline -1`, `git status --porcelain`, và số `passed`.