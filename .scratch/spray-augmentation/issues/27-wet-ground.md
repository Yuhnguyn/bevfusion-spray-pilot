# 27: Bước 0 — wet ground (mặt đường ướt mất điểm phản xạ gương)

**Type:** task
**Status:** needs-triage
**Blocked by:** 26
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ

`[PAPER]` §III-A: "road spray does not occur without water on the pavement", dùng mô hình
wet ground của `[9]` = Hahner et al., LiDAR snowfall simulation, CVPR 2022.

**Có 2 nguồn, ưu tiên nguồn thứ 1:**
1. `[CODE]` **cùng file** `DetectionEnvironmentalEffects.cpp:305–380` (`simulate_wet_pavement`) —
   phương trình đầy đủ eq. 12–19: `n_air = 1,0003`, `n_w = 1,33`, `pavement_depth = 0,5 mm`,
   `gamma = clamp(wfh / 0,5 mm, 0, 1)`, `t_p`, `r_wp`, intensity `× 0,3`.
   Đây chính là mô hình paper trích dẫn ⇒ **port từ đây**, không phải suy từ Python.
2. `[ĐO]` repo `SysCV/LiDAR_snow_sim` có `tools/wet_ground/` (Python) — dùng để đối chiếu chéo,
   không phải nguồn chính.

Phạm vi áp dụng trong code gốc: chỉ điểm cách mặt đường **±0,2 m** và có `y` (ngang) trong
khoảng **(2, 7) m** — tức chỉ làm tối điểm đất ở làn bên cạnh, không làm tối toàn bộ mặt đường.
`[CHỌN]` v2 giữ đúng cửa sổ này, ghi config `wet_ground.y_window_m: [2, 7]`.

v1 bỏ bước này (ADR-0002). Đó là một phần lý do ticket 11 null: ta không đổi phân bố điểm
mặt đường, chỉ thêm điểm plume.

## Việc phải làm

1. Ghim commit của `SysCV/LiDAR_snow_sim` (ghi sha vào docstring), **không** vendor cả repo:
   copy 4 file vào `spray/third_party/wet_ground/` kèm LICENSE + ghi chú nguồn.
2. `spray/wet_ground.py` — hàm `apply_wet_ground(points, ctx, cfg)`:
   ước lượng ground plane, làm mất điểm theo phản xạ gương ướt; trả `(points, stats)` với
   `stats.removed`, `stats.ground_points_in`, `stats.pool_remaining`.
3. Config `wet_ground: {enabled: false, ...}` trong `plume_default.yaml`; **mặc định tắt** ở
   ticket này, bật ở ticket 29/31 để A/B tách đóng góp.
4. `tests/test_wet_ground.py` — 3 test: tắt → điểm không đổi; bật trên point cloud tổng hợp
   phẳng → chỉ mất điểm gần `z` mặt đất; điểm cao > 1 m không bị xoá.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` không giảm số test.
- [ ] Log marker `WET_GROUND_STATS removed=<n> ground_in=<n>`.
- [ ] Trên 1 frame thật: `removed > 0` khi bật, `removed == 0` khi tắt.
- [ ] Có LICENSE + sha nguồn trong `spray/third_party/wet_ground/NOTICE.md`.

## Cấm

- Không chỉnh sửa số liệu vật lý trong `phy_equations.py` của tác giả.
- Không bật mặc định trong ticket này.

---

## PM điều chỉnh phạm vi — 2026-11-10 (trước khi giao)

Hai điểm của ticket không khớp thực tế, PM đã kiểm bằng máy và sửa trong `dispatch/dispatch-27a.md`:

1. **Không vendor `SysCV/LiDAR_snow_sim`.** Repo đó (HEAD `af376b3`) có `tools/wet_ground/` 4 file, 796 dòng,
   cần `scipy` + `sklearn` + `matplotlib`, giấy phép **CC BY-NC 4.0** (Attribution-**NonCommercial**). Repo dự án
   là công khai và artifact luận văn ⇒ vendor vào là rủi ro giấy phép, trong khi nguồn chuẩn của chính ticket
   (`dee.cpp:305–380`) là **MPL-2.0**. ⇒ **Port từ `dee.cpp`**, dùng repo Python chỉ để đối chiếu đọc.
2. **Mô hình giảm intensity, không xoá điểm.** Vé ticket ghi "làm mất điểm … `stats.removed`", nhưng hàm gốc
   `simulate_wet_pavement` **chỉ** gọi `set_intensity(...)`, không xoá detection nào. Xoá điểm là mô hình tuyết
   của Hahner. ⇒ `stats` đổi thành `points_in / attenuated / boosted / mean_ratio`.
3. Ticket tách làm **27a** (module `spray/wet_ground.py` + test + khoá YAML, chưa nối pipeline) và **27b**
   (nối vào `inject_plume_stateful`, marker trong log eval).

---

## PM nghiệm thu 27a — 2026-11-11

**Trạng thái: done.** CommandCode `--max-turns 60`, exit 0.

| Kiểm | Kết quả `[ĐO]` |
|---|---|
| `pytest -q tests/` | **223 passed, 4 skipped** (218 + 5 test mới) |
| `pytest -q tests/test_wet_ground.py` | 5 passed |
| File | `spray/wet_ground.py` (231 dòng), `tests/test_wet_ground.py` (135), `spray/config/wet_ground_default.yaml` (mới) |
| Không dependency mới | `grep scipy/sklearn/matplotlib` trong module: 0 hit |
| Frame thật | `WET_GROUND_STATS points_in=14576 attenuated=2821 boosted=11755 mean_ratio=0.914` |

**PM tự kiểm công thức** (probe riêng, 3 điểm trong cửa sổ `y`):
`wfh = 0` → tỉ lệ intensity còn lại **đúng 0,300** (= hằng 0,3 của code gốc, khớp tuyệt đối);
`wfh = 0,25 mm` → 0,165; `wfh = 1,0 mm` → 0,030 (điểm sáng) và 0,008 (điểm tối). Chiều tác động đúng:
**nhiều nước hơn ⇒ tối hơn**.

**Hai điểm PM ghi nhận:**

1. **Brief của PM sai một kỳ vọng:** tôi viết "wfh tăng ⇒ `mean_ratio` tăng". Thực tế ngược lại, và agent làm
   đúng vật lý (nước dày ⇒ truyền qua ít hơn), đồng thời ghi rõ trong docstring. Test kiểm chiều **giảm**.
   Lỗi ở brief, không ở code.
2. **YAML tách file riêng thay vì thêm khối vào `plume_default.yaml`** (ngoài brief, PM chấp thuận):
   `plume_default.yaml` là bản sao khít của các field `PlumeConfig` và được truyền thẳng vào
   `PlumeConfig(**config)`, nên một khối lạ ở top-level sẽ làm vỡ `test_plume_config_yaml.py` và constructor.
   Agent tạo `spray/config/wet_ground_default.yaml` + ghi lý do trong header. Đúng hơn brief.

**Còn lại cho 27b:** nối `apply_wet_ground` vào `inject_plume_stateful` (thứ tự: wet ground trên
`points_clean` → rồi mới thêm plume), bật/tắt qua config, và kiểm `mean_ratio` trong log eval thật.
