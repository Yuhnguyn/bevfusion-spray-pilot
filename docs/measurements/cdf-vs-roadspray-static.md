# CDF cự ly detection vs RoadSpray `*_static` — lần đo đầu (2026-11-25)

Trước hôm nay **chưa từng** chạy được `--mode real-static`: `data/roadspray/` trống, nên thước
"thật" của Paper A Fig. 12 (CDF cự ly detection 0–50 m) chỉ có vế sinh. User đưa
`Crafter_static.zip` / `Crafter_dynamic.zip` / `meta_data_dataset.json`; xlsx metadata lấy thêm qua
DSpare REST. Golf_static vẫn thiếu (paper chỉ định lượng Crafter).

Lệnh:

```
# thật — 6 bag RoadSpray static (2 bag × 50/100/130 km/h), 271 frame
scripts/measure_cdf_over_range.py --mode real-static \
  --crafter-zip data/roadspray/Crafter_static.zip \
  --xlsx data/roadspray/meta_data_measurement.xlsx \
  --real-static-jsonl $T/real_static.jsonl --speeds 50,100,130 --bags-per-speed 2

# sinh — kịch bản static, 2 seed, 1442 frame
scripts/measure_cdf_over_range.py --mode gen-static --seeds 2 \
  --gen-static-jsonl $T/gen_static.jsonl

# tổng hợp (cần cả 3 nguồn; thiếu Golf thì script in `!! BỎ QUA lớp Golf` và đi tiếp)
scripts/measure_cdf_over_range.py --mode aggregate \
  --real-static-jsonl … --gen-static-jsonl … --following-jsonl … --summary …
```

## 1. `[ĐO]` CDF cự ly — vế **thật** lần đầu có (Crafter, RoadSpray static)

| band | n det thật | CDF10 | CDF20 | CDF30 | p50 | p25 / p75 |
|---|---:|---:|---:|---:|---:|---|
| 50–70 | 13 028 | 71,1 % | 89,9 % | 100 % | 7,6 m | 6,3 / 13,4 |
| 80–110 | 25 111 | 36,0 % | 84,8 % | 100 % | 22,0 m | — |
| 120–130 | 30 648 | 0,6 % | 14,0 % | 40,0 % | 33,7 m | — |

**Đây là phát hiện lớn nhất của lần đo này:** plume thật **không** nằm sát đuôi.
Ở 120–130 km/h chỉ **0,6 %** detection trong 10 m đầu, p50 = **33,7 m**. Ở 50–70 km/h thì ngược
lại, p50 = 7,6 m. ⇒ **CDF thật dịch ra xa rất mạnh theo tốc độ** (7,6 → 22,0 → 33,7 m).

Trước đây repo chỉ có số `trail90` (44 / 52 m) — cùng xu hướng nhưng không phải CDF, nên không
so trực tiếp được với Fig. 12. Nay có CDF.

## 2. `[ĐO]` So với generator (cùng kịch bản static, 2 seed)

| band | KS | KS tại | CDF10 thật | CDF10 sinh | **Δ CDF10** |
|---|---:|---:|---:|---:|---:|
| 50–70 | **0,789** | 16 m | 71,1 % | **0,0 %** | **−71,1** |
| 80–110 | 0,208 | 16 m | 36,0 % | **0,0 %** | **−36,0** |
| 120–130 | 0,244 | 9 m | 0,6 % | **0,0 %** | −0,6 |

Hai điều:

1. **Generator KHÔNG BAO GIỜ sinh detection dưới 10 m** ở kịch bản này (`CDF10 = 0,0 %` cả 3
   band) — vì miền paper cắt `‖pos‖ − r ≥ 2,5 m` **cộng** vùng sinh bắt đầu cách xe ≥ 18 m. Thật
   thì 71 % ở 50–70 km/h nằm dưới 10 m. Đây là **lệch có cấu trúc**, không phải nhiễu.
2. Ở 50–70 km/h KS = 0,789 là **lệch nặng nhất trong mọi ô đã đo** — generator dồn ở 20–30 m
   trong khi thật dồn ở 5–10 m.

## 3. `[ĐO]` Phát hiện nghiêm trọng: 12,8 % detection **trước mặt đuôi xe**

| vế | n trước mặt đuôi | n trong vùng | % |
|---|---:|---:|---:|
| **thật static** | **0** | 68 787 | **0,0 %** |
| **sinh static** | **3 953** | 26 847 | **12,8 %** |

Spray bắn ra từ bánh sau **không thể** nằm trước mặt đuôi xe. Đây là vi phạm vật lý của
generator, độc lập với mọi thước khác. Nguyên nhân khả nghi (chưa kiểm): `raycast_frame` sinh
detection dọc theo **tia**, không theo mặt cầu — một tia đi qua rìa quả cầu có thể trả điểm ở
rất gần gốc, và nếu tia đó cắt qua vùng trước mặt đuôi thì điểm rơi vào đó. Cùng cơ chế đã được
ghi ở `a5-domain-a3v.md` §3 mục 5 cho near-field `det < 3 m` (max tới 127).

**Hệ quả:** nếu dùng generator này để train, model sẽ học "spray có thể xuất hiện trước xe" —
một tín hiệu sai về mặt vật lý. Phải cắt ở tầng detection (sau raycast), đúng như A5 đã kết luận
("muốn về đúng 0 phải cắt ở tầng detection — **chưa làm**, và nếu làm phải pre-register riêng").

## 4. `[ĐO]` Profile độ sâu: generator dồn sát gấp 4 lần

p50 depth sau mặt đuôi (m):

| km/h | thật | sinh | tỉ |
|---|---:|---:|---:|
| 50 | 0,4 | 0,2 | 0,50 |
| 100 | 4,4 | 1,0 | 0,23 |
| 130 | 6,6 | 1,6 | 0,24 |

Generator dồn sát mặt đuôi **2–4 lần** so với thật trong hệ quy chiếu depth-sau-đuôi, trong khi
ở hệ quy chiếu cự ly cảm biến (`|p|`, thước paper) nó lại nằm **quá xa** (CDF10 = 0 %).
Hai phát biểu không mâu thuẫn: cụm nằm ở ~20–25 m tính từ cảm biến, nhưng **ngay sau mặt đuôi**
vì xe cũng ở ~20–25 m ở kịch bản following; ở static xe chạy ra xa 20→200 m nên cụm bám đuôi
trong khi thật thì plume trải ra 30 m.

## 5. Việc cần làm, theo thứ tự

1. **Cắt detection trước mặt đuôi** (12,8 % → 0) — vi phạm vật lý, phải sửa trước mọi thứ khác.
   Pre-register: cắt theo `x > rear_x` ở tầng detection, đo lại A5 + CDF.
2. **Bù khối lượng** (A5 0,23–0,89×) — cần mở ADR-0006 §5.7 vì đang cấm `spawn_scale`.
3. **Golf_static** — chỉ cần nếu muốn bảng theo lớp xe; paper chỉ định lượng Crafter.

## 6. Số thô

`%TEMP%/cdfprobe/{real_static,gen_static,following_all}.jsonl`, `summary_cdf.json`.
