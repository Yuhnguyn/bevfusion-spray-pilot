# Dispatch 29e-d-ii — CommandCode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `6c775e6` (tree sạch, trừ `graphify-out/` untracked). Baseline: **299 passed, 4 skipped**.

## Đọc trước

1. `.scratch/spray-augmentation/issues/29e-d-ii-overlap.md` — ticket, nguồn duy nhất của mọi số đích.
2. `docs/measurements/29ed-real-distributions.md` — số 29e-d đã đo (r_cl, P_det, elong khớp paper).
3. `docs/measurements/29ec-range-buckets.md` — bảng 4 dải cự ly của 29e-c.
4. `scripts/measure_29ed.py` — script đo hiện có, sửa 3 lỗi trong đó chứ đừng viết lại từ đầu.

## Thứ tự bắt buộc

### Bước 1 — sửa 3 lỗi của `scripts/measure_29ed.py`

1. `_stats()` khởi tạo `p10 = nan` rồi chỉ điền quantile trong tham số `quantiles` (mặc định
   50/90/99) ⇒ cột `p10` luôn `nan`. Sửa cho `p10` được tính thật.
2. `P_det` fit lognormal ra `µ=−4,06, σ=2,60` ⇒ mean 0,50, trong khi mean đo được 0,118. In thêm
   fit trên **tập lọc** `elong ≤ 1.2 và P_det ≤ 1.0` (cụm gần cầu, chưa bị gộp), kèm số cụm còn lại.
3. Thêm cột `n_max` trung vị theo dải cự ly, cạnh tỉ lệ `P_det > 1` đã có.

Chạy lại, ghi đè `docs/measurements/29ed-real-distributions.md`.

### Bước 2 — viết `scripts/measure_29ed2.py` (đo chồng cụm)

Với mỗi frame trên `cal` (3 scene × 30 frame/ô, 2 lớp, 9 tốc độ), lấy tâm cụm DBSCAN
(0,7°/minPts=3) trên điểm label 2, tính `nn`, `nn_norm = nn/(r_i+r_j)`, `overlap_frac`,
`pts_in_overlap`, `n_merged` (`elong > 1.5`), `nn_merged`. In bảng theo lớp × tốc độ và theo 4 dải
cự ly. Ghi `docs/measurements/29ed2-overlap.md`.

**Cửa chặn: `overlap_frac < 5 %` ⇒ dừng, báo PM.** Không được sửa generator.

### Bước 3 — không cắm số

**Không sửa `spray/`.** `P_DET_MU_BY_CLASS` đang có trong `spray/raycast.py` giữ nguyên.

## Ràng buộc

- `spray/` phải **không đổi** so với `6c775e6` — PM sẽ `git diff --stat spray/` để kiểm.
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`; `if __name__ == "__main__":`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29ed.py
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29ed2.py
git diff --stat spray/
```

## Báo cáo cuối (đúng 6 dòng)

```
OVERLAP         : <overlap_frac 2 lop x 9 toc do>
PTS_IN_OVERLAP  : <% diem nam trong cum chong nhau, theo lop>
NN_NORM         : <median nn_norm, va median cua cum elong>1,5>
P10 FIX         : <p10 Crafter@100 / Golf@100 truoc va sau>
P_DET FILTERED  : <fit mu/sigma/mean tren tap loc, so cum con lai>
SPRAY DIFF      : <git diff --stat spray/ phai rong>
```