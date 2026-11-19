# HANDOFF — nhánh `sspp` (BEVFusion trên SemanticSpray++ + plume spray)

Cập nhật: **2026-11-19 18:20** · nhánh `sspp` · test: **213 passed** (không cần GPU).
Kế hoạch thi công 6 giai đoạn: **`.scratch/roadspray-cal/plan.md`**. ADR chuẩn: **`docs/adr/0006-*.md`**.

---

## 0. ĐỌC KHỐI NÀY TRƯỚC (15 dòng)

Câu hỏi dự án: **augmentation plume spray tổng hợp có làm detector 3DOD (BEVFusion LiDAR-only) tốt hơn trên
SSPP không?** Generator sinh cụm spray lấy tham số từ paper Linnhoff 2022 (arXiv 2212.08558) + dữ liệu
calibration RoadSpray `*_static`.

**Ba phán quyết hiện tại (đã pre-register trước khi đo, KHÔNG diễn giải lại):**

| Cổng | Kết quả | Ghi chú |
|---|---|---|
| **A3** (generator khớp thống kê spray thật — kịch bản static) | **KHÔNG ĐẠT** | (a) det + trail đạt ở 100/130; (b') profile trượt; ≤60 km/h ngoài miền |
| **A3-V** (kiểm chứng kịch bản following, 72 scene non-eval) | **FAIL 5/6 ô** | đậm hơn thật 2,7–4,6× @80–110, **8–17× @120–130** |
| **Cổng C** (plume bơm vào frame sạch có hại detector không) | **HƯỚNG TRAIN CHẾT** | plume ↑FP **+0,299** nhưng **recall −0,268**; spray thật chỉ −0,049 |

**Nguyên nhân gốc đã chẩn đoán (quan trọng nhất):** near-field. Ở kịch bản following, cụm bị drag làm rơi lùi
rồi **trôi ngược xuyên qua cảm biến**; mô hình ray-cast quả cầu cho số detection ∝ `(r/R)²` ⇒ **bùng nổ** khi
`R→0` (48 % detection sinh ở range <4 m, trong khi dữ liệu thật **không có** spray nào dưới 2,5 m). Plume tạo
**"tấm màn" trước cảm biến**, che chiếc xe ở 22–25 m ⇒ recall sụp.

**Câu hỏi mở duy nhất còn lại:** nếu **cull cụm ở <25 m** (biên paper dùng để hiệu chỉnh) rồi chạy lại cổng C,
plume có hại **ngang spray thật** không? Nếu có ⇒ augmentation hợp lệ, câu hỏi train mới có nghĩa. Nếu không ⇒
kết luận trung thực: mô hình paper không dùng được cho bộ dữ liệu này.

**Phát hiện quan trọng cho motivation:** spray **thật** chỉ làm mất **4,9 điểm recall** ⇒ **trần lợi ích** của mọi
augmentation spray trên benchmark này là rất nhỏ. Phải nêu ngay ở phần motivation, không để ở phần kết quả âm.

---

## 1. Ba kết quả chi tiết

### 1.1 A3 — kịch bản static (ego đứng yên, xe chạy ra xa), 8 seed
Đo bằng `scripts/measure_plume_size_tail.py`. Vùng 0–60 m sau đuôi, mask `|y|≤5 m`, `0≤z−road_z≤3 m`.

| km/h | điểm/frame ± CI95 | tỉ lệ (a) | trail90 | tỉ lệ | profile (b') lệch max | verdict |
|---|---:|---:|---:|---:|---:|---|
| 50 | 13,0 ±11,3 % | **0,15×** | 2,2 m | **0,38×** | 98 % | FAIL — ngoài miền |
| 100 | 144,0 ±5,8 % | 0,71× ✅ | 40,2 m | 0,91× ✅ | **268 %** | FAIL |
| 130 | 283,4 ±9,1 % | 1,36× ✅ | 49,8 m | 0,96× ✅ | **995 %** | FAIL |

Nguyên nhân ≤60 km/h: công thức lifetime `T = 0,02·wfh·(v−50)+0,2` là `[CODE] dee.cpp:530`; tại `v ≤ 50` cho
`T = 0,2 s` **bất kể màng nước**, trong khi dữ liệu đòi `T ≈ 1,0 s`. Paper chỉ định nghĩa T qua **Fig. 6**,
không cho công thức ⇒ **limitation của reference impl, không sửa**.

### 1.2 A3-V — kịch bản following (production), tập B = 72 scene **không bao giờ nằm trong eval**
Đo bằng `scripts/measure_following_scenario.py --frames-per-scene 30`. Metric pre-registered:
`median_frame(det_sinh / det_thật)` trong 0–60 m sau box xe dẫn; PASS khi median ∈ [0,5; 2,0] **và** CI95 nằm trọn.

| lớp | 50–70 | 80–110 | 120–130 |
|---|---:|---:|---:|
| Crafter | 1,98 [1,58; 2,60] | 2,73 [2,30; 3,14] | **16,92 [13,88; 20,88]** |
| Golf | 0,86 [0,51; 1,68] | 4,63 [3,97; 5,73] | 8,02 [6,07; 11,64] |

Near-field: `%det <10 m` = 39,6–81,5 %; `<4 m` = 15,9–49,2 %. Doc: `docs/measurements/following-scenario-density.md`.

### 1.3 Cổng C — detector thật, 954 frame × 3 nhánh paired, τ=0,20 (chốt trước)
Kernel `nguynhuy9669/bevfusion-gate-c-full-ch4fix` (**VALID**, 22 phút). Doc: `gate-c-runbook.md` §7c.

| nhánh | FP/frame | recall | % frame có FP |
|---|---:|---:|---:|
| clean (bỏ `label==2`) | 1,018 | **0,821** | 56,1 % |
| **plume** (bơm tổng hợp) | 1,288 | **0,570** | 66,0 % |
| **real** (giữ spray thật) | 1,243 | **0,777** | 63,1 % |

| so sánh | ΔFP [CI95] | Δrecall [CI95] |
|---|---|---|
| plume − clean | +0,299 [+0,123; +0,494] | **−0,268 [−0,372; −0,174]** |
| real − clean | +0,268 [+0,147; +0,397] | **−0,049 [−0,083; −0,019]** |
| plume − real | +0,031 [−0,126; +0,183] | **−0,219 [−0,301; −0,146]** |

⇒ TC1 (plume ↑FP) ĐẠT; TC2 (recall ≥ −0,02) TRƯỢT NẶNG ⇒ **theo pre-register: DỪNG hướng train**.
Nhưng **plume ≈ real về FP** và **tệ hơn real về recall** ⇒ lỗi là **mô hình** (mật độ/near-field), không phải
bản chất spray.

### 1.4 CDF theo cự ly — đúng thước Paper A Fig. 12
`scripts/measure_cdf_over_range.py`; doc `docs/measurements/cdf-over-range-vs-paper.md`.

- **Following:** KS **0,24–0,43**, lệch ghim ở **0–15 m**; ≥80 km/h sinh **gần hơn** thật 3,1–4,7 m; 50–70 km/h
  sinh **xa hơn** 1,6–6,5 m (ngược dấu với lệch mà paper tự chấp nhận ở 80–110).
- **Static:** KS 0,69–0,90 **nhưng do lỗi dựng kịch bản** (box đứng yên trong warm_start ⇒ 45 % detection frame 0
  nằm **trước** mặt đuôi) ⇒ **không dùng làm bằng chứng**.

---

## 2. Cơ chế gốc — đọc kỹ trước khi sửa bất cứ gì

1. **Định luật tỉ lệ theo cự ly của mô hình sai.** Ray-cast quả cầu cho detections ∝ `(r/R)²` ⇒ bùng nổ ở gần,
   vô hình ở xa. Vật lý của đám hạt quang học mỏng cho detections ∝ `r³`, **không phụ thuộc R**.
   Đo được: `n(R)` gần phẳng (`b_n = −0,112`), `r` đo được lại tăng `∝ R^0,415` (vì gom cụm bằng ngưỡng góc 0,7°).
2. **Bảng tia production chỉ phủ FOV 9,94°** (`ELEVATION_MIN=-4.06`, `MAX=+5.88`, 30 ring) — đúng "central
   elevation FOV" mà paper nói (`L368–372`) và đúng cho frame train (97,2 % điểm SSPP nằm trong FOV), **nhưng**
   khiến **40,8 % cụm thật** (toàn bộ ở R<6 m) có `n_max = 0` ⇒ near-field **không có tia nào**.
3. **`P_det = n/n_max` (paper Eq. 7) chỉ được đo ở 25 m.** Dùng như hằng số ở cự ly khác là **giả định của ta**,
   paper không nói. Đo lại: `b = +0,222 [−0,135; +0,547]` (không phân biệt được với 0) ⇒ **`P_det(R)` không cứu được
   near-field**; đã cài thành **opt-in, default 0,0** (`pdet_range_exponent`, tái lập bit-for-bit số cũ).
4. **D2-v2 (hiệu chỉnh trên train-only) đã FAIL 4/6 ô** — vì lệch **không phải hằng số tỉ lệ** (dải 0,76→13,4×).
   `spawn_scale` **giữ 1,0** trong production.

---

## 3. Việc tiếp theo, theo thứ tự (chưa làm)

1. **Cull near-field**: thêm `near_field_cull_m = 25.0` vào `spray/plume_state.py` prune (default 25; `∞`/`0` = tắt
   để tái lập số cũ; assert bit-for-bit khi tắt). **25 m = khoảng cách paper dùng để hiệu chỉnh** (`P_det` Fig. 7),
   không phải số tự chọn; **phải pre-register vào ADR trước khi đo**.
2. **Pre-register mới cho cổng C** (ghi vào ADR trước khi chạy): plume ↑FP với CI95 không chứa 0 **VÀ**
   `Δrecall(plume−clean)` không khác `Δrecall(real−clean)` quá 0,05 (vì `real−clean = −0,049` là mức spray thật tự gây).
3. Chạy lại **A3-V** (CDF 0–15 m phải hết "tấm màn") rồi **cổng C đầy đủ** (~22 phút kernel) theo pre-register mới.
4. Nếu plume ≈ real ⇒ augmentation hợp lệ ⇒ có thể sang **F** (train). Nếu không ⇒ dừng, viết kết luận âm tính.
5. Hai nhánh phụ chẩn đoán cơ chế (nếu cần tách bạch): `plume_no_atten` (tắt attenuation) và `plume_far`
   (chỉ bơm cụm ≥10 m) — mỗi nhánh ~22 phút.

---

## 4. Bản đồ tài liệu

| File | Nội dung |
|---|---|
| `docs/adr/0006-detection-protocol-and-calibration-source.md` | **ADR chuẩn**: §1–4 protocol; §5.1–5.6 A3 (verdict, 2 mở rộng, miền tin cậy, vượt điều kiện dừng, kiểm chứng độc lập, khoảng trống nghiệm thu↔production); **A3-V** (pre-registered + verdict); **D2-v2** |
| `docs/measurements/plume-a3-diagnosis.md` | §6–8: 4 lần lệch toán tử, QĐ7–QĐ14, verdict A3, lỗi định nghĩa (b') |
| `docs/measurements/roadspray-static-depth-profile.md` | **T4**: trail thật 0–60 m = 6,0/44,0/52,0 m; %mass≤20 m; body-box |
| `docs/measurements/following-scenario-density.md` | **A3-V**: đo following + D2-v2 fit/verify (§7) |
| `docs/measurements/pdet-vs-range.md` | **P_det(R)**: b=+0,222, 40,8 % cụm `n_max=0`, phụ lục §11 |
| `docs/measurements/cdf-over-range-vs-paper.md` | **CDF Fig. 12**: KS 0,24–0,43 (following) |
| `docs/measurements/gate-c-runbook.md` | **Cổng C**: 3 bug pointpillars, model0≠pointpillars, **§7b INVALID**, **§7c kết quả VALID** |
| `docs/measurements/model0-blindness-diagnosis.md` | **Lỗi kênh 4** + verify 5 frame (trước/sau) |
| `docs/measurements/a3-parameter-provenance.md` | Audit 49 tham số: 9 PHẢI BỎ |
| `docs/reference/paper-validation-protocol.md` | 17 trích dẫn: paper **không có** validation plume cho ego chạy |

Scripts đo: `measure_plume_size_tail.py` (A3) · `measure_following_scenario.py` (A3-V) · `measure_pdet_vs_range.py` ·
`measure_cdf_over_range.py` · `roadspray_static_depth_profile.py` (T4) · `sspp_infer.py` (cổng C) ·
`visualize_plume_vs_real.py` (clip so sánh).

---

## 5. Lệnh tái lập

```bash
cd <repo>
export PY="CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=."
eval $PY /opt/anaconda3/bin/python -m pytest -q tests          # 213 passed

eval $PY /opt/anaconda3/bin/python scripts/measure_plume_size_tail.py        # A3, 8 seed × 120 frame
eval $PY /opt/anaconda3/bin/python scripts/measure_following_scenario.py --frames-per-scene 30   # A3-V
eval $PY /opt/anaconda3/bin/python scripts/measure_pdet_vs_range.py          # P_det(R)
eval $PY /opt/anaconda3/bin/python scripts/measure_cdf_over_range.py --help  # CDF (nhiều mode)
eval $PY /opt/anaconda3/bin/python scripts/sspp_infer.py --dry-run           # cổng C plumbing (không cần mmcv)
```

Cổng C trên Kaggle (local **không có** mmcv/mmdet/mmdet3d):

| Kernel | Trạng thái |
|---|---|
| `nguynhuy9669/bevfusion-gate-c-plume-vs-detector` | v4 **INVALID** (lỗi kênh 4) |
| `nguynhuy9669/bevfusion-gate-c-verify5-channel4-fix` | PASS verify 5 frame |
| `nguynhuy9669/bevfusion-gate-c-full-ch4fix` | **VALID** — kết quả §1.3 |

Dataset private: `sspp-gate-c-code` (re-version khi code đổi), `sspp-gate-c-data`.
Lấy output: `kaggle kernels output <id> -p /tmp/out`.

---

## 6. Dựng lại trên máy khác

```bash
git clone https://github.com/Yuhnguyn/bevfusion-spray-pilot.git && cd bevfusion-spray-pilot
git checkout sspp
git clone https://github.com/mit-han-lab/bevfusion.git mit/bevfusion   # gitignored
git -C mit/bevfusion checkout da93b27                                  # pin bắt buộc (mit/PIN.md)
```

| Cần gì | Ở đâu |
|---|---|
| SSPP (31 GB) | `scripts/fetch_semantic_spray.py` → `data/SemanticSprayDataset` |
| RoadSpray static (zip) | `data/roadspray/*.zip` (**gitignored**, phải tải lại: Crafter_static 7 924 255 130 B, Golf_static 5 460 144 118 B, `meta_data_measurement.xlsx`) |
| `lidar-only-det.pth` (33 362 653 B) | `data/lidar-only-det.pth` — tải theo `docs/PROJECT.md` §7 |
| `mmcv`/`mmdet`/`mmdet3d` | **không cài local** — chỉ cần cho Kaggle |
| Python | `/opt/anaconda3/bin/python` (torch 2.2.2 CPU, numpy 1.26) |

⚠️ **Không có** `kaggle/gate_c/bundles/` trong repo (đã gitignore, là build artifact): tạo lại bằng
`python kaggle/gate_c/make_bundles.py`. Bundle chứa bản copy repo + checkpoint (68 MB).

---

## 7. CẤM — những việc đã gây hại và đã ghi vào ADR

1. **Không thêm bậc tự do thứ ba** cho generator. Hai mở rộng ngoài paper đã khai là **đủ**: (a) bỏ `streak`;
   (b) tán xạ `r(t) = r₀ + α·d_rel`, **α = 0,06**.
2. **Không đổi tiêu chí/ngưỡng sau khi đã thấy số.** Mọi ngưỡng phải ghi vào ADR **trước** khi đo.
3. **Không dùng SSPP để CHỌN tham số** (D2-chặt): SSPP chỉ để **kiểm chứng**. Ngoại lệ duy nhất đã được duyệt
   là D2-v2 (1 hệ số, fit 2/3 – verify 1/3, `assert fit ∩ eval = ∅`) — và nó **đã FAIL**, nên giữ `spawn_scale = 1,0`.
4. **Không "sửa cho khớp số"**: nếu kết quả xấu, ghi limitation và dừng.
5. **Không tin số cổng C trước commit `f4c6669`** — model bị nạp sai kênh 4, mọi số FP/recall trước đó vô hiệu.
6. **Không đọc chênh lệch < 25 %** trong các phép đo plume: sai số cửa sổ đã là 12–22 %.

---

## 8. Bẫy đã trả giá — 11 lần "lệch toán tử" (mỗi lần đều làm kết luận cũ vô hiệu)

1. Đo trên tầng điểm materialised (`ring=−1`) thay vì `RaycastResult.detections`.
2. Lưới tia tự dựng 32×1800 thay vì `load_beam_table()` production.
3. DBSCAN cả frame vs DBSCAN trong lát Δ=1,0 m.
4. Detections cả frame vs trong hộp đo.
5. Hình học cụm: sphere model vs chuỗi điểm dày (⇒ bỏ tiêu chí cụm).
6. Vùng bao cả thân xe (giả thuyết "68 % thân xe" **sai** — kiểm hình học chỉ 14 %).
7. **Bối cảnh mô phỏng**: ego chạy theo vs ego đứng yên (⇒ near-field bùng nổ).
8. **`P_det` dùng như hằng số ở cự ly khác 25 m**.
9. **Kênh 4**: nuScenes cột 4 = time-lag; `.bin` SSPP cột 4 = ring ⇒ model **mù** (TP=0/954). *Lỗi tốn kém nhất.*
10. **Bảng tia 9,94°** ⇒ 40,8 % cụm thật vô hình.
11. **Warm_start dựng lịch sử với box đứng yên** ⇒ detection nằm trước mặt đuôi.

**Bài học chung:** mỗi khi kết quả "quá xấu và quá hợp lý", **nghi dụng cụ trước khi nghi khoa học**.
Và: mỗi tiêu chí phải ghi rõ **đo bằng toán tử nào**, hai vế phải dùng **cùng một toán tử**.

---

## 9. Trạng thái dữ liệu (gitignored)

| File | Byte | Trạng thái |
|---|---:|---|
| `data/SemanticSprayDataset` | 31 GB | ✅ 207 scene (36 có box / 2.587 frame) |
| `data/roadspray/Crafter_static.zip` | 7 924 255 130 | ✅ 163 bag |
| `data/roadspray/Golf_static.zip` | 5 460 144 118 | ✅ 171 bag |
| `data/roadspray/Crafter_dynamic.zip` | 6 127 018 713 | ✅ 108 bag |
| `data/roadspray/meta_data_measurement.xlsx` | 26 774 | ✅ 549 dòng |
| `data/lidar-only-det.pth` | 33 362 653 | ✅ checkpoint Model 0 (`voxelnet_0p075`, 10 class nuScenes) |
| `mit/bevfusion` | — | ✅ clone, pin `da93b27` |

---

## 10. Bẫy môi trường (giữ từ nhánh cũ)

1. Phải có `env -u PYTHONPATH`, không thì numpy của venv Python 3.14 bị nạp vào Python 3.11.
2. `timeout` **không tồn tại** trên shell macOS mặc định.
3. `ps` bị sandbox chặn; dùng `job_list` để xem tiến trình.
4. Matplotlib cần `MPLCONFIGDIR=/tmp/mplc` (home không ghi được).
5. Không giải nén cả zip RoadSpray ra đĩa (7,9 GB) — stream 1 bag tại một thời điểm vào `.scratch/tmp/`.
6. `box[2]` là **đáy** hộp (không phải tâm); `box_dim` = **9** (7 hình học + 2 vận tốc).
7. Ảnh: agent phải dùng model **có đầu vào hình ảnh** mới `read_image` được; model text-only sẽ báo lỗi.
