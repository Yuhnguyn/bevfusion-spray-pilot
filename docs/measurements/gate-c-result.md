# A7 — CỔNG C: kết quả (2026-11-19)

Kernel `nguynhuy9669/bevfusion-gate-c-plume-vs-detector` **version 5**, `COMPLETE` lúc 00:48,
`inference_s = 873,3`. Config `model0` (LiDAR-only BEVFusion, 33 362 653 byte, sha256 khớp),
τ = 0,20, IoU = 0,5, range 54 m, paired theo scene, 954 frame / 12 scene, **paired cùng frame**.

Cấu hình plume: **Cách A** qua `--paper-domain` — `diffusion_alpha = 0`, `‖pos‖ − radius ≥ 2,5 m`,
`‖pos‖ ≤ 50 m`, `wfh` lấy mẫu theo scene. `wet_ground = true`, `wfh_mm = 1,0` (hai thứ này giữ
nguyên như runbook cũ để paired sạch).

---

## 1. KẾT QUẢ `[ĐO]`

| nhánh | recall | precision | FP/frame | TP/frame |
|---|---:|---:|---:|---:|
| `clean` | **0,8208** | 0,561 | 1,018 | 0,821 |
| `plume` (Cách A) | **0,6080** | 0,365 | 1,334 | 0,608 |
| `real` (spray thật) | **0,7767** | 0,491 | 1,243 | 0,777 |

| đại lượng | giá trị | CI95 bootstrap (2000 lần, theo scene) |
|---|---|---|
| **Δrecall(plume − clean)** | **−0,2188** | **[−0,2949 ; −0,1555]** |
| ΔFP(plume − clean) | **+0,3278** | **[+0,1956 ; +0,4540]** |
| Δrecall(real − clean) | −0,0441 | (bằng chứng tham chiếu của pre-register: −0,049) |

**12/12 scene** có Δrecall âm (min −0,526, max −0,078). Đếm lại bằng tay từ `gate_c_detections.jsonl`
+ GT gốc ra **đúng −0,2188** ⇒ số của harness được xác nhận độc lập, không phải lỗi eval.

## 2. Chấm theo pre-register (ADR-0006 §5.7 mục 3, ghi ở `ecfdb23`)

| | tiêu chí | kết quả |
|---|---|---|
| **TC1** | `ΔFP(plume − clean)` có CI95 **không** chứa 0 | **ĐẠT** — [+0,1956; +0,4540] |
| **TC2** | `Δrecall(plume − clean) ∈ [−0,099 ; +0,001]` | **TRƯỢT NẶNG** — −0,2188 |
| | `< −0,15` ⇒ **DỪNG** (mục 3) | **kích hoạt** |

**Dự đoán ghi trước là −0,05; kết quả −0,2188.** Sai 4,4 lần. Cách A đã lấy lại được
0,049 trong 0,268 (18 %), **không** phải phần lớn.

## 3. Cơ chế — đo được, **không** phải che khuất

Đây là phần quan trọng nhất, vì nó đổi hẳn cách hiểu kết quả.

**Bằng chứng phủ định "che khuất":**

1. Spray chỉ thêm **0,04–1,47 %** số điểm nền (13–398 điểm/frame trên 27–31 nghìn). Không đủ khối
   lượng để che một hộp ở 20–25 m.
2. Tương quan **liều–đáp ứng ngược**: `corr(Δrecall, inj/clean%) = +0,192`. Scene 0000 sụp
   **−0,526** với chỉ 55 điểm/frame; Golf 0102 bơm **342 điểm/frame** mà chỉ sụp **−0,091**. Nếu
   là che khuất thì nhiều spray phải hại hơn — dữ liệu nói ngược.
3. Hộp dự đoán **gần như không di chuyển**: IoU(clean, plume) = 0,84–0,93, dịch 0,1–1,2 m.

**Cơ chế thật — score sụp, vị trí đúng.** Trên 678 frame có GT khớp ở nhánh `clean`:

| số phận hộp đúng | n | % |
|---|---:|---:|
| plume **giữ** (IoU ≥ 0,5 **và** score ≥ 0,2) | 497 | **73,3** |
| plume **rớt score** (IoU ≥ 0,5, score < 0,2) | 136 | **20,1** |
| plume **mất hộp** (IoU < 0,5) | 45 | 6,6 |

Score hộp đúng: `clean` p50 = **0,482** → `plume` p50 = **0,352**; min 0,050. Ví dụ điển hình
(IoU vẫn 0,85 nhưng score 0,337 → 0,050):

```
0000_2021-09-08-14-36-56_0  f4   score 0,337 -> 0,050   IoU 0,846
0054_2021-09-08-16-19-50_0  f9   score 0,336 -> 0,051   IoU 0,812
0096_2021-09-08-17-49-24_0  f62  score 0,491 -> 0,053   IoU 0,714
```

