# 25: Đo 0 GPU — tốc độ, beam angles, quỹ đạo, hằng số (chặn mọi tham số v2)

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (spec `spec-v2-paper-faithful.md`)
**Chủ:** CommandCode. PM: Hermes.

## Vì sao ticket này chặn tất cả

Spec v2 đặt mật độ mục tiêu theo **tốc độ của đúng tập frame đem augment** `[PAPER]` Fig. 11a.
Chưa đo tốc độ thì mọi con số mật độ trong spec chỉ là phỏng đoán. Tương tự, ray casting cần
32 góc elevation thật; không có thì bước 4 không kiểm được.

Không train, không GPU. Chỉ đọc dataset + chạy script.

## Bố cục dữ liệu THẬT (PM kiểm 2026-11-10, `data/SemanticSprayDataset/`) — đọc trước khi code

| Đường dẫn | Nội dung | Ghi chú |
|---|---|---|
| `Crafter_dynamic/<scene>/metadata.txt` | CSV: `object_name, object_velocity (km/h), object_direction, ego_velocity (km/h), distance_to_object (m), amb_tmp, unimog_direction, measurement_itr, itr_after_water` | **1 dòng/scene** — vận tốc có sẵn, không phải vi phân |
| `.../poses.txt` | 85 dòng (1 dòng/frame), **16 float** = ma trận 4×4 (row-major) | quỹ đạo ego, không có timestamp |
| `.../labels/000000.label` | `int32[]`, `n = số điểm` (vd 29.747) | **nhãn semantic theo điểm**, KHÔNG phải box |
| `.../velodyne/000000.bin` | float32 ×4 | có; `image_2`, `delphi_radar`, `ibeo_front/rear` đi kèm |
| JSON meta kiểu nuScenes (`sample_annotation`, `ego_pose.json`) | **KHÔNG CÓ** | đừng viết script theo nuScenes devkit |

Hệ quả: **velocity đo trực tiếp từ `metadata.txt`**, không cần `nuscenes-devkit`.
`itr_after_water` là **biến điều khiển mức nước** của SemanticSpray (số iteration sau khi tưới)
— dùng làm proxy cho `wfh`, không phải `wfh` theo mét.

## Việc phải làm

1. `scripts/measure_speeds.py` — đọc **toàn bộ** `metadata.txt` của 207 scene:
   bảng `object_velocity`, `ego_velocity`, `distance_to_object`, `itr_after_water`.
   Xuất: n scene, histogram tốc độ, số scene có `object_velocity ≥ 50`, số scene `≥ 40`
   (ngưỡng kích hoạt spray). **Không** suy vận tốc từ `poses.txt` khi metadata đã có.
2. `scripts/measure_beam_angles.py` — 32 góc elevation HDL-32E: lấy từ spec nhà sản xuất (ghi URL),
   rồi **kiểm chéo** bằng phân bố `ring` thật của 1.209 frame: mỗi ring phải tương ứng một dải
   elevation, sai lệch median < 0,5°. Nếu không khớp thì báo, không tự sửa.
   **Kiểm thêm:** `velodyne/*.bin` là float32×4 hay ×5 (`intensity` có không), và `ring` có trong
   file không — pipeline hiện tại đọc `points (N,5)`, phải xác nhận cột 4 và 5 là gì.
3. `scripts/measure_ego_motion.py` — từ `poses.txt` của 3 scene: quỹ đạo ego (x, y, yaw mỗi frame),
   `d(yaw)/dt` so với `ego_velocity` trong `metadata.txt` (kiểm chéo, sai lệch < 10 %). Xuất CSV.
4. ~~`scripts/verify_constants.py`~~ **XONG 2026-11-10 (PM đọc code)** — không cần giao lại.
   Kết quả, dẫn `file:line`, đã ghi vào `spec-v2-paper-faithful.md` §1:
   số cụm **tất định** `round(mean)` (`dee.cpp:509–512`); `K = 2,51` **không tồn tại** (0 hit `grep "2\.51"`);
   `T ~ N(…; σ=0,2)`; xoá `age > 4·T`; drag `N(−0,12; 0,04)` + gió 208°/2 m/s; khối phun 3,4 × 1,5 m;
   wet ground đã có sẵn trong `simulate_wet_pavement` (`dee.cpp:305–380`).
   **Còn mở:** đơn vị `wfh` — repo không kèm scenario, đã chọn **mm** theo Fig. 11b, ticket 31 đối chiếu.
5. `scripts/verify_frame_geometry.py` — 1 frame thật: `z` mặt đường dưới cảm biến (m),
   và thứ tự `w`/`l` trong box 9 cột của pipeline (in 3 box thật + `sample_annotation` gốc).

## Tiêu chí nghiệm thu

- [ ] 4 script (item 1, 2, 3, 5) chạy được, exit 0, mỗi script in bảng số ra `docs/plume-v2-measurements.md`.
- [ ] Mỗi số trong doc có tag `[ĐO]` và tên script sinh ra nó.
- [ ] Bảng tốc độ nêu rõ: bao nhiêu frame sẽ **không** kích hoạt spray (< 50 km/h) — đây là
      ràng buộc trần dữ liệu, phải biết trước khi làm bước 2.
- [ ] Kết luận đơn vị `wfh` có **số** đối chiếu Fig. 11b, không phải suy luận.
- [ ] Không sửa file nào trong `spray/`, `mit/`, `tests/`.

## Cấm

- Không thêm dependency mới ngoài `numpy`/`nuscenes-devkit` đã có.
- Không sửa `spray/config/plume_default.yaml`.
- Không "ước lượng" tốc độ từ số vòng quay bánh; không có dữ liệu thì ghi "không đo được".

