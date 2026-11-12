# 29g — Nghiệm thu PM: D3′ cũng sai đơn vị, lần thứ ba

Type: research
Status: **closed — không sửa bảng spawn rate**
Follows: 29f-acceptance (`460b00f`), 29g (`e8ad035`)
Owner: PM

## Worker làm đúng, và dừng đúng cửa chặn

- Sửa bug `render()`: `high` → `low`, doc §3 giờ ghi **"2/18 ô ≤ 0,7× (Golf@120, Golf@130)"** — khớp
  tính tay của PM. Thêm 4 test (`tests/test_measure_29f_render.py`).
- **Không sửa** bảng Crafter: vòng 1 chỉ đưa 2/9 mốc vào khoảng đích ⇒ trượt cửa chặn 3/9 ⇒ dừng.
- `spray/` **sạch** (`git diff --stat spray/` rỗng). Test **316 passed, 4 skipped**.

## Dữ kiện worker đưa ra — đúng và quan trọng

1. **`dbscan` bão hoà theo bảng spawn rate.** Nhân cả bảng ×2 tại @100 chỉ đưa `dbscan` 12,89 → 19,99
   (ratio 0,59 → 0,92) — **không tuyến tính**. Nhân ×1,44 (đúng mục tiêu) chỉ được ~17,6 (0,81).
2. **Cơ chế:** số cụm `alive` bị DBSCAN gộp đã 4,8–25,5, `phủ max` tới 7,6. Thêm cụm chỉ làm DBSCAN
   gộp thêm, không tách được ở `eps = 0,7°`.
3. **Nghịch lý @70:** `dbscan` **giảm** (8,60 → 7,51) khi `alive` tăng 26,5 → 43,5.
4. Vòng 2 cho số **y hệt** vòng 1 ⇒ không có vòng nào hội tụ.

## PM tính lại — D3′ là tiêu chí SAI, lần thứ ba

Bảng đầy đủ (Crafter, 9 mốc):

| km/h | alive | visible | dbscan | real | `dbscan/visible` | `visible/real` | `alive/real` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 9,4 | 4,6 | 2,9 | 4,5 | 0,64 | 1,01 | 2,08 |
| 60 | 21,3 | 11,9 | 5,8 | 9,7 | 0,49 | 1,23 | 2,18 |
| 70 | 26,5 | 13,0 | 8,6 | 16,4 | 0,66 | 0,79 | 1,61 |
| 80 | 30,7 | 13,7 | 9,9 | 16,2 | 0,72 | 0,85 | 1,90 |
| 90 | 25,0 | 11,5 | 16,2 | 18,7 | **1,42** | 0,61 | 1,34 |
| 100 | 28,6 | 13,4 | 12,9 | 21,8 | 0,96 | 0,61 | 1,31 |
| 110 | 23,8 | 11,2 | 16,8 | 18,3 | **1,51** | 0,61 | 1,30 |
| 120 | 13,3 | 7,0 | 12,5 | 15,7 | **1,79** | 0,44 | 0,85 |
| 130 | 12,8 | 6,7 | 8,4 | 15,0 | **1,25** | 0,45 | 0,85 |

`dbscan/visible` biến thiên **0,49 – 1,79**, không đơn điệu theo `alive`:

- `det/alive` thấp (4–6) ⇒ `dbscan/visible` **0,49–0,72**: cụm **biến mất** (dưới `minPts = 3`).
- `det/alive` cao (10–14) ⇒ `dbscan/visible` **1,42–1,79**: cụm **bị tách** (tia cắt cầu ở nhiều ring).

⇒ **DBSCAN trên detection thưa (~6 điểm/cụm) là estimator KHÔNG ỔN ĐỊNH.** DBSCAN trên mảng nước
thật (dày đặc, hàng trăm điểm/cụm) là estimator **ổn định**. So hai thứ này là so estimator không ổn
định với ổn định — **cùng loại lỗi với A1 và `mean det/cụm`**.

## Ba tiêu chí sai liên tiếp, cùng một nguyên nhân

| ticket | tiêu chí | sai ở đâu |
|---|---|---|
| 29c | A1: `visible_cluster_count_for_speed` vs Bảng 1 | so số **lý thuyết** với cụm **DBSCAN** |
| 29e-b | `mean det/cụm` = 47,3 | mean bị **đuôi** chi phối; p50 = 6 |
| 29g | D3′: `dbscan/real` ∈ [0,85; 1,15] | DBSCAN trên **6 điểm/cụm** không ổn định (0,49–1,79) |

Luật rút ra: **trước khi đặt tiêu chí, phải chứng minh đại lượng đo được ổn định** — đo hai lần với
seed khác nhau, hoặc kiểm phương sai theo điều kiện. Không kiểm thì tiêu chí chỉ là ý định.

## Đại lượng ĐÚNG để so — `visible/real`

`visible` = số cụm có ≥ 1 detection, đo trực tiếp trên cụm generator, **không qua DBSCAN**:

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `visible/real` | 1,01 | 1,23 | 0,79 | 0,85 | 0,61 | 0,61 | 0,61 | 0,44 | 0,45 |

TB **0,73**. Xu hướng rõ và đơn điệu theo tốc độ: **khớp ở 50–80, thiếu ở 90–130**. Đây là đại lượng
ổn định (đếm trực tiếp, không phụ thuộc `eps`/`minPts`).

## Quyết định

1. **Không sửa bảng spawn rate** dựa trên `dbscan`. Lý do: estimator không ổn định.
2. **Tiêu chí mới D3″**: `visible/real` ∈ **[0,75; 1,25]** ở 9 mốc × 2 lớp. Chẩn đoán: `dbscan/real`
   in ra nhưng **không chặn**.
3. **Ghi limitation**: DBSCAN trên plume thưa không đếm được cụm; paper dùng DBSCAN trên dữ liệu
   **thật** (dày) để hiệu chuẩn, nên Bảng 1 và generator không so được qua DBSCAN.
4. Việc sửa thật (nếu cần): tăng `visible` ở 90–130 km/h từ 0,61/0,45 lên ~1,0 — nhưng **chỉ sau khi**
   D3″ được đóng băng và commit, để không tune sau khi thấy số.

## Không mở lại

- Không đổi `eps`/`minPts`/`Ω_tia`.
- Không sửa `visible/alive` (0,509 = `exp(−age/T)` của paper).
- Không dùng `dbscan/real` làm tiêu chí chặn ở bất kỳ ticket nào.