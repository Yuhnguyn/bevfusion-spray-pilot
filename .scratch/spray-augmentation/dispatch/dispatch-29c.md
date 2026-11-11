# DISPATCH 29c — sửa đầu ra generator plume (7 lỗi) theo số đo `cal`

**Cho:** CommandCode, `--yolo`, skill `tdd`.
**HEAD khi giao:** `13557da` (nhánh `main`). Ticket nguồn:
`.scratch/spray-augmentation/issues/29-ray-casting-attenuation.md` (**đọc hết, 135 dòng** — brief này
chỉ là thứ tự thi công và các mốc kiểm, không thay ticket).
**Skill:** `tdd` — viết test trước cho từng mục, đỏ rồi mới sửa, xanh rồi đi tiếp.

## 0. Bối cảnh một đoạn

`spray/plume.py` sinh cụm spray + `spray/raycast.py` cast tia để quyết định detection. Bản hiện tại
sinh **quá nhiều cụm**, intensity sai, khối sau đuôi cứng 1,5 m, tán xạ ngang Gaussian hẹp, và chậm
266–476 ms/frame. Hậu quả: augmentation gần như vô hại trong A/B v1 (interaction −0,0031, CI95
[−0,0140; 0,0017]) ⇒ phải sửa **đầu ra** cho khớp dữ liệu thật trước khi train lại.

Mọi đích là số đo trên **`cal`** (104 scene). `held-out` **cấm** dùng để chọn tham số.

## 1. Số bàn giao (đã đo, `[ĐO]` — không cần đo lại trừ khi brief nói rõ)

| đại lượng | giá trị trên `cal` |
|---|---:|
| chiều cao noise trên mặt đường p5 / med / p95 | **0,111 / 1,197 / 2,264 m** |
| p95(\|y\|) hệ LiDAR | **2,308 m** |
| noise/frame (mọi tốc độ, median) | **188** |
| cụm/frame (mọi tốc độ, mean) | **13,414** |

| km/h | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Crafter cụm/frame | 4,18 | 11,31 | 17,42 | 22,02 | 20,69 | **29,24** | 28,49 | 17,58 | **17,69** |
| Golf cụm/frame | 3,62 | 8,84 | 11,36 | 12,87 | 10,51 | 18,07 | 16,69 | 15,27 | 16,64 |
| Crafter det/cụm (med) | 7,8 | 5,6 | 5,1 | 14,6 | 15,3 | **19,4** | 16,5 | 53,8 | 36,2 |

Bảng gốc: `docs/measurements/semantic-spray-clusters-by-speed.md`. Cách đo: DBSCAN `eps = 0,7°`
Euclid trên `(azimuth, elevation)`, `minPts = 3`, elevation snap `0,333°`, azimuth wrap 360°,
chỉ `label == 2`.

## 2. Thứ tự thi công (bắt buộc — khác thứ tự trong ticket, có lý do)

Ticket liệt kê 9 mục theo chủ đề. Thi công theo **4 checkpoint** dưới đây vì mục 7 (giảm số cụm)
tự động hạ latency ~6×, nên phải làm 7 **trước** rồi mới biết mục 4 cần tối ưu thêm bao nhiêu.

Sau **mỗi** checkpoint: `pytest -q tests/` phải xanh, ghi lại số passed. Nếu một checkpoint không
thể xanh sau 3 lần sửa, **dừng và báo** (ghi rõ test nào, vì sao) thay vì nới test.

### CP1 — mục 7 + 8: số cụm theo bảng đo `cal`, rồi canvas điểm

- `spray/plume.py:144` `cluster_count_for_speed` đang dùng `(0,2·wfh+0,1)·(v−50)` [CODE dee.cpp].
  Thay bằng **bảng tra theo lớp xe** (`Crafter` / `Golf`) + nội suy tuyến tính giữa các mốc 10 km/h,
  đường cong **không đơn điệu** nên **không** fit `a·(v−v0)`.
