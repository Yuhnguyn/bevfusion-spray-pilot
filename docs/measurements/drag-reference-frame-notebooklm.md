# Hệ quy chiếu của drag — NotebookLM trả lời (2026-11-25)

Hỏi notebook `Mô Phỏng Hiệu Ứng Bụi Nước Trên Cảm Biến Lidar Ô Tô`
(`f2c09ee8-1c5c-45d3-869d-e62559073f1c`, source duy nhất = PDF arXiv 2212.08558) qua
`notebooklm -p phk4 ask`. Câu trả lời trích nguyên văn; chỗ paper không nói được đánh
`NOT STATED IN PAPER`.

## 1. `[PAPER]` Phương trình chuyển động — §III-B "Update Cluster Parameters"

| Eq. | Nguyên văn |
|---|---|
| (2) | `F⃗ = ½ ρ_air · c_D · A · v⃗_rel²` |
| (3) | `m · a⃗ = ½ ρ_air · c_D · A · (v⃗_w + v⃗_cl)²` |
| (4) | `v⃗_cl = ∫₀ᵗ (ρ_air·c_D·A / 2m)(v⃗_w + v⃗_cl)² dt + v⃗₀` |
| **(5)** | `v⃗_cl,k = C · (v⃗_w + v⃗_cl,k−1)² · Δt + v⃗_cl,k−1` |
| **(6)** | `p⃗_cl,k = p⃗_cl,k−1 + Δt · v⃗_cl,k` |

Paper nói rõ **số hạng bên trong là tổng `(v_w + v_cl)`**, và Eq. (5) bình phương nó.
Đây là điểm quan trọng nhất — xem §3.

Hằng số: `C = −0,15 m⁻¹`, `Δt = 100 ms`.
Nguyên văn: *"Optimizing the constant to fit the movement of the clusters in measurements
with different vehicle velocities and wind velocities yields a factor of C = −0.15 m⁻¹."*
Và: *"It should be noted that the factor depends on the step size Δt and has to be
re-calibrated for sensors with different scanning frequencies."*

## 2. `[PAPER]` Hệ quy chiếu — **NOT STATED IN PAPER**, suy ra là ground

Paper **không** đặt tên hệ quy chiếu. NotebookLM ghi `NOT STATED IN PAPER` rồi suy ra:

- *"The state of every cluster kept in the global vector is updated"* — "global vector"
- vận tốc ban đầu = *"the velocity of the moving object is set as an initial cluster
  velocity"*, tức vận tốc **đối với mặt đất**
- `v⃗_w` là *"overall wind velocity"*

⇒ ground/world frame. **Code hiện tại dùng đúng ground frame** (`advance` trừ
`ego_velocity` ở bước vị trí, không trừ ở bước vận tốc). **Không có bug hệ quy chiếu.**

## 3. `[PAPER]` Chuyển động sau khi sinh

Nguyên văn §III-B:
> *"the measurements show that clusters first move in the direction of the moving object,
> then decelerate due to air resistance. This is possibly caused by the dead wake directly
> behind the moving object."*

Vận tốc ban đầu: *"during generation of a cluster, the velocity of the moving object is
set as an initial cluster velocity."*

## 4. `[PAPER]` Gió

Cluster chịu gió; gió giống nhau cho mọi cụm (paper tự nêu là hạn chế). **Giá trị số gió
KHÔNG có trong paper** — chỉ nói *"The vehicle velocity and wind velocity are measured"*.
`2 m/s from 208°` là `[CODE]` `dee.cpp`, không phải paper.

## 5. Điều kiện rời vùng / xoá cụm

`NOT STATED IN PAPER`. Paper chỉ có `P_t(t) = e^{−t/T}` (Eq. 1) làm cơ chế tan dần.
Nguyên văn: *"Clusters do not just disappear after a certain amount of time, but they
dissolve gradually."* Hệ số `4T` (code) hoặc `12T` (repo) đều là `[CHỌN]`.

---

# 6. Hệ quả — nơi generator lệch paper

## 6.1 `[ĐO]` Eq. (5) cho đuôi dài đúng bằng thật — nhưng code không tái lập được

Mô phỏng Eq. (5)+(6) thuần (`.scratch/paper-faithful/eq5_reference_tail.py`), cụm sinh ở
đuôi xe @ 24 m, `v₀` = vận tốc xe, `C = −0,15`, `Δt = 0,1 s`, gió `[0,94; 1,77; 0]`:

| km/h | depth p50 | depth p95 | `\|p\|` p50 |
|---|---:|---:|---:|
| 50 | 0,7 | 3,3 | 22,7 |
| 100 | **16,5** | 81,9 | 29,1 |
| 130 | **36,2** | 162,5 | 31,4 |

