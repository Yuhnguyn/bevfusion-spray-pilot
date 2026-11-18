# Repo-fit: RoadSpray có chen được vào thí nghiệm hiện tại không?

Audit ngày 2026-11-18, nhánh `sspp` @ `064f1c1`, cộng WIP chưa commit (`git diff --stat`:
`spray/wet_ground.py` ±340 dòng, `spray/config/wet_ground_default.yaml`, 2 file test; 4 script
`scripts/audit_cal_only.py`, `diag_cal_audit.py`, `diag_split_options.py`, `diag_split_structure.py`
untracked). Mọi số ghi kèm file nguồn; số tự đo trong audit này đánh dấu `[ĐO MỚI]` + file dữ liệu
đã đo.

**TL;DR** — Không option nào đáng làm *cho thí nghiệm*. Repo còn cách kết quả đầu tiên 3 bước
(bước 3–5 của plan: `kaggle/train/sspp_arms.py` và `sspp_eval.py` **chưa tồn tại**; grep chỉ ra
chúng trong `.hermes/plans/2026-11-13_171500-sspp-plan-ngan.md`) và không bước nào cần thêm dữ
liệu. Việc đáng làm nhất (2–4 h) là **bỏ RoadSpray khỏi phương trình**: siết cal table vào
`cal ∩ (train ∪ val)` để hết leak 6/12 test scene. Thứ duy nhất RoadSpray làm được (16–24 h) là
một câu Limitations, không đổi được verdict A/B.

---

## 1. Claim định lượng nào phụ thuộc spray STATISTICS

Tất cả đều đo trên `label == 2` của SemanticSprayDataset, tức `cal` scenes trừ khi ghi khác.
`cal` = 104/207 scene (`docs/measurements/semantic-spray-cal-vs-heldout.md:38-42`).

| # | Nơi chứa | Số | Đo trên | Tiêu thụ bởi |
|---|---|---|---|---|
| 1 | `spray/plume.py:21-47` `_CLUSTER_VISIBLE_BY_SPEED` | crafter 4,18 / 11,31 / 17,42 / 22,02 / 20,69 / 29,24 / 28,49 / 17,58 / 17,69 ở 50…130 km/h; golf 3,62…16,64 | `cal`, DBSCAN góc 0,7°/minPts 3, 15 frame/scene × 3 scene/ô = 45 frame/ô (`semantic-spray-clusters-by-speed.md:19`) | `visible_ref` → `rate` → số cụm sinh mỗi frame (`plume.py:214-231`, `:283-314`) |
| 2 | `semantic-spray-cal-vs-heldout.md:120-128` cổng G1–G7 | G1 188,0 vs 184,0 điểm noise/frame (−2,1 %); G2 13,414 vs 13,307 cụm/frame; G3 6,0 vs 6,0 điểm/cụm; G5 \|y\|p95 2,308 vs 2,401; G7 elevation 7,494° vs 7,334° | 207 scene, 60 frame/scene, τ ngưỡng đóng băng; roles theo `semantic_split.py:205-233` | verdict "7/7 PASS" (`:155`) và câu "split đại diện được cho tham số 29c" |
| 3 | `semantic-spray-cal-vs-heldout.md:139-151` "số bàn giao 29c" | noise/frame p5/med/p95 = 4,00 / 188,00 / 1.671,35; 13,41 cụm/frame; điểm/cụm 3 / 6 / 135; `tail_block_height_frac` 0,04–0,86; p95\|y\| 2,31 m; intensity 0/1/3; ring 0–31 med 8 | `cal` only | chính là đầu vào tham số generator |
| 4 | `docs/generator-reading-map.md:46-63` | `lateral_half_width_m` 2,34 (từ p95\|y\| 2,22 trên 1.022 frame `cal`); `radial_squash` 0,885 (đích r_range/r_extent 1,28); `tail_block_width_m` 3,4; `tail_block_height_frac` (0,05; 0,92); `_POINTS_MEDIAN_BY_RANGE` 30/20/14/10 (single-linkage 0,5 m); `points_per_cluster_sigma` 0,67 `[CHỌN]` | trộn `[ĐO]` trên `cal` và `[CHỌN]` | hình học plume của Arm B |
| 5 | `docs/measurements/sspp-plume-probe.md:23-32`, `:49-56` | 8 ô (group × tốc độ); det/cụm p50 thật 5,88 vs gen 14,06; height p5 thật 0,22–0,30 vs gen 0,39–0,65 m; cụm/frame gen/thật 0,20–0,73× | split `train` (16 scene × 10 frame = 160) | chẩn đoán generator, không vào bảng kết quả |
| 6 | `docs/measurements/plume-root-cause.md:29-33`, `:65-77` | điểm thật/frame 174–203 @60, 1.766–2.791 @100, 1.001–2.748 @120; gen 192–316 / 123–909 / 111–514; cụm thật max 982–1.238 điểm vs gen max ~91 | 36 scene có box + chạy generator 120 frame | thứ tự sửa generator (`:161-172`) |
| 7 | `docs/measurements/semantic-spray-stats.md:56-86`, `:109-116` | noise/frame med 159, mean 422; intensity == 0 ở 81,95 %; spray 0,25–0,5 % số điểm/scan; 17.419 scan, ~28.546 điểm/scan | 2.070 frame mẫu của 207 scene | so simulator; **cụm trong file này đã bị vô hiệu** (`:3-8`) |
| 8 | `scripts/diag_split_options.py` (untracked, chạy được) | leak: 8/16 train scene, 4/8 val, **6/12 test scene là `cal`**; cal∩test = 503/954 test frame; ở 50 / 90 / 130 km/h có 2/12, 2/10, 2/12 scene `cal` là test scene | `data/sspp_infos_{train,val,test}.pkl` + `metadata.txt` | chưa vào doc nào — đây là con số quan trọng nhất trong file này |
| 9 | `[ĐO MỚI]` 36 scene box trong `data/SemanticSprayDataset` + `data/sspp_infos_*.pkl` | tổng cả ba = **2.587**: scan `velodyne` = json `object_labels/lidar` có `instances` = frame trong infos; không scene nào lệch số velodyne vs infos (**0/36**) | chính dataset đã xử lý | phủ định option "reframe lại frame SSPP đã bỏ" (xem §3) |

