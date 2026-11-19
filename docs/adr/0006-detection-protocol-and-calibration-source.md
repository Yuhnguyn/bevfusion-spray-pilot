# ADR-0006: Đơn vị eval, nguồn calibration, và criterion của thí nghiệm detection

Status: Accepted (2026-11-18). Thay phần eval của ADR-0005, **không** thay quyết định dùng SSPP
làm domain detection.

## Context

ADR-0005 chốt detection chạy trên SemanticSpray++ với split theo tốc độ: 16 scene train, 8 val,
12 test. Đo lại ngày 2026-11-18 (`.scratch/roadspray-cal/{power-design,spec}.md`, `[ĐO]`) tìm ra
bốn vấn đề làm kết luận **không đứng được**, kể cả khi augmentation có tác dụng thật:

1. **Test quá ít đơn vị.** Scene-level CV của tín hiệu spray là **0,483** (clusters/frame) và
   **0,761** (noise/frame); ICC 0,14–0,32 nên frame trong cùng scene không phải đơn vị độc lập.
   Với n = 12, **CI95 half-width = 28,4 % / 44,5 %** — cùng cỡ với effect 30 % mà
   `docs/PROJECT.md` §5 đang nhắm. Một effect thật 30 % sẽ có CI **[2 %; 58 %]** (clusters) và
   **[−14 %; 74 %]** (noise): không phân biệt được với "gần như không có tác dụng".
2. **Calibration leak.** Tham số generator chọn trên 104 scene `cal`, trong đó **6/12 test scene
   là `cal`** = **503/954 frame test (52,7 %)**. Và kể cả bỏ scene test khỏi `cal` thì vẫn còn
   **28 scene `cal` ở đúng 3 tốc độ test** — cùng group, cùng cự ly, cùng mẻ nước. Không thể sửa
   bằng cách lọc scene.
3. **Generator chưa đúng.** `docs/measurements/plume-root-cause.md` liệt kê: 3 lỗi quy ước box
   (đã sửa ở `3a971b8`), **lỗi 4× ngân sách cụm chưa sửa**, wet ground đang sửa dở, đuôi phân bố
   điểm/cụm chưa khớp (sinh max ~91 điểm vs thật 982–1 238). Đo plume với detector trước khi sửa
   sẽ trả lời sai: "plume vô hình" có thể chỉ là hệ quả của bug.
4. **Criterion nhị phân có power ~50 %.** `PROJECT.md` §5 đòi "point estimate ≥ 30 % **và** CI95
   loại trừ 0". Vế thứ nhất chặn trần xác suất pass ở **50 %** ngay cả khi effect thật đúng 30 %,
   với **mọi n**. Fail vì vậy không phân biệt được "augment vô dụng" với "xui".

Đồng thời, hai nguồn đã có sẵn cho phép sửa mà **không mua thêm dataset**:

- **RoadSpray `*_static`** (tudatalib/3537, 333 recording, ego đỗ) là đúng chiến dịch calibration
  của Paper A, **không có scene nào trùng SSPP**. Đây là nguồn calibration độc lập duy nhất.
- **Nhãn điểm của SSPP phủ cả 207 scene**, nên box 3D dựng lại được cho 171 scene thiếu box:
  **BEV IoU p50 = 0,931 / p5 = 0,847**, 99,8 % frame ≥ 0,7 trên 36 scene có box `[ĐO]`.

## Decision

Bốn quyết định, áp cùng nhau:

**D1. Đơn vị eval = 3-fold leave-speed-out trên cả 36 scene, pooled out-of-fold n = 36.**
Rule tất định `fold = rank(speed) mod 3 + 1` trên 9 tốc độ 50–130 km/h; mỗi fold 24 scene train /
12 scene test; mỗi scene được test **đúng một lần**, bởi model chưa từng thấy nó. Báo cáo chính là
**pooled**, per-fold là robustness, per-speed (50/130, n = 4) chỉ là **direction check**.

**D2. Calibration lấy từ RoadSpray `*_static`, không từ SSPP.** Generator được hiệu chỉnh trên dữ
liệu kalibre label-free của Paper A (§III-B), tách hoàn toàn khỏi mọi scene SSPP. Assertion cứng
`cal ∩ SSPP = ∅`. **Fallback** nếu D2 chưa xong: eval chỉ trên **18 held-out scene** (pooled n = 18,
CI half-width ≈ 0,18), khai rõ là phương án yếu hơn.

