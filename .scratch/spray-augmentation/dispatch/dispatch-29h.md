# Dispatch 29h — opencode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `462e8c6` (tree sạch trừ `graphify-out/` untracked).
Baseline test **đo hôm nay**: `316 passed, 4 skipped, 0 failed`. Số thật khác thì DỪNG, báo PM.

## Đọc trước (chỉ 4 file, đừng thám hiểm thêm)

1. `.scratch/spray-augmentation/issues/29h-drop-vz-ceiling.md` — ticket, nguồn duy nhất của mọi số.
2. `docs/reference/paper-qa-notebooklm.md` §13 — nguyên văn paper về gravity/`vz`/chiều cao.
3. `spray/plume_state.py` — `INITIAL_VZ_MAX_MPS`, `prune()`, chỗ spawn `vz`.
4. `spray/plume.py` — `inject_plume_stateful`, chỗ dựng `ceilings`.

## Bối cảnh — số đã có, không suy lại

`alive/target` giảm đơn điệu **2,34 → 0,71** từ 50 → 130 km/h. Nguyên nhân: `vz ~ U(0,5)` mỗi cụm
+ không có trọng lực ⇒ cụm bay lên `vz·T` = 0,5 m @50, 3,0 m @100, 4,5 m @130, vượt trần box 2,62 m
⇒ bị `prune(ceilings)` xoá oan.

Paper **không có** `vz` và **không có** trần. Hai thứ này là `[CODE]`/`[CHỌN]` của mình và bù nhau.

## Việc 1 — bỏ `vz`

`INITIAL_VZ_MAX_MPS = 5.0` → **0,0**, comment `[PAPER] arXiv 2212.08558 §III-C: no vertical initial
velocity; v0 = object velocity`, ghi rõ `dee.cpp:540` có `vz` nhưng paper không. **Giữ** dòng
`vz = rng.uniform(0.0, cfg.initial_vz_max_mps)` (uniform(0,0) = 0) để bật lại chỉ cần đổi hằng số.

## Việc 2 — bỏ trần

- `PlumeState.prune()`: bỏ nhánh `above` (hoặc `ceilings=None` mặc định).
- `spray/plume.py`: xoá `ceilings[index] = float(box[2] + box[5] / 2.0)` và không truyền `ceilings`.
- **Giữ** luật `age > max_age_factor * T` — cái này là `[CODE] dee.cpp:445–450`, có trong paper.
- Test nào kiểm `ceilings` thì sửa thành kiểm "cụm không bị xoá vì độ cao".

## Việc 3 — đo lại

Chạy `scripts/measure_29f.py`, ghi đè `docs/measurements/29f-cluster-visibility.md`. **Thêm cột
`h p5/med/p95`** của detection sinh ra (tính `det_z − ROAD_Z_M`, như `measure_29ec.py`).

Báo **trước và sau** cho: `alive/target`, `alive/real`, `visible/real`, `dbscan/real`, `h p5/med/p95`,
`det_per_alive` — 9 mốc × 2 lớp.

## Tiêu chí

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| F1 | `alive/target` | **0,95–1,05** ở 9 mốc × 2 lớp |
| F2 | `visible/real` | **0,75–1,25** ở 9 mốc × 2 lớp |
| F3 | `h p5/med/p95` | 0,111 / 1,197 / 2,264 ± 0,20 m |
| F4 | test | **≥ 316 passed**, 0 failed |
| F5 | `points_clean` | byte-equal |
| F6 | `capped` | 0 ở 4 tốc độ |
| F7 | `eps`/`minPts`/`Ω_tia`/`visible/alive` | không đổi, grep xác nhận |

**Cửa chặn:** F1 đạt mà F3 trượt xa (p95 lệch > 0,35 m) ⇒ **DỪNG, báo PM**.

## Ràng buộc

- Không thêm trọng lực. Không giảm `vz` theo tốc độ — **bỏ hẳn**.
- Không sửa `_CLUSTER_VISIBLE_BY_SPEED` trong ticket này.
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29f.py
grep -n "INITIAL_VZ_MAX_MPS\|ceilings" spray/plume_state.py spray/plume.py
```

## Báo cáo cuối (đúng 7 dòng)

```
VZ              : <gia tri moi, file:line, comment paper>
CEILING         : <da bo o dau, con luat age giu nguyen>
ALIVE/TARGET    : <9 moc x 2 lop, truoc -> sau>
VISIBLE/REAL    : <9 moc x 2 lop, truoc -> sau>
H P5/MED/P95    : <truoc -> sau, so voi 0,111/1,197/2,264>
F1-F3           : <moc nao dat, moc nao truot>
F4-F7           : <pytest / byte-equal / capped / grep khong doi>
```