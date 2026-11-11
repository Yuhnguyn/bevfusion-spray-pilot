# 29d: cổng chia `cal` / `held-out` cho SemanticSpray + đo lại thống kê

**Type:** task
**Status:** ready-for-agent
**Blocked by:** — (25, 27a/b, 28a–d, 29a/29b đã xong)
**Chủ:** CommandCode. PM: Hermes.
**Brief:** `dispatch/dispatch-29d.md`

## Vì sao có ticket này

Mọi tham số của generator v2 đều đang được đo trên **cả 207 scene** SemanticSpray:

| Tham số | Nguồn hiện tại |
|---|---|
| mật độ cụm/frame | `docs/measurements/semantic-spray-stats.md` (17,06 cụm/frame) |
| điểm/cụm theo cự ly | `plume-geometry-measurements.md` (30/20/14/10/10) |
| chiều cao khối | `plume-v2-measurements.md` (939.803 điểm; 5–92 % chiều cao box) |
| bề rộng khối | `|y|` p95 = 2,31 m |
| `intensity`, `ring` | `semantic-spray-stats.md`, ticket 31 tiêu chí |

Nếu giữ nguyên cách làm đó rồi báo cáo "generator khớp SemanticSpray trong ±X" trên **đúng 207 scene
đã dùng để chọn tham số**, con số là **in-sample**: nó không chứng minh được gì, ticket 31 không nghiệm
thu được, và người phản biện bác ngay. 29d cắt vòng tròn đó trước khi 29c/30/31 tiêu thụ các tham số.

## Đo được trước khi làm (PM, 2026-11-11, 0 GPU)

| # | Số `[ĐO]` | Hệ quả |
|---|---|---|
| 1 | 207 scene = `Crafter_dynamic` **108** + `Golf_dynamic` **99**; **17.419** frame; ~84 frame/scene | 1 scene = 1 timestamp = 1 lần ghi ⇒ chia theo scene, frame trong scene không rò rỉ |
| 2 | **36 ô** = `group × object_velocity × distance_to_object`; 34 ô có **6** scene, 1 ô có **2** (`Golf_dynamic` 80 km/h / 30 m), 1 ô có **1** (`Golf_dynamic` 90 km/h / 20 m) | Chia 1:1 trong từng ô; ô lẻ phải khai báo `unpaired`, không được im lặng |
| 3 | `object_velocity` 50…130 km/h bước 10; `distance_to_object` chỉ 20,0 / 30,0 m; `measurement_itr` = 1 ở 207/207; `unimog_direction` = nan | Ma trận thí nghiệm có kiểm soát ⇒ stratify được, không phải chia ngẫu nhiên |
| 4 | `amb_tmp` 18–26 °C, lệch theo lô (`Crafter` 26 °C ở 108 scene) | Không đưa `amb_tmp` vào ô chia — sẽ làm ô mất cân bằng mà không thêm thông tin |

## Luật chia — ĐÓNG BĂNG (`[CHỌN 2026-11-11]`)

1. **Ô** = `(group, object_velocity_kmh, distance_to_object_m)`.
2. Trong mỗi ô: sắp scene theo tên (lexicographic trên đường dẫn tương đối), gán **xen kẽ**
   `cal`, `held-out`, `cal`, … (chỉ số chẵn → `cal`).
3. Ô **lẻ** scene: scene dư về `cal`; ô đó mang cờ `unpaired: true` và **phải** được liệt kê trong báo cáo.
4. **Không RNG.** Cùng input → cùng output, không phụ thuộc thứ tự `os.listdir` hay thứ tự đọc file.
5. Kỳ vọng (assert, không phải ước lượng): `cal` = **104**, `held-out` = **103**, `|Δ| ≤ 2`;
   35/36 ô cân bằng đúng ±1; đúng 1 ô `unpaired`.
