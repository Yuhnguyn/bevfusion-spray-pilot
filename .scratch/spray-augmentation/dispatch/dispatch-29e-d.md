# Dispatch 29e-d — CommandCode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `40c9c78` (tree sạch). Baseline: **299 passed, 4 skipped** (117 s).

## Đọc trước

1. `.scratch/spray-augmentation/issues/29e-d-measure-distributions.md` — ticket, nguồn duy nhất của
   mọi con số đích.
2. `docs/measurements/29ec-range-buckets.md` — bảng 4 dải cự ly của 29e-c (chỗ mất điểm).
3. `docs/reference/paper-qa-notebooklm.md` mục 10 — định nghĩa `n`, `n_max`, `r_cl`, `P_det` đã hỏi
   NotebookLM, `[PAPER]` chứ không phải suy đoán.

## Thứ tự bắt buộc

### Bước 1 — chỉ đo, KHÔNG sửa generator

`scripts/measure_29ed.py`: với mỗi cụm thật trên `cal` (3 scene × 30 frame/ô, 9 tốc độ, 2 lớp) tính
`d`, `n`, `r_cl` (max khoảng cách tới tâm), `n_max` (dùng đúng `Ω_tia = 2,003e−5 sr` của
`spray/raycast.py`), `P_det = n/n_max`, `elong`. In bảng + fit lognormal (`scipy.stats.lognorm.fit`
hoặc MLE thủ công nếu scipy không có).

Ghi `docs/measurements/29ed-real-distributions.md`.

**Nếu `P_det > 1` quá 5 % số cụm: dừng, báo PM ngay** — nghĩa là giả thiết “cụm là cầu” không đủ,
không được tự nới.

### Bước 2 — cắm số đo

- `radius_mu` / `radius_sigma` ← fit `r_cl` **theo lớp** (Crafter, Golf), ghi `[ĐO 2026-11-11]`.
- `mu_det` / `sigma_det` ← fit `P_det` **theo lớp**, ghi `[ĐO 2026-11-11]`.
- Giữ `RADIUS_MAX_M = 1.0` trừ khi p99 đo được vượt.
- Không thêm hằng số nào khác, không thêm `*_PER_KMH`.

### Bước 3 — đo lại A1–A11

Đúng 1 vòng. Trượt thì dừng, báo số.

## Ràng buộc

- Không train, không đụng `kaggle/`, không tune trên `held-out`.
- Không xoá/nới test cũ; thêm test cho tham số mới theo lớp.
- **Không commit.**
- macOS không có `timeout`; `multiprocessing` cần `if __name__ == "__main__":`;
  `CONDA_NO_PLUGINS=true PYTHONPATH=.`; `env -u PYTHONPATH` khi gọi công cụ ngoài.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29ed.py
```

## Báo cáo cuối (đúng 8 dòng)

```
r_cl fit        : Crafter mu/sigma/median, Golf mu/sigma/median vs paper (-1,2; 0,8; 0,30 m)
P_det fit       : Crafter mu/sigma/mean, Golf mu/sigma/mean vs paper (-2,3; 1,09; 0,18)
P_det > 1       : <ti le %>
elong median    : <so> vs 1,48
cum/frame <15 m : real <so> vs gen <so>
A1 cum/frame    : <9 so x 2 lop>
A2 diem/frame   : <9 so x 2 lop>
A3-A5           : p50 / chieu cao p5-med-p95 / p95|y|
A6-A11          : latency / capped / pytest / byte-equal / RuntimeError / fit tren du lieu sinh
```