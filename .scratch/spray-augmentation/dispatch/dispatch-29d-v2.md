# Ticket 29d v2: cân bằng `itr_after_water` giữa `cal` và `held-out`

HEAD: `177daf5`  Nhánh: `main`
Skill: tdd — `/Users/huynguyen/.agents/skills/tdd` (1 skill duy nhất)

Ticket gốc: `.scratch/spray-augmentation/issues/29d-semantic-split-gate.md` — **đọc trước**. Luật chia
trong brief này là **v2**; **7 tiêu chí vẫn đóng băng, không được sửa một chữ nào**.

Luật không đổi của repo: `/opt/anaconda3/bin/python`; `PYTHONPATH=.`; `CONDA_NO_PLUGINS=true`;
không thêm dependency; mọi số mới gắn `[ĐO]`/`[CHỌN]`/`[CODE]`.

## Hiện trạng (PM đã kiểm)

- Code 29d đã merge ở `9f110f9`: `spray/semantic_split.py`, `spray/semantic_stats.py`,
  `scripts/semantic_spray_split.py`, `tests/test_semantic_split.py`, `tests/test_semantic_stats.py`,
  `spray/config/semantic_spray_split.yaml`. Test hiện tại: **255 passed, 4 skipped**.
- PM đã chạy full `--measure --frames-per-scene 60` (12.420 frame). Kết quả:

  `SPLIT_GATE ok=False failed=[G1,G6,G7] frames_cal=6015 frames_heldout=6065`

  | id | cal | held-out | Δ | ngưỡng |
  |---|---:|---:|---:|---:|
  | G1 noise_frame median | 260,0 | 144,0 | **−44,6 %** | 15 % |
  | G2 clusters_frame mean | 14,796 | 11,937 | −19,3 % | 20 % → PASS |
  | G6 height p5/p50/p95 | 0,128 / 1,335 / 2,307 | 0,067 / 0,964 / 2,153 | −0,371 m (p50) | 0,20 m |
  | G7 elevation median | 7,678° | 6,861° | −0,817° | 0,565° |

  G3/G4/G5 PASS.

## Nguyên nhân gốc (PM đã đo, không phải giả thuyết)

`metadata.txt` của 6 scene trong mỗi ô có `itr_after_water` = **1,2,3,4,5,6** đúng theo thứ tự tên file,
và **bể nước vơi dần sau mỗi lần đo**. Luật v1 (parity cố định, `index % 2 == 0 → cal`) vì thế đẩy
`cal` vào **iteration 1,3,5** (ngay sau khi thay nước) và `held-out` vào **2,4,6** (nước đã vơi).

Đo 8 frame/scene, noise/frame (`label == 2`, DBSCAN góc) `[ĐO]`:

| ô | w=1 | w=2 | w=3 | w=4 | w=5 | w=6 |
|---|---:|---:|---:|---:|---:|---:|
| Crafter 100 km/h / 20 m | **1.597** | 1.177 | 1.242 | 473 | 864 | 633 |
| Crafter 100 km/h / 30 m | **1.724** | 659 | 1.681 | 534 | 544 | 333 |

Tỉ lệ trung bình `cal{1,3,5}` / `held-out{2,4,6}` = **1,62** ⇒ khớp đúng Δ −44,6 % của G1, và giải thích
luôn G6 (plume cal cao hơn) và G7 (elevation cal lớn hơn).

Các trục khác đã kiểm và **không** phải confound: `amb_tmp` hằng số trong từng ô (chỉ tăng theo ngày đo),
`measurement_itr` toàn = 1, `comment` gần như rỗng. Vậy `itr_after_water` là trục ẩn **duy nhất** bên
trong ô.

## Việc phải làm

### 1. `assign_roles` → v2 (`spray/semantic_split.py`)

```python
RULE_VERSION = "v2-parity-flip-by-cell"
SPLIT_VERSION = "semantic-spray-split-v2"

for cell_index, key in enumerate(sorted(cells)):
    members = sorted(cells[key], key=lambda meta: (meta.itr_after_water, meta.rel_path))
    offset = cell_index % 2
    for index, meta in enumerate(members):
        roles[meta.rel_path] = (
            ROLE_CAL if (index + offset) % 2 == 0 else ROLE_HELD_OUT
        )
```

Với ô 6 scene: ô chẵn nhận `{1,3,5}` vào `cal`, ô lẻ nhận `{2,4,6}` ⇒ toàn cục **mỗi vai có đúng cùng
số scene cho từng mức `w_itr`**.

