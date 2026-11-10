# Bảng góc beam đo được từ SemanticSpray (ring → elevation)

Ngày: 2026-11-11 · PM đo trên máy này · Sinh ra để ticket 29 dùng cho ray casting.

## Kết luận một câu

Ring id trong `velodyne/*.bin` **là beam id thật** (mỗi ring phủ 359,8° azimuth, elevation lệch chuẩn
0,26–0,59° trong một frame), nhưng **bảng góc của nhà sản xuất không dùng được** — các beam trong bản release
này chỉ nằm trong dải ~**−4° … +1°** và ring id đã được đánh lại `0…19`. Phải dùng **bảng đo từ chính dữ liệu**.

## Đo 1 — ring có phải beam không (1 frame, scene `Crafter_dynamic/0000_2021-09-08-14-36-56_0`)

`[ĐO]` 29.178 điểm; ring id `0…28`; `z ∈ [−6,68; +6,53] m`; tầm xa tối đa 130,3 m.

| Ring | n điểm | elevation median | elevation std | azimuth span |
|---:|---:|---:|---:|---:|
| 0 | 1.620 | −3,91° | 17,72° (có outlier) | 359,4° |
| 1 | 1.740 | −2,50° | 0,354° | 359,8° |
| 2 | 1.754 | −1,71° | 0,262° | 359,8° |
| 3 | 1.785 | −1,16° | 0,331° | 359,8° |
| 5 | 1.739 | −0,49° | 0,545° | 359,8° |
| 10 | 1.558 | −0,19° | 0,570° | 359,8° |
| 14 | 1.675 | −0,08° | 0,473° | 358,8° |
| 17 | 765 | −0,06° | 0,591° | 234,1° |
| 20 | 71 | +0,51° | 1,168° | 158,1° |

Đủ 360° azimuth ở các ring dày ⇒ đó là một tia quét hết vòng, không phải một nhóm điểm theo phương vị.
Ring 0 chứa outlier tới `+52°` (std 17,7°) — điểm nhiễu/spray bị gán ring 0 ⇒ **phải dùng median trong IQR,
không dùng mean**.

## Đo 2 — độ ổn định giữa các frame/scene (10 frame rải trên 10 scene)

`[ĐO]` median elevation mỗi ring (robust trong IQR), so với frame đầu:

| Nhóm ring | Số beam | std giữa 10 frame | Đánh giá |
|---|---:|---:|---|
| 9–14 | 6 | **0,05 – 0,13°** | rất ổn định |
| 0–8 | 9 | 0,15 – 0,25° | ổn định |
| 15–19 | 5 | 0,20 – 0,43° | dùng được, mẫu thưa |

⇒ Một bảng góc chung cho cả dataset, sai số ±0,1–0,2° ở các beam dày, là đủ để dựng tia.

## Đo 3 — vì sao bảng hãng lệch 3,49°

`[ĐO]` Bản release không có các beam dưới và trên: `z` toàn frame chỉ `−6,68 … +6,53 m` trong khi tầm xa
130 m. Một scan VLP-32C đầy đủ có beam `−25°` thì ở 130 m phải có `z ≈ −60 m`. Vậy dữ liệu đã bị cắt theo
phương thẳng đứng (hoặc cấu hình cảm biến khác), và ring id được **đánh lại** `0…19` cho các beam còn lại —
đó là lý do so cùng ID với bảng VLP-32C lệch median 3,49° (`docs/plume-v2-measurements.md` §2) trong khi
bảng đo lại ổn định.

## Hệ quả cho ticket 29 (ray casting)

1. Dùng `ring → elevation` **đo được**, lưu trong config (`beam_elevation_deg`), tag `[ĐO]`. Không dùng bảng
   của Velodyne.
2. Mật độ beam gần chân trời rất dày: 20 beam trong ~5° ⇒ cụm ở 20–50 m (bán kính góc 0,3–1°) chỉ cắt **vài
   beam** ⇒ số detection/cụm ~2,5 như paper báo. Đây là lời giải cho câu "10–30 hay 2,5 điểm/cụm": số điểm
   **nở ra** từ số beam cắt qua cụm, không phải hằng số ta chọn.