Ghi chú §1: bảng #1 từng được audit bằng `sspp_infos_train.pkl` — tức trộn `cal` với `held-out` —
và `scripts/audit_cal_only.py:8-9` ghi rõ "số bẩn". `plume-root-cause.md:153-157` đo lại toàn
`train` ra 120 km/h → 11,0 trong khi bảng ghi 17,6 (lệch 1,6×). Nên **bảng #1 hiện không tái lập
được**, độc lập với chuyện RoadSpray.

---

## 2. Confound `cal`/`held-out`: hiện trạng, cái cổng sửa được, cái không

### 2.1 Người dùng đang đuổi câu gì (4 script WIP)

| Script | Câu hỏi | Trạng thái |
|---|---|---|
| `diag_cal_audit.py:1-5` | (i) bảng cal dùng 3 scene/ô — variance giữa scene có quá lớn không? (ii) Fig. 11 đo @50 m còn bảng đo @20–30 m — có phải đó là nguồn lệch? (iii) 1.766 điểm là 1 frame, cả scene thì sao? | đọc `sspp_infos_train.pkl` → **trộn role**, đúng cái `audit_cal_only.py` sinh ra để sửa |
| `audit_cal_only.py:1-10` | đo lại bảng cal **chỉ trên scene vai `cal`**, đúng protocol bảng gốc; kèm bảng phân tán theo scene (p25/p50/p75, `scene_CV`, `frame_CV`) | viết xong, chưa thấy output lưu lại |
| `diag_split_structure.py` | cal/held-out có chồng lấn split model không; cal ∩ test = scene nào | chạy được, in ra 6/12 |
| `diag_split_options.py` | 2 phương án tái cấu trúc: (A) test = held-out only; (B) calibrate chỉ trên `cal ∩ (train ∪ val)` — giá bao nhiêu frame/scene | chạy được |
| `probe_static_speeds.py:1-8` | **Crafter_static** có object chuyển động không, tốc độ bao nhiêu (đọc `/front_ibeo_lux/as_tx/objects`, `rosbags`) — vì "static là calibration set của Paper A" và RoadSpray **không có `metadata.txt`** | mới nhất (21:07 17-11), chưa có kết quả trong repo |

Tức câu đang đuổi là: *"bảng cal có đáng tin không, và nếu nó nhiễm test thì lấy dữ liệu đâu
thay thế?"* — RoadSpray được nhắm vào đúng chỗ "lấy dữ liệu đâu thay thế".

### 2.2 In-sample là gì

