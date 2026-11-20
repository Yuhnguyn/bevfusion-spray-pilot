# Root cause recall cổng C — chuỗi bằng chứng đầy đủ (2026-11-20)

Truy nguyên cơ chế khiến recall tụt **−0,2188 [−0,2949; −0,1555]** khi bật plume generator
(Cách A). Mỗi mục là một giả thuyết **đo được**, kèm kết luận.

---

## 1. Bảng loại trừ

| Giả thuyết | Phép đo | Kết quả |
|---|---|---|
| **Voxel eviction** (`max_num_points=10` cắt điểm xe) | Đếm điểm xe bị cắt trong voxel, 120 frame | **0 điểm bị cắt**. Voxel > 10 điểm y hệt clean/plume |
| **Hộp giả tranh chỗ** (decoy chiếm NMS) | Hộp không khớp GT trong 4 m quanh hộp GT | Nhóm GIỮ có decoy **55,1 %**, nhóm MẤT **45,9 %**. r = −0,074 |
| **Mất điểm vật thể là nguyên nhân chính** | `real_points` một mình (không cộng detections), 1696 hộp | Chỉ **2903 điểm** bị xoá/954 frame = **0,01 %**; 1818 trong hộp GT. Có đóng góp nhưng **nhỏ** |
| **Hiệu ứng toàn cục** | Mất hộp theo khoảng cách plume→hộp | Cục bộ: 2–4 m mất **22,9 %**, > 20 m chỉ **0,9 %** |
| **Tương quan dương "spray nhiều hại ít"** | retention vs mẫu số | **Artefact mẫu số** (mục 2) |

---

## 2. Nghịch lý `corr(Δrecall, lượng spray) = +0,192` — đã giải

Mỗi frame chỉ có **đúng 1 GT box** (`n_gt/frame = 1,00` cả 12 scene) ⇒ recall mỗi frame là
nhị phân. Biến sạch là **retention**:

```
retention = frame plume bắt được / frame clean bắt được
Δrecall   = clean_recall × (retention − 1)
```

Kiểm chứng: `corr(Δrecall thật, công thức) = +0,996`, sai số tuyệt đối p50 = **0,0048**.

Dấu dương là confound: `corr(Δrecall, clean_recall) = +0,205` (hiệu ứng trần) cộng
`corr(clean_recall, spray/f) = +0,537` (scene dễ nhiều spray hơn).

Retention p25/p50/p75 = 0,617 / **0,773** / 0,815 (min–max 0,323–0,922). Đây là biến cần giải thích.

---

## 3. NGUYÊN NHÂN CHÍNH: nhiễm độc feature trong VÀNH 2–6 m quanh vật thể

Chỉ xét **1632 hộp có 0 điểm plume trong footprint** (loại hẳn cơ chế "điểm nằm trên xe").
Đếm điểm plume trong vành BEV 2–6 m quanh tâm hộp:

| Điểm plume trong vành 2–6 m | n | Tỉ lệ mất hộp | Δscore p50 |
|---|---:|---:|---:|
| **0** | 898 | **2,6 %** | +0,003 |
| 1–50 | 189 | **19,0 %** | −0,029 |
| 51–200 | 326 | **29,8 %** | −0,104 |
| 201–600 | 213 | **27,2 %** | −0,110 |
| 601+ | 6 | **50,0 %** | −0,088 |

**Quan hệ liều–đáp ứng đơn điệu**, tương quan mức nhóm **+0,891**; tương quan điểm–hộp
`corr = +0,280`. Một hộp không có một điểm plume nào bên trong vẫn mất 29,8 % nếu vành
quanh nó dày plume.

Đối chứng hai vành (hộp 0 điểm trong footprint):

| Vành | Có plume | Không plume |
|---|---:|---:|
| trong 2–4 m | n=491, mất **22,0 %** | n=1141, mất 9,6 % |
| ngoài 4–6 m | n=702, mất **26,8 %** | n=930, mất **3,1 %** |

Vành ngoài tác động **mạnh hơn** vành trong (26,8 % vs 22,0 %), và nền không-plume của nó
sạch hơn (3,1 % vs 9,6 %) ⇒ tác động trải rộng chứ không chỉ ở mép hộp. Phù hợp với
receptive field của BEV feature map: plume trong bán kính ~6 m làm nhiễu đặc trưng cục bộ
mà detector dùng để tự tin vào hộp.