- Công thức ticket: `rate(v) = visible_ref(v) / K(T_ref(v))`, `visible = round(rate × K(T(wfh, v)))`.
  `rate` **không** chứa `wfh`; độ ẩm chỉ tác động qua `T`. `T` **giữ nguyên** (`plume.py:165`).
- `K` = `steady_state_cluster_factor` (`plume.py:178`) — dùng lại, không viết mới.
- Golf có bảng riêng (paper `NOT STATED` cho Golf).
- Mục 8: sau khi hạ số cụm, kiểm canvas ở 100 km/h Crafter: `29,24 × 19,4 ≈ 570` điểm trong cụm;
  đích tổng điểm spray/frame **570–1.555**. Lệch thì chỉnh **median `points_per_cluster`**
  (`plume.py:82`, đang `17.0`), **không** đổi dạng `P_det`, **không** nâng trần.
- In bảng đối chiếu 9 mốc × 2 lớp (đo-vs-code) vào cuối lần chạy.

### CP2 — mục 1, 2, 3, 9: intensity, trần điểm, khối đuôi, tán xạ ngang

- **Mục 1** `raycast.py:256–261`: bỏ `intensity * 255 * ...`. Detection sinh ra có
  `intensity = 0` tuyệt đối `[PAPER]`. `N(0,5; 0,05)` **chỉ** xếp hạng strongest-return trong một
  beam, không nhân 255, không xuất ra. Điểm **thật** vẫn bị attenuation `e^(−2·0,02·L)`.
- **Mục 2** `plume.py:104` + hai chỗ cắt `plume.py:310`/`:466`: bỏ `max_injected_points = 2000`,
  thay `max_injected = max(500, round(0,05 × số điểm thật của frame))`; vẫn báo `capped=<n>`.
- **Mục 3** `plume.py:116` `tail_block_height_m = 1.5` (dùng ở `:394`, `:402`) → thay bằng
  phân số chiều cao box, khởi điểm `frac = (0,05; 0,92)`, đáy = mặt đường + `0,05·h`
  (z đáy box SemanticSpray = `−0,411 m`). Bề rộng giữ `3,4 m`.
  **Đích là ba phân vị đã đo**: p5/med/p95 = `0,111 / 1,197 / 2,264 m`, mỗi cái lệch ≤ `0,20 m`;
  elevation median của điểm sinh ra vào `8,9–11,0°` ở 70/100/130 km/h. Nếu `frac` khởi điểm không
  đạt, chỉnh `frac` **và ghi lại số đo dẫn tới giá trị mới** trong ticket.
- **Mục 9** `plume.py:255` `rng.normal(0,cfg.lateral_sigma_m)` → phân bố **đều** trên `±half_width`
  `[PAPER]`. `half_width` **không chọn tay**: đo `p95(|y − y_tâm_box|)` của điểm noise thật trên
  `cal` rồi đặt `half_width = p95 / 0,95` (đều trên `±a` có `p95 = 0,95·a`). In **cả hai** số
  (2,308 m là `p95(|y|)` hệ LiDAR, chỉ để tham chiếu). Test histogram 10 bin, χ² không bác `p > 0,01`.

### CP3 — mục 4, 5, 6: latency, marker, xoá bảng beam cũ

- **Đo lại latency trước khi tối ưu** (sau CP1 số cụm đã giảm ~6×; rất có thể đã < 100 ms).
  Đo bằng `time.perf_counter`, 100 cụm, in ms thật.
- Nếu vẫn > 100 ms: áp hai luật của `dee.cpp:232–238` — (a) lọc beam theo cửa sổ
  `min/max_azimuth` của từng cụm trước khi cast; (b) bỏ qua cụm đã ra sau mặt phẳng cảm biến.
  **Không** vector hoá kiểu tăng bộ nhớ vượt 2 GB.
- **Mục 5** marker mỗi frame có plume:
  `PLUME_RAYCAST beams=<n> hit=<n> det=<n> att_m=<L> capped=<n> ms=<t>` — đủ 6 khoá.
