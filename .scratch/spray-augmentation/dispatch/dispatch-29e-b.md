# Dispatch 29e-b — CommandCode (PM: Hermes)

Skill: tdd
Repo: /Users/huynguyen/projects/bevfusion-spray-pilot
HEAD: `885e290` + **working tree chưa commit** (29e cắt ngang ở phút 61). Baseline đã xác nhận:
`pytest -q tests/` → **294 passed, 4 skipped**.

## Đọc trước khi làm

1. `.scratch/spray-augmentation/issues/29e-b-population-block.md` — ticket, có bảng đích.
2. `.scratch/spray-augmentation/issues/29-ray-casting-attenuation.md` — mục
   “Biên bản nghiệm thu PM (2026-11-11) — ĐẠT MỘT PHẦN”.
3. `.scratch/spray-augmentation/issues/29e-wire-raycast.md` — hợp đồng E1 (đã xong, không phá).
4. `docs/measurements/semantic-spray-clusters-by-speed.md` — Bảng 1, nguồn mọi số đích.

## Hiện trạng working tree (đừng revert)

- **E1 xong và đã có bằng chứng**: `spray/spray_context_transform.py`,
  `scripts/build_plume_speed_index.py`, `raycast_frame` được gọi trong `PlumeTransform`, marker
  `PLUME_RAYCAST beams=… hit=… det=… att_m=… capped=… ms=…`, `points_clean` byte-equal.
  **Không sửa** các file này trừ khi test đỏ.
- **E2 sai hướng**: `RADIUS_MEDIAN_PER_KMH = 0.0055` (plume_state.py) — **xoá**, thay bằng bảng.

## Checkpoint B1 — dân số + bán kính (làm trước, đo trước)

1. `WFH_REF_MM = 1.0`; `cluster_spawn_rate_for_speed_abs` phải cho `alive/frame` khớp bảng ở
   `wfh_ref` (hiện 42 vs 18,65 @130 — sai 2,25×).
2. Xoá `RADIUS_MEDIAN_PER_KMH`; thêm `RADIUS_MEDIAN_BY_KMH` (9 mốc, nội suy tuyến tính) theo bảng
   trong ticket; dùng cho `radius_mu` khi spawn; giữ `σ = 0,8`, `radius_max_m = 1,0`.
3. Đo bằng `scripts/measure_29eb.py` (tự viết): 30 frame × 3 scene × 9 mốc × 2 lớp, `wfh_ref`.
   In bảng: alive/frame, noise/frame, det/cụm mean, h p5/med/p95, p95|y|, latency, capped.
4. **Dừng và báo số** nếu A1–A3 không vào ngưỡng sau khi sửa 2 mục trên. Không quét thêm tham số.

## Checkpoint B2 — khối đuôi + phong bì ngang

5. `PlumeConfig.tail_block_height_frac = (0.05, 0.92)`.
6. Kẹp ngang: `|pos[1] − y_block| ≤ 2.43 m` mỗi bước; cụm không được trôi ra ngoài phong bì đo.
7. Đo lại, đối chiếu A4 (chiều cao 3 phân vị ±0,20 m) và A5 (p95|y| 2,308 ±15 %).

## Ràng buộc

- Chỉ sửa generator; **không train**, không đụng `kaggle/train/ab_run.py` ngoài phần context đã có.
- Không tune trên `held-out`; mọi tham số đo trên `cal`.
- Không xoá/nới test cũ. Thêm test cho: nội suy bảng bán kính, `wfh_ref`, frac mới, kẹp ngang.
- **Không commit.** PM nghiệm thu và commit.
- macOS: không có `timeout`; `multiprocessing` = spawn ⇒ `if __name__ == "__main__":`.
  conda: `CONDA_NO_PLUGINS=true` (plugin nội bộ gây lỗi giả).

## Lệnh kiểm tra (dùng đúng như PM sẽ chạy)

```
cd /Users/huynguyen/projects/bevfusion-spray-pilot
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q tests/
CONDA_NO_PLUGINS=true PYTHONPATH=. /opt/anaconda3/bin/python scripts/measure_29eb.py
```

## Báo cáo cuối (PM đọc đúng 6 dòng này)

```
B1 alive/frame      : <9 số> vs bảng
B1 noise/frame      : <9 số> vs bảng
B1 det/cụm mean     : <9 số> vs bảng
B2 h p5/med/p95     : <số>  (đích 0,111 / 1,197 / 2,264)
B2 p95|y|           : <số>  (đích 2,308)
latency/capped/marker: <số>
pytest              : <số passed/skipped>
```