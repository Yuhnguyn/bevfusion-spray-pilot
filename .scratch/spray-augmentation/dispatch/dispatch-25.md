# Ticket 25: đo 0 GPU — tốc độ, beam angles, quỹ đạo ego, hình học frame (chặn mọi tham số v2)

HEAD: b94cc5a  Nhánh: main
Skill: không

Ticket gốc: `.scratch/spray-augmentation/issues/25-measure-zero-gpu.md` — đọc trước.
Spec tham chiếu: `.scratch/spray-augmentation/spec-v2-paper-faithful.md` (chỉ đọc §1, §2).

## Hiện trạng (PM đã kiểm bằng máy, không suy đoán)

- Dataset local: `data/SemanticSprayDataset/` 16 GB, **207 scene** (`Crafter_dynamic` 108 + `Golf_dynamic` 99),
  **17.419 frame** có `velodyne/*.bin` và `labels/*.label` tương ứng 1–1. (`find | wc -l`)
- Mỗi scene: `metadata.txt` (1 dòng CSV: `file_name,object_name,object_velocity,object_direction,ego_velocity,
  distance_to_object,amb_tmp,unimog_direction,measurement_itr,itr_after_water,comment`), `poses.txt`
  (1 dòng/frame, **16 float** row-major 4×4), `labels/NNNNNN.label` (`int32[]`, **giá trị 0/1/2**, `2`=spray),
  `velodyne/NNNNNN.bin`, kèm `image_2`, `delphi_radar`, `ibeo_front`, `ibeo_rear`.
- Scene `Crafter_dynamic/0000_2021-09-08-14-36-56_0`: metadata `object_velocity=50, ego_velocity=50,
  distance=20.0, itr_after_water=1`; `poses.txt` **76 dòng** — tức **số frame mỗi scene KHÁC NHAU**, không phải 85.
- `velodyne/000000.bin` của scene trên: 583.560 byte = **145.890 float32 = 29.178 điểm × 5 cột**
  (thử 4 cột và 6 cột đều không chia hết → **đúng 5 cột**). Cột 3 ∈ [0; 242], cột 4 ∈ [0; 28].
