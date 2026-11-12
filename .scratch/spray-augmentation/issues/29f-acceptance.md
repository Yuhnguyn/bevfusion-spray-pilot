# 29f — Nghiệm thu PM (2026-11-12)

Type: research
Status: **đo xong, kết luận của worker SAI — PM đã tính lại**
Owner: PM (worker bị ngắt `EXIT=130` trước khi sửa §3)

## Số đo (đúng, dùng được)

Nguồn: `docs/measurements/29f-cluster-visibility.md` §1–2, commit `20e9653`.

| lớp | `alive/real` | `visible/alive` | `dbscan/real` |
|---|---:|---:|---:|
| Crafter (TB 9 tốc độ) | **1,49** | **0,49** | **0,68** |
| Golf (TB 9 tốc độ) | **1,08** | **0,70** | **0,84** |

Theo tốc độ, Crafter:

| km/h | alive | visible | dbscan | real | visible/alive | dbscan/real |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 9,4 | 4,6 | 2,9 | 4,5 | 0,49 | 0,65 |
| 70 | 26,5 | 13,0 | 8,6 | 16,4 | 0,49 | 0,52 |
| 100 | 28,6 | 13,4 | 12,9 | 21,8 | 0,47 | 0,59 |
| 130 | 12,8 | 6,7 | 8,4 | 15,0 | 0,52 | 0,56 |

## Kết luận §3 của worker là SAI

Worker ghi: *"**Nhánh 3b (sinh cụm):** 16/18 ô có `alive` ≤ 0,7× real/frame."*

Sai hai chỗ, cả hai đều do **lỗi đếm trong `render()`** (`scripts/measure_29f.py`):

1. **Đảo nghĩa biến.** `high = [cell for cell in cells if cell["alive_ratio"] > STOP_GATE]` đếm các ô
   `alive_ratio > 0,7`, rồi in ra thành "có `alive` ≤ 0,7×". Đếm số ô **vượt** ngưỡng nhưng gán nhãn
   là số ô **dưới** ngưỡng.
2. **Số sai.** Thực tế chỉ **2/18 ô** có `alive/real ≤ 0,7` (Golf@120 = 0,62; Golf@130 = 0,63).
   **10/18 ô có `alive/real ≥ 1,0`** — generator sinh cụm **nhiều hơn** thật.

⇒ Cửa chặn **không** chỉ vào nhánh 3b. `alive` không thiếu; nó **thừa** ở phần lớn ô.

## Cơ chế thật — mất ở khâu `visible`, không phải khâu sinh

`visible/alive = 0,49` (Crafter). Đây **không phải lỗi**, mà là **toán học của mô hình**:

- Mỗi cụm có `P_t = exp(−age/T)` ([PAPER] §III-C), tuổi phân bố đều trong `[0, 4T]`.
- Tỉ lệ cụm còn "sống đủ để sinh detection" = trung bình `exp(−a/T)` trên `[0,4T]`:

  `∫₀^{4T} e^{−a/T} da / ∫₀^{4T} da = (1 − e^{−8}) / (2(1 − e^{−4})) = **0,509**`

- Đo được **0,49** (Crafter) — khớp công thức trong sai số 4 %. Golf 0,70 vì `T` ngắn hơn.

⇒ `visible ≈ alive × 0,51` là **đúng thiết kế paper**, không sửa.

## Vậy lỗi thật nằm ở đâu — hai lớp ngược chiều nhau

| lớp | `dbscan/real` | nghĩa |
|---|---:|---|
| Crafter | **0,68** | thiếu cụm nhìn thấy (cần ×1,47) |
| Golf | **0,84** | hơi thiếu |
| Golf@100–130 | **1,02–1,36** | **THỪA** cụm |

Golf@100 có `dbscan/real = 1,36` — generator sinh **nhiều hơn 36 %** số cụm thật. Crafter@100 thì
thiếu 41 %. **Một bảng spawn rate không phục vụ được cả hai lớp cùng lúc** ở dạng hiện tại.

Đây là cùng loại vấn đề với `P_det`: paper cho **một** bộ tham số (đo trên Crafter), dataset có hai
lớp hành xử khác nhau.

## Việc phải làm

1. **Sửa `render()` trong `scripts/measure_29f.py`**: đổi `high` → `low`, và in đúng số ô dưới ngưỡng.
   Đây là bug hiển thị, không phải bug đo.
2. **Không sửa spawn rate theo một lớp.** Xem xét: bảng `_CLUSTER_VISIBLE_BY_SPEED` đã tách theo lớp
   (`vehicle_class`), nên có thể chỉnh **riêng Crafter** mà không đụng Golf. Kiểm trước khi làm:
   `dbscan/real` của Crafter cần ×1,47; của Golf đã 0,84–1,36.
3. **Ghi nhận `visible/alive = 0,51` là đúng paper** vào doc, để lần sau không ai "sửa" nó.

## Tiêu chí (thay A1)

| # | Tiêu chí | Ngưỡng |
|---|---|---|
| D3′ | `dbscan/real` | **0,85–1,15** ở 9 mốc × 2 lớp (hai chiều, không chỉ ≥) |
| D4 | `visible/alive` | 0,51 ± 0,08 — **chẩn đoán**, khớp công thức paper |
| D5 | `alive/real` | **chẩn đoán** — không dùng làm cửa chặn (đã chứng minh không tương quan với `dbscan`) |

## Không mở lại

- Không sửa `visible/alive` — đó là `exp(−age/T)` của paper.
- Không đổi `eps`/`minPts`/`Ω_tia`.
- Không dùng `alive` làm cửa chặn — nó **thừa** ở 10/18 ô trong khi `dbscan` vẫn thiếu.