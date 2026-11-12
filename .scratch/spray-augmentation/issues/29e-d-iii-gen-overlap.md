# 29e-d-iii — Revert hằng số sai, đo chồng cụm phía generator, thu hẹp vùng đặt

Type: task
Status: ready-for-agent
Follows: 29e-d-ii (`c46e751`)
Owner: PM dispatch → opencode (mistral/deepseek-v4-1-flash-1017)

## Số đo đã có (không suy lại)

### Chồng cụm trên `cal` — `docs/measurements/29ed2-overlap.md`

| đại lượng | giá trị | cửa chặn |
|---|---:|---|
| `overlap_frac` (gộp) | **62,7 %** | 5 % |
| `pts_in_overlap` | **87,8 %** | — |
| median `nn` (tâm→tâm) | **0,684 m** | — |
| median `nn_norm = nn/(r_i+r_j)` | **0,576** | <1 = chồng |
| cụm đã bị gộp (`elong>1,5`) | **46,4 %** | — |
| Crafter@100 | 64,7 % chồng, `nn` 0,656 m | — |
| Golf@100 | 65,5 % chồng, `nn` 0,667 m | — |
| dải `<15 m` | 63,7 % chồng | — |
| dải `25–40 m` | 34,0 % chồng | — |

@50 km/h chỉ **11,1 %** (vì chỉ 4,5 cụm/frame) — tức chồng cụm là hiện tượng **tăng theo số cụm**.

### Phân bố paper đã khớp — KHÔNG cần cắm số

| đại lượng | `cal` | paper |
|---|---:|---:|
| `r_cl` median | 0,271 m | 0,30 m |
| `P_det` median | 0,035 | 0,10 |
| `elong` median | 1,477 | 1,48 |

## Việc 1 — REVERT hằng số đo sai trong `spray/`

Commit `6c775e6` đã cắm `RADIUS_MU_BY_CLASS = {"crafter": -0.928, "golf": -0.850}` vào
`spray/plume_state.py` và `P_DET_MU_BY_CLASS = {"crafter": -4.064, "golf": -4.415}` vào
`spray/raycast.py`. Hệ quả: median bán kính sinh ra = e^−0,928 = **0,395 m**, trong khi đo được
**0,271 m** và paper **0,30 m**. Test `tests/test_plume_lifetime.py::test_radius_median_does_not_grow_with_speed`
**đang fail**: `0.3844 == 0.3 ± 0.06`.

Lý do: MLE lognormal bị đuôi chi phối (p99 = 12 m do DBSCAN nối điểm dọc scan line), nên `µ` fit
**không** tái tạo median đo được. Fit không dùng được.

**Phải làm:** đưa `radius_mu`/`radius_sigma` và `p_det_mu`/`p_det_sigma` về **hằng số paper**
(`−1,2 / 0,8` và `−2,3 / 1,09`), xoá hai dict `*_BY_CLASS` cùng hàm `p_det_params_for_class` nếu
không còn ai gọi. Giữ fallback paper cho mọi lớp. Xoá/bỏ test nào chỉ kiểm dict vừa xoá; **không**
xoá `test_radius_median_does_not_grow_with_speed` — nó là test canh đúng.

Sau việc 1: `pytest -q tests/` phải **xanh toàn bộ** (baseline hiện tại: 1 failed, 315 passed,
4 skipped — phải thành 316 passed, 4 skipped hoặc hơn, **0 failed**).

## Việc 2 — đo chồng cụm phía GENERATOR

Viết `scripts/measure_29ed3.py`: chạy generator (đường stateful, `PlumeTransform` + raycast) trên
`cal`, 3 scene × 30 frame/ô, 2 lớp, 9 tốc độ, rồi tính **đúng các đại lượng của 29ed2** trên
**detection sinh ra** (không phải điểm thật): `nn`, `nn_norm`, `overlap_frac`, `pts_in_overlap`,
`n_merged`, `nn_merged`.

In bảng **so sánh real vs gen** theo lớp × tốc độ, cột cuối là `Δ overlap_frac`. Ghi
`docs/measurements/29ed3-gen-overlap.md` (**file mới**).

Đây là phép đo **quyết định**: nếu `overlap_frac` của gen đã ≥ 40 % thì giả thuyết "vùng đặt quá
rộng" **sai** ⇒ dừng, báo PM, không sửa gì thêm.

## Việc 3 — chỉ khi việc 2 cho thấy gen chồng ít hơn real

Thu hẹp vùng đặt cụm trong `spray/plume.py` (`inject_plume_stateful`, chỗ dựng `center`/`extents`
của khối sau đuôi) để `overlap_frac` của gen tiến về 60–65 %.

**Ràng buộc cứng — paper không cho phép thêm cơ chế:**

> *"spheres are positioned with a **uniform distribution** in the region behind every moving object…
> A uniform distribution was chosen as a first estimate, as no other form of distribution was visible."*

⇒ **CẤM** thêm bước gom cụm / đặt cụm theo nhóm / cụm-của-cụm. Chỉ được **đổi kích thước vùng đặt**
(hoặc mật độ trong vùng), giữ nguyên: uniform, độc lập từng cụm, trong vùng sau xe.

Nếu bạn cho rằng phải thêm cơ chế khác ⇒ **DỪNG, báo PM kèm số**. Đó là quyết định của PM.

Cho phép **1 vòng** sửa → đo lại. Trượt thì dừng, báo số.

## Tiêu chí nghiệm thu

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| C1 | `pytest -q tests/` | **0 failed**, ≥316 passed, 4 skipped |
| C2 | `spray/` không còn `*_BY_CLASS` | `grep -rn "BY_CLASS" spray/` rỗng |
| C3 | median bán kính sinh ra | 0,30 m ± 20 % (test đã có canh) |
| C4 | `overlap_frac` gen vs real | in được 18 ô, có cột Δ |
| C5 | nếu đã sửa vùng đặt: `overlap_frac` gen | ≥ 40 % ở @100 và @130 |
| C6 | `points_clean` | byte-equal |
| C7 | `capped` | 0 ở 4 tốc độ |

## Không được làm

- Không tune trên `held-out`. Không sửa `docs/measurements/semantic-spray-*.md` của 29d.
- Không thêm `*_PER_KMH`, không thêm cơ chế gom cụm.
- Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.