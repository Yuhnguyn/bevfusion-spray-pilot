# Decision log — lịch sử các quyết định về generator plume

Mục đích: **comment trong code chỉ mô tả HÀNH VI HIỆN TẠI.** Mọi phần "trước đây làm X, đã
bỏ ở QĐn" được chuyển về đây. Khi cần biết vì sao một tham số có giá trị đó, tra file này.

Định dạng: mã QĐ · ngày · đã đổi gì → thành gì · vì sao · căn cứ.

Bảng tra tài liệu lỗi thời (cấp S1–S5): `docs/adr/0007-superseded-claims.md`.

---

## QĐ7 · 2026-11-19 · tách vùng SINH khỏi vùng ĐO

- **Trước:** khối sinh cụm = hộp đo calibration 20 m (dài 20 m, cao `0,05–0,92 × cao box`,
  có clamp ngang `2,43 m`).
- **Sau:** QĐ11 làm lại lần nữa thành slab `|v|·Δt` (xem dưới). QĐ7 đóng góp phần **bỏ clamp**.
- **Vì sao:** gộp hai vùng vào một là lỗi khái niệm — vùng đo là nơi *đếm* cụm trên dữ liệu
  thật, vùng sinh là nơi *đặt* cụm. Calibration đo trong 20 m không có nghĩa cụm phải sinh
  trong 20 m.
- **Căn cứ:** audit R2 trên 49 tham số đánh `clamp 2,43 m`, `source_lateral_m`,
  `tail_block_height_frac` là **PHẢI BỎ** vì nguồn là SSPP `cal` (bị leak).

## QĐ11 · 2026-11-19 · khối sinh = slab `|v|·Δt × 3,4 × 1,5 m`

- **Trước:** hộp 20 m sâu, cao theo chiều cao box.
- **Sau:** dài `|v|·Δt` (quãng xe đi trong một chu kỳ 0,1 s: 1,4 m @50 · 2,8 @100 · 3,6 @130),
  rộng 3,4 m, cao 1,5 m tính từ mặt đường.
- **Vì sao:** đúng `define_spray_volumes()` của code tác giả; paper chỉ nói *"uniform
  distribution in the region behind every moving object"*, không cho kích thước.
- **Hệ quả nhận thức:** vệt dài 44–52 m ở 100–130 km/h **không** do khối sinh rộng, mà do các
  cụm sinh ở nhiều chu kỳ khác nhau rồi trôi đi.
- **Căn cứ:** `[CODE]` `openMSL/sl-1-2` `define_spray_volumes()` + bề ngang/cao của hộp đo
  calibration static.

## QĐ12 · 2026-11-19 · `prune` tan theo xác suất, bỏ cắt cứng `4T`

- **Trước:** xoá cứng khi `age > 4·T` (`[CODE]` `dee.cpp:446`), hệ số tích luỹ `4T/Δt + 1`.
- **Sau:** mỗi chu kỳ cụm sống với xác suất `P = exp(−Δt/T)`; trần số học `12·T` chỉ để chặn
  đuôi (`exp(−12) = 6e−6`).
- **Vì sao:** paper Eq. 1 nguyên văn *"probability … to still exist after time t is exp(−t/T)"*.
  Cắt cứng làm hệ số tích luỹ sai **4 lần** so với paper.
- **Hệ quả:** `steady_state_cluster_factor` và `steady_state_alive_factor` giờ **bằng nhau**
  (cùng là `K = 1/(1−exp(−Δt/T))`); hai tên giữ lại cho caller cũ.

## QĐ13 · 2026-11-19 · tán xạ `r(t) = r₀ + α·d_rel`, α = 0,06

- **Trước:** bán kính = một lognormal cố định, trần `2,0 m` (p99 của paper).
- **Sau:** bán kính nở theo độ sâu sau mặt đuôi, trần nâng lên `4,0 m`.
- **Vì sao:** paper §III-B định nghĩa `r_cl` là *"maximum distance of detections to the
  respective cluster center"* — đại lượng **đo được ở nhiều tuổi plume**, nên mô hình hoá
  tường minh sự nở theo tuổi là nhất quán. **Đây là mở rộng NGOÀI paper, có khai báo.**
- **Căn cứ:** α hiệu chỉnh từ `trail90` của RoadSpray `*_static` (6 / 44 / 52 m @50/100/130).

