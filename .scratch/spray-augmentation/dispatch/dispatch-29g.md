# Dispatch 29g — opencode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `460b00f` (tree sạch trừ `graphify-out/` untracked).
Baseline test **đo hôm nay**: `312 passed, 4 skipped, 0 failed`. Số thật khác thì DỪNG, báo PM.

## Đọc trước (chỉ 4 file, đừng thám hiểm thêm)

1. `.scratch/spray-augmentation/issues/29f-acceptance.md` — nghiệm thu PM, **nguồn duy nhất** của mọi số.
2. `docs/measurements/29f-cluster-visibility.md` §1–2 — bảng `alive`/`visible`/`dbscan`.
3. `scripts/measure_29f.py` — script đo, sửa bug trong `render()`.
4. `spray/plume.py` — `_CLUSTER_VISIBLE_BY_SPEED` và `cluster_visible_target_for_speed`.

## Bối cảnh — số PM đã tính lại, không suy lại

| lớp | `alive/real` | `visible/alive` | `dbscan/real` |
|---|---:|---:|---:|
| Crafter (TB 9 tốc độ) | 1,49 | 0,49 | **0,68** |
| Golf (TB 9 tốc độ) | 1,08 | 0,70 | **0,84** |
| Golf@100 | 0,96 | 0,78 | **1,36** |
| Crafter@100 | 1,31 | 0,47 | **0,59** |

**`visible/alive = 0,49` là ĐÚNG paper**, không sửa: `∫₀^{4T}e^{−a/T}da / 4T = (1−e^{−8})/(2(1−e^{−4})) = 0,509`.

Kết luận cũ trong `29f-cluster-visibility.md` §3 ("16/18 ô alive ≤ 0,7×") là **SAI** — bug đếm
`high` gán nhãn `low`. Thực tế **2/18 ô** dưới 0,7 và **10/18 ô** ≥ 1,0.

## Việc 1 — sửa bug hiển thị trong `scripts/measure_29f.py`

Trong `render()`: biến `high` đếm `alive_ratio > STOP_GATE` nhưng câu in ghi "≤". Đổi thành `low`,
đếm `alive_ratio <= STOP_GATE`, và in đúng số ô dưới ngưỡng. Chạy lại, ghi đè
`docs/measurements/29f-cluster-visibility.md`. **Chỉ sửa phần kết luận §3**, không đổi phép đo.

## Việc 2 — chỉnh bảng Crafter để `dbscan/real` về ~1,0

`_CLUSTER_VISIBLE_BY_SPEED` trong `spray/plume.py` **đã tách theo lớp** (`crafter`, `golf`). Chỉ sửa
nhánh **crafter**.

Mục tiêu: `dbscan/real` của Crafter từ **0,68 → 0,85–1,15** ở 9 mốc.

Cách làm: `dbscan ≈ alive × 0,51 × (tỉ lệ DBSCAN nhận ra)`. Vì `alive/real` của Crafter đã 1,49 (thừa),
nhân thẳng spawn rate lên sẽ làm `alive` phình thêm. **Phải đo trước khi sửa**: chạy `measure_29f.py`
với bảng hiện tại để có baseline từng mốc, rồi chọn hệ số theo **từng tốc độ** (bảng, không slope) để
`dbscan/real` vào khoảng đích.

Ghi `[ĐO 2026-11-12]` cạnh bảng mới, kèm số `dbscan/real` trước/sau từng mốc.

**Cửa chặn:** nếu sau 1 vòng chỉnh mà `dbscan/real` Crafter vẫn < 0,85 hoặc > 1,15 ở quá 3/9 mốc ⇒
**DỪNG, báo PM kèm bảng**, không chỉnh vòng 2.

## Việc 3 — xác nhận Golf không bị ảnh hưởng

`dbscan/real` của Golf phải **không đổi** (0,84 TB; 1,36 @100). Nếu đổi ⇒ bạn đã sửa nhầm nhánh.

## Ràng buộc

- **CẤM** đổi `minPts = 3`, `eps = 0,7°`, `Ω_tia`.
- **CẤM** sửa `visible/alive` — đó là `exp(−age/T)` của paper.
- **CẤM** thêm `*_PER_KMH` hay dict mới theo lớp cho `r_cl`/`P_det` (đã revert 1 lần).
- Không tune trên `held-out`. Không commit.
- macOS không có `timeout`; `CONDA_NO_PLUGINS=true PYTHONPATH=.`;
  `multiprocessing` cần `if __name__ == "__main__":`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29f.py
grep -n "crafter" spray/plume.py | head
```

## Báo cáo cuối (đúng 7 dòng)

```
BUG RENDER      : <sua gi trong render(), so o duoi nguong dung>
BASELINE        : <dbscan/real Crafter 9 moc TRUOC khi sua bang>
BANG MOI        : <9 gia tri crafter sau khi sua>
DBSCAN/REAL     : <9 ti le sau khi sua, so moc trong 0,85-1,15>
GOLF KHONG DOI  : <dbscan/real Golf 9 moc, so voi truoc>
D5-D7           : <pytest / byte-equal / capped>
CUA CHAN        : <co roi vao truong hop DUNG khong>
```