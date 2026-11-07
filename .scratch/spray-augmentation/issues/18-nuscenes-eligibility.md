# 18: Quét lại eligibility trên nuScenes — có ego speed, scene count, và bảng 2 chiều

**Type:** research
**Status:** ready-for-agent
**Blocked by:** — (cần 1 lần push Kaggle, không cần data local)
**Chủ:** CommandCode. PM: Hermes.

## Vì sao có ticket này

`docs/velocity-contract.md` (2026-11-05) đã quét: **≥50 km/h và front ≤30 m → 697 frame val (2,0%)**.
Con số đó thiếu ba thứ khiến nó **không dùng được để chốt eval set**:

1. **Không có vận tốc ego.** Paper §III-C chỉ augment khi *"ego-velocity exceeds 60 km/h"*. Filter hiện
   tại chỉ lọc tốc độ **xe dẫn**. Frame ego đang đứng chờ đèn mà có xe 55 km/h chạy ngang vẫn được đếm
   → plume được đặt vào chỗ mà thực tế ego không nằm trong đó.
2. **Không có số scene.** 697 frame rơi vào bao nhiêu scene? Mỗi scene 40 keyframe gần giống nhau, và
   plan yêu cầu **bootstrap theo scene** → n có hiệu dụng là **số scene**, không phải 697. Thiếu số này
   thì không biết noise floor, tức không kiểm được điều kiện G3#1.
3. **Chỉ có một điểm đo.** Chỉ biết mốc ≤30 m. Trong khi ticket 16 nghi rằng ở 30–40 m plume gần như
   không sinh điểm với cảm biến 32 tia → có thể phải chọn mốc gần hơn, và khi đó cần biết còn bao nhiêu
   frame. Hiện không có số cho các mốc 10/15/20/40/50 m.

## Việc phải làm

Tạo **kernel riêng nhẹ** `kaggle/eligibility/` (`kernel-metadata.json` + một file `main.py`), **CPU, không
GPU, không tải checkpoint**, attach cùng dataset nuScenes
(`sahangunasekara92/nuscenes-v1-0-full-keyframes`), `enable_internet: true` để `pip install nuscenes-devkit`.

Lý do không nhét vào kernel cũ: mỗi lần push `kaggle/smoke_test` tốn ~13 phút vì phải dựng lại venv
Python 3.8 + tải checkpoint từ Dropbox — với một phép đếm annotation thì quá đắt, và làm tăng nguy cơ
đụng vào artifact đang chứng minh ticket 04/06/07.

Đọc trực tiếp **nuScenes devkit**, **không** dùng infos pkl (không cần `create_data.py`, không chờ
30 phút):

### Định nghĩa phải dùng đúng (đừng tự đặt biến thể khác)

| đại lượng | định nghĩa chính xác |
|---|---|
| `d` (khoảng cách) | **min khoảng cách BEV từ gốc LIDAR_TOP tới 4 góc footprint** của box, trong **LiDAR frame** (global → ego bằng nghịch đảo `ego_pose`, ego → LiDAR bằng nghịch đảo `calibrated_sensor`). **Chỉ tính box ở phía trước: `x` tâm box trong LiDAR frame phải `> 0`.** Box phía sau / bên cạnh bị loại — plume của nó không đi vào cảm biến phía trước |
| `d_legacy` (hàng đối chứng) | khoảng cách **tâm** box tới gốc LiDAR, chỉ box có `x > 0`, **không** lấy min 4 góc — đúng định nghĩa đã sinh ra bảng 697 frame trong `docs/velocity-contract.md`. Phải in thành **một hàng riêng** |
| `v_box` | `‖nusc.box_velocity(ann_token)‖ × 3.6` km/h |
| `v_ego` | từ `ego_pose` của keyframe hiện tại và keyframe trước **trong cùng scene**, `‖Δp‖ / Δt`, `Δt = 0.5 s`. Frame đầu của scene → gán NaN và loại khỏi các hàng có lọc ego |
| class | dùng **đúng tập vehicle của ticket 03** để còn so được với bảng cũ; nếu không chắc tập đó gồm những class nào thì báo **cả hai** dòng: `car`-only và `all vehicle-ish` |
| chia split | đúng split val của repo (không tự chia lại) |

### Hàng đối chứng bắt buộc (phải in trước bảng 1)

Một hàng duy nhất: **`d_legacy ≤ 30 m`, không lọc ego, tập vehicle-ish**. Kỳ vọng xấp xỉ **952 box / 697 frame**
của bảng cũ (2026-11-05).