## Ticket 29e-c · 2026-11-18 · `rate` neo tại `wfh = 1,0 mm`

- **Vấn đề:** bảng `cal` cho **tích** `alive = rate × K`, không cho từng thừa số. Một phương
  trình, hai ẩn.
- **Giải:** chốt `rate(v) = visible_ref(v) / K(T_ref)` với `T_ref` tại `WFH_REF_MM = 1,0 mm`.
  Hệ quả là tại đúng 1,0 mm thì `alive` trả về đúng số bảng (kiểm: 9,04 / 30,50 / 33,08 khớp).
- **Vì sao không dùng `wfh` của scene:** khi đó `alive = [visible/K(wfh)] × K(wfh) = visible`
  bất kể độ ẩm ⇒ `wfh` thành biến chết, mâu thuẫn paper Fig. 11b (moist ~50 vs fully ~107 cụm).
- **Bất nhất còn treo:** bảng đo trên RoadSpray gộp `itr_after_water` 1–6, còn neo là 1,0 mm
  (fully covered). Xem `docs/measurements/roadspray-static-clusters-by-speed.md` §7.

## Ticket 29e-d-iii · 2026-11-18 · bỏ MLE fit riêng cho từng lớp

- **Trước:** `P_det` và `r_cl` fit MLE **theo từng lớp xe** (Crafter / Golf riêng).
- **Sau:** dùng lognormal của paper cho **mọi** lớp; chỉ bảng số cụm là khác theo lớp.
- **Vì sao:** `mu` của fit bị đuôi cụm-đã-gộp chi phối, không tái lập được phân bố đo.
- **Căn cứ:** paper `P_det` lognormal μ=−2,3 σ=1,1; `r_cl` μ=−1,2 σ=0,8 (Fig. 5).

## Ticket 28b/29c · 2026-11-18 · bỏ bảng tia đo được, dùng lưới đều

- **Trước:** bảng `ring → elevation` đo từ release + file YAML.
- **Sau:** lưới đều `0,333°` elevation trên FOV đo được `−4,06…+5,88°`, `0,197307°` azimuth.
- **Vì sao:** `ring` trên release **không phải** beam id (lệch trung vị 3,49° so với VLP-32C);
  bảng đo được còn bị một filter cắt mất các ring hướng lên — đúng những ring nhìn thấy plume.
- **Hệ quả:** file YAML cũ đã xoá, không gì được đọc nó (`tests/test_beam_model.py` assert).

## Ticket 29h · 2026-11-18 · bỏ `vz` ban đầu và trần chiều cao

- **Trước:** `vz ~ U(0, vz_max)` (`[CODE]` `dee.cpp:540`) + xoá cụm khi vượt trần chiều cao.
- **Sau:** `INITIAL_VZ_MAX_MPS = 0.0`, `prune(ceilings=…)` nhận tham số nhưng **bỏ qua**.
- **Vì sao:** paper không có gravity và không có phương trình `z`, nên cụm không tự bay lên.
  Chiều cao plume **thuần** đến từ vị trí khối sinh.

## Lỗi D7 · 2026-11-18 · ngân sách điểm plume

- **Trước:** trần tuyệt đối 2.000 điểm/frame.
- **Sau:** `max(500, round(0,05 × N_thật))`.
- **Vì sao:** trần tuyệt đối cắt oan frame dày; hình học đúng cho 807–1.555 điểm/frame. Sàn 500
  giữ frame thưa vẫn có plume.

## QĐ10 / A3 · 2026-11-19 · `p_det_scale` và `pdet_range_exponent` thành opt-in

- **`p_det_scale`** mặc định `1,0` = giữ nguyên paper. Nó là hệ số nhân vào tích
  "số tia trúng × `P_det`", vì mô hình tia của repo (54.750 tia) khác cảm biến của paper.
- **`pdet_range_exponent`** (b trong `P_det(R) = P_det0·(R/R0)^b`) mặc định `0,0` = `P_det`
  hằng. Đo lại được `b = +0,222 [−0,135; +0,547]` ⇒ không phân biệt được với 0 ⇒ **không cứu
  được near-field**, giữ tắt.