Giữ nguyên: cell key `(group, object_velocity_kmh, distance_to_object_m)`, 3/3 mỗi ô, ô lẻ dư về `cal` +
`unpaired`, **không RNG**, deterministic. Cập nhật `SPLIT_RULE`, docstring module (nói rõ v1 fail vì bể
nước vơi, v2 đảo parity) và **hệ quả**: so sánh **theo từng ô** giữa hai vai **không còn nghĩa**; chỉ
aggregate role-level mới dùng được.

### 2. Test mới (`tests/test_semantic_split.py`), ≥ 4 test

1. **Cân bằng**: dataset giả 2 group × vài ô × 6 scene `w_itr` 1..6 ⇒
   `Counter(w_itr | cal) == Counter(w_itr | held-out)` cho **từng group** và toàn cục.
2. **Cấu trúc giữ nguyên**: 3/3 mỗi ô 6 scene; ô 5 scene → cal 3 / held-out 2 + `unpaired=True`; ô 1
   scene → cal + `unpaired=True`.
3. **Deterministic**: shuffle / reverse / rotate input cho cùng kết quả (test cũ vẫn phải pass).
4. Nếu thêm helper đọc bảng cân bằng (cho báo cáo) thì phải có test cho helper đó.

### 3. Progress output cho `--measure` (BẮT BUỘC — PM đã mù 36 phút vì thiếu cái này)

Thêm vào `scripts/semantic_spray_split.py`:

```
MEASURE_START role=<cal|held-out> scenes=<n> frames_per_scene=<n>
MEASURE_PROGRESS role=<r> scene=<i>/<n> frames=<f>      # mỗi 10 scene, flush=True
MEASURE_DONE elapsed=<giây> frames=<n> skipped=<n>
```

**Không** đổi phần tính toán, không đổi cách lấy frame, không đổi số frame.

### 4. Báo cáo `docs/measurements/semantic-spray-cal-vs-heldout.md`

Sinh lại từ đầu bằng `--measure`. Thêm:

- dòng `rule: v2-parity-flip-by-cell` + ngày 2026-11-11 + lý do đổi luật (1 đoạn ngắn);
- **Bảng 4 — cân bằng `itr_after_water`**: 2 group × 2 vai × 6 mốc, số scene mỗi mốc;
- câu ghi rõ: số liệu của luật v1 (`SPLIT_GATE ok=False failed=[G1,G6,G7]`) **không dùng nữa**.

### 5. Smoke (không chạy full)

```
--build                                  → SPLIT_BUILT cal=… heldout=… cells=36 unpaired=1
--verify                                 → SPLIT_VERIFY_OK
--measure --limit-scenes 6 --frames-per-scene 5   → phải thấy MEASURE_START/PROGRESS/DONE
```

Full 207 scene **PM chạy** (36 phút), không làm trong lượt này.

## Tiêu chí nghiệm thu (agent tự kiểm trước khi báo xong)

- [ ] `pytest -q tests/` ≥ **259 passed, 4 skipped**; dán số thật.
- [ ] `--build` in `cal=104 heldout=103 cells=36 unpaired=1`.
- [ ] `--verify` exit 0, chạy lại `--build` rồi `--verify` vẫn 0.
- [ ] Bảng 4 chứng minh hai vai **bằng nhau từng mốc `w_itr`**; dán bảng vào báo cáo cuối.
- [ ] Smoke measure in đủ 3 loại dòng `MEASURE_*`.
- [ ] `git status --porcelain` chỉ có: `spray/semantic_split.py`, `scripts/semantic_spray_split.py`,
      `tests/test_semantic_split.py`, `spray/config/semantic_spray_split.yaml`,
      `docs/measurements/semantic-spray-cal-vs-heldout.md`.
- [ ] Không tự commit; PM nghiệm thu rồi commit.

## Cấm

- Không đổi **7 ngưỡng**, định nghĩa đại lượng, cell key, hay toán tử cụm (`cluster_angular`).
- Không dùng `held-out` để chọn tham số; không trộn vai.
- **Không tối ưu DBSCAN O(n²)** — đó là ticket riêng; lượt này chỉ thêm progress print.
- Không đụng `spray/plume.py`, `spray/raycast.py`, `spray/beam_model.py`, `spray/config/plume_default.yaml`,
  `scripts/measure_spray_height.py`, `scripts/semantic_spray_stats.py`, `scripts/plume_v2_measure_common.py`.
- Không sửa dữ liệu trong `data/`, không train, không Kaggle, không thêm dependency.