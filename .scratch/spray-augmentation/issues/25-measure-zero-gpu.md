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

## Việc phải làm

1. `scripts/measure_speeds.py` — trên nuScenes **val**, lọc box trong 50 m:
   tốc độ ego (từ `ego_pose` hai sample liên tiếp / `timestamp`) và tốc độ box
   (`sample_annotation.velocity`). Xuất bảng: `n_frame`, `median/p90 speed`, số frame có
   ego ≥ 50 km/h, số box ≥ 40 km/h. Nếu `sample_annotation` không có thì ghi rõ và dùng
   vi phân vị trí — **không bịa**.
2. `scripts/measure_beam_angles.py` — 32 góc elevation HDL-32E: lấy từ spec nhà sản xuất (ghi URL),
   rồi **kiểm chéo** bằng phân bố `ring` thật của 1.209 frame: mỗi ring phải tương ứng một dải
   elevation, sai lệch median < 0,5°. Nếu không khớp thì báo, không tự sửa.
3. `scripts/measure_trajectory.py` — 1 scene có xe chạy ≥ 50 km/h: trích quỹ đạo 5 s của xe đó
   (position + yaw theo từng keyframe) để dùng cho bước 1. Xuất CSV.
4. ~~`scripts/verify_constants.py`~~ **XONG 2026-11-10 (PM đọc code)** — không cần giao lại.
   Kết quả, dẫn `file:line`, đã ghi vào `spec-v2-paper-faithful.md` §1:
   số cụm **tất định** `round(mean)` (`dee.cpp:509–512`); `K = 2,51` **không tồn tại** (0 hit `grep "2\.51"`);
   `T ~ N(…; σ=0,2)`; xoá `age > 4·T`; drag `N(−0,12; 0,04)` + gió 208°/2 m/s; khối phun 3,4 × 1,5 m;
   wet ground đã có sẵn trong `simulate_wet_pavement` (`dee.cpp:305–380`).
   **Còn mở:** đơn vị `wfh` — repo không kèm scenario, đã chọn **mm** theo Fig. 11b, ticket 31 đối chiếu.
5. `scripts/verify_frame_geometry.py` — 1 frame thật: `z` mặt đường dưới cảm biến (m),
   và thứ tự `w`/`l` trong box 9 cột của pipeline (in 3 box thật + `sample_annotation` gốc).

## Tiêu chí nghiệm thu

- [ ] 5 script chạy được, exit 0, mỗi script in bảng số ra `docs/plume-v2-measurements.md`.
- [ ] Mỗi số trong doc có tag `[ĐO]` và tên script sinh ra nó.
- [ ] Bảng tốc độ nêu rõ: bao nhiêu frame sẽ **không** kích hoạt spray (< 50 km/h) — đây là
      ràng buộc trần dữ liệu, phải biết trước khi làm bước 2.
- [ ] Kết luận đơn vị `wfh` có **số** đối chiếu Fig. 11b, không phải suy luận.
- [ ] Không sửa file nào trong `spray/`, `mit/`, `tests/`.

## Cấm

- Không thêm dependency mới ngoài `numpy`/`nuscenes-devkit` đã có.
- Không sửa `spray/config/plume_default.yaml`.
- Không "ước lượng" tốc độ từ số vòng quay bánh; không có dữ liệu thì ghi "không đo được".