**D3. Criterion = effect size + CI95, paired theo scene.** Primary metric = SPF proxy/frame, effect
= chênh tương đối trung bình `log(FP_B/FP_A)` trên từng scene, CI95 = percentile bootstrap **theo
scene** (B = 20 000). Chỉ claim "giảm ≥ X %" khi **cận dưới CI ≥ X**. Không dùng pass/fail nhị phân.
Pre-registration ghi ở `.scratch/roadspray-cal/plan.md` §4.

**D4. Train được mở rộng bằng pseudo-box dựng từ `label == 1`, chỉ dùng cho TRAIN.** Eval/val/metric
**tuyệt đối** dùng human box. Giữ một cặp A/B **human-only** làm đối chứng để kết luận không phụ
thuộc lượng data. Gate: `purity ≥ 0,7` và `n_primary ≥ 50`.

## Thi hành D2 — kết quả đo (2026-11-18)

D2 được thi hành bằng một phép đo mới trên RoadSpray `*_static`, không nhãn, ghi đầy đủ ở
`docs/measurements/roadspray-static-clusters-by-speed.md`. Tóm tắt những gì **quyết định ADR**:

**Cách đo (mỗi thành phần có nguồn, không tự đặt).** Vùng đo = **hộp ngay sau đuôi xe** (Paper A §II
*"The initialization of clusters is restricted to the vehicle trajectory"*; §III-B đếm *"in a spray
filter region behind the vehicle"* rồi chia cho `độ dài vùng / quãng xe đi 1 scan` ⇒ độ dài vùng tự
triệt tiêu). Kích thước lấy từ `define_spray_volumes()` của code tác giả: **rộng 3,4 m, cao 1,5 m**.
Tách spray không cần nhãn bằng **range-image nền** (ego đỗ ⇒ mỗi tia luôn trả về cùng vật thể).
Định vị xe bằng track ibeo `ns == 'Car'`; mặt đuôi xác định từ điểm cao > 1,6 m (plume paper ≤ 1,5 m).
Chỉ đo bag `object_direction = +1` (ego thấy đuôi xe; `−1` là ngược chiều, plume bị che).

**Kết quả `[ĐO]` (9 bag/lớp/tốc độ, CI95 bootstrap ở mức bag, đối chứng âm phía trước xe = 0,0):**

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter cụm/frame | 6,0 | 13,2 | 19,0 | 26,7 | 24,8 | 25,7 | 27,4 | 20,6 | 22,2 |
| Golf cụm/frame | 4,7 | 8,8 | 13,2 | 17,8 | 20,9 | 22,6 | 22,0 | 25,8 | 25,2 |

Hai lớp cùng hình dạng (tăng tới ~22–27 cụm/frame ở 100–130 km/h). 81 bag Crafter và 85 bag Golf được
dùng; bag bị loại vì xe **tiến lại** gần ego (plume bị thân xe che) — xem doc §5.

**Kiểm chứng chéo ba nguồn độc lập:**

| Cặp so sánh | Kết quả |
|---|---|
| static vs bảng SSPP cũ (`cal`, 45 frame/ô) | tỉ lệ **1,13×** (0,91–1,32), Pearson **r = 0,79**, cùng chạm đáy 120 km/h |
| bảng SSPP **per-fold không leak** vs static | r = 0,77 (bảng fold khô hơn vì 10/12 scene `itr` 2–6) |
| bảng cũ vs SSPP ở **đúng điều kiện eval** (`itr = 1`, 2 scene/ô) | lệch 12,2 %, **r = 0,98** |

⇒ Hệ quả cho D2: **bảng cũ không sai số, nó chỉ bị leak.** Đổi nguồn sang static là sửa *protocol*,
không sửa *con số*; độ dịch trung bình ~1,13×, nằm trong dải bất định.

**Độ bất định phải khai kèm (quan trọng cho D3).** Thống kê ±10 % (đã nhỏ sau khi tăng lên 54 bag),
nhưng **định nghĩa vùng** chi phối: bề dày lát cự ly từ 1,0 → 6,0 m làm số cụm đổi **17,9 ↔ 39,8**
(2,2×) tại 100 km/h. Nên bảng chỉ xác định tới **±30–40 %**. **Cổng B (`sinh/thật ∈ [0,7; 1,5]`) và
mọi claim từ bảng phải đọc cùng dải này**; không được coi bảng là số chính xác.

**Trạng thái thi hành:** **XONG** — `_CLUSTER_VISIBLE_BY_SPEED` trong `spray/plume.py` đã thay bằng
bảng RoadSpray static cho **cả hai lớp** (2026-11-18 23:40), 203 test xanh. Bảng SSPP `cal` cũ giữ lại
trong `docs/measurements/semantic-spray-clusters-by-speed.md` để đối chiếu, không dùng trong code.
Fallback của D2 (eval trên 18 held-out scene) **không cần dùng**.

