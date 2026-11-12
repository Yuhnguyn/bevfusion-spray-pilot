# Dispatch 29e-d-iii — opencode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `c46e751` (tree sạch trừ `graphify-out/` untracked).
Baseline test **đo hôm nay**: `1 failed, 315 passed, 4 skipped` — fail là
`test_radius_median_does_not_grow_with_speed` (`0.3844 == 0.3 ± 0.06`). Số thật khác số này thì DỪNG, báo PM.

## Đọc trước (chỉ 4 file, đừng thám hiểm thêm)

1. `.scratch/spray-augmentation/issues/29e-d-iii-gen-overlap.md` — ticket, nguồn duy nhất của mọi số.
2. `docs/measurements/29ed2-overlap.md` — số chồng cụm trên dữ liệu thật.
3. `docs/measurements/29ed-real-distributions.md` — `r_cl`/`P_det`/`elong` đã khớp paper.
4. `scripts/measure_29ed2.py` — tái dùng logic đo chồng cụm, đừng viết lại từ đầu.

## Thứ tự bắt buộc

### Việc 1 — revert hằng số sai (làm trước, phải xanh test)

- `spray/plume_state.py`: xoá `RADIUS_MU_BY_CLASS`, `RADIUS_SIGMA_BY_CLASS`; `radius_mu`/`radius_sigma`
  về scalar **−1,2 / 0,8** (paper). Bỏ `Mapping`/`field` nếu không còn dùng.
- `spray/raycast.py`: xoá `P_DET_MU_BY_CLASS`, `P_DET_SIGMA_BY_CLASS`, `p_det_params_for_class` nếu
  không còn call site. `p_det_mu`/`p_det_sigma` về **−2,3 / 1,09**.
- `spray/beam_model.py` + `tests/test_beam_model.py`: revert phần thêm `vehicle_class` nếu nó chỉ phục
  vụ dict vừa xoá. Kiểm call site trước khi xoá.
- Xoá `tests/test_plume_measured_distributions.py` nếu nó chỉ kiểm hai dict vừa xoá.
- **KHÔNG** xoá `tests/test_plume_lifetime.py::test_radius_median_does_not_grow_with_speed`.
- `scripts/measure_29ec.py`: bỏ tham số `vehicle_class` nếu hàm nhận không còn dùng.

Xong việc 1 phải chạy `pytest -q tests/` → **0 failed**.

### Việc 2 — đo chồng cụm phía generator

`scripts/measure_29ed3.py`: generator stateful trên `cal`, 3 scene × 30 frame/ô, 2 lớp, 9 tốc độ;
tính `nn`, `nn_norm`, `overlap_frac`, `pts_in_overlap`, `n_merged`, `nn_merged` trên **detection sinh
ra**. Bảng real vs gen + cột `Δ overlap_frac`. Ghi `docs/measurements/29ed3-gen-overlap.md`.

**Cửa chặn:** nếu `overlap_frac` của gen **đã ≥ 40 %** ⇒ giả thuyết "vùng đặt quá rộng" sai ⇒
**DỪNG, báo PM**, không sửa gì thêm.

### Việc 3 — chỉ khi việc 2 cho thấy gen chồng ít hơn real

Thu hẹp vùng đặt trong `spray/plume.py` (`inject_plume_stateful`, chỗ dựng `center`/`extents`) để
`overlap_frac` gen tiến về 60–65 %.

**CẤM** thêm cơ chế gom cụm / cụm-của-cụm / đặt theo nhóm. Paper chỉ cho: **uniform, độc lập từng
cụm, trong vùng sau xe**. Chỉ được đổi kích thước vùng hoặc mật độ trong vùng.

Nếu bạn cho rằng phải thêm cơ chế khác ⇒ **DỪNG, báo PM kèm số**.

Đúng **1 vòng** sửa → đo lại. Trượt thì dừng, báo số.

## Ràng buộc

- Không train, không đụng `kaggle/`, không tune trên `held-out`.
- Không thêm `*_PER_KMH`.
- **Không commit.**
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
grep -rn "BY_CLASS" spray/ ; echo "(rong = ok)"
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29ed3.py
```

## Báo cáo cuối (đúng 7 dòng)

```
REVERT          : <da xoa gi, file nao>
PYTEST          : <N passed, M failed, K skipped>
BY_CLASS        : <grep rong hay khong>
OVERLAP gen     : <overlap_frac 2 lop x 9 toc do>
DELTA vs real   : <Δ overlap_frac @100 va @130>
VUNG DAT        : <co sua khong; neu co thi sua gi, so truoc/sau>
C6-C7           : <byte-equal / capped>
```