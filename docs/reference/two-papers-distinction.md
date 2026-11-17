# Hai paper, hai mục đích — đừng gộp

Tài liệu này chốt lại một nhầm lẫn đã xảy ra nhiều lần trong dự án: **hai paper khác nhau bị
gộp thành một**. Ghi rõ ở đây để mọi quyết định sau trích đúng nguồn.

Nhãn số theo `docs/PROJECT.md:181`: `[PAPER]` paper nói · `[CODE]` code tham chiếu · `[ĐO]` đo trên máy này · `[CHỌN]` tự chọn.

---

## Bảng phân biệt

| | **Paper A — Augmentation** | **Paper B — SemanticSpray++** |
|---|---|---|
| Tiêu đề | Simulating Road Spray in Lidar Sensor Models | Energy-based Detection of Adverse Weather Effects in LiDAR Data |
| Tác giả | Linnhoff, Scheuble, Bijelic, Elster, Rosenberger, Winner | Piroli, Dallabetta, Kopp, Walessa, Meissner, Dietmayer |
| arXiv | **2212.08558** | **2305.16129** |
| Năm | 2022 (IEEE Sensors Journal) | 2023 (RA-L) |
| **Mục đích** | **SINH** plume bụi nước để augment | **PHÁT HIỆN** nhiễu thời tiết bằng energy score |
| Method | Mô phỏng vật lý: cluster + lifetime + raycast + wet ground | Energy-based outlier detection (hypersphere + energy loss) |
| Dataset dùng | **RoadSpray** (tự công bố) | **SemanticSpray** (tự công bố, xây từ RoadSpray) |
| Dataset URL | `tudatalib.ulb.tu-darmstadt.de/items/2894756f-...` (DOI `10.48328/tudatalib-930`) | `semantic-spray-dataset.github.io` |
| License | CC BY 4.0 | theo trang dataset |
| Vai trò trong repo này | **nguồn của `spray/plume.py`, `spray/raycast.py`, `spray/wet_ground.py`** | **nguồn của dataset + nhãn + split + metric đánh giá** |

---

## Chuỗi quan hệ giữa các dataset

### Paper A dùng **ba** bộ dữ liệu khác nhau — không phải một

| Bộ | Dùng để | Xe | Cự ly | Nhãn |
|---|---|---|---|---|
| **Calibration set** (August-Euler-Airfield, Darmstadt) | hiệu chuẩn tham số vật lý | VW Golf, VW Crafter | 25 m (Fig. 4), 50 m (Fig. 11) | không nhãn — DBSCAN thủ công |
| **STF** (SeeingThroughFog) | **train** detector | Mercedes (dataset có sẵn) | 0–50 m | có nhãn 3D box |
| **Spray test set** (closed highway, tự thu) | **test** detector | G-Class, CLA, Smart | 0–50 m | auto-label pipeline, 1463 frame |

`[PAPER]` §V-D: *"In total, **1463 frames** are collected and labeled"* — test set riêng, khác
calibration set. Tab. I: 6 tổ hợp (G-Class wet 79,9 km/h; Smart wet 118,3; CLA wet 97,4;
Smart watered 97,6; CLA watered 121,0; CLA+2×G-Class watered 96,2).

**Fig. 11 thuộc calibration set** — VW Crafter @50 m, 100 km/h, DBSCAN trên điểm thô (không nhãn).

### RoadSpray (tudatalib-930) là bộ **thứ tư** — không nằm trong Paper A

Paper A (arXiv 2212.08558) **không** cite tudatalib, không dùng chữ "RoadSpray".
RoadSpray được công bố riêng: `[3]` của Paper B = Linnhoff et al., *"Road spray in lidar and radar
data for individual moving objects"*, 2022-04, `tudatalib/handle/tudatalib/3537`.

Nội dung RoadSpray: Crafter_dynamic, Crafter_static, Golf_dynamic — **cùng xe, cùng đường thử,
cùng tham số** với calibration set của Paper A, nhưng công bố thành dataset riêng, **không nhãn**.

### SemanticSpray = RoadSpray + nhãn tay

Nguyên văn Paper B §IV (dòng 605–620 của bản text):

> "The data is based on the recently released **RoadSpray [3]** dataset, which performs large-scale
> testing of the effect of vehicle spray on LiDAR, camera, and radar sensors. The RoadSpray dataset
> provides **unlabeled** scenes of vehicles driving on wet a surface at different speeds in
> highway-like scenarios. [...] To create the SemanticSpray dataset, we **manually label each point**
> in a LiDAR scan as one of three categories: **background, vehicle, and spray**."

**Sơ đồ:**