6. Seed/nhãn phiên bản split: `semantic-spray-split-v1`. Đổi luật ⇒ đổi nhãn, không sửa `v1`.

## 7 tiêu chí đóng băng — `cal` vs `held-out`

Đo trên `cal` và `held-out` độc lập, cùng định nghĩa, cùng `--frames-per-scene`. Mỗi dòng một verdict
`PASS` / `FAIL`; **cổng chỉ PASS khi 7/7 PASS**. Không sửa ngưỡng sau khi thấy số.

| Mã | Đại lượng | Ước lượng | Ngưỡng **sàn** (frozen) |
|---|---|---|---|
| G1 | điểm noise (`label == 2`)/frame | median | `|Δ|/cal ≤ 15 %` |
| G2 | cụm/frame (single-linkage 0,5 m, giữ cụm ≥ **3** điểm) | mean | `|Δ|/cal ≤ 20 %` |
| G3 | điểm/cụm (cụm ≥ 3 điểm) | median | `|Δ|/cal ≤ 20 %` |
| G4 | `r_range / r_extent` của cụm ≥ 3 điểm | median | `|Δ| ≤ 0,10` (tuyệt đối) |
| G5 | bề rộng ngang: `p95(|y|)` của điểm noise | p95 | `|Δ|/cal ≤ 15 %` |
| G6 | độ cao trên mặt đường đã fit (pitch/roll đã trừ) | p5, med, p95 — **cả ba** | mỗi phân vị `|Δ| ≤ 0,20 m` |
| G7 | elevation của điểm noise, `atan2(z, hypot(x, y))` | median | `|Δ| ≤ 0,5°` |

**Ngưỡng hiệu dụng** mỗi dòng = `max(sàn, 2 × Δ_halfsplit)`, trong đó `Δ_halfsplit` = chênh giữa hai
nửa của `cal` (cal-A / cal-B, chia bằng đúng luật xen kẽ trên danh sách `cal` đã sắp theo tên).
Đây là **sàn nhiễu nội tại** của chính `cal`, không phải CI hình thức — ghi nhãn `[CHỌN]` trong báo cáo.

**Cổng dữ liệu tối thiểu:** mỗi vai phải có ≥ **300 frame** và ≥ **100 cụm** (≥ 3 điểm). Thiếu ⇒ dòng
tương ứng `FAIL` với ghi chú `quá ít dữ liệu`, không được nới ngưỡng.

**Khi FAIL:** ghi nguyên số, kết luận "split không đại diện được cho tham số X", **không** trộn
`cal` vào `held-out`, **không** đổi luật chia, **không** đổi ngưỡng. Quyết định tiếp theo là của user.

## SỬA 2026-11-11 (sau khi đối chiếu paper, TRƯỚC khi đo full)

`docs/reference/paper-qa-notebooklm.md` §4 ghi paper dùng **DBSCAN `minPts = 3`, neighborhood góc 0,7°,
elevation discretisation 0,333°** (VLP-32C). Bản brief đầu tiên dùng neighbor Euclid **0,5 m** (lấy từ
`spray/spray_stats.py` cũ) ⇒ toán tử đếm cụm **không phải recipe paper**. Chốt lại:

| | Cổng `cal` vs `held-out` | Bảng phụ (so với số cũ) |
|---|---|---|
| Cụm | **DBSCAN góc**: `eps = 0,7°` trong mặt phẳng (azimuth, elevation), elevation snap lưới **0,333°**, `minPts = 3` | single-linkage **0,5 m** + lọc cụm ≥ 3 điểm |
| Áp lên `G2`, `G3`, `G4` | ✅ | chỉ để so `17,06` cụm/frame của ticket 16 |

- Đại lượng, ngưỡng sàn và luật chia **không đổi** — chỉ đổi toán tử đếm cụm.
- `azimuth` wrap ±180° phải xử lý (khoảng cách góc theo modulo 360).
- Nếu paper (hỏi lại notebook) nói rõ lân cận là **hộp** hay **tròn** trong mặt phẳng góc: theo paper;
  chưa rõ thì dùng Euclid trong mặt phẳng góc và ghi `[CHỌN]`.

