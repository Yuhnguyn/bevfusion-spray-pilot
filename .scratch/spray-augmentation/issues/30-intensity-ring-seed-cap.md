# 30: Intensity, ring, seed theo epoch, cap

**Type:** task
**Status:** needs-triage
**Blocked by:** 29
**Chủ:** CommandCode. PM: Hermes.

## Căn cứ đo

`[ĐO]` trên spray thật: intensity **82,65 % = 0**, 14,34 % = 1, p90 = 1, p99 = 3, max 53.
`ring` phủ **0–31**, median **4** ring/frame, 31,9 % rơi ring 0. `use_dim: 5` ⇒ ring là **kênh vào model**
(`mit/bevfusion/configs/nuscenes/default.yaml:6`). v1 gán `ring = 0,0` và `intensity` hằng cho
**toàn bộ** điểm sinh (`spray/plume.py:104, 265`), seed cố định ⇒ plume giống hệt mọi epoch.

## Việc phải làm

1. `intensity`: lấy từ `N(0,5)/255·100` như `[CODE]` (không tự đặt phân bố mới), rồi so phân bố
   sinh ra với số đo trên; nếu khác quá 1 bậc thì ghi rõ trong doc, **không** chỉnh số đo.
2. `ring`: gán theo elevation của beam đã sinh ra điểm (ring = chỉ số elevation gần nhất).
3. Seed: `seed = blake2b(f"{scene_token}:{epoch}")` — đổi theo epoch, tái lập được.
4. Cap: `min(2000, 40·số_cụm)` hoặc bỏ cap cứng; log `capped` (v1: 16 xe @80 km/h = 2.340 điểm → cắt 14,2 % `[ĐO]`).
5. `tests/test_plume_fields.py` — ring ∈ [0,31]; seed khác epoch → điểm khác; cùng epoch → giống hệt.

## Tiêu chí nghiệm thu

- [ ] `pytest -q tests/` không giảm.
- [ ] Marker `PLUME_FIELDS intensity_p50=<n> ring_median=<n> capped=<n>`.
- [ ] `ring` không còn là hằng số: `len(np.unique(ring)) > 3` trên 20 frame.
- [ ] Hai epoch khác nhau → `hash(points) ` khác nhau; cùng epoch → giống hệt (byte-equal).

## Cấm

- Không "sửa" số đo intensity thật cho khớp simulator.
- Không tăng cap để né cắt.
