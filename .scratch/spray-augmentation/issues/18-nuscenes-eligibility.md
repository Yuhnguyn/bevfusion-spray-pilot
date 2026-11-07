# 18: Quét lại eligibility trên nuScenes — có ego speed, scene count, tách split

**Type:** research
**Status:** ready-for-agent
**Blocked by:** — (1 kernel CPU trên Kaggle, không cần data local)
**Chủ:** CommandCode. PM: Hermes.

## Vì sao có ticket này

`docs/velocity-contract.md` (2026-11-05) đã quét: **≥50 km/h và front ≤30 m → 697 frame (2,0%)**.
Con số đó không dùng được để chốt eval set, vì **bốn** lý do — hai cái phát hiện sau khi đọc log v1:

1. **Không có vận tốc ego.** Paper §III-C chỉ augment khi *"ego-velocity exceeds 60 km/h"*. Filter cũ
   chỉ lọc tốc độ xe dẫn, nên frame ego đang đứng chờ đèn mà có xe 55 km/h chạy ngang vẫn được đếm.
2. **Không có số scene.** 697 frame rơi vào bao nhiêu scene? Plan yêu cầu bootstrap **theo scene** → n
   có hiệu dụng là số scene, không phải số frame.
3. **Có thể nhầm split.** Bảng cũ ghi "quét toàn bộ **val** infos 34.029 frame". Nhưng nuScenes trainval
   có **34.149** keyframe, và **val chỉ có 6.019**. 34.029 ≈ toàn bộ trainval, không phải val. Nếu đúng
   vậy thì 697 frame và 2,0% đang tính trên **cả tập train**, và số tương đương trên val chỉ còn cỡ
   **~120 frame** — chuyện này đổi hẳn kết luận về độ khả thi. Phải tách split rõ ràng.
4. **Thiếu điều kiện phía trước.** Định nghĩa cũ có `x > 0` (box ở phía trước ego). v1 bỏ mất → đếm cả
   xe phía sau/bên cạnh, mà plume của chúng không đi vào cảm biến trước.

## Bài học từ v1 — đừng lặp lại

Kernel v1 (`e58f3c5`, version 1) chết sau 4 phút:

```
devkit import check failed: ImportError("cannot import name 'broadcast_to' from
'numpy.lib.stride_tricks' (/usr/local/lib/python3.13/dist-packages/numpy/lib/stride_tricks.py)")
RuntimeError: nuscenes-devkit is not importable in this image
```

Nguyên nhân: Kaggle image dùng **Python 3.13 + numpy 2.x**; `pip install nuscenes-devkit` kéo numpy
xuống **1.26.4**, làm hỏng các module đã build sẵn → import fail. Đừng cài devkit theo cách thường.

**Yêu cầu mới: script phải chạy được kể cả khi devkit không import được.** Không push lần nào mà ra
zero thông tin.

## Việc phải làm

Sửa `kaggle/eligibility/main.py` (giữ kernel `nguynhuy9669/nuscenes-eligibility-scan`):

### 1. Bỏ phụ thuộc cứng vào devkit — hai đường, tự dò

- **Đường A (devkit):** cài bằng `pip install --no-deps nuscenes-devkit==1.1.11 pyquaternion descartes`
  — **tuyệt đối không để pip đổi numpy** (`--no-deps` cho mọi gói). Import được thì dùng
  `nusc.box_velocity()` và `nuscenes.utils.splits.val`, đặt `velocity_source = "devkit"`.
- **Đường B (fallback thuần Python):** nếu devkit không import được thì vẫn phải chạy. Đọc thẳng JSON
  (`scene/sample/sample_annotation/sample_data/ego_pose/calibrated_sensor/category`), và:
  - **velocity** tự tính đúng công thức devkit: với mỗi annotation lấy instance, tìm annotation
    trước/next của cùng instance; `v = (p_next − p_prev) / ((t_next − t_prev)/1e6)`; nếu thiếu một đầu
    thì dùng đầu còn lại với annotation hiện tại; nếu `Δt > 0.5 s` thì NaN. Đặt
    `velocity_source = "fallback_python"`.
  - **val split**: tải `splits.py` từ
    `https://raw.githubusercontent.com/nutonomy/nuscenes-devkit/master/python-sdk/nuscenes/utils/splits.py`
    và đọc danh sách `val`. Nếu không tải được thì `val_split_available = false` và **vẫn chạy toàn bộ**.
  - Quaternion → ma trận xoay: viết hàm 10 dòng bằng numpy, không cần pyquaternion.

Ghi `velocity_source`, `val_split_available` vào JSON và in ra log.

### 2. Tách split — đây là câu trả lời quan trọng nhất

Báo **ba** mức, mỗi mức đủ `#boxes / #frames / #scenes / frames-per-scene`:

| mức | để làm gì |
|---|---|
| **toàn bộ keyframe trong dataset** | đối chiếu với 34.029 của bảng cũ → biết bảng cũ quét tập nào |
| **val split** | eval set thật (không được train trên frame eval) |
| **train split** | chỉ để đối chiếu, không dùng làm eval |

Đồng thời in `n_scenes_total`, `n_samples_total` để so với 34.149 / 6.019.

### 3. Định nghĩa phải dùng đúng

| đại lượng | định nghĩa |
|---|---|
| `d` | **min khoảng cách BEV từ gốc LIDAR_TOP tới 4 góc footprint** box, trong LiDAR frame. **Chỉ box phía trước: `x` tâm box trong LiDAR frame `> 0`** |
| `d_legacy` | khoảng cách **tâm** box tới gốc LiDAR, chỉ box `x > 0` — đúng định nghĩa của bảng cũ. In **một hàng riêng** |
| `v_box` | `‖velocity‖ × 3.6` km/h, `velocity` global (độ lớn không phụ thuộc frame) |
| `v_ego` | từ `ego_pose` keyframe hiện tại và keyframe trước **cùng scene**, `‖Δp‖/0,5 s`. Frame đầu scene → null, loại khỏi các hàng có lọc ego |
| class | tập vehicle của ticket 03 (8 category của `NameMapping`). In **cả** `vehicle-ish` và `car`-only |
| split | không tự chia lại |

### 4. Bảng phải in (theo thứ tự)

0. **Hàng đối chứng**: `d_legacy ≤30 m`, không lọc ego, toàn bộ keyframe → kỳ vọng ≈ **952 box / 697 frame**.
   Lệch <5% ⇒ định nghĩa tương đương. Lệch ≥5% ⇒ ghi rõ lệch ở đâu, không trộn hai bộ số.
1. **Bảng 1** — `vehicle-ish` + `car`-only, `d ≤ 10/15/20/30/40/50 m`, **cho từng split** (all/val/train).
2. **Bảng 2** — như bảng 1 nhưng thêm lọc `v_ego`: không lọc / ≥30 / ≥50 / ≥60. **Chỉ cần split val**
   (và all để đối chiếu); train chỉ in dòng không lọc ego.
3. **Bảng 3** — highway (`scene.description` chứa "highway"): (i) có bao nhiêu scene/frame highway
   trong val; (ii) funnel `≥50 km/h` → `+d≤30` → `+v_ego≥50`.
4. **Bảng 4** — top 10 scene theo frame đủ điều kiện (`≥50 km/h, d≤30 m, v_ego≥50`), kèm %eligible và %val.

## Xong khi

- Kernel `COMPLETE` (không phải ERROR), log có `TICKET18_OK`.
- `docs/nuscenes-eligibility.md` có đủ 5 bảng trên, **mọi ô có số thật**, gắn `[ĐO]`.
- `kaggle/smoke_test/evidence/eligibility.json` — bản rút gọn (bỏ mảng `frames` chi tiết nếu > 5 MB),
  commit vào `evidence/`.
- Trả lời được **3 câu, mỗi câu một con số**: (a) bảng cũ 34.029 là split nào; (b) val split còn bao
  nhiêu frame/scene ở mức `≥50 km/h, d≤30 m, v_ego≥50`; (c) highway có cứu được không.
- `pytest -q tests/` vẫn **33 passed**.

## Không làm

- Không sửa `spray/`, không đổi `PlumeConfig`, không đổi ngưỡng trong code. Ticket này **chỉ đo**.
- Không chốt eval set — PM quyết sau khi đọc bảng.
- Không sửa `kaggle/smoke_test/` (đang là bằng chứng ticket 04/06/07).
- Không để pip đổi numpy. Không `pip install nuscenes-devkit` không có `--no-deps`.
- Không chờ kernel trong session; push rồi thoát, PM poll.

## Comments

- PM: `kaggle/eligibility/kernel-metadata.json` đang có `id` = `nguynhuy9669/bevfusion-eligibility` nhưng
  Kaggle đặt tên thật là `nguynhuy9669/nuscenes-eligibility-scan` (slug lấy từ `title`). **Sửa `id`**
  thành tên thật, và sửa `payload["kernel"]` trong `main.py`, nếu không lần push sau sẽ lỗi.
- PM: v1 đã chết vì devkit; v1 **không sinh số nào dùng được**. Hai lỗi spec đã sửa trong ticket này:
  thiếu `x>0`, và thiếu tách split.
- PM: lần push này **được phép fail** — nếu fail, đọc log, sửa, push lại. Nhưng mỗi lần push phải làm
  script chạy được xa hơn lần trước; đừng push lại y nguyên.