**Đã hỏi lại notebook (2026-11-11, §8.1 của `docs/reference/paper-qa-notebooklm.md`)** — nguyên văn §III-B:
*"a DBSCAN algorithm is applied to the detections"*, *"applied to the point cloud in spherical coordinates
to account for the change in Cartesian resolution over distance"*, *"search neighborhood of DBSCAN is set
to 0.7° to cover at least two scan lines"*, *"three points is defined as the minimum number of points that
can form a cluster"*. Paper **không** nói hộp hay tròn, **không** nói lân cận có ràng buộc `r` ⇒ chốt:
`eps = 0,7°` **Euclid trong mặt phẳng `(azimuth, elevation)`**, elevation snap `0,333°`, `minPts = 3`,
`[CHỌN]` cho hai điểm mơ hồ.

**Số neo để so `[PAPER]`:** 100 km/h, Crafter 50 m → **33** cụm/frame, **14,3** detection/cụm,
**84,1 %** clustered (Fig. 1 text box); 130 km/h → **~75** cụm đo được (Fig. 11b). Số `17,06` cụm/frame
trong `docs/measurements/semantic-spray-stats.md` do toán tử `0,5 m` + `dense_min = 5` ⇒ **đếm thiếu**,
chỉ dùng làm bảng phụ. Ticket 31 **không** được lấy `17,06` làm mốc.

**Protocol của paper khác mình:** paper *"object distances and values, which were not utilized for the
model calibration, are used on the same data set"* (§IV-1) — giữ **điều kiện**, không chia scene; và có
bộ dữ liệu thứ hai 1.463 frame. Split scene 1:1 của 29d là `[CHỌN]` của mình; báo cáo phải nói rõ
điều này, không được trình bày như protocol paper.

## Việc phải làm

1. `spray/semantic_split.py` — luật chia thuần, đọc/ghi split, lọc scene theo vai, đánh giá 7 tiêu chí
   (hàm thuần, nhận dict số → test được bằng số tổng hợp).
2. `spray/semantic_stats.py` — thống kê **một frame** + gộp nhiều frame: `noise/frame`, `cụm/frame`,
   `điểm/cụm`, `r_range/r_extent`, `p95(|y|)`, độ cao trên mặt phẳng fit, elevation, `intensity`, `ring`.
3. `scripts/semantic_spray_split.py` — CLI `--build` / `--verify` / `--measure`, ghi
   `spray/config/semantic_spray_split.yaml` và `docs/measurements/semantic-spray-cal-vs-heldout.md`
   (idempotent; `--measure` exit 1 khi cổng FAIL).
4. `tests/test_semantic_split.py`, `tests/test_semantic_stats.py` — viết **trước** khi code.

