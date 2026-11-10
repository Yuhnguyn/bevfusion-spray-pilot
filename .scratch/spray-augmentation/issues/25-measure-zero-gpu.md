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