Đích RoadSpray thật (dải `car_range` [20,40)): 50 → 0,5/6,5; 100 → **17,5**/26,5;
130 → **20,5**/29,5.

⇒ **Eq. (5) một mình đã cho p50 = 16,5 m @100 km/h, khớp thật 17,5 m.** Paper đúng ở
tầng phương trình. p95 của Eq. (5) quá lớn (81,9 vs 26,5) vì tôi chưa áp trần tuổi —
`P_t = e^{−t/T}` sẽ cắt đuôi đó; cần mô phỏng đầy đủ mới so p95.

## 6.2 `[ĐO]` Generator hiện tại chỉ đạt p50 = 2,5 m — lệch 6,6 lần

| km/h | THẬT p50/p95 | SINH b=0 | SINH b=+2,0 |
|---|---|---|---|
| 50 | 0,5 / 6,5 | 0,5 / 1,5 | 0,5 / 1,5 |
| 100 | **17,5** / 26,5 | **2,5** / 9,5 | 2,5 / 9,5 |
| 130 | **20,5** / 29,5 | **3,5** / 9,5 | 3,5 / 9,5 |

Chú ý: `b = +2,0` **không đổi** p50 — nên không phải luật `P_det(R)`.

## 6.3 `[ĐO]` Nguyên nhân thật: cụm bị **dồn về phía ego**, không phải đi chậm

Kiểm trực tiếp bằng cách chạy `PlumeState` (§6.1 kịch bản): cụm **có** bay xa —
t = 4 s ở x = 40,5 m. Vậy quãng đường không phải nút thắt.

Nhưng trong `gen_static` ở dải `car_x` [20,40), phân bố cho thấy:

| car_x | n_det | n_in_hist | **n_ahead (trước mặt đuôi)** | p95 |
|---|---:|---:|---:|---:|
| 21,8 | 203 | 46 | **157** | 2,5 |
| 24,6 | 191 | 74 | **117** | 3,5 |
| 27,3 | 149 | 72 | **77** | 5,5 |
| 30,1 | 88 | 87 | 1 | 6,5 |
| 32,9 | 119 | 118 | 1 | 8,5 |
| 38,4 | 78 | 76 | 2 | 10,5 |

**77–157 trên ~200 detection "trước mặt đuôi xe"** ở các frame đầu. Đó là lý do p50/p95
của `depth_hist` sụp xuống 2,5–3,5 m: phần lớn khối lượng điểm **không nằm sau đuôi**,
nên nó không vào `depth_hist` — nó vào `n_ahead_of_rear`.

⇒ **Đuôi "ngắn" trong bảng là artifact của chính phép đo**: khối lượng bị dồn vào
`n_ahead`, chỉ phần nhỏ còn lại mới được histogram hoá. Cần đo lại với vế thật **cùng
định nghĩa** (không lọc `depth >= 0`) trước khi kết luận về độ dài đuôi.

---

# 7. `[ĐO]` Đo lại với HAI VẾ CÙNG ĐỊNH NGHĨA (2026-11-25, sau khi sửa script)

`run_real_static` trước đây lọc `depth >= 0.0` **trước** khi histogram ⇒ `n_ahead_of_rear`
luôn 0 theo cấu trúc. Đã thêm biến thể `*_all` (mọi detection trong vùng, **không** ràng
buộc depth) để so cùng định nghĩa với `gen_static` (đo trên toàn bộ detection).

## 7.1 Đuôi plume, cùng định nghĩa

| km/h | `car_range` | THẬT n_ahead / n_all | p50 | p95 | SINH n_ahead / n_all | p50 | p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| 50 | [20,40) | **7 / 3 200** (0,2 %) | 0,5 | 6,5 | **127 / 1 666** (7,6 %) | 0,5 | 1,5 |
| 100 | [20,40) | **5 / 14 075** (0,04 %) | **17,5** | 26,5 | **553 / 2 158** (25,6 %) | **2,5** | 9,5 |
| 130 | [20,40) | **4 / 7 283** (0,05 %) | **20,5** | 29,5 | **219 / 833** (26,3 %) | **3,5** | 9,5 |
| 50 | [40,80) | 0 / 37 | 45,5 | 59,5 | 10 / 903 (1,1 %) | 1,5 | 2,5 |
| 100 | [40,80) | 0 / 11 003 | **34,5** | 54,5 | 3 / 1 373 (0,2 %) | 8,5 | 25,5 |
| 130 | [40,80) | 0 / 23 139 | **38,5** | 56,5 | 0 / 582 | 14,5 | 35,5 |

**Kết luận giữ nguyên, và giờ đã cùng chuẩn:** ở 100–130 km/h, đuôi plume thật p50 =
17,5–38,5 m vs generator 2,5–14,5 m. Đuôi hụt **3,5–7 lần**.