Ba bug phương pháp đã trả giá, ghi ở doc §5 để không lặp lại: (a) `object_direction` không cùng ngữ
nghĩa giữa hai chiến dịch ⇒ phải quyết định chiều bằng **hình học**; (b) ibeo đổi nhãn phân loại theo
tốc độ (`Car` ↔ `Truck`) ⇒ không dùng nhãn để chọn track; (c) track rác 4–6 mẫu của ibeo ⇒ chọn track
**nhiều mẫu nhất**, nếu không số cụm bị đẩy lên ~1,4×.

## Consequences

**Được:**

- Kết luận có thể đứng trước reviewer: n = 36, CI half-width 15,7 %, và **không** scene nào dùng để
  chọn tham số lại được dùng để chấm.
- Train từ 16 scene/1 124 frame lên **92 scene/~7 180 frame (6,4×)** mà không cần dataset mới.
- Không phụ thuộc vào một lần bốc xấu: test hiện tại có spray bằng **0,79×** trung bình 36 scene và
  65 % frame nằm ở tốc độ ngoại suy.
- Criterion đo được **độ lớn** của tác dụng, không chỉ "có/không".

**Mất / phải khai:**

- Train gấp **3 lần** số run (3 fold) ⇒ ngân sách GPU ~10–27 h, phải dùng detector nhẹ
  (`pointpillars.yaml` có sẵn + crop `[0,64]×[−16,16] m`) làm pilot.
- Pseudo scene là `itr_after_water` 2–6 trong khi eval là 1; lượng spray khác 1,2–5,4× tuỳ tốc độ.
  Đo trên input train (đã bỏ `label == 2`) cho thấy khác **< 1,1 %** số điểm `[ĐO]` — nhưng vẫn
  phải khai vì nó ảnh hưởng cách viết claim, và **cấm** trộn itr nếu có arm train giữ spray.
- Pseudo-box **không** dùng được để đo yaw/độ cong: 120 km/h (cua) chỉ 88,8 % frame đạt 3D IoU ≥ 0,7.
- Không so số tuyệt đối với nhánh `main` hay Model 0 cũ; chỉ đọc delta ghép cặp.

## Điều gì sẽ khiến mở lại ADR này

- **P2**: kết quả P1 dương nhưng muốn kiểm generalization ngoài domain → train trên STF
  (`.scratch/roadspray-cal/spec.md` Phụ lục A). Khi đó D1 vẫn giữ, chỉ đổi tập train.
- Bộ test 1.463 frame của Paper A (G-Class/CLA/Smart) được công bố → thay SSPP làm test, mở lại D1.
- Generator được chứng minh không thể khớp spray thật (chốt chặn B hoặc C thất bại) → câu hỏi
  nghiên cứu phải đổi, không chỉ đổi protocol.
- Box 3D được công bố cho cả 207 scene → bỏ D4, dùng human box toàn bộ.
- `Golf_static` lấy được → đo nốt dòng Golf và đưa bảng static vào `_CLUSTER_VISIBLE_BY_SPEED`.
- Bảng static lệch bảng per-fold > 1,5× sau khi có Golf → kiểm lại phương pháp đo.

## Liên quan

- ADR-0005: giữ nguyên quyết định domain detection = SSPP; ADR này sửa cách **chia** và cách **chấm**.
- `docs/PROJECT.md` §5: bảng kết quả đã cập nhật theo D3.
- Kế hoạch thi công: `.scratch/roadspray-cal/plan.md`.

---

## Sửa đổi A3 (2026-11-19) — pre-registration, chốt TRƯỚC khi có profile T4

Trạng thái: **Accepted bởi Lead.** Ghi lại tiêu chí nghiệm thu A3 **trước** khi nhìn thấy số liệu vùng đo
của dữ liệu thật (task-13/T4), để không ai có thể nói tiêu chí được chỉnh cho vừa kết quả.

### 1. Vì sao phải sửa tiêu chí

A3 gốc so 4 đại lượng cụm (`r50`, `p95`, `share`, `cụm/frame`) giữa generator và RoadSpray static.
Chuỗi audit 2026-11-19 phát hiện **năm lần "lệch toán tử"** — cùng một lỗi: so hai đại lượng đo bằng
hai cái thước khác nhau.