Chi tiết chữ ký hàm, danh sách test và lệnh chạy: `dispatch/dispatch-29d.md`.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` ≥ **251 passed, 4 skipped** (239 hiện tại + ≥ 12 test mới; không skip mới).
- [ ] `spray/config/semantic_spray_split.yaml`: 207 scene, `cal` 104 / `held-out` 103, 36 ô,
      đúng 1 ô `unpaired`, có `version: semantic-spray-split-v1` và bảng 7 tiêu chí đóng băng.
- [ ] `--verify` chạy 2 lần liên tiếp: lần 1 exit 0, `--build` lại rồi `--verify` vẫn exit 0 (byte-identical).
- [ ] `--measure` sinh đủ bảng: 36 ô × vai, 7 dòng tiêu chí có `cal / held-out / Δ / Δ_halfsplit /
      ngưỡng / verdict`, phụ lục `intensity` p50/p90/p99 và `ring` phủ 0–31.
- [ ] Số bàn giao cho 29c ghi rõ: `tail_block_height_frac` p5/p95 trên `cal`, `p95(|y|)` trên `cal`,
      điểm noise/frame và cụm/frame trên `cal`.
- [ ] Không file cũ nào bị đổi số: `git diff docs/measurements/` rỗng (trừ file mới).
- [ ] Biên bản nghiệm thu trong ticket này: số đo thật, phần chưa khớp.

## Cấm

- Không train, không chạy Kaggle, không sửa `spray/plume.py`, `spray/raycast.py`, `spray/config/plume_default.yaml`.
- Không đổi luật chia, không đổi 7 ngưỡng, không đổi định nghĩa đại lượng sau khi đã xem số.
- Không dùng `held-out` để chọn tham số; không trộn hai vai.
- Không thêm dependency (chỉ `numpy` + `yaml` + stdlib).
- Không tự commit; PM nghiệm thu rồi commit.

## Biên bản nghiệm thu (PM, 2026-11-11)

**Kết luận: cổng đạt, PASS 7/7.** Ba vòng: v1 FAIL 3/7 → v2 PASS (đảo parity
theo ô, commit `09cd650`) → v3 PASS (ngưỡng = sàn, commit `a82e4e9`).

Số thật của vòng chốt (`docs/measurements/semantic-spray-cal-vs-heldout.md`,
12.080 frame, 0 frame bỏ):

| id | cal | held-out | Δ | Δ_halfsplit | sàn | verdict |
|---|---:|---:|---:|---:|---:|---|
| G1 | 188 | 184 | −2,1 % | 14,9 % | 15 % | PASS |
| G2 | 13,414 | 13,307 | −0,8 % | 3,4 % | 20 % | PASS |
| G3 | 6 | 6 | 0 % | 0 % | 20 % | PASS |
| G4 | 1,480 | 1,482 | +0,002 | 0,007 | 0,10 | PASS |
| G5 | 2,308 | 2,401 | +4,0 % | 5,5 % | 15 % | PASS |
| G6 | 0,111 / 1,197 / 2,264 | 0,093 / 1,183 / 2,248 | −0,018 / −0,014 / −0,016 | 0,013 | 0,20 | PASS |
| G7 | 7,494 | 7,334 | −0,160 | 0,264 | 0,50 | PASS |

Phân bố `itr_after_water` sau khi chốt (`[ĐO]`, đọc trực tiếp `metadata.txt`):

| group | vai | w1 | w2 | w3 | w4 | w5 | w6 | tổng |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Crafter | cal | 9 | 9 | 9 | 9 | 9 | 9 | 54 |
| Crafter | held-out | 9 | 9 | 9 | 9 | 9 | 9 | 54 |
| Golf | cal | 9 | 8 | 8 | 8 | 8 | 9 | 50 |
| Golf | held-out | 9 | 8 | 8 | 8 | 8 | 8 | 49 |
| cal_a | — | 9 | 9 | 8 | 9 | 8 | 9 | 52 |
| cal_b | — | 9 | 8 | 9 | 8 | 9 | 9 | 52 |

Phần chưa khớp / còn nợ:

1. Golf lệch 1 scene ở mốc 6 (ô `Golf 90 km/h@20 m` chỉ có 1 scene) — không
   thể cân bằng hơn vì tổng `1..6 = 21` lẻ. Chấp nhận.
2. `--measure` chưa có cờ `--out`, ghi đè báo cáo cố định → phải thêm trước khi
   dùng cổng cho 29c/31.
3. Cổng chỉ chứng minh **hai vai giống nhau về phân bố**, không chứng minh
   generator khớp số tuyệt đối với bản đo trên `cal` (việc đó thuộc 29c/31).
4. `G1` nằm sát sàn (Δ 2,1 % so với 15 %, Δ_halfsplit 14,9 %) — nếu sau này
   thêm scene, phải chạy lại cổng chứ không suy diễn.