⇒ **Spray không che hộp. Nó làm detector mất TỰ TIN vào hộp đúng.** 20,1 % hộp đúng rớt xuống
dưới τ = 0,20 và bị tính là FN dù hộp vẫn ở đúng chỗ với IoU 0,7–0,8. Cộng với 6,6 % mất hộp
thật, đó là toàn bộ −0,219.

## 4. Vì sao "thêm ít điểm" lại hạ confidence nhiều — giả thuyết còn mở

Ba khả năng, **chưa cái nào được kiểm**:

1. **Điểm spray nằm trong/quanth hộp GT** cùng voxel với điểm xe ⇒ voxel đó bị lấp bởi điểm nước
   (intensity thấp), làm feature của vật thể loãng đi. Voxel `max_num_points = 10` ⇒ 10 điểm nước
   có thể **đẩy điểm xe ra khỏi voxel**.
2. **Phân bố điểm spray lệch khỏi phân bố train** ⇒ BEVFusion coi là nhiễu, hạ score toàn vùng.
3. Tương tác với `wet_ground` bật: 982 814 điểm thật bị attenuate (3,48 %) **chỉ ở nhánh plume**,
   không ở `clean`/`real` ⇒ đây là **biến gây nhiễu** giữa hai nhánh, cần ablation riêng
   `--no-wet-ground` để tách.

Khả năng 1 kiểm được ngay bằng `max_num_points`/voxel-occupancy; khả năng 3 kiểm bằng một lượt
kernel `--no-wet-ground`. **Chưa làm.**

## 5. Kết luận theo pre-register

**DỪNG.** TC1 đạt nhưng TC2 trượt nặng (−0,2188 < −0,15), 12/12 scene âm, và dự đoán ghi trước
(−0,05) sai 4,4 lần. Theo mục 3 của §5.7: *"ghi kết luận âm tính, không thêm hệ số nào."*

Điều **được** phép nói: Cách A sửa đúng **ba bệnh đã đo** của generator (near-field, trôi về sau,
tỉ lệ điểm) mà không phá recall về 0 — nó chỉ lấy lại 18 % mức sụt. Nhưng **không** đủ để
augmentation này dùng được cho train: Δrecall −0,219 so với spray thật −0,044 nghĩa là plume vẫn
hại detector **5 lần** nhiều hơn spray thật.

Điều **không** được nói: rằng near-field là nguyên nhân duy nhất. Bằng chứng §3 cho thấy cơ chế là
**score calibration**, không phải hình học cụm.

## 6. Việc tiếp theo (chưa làm, cần quyết định)

1. **A7-b `--no-wet-ground`** — tách biến gây nhiễu 3,48 % attenuation khỏi hiệu ứng spray. Một
   lượt kernel ~15 phút. Nếu Δrecall về gần −0,044 thì toàn bộ kết luận đổi.
2. **A7-c voxel occupancy** — kiểm khả năng `max_num_points = 10` bị điểm nước chiếm chỗ. Đo được
   offline, không cần kernel.
3. **Không** thêm hệ số, **không** đổi τ, **không** đổi ngưỡng pre-register.

---

## 7. Kiểm chéo: miền Cách A có thật sự được bật? (2026-11-19, bổ sung)

Log kernel v5 in **`paper_domain=0`** — đọc qua thì tưởng nhánh chính chạy production. Kiểm ra:
`kernel.py` có **hai** lời gọi `sspp_infer.py`:

| hàm | có `--paper-domain`? | vai trò |
|---|---|---|
| `dry_run()` | **KHÔNG** (thiếu) | probe plumbing 1 frame |
| `run_gate_c()` | **CÓ** | chạy 954 frame, sinh kết quả |

Dòng `paper_domain=0` xuất hiện **đúng 1 lần** (t = 37 s) và thuộc `dry_run()`. Nhánh chính
không in dòng `GATE_C_PLUME` nào. Đã sửa `dry_run()` cho khớp (commit dưới).

**Chứng minh nhánh chính CÓ bật miền** — bằng chữ ký không thể trùng hợp: `wfh` lấy mẫu **theo
scene** bằng `sample_wfh_mm()`, hàm băm riêng của repo mà production **không bao giờ** gọi
(production luôn `wfh = 1,0`).

| | giá trị đo từ nhánh plume của cổng C |
|---|---|
| `wfh` theo scene | **0,137 / 0,805 / 1,200** mm (min/p50/max) |
| số scene `wfh ≠ 1,0` | **7/12** |
| `corr(wfh, atten%)` | −0,248 |

Nếu là production thì cả 12 scene phải cùng `wfh = 1,0`. Chúng không cùng ⇒ **miền Cách A đã
chạy đúng** ở nhánh plume. Kết quả §1–§6 là của Cách A, không phải production.

**Bài học thước đo (lần thứ ba trong phiên):** đọc log phải kiểm **số lần** xuất hiện và **hàm nào**
in ra, không chỉ grep dòng đầu. Ban đầu tôi kết luận "kết quả là của production" từ một dòng log
duy nhất — sai.