---

## 4. ỨNG VIÊN LỚN HƠN: `wet_ground` đổi intensity 75,9 % điểm nền

Đây là phát hiện **muộn** và có thể là nguyên nhân **lớn hơn** mục 3.

`--wet-ground` **default True** (`scripts/sspp_infer.py:1356-1358`), log kernel xác nhận
`wet_ground=1`. Nó **chỉ chạy ở nhánh plume**; clean/real không có.

Đo trên 6 scene × 6 frame (1 078 344 điểm nền):

| Chỉ số | Giá trị |
|---|---|
| Điểm bị đổi intensity | **818 933 = 75,944 %** |
| Trong đó ở mặt đường (`abs(z−road)<0,15`) | 364 280 = 44,5 % |
| Trong đó ở thân xe (`z > road+0,4`) | 72 303 = **8,8 %** |
| Trong hộp GT | 1 453 = 0,2 % |
| Tỉ lệ intensity sau/trước p05/p50/p95 | **0,002 / 0,370 / 0,687** |
| Số điểm giảm >50 % intensity | **65,1 %** |

Nghĩa là: **ba phần tư** đám mây điểm bị đổi cường độ, trung vị còn **37 %** giá trị cũ, và
8,8 % số điểm bị đổi nằm ở **thân xe**. Detector dùng `in_channels = 5`
(x, y, z, intensity, ring) ⇒ đây là thay đổi trực tiếp vào input.

Phép đo trước ra "0 điểm đổi" là **lỗi script** (không truyền `WetGroundConfig` vào
`inject_plume_stateful`), không phải kết quả.

---

## 5. Ba tầng nguyên nhân, xếp theo độ lớn bằng chứng

1. **`wet_ground` đổi intensity 75,9 % điểm nền** — biến lớn nhất, chưa tách được phần đóng
   góp riêng vì cổng C chạy `wet_ground=1` ở mọi frame plume.
2. **Nhiễm độc feature vành 2–6 m** — quan hệ liều–đáp ứng đơn điệu (+0,891), mất hộp từ
   2,6 % lên 29,8 % khi vành dày plume.
3. **Mất điểm vật thể** (2903 điểm, 1818 trong hộp) — có thật nhưng nhỏ (0,01 % tổng).
4. **Độ mỏng vật thể** — cùng liều, vật thể mỏng mất recall **gấp 4,4 lần**
   (−1,68 vs −0,38 trên mỗi 1 % liều); `corr(điểm xe/box, Δrecall) = −0,492`.

---

## 6. Phép đo CẦN làm để chốt (chưa làm)

Chạy lại cổng C với **`--no-wet-ground`** (A7-b, ~15 phút kernel), so với bản đã có. Đây là
phép tách biệt duy nhất có thể quy phần đóng góp của mục 4 — hiện tại nó bị trộn với mục 2.

Tiên đoán ghi trước: nếu `wet_ground` là nguyên nhân chính thì `--no-wet-ground` phải lấy
lại **≥ 50 %** mức sụt (Δrecall từ −0,2188 lên ≥ −0,109). Nếu chỉ lấy lại < 25 % thì mục 3
(vành plume) mới là chính.

---

## 7. Cách báo cáo phải sửa

Không báo `corr(Δrecall, lượng spray)` — gây hiểu sai đúng như đã lo. Báo:

1. **retention** (0,323–0,922, p50 0,773) kèm CI Wilson;
2. **Δrecall trên mỗi 1 % liều**, chia theo độ dày vật thể;
3. **Δrecall thô, luôn kèm clean_recall**;
4. **quan hệ liều–đáp ứng theo vành 2–6 m** (mục 3) — đây là bằng chứng cơ chế mạnh nhất.

---

## 8. Tái lập

```bash
cd /Users/huynguyen/projects/bevfusion-spray-pilot
P="CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=."
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_voxel.py              # loại H1
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_point_loss_fixed.py  # điểm bị xoá
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_occlusion_vs_decoy.py # chắn vs decoy
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_local_vs_global.py   # cục bộ 6 m
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_annulus.py           # CHỐT: vành 2-6 m
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_retention.py         # giải nghịch lý
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_fragility.py         # độ mỏng
$P /opt/anaconda3/bin/python .scratch/paper-faithful/rootcause_wet_ground_fixed.py  # wet_ground
```
