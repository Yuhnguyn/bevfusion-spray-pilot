# Dispatch 29f — opencode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `d72abf7` (tree sạch trừ `graphify-out/` untracked).
Baseline test **đo hôm nay**: `312 passed, 4 skipped, 0 failed`. Số thật khác thì DỪNG, báo PM.

## Đọc trước (chỉ 4 file, đừng thám hiểm thêm)

1. `.scratch/spray-augmentation/issues/29f-cluster-count-visible.md` — ticket, nguồn duy nhất của mọi số.
2. `docs/measurements/29ed3-gen-overlap.md` §2 — cột `cụm real` vs `cụm gen` (12,9 vs 21,8 @100).
3. `docs/measurements/29ed-real-distributions.md` §5 — `P_det` gen 0,008 vs cal 0,017.
4. `scripts/measure_29ed3.py` — tái dùng khung dựng DBSCAN + đếm cụm, đừng viết lại từ đầu.

## Thứ tự bắt buộc

### Việc 1 — viết `scripts/measure_29f.py`, chỉ đo

Trên `cal`, 3 scene × 30 frame/ô, 2 lớp, 9 tốc độ. Mỗi ô in: `alive` (số cụm còn sống trong
`state.all_alive()`), `visible` (số cụm có ≥ 1 detection), `dbscan` (số cụm DBSCAN dựng lại từ
detection, ≥ 3 điểm), `alive_not_dbscan = alive − dbscan`, `det_per_alive`, cạnh `real dbscan` (lấy từ
`29ed3`) và `Δ`. Ghi `docs/measurements/29f-cluster-visibility.md` (**file mới**).

### Việc 2 — xác nhận đơn vị đếm của Bảng 1

Đọc `docs/measurements/semantic-spray-clusters-by-speed.md`. Xác nhận Bảng 1 đếm **cụm DBSCAN** hay
**cụm "còn sống"**. Ghi rõ một dòng trong báo cáo. Nếu Bảng 1 đếm DBSCAN thì A1 đạt là trùng hợp.

### Việc 3 — sửa, theo kết quả việc 1

**Cửa chặn:** nếu `alive` ≤ 0,7× real ⇒ lỗi ở **khâu sinh cụm** ⇒ làm 3b. Nếu `alive` ≈ real mà
`dbscan` thấp ⇒ lỗi ở **ray-cast** ⇒ làm 3a. Ghi rõ bạn rơi vào nhánh nào.

- **3a (ray-cast):** kiểm theo thứ tự — (i) phân bố `n_max` theo cự ly, kỳ vọng cụm 0,30 m ở 20 m cho
  ~35 tia (`Ω_cầu/Ω_tia`); (ii) `P_det` hiệu dụng sau Bernoulli từng tia, kỳ vọng `n_max × P_det`;
  (iii) cụm có bị loại vì `max_distance_m = 100` hoặc `rejected_box` không.
- **3b (sinh cụm):** kiểm `cluster_count_for_speed_abs` (`spray/plume_state.py`) và
  `_CLUSTER_VISIBLE_BY_SPEED` (`spray/plume.py`), so trực tiếp Bảng 1, sửa bảng theo số đo, ghi
  `[ĐO 2026-11-12]`.

Cho phép **1 vòng** sửa → đo lại. Trượt thì dừng, báo số.

## Ràng buộc

- **CẤM** đổi `minPts` (3), `eps` (0,7°), `Ω_tia` — recipe paper.
- Không thêm `*_PER_KMH`, không thêm dict theo lớp (vừa revert, đừng đưa lại).
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29f.py
grep -rn "minPts\|MIN_PTS\|eps=" spray/raycast.py spray/plume_state.py | head
```

## Báo cáo cuối (đúng 7 dòng)

```
ALIVE vs REAL   : <alive 2 lop x 9 toc do, kem ti le so voi real>
VISIBLE/DBSCAN  : <dbscan 2 lop x 9 toc do, kem ti le so voi real>
NUT THAT        : <alive_not_dbscan, det_per_alive>
BANG 1 DON VI   : <DBSCAN hay alive>
NHANH           : <3a ray-cast hay 3b sinh cum, vi sao>
DA SUA          : <sua gi, so truoc/sau>
D5-D8           : <pytest / byte-equal / capped / minPts-eps khong doi>
```