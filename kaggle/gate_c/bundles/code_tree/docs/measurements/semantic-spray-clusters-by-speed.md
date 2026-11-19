# Cụm bụi nước theo tốc độ và cự ly — đo trên `cal` (2026-11-11)

## Vì sao đo

Ticket 29c phải hiệu chỉnh **số cụm sinh ra mỗi chu kỳ** của generator. Mốc ban đầu lấy từ
paper Fig. 11b (**~75 cụm/frame @130 km/h**, **33 @100 km/h**, **21 @80 km/h**). Trước khi lấy
các số đó làm đích, cần biết **chính dataset** cho ra bao nhiêu cụm/frame khi đếm bằng recipe
của paper — nếu không thì generator sẽ được hiệu chỉnh về một con số không tồn tại trong dữ liệu
mà nó phải khớp.

## Phương pháp

| Thành phần | Giá trị |
|---|---|
| Dữ liệu | `data/SemanticSprayDataset`, **chỉ scene vai `cal`** (luật chia ticket 29d) |
| Điểm được đếm | `label == 2` (noise: spray + mưa/phản xạ) |
| Toán tử cụm | DBSCAN trên mặt phẳng `(azimuth, elevation)` `[CHỌN 2026-11-11]` |
| Tham số | `eps = 0,7°` (Euclid trong mặt phẳng góc), `minPts = 3`, elevation snap `0,333°`, azimuth wrap 360° |
| Mẫu | Bảng 1: 15 frame/scene × 3 scene/ô; Bảng 2: 10 frame/scene × 2 scene/ô; frame lấy cách đều trong scene |
| Frame bị bỏ | 0 (mọi frame có `labels.size == points.shape[0]`) |
| 0 GPU | Chỉ đọc `.bin` + `.label`, CPU |

Script dùng lại `spray.semantic_stats.cluster_angular` và `spray.semantic_split.read_dataset` /
`assign_roles`, tức **cùng một toán tử** với cổng `cal`/`held-out` của 29d.

## Bảng 1 — theo lớp xe và tốc độ `[ĐO]`

| group | km/h | frame | noise/frame | cụm/frame | điểm/cụm (median) |
|---|---:|---:|---:|---:|---:|
| Crafter_dynamic | 50 | 45 | 47,6 | 4,18 | 7,8 |
| Crafter_dynamic | 60 | 45 | 179,9 | 11,31 | 5,6 |
| Crafter_dynamic | 70 | 45 | 361,2 | 17,42 | 5,1 |
| Crafter_dynamic | 80 | 45 | 856,0 | 22,02 | 14,6 |
| Crafter_dynamic | 90 | 45 | 945,2 | 20,69 | 15,3 |
| Crafter_dynamic | 100 | 45 | 1.382,0 | **29,24** | 19,4 |
| Crafter_dynamic | 110 | 45 | 1.417,9 | 28,49 | 16,5 |
| Crafter_dynamic | 120 | 45 | 753,4 | 17,58 | 53,8 |
| Crafter_dynamic | 130 | 45 | 877,9 | **17,69** | 36,2 |
| Golf_dynamic | 50 | 45 | 47,8 | 3,62 | 8,9 |
| Golf_dynamic | 60 | 45 | 149,1 | 8,84 | 9,4 |
| Golf_dynamic | 70 | 45 | 305,3 | 11,36 | 8,5 |
| Golf_dynamic | 80 | 45 | 361,1 | 12,87 | 10,8 |
| Golf_dynamic | 90 | 45 | 313,0 | 10,51 | 8,8 |
| Golf_dynamic | 100 | 45 | 566,4 | 18,07 | 6,8 |
| Golf_dynamic | 110 | 45 | 632,8 | 16,69 | 6,6 |
| Golf_dynamic | 120 | 45 | 566,8 | 15,27 | 9,5 |
| Golf_dynamic | 130 | 45 | 666,0 | 16,64 | 7,1 |

## Bảng 2 — tách thêm cự ly `[ĐO]`