## 7.2 `[ĐO]` "Trước mặt đuôi" — không phải tautology, và generator lệch 500 lần

| km/h | THẬT % trước mặt đuôi | SINH % | tỉ |
|---|---:|---:|---:|
| 50 | 0,2 % | 7,6 % | 35× |
| 100 | **0,04 %** | **25,6 %** | **580×** |
| 130 | **0,05 %** | **26,3 %** | **495×** |

Đây là số đo hợp lệ (cả hai vế cùng định nghĩa). **¼ detection của generator ở 100–130 km/h
nằm trước mặt phẳng đuôi xe** — trong khi dữ liệu thật gần như bằng 0.

Vẫn **chưa** đủ để nói "vi phạm vật lý": phần trước mặt đuôi **của ego** là hợp lệ (plume từ
xe phía trước rơi vào vùng giữa ego và xe đích). Nhưng 25,6 % là quá cao, và trước đây
A5-domain đo `det < 3 m` mean 0,1–3,2 max 127 cùng cơ chế.

## 7.3 Vì sao generator sinh nhiều điểm trước mặt đuôi

Kịch bản static: ego đứng yên, xe đích chạy ra xa từ ~20 m. Cụm sinh **tại** đuôi xe với
`v₀ = vận tốc xe` (27,8 m/s @100). Nhưng `raycast_frame` bắn tia từ **gốc ego**; một cụm ở
21–25 m có góc khối nhỏ, và vì `P_det` là Bernoulli **mỗi tia cắt**, cụm ở gần bị bắn nhiều
tia hơn. Frame đầu tiên, cụm còn ở rất gần đuôi và **vượt** nó trong `Δt` kế tiếp
(`v·Δt = 2,8 m`), nên một phần detection rơi về phía trước mặt phẳng đuôi.

Đây là hệ quả của **vị trí sinh + vận tốc ban đầu**, không phải của raycast.

---

# 8. `[ĐO]` Eq. (5) cho đuôi đúng, nhưng ở cự ly khác

`.scratch/paper-faithful/eq5_reference_tail.py` mô phỏng Eq. (5)+(6) thuần, `v₀` = vận tốc
xe, `C = −0,15`, `Δt = 0,1 s`, sinh tại đuôi xe @ 24 m:

| km/h | Eq.(5) depth p50 | Eq.(5) depth p95 | THẬT p50 / p95 |
|---|---:|---:|---|
| 50 | 0,7 | 3,3 | 0,5 / 6,5 |
| 100 | 16,5 | 81,9 | **17,5 / 26,5** |
| 130 | 36,2 | 162,5 | **20,5 / 29,5** |

p50 khớp rất tốt ở 100 km/h (16,5 vs 17,5). p95 quá lớn vì tôi chưa áp `P_t` — nhưng có
một điều đáng chú ý: Eq. (5) cho cụm bay **rất xa** nếu `T` đủ dài, và p50 ≈ 17,5 m chỉ đạt
được khi `T` ≈ 1,2 s. `T = 0,02·wfh·(v−50) + 0,2` cho đúng 1,2 s ở 100 km/h.

⇒ Hai điều:
1. `C = −0,15` và `T` của paper **cho đúng đuôi thật ở 100 km/h** khi mô phỏng thuần.
2. Generator hiện tại cho 2,5 m — lệch 6,6 lần. Vì 25,6 % khối lượng bị đẩy sang
   `n_ahead` (bị `depth_hist` bỏ), phần còn lại chỉ là đuôi ngắn. **Nếu cộng `n_ahead` vào,
   con số thật của generator có thể gần đúng hơn** — cần tính lại trước khi kết luận có bug.

## 8.1 Việc phải làm để chốt

## 8.2 `[ĐO]` CHỐT: đuôi hụt là **transient của giai đoạn đầu**, không phải bệnh của mô hình

Tách `gen_static` theo `car_x` (xe chạy ra xa dần) — thấy rõ quy luật:

| km/h | `car_x` | nfr | n_all | % sau đuôi | p50 | p95 |
|---|---|---:|---:|---:|---:|---:|
| 100 | [20,30) | 6 | 1 214 | **55,8 %** | 2,5 | 4,5 |
| 100 | [30,40) | 8 | 944 | 98,3 % | 4,5 | 11,5 |
| 100 | [40,60) | 14 | 913 | 100,0 % | 8,5 | 20,5 |
| 100 | [60,80) | 14 | 460 | 99,3 % | 9,5 | 31,5 |
| 100 | [80,110) | 22 | 352 | 99,4 % | **16,5** | **49,5** |
| 100 | [110,150) | 30 | 88 | 100,0 % | **38,5** | 50,5 |
| 130 | [20,30) | 6 | 620 | **66,1 %** | 2,5 | 4,5 |
| 130 | [40,60) | 12 | 422 | 100,0 % | 14,5 | 24,5 |
| 130 | [80,110) | 18 | 197 | 100,0 % | 18,5 | 52,5 |
| 130 | [110,150) | 22 | 63 | 100,0 % | **37,5** | 55,5 |

