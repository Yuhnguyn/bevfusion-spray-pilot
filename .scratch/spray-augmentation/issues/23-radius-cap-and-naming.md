# 23: Ba chỉnh nhỏ còn lại sau khi đối chiếu code Linnhoff

Không đổi hành vi sinh plume đáng kể. Mỗi mục kèm lý do + số.

## 1. Trần bán kính cụm: 1,50 m → **1,00 m**

- Code gốc: `radius = std::min(1.0f, lognormal(mu=-1.2, sigma=0.8))` — `dee.cpp:528`.
- Ta đang cắt ở `(0,10; 1,50)`; code cắt ở 1,0 ⇒ **6,7%** cụm lẽ ra > 1 m bị bóp về 1,0
  (`z = (ln 1,0 + 1,2)/0,8 = 1,5`, `Φ(1,5) = 93,3%`).
- Sửa: `cluster_radius_bounds_m = (0.10, 1.00)`. Thêm 1 test: 20.000 lần rút, `max(r) ≤ 1.0`
  và **tỉ lệ chạm trần ≈ 6–8%**.

## 2. Đổi tên cột 5: `time_lag` → `ring`

- nuScenes `.bin` là `load_dim = 5` ⇒ cột 5 = **ring index** (`docs/PROJECT.md:46` ghi đúng,
  `spray/plume.py:102` đặt tên sai là `time_lag`).
- Giá trị vẫn là `0.0` nhưng phải đổi tên field + comment: "điểm tổng hợp gán ring 0; không dùng
  cho occlusion". Không đổi số test.

## 3. Ghi 2 điều vào `docs/plume-model-provenance.md`

**(a) `K` là cận dưới nhẹ so với code gốc.** Code rút `T ~ N(T; 0,2)` (std bằng chính mean) ⇒
15,9% cụm có `T ≤ 0` (chết ngay chu kỳ đầu) nhưng đuôi `T` lớn sống lâu hơn tuyến tính, nên
`E[K] = 2,76` vs `K = 2,51` khi `T` cố định (**+10%**). Ta chọn `T` cố định vì tái lập được —
ghi rõ là sai lệch đã biết [CHỌN].

**(b) `water_film_height` tính bằng MÉT.** `T = wfh·0,02·(v−50)+0,2` với `wfh = 0,001 m`
⇒ số hạng tốc độ chỉ `0,0004 s` ⇒ `T ≈ 0,20 s` ở mọi tốc độ, `K ≈ 2,51` không đổi.
Nếu hiểu `wfh = 1 mm` là số 1,0 thì `T(130 km/h) = 0,84 s` và `K ≈ 9` — **sai 3,6×**. Phải ghi
đơn vị để người đọc không nhân sai.

## 4. Ghi 1 hạn chế mới phát hiện từ clip A

Trong spray **thật**, ngoài cụm sau xe dẫn đường (x ≈ 19–21 m) còn có cụm **ngay sau chính ego**
(x ≈ −4,5 m, y ≈ 0) — bụi nước do bánh xe ego hất lên. Generator chỉ sinh sau **xe phía trước**,
không có self-spray. Không ảnh hưởng eval set A (box phía trước, `x > 0`) nhưng phải ghi vào
danh sách hạn chế để không bị hỏi khó.

**PM nghiệm thu 2026-11-07 16:00 — ĐẠT.** commit `da996ff`, 3 file (+48/−3), tree sạch; pytest **57 passed**.
`cluster_radius_bounds_m = (0.10, 1.00)`; `grep -rn time_lag spray/` = rỗng; test mới
`test_cluster_radius_capped_at_one_meter` assert `max ≤ 1.0` và tỉ lệ chạm trần ∈ [0.05, 0.09].
Đo thật 20.000 lần rút (seed 0): **1303/20000 = 6,51%** — khớp 6,7% giải tích. Không tham số nào khác bị đổi.

**Nghiệm thu:** `cluster_radius_bounds_m` = `(0.10, 1.00)`, không còn chuỗi `time_lag` trong
`spray/`, pytest **≥57 passed**, docs có 2 mục (a)(b) + hạn chế self-spray.
Commit: `fix(plume): cap cluster radius at 1.0 m per dee.cpp:528; rename col5 to ring; document K/T`