- **Căn cứ:** `docs/measurements/pdet-vs-range.md` §11. D2-chặt: hiệu chỉnh trên `*_static`
  label-free thì hợp lệ, không phải fudge factor.

## QĐ14 · 2026-11-25 · `P_det0` là hằng số theo CỤM (hết nháy sáng/tắt)

- **Trước:** `raycast_frame` rút `lognormal(p_det_mu, p_det_sigma)` mỗi lần gọi, tức mỗi
  frame cho mỗi cụm. Cụm sống 10–40 frame vì `P = exp(−Δt/T)`, nên cùng một cụm có `P_det0`
  độc lập giữa các frame dù `p_det_sigma = 1,1` cho p99/p50 ≈ 13× ⇒ cụm rực sáng một frame
  rồi tắt hẳn frame sau (**nháy**).
- **Sau:** `spawn` rút **z-score** `N(0,1)` một lần, lưu `SprayCluster.p_det_z`;
  `raycast_frame` dựng `P_det0 = exp(p_det_mu + p_det_sigma · z)` từ config hiện hành.
- **Vì sao lưu z chứ không lưu `P_det0` tuyệt đối:** `RaycastConfig.p_det_mu/sigma` là API
  của caller (gate C, script đo, test). Lưu giá trị tuyệt đối sẽ làm config **bị bỏ qua im
  lặng** với mọi cụm production.
- **Căn cứ:** paper Fig. 7 fit lognormal trên phân bố `P_det` **giữa các cụm** ⇒ mỗi cụm có
  một `P_det` cố định. `[ĐO] 2026-11-25` trên scene 0072 (110 km/h, 40 frame): độ nháy
  `mean|Δ det|/mean det` giảm **0,420 → 0,232 (−45 %)**; với MỘT cụm cô lập qua 12 frame,
  CV giảm **0,949 → 0,395** (min/max 0→14 thành 0→7) — phần còn lại là nhiễu Bernoulli.
- **Không bias kỳ vọng:** 120 realization độc lập của `z` (14 cụm, 8 frame/realization) so
  với chế độ rút lại: **−2,4 %, |z| = 0,55** ⇒ cùng kỳ vọng. Một phép đo đơn lẻ trước đó
  lệch −13,5 % chỉ là phương sai mẫu của đuôi nặng (`std giữa realization 158,9` ≈
  `std giữa frame 156,6`).
- **Điều KHÔNG sửa được:** phương sai tổng `det/frame` giữa các scene/realization vẫn lớn
  (CV ≈ 45 %) vì `p_det_sigma = 1,1` là số của paper. Muốn giảm phải đổi σ ⇒ cần quyết định
  riêng, không thuộc QĐ14.
- **Không đổi:** cụm không mang `p_det_z` (dựng tay trong test) vẫn được rút z tại chỗ như cũ.

## ADR-0006 D2 · 2026-11-18 · nguồn bảng số cụm: SSPP `cal` → RoadSpray `*_static`

- **Trước:** `_CLUSTER_VISIBLE_BY_SPEED` đo trên SSPP `cal`, mà `cal` chứa **6/12 scene test**
  (503/954 frame = 52,7 %) ⇒ tham số fit một phần trên chính dữ liệu báo kết quả.
- **Sau:** đo lại trên RoadSpray `*_static` — chiến dịch calibration của Paper A, ego đỗ,
  không scene nào trùng SSPP. Cột chuẩn thức = lát `Δ = 1,0 m`.
- **Vì sao đổi `Δ`:** DBSCAN của paper chạy trên `(azimuth, elevation)`, không có chiều cự ly;
  lát dày làm nhiều đám thật nối thành chuỗi ⇒ số cụm phình **1,6–2,1×** (Crafter 100 km/h:
  Δ=1,0 → 35,86 · Δ=2,5 → 25,75 · Δ=6,0 → 17,21).
- **Dải bất định phải đọc kèm:** định nghĩa vùng (`Δ` từ 1,0 → 6,0 m) cho **±30–40 %**, chi phối
  hơn sai số mẫu. Mọi claim từ bảng đọc cùng dải này.
- **Golf chưa hiệu chỉnh:** chưa có phép đo static `Δ=1,0` cho Golf; giá trị Golf trong code vẫn
  là `Δ=2,5` cũ ⇒ không phải cùng chuẩn.
