# Dispatch 29e-c — CommandCode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `5720ed9` (working tree sạch). Baseline: `pytest -q tests/` → **294 passed, 4 skipped**.

## Đọc trước

1. `.scratch/spray-augmentation/issues/29e-c-diagnose-then-fix.md` — ticket, **nguồn duy nhất** của
   mọi con số đích.
2. `.scratch/spray-augmentation/issues/29-ray-casting-attenuation.md` — mục “Biên bản nghiệm thu PM
   (2026-11-11) — ĐẠT MỘT PHẦN”.
3. `.scratch/spray-augmentation/issues/29e-wire-raycast.md` — hợp đồng E1 (đã xong, không phá).

**Đừng đọc/đừng dùng** `.scratch/spray-augmentation/issues/29e-b-population-block.md` — ticket đó bị
thay; đích `mean det/cụm` trong đó sai (đuôi phân bố, không phải mục tiêu mô hình).

## Thứ tự bắt buộc

### Bước 1 — chỉ đo, chưa sửa

Viết `scripts/measure_29ec.py` theo mô tả trong ticket (bảng theo 4 dải cự ly, gen vs real,
2 tốc độ 100/130, 2 lớp, 30 frame × 3 scene, `wfh_ref = 1,0`). Chạy, in bảng.

Ghi ra `docs/measurements/29ec-range-buckets.md` (file mới — **không** ghi vào file của 29d/29c).

### Bước 2 — sửa theo bảng

Theo decision tree trong ticket. Tóm tắt phần chắc chắn phải làm bất kể bảng:

- Xoá `RADIUS_MEDIAN_PER_KMH` (đã thêm ở 29e) → `r_cl` về lognormal paper **µ = −1,2, σ = 0,8**
  (`[PAPER, Fig. 5]`, median 0,30 m), `radius_max_m = 1,0`.
- `PlumeConfig.tail_block_height_frac = (0.05, 0.92)`.
- Kẹp `|y − y_block| ≤ 2.43 m` mỗi bước.
- `WFH_REF_MM = 1.0`, spawn rate đóng vòng theo bảng cụm/frame ở `wfh_ref`.

### Bước 3 — đo lại, đối chiếu A1–A10

Đúng **1 vòng** sửa → đo. Trượt thì dừng, báo số, không quét tham số.

## Ràng buộc

- Không train; không đụng `kaggle/`.
- Không tune trên `held-out`.
- Không xoá/nới test cũ; thêm test cho frac mới, kẹp ngang, `wfh_ref`, việc xoá hằng số slope.
- **Không commit.**
- macOS không có `timeout`; `multiprocessing` cần `if __name__ == "__main__":`;
  conda: `CONDA_NO_PLUGINS=true`.

## Lệnh PM sẽ chạy lại

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29ec.py
```

## Báo cáo cuối (đúng 7 dòng)

```
BANG DAI CU LY  : <dán bảng 4 dải × 2 tốc độ, gen vs real>
gen_dropped     : <số điểm bị DBSCAN bỏ, theo dải>
DA SUA          : <liệt kê ngắn>
A1 cum/frame    : <9 số> vs bang
A2 diem/frame   : <9 so>
A3 p50/cum      : <so>
A4 h / A5 |y|   : <so>
A6-A10          : latency / capped / pytest / byte-equal / RuntimeError
```