3. Vẫn giữ `compute_elevation_deg()` (tính từ toạ độ) làm đường dự phòng khi context không có bảng beam.

## Cách tái lập

Đoạn mã dùng để ra các bảng trên (chạy từ root repo, không cần GPU):

```python
import numpy as np, glob
for f in sorted(glob.glob('data/SemanticSprayDataset/*/*/velodyne/*.bin'))[::1500][:10]:
    p = np.fromfile(f, np.float32).reshape(-1, 5)
    x, y, z, ring = p[:,0].astype(float), p[:,1].astype(float), p[:,2].astype(float), p[:,4].astype(int)
    elev = np.degrees(np.arctan2(z, np.hypot(x, y)))
    az = np.degrees(np.arctan2(y, x))
    for r in range(21):
        m = ring == r
        if m.sum() < 100:
            continue
        lo, hi = np.percentile(elev[m], [25, 75])
        inner = elev[m][(elev[m] >= lo) & (elev[m] <= hi)]      # bỏ outlier trong IQR
        print(f, r, m.sum(), float(np.median(inner)), float(np.ptp(az[m])))
```

## Bảng sinh tự động (tái lập bằng `scripts/measure_beam_table.py`)

`[ĐO]` 120 frame / toàn dataset, xuất ra `spray/config/beam_elevation.yaml` (shasum `51c25f6`,
chạy 2 lần cho cùng shasum). `M = 20` beam, `azimuth_step_deg = 0,197307`.

Đo trên **120 frame** rải đều toàn dataset (20 beam, ring id `0…19`).

| ring | n_frame | n_điểm | elevation_median | std_giữa_frame | azimuth_step |
|---:|---:|---:|---:|---:|---:|
| 0 | 120 | 196,007 | -4.0556 | 0.2096 | 0.1776 |
| 1 | 120 | 213,131 | -2.6096 | 0.1689 | 0.1943 |
| 2 | 120 | 213,113 | -1.9589 | 0.1544 | 0.1962 |
| 3 | 120 | 213,166 | -1.3230 | 0.1816 | 0.1960 |
| 4 | 120 | 209,554 | -1.0462 | 0.1990 | 0.1947 |
| 5 | 120 | 206,854 | -0.6554 | 0.1927 | 0.1954 |
| 6 | 120 | 195,169 | -0.5364 | 0.1927 | 0.1975 |
| 7 | 120 | 198,743 | -0.4264 | 0.1829 | 0.1973 |
| 8 | 120 | 196,980 | -0.2715 | 0.1776 | 0.1968 |
| 9 | 120 | 192,550 | -0.2227 | 0.1724 | 0.1975 |
| 10 | 120 | 189,034 | -0.1882 | 0.1636 | 0.1988 |
| 11 | 120 | 192,366 | -0.2169 | 0.1438 | 0.1982 |
| 12 | 120 | 196,080 | 0.0203 | 0.1396 | 0.1972 |
| 13 | 120 | 185,685 | 0.0029 | 0.1273 | 0.1965 |
| 14 | 120 | 191,378 | 0.0238 | 0.1343 | 0.1981 |
| 15 | 120 | 161,602 | -0.0787 | 0.2000 | 0.1973 |
| 16 | 120 | 150,245 | 0.1094 | 0.2245 | 0.1980 |
| 17 | 120 | 112,724 | 0.0883 | 0.3005 | 0.1992 |
| 18 | 120 | 90,306 | -0.0068 | 0.3632 | 0.1983 |
| 19 | 115 | 46,735 | -0.0580 | 1.0764 | 0.2000 |

Bỏ (không phải beam, < 90% số frame có ≥ 100 điểm): 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31

Đã ghi spray/config/beam_elevation.yaml
Beam: 20 (M = 20)
azimuth_step_deg = 0.197307
Elapsed: 10.37 s