- **Mục 6** xoá `spray/config/beam_elevation.yaml`; `spray/beam_model.py` chỉ còn lưới đều
  `0,333° × 0,197307°`, FOV `−4,06…+5,88°`; `load_beam_table` (`:53`) không còn đọc YAML.
  `grep -rn beam_elevation` phải rỗng.

### CP4 — tự kiểm cuối và bảng bàn giao cho PM

In bảng: cụm/frame đủ 9 mốc × 2 lớp (đo-vs-code, % lệch), det/cụm @100 và @130, điểm/frame tổng,
p5/med/p95 chiều cao, `p95(|lateral|)` sinh ra vs đo, latency ms, số test passed. Không tự commit.

## 3. Test bắt buộc thêm (ngoài test hiện có)

1. `intensity` của **100 %** detection sinh ra `== 0`; điểm thật sau plume có intensity giảm;
   `points_clean` **byte-equal**.
2. Cụm/frame ở cả 9 mốc × 2 lớp trong **±20 %** bảng `cal` (dùng `rate`/`visible` trực tiếp, không
   qua raycast — test nhanh).
3. `lateral` là đều: χ² 10 bin `p > 0,01`; và **không** còn `rng.normal` cho `lateral`
   (`grep` trong diff).
4. Trần điểm: frame 10.000 điểm thật → `max_injected = 500`; frame 40.000 → `2.000`; frame 1.000 →
   `500` (sàn); `capped` được báo.
5. Khối đuôi: với box cao `2,62 m`, điểm sinh ra nằm trong `[đáy + 0,05·h, đáy + 0,92·h]` ± `1e-6`.
6. Marker: đủ 6 khoá, parse được bằng regex.
7. Không file nào reference `beam_elevation.yaml`; `spray/config/beam_elevation.yaml` không tồn tại.

## 4. Cấm

- Không sửa `spray/semantic_split.py`, `tests/test_semantic_split.py`,
  `spray/config/semantic_spray_split.yaml`, `scripts/semantic_spray_split.py`,
  `docs/measurements/semantic-spray-cal-vs-heldout.md` — đó là cổng 29d đã đóng.
- Không dùng `held-out` để chọn bất kỳ tham số nào.
- Không đổi **dạng** `P_det` (lognormal bốc `n` mỗi cụm, Bernoulli mỗi tia `n/n_max`); chỉ được đổi
  tốc độ sinh cụm (CP1) và median `points_per_cluster`.
- Không đổi `T`, `C = −0,15`, ngưỡng `age > 4T`, `wfh`.
- Không thêm ngưỡng cắt cụm theo mét (`p5` của `x` dao động `−40,6…+3,7 m` giữa hai nửa scene).
- Không đổi/nới test cũ để dễ qua; nếu test cũ mâu thuẫn với ticket thì **báo**, không tự xoá.
- Không train, không chạy Kaggle, không commit.

## 5. Lệnh smoke (chạy trong repo, `CONDA_NO_PLUGINS=true PYTHONPATH=.`)

```bash
/opt/anaconda3/bin/python -m pytest -q tests/
/opt/anaconda3/bin/python -m pytest -q tests/test_plume.py tests/test_raycast.py tests/test_beam_model.py
grep -rn "beam_elevation" --include=*.py --include=*.yaml . | grep -v docs
```

Latency và các phân vị: viết script tạm ở `/tmp`, **không** thêm file đo vào repo trừ khi ticket yêu cầu.

## 6. PM sẽ nghiệm thu độc lập

`git diff --stat` đúng phạm vi; `pytest` ≥ 266 passed / 4 skipped; đọc code xác nhận `intensity = 0`
và không còn `max_injected_points`; tự chạy một frame thật để đọc marker + đo lại 3 phân vị chiều cao
và số cụm; đối chiếu bảng 9 mốc; đo latency bằng máy PM. Lệch số nào PM ghi lại thành mục "chưa khớp".