- Tham số generator (bảng #1, #3, #4) chọn trên `cal`; rồi chính `cal`/`held-out` được báo cáo
  là "đại diện" bằng G1–G7 (`semantic-spray-cal-vs-heldout.md:21-28`).
- **Nặng hơn**: `cal` không tách khỏi split model. 6/12 test scene là `cal`
  (`diag_split_options.py` §1–2) = **503/954 test frame (52,7 % `[ĐO MỚI]` trên
  `data/sspp_infos_test.pkl`)**. Ở đúng 3 tốc độ test (50/90/130) mỗi tốc độ có 2 scene `cal` là
  test scene. Vậy Arm B được augment bằng plume hiệu chỉnh **trên chính ô tốc độ sẽ chấm điểm**.
  Hướng lệch là có lợi cho B — nhưng độ lớn chưa đo, và tiêu chí "B < A ≥ 30 % tương đối"
  (`docs/PROJECT.md:129`) không nói được bao nhiêu phần trăm là do leak.
- Cổng tồn tại để chặn "chọn và kiểm trên cùng scene" (`spray/semantic_split.py:24-26`).

### 2.3 Cổng KHÔNG sửa gì

1. **Không sửa leak vào test** — G1–G7 chỉ so `cal` với `held-out` trên toàn dataset, không biết
   split model tồn tại. Đây đúng là lỗ hổng `diag_split_options.py` phát hiện.
2. **Không sửa bias theo tốc độ** — 7 tiêu chí pool toàn bộ tốc độ và group; lỗi 1,6× ở
   120 km/h (`plume-root-cause.md:153-157`) vẫn PASS cổng.
3. **Không sửa `label == 2` nhiễm** — cả 7 tiêu chí là thống kê của *noise*, không phải *spray*
   (`semantic-spray-cal-vs-heldout.md:164`; `semantic-spray-stats.md:131-136`).
4. **Không phải protocol paper** — paper giữ *điều kiện* chưa dùng trên cùng dataset, không chia
   scene (`docs/reference/paper-qa-notebooklm.md:130-141`); split 1:1 theo scene là `[CHỌN]`
   (`semantic-spray-cal-vs-heldout.md:163`).

### 2.4 RoadSpray có sửa được không? **Không.**

- Điều cần sửa (1) là **bookkeeping trong SSPP**: chỉ cần lọc scene, không cần byte dữ liệu mới.
- Điều cần sửa (2)/(3) đòi một tập **có nhãn** độc lập. RoadSpray **không có nhãn điểm, không có
  box** (`docs/reference/two-papers-distinction.md:49-60`: RoadSpray unlabelled, SemanticSpray =
  RoadSpray + nhãn tay; chứng cứ trực tiếp: `unzip -l data/roadspray/Crafter_static.zip` = 163
  `.bag` + 1 entry thư mục, **không có file nhãn nào**; `Crafter_dynamic.zip` = 108 `.bag`).
  G1–G7 định nghĩa trên `label == 2` → không tính được trên bag static.
  Một estimator label-free mới sẽ (a) không so được với 7 ngưỡng đã đóng băng, (b) muốn validate
  vẫn phải dùng nhãn SSPP → **vòng tròn mới**, không phải vòng tròn được phá.
- Static là **điều kiện khác** (khác ngày ghi: bag 2021-09-09 vs dynamic 2021-09-08,
  `unzip -l data/roadspray/*.zip`). Kể cả nếu có nhãn, nó là **domain thứ ba** → một thí nghiệm
  mới, không phải bản vá cho confound này.

---

## 3. Options

| Option | Chạm vào artifact | Cho phép claim gì mới | Giờ | Tooling | Blocker thật |
|---|---|---|---|---|---|
| **O1. Static làm held-out thống kê** | không có; doc mới | "cụm/frame theo tốc độ lặp lại ở điều kiện static" | 16–24 | `rosbags` 0.11.9 (Python 3.11.5 tại `/opt/anaconda3`), DBSCAN góc | không có `label == 2` → không tính được đại lượng của bảng #1/#3; không có `metadata.txt` → tốc độ/cự ly phải suy từ MarkerArray, chưa validate (`probe_static_speeds.py`) |
| **O2. Reframe frame SSPP đã bỏ** | `spray/sspp_adapter.py`, split | không có | 2–4 | đọc bag + đối chiếu `scan_id` | §1 #9: SSPP giữ **100 %** scan của 36 scene box (2.587/2.587); bag có nhiều hơn thì frame dư cũng **không nhãn điểm, không box** → không vào Arm A/B (nền train là `points[labels != 2]`, `docs/PROJECT.md:88`) và không chấm được FP/recall |
| **O3. Static làm "noise floor" để định lượng `label == 2` nhiễm** | `docs/measurements/semantic-spray-stats.md` (caveat) | "bảng cal phóng đại spray bao nhiêu %" — một câu Limitations | 16–24 | như O1 + ROI quanh object | vòng tròn: muốn nói static là "nhiễu không spray" thì phải biết nó có spray hay không — không nhãn, không README (zip chỉ có 163 bag + 1 entry thư mục) |
| **O4. Test set detection mới** | `sspp_split.json`, toàn bộ bảng kết quả | test rộng hơn | 24+ (nếu có nhãn) | pipeline label 3 lớp | không box → FP/frame và recall **không định nghĩa được**; 12 scene test đã CI rộng (`docs/adr/0005...:47`) |
| **O5. Modality radar / Ibeo** | không có | không có | 0 | – | SSPP **đã ship** `delphi_radar` (16 B/frame = 1 detection/frame), `ibeo_front` (1.368 B = 22 detection/frame), `ibeo_rear` (720 B), `radar_labels/*.npy` `[ĐO MỚI]` — bag thô không thêm gì; không GT trong các frame đó |
| **O6. Camera / fusion** | ADR-0005 | mở lại nhánh fusion | – | – | `data/roadspray/meta_data_dataset.json` (2.517 B) liệt kê 5 sensor, **không có camera**; ADR-0005 đòi 6 camera 360° + calib (`docs/adr/0005...:51`) → RoadSpray không đủ điều kiện mở lại ADR |
| **O7. Không làm gì** | – | – | 0 | – | – |
| **O8. (không cần RoadSpray) siết cal vào `cal ∩ (train∪val)`** | `scripts/audit_cal_only.py`, bảng #1, `plume.py:21-47` | "tham số generator chưa từng thấy scene test" — đúng thứ paper đòi | 2–4 | script đã 90 % có sẵn | 50 và 130 km/h **không còn** trong tập calibrate (`diag_split_options.py` §4) → phải ngoại suy ngoài dải 60–120 |
| **O9. (không cần RoadSpray) test = held-out only** | `build_sspp_split.py` | không còn scene `cal` trong test | 4–6 | – | test 954 → 451 frame, 12 → 6 scene (`diag_split_options.py` §3) → CI nới ~√2 |

**Disk (d)** `[ĐO MỚI]`: `df` = 27,50 GiB avail. `Crafter_static.zip` 7,38 GiB → giải nén
**15,98 GB** (`unzip -l`); dataset SSPP hiện tại 16,55 GB cho 17.419 scan
(`diag_split_options.py` §5). Ước tính convert 163 bag static (kp + radar/ibeo/image như SSPP)
cần ~20 GiB → **vượt** chỗ trống còn lại (~12,6 GiB). Cứu được 15,71 GiB bằng cách xoá
`data/SemanticSprayDataset.tar` (đã giải nén rồi). Không option nào ở trên cần tới 163 bag.

---

## 4. Xếp hạng

**R1 — đo leak trước, đừng tái cấu trúc vội (2–4 h). Không liên quan RoadSpray.**
Dùng `audit_cal_only.py` chạy bảng cal **hai lần**: một lần đúng như hiện tại, một lần loại 6 scene
`cal` nằm trong test (lọc theo `data/sspp_split.json`). Xem các ô 50/90/130 dịch bao nhiêu. Đây là
cách rẻ nhất để biết leak có phải vấn đề số hay chỉ là vấn đề câu chữ: nếu dịch <5 %, trích dẫn
được "generator không nhạy với scene test" và **không phải đổi split**; nếu dịch lớn, đó là một
kết quả phải báo, và lúc đó mới chọn O8 hay O9. Bản thân việc tái cấu trúc (O8/O9) đều có giá:
O8 mất hiệu chuẩn đúng tại 50 và 130 km/h (`plume.py:199-211` nội suy, dưới 50 km/h = 0 cụm),
O9 nới CI ~√2.

**R2 — O3 (16–24 h), chỉ sau khi có kết quả A/B.** Static là chỗ duy nhất có thể định lượng cái
caveat `label == 2` nhiễm — caveat đã lặp lại 3 lần trong repo mà chưa bao giờ được đo
(`semantic-spray-cal-vs-heldout.md:164`, `semantic-spray-stats.md:131-136`,
`semantic-spray-clusters-by-speed.md:102`). Giá trị: một mục Limitations trung thực. Giá trị cho
verdict: **không**.

**Trap — O1**: nghe hợp lý nhất nhưng sai bản chất: nó không "giữ lại điều kiện chưa dùng", nó
tạo ra một estimator không so được với ngưỡng đã đóng băng, rồi phải validate trên chính nhãn
SSPP → vòng tròn mới. 16–24 h cho một con số không ai tiêu thụ.

**Trap — O2**: đã bị số liệu phủ định (§1 #9 + không nhãn). Nếu ai đó vẫn muốn thử: đối chiếu
số Velodyne message trong 1 bag dynamic với số scan của scene tương ứng — nhưng kể cả dư frame,
chúng vô dụng vì thiếu `label`.

**Trap — O4**: chết ở chỗ không box. Muốn có box thì phải gán tay 163 scene — đúng bằng công
sức mà Paper B đã bỏ ra để làm SemanticSpray; đó là một luận văn, không phải một ticket.

**Waste of time — O5, O6**: dữ liệu đã có sẵn trong SSPP (O5); RoadSpray không có camera (O6).

**"Do nothing" là câu trả lời đúng** nếu câu hỏi là "áp RoadSpray vào thí nghiệm hiện tại". Thứ
đứng giữa repo và kết quả đầu tiên là: 3 lỗi convention (đã sửa, `3a971b8`), lỗi ngân sách cụm
4× (`plume-root-cause.md:41-62`, **chưa sửa**), wet ground tăng cường độ ngược ý định
(`plume-root-cause.md:115-124`, **đang sửa dở** trong working tree), rồi bước 3–4 của plan chưa
có file. Không mục nào trong đó nhận được gì từ 163 bag.

---

## 5. Chỗ docs repo đã trả lời tốt hơn phân tích mới

1. **`docs/reference/two-papers-distinction.md:43-78`** trả lời gọn câu "RoadSpray là gì so với
   calibration set của Paper A / SemanticSpray", kèm trích nguyên văn Paper B §IV và 4 con số
   cấm so sánh (`:125-132`: 75 cụm, 17,69 cụm, 16.565 scene, 1.463 frame). Đừng suy lại.
2. **`docs/reference/paper-qa-notebooklm.md:130-141`** (§8.3) đã chốt: paper **không chia scene**,
   giữ *điều kiện* chưa dùng, có bộ test riêng 1.463 frame → mọi so sánh "split của mình có đúng
   protocol paper không" đã có đáp án trong cây.
3. **`docs/adr/0005-sspp-as-detection-domain.md:49-55`** liệt kê đúng điều kiện mở lại ADR (6
   camera 360° + calib + box đủ 207 scene). RoadSpray không thoả điều nào → không cần bàn lại.
4. **`docs/measurements/plume-root-cause.md:161-172`** đã là danh sách việc đúng thứ tự cho
   generator. Bất kỳ đề xuất nào chen RoadSpray vào trước danh sách này đều sai thứ tự.
5. **`docs/measurements/semantic-spray-cal-vs-heldout.md:163-165`** đã viết ra đúng 2 caveat mà
   O1/O3 định "sửa" (split là `[CHỌN]`; `label 2` gồm nhiễu không spray). Cái thiếu chỉ là **con
   số**, không phải cách hiểu.
6. **Cảnh báo khi trích số**: 8 file `docs/measurements/*.md` được tham chiếu nhưng **đã bị xoá**
   khỏi nhánh này — `29ec-range-buckets.md`, `29ed-real-distributions.md`, `29ed2-overlap.md`,
   `29ed3-gen-overlap.md`, `29f-cluster-visibility.md`, `plume-geometry-measurements.md`,
   `plume-geometry-vs-real.md`, `plume-v2-measurements.md`. Ví dụ `semantic-spray-cal-vs-heldout.md:141`
   dẫn `plume-v2-measurements.md` cho chiều cao box 2,6206 m — không còn trong cây.
7. **Số doc sai**: `README.md:49` và `HANDOFF.md:63` ghi dataset 31 GB; đo được 16,55 GB
   (`diag_split_options.py` §5) / `du` 16 GB. Lo về disk vì thế nhẹ hơn doc mô tả.