- Lệch < 5% → hai định nghĩa coi như tương đương, dùng số mới, ghi rõ "đã đối chứng".
- Lệch ≥ 5% → ghi rõ lệch ở đâu (tập class, điều kiện `x>0`, hay cách đo khoảng cách) và **không** được
  trộn hai bộ số trong cùng một bảng. PM sẽ quyết dùng bộ nào.

### Bảng 1 — 2 chiều: ngưỡng box speed × ngưỡng khoảng cách

Hàng: `≥50 km/h`. Cột: `d ≤ 10 / 15 / 20 / 30 / 40 / 50 m`.
Mỗi ô: `#box`, `#frame`, **`#scene`**, `frames/scene`.

### Bảng 2 — thêm lọc ego speed

Cùng cấu trúc bảng 1, thêm ba bản: `v_ego` không lọc / `≥30` / `≥50` / `≥60` km/h.

### Bảng 3 — highway

`scene.description` chứa `"highway"` (nuScenes không có cờ `is_highway`; phải parse chuỗi).
Báo **hai tầng** để tách nguyên nhân:

- (i) val có bao nhiêu scene highway, bao nhiêu frame;
- (ii) trong đó bao nhiêu frame đủ điều kiện `≥50 km/h`, `≤30 m`, `v_ego ≥50`.

Nếu (i) đã ít → highway không cứu được. Nếu (i) nhiều mà (ii) ít → vấn đề là filter, không phải scene.

### Bảng 4 — tập trung theo scene

Top 10 scene theo số frame đủ điều kiện (cột `≥50 km/h, ≤30 m`), kèm % của tổng. Để thấy 697 frame
có bị dồn vào vài scene hay không.

## Ra cái gì

- 4 bảng trong `docs/nuscenes-eligibility.md` (file mới), mỗi ô có số thật.
- `kaggle/smoke_test/evidence/eligibility.json` — JSON thô để truy lại, commit vào `evidence/`.
- Log kernel có marker `TICKET18_OK`.
- Một đoạn kết luận **5 dòng** trả lời đúng: mốc nào còn ≥100 frame và ≥20 scene; ego ≥50 km/h ăn mất
  bao nhiêu %; highway có cứu được không.

## Xong khi

- 4 bảng đầy đủ, **không ô trống**, mọi số gắn `[ĐO]`, kèm ngày chạy và version kernel.
- Mọi hàng có `#scene`; hàng nào `#scene < 10` ghi rõ **"quá ít scene, không dùng để bootstrap"**.
- Ô nào `#frame = 0` thì ghi `0`, không bỏ hàng — để thấy ngưỡng nào chết.
- `pytest -q tests/` vẫn **33 passed** (không chạm `spray/`).
- Commit: `data(nuscenes): eligibility scan with ego speed, scene counts and distance ladder`

## Không làm

- Không sửa `spray/plume.py`, không đổi `PlumeConfig`, không đổi ngưỡng trong code. Ticket này **chỉ đo**.
- Không chốt eval set — PM quyết sau khi đọc bảng.
- Không sửa `docs/velocity-contract.md`; ghi file mới và link từ đó.
- Không chạy lại `create_data.py`.
- **Chỉ push kernel một lần.** Vì vậy cell phải in từng bảng ngay khi tính xong (không dồn in ở cuối),
  và bọc từng bảng trong `try/except` để một bảng lỗi không làm mất ba bảng kia. Nếu push lần đầu fail,
  đọc log rồi báo PM trước khi push lại.

## Comments

- PM: nếu Kaggle hết quota CPU, dừng và báo — đừng đổi sang chạy local, máy local không có nuScenes.
- PM: ticket này **không** phụ thuộc 08/16/17. Chạy trước được.
- **v1 (commit `e58f3c5`, kernel `nguynhuy9669/nuscenes-eligibility-scan` version 1):** chạy với định nghĩa
  `d` **thiếu điều kiện `x > 0`**, nên số đếm gồm cả box phía sau và bên cạnh ego. Đây là lỗi trong spec
  (PM viết thiếu), không phải lỗi agent — agent đã báo đúng chỗ mơ hồ. **Không dùng bảng của v1 để chốt
  eval set**; v2 phải chạy lại với định nghĩa đã sửa + hàng đối chứng `d_legacy`.
- PM: `kaggle/eligibility/kernel-metadata.json` phải đổi `id` thành
  `nguynhuy9669/nuscenes-eligibility-scan` — Kaggle lấy slug từ `title` chứ không từ `id`, nên `id` cũ
  (`bevfusion-eligibility`) sẽ làm lần push sau lỗi. Sửa luôn `payload["kernel"]` trong `main.py`.