---

## PM nghiệm thu — 2026-11-10

**Trạng thái: done.** Thi công CommandCode (`--max-turns 80`, log `/tmp/t25.log`). Agent bị ngắt ở bước
validation cuối (EXIT=130, `Terminated.`) **sau khi** đã ghi xong file; PM tự chạy lại toàn bộ để nghiệm thu.

### Bằng chứng PM tự đo

| Kiểm | Lệnh | Kết quả |
|---|---|---|
| 4 script chạy được | `/opt/anaconda3/bin/python scripts/{measure_speeds,measure_beam_angles,measure_ego_motion,verify_frame_geometry}.py` | cả 4 **EXIT=0** |
| Idempotent | chạy 2 lượt, `shasum docs/plume-v2-measurements.md` | `3085a237…` **giống hệt** 2 lượt |
| Cấu trúc doc | marker `BEGIN/END` | **5 section**: 4 script + `conclusion` |
| Test | `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` | **192 passed, 4 skipped** (không đổi baseline) |
| Phạm vi | `git status --porcelain` | chỉ file mới: 5 script + doc + `docs/figs/ego-motion/`; **không** chạm `spray/`, `mit/`, `tests/` |

PM sửa 3 chuỗi tag trong `verify_frame_geometry.py::render_conclusion` (nhãn `[ĐO …]` ghi sai tên script —
tốc độ do `measure_speeds.py` sinh, elevation do `measure_beam_angles.py`) và 1 câu trong `measure_speeds.py`
(`wfh` giờ là mm). **Không đổi logic**, chỉ đổi nhãn nguồn; tái sinh doc rồi kiểm sha 2 lượt.

### 5 phát hiện đổi thiết kế ticket 26–31

1. **Không có quỹ đạo ego.** `poses.txt` **toàn bộ 207 scene** có cột tịnh tiến = `0.000000 m`; chỉ rotation,
   `max|R·Rᵀ−I| = 2,2e-16`. ⇒ Tốc độ suy từ vị trí = `0 m/s`, lệch **100 %** so với `metadata.txt`
   (`50`/`130` km/h) → **KHÔNG ĐẠT** ngưỡng <10 % của ticket. Kết luận: **tốc độ ego chỉ lấy từ `metadata.txt`**;
   `poses.txt` dùng được cho yaw, không dùng cho dịch chuyển.
2. **`object_velocity == ego_velocity` ở 207/207 scene**, `distance_to_object` chỉ có **20,0 m (103 scene)** và
   **30,0 m (104 scene)**, `itr_after_water` ∈ 1…6. Đây là **ma trận thí nghiệm có kiểm soát**, không phải lái tự
   nhiên: xe dẫn giữ đúng khoảng cách, cùng tốc độ ego. Vệt spray trong frame ego gần như **đứng yên tương đối**
   (đo phụ: vận tốc tương đối từ box ≤ 6,26 km/h).
3. **Box 3D thật chỉ có ở 36/207 scene** (`object_labels/lidar/`, 1 instance/frame, class `Van`).
   Với 171 scene còn lại **không có box** ⇒ hướng (c) của spec (sinh từ `metadata.txt`) là bắt buộc, không phải
   lựa chọn thẩm mỹ. Thứ tự cột box đã chốt bằng số: `size3D = (dài 6,83, rộng 2,42, cao 2,62) m`,
   tức **`x` là chiều dài** — ngược quy ước `_inside_box` của v1 (lỗi **D6** nay có bằng chứng).
4. **Ring id KHÔNG dùng được làm góc elevation.** Cột 4 (`0…31`) đúng là ring id, nhưng so cùng ID với bảng
   VLP-32C lệch median `|Δ| = 3,49°`, max `25,38°`, `27/32` ring lệch `≥ 0,5°`. Cảm biến là **VLP-32C**
   (README SemanticSpray), không phải HDL-32E như ticket ghi. ⇒ bước 4 ray casting **phải** tính
   `atan2(z, √(x²+y²))` từ toạ độ điểm.
5. **`z` mặt đường SemanticSpray = `−0,411 m`** (p1, label 0, `|x|,|y|<20 m`; p5 = `−0,372`), khớp đáy box
   thật `−0,4113 m` trong `0,0003 m`. Đây **không phải** `−1,84 m` của nuScenes. ⇒ ticket 28 phải đọc mặt đường
   **theo từng dataset**, không hardcode một hằng.

### Trần dữ liệu (chặn kỳ vọng, không chặn code)

`0,00 %` frame có `object_velocity < 50`, nhưng **16,33 % (2.844 frame) nằm đúng 50 km/h** ⇒
`mean = (0,2·wfh+0,1)·(50−50) = 0` cụm, tức **0 điểm spray** dù đã vượt ngưỡng kích hoạt 40 km/h.
Eval/calibration phải báo riêng dải 50 km/h hoặc loại khỏi mẫu dose–response.

### Việc còn mở (không thuộc ticket 25)

- `[CHỌN]` **đơn vị `wfh` trong công thức `T`**: `T = 0,02·wfh·(v−50)+0,2` cho `0,20 s` nếu `wfh` là mét (v1)
  và **1,80 s @130 km/h** (vệt 65 m) nếu `wfh = 1` mm (paper, user xác nhận 2026-11-10). Chốt trước ticket 28.
- Đơn vị `rotation3D.z` trong `object_labels` (radian vs độ) — toolkit gốc dùng `deg2rad`, script dùng trực tiếp;
  ở góc nhỏ chưa đổi kết luận, ghi lại để ticket 26 xử lý.