**Đọc bảng này:**

1. **`n_ahead` chỉ xảy ra ở giai đoạn đầu** (`car_x` < 40 m, 2–3 giây đầu). Sau đó nó về 0
   và `% sau đuôi` = 100 %. Vậy "25,6 % trước mặt đuôi" là **transient khởi động**, không
   phải tính chất của mô hình.
2. **Đuôi `p50` tăng dần theo `car_x`** — 2,5 m ở 20–30 m, **38,5 m ở 110–150 m**. Plume
   **vẫn đang mở rộng** khi xe đi xa. Ở cự ly 110–150 m, generator cho p50 = 38,5 m, khớp
   với thật (34,5 m ở dải `car_range` [40,80)).
3. **Bảng "đuôi hụt 3,5–7 lần" ở §7.1 là artifact của việc so ở `car_x` [20,40) — đúng chỗ
   transient chưa tan.** So cùng dải `car_x` thì generator **khớp thật**.

## 8.3 `[ĐO]` So đúng: cùng `car_x` bin, cùng định nghĩa

| km/h | `car_x` | THẬT p50 | SINH p50 | tỉ |
|---|---|---:|---:|---:|
| 100 | [40,80) | 34,5 | 8,5 | 0,25× |
| 100 | [80,110) | — (bag hết plume) | 16,5 | — |
| 130 | [40,80) | 38,5 | 7,5–14,5 | 0,3× |

Ở [40,80) generator vẫn hụt 3–4 lần. Nhưng ở [110,150) generator cho 38,5 m — **bằng
thật**. Hai điều này chỉ tương thích nếu: **generator mở rộng plume chậm hơn thật**, tức
`T` ngắn so với đường đi, chứ không phải "đuôi bị chặn".

## 8.4 Kết luận đã hiệu chỉnh (thay cho §6.3 và §7)

| tuyên bố trước | trạng thái |
|---|---|
| "Đuôi ngắn 6,6 lần, do drag chặn" | **SAI** — ở `car_x` ≥ 110 m generator đạt 38,5 m, bằng thật |
| "25,6 % detection trước mặt đuôi, vi phạm vật lý" | **SAI về bản chất** — chỉ là transient ở `car_x` < 40 m; về 0% sau đó |
| "drag = −0,15 chặn quãng đường < 20 m" | **SAI** — `advance()` cho cụm bay tới 40 m sau 4 s; và Eq.(5) thuần cho p50 = 16,5 m @100 |
| "không có đòn bẩy nào để hiệu chuẩn" | **SAI** — `T`/`wfh` và `C` đều là đòn bẩy, chỉ là tôi đo sai chỗ |

**Bệnh thật, đo được:** generator mở rộng plume **chậm hơn thật** — ở `car_x` [40,80)
(tức 2–5 s sau khi sinh) đuôi chỉ 7,5–8,5 m trong khi thật đã 34,5–38,5 m. Ở giai đoạn muộn
hơn thì khớp. Đây là **hằng số thời gian `T` quá ngắn so với tốc độ mở rộng thật**, không
phải drag.

## 6.4 Còn treo

1. Tính **depth của MỌI detection** (kể cả trước mặt đuôi, dùng depth âm) cho cả hai vế rồi
   so phân bố đầy đủ — không cắt ở 0. Script đã có `depth_hist_all` cho vế thật; vế sinh
   đã có `n_ahead` nhưng chưa xuất histogram của miền âm.
2. Chỉ sau đó mới biết generator có bug độ dài đuôi hay chỉ là artifact của phép cắt.

## 6.4 Còn treo

1. Vì sao cụm ở **trước** mặt đuôi xe? `spawn` đặt `center` trước, cụm có `vel` = 27,8 m/s
   nên frame đầu tiên nó **vượt** mặt đuôi. Ở 100 km/h, `v·Δt = 2,8 m` mỗi frame — nếu
   sinh ở đuôi thì sau 1 frame đã ở +2,8 m, mà `rear_x` cũng tiến 2,8 m ⇒ phải bám.
   Nhưng `advance()` chạy **trước** `spawn()` trong `inject_plume_stateful` (dòng 539–542),
   nên cụm mới sinh ở frame `k` bị `advance` ở frame `k+1` đẩy đi thêm `Δt·v` **cộng**
   với việc xe cũng tiến — cần đo chính xác thứ tự để biết có cộng đôi không.
2. p95 của Eq. (5) = 81,9 m > thật 26,5 m ⇒ cần áp `P_t` đầy đủ rồi mới so.
