Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. `AGENTS.md`
2. `.scratch/spray-augmentation/issues/21-port-reference-mechanisms.md` ← **nguồn đúng, làm đúng ticket này**
3. `spray/plume.py` (generator hiện tại) + `tests/test_plume.py`
4. `docs/plume-geometry-vs-real.md` (số đo ticket 16 — bảng điểm/cụm theo cự ly)

## Bối cảnh một câu

Code tham chiếu của Linnhoff 2022 **đã publish** (GitHub `openMSL/sl-1-2-reflection-based-lidar-object-model`,
MPL-2.0). Ticket 21 port **3 cơ chế** (kích hoạt 40 km/h, số cụm theo 50 km/h, lifetime T=0,2 s) — chi tiết +
số dòng code trong ticket. Đọc ticket trước khi sửa dòng nào.

## 3 điều dễ làm sai — đọc kỹ

1. `40/3.6` là ngưỡng **kích hoạt**, KHÔNG phải offset số cụm. Offset số cụm là **50 km/h**. Đừng đổi 50 → 40.
2. Ở `v ≤ 50 km/h` công thức cho **0 cụm**. Giữ đúng 0, không thêm sàn cho "đẹp".
3. Số cụm sinh ra sẽ **thấp hơn** 17,06 cụm/frame đo được trên spray thật. **Báo độ lệch, KHÔNG tự nâng** tham số.

## Không được làm

- Không sửa `mit/bevfusion`, `third_party/`, `spray/plume_transform.py`, `spray/model_routing.py`.
- Không đổi `cluster_radius_median_m = 0.30`, không đổi bảng 30/20/14/10/10 điểm/cụm (đó là số đo).
- Không port occlusion / drag / ray-sphere — chỉ ghi thành giới hạn trong docs.
- Không commit nếu pytest < 49 passed.

## Lệnh test

    CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/

Baseline: **49 passed**. Sau ticket: 49 + ≥4 test mới.

## Commit message (đúng dòng cuối ticket)

    fix(plume): port activation/count/lifetime from published Linnhoff reference code

## Báo lại

1. bảng 6 tốc độ 40/50/60/80/100/130 km/h: số cụm trước → sau
2. dòng so sánh với 17,06 cụm/frame (thiếu bao nhiêu lần)
3. 4 test mới tên gì, assert gì
4. tỉ lệ cụm sống đo được trên 2.000 mẫu (kỳ vọng ~0,245)