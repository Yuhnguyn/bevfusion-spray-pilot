# Root cause recall cổng C — chuỗi bằng chứng đầy đủ (2026-11-20)

> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục S5.
> Phần còn đúng: Chuỗi bằng chứng cổng C vẫn đúng; §5 (wet_ground) SAI, xem ADR-0007.

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

## 4. SO VỚI SPRAY THẬT: plume của mình dồn điểm vào chỗ nguy hiểm 4,8 lần

Cùng tập test, cùng checkpoint, cùng frame. Spray thật = điểm `label == 2` do cảm biến
thật ghi từ nước. Plume = điểm generator sinh ra sau raycast.

48 frame, 6 scene:

| | THẬT | MÌNH | Tỉ số |
|---|---:|---:|---:|
| Tổng điểm | 27 667 | 9 262 | **0,33×** |
| Điểm trong vành 2–6 m / frame | 24,9 | 47,4 | **1,90×** |
| **Mật độ tương đối trong vành** | 1,0 | — | **5,3×** |
| Điểm nằm trong **6 m quanh vật thể** | **4,4 %** | **21,0 %** | **4,8×** |
| Điểm ở xa hơn 25 m | 3,4 % | 8,2 % | 2,4× |
| Cự ly p50 / p95 | 9,37 / 23,93 m | 11,30 / 28,51 m | — |

Đọc đúng bảng này: plume của mình **không nhiều điểm hơn** (chỉ 0,33×) — nó **bám vật thể
gấp 4,8 lần** và đồng thời **trôi xa hơn**. Hai đầu đều tệ, ở giữa thì thiếu.

### Không phải lỗi intensity

Paper A dòng 398-399: *"the final intensity value of the simulated spray detections are set
to 0"*. Và đo được **70,5 %** điểm spray thật cũng có `intensity == 0`. Nên `intensity = 0`
là **đúng paper**, không phải nguyên nhân. (`raycast.py:379-381` gán 0 — khớp [PAPER].)

### Số cụm khớp bảng đo

`cluster_count_for_speed` (bảng `_CLUSTER_VISIBLE_BY_SPEED`, đo trên `cal`):

| | 50 km/h | 90 km/h | 130 km/h |
|---|---:|---:|---:|
| crafter | 9,0 | 30,0 | 33,0 |
| golf | 4,7 | 20,9 | 25,2 |

Nên nguyên nhân **không phải số cụm** — số cụm theo đúng bảng đo. Nghi vấn nằm ở **vị trí
cụm được sinh và quỹ đạo trôi của chúng** (ticket: cụm bám vật thể quá chặt so với thật).

---

## 5. `wet_ground` — **DEAD BRANCH**, không phải "biến gây nhiễu chưa tách"

> **SỬA LẠI 2026-11-20.** Mục này trước đây xếp `wet_ground` là "nguyên nhân lớn nhất, chưa tách
> được". **Sai.** Nó là **no-op** trên đường ống production. Xem `docs/adr/0007-superseded-claims.md`
> §"Sửa một kết luận sai cụ thể".

`--wet-ground` **default True** (`scripts/sspp_infer.py:1356-1358`), log kernel xác nhận
`wet_ground=1`. Nó **chỉ chạy ở nhánh plume**; clean/real không có.

Stage này **có tác dụng thật** nếu được nối đúng — đo trên 1 078 344 điểm nền: **818 933 điểm
(75,9 %)** bị đổi intensity, p50 còn **0,370** giá trị cũ, **65,1 %** giảm hơn nửa.
Nhưng output đó **bị vứt bỏ** trước khi tới detector:

- `inject_plume_stateful` tính `base` = clean đã qua `apply_wet_ground` (`plume.py:557-566`),
  rồi trả `points_clean = clean.copy()` — tức **input y nguyên** (`plume.py:730`).
- `PlumeTransform` lại gọi `raycast_frame(clean, ...)` trên `result.points_clean`
  (`plume_transform.py:130`), **không** trên `base`.

Kiểm bằng số (2026-11-20, frame `Crafter_dynamic/0054` frame 10, cùng seed):