```
Paper A (2212.08558) — augmentation
   ├─ Calibration set (airfield, Crafter/Golf, 25–50 m)  → Fig. 4, Fig. 11
   ├─ STF (train detector)
   └─ Spray test set (G-Class/CLA/Smart, 1463 frame)

RoadSpray (tudatalib-930) — dataset riêng, KHÔNG nhãn
   └─ Crafter_dynamic, Crafter_static, Golf_dynamic

SemanticSpray (Paper B, 2305.16129)
   └─ RoadSpray + nhãn tay 3 lớp → 16.565 dynamic scene
```

**RoadSpray ≈ calibration set của Paper A** về thiết bị và điều kiện, nhưng là bản công bố
đầy đủ hơn (có cả static). Không phải cùng file, nhưng cùng nguồn thực nghiệm.

---

## Hệ quả cho dự án này

### 1. Generator plume lấy từ Paper A, không phải Paper B

`spray/plume.py`, `spray/raycast.py`, `spray/wet_ground.py` port cơ chế của **Paper A**
(`openMSL/sl-1-2`, MPL-2.0). Paper B **không có** mô hình sinh plume — nó chỉ phát hiện.

### 2. Số liệu calibration lấy từ SemanticSpray (dataset của Paper B), không phải Fig. 11 của Paper A

- Bảng `_CLUSTER_VISIBLE_BY_SPEED` đo trên **SemanticSpray** (có nhãn `label == 2`).
- Fig. 11 của Paper A đo trên **calibration set** (airfield, Crafter @50 m) — **không nhãn**,
  đếm cụm bằng DBSCAN trên toàn bộ điểm trả về.

**Đây là lý do không thể "khớp Fig. 11b":**
- khác dataset (calibration set của Paper A vs SemanticSpray),
- khác cách đếm (toàn bộ điểm vs `label == 2`),
- khác cự ly (50 m vs 20–30 m — `[ĐO]` SemanticSpray chỉ có 20 m và 30 m, 0 frame ở 40–50 m).

### 3. Metric đánh giá lấy từ Paper B

- `label == 2` = spray → dùng làm GT cho SPF proxy.
- DBSCAN `eps = 0,7°`, `minPts = 3` trên `(azimuth, elevation)` — recipe của Paper A §III-B
  `[PAPER]`, nhưng áp lên nhãn của Paper B.

### 4. Wet ground: Paper A mượn của Hahner et al. 2022, không tự định nghĩa

Nguyên văn Paper A §III:

> "The first step is the simulation of the wet pavement, as road spray does not occur without water
> on the pavement. This first step leads to **significant amounts of lost ground points due to
> specular reflection** of laser beams on watered surfaces. To simulate this loss, the **wet ground
> model from [9]** is used."

`[9]` = Hahner et al., "LiDAR Snowfall Simulation for Robust 3D Object Detection", **arXiv 2203.15118**,
§3.1 + Algorithm 2. Công thức: Fresnel 2 phân cực + Snell + chuỗi phản xạ vô hạn trong màng nước.

**Không phải** `dee.cpp` của `openMSL/sl-1-2` — đó là code của một nhánh khác, có cửa sổ
`y ∈ (2, 7)` và nhánh **tăng** cường độ, cả hai đều không có trong paper nào.

---

## Ba con số dễ nhầm

| Con số | Thuộc về | Nghĩa |
|---|---|---|
| `~75 cụm/frame @130 km/h` | Fig. 11b Paper A, **calibration set @50 m** | mô phỏng vs đo, dataset không nhãn |
| `17,69 cụm/frame @130 km/h` | Bảng cal repo, **SemanticSpray @20–30 m** | DBSCAN trên `label == 2` |
| `16.565 scene` | Paper B §IV | tổng số dynamic scene của SemanticSpray |
| `1463 frame` | Paper A §V-D Tab. I | spray test set (G-Class/CLA/Smart), dùng để **test detector** |

Bốn số này **không so sánh được với nhau** — khác dataset, khác cự ly, khác cách đếm.

---

## Nguồn để đối chiếu

| Tài liệu | Đường dẫn |
|---|---|
| Paper A (augmentation) | `https://arxiv.org/pdf/2212.08558` — local: `~/.hermes/cache/scratch/spray2212.pdf` |
| Paper B (SemanticSpray++) | `https://arxiv.org/pdf/2305.16129` — local: `~/.hermes/cache/scratch/ssp2305.pdf` |
| Hahner 2022 (wet ground) | `https://arxiv.org/pdf/2203.15118` — local: `~/.hermes/cache/scratch/hahner2022.pdf` |
| RoadSpray dataset | `https://tudatalib.ulb.tu-darmstadt.de/items/2894756f-1316-4a4e-a25e-92db5f0d5b8e` (DOI `10.48328/tudatalib-930`) |
| SemanticSpray dataset | `https://semantic-spray-dataset.github.io` |
| SemanticSpray toolkit | `https://github.com/aldipiroli/semantic_spray_dataset` |
| NotebookLM | notebook `f2c09ee8-1c5c-45d3-869d-e62559073f1c` — chứa cả 2 paper |