| # | Toán tử lệch | Sửa |
|---|---|---|
| 1 | Đo trên điểm materialised (`ring=-1`) vs điểm lidar thật thấy | đo `RaycastResult.detections` |
| 2 | Lưới tia tự dựng 32×1800 vs production | `load_beam_table()` 30×1825 = 54.750 tia |
| 3 | DBSCAN cả frame vs DBSCAN trong lát Δ=1,0 m | cài toán tử lát vào dụng cụ |
| 4 | detections cả frame vs vùng hộp 3,4×1,5×20 m | đếm theo vùng |
| 5 | Hình học cụm: sphere model vs chuỗi điểm dày | **bỏ tiêu chí cụm** (bên dưới) |

### 2. Bằng chứng cho việc bỏ tiêu chí cụm — hàm truyền của toán tử

Đo bằng cách nạp quả cầu bán kính **biết trước** vào raycast + cắt lát Δ=1,0 m + `cluster_angular(0,7°; 3)`
(`.scratch/tmp/operator_transfer.py`):

| bán kính nạp (m) | 0,20 | 0,31 | 0,50 | 0,80 |
|---|---:|---:|---:|---:|
| r50 đo lại | 0,176 | 0,242 | 0,360 | 0,459 |
| hệ số truyền | 0,88 | 0,78 | 0,72 | 0,57 |

Tăng mật độ 1 → 120 cụm chỉ kéo r50 0,179 → 0,232 (+30 %). ⇒ Toán tử **bóp méo bán kính 0,57–0,88×**,
và mức bóp méo **khác nhau** giữa sphere model và chuỗi điểm dày của dữ liệu thật (thật: 26 điểm/cụm;
sphere 0,31 m: ~9 điểm/cụm).

**Hệ quả 1:** muốn đo ra 0,349 (đích) phải nạp cầu **0,7–0,8 m** = **2,5× số paper 0,30 m** ⇒ đó là fudge,
không phải hiệu chỉnh.

**Hệ quả 2:** các số 0,349 / 0,292 / 0,311 là **đại lượng ĐO ĐƯỢC** (đầu ra của toán tử), **không phải**
bán kính quả cầu (đầu vào của mô hình). Nạp đầu ra làm đầu vào là **đếm trùng** đúng hệ số bóp méo.
⇒ **Quyết định: bán kính mô hình giữ 0,30–0,31 m của paper; huỷ đề xuất dùng bảng 9 tốc độ làm tham số.**

### 3. Tiêu chí nghiệm thu A3 v2 (pre-registered)

PASS cần **đủ 3** điều, đo trên vùng **0–60 m sau mặt đuôi**, bin **2 m**, mask `|y| ≤ 5,0 m` /
`0,15 m ≤ z − road_z ≤ 3,0 m` (hai vế dùng cùng mask):