| | bật `wet_ground` | tắt | trùng? |
|---|---|---|---|
| `wet_points_in` trong stats | 19 922 | 0 | — |
| output rows | 30 926 | 30 926 | có |
| `np.array_equal(out["points"])` | — | — | **True (từng byte)** |
| `det` | 221 | 221 | có |

Và trên kernel: bản A7-b `--no-wet-ground` ra `gate_c_detections_nowet.jsonl` có **md5 trùng
khít** bản v5 — `18d02243961f1e2c2915692e5520c1f0`, **2.862/2.862 dòng giống hệt**, attenuation
982 814 và removed 4 957 y hệt, chỉ nhanh hơn 273 s (600 s vs 873 s).

**Hệ quả cho mọi lượt sau:** (a) đừng đổ lỗi `wet_ground` cho FP/recall; (b) đừng "sửa" tham số
wet-ground để cải thiện eval; (c) nếu muốn nó có tác dụng thật thì phải nối lại đường ống
(raycast trên `base`) — việc riêng, phải pre-register trước khi đo.

Điều này **không** đổi kết quả cổng C: Δrecall = −0,2188 vẫn đứng, đúng vì biến đó chưa từng
tác động lên frame nào.

---

## 6. Các tầng nguyên nhân, xếp theo độ lớn bằng chứng

1. **Plume bám vật thể 4,8 lần** spray thật (21,0 % vs 4,4 % điểm trong 6 m) — mục 4.
2. **Nhiễm độc feature vành 2–6 m** — quan hệ liều–đáp ứng đơn điệu (+0,891), mất hộp từ
   2,6 % lên 29,8 % khi vành dày plume.
3. **Mất điểm vật thể** (2903 điểm, 1818 trong hộp) — có thật nhưng nhỏ (0,01 % tổng).
4. **Độ mỏng vật thể** — cùng liều, vật thể mỏng mất recall **gấp 4,4 lần**
   (−1,68 vs −0,38 trên mỗi 1 % liều); `corr(điểm xe/box, Δrecall) = −0,492`.

`wet_ground` **không** nằm trong danh sách này — nó là dead branch (mục 5), đóng góp đúng bằng 0.

---

## 7. Phép đo đã chốt: ablation `--no-wet-ground`

**ĐÃ CHẠY (A7-b, kernel v6).** Kết quả: output **trùng từng byte** với bản v5
(md5 `18d02243961f1e2c2915692e5520c1f0`, 2.862/2.862 dòng), Δrecall vẫn **−0,2188**. Tiên đoán
ghi trước ở commit `fbec7d3` ("lấy lại ≥ 50 % mức sụt") **không xảy ra**, và lý do là
`wet_ground` chưa bao giờ chạy trên đường ống thật — xem mục 5.

Nghĩa là: phần đóng góp của `wet_ground` là **0**, không phải "chưa tách được". Toàn bộ −0,2188
thuộc về mục 3 và 1 ở trên.

**Còn thật sự chưa làm:** truy tại sao cụm lại **bám vật thể 4,8×**. Số cụm đúng bảng đo (`cal`), số điểm
ít hơn thật (0,33×), nên nghi vấn nằm ở **vị trí sinh cụm** và **quỹ đạo trôi** (drag
`C = −0,15 m⁻¹`, `diffusion_alpha = 0` ở Cách A). Cần đo phân bố vị trí cụm so với paper Fig. 3.

---

## 8. Cách báo cáo phải sửa

Không báo `corr(Δrecall, lượng spray)` — gây hiểu sai đúng như đã lo. Báo:

1. **retention** (0,323–0,922, p50 0,773) kèm CI Wilson;
2. **Δrecall trên mỗi 1 % liều**, chia theo độ dày vật thể;
3. **Δrecall thô, luôn kèm clean_recall**;
4. **quan hệ liều–đáp ứng theo vành 2–6 m** (mục 3) — bằng chứng cơ chế mạnh nhất;
5. **so với spray thật** (mục 4) — tỉ lệ điểm trong 6 m quanh vật thể: 21,0 % vs 4,4 %.

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
$P /opt/anaconda3/bin/python .scratch/paper-faithful/why_worse_than_real.py         # so với thật
$P /opt/anaconda3/bin/python .scratch/paper-faithful/why_concentrated.py            # vì sao bám
```
