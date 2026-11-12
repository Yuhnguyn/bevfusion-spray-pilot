# 29h — Bỏ `vz` và bỏ trần: hai thứ KHÔNG có trong paper

Type: task
Status: ready-for-agent
Follows: 29g-acceptance (`6b4652e`), paper-qa §13 (`462e8c6`)
Owner: PM dispatch → opencode

## Căn cứ — NotebookLM, nguyên văn paper (2026-11-12)

| câu hỏi | paper trả lời |
|---|---|
| có trọng lực? | **KHÔNG**. Chỉ `F_D = ½ρc_D A v_rel²`, `v ← C(v_w+v)²Δt + v`, `C = −0,15 m⁻¹` |
| có `vz` ban đầu? | **KHÔNG**. *"the velocity of the moving object is set as an initial cluster velocity"* — thuần ngang |
| định nghĩa chiều cao plume? | **KHÔNG**. *"height"* chỉ dùng cho **water film height** / góc elevation LiDAR |
| so phân bố `z`? | **KHÔNG**. Chỉ so tổng điểm (Fig 11a), phân bố cự ly (Fig 12), số cụm (Fig 11b) |

Chi tiết: `docs/reference/paper-qa-notebooklm.md` §13.

## Hai lỗi bù nhau trong code

| # | code hiện tại | paper | nhãn thật |
|---|---|---|---|
| 1 | `INITIAL_VZ_MAX_MPS = 5.0`, `vz ~ U(0, 5)` mỗi cụm (`spray/plume_state.py:93`) | **không có** | `[CODE] dee.cpp:540` — không phải paper |
| 2 | `prune(ceilings=...)` xoá cụm `pos[2] > ceiling` (`spray/plume_state.py`, `spray/plume.py:498–502`) | **không có** | `[CHỌN]` của mình, thêm để bù (1) |

Hệ quả đo được: `T = 0,02·wfh·(v−50)+0,2` dài ở tốc độ cao ⇒ `vz·T` = 0,5 m @50, 3,0 m @100,
4,5 m @130, trong khi trần = đỉnh box 2,62 m ⇒ cụm bị xoá oan ⇒ `alive/target` giảm đơn điệu
**2,34 → 0,71** từ 50 → 130 km/h (`docs/measurements/29f-cluster-visibility.md`).

## Việc 1 — bỏ `vz`

- `INITIAL_VZ_MAX_MPS` → **0,0**, kèm comment `[PAPER] arXiv 2212.08558 §III-C: no vertical initial
  velocity; v0 = object velocity` và ghi rõ `dee.cpp:540` có `vz` nhưng paper không.
- Chỗ spawn: `vz = float(rng.uniform(0.0, cfg.initial_vz_max_mps))` giữ nguyên code (uniform(0,0) = 0),
  **không** xoá dòng — để nếu cần bật lại thì chỉ đổi hằng số.

## Việc 2 — bỏ trần

- `PlumeState.prune(ceilings=...)`: bỏ nhánh `above`, hoặc để tham số `ceilings=None` mặc định và
  **không truyền** từ `inject_plume_stateful`.
- Xoá dòng `ceilings[index] = float(box[2] + box[5] / 2.0)` trong `spray/plume.py`.
- Giữ luật `age > max_age_factor * T` — luật này là `[CODE] dee.cpp:445–450`, **có** trong paper.
- Test nào kiểm `ceilings` thì sửa thành kiểm "cụm không bị xoá vì độ cao".

## Việc 3 — đo lại

Chạy `scripts/measure_29f.py` (đã có), ghi đè `docs/measurements/29f-cluster-visibility.md`.
Thêm cột **`h p5/med/p95`** của detection sinh ra (tính như `measure_29ec.py`: `det_z − ROAD_Z_M`).

Báo các số sau, **trước và sau** khi sửa:

| đại lượng | lấy ở đâu |
|---|---|
| `alive/target` 9 mốc | bảng §1 của `29f` |
| `alive/real`, `visible/real`, `dbscan/real` 9 mốc | bảng §1 |
| `h p5/med/p95` | đo mới |
| `det_per_alive` | bảng §1 |

## Tiêu chí nghiệm thu

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| F1 | `alive/target` | **0,95–1,05** ở 9 mốc × 2 lớp (bỏ trần ⇒ không còn bị xoá oan) |
| F2 | `visible/real` | **0,75–1,25** ở 9 mốc × 2 lớp |
| F3 | `h p5/med/p95` | 0,111 / 1,197 / 2,264 ± 0,20 m (A4 của 29e-d) |
| F4 | test | **≥ 316 passed**, 0 failed |
| F5 | `points_clean` | byte-equal |
| F6 | `capped` | 0 ở 4 tốc độ |
| F7 | không đổi `eps`/`minPts`/`Ω_tia`/`visible/alive` | grep xác nhận |

**Cửa chặn:** nếu F1 đạt mà F3 trượt xa (> 0,35 m ở p95) ⇒ **DỪNG, báo PM** — nghĩa là chiều cao
plume không đến từ vị trí đặt mà từ chỗ khác, cần chẩn đoán mới.

## Không được làm

- Không thêm trọng lực (paper không có).
- Không giảm `vz` theo tốc độ — **bỏ hẳn**, không phải hiệu chỉnh.
- Không đổi `eps`/`minPts`/`Ω_tia`.
- Không sửa bảng `_CLUSTER_VISIBLE_BY_SPEED` trong ticket này (bảng đã khớp Bảng 1; nếu F2 trượt thì
  báo số, PM quyết).
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.