| group | km/h | cự ly (m) | frame | noise/frame | cụm/frame | điểm/cụm (median) |
|---|---:|---:|---:|---:|---:|---:|
| Crafter_dynamic | 100 | 20 | 20 | 1.545,3 | 33,30 | 8,8 |
| Crafter_dynamic | 100 | 30 | 20 | 1.756,0 | 29,40 | 32,6 |
| Crafter_dynamic | 110 | 20 | 20 | 1.708,0 | 32,60 | 11,4 |
| Crafter_dynamic | 110 | 30 | 20 | 1.563,9 | 26,60 | 22,6 |
| Crafter_dynamic | 120 | 20 | 20 | 953,5 | 21,95 | 37,2 |
| Crafter_dynamic | 120 | 30 | 20 | 1.116,6 | 21,80 | 50,8 |
| Crafter_dynamic | 130 | 20 | 20 | 890,5 | 18,65 | 49,5 |
| Crafter_dynamic | 130 | 30 | 20 | 1.023,8 | 19,80 | 64,2 |
| Golf_dynamic | 100 | 20 | 20 | 662,5 | 18,80 | 7,8 |
| Golf_dynamic | 100 | 30 | 20 | 446,6 | 14,00 | 6,1 |
| Golf_dynamic | 130 | 20 | 20 | 665,7 | 18,20 | 6,8 |
| Golf_dynamic | 130 | 30 | 20 | 675,1 | 17,55 | 7,7 |

## Kết luận `[ĐO]`

1. **Cụm/frame không đơn điệu theo tốc độ.** Crafter đạt đỉnh **33,3 (20 m) / 29,4 (30 m)** ở
   **100 km/h**, rồi **giảm** còn **18,7 / 19,8** ở **130 km/h**. Noise/frame cũng vậy: đỉnh
   1.545–1.756 điểm/frame ở 100–110 km/h, còn 890–1.116 ở 120–130 km/h.
2. **Cự ly xa ⇒ ít cụm hơn** (20 m nhiều hơn 30 m khoảng 10–20 % ở cùng tốc độ). Xu hướng này
   **ngược** với giả thuyết "paper đo ở 50 m nên mới có 75 cụm": nếu ngoại suy 30 m → 50 m thì
   số cụm còn **giảm**, không tăng lên 75.
3. **Cụm bị nhập khối ở tốc độ cao.** Điểm/cụm (median) Crafter 20 m: **8,8** @100 → **49,5** @130.
   Số cụm giảm trong khi kích thước cụm tăng gần 6 lần ⇒ ở 130 km/h plume là vài khối lớn, không
   phải nhiều cụm nhỏ.
4. **Phần lớn `label == 2` không nằm trong cụm.** Ví dụ Crafter 100 km/h / 20 m: 1.545 điểm/frame
   nhưng 33,3 cụm × ~8,8 điểm ≈ 293 điểm có cụm; phần còn lại là điểm rời (mưa, phản xạ, spray
   loãng) mà DBSCAN bỏ qua. "Cụm/frame" chỉ đếm phần kết đám.
5. **Golf thấp hơn Crafter nhưng không theo tỉ lệ cố định.** Ở 100 km/h / 20 m: 18,8 so với 33,3
   (**0,56×**); ở 130 km/h: 18,2 so với 18,65 (**0,98×**). Không được suy Golf từ Crafter bằng
   một hệ số — phải đo riêng từng lớp, đúng như paper nói (chỉ Crafter được định lượng).

## Hệ quả cho ticket 29c

- **Đích hiệu chỉnh là bảng đo trên, không phải Fig. 11b.** Fig. 11b (75 cụm @130, 33 @100) là của
  **50 m**, dataset ở đây chỉ có **20 / 30 m** và số đo thực tế ở 130 km/h thấp hơn 4 lần. Dùng số
  paper làm đích sẽ đẩy generator lên một con số **không tồn tại trong dữ liệu**.
- Generator hiện tại sinh **184 cụm/frame** (100 km/h) và **436** (130 km/h) ⇒ vượt số đo
  **6×** và **25×**. Cần đưa về cùng bảng đo, theo từng **lớp xe × tốc độ**, nội suy giữa các mốc
  10 km/h.
- **det/cụm** cũng phải khớp cột cuối bảng đo (8,8 → 49,5 với Crafter 20 m), không phải 14,3 của
  Fig. 1 (số đó là của 100 km/h / 50 m và là trung bình toàn plume).
- Mốc 14,3 vẫn giữ làm **kiểm tra chéo** ở 100 km/h: bảng đo cho 19,4 @100 km/h (không tách cự ly)
  — cùng bậc, không dùng để fit.

## Caveats

- Subsample 10–15 frame/scene × 2–3 scene/ô, không phải toàn bộ 12.420 frame; sai số lấy mẫu
  chưa được định lượng. Báo cáo `--measure` full (60 frame/scene, 207 scene) cho số vai-level
  chính thức; bảng ở đây là **theo ô tốc độ × cự ly**, thứ mà `--measure` không xuất.
- `label == 2` gồm cả nhiễu không phải spray; nếu tách được spray thuần thì số cụm sẽ nhỏ hơn.
- Ngưỡng `eps = 0,7°` là `[CHỌN]` (paper nói "0.7°" và "spherical coordinates" nhưng không nói
  lân cận là hộp hay tròn, cũng không ràng buộc bán kính).