- `labels/000000.label`: 29.178 int32, unique = {0,1,2}.
- Test baseline: `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **192 passed, 4 skipped**.

**Dùng `/opt/anaconda3/bin/python`** cho mọi script (3.11 + numpy 2.4.3). `python3` mặc định là 3.12 và numpy
hỏng trên máy này.

## Nguyên nhân gốc (vì sao ticket này chặn 26–31)

Spec v2 lấy mật độ cụm từ tốc độ **của đúng tập frame đem augment**, và ray casting cần góc elevation thật.
Chưa có 4 phép đo dưới đây thì mọi tham số v2 là phỏng đoán, và không phân biệt được "generator sai" với
"dữ liệu không có regime spray".

## Việc phải làm

Tạo 4 script trong `scripts/`. Mỗi script: chạy được từ root repo, exit 0, in bảng markdown ra stdout **và**
ghi section của mình vào `docs/plume-v2-measurements.md` theo đúng cặp marker
`<!-- BEGIN <tên-script> -->` … `<!-- END <tên-script> -->` (chạy lại phải **thay** section cũ, không nối thêm).
Mọi con số in ra kèm tag `[ĐO]` và tên script sinh ra nó. Không thêm dependency ngoài `numpy` (+ `csv`, `json`,
`statistics`, `pathlib` của stdlib).

1. `scripts/measure_speeds.py` — đọc **toàn bộ 207** `metadata.txt`:
   - n scene, histogram `object_velocity` (bin 10 km/h) và `ego_velocity`, phân bố `distance_to_object`,
     phân bố `itr_after_water`, `object_name` (bao nhiêu Crafter / Golf / khác).
   - **Đếm scene** có `object_velocity` ≥ 40 (ngưỡng kích hoạt) và ≥ 50 (ngưỡng paper), kèm % trên 207.
   - Đếm thêm theo **frame**: số frame thuộc scene có `object_velocity ≥ 50` trên tổng 17.419 frame, tức
     **bao nhiêu % frame sẽ KHÔNG sinh spray**. Đây là ràng buộc trần dữ liệu — phải nêu rõ bằng số.
   - **Cấm** suy vận tốc từ `poses.txt` khi metadata đã có.

2. `scripts/measure_beam_angles.py` — góc elevation cảm biến:
   - Lấy 32 góc elevation HDL-32E từ **spec nhà sản xuất, ghi URL nguồn vào doc** (tag `[PAPER]`, mỗi góc
     kèm nguồn). Không bịa bảng góc.
   - Kiểm chéo bằng **phân bố cột 4 thật** của 5 cột trong `velodyne/*.bin`: PM đo scene 0000 thấy cột 4 ∈
     [0; 28] — **không phải 0..31**. Phải kết luận cột 4 là gì (ring id? index khác?) bằng số: đếm số giá trị
     phân biệt trên ≥ 50 frame rải trên ≥ 5 scene, tần suất mỗi giá trị.
   - Với mỗi ring: tính elevation quan sát được từ chính toạ độ điểm (`atan2(z, sqrt(x²+y²))`) rồi so với góc
     danh nghĩa gần nhất. Báo **sai lệch median** mỗi ring; **nếu median ≥ 0,5° thì báo là KHÔNG KHỚP** và nêu
     số, **không tự sửa** bảng góc, không tự suy ra cảm biến khác.
   - Chốt rõ: **5 cột = (x, y, z, ?, ?)** — cột nào là intensity, cột nào là ring (hoặc không có ring), kèm
     bằng chứng số (miền giá trị, số giá trị phân biệt, tương quan với elevation).

3. `scripts/measure_ego_motion.py` — `poses.txt` của **3 scene** (chọn 1 Crafter + 1 Golf + 1 scene có
   `object_velocity` cao nhất; ghi tên scene vào doc):
   - Giải 4×4 → `x, y, yaw` mỗi frame. Xuất CSV `docs/figs/ego-motion/<scene>.csv` (cột `frame,x,y,yaw_deg`).
   - Tính tốc độ từ `d(yaw)` / vị trí và so với `ego_velocity` trong `metadata.txt` — **sai lệch < 10 %**
     mới đạt; nếu ≥ 10 % thì báo số và nêu giả thuyết (đơn vị, frame skip), không tự đổi công thức.
   - Nêu rõ: `poses.txt` **không có timestamp** → phải giả định Δt; nói rõ giả định đó bằng số (ví dụ 10 Hz
     ⇒ Δt = 0,1 s) và đánh dấu `[CHỌN]`.

4. `scripts/verify_frame_geometry.py` — 1 frame thật, scene `Crafter_dynamic/0000_2021-09-08-14-36-56_0`,
   frame 0:
   - `z` mặt đường dưới cảm biến (m): lấy **percentile 1 và 5 của z** trên các điểm mặt đường (label 0 và
     `|x|,|y| < 20 m`), in cả hai. Đây là số dùng để neo plume v2 vào mặt đường — nêu rõ chọn percentile nào.
   - Đọc `object_labels/` (nếu có) và in **3 object thật** để chốt: thứ tự cột `w`/`l` của box và đơn vị.
     Nếu không có box ở scene này thì nói rõ "không có box trong dataset" và **dừng** — không suy từ nuScenes.

### Item đã xong, KHÔNG làm lại
Item 4 của ticket (verify_constants) đã chốt 2026-11-10 và ghi vào `spec-v2-paper-faithful.md` §1. Không mở lại.

### Kết luận bắt buộc ở cuối doc
`docs/plume-v2-measurements.md` phải có mục **"Kết luận cho v2"** gồm đúng 4 dòng, mỗi dòng 1 số:
- % frame không kích hoạt spray (`object_velocity < 50`) → trần dữ liệu.
- Cột 4 của `velodyne` là gì → ray casting có dùng được ring thật hay phải tính elevation từ toạ độ.
- Đơn vị `wfh`: mm hay m — **kèm phép tính số** đối chiếu Fig. 11b (24 cụm @130 km/h) cho cả hai giả thuyết:
  `mean = (0,2·wfh + 0,1)·(v − 50)`, `count = round(max(0, mean))`. Nêu số cụm ra với `wfh = 0,001` (m),
  `wfh = 1` (mm), và `wfh = 10` (closest "1 mm viết sai thành 10"? chỉ khi có căn cứ) — chọn cái khớp 24.
- `z` mặt đường (m, percentile đã chọn) + chênh lệch so với `-1.84` mà audit v1 đã đo.

## Tiêu chí nghiệm thu

- [ ] 4 script chạy được, exit 0, chạy lại 2 lần cho ra doc **giống nhau** (idempotent, không nối section).
- [ ] `docs/plume-v2-measurements.md` có 4 section theo marker + mục "Kết luận cho v2" đủ 4 dòng số.
- [ ] Mỗi số có tag `[ĐO]`/`[PAPER]`/`[CHỌN]` và tên script sinh ra nó.
- [ ] Bảng tốc độ nêu rõ **số frame và % frame không kích hoạt spray**.
- [ ] Kết luận đơn vị `wfh` có phép tính số, không phải suy luận.
- [ ] `pytest -q tests/` vẫn **192 passed, 4 skipped** (không giảm, không skip mới).
- [ ] Không sửa file nào trong `spray/`, `mit/`, `tests/`, `kaggle/`, `proxy_eval/`.
- [ ] Không sửa `spray/config/plume_default.yaml`.

## Cấm

- Không đọc file `.label` hay `.bin` bằng `cat`/`head` (rác nhị phân); dùng `numpy.fromfile`.
- Không "ước lượng" tốc độ từ số vòng quay bánh; không có dữ liệu thì ghi **"không đo được"**.
- Không tự sửa bảng góc elevation để khớp dữ liệu; không đổi `PlumeConfig`; không train, không GPU.
- Không refactor ngoài phạm vi, không đổi pin MIT, không thêm dependency.
- Không tự commit; để PM nghiệm thu và commit.