| | Tiêu chí | Ngưỡng |
|---|---|---|
| **(a)** | tổng điểm/frame 0–60 m: tỉ lệ sinh/thật | **∈ [0,7; 1,5]** |
| **(b')** | profile chuẩn hoá theo độ sâu: mỗi bin có ≥10 % mass lệch | **≤ 30 %** |
| | độ sâu chứa 90 % mass lệch | **≤ 25 %** |
| **(c)** | CI95 half-width của (a) qua seed | **≤ 25 %** — trượt ⇒ in `NHIỄU`, **không kết luận** |

Mọi đại lượng cụm (`r50`, `rsig`, `p95`, `share`, `cụm/frame`) **chỉ là chẩn đoán in ra**, không tham gia
kết luận PASS/FAIL.

### 4. Điều gì sẽ khiến mở lại phần này

- T4 cho thấy plume thật dồn sát đuôi (< 10 m) trong khi mô hình paper (drag `C=−0,15 m⁻¹`) dồn về xa
  ⇒ mô hình drag/lifetime **không tái tạo được** dữ liệu này. Đó là phát hiện phải ghi, **không** phải
  để chỉnh công thức paper cho khớp.
- Profile khớp nhưng (a) lệch > 2× ⇒ quay lại A (theo chốt chặn B của plan).
- Bất kỳ ai muốn đổi ngưỡng ở §3 phải mở lại ADR và ghi lý do **trước** khi đo.

### 5. KẾT QUẢ NGHIỆM THU A3 (2026-11-19) — **KHÔNG ĐẠT**

Nghiệm thu: 8 seed, kịch bản static (ego đứng yên, xe chạy xa), `diffusion_alpha = 0,06`,
`p_det_scale = 1,0`, commit `6cb75dc`. Số đầy đủ: `.scratch/tmp/a3_acceptance.json`.

| km/h | điểm/frame ± CI95 | tỉ lệ (a) | trail90 | tỉ lệ | profile (b') lệch max | verdict |
|---|---:|---:|---:|---:|---:|---|
| 50 | 13,0 ± 11,3 % | **0,15×** | 2,2 m | **0,38×** | 98 % | **FAIL — ngoài miền** |
| 100 | 144,0 ± 5,8 % | 0,71× ✅ | 40,2 m | 0,91× ✅ | **268 %** | **FAIL** |
| 130 | 283,4 ± 9,1 % | 1,36× ✅ | 49,8 m | 0,96× ✅ | **995 %** | **FAIL** |

- (a) và (c) **đạt** ở 100/130; trail **đạt** ở 100/130; **(b') profile trượt cả 3**.
- Nguyên nhân trượt profile: near-field 0–6 m của generator chiếm 4–5 % mass trong khi dữ liệu thật
  chỉ 0,4–0,7 % ⇒ mass của ta dồn sát đuôi hơn thật ở tốc độ cao.
- **Không** ghi "A3 đạt một phần"; trạng thái là **KHÔNG ĐẠT**.

#### 5.1 Lỗi trong chính tiêu chí đã đăng ký — phải ghi lại

Luật (b') đăng ký ở §3 viết *"mỗi bin có ≥10 % mass thật thì lệch ≤30 %"*. Nhưng ở 100/130
**không bin nào đạt 10 %** (max 9,86 % / 9,64 %) ⇒ đọc nguyên văn thì tiêu chí **rỗng và tự đạt**
(vacuous) — nếu dùng nguyên văn thì 100/130 sẽ PASS giả tạo.

**Định nghĩa hiệu lực:** `|gen_norm(i) − real_norm(i)| / real_norm(i) ≤ 30 %` cho **mọi bin nằm
trong vùng chứa 90 % mass thật**.

Việc sửa này đi theo hướng **nghiêm hơn** (bản rỗng tự đạt → bản sửa cho 268 % / 995 %), nên không
phải chỉnh tiêu chí cho dễ. Vẫn phải khai vì nó thay đổi văn bản đã đăng ký.

#### 5.2 Hai mở rộng ngoài paper đang được dùng (phải khai trong luận văn)

| # | Mở rộng | Tham số | Căn cứ |
|---|---|---|---|
| 1 | Bỏ `streak` (vệt kéo dài) | — | Cơ chế tự thêm, không có trong paper |
| 2 | Tán xạ: `r(t) = r₀ + α·d_rel(t)` | α = 0,06 **[CHỌN]** | `r_cl` của paper là *khoảng cách xa nhất từ tâm tới detection* — đại lượng đo ở nhiều tuổi plume ⇒ mô hình hoá tường minh sự nở theo tuổi là nhất quán. **α KHÔNG hiệu chỉnh thuần từ trail90**: kiểm chứng độc lập cho thấy trail90 **không phân biệt** được α ∈ [0,03; 0,08] (cả ba đều cho trail 41/49 m ở 100/130 km/h). α = 0,06 được chọn **[CHỌN]** đồng thời theo trail90 **và** điểm/frame (α = 0,03 làm det@100 = 0,42× trượt). User-approved 2026-11-19 |

#### 5.3 Miền tin cậy và hệ quả downstream

- **Dùng được: 100–130 km/h.** **Ngoài miền: ≤ 60 km/h.**
- Lý do ngoài miền: lifetime `T = 0,02·wfh·(v−50)+0,2` là `[CODE] dee.cpp:530`; tại `v ≤ 50` cho
  `T = 0,2 s` **bất kể màng nước**, trong khi dữ liệu đòi `T_eff ≈ 1,0 s`. Paper chỉ cho T qua
  **Fig. 6**, không cho công thức ⇒ **limitation của reference impl**, không sửa công thức.
- **Cổng B** phải báo **riêng theo nhóm tốc độ**; gộp sẽ che mất nhóm ≤60 km/h lệch.
- Augmentation ở ≤60 km/h **yếu hơn thực tế** (thiếu đuôi plume) ⇒ nếu arm B không cải thiện ở
  nhóm tốc độ thấp thì đó là **kỳ vọng đã biết**, không phải bằng chứng phản bác.
- A3 không đạt **không** chứng minh augmentation vô dụng — việc đó là cổng C.

#### 5.4 Điều kiện dừng của plan đã bị vượt — ghi lại

`plan.md` §7 ghi *"B: sau A vẫn lệch > 2× → dừng, quay lại A"*. Ở 50 km/h lệch **6,7×**, tức vượt
điều kiện dừng. Quyết định của user ngày 2026-11-19: **tiếp tục với miền giới hạn 100–130 km/h**,
50–60 km/h loại khỏi miền claim. Quyết định này phải được trích dẫn mỗi khi báo kết quả từ cổng B
trở đi.

#### 5.5 Kiểm chứng độc lập (R3, 2026-11-19) — các chỗ phải khai thêm

R3 chấm lại bằng **harness riêng** (tự inject/raycast/mask/bin, không đọc output của R1), 8 seed:
det 13,03 / 144,0 / 283,4 · trail90 2,0 / 40,0 / 50,0 m · CI95 ±11,1 / ±5,8 / ±9,0 % — **lệch < 0,5 %**
so với bảng nghiệm thu ⇒ hai harness độc lập ra cùng kết quả. Determinism: cùng seed chạy 2 lần
giống tuyệt đối.

**Bắt buộc khai khi trích dẫn:**

1. **100/130 KHÔNG phải PASS.** Chúng chỉ "pass" dưới tiêu chí (b')(i) **rỗng**; dưới định nghĩa
   hiệu lực (mọi bin trong vùng chứa 90 % mass thật) profile lệch **268 % / 995 %** ⇒ **FAIL**.
   A3 **KHÔNG ĐẠT ở cả ba tốc độ**, không phải "đạt một phần".
2. **(a) @100 chỉ hơn ngưỡng 1,1 %** (0,711 vs 0,70). Số seed đạt/8: **0 / 5 / 6** (50/100/130)
   ⇒ ngay cả tiêu chí dễ nhất cũng không bền ở 130.
3. **"8 seed × 120 frame" là sai nguyên văn** — 120 chỉ là **cap**; frame thực **120 / 66 / 51**
   (100/130 bị giới hạn bởi đường chạy 200 m).
4. **`range < 15 m` @50 = 0,0264 %** (không tuyệt đối 0); `range ≤ 4 m` = 0 ở cả 3 tốc độ.
5. **@50 generator chạy tới ~200 m** trong khi dữ liệu thật `car_range` max chỉ **97 m** ⇒ hình học
   @50 xa hơn thật; không đổi verdict nhưng phải khai.
6. **α = 0,06 là [CHỌN]**, không phải "hiệu chỉnh thuần từ trail90" (xem §5.2).
7. `p_det_scale = 1,0` đã kiểm **cả trong production**: `PlumeTransform` gọi `raycast_frame()`
   không truyền config ⇒ không có scale ẩn.

**Còn nợ dọn doc** (R3 phát hiện, chưa sửa): `plume-a3-diagnosis.md` §6.6 vẫn nêu tiêu chí cụm cũ
(r50/rsig) mà không đánh dấu *superseded*; §7.9 còn ghi α default = 0,0 trong khi đã bake 0,06;
§6.3 (không phải §7.4) nói đã bỏ `tail_block_height_frac` nhưng field còn; đếm thực tế là **2 test**
(`tests/test_plume_tail_block.py` assert `== (0.05, 0.92)`, `tests/test_sspp_plume_integration.py`) +
**1 script** (`scripts/diag_verify_conventions.py`) — muốn xoá hẳn phải sửa cả 3 file.

#### 5.6 Khoảng trống giữa nghiệm thu A3 và production (R3 kiểm, 2026-11-19)

R3 kiểm đường production thật (`spray/plume_transform.py` → `inject_plume_stateful` → `all_alive` →
`raycast_frame(load_beam_table())`). **4/6 tham số khớp**, nhưng có ba khoảng trống phải khai:

1. **KỊCH BẢN KHÁC HẲN — nghiêm trọng nhất.** A3 nghiệm thu ở kịch bản **static** (ego đứng yên, xe
   chạy ra xa tới 200 m). Production chạy ở kịch bản **following** (`PlumeContext` SSPP thật: ego
   chạy, object 20–50 m phía trước) + warm-start. Vì α tác động qua `d_rel`, mà phân bố `d_rel`
   khác nhau giữa hai kịch bản ⇒ **các số (a)/(b')/(c) của A3 KHÔNG chứng minh kịch bản train**.
2. **Attenuation + occlusion của real returns.** Production xuất `real_points` bị attenuate
   `exp(−2·0,02·L)` và bị plume che; A3 **chỉ đếm detections**, chưa đo phần real returns bị mất.
   Hệ quả: plume có thể làm **giảm recall** (che vật thể) — A3 không thấy điều này.
3. **`vehicle_class` không được truyền** trong `inject_plume_stateful` ⇒ **mọi scene dùng bảng
   Crafter**, kể cả Golf (bảng Golf còn ở Δ=2,5, chưa validate Δ=1,0).

Ghi chú thêm: `diffusion_alpha = 0,06` khớp **gián tiếp** qua module default (`PlumeTransform` khởi
tạo `PlumeState()` không config) — không được pin tường minh, đổi hằng số là đổi nghiệm thu.
`PlumeTransform` **không được khai báo trong config nào của repo** ⇒ chỉ verify được ở mức class.

**Hệ quả bắt buộc cho cổng C:** đây là **phép đo đầu tiên ở đúng kịch bản production**, nên cổng C
phải đo **cả recall** (real returns mất do attenuation/occlusion) chứ không chỉ false-positive, và
phải ghi rõ nó chạy ở kịch bản following. Nếu chỉ đo FP thì không kết luận được về tác dụng ròng.

---

## A3-V — Kiểm chứng ở kịch bản FOLLOWING (pre-registered 2026-11-19)

Trạng thái: **Accepted bởi Lead**. Ngưỡng dưới đây được ghi **TRƯỚC** khi phép đo T5 (`task-14`) báo số.

### Vì sao cần

A3 nghiệm thu ở kịch bản **static**; production chạy **following** (xem §5.6). R2 đọc lại Paper A
(`docs/reference/paper-validation-protocol.md`, 17 trích dẫn) và kết luận:

- Paper **fit** tham số trên calibration set static rồi **validate trên CÙNG bộ dữ liệu**, chỉ giữ lại
  "object distances and values" chưa dùng để fit (`L1043-1047`, Fig. 10/11/12). Fig. 10 ghi rõ
  *"passing by the stationary ego vehicle"* ⇒ **validation plume của paper cũng là ego đỗ**.
- Paper **không có** bất kỳ hình/bảng nào so phân bố plume mô phỏng với dữ liệu khi **ego chạy**.
  Họ chỉ kiểm ở mức end-task (augment STF rồi đo AP) — chứng minh *hữu dụng*, không chứng minh
  *phân bố đúng*.
- Paper **không nói** gì về việc truyền phân bố góc đo từ ego đỗ sang ego chạy; chỉ cảnh báo
  near-field/resolution (`L1520-1527`).

⇒ **D2-chặt là cần nhưng CHƯA ĐỦ**: nó quy định *nguồn tham số*, không quy định *cách kiểm chứng*.

### Protocol (chốt trước khi đo)

| Hạng mục | Giá trị |
|---|---|
| Dữ liệu | **171 scene SSPP KHÔNG có human box** (D1 chỉ eval 36 scene có box ⇒ 171 chưa bao giờ eval), ≥20 scene/nhóm tốc độ, cả Crafter và Golf |
| Dựng kịch bản | `PlumeContext` từ chính frame SSPP: ego/object speed + `distance_to_object` từ `metadata.txt`, box xe dẫn theo `object_labels`, road_z bằng RANSAC |
| Đường chạy | **đúng production**: `inject_plume_stateful` → `raycast_frame(load_beam_table())`, seed theo frame (paired) |
| Vùng đo | 0–60 m sau **box xe dẫn**, mask `|y| ≤ 5 m`, `0 ≤ z − road_z ≤ 3 m` (loại spray ngoài vùng/ego) |
| Metric chính | `median_frame(det_sinh / det_thật)` với `det_thật` = số điểm `label == 2` trong cùng vùng |
| CI | bootstrap **theo scene**, B = 2000 |
| Metric phụ (báo, không chặn) | depth profile 2 m/bin; % det_sinh ở range < 10 m và < 4 m; range của xe p5/p50/p95 |

### Ngưỡng PASS/FAIL (pre-registered)

PASS khi **cả hai**:

1. `median(det_sinh / det_thật) ∈ [0,5 ; 2,0]`
2. **CI95 nằm trọn trong** `[0,5 ; 2,0]` (không vắt biên)

Lý do chọn [0,5; 2,0] thay vì [0,7; 1,5] của A3: ở kịch bản following, `label==2` **không phải**
toàn bộ spray (gồm cả spray của ego/nguồn khác) và hình học near-field nhạy hơn nhiều; dải ±2× là
mức "cùng bậc" còn phân biệt được, trong khi sai số cửa sổ đo đã là 12–22 %.

**Nếu FAIL:** ghi limitation + là **covariate bắt buộc** khi đọc cổng C. **KHÔNG sửa generator để
pass** (SSPP là domain eval). Muốn sửa tham số thì phải mở lại ADR này và nêu nguồn tham số mới
hợp lệ — không được lấy chính số đo A3-V ra làm nguồn.

### Caveat phải khai khi trích dẫn

- `label == 2` của SSPP gồm **spray + noise**, có thể có spray từ nguồn khác ⇒ chỉ so trong vùng
  sau xe dẫn, và ghi rõ giới hạn này.
- SSPP là **dynamic subset của chính RoadSpray** ⇒ A3-V là **consistency check**, không phải
  kiểm tra out-of-distribution.
- Đây là **bước bổ sung của repo `[CHỌN]`**, **không** có trong paper. Phải trình bày đúng như vậy,
  không được viết thành "paper quy định".
- A3-V chỉ kiểm mức *phân bố plume*. Kiểm mức end-task (AP) là việc của cổng C.

---

## D2-v2 — Hiệu chỉnh kịch bản trên dữ liệu TRAIN-ONLY (pre-registered 2026-11-19)

Trạng thái: **Accepted bởi user 2026-11-19**. Ghi **TRƯỚC** khi T5 (`task-14`) báo số.

### Vì sao được phép mở (và vì sao không phải goalpost-moving)

D2-chặt ra đời để sửa chẩn đoán **V2**: có 6/12 scene test **cũng là** scene calibration ⇒ eval bị bẩn.
Nhưng **171 scene SSPP không có human box KHÔNG BAO GIỜ nằm trong eval** (D1 chỉ eval trên 36 scene
có box). Và theo D4/E4, chính 171 scene đó sẽ được sinh **pseudo-box để TRAIN** (BEV IoU p50 0,931).

⇒ Hiệu chỉnh augmentation trên **dữ liệu train** không rò rỉ vào eval. Đây là thực hành ML chuẩn,
khác hẳn lỗi V2 (calibrate trên chính dữ liệu eval).

### Phạm vi được phép (hẹp có chủ ý)

| | |
|---|---|
| **Được hiệu chỉnh** | **ĐÚNG MỘT** đại lượng vô hướng: `following_density_scale` — nhân vào tốc độ phát cụm trong **đường production** (kịch bản following), để mật độ plume khớp dữ liệu train-only |
| **KHÔNG được đổi** | `RADIUS_MEDIAN_M`, `RADIUS_SIGMA`, `RADIUS_MAX_M`, lifetime `T`, drag `C`, `P_det` (µ, σ), `diffusion_alpha` — tất cả vẫn từ **paper + RoadSpray static**, không đụng |
| **KHÔNG được đổi** | tiêu chí A3 (đã đóng) và tiêu chí A3-V (§ dưới) |
| **Cấm** | thêm bậc tự do thứ hai; hiệu chỉnh theo tốc độ/lớp xe (chỉ một số vô hướng toàn cục) |

### Chống rò rỉ — bắt buộc

1. **36 scene eval không bao giờ được dùng** để fit `following_density_scale`, cũng không dùng để chọn
   giá trị. Code phải assert `fit_scenes ∩ eval_scenes = ∅`.
2. **Chia 171 scene thành fit/verify** (phân tầng theo nhóm tốc độ × lớp xe), tỉ lệ **2/3 fit – 1/3 verify**.
   `following_density_scale` chỉ fit trên phần **fit**; verdict A3-V chỉ đọc trên phần **verify**.
   ⇒ Không được fit rồi verify trên cùng scene (sẽ là tautology).
3. `following_density_scale = 1,0` cho tới khi có số. Giá trị cuối + danh sách scene fit phải ghi vào
   ADR này **và** vào metadata checkpoint.
4. A3 (nghiệm thu static) đã đóng với `scale = 1,0`; nếu production dùng scale ≠ 1,0 thì mọi trích dẫn
   kết quả A3 phải nói rõ "A3 đo ở scale 1,0".

### Ngưỡng A3-V giữ nguyên

Ngưỡng ở mục A3-V **không đổi**: `median(det_sinh/det_thật) ∈ [0,5 ; 2,0]` và CI95 nằm trọn trong dải,
đo trên **phần verify**. Ngưỡng này được ghi trước khi biết bất kỳ số nào của T5, và **không** được
nới sau khi thấy số.

**Nếu sau khi fit `following_density_scale` mà phần verify vẫn FAIL:** ghi limitation, **dừng** —
không thêm hệ số thứ hai, không đổi ngưỡng. Đó là kết luận rằng mô hình plume không tái tạo được
kịch bản following, và nó ảnh hưởng trực tiếp tới cách đọc cổng C.
