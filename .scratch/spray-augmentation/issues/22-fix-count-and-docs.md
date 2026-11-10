# 22: Sửa lỗi tính hai lần (spawn × dropout) + hiệu chỉnh tài liệu theo số đọc từ code

**Bối cảnh:** ticket 21 (`a4fdf24`) port đúng công thức code openMSL, nhưng PM đo lại thì thấy
số cụm còn **quá ít**: công thức đã là *số cụm sinh ra mỗi chu kỳ 0,1 s*, rồi code còn dropout
theo lifetime một lần nữa → tính hai lần sự suy giảm.

## Việc 1 — bỏ dropout trên số cụm, dùng hệ số tích luỹ trạng thái dừng

Số đo PM chạy trên `a4fdf24` `[ĐO] 2026-11-07`:

| v_kmh | 40 | 50 | 60 | 80 | 100 | 130 |
|---|---:|---:|---:|---:|---:|---:|
| cụm sinh | 0 | 0 | 1 | 3 | 5 | 8 |
| còn sau dropout | 0 | 0 | 0,24 | **0,73** | 1,23 | 1,96 |
| đo thật (ticket 16) | — | — | — | **17,06** | — | — |

Sửa: số cụm **nhìn thấy trong một frame** = `round(spawn_per_cycle × K)`, với

```
K = Σ_{k=0}^{4T/Δt} exp(−k·Δt/T)   với Δt = 0,1 s, T = 0,2 s  →  K = 2,51
```

`[CODE]` Δt lấy từ `update_cycle_time` của profile, `T` từ `dee.cpp:530`; `K` là tổng cấp số nhân,
không phải tham số bịa. Bỏ hẳn bước dropout `age ~ U(0,4T)` khỏi `inject_plume` (nó chỉ dùng để
mô phỏng cụm già; ở trạng thái dừng sự suy giảm đã nằm trong `K`).

Kỳ vọng sau sửa: 80 km/h → **7,5** cụm; 130 km/h → **20,1**. Vẫn thấp hơn 17,06 ở mức trung bình
nhưng **cùng bậc**, và không còn frame rỗng. **Không** được tự nâng `wfh` hay hệ số nào để khớp
đúng 17,06 — chênh lệch còn lại là do `wfh` chưa biết, phải ghi vào docs.

## Việc 2 — script tái lập bảng mật độ

Thêm `scripts/plume_density_table.py` (không cần GPU, chỉ numpy): 3 box 12/22/38 m × seed 0–4,
in bảng `điểm trước → sau` + tổng, **in cạnh** bảng cũ trong docs để thấy chênh.
Test: script chạy được và tổng điểm sau ≥ trước (vì bỏ dropout thì thêm nhiều hơn).

Bảng cũ trong docs (`1.330 → 1.057`, `−21%`) sinh bằng công thức trước 21 → **phải đánh dấu
"bảng cũ, công thức trước ticket 21–22"** hoặc thay bằng bảng mới; không để hai bảng cùng nhãn.

## Việc 3 — sửa 3 câu sai trong docs (đã có số để thay)

1. `docs/history/plume-model-provenance.md` + `STATUS.md` đang ghi **"occlusion là chỗ làm kết quả
   lạc quan nhất"** → **sai**, thay bằng số đọc từ `dee.cpp:250–300` + `add_max_detection` (:781):
   - mỗi tia cắt cụm mới sinh điểm spray với xác suất `min(1, lognormal(−2,3; 1,1))`,
     median **0,10**, trung bình sau chặn **≈0,19**;
   - nếu sinh, điểm spray **vẫn phải thắng** theo `power = intensity / distance²` so với điểm thật
     đã suy giảm; spray intensity ≈ `0,5/255×100 = 0,196` ở 25 m → `3,1e−4`;
     điểm xe ở 40 m thắng khi `I_xe > 0,5` (thang 0–100) — xe thật **4–40**, nên **xe gần như
     không bao giờ bị che**;
   - ⇒ occlusion trong model tham chiếu là **thay thế các return yếu** (mặt đường, vật tối ở xa),
     không phải "xe biến mất". Xếp lại thứ tự nguồn lạc quan: **(1) camera branch sạch,
     (2) số cụm, (3) lifetime, (4) drag, (5) occlusion**.
2. Hệ số suy giảm: `exp(−2×0,02×d)` = **0,04 m⁻¹**, không phải 0,02. Ở `d = 0,5–0,8 m` còn
   **98,0–96,9%** (không phải 99–98,4%). Kết luận "bỏ attenuation" **không đổi**, chỉ sửa số.
3. σ phân bố bán kính cụm: **1,1** (profile), không phải 1,09. `T` không phải hằng 0,2 mà
   `wfh·0,02·(v−50)+0,2`.

## Nghiệm thu

- [x] `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → **≥55 passed** → thực tế
      **56 passed** (PM tự chạy tại `75d210c`, 2026-11-07)
- [x] in bảng mật độ mới + bảng cũ cạnh nhau → `scripts/plume_density_table.py`: cũ `1.330 → 1.057 (−21%)`,
      mới `5.000 → 7.335 (+47%)`, 120 cụm. **Caveat**: bảng mới chạy trên nền **1.000 điểm tổng hợp**
      (nuScenes không có local) ⇒ không trích `+47%` vào docs như số của frame thật
- [x] grep `"lạc quan nhất"` phải về **0**; grep `0,02 m⁻¹` phải về 0 (còn 0,04) → cả hai đều **0**
- [x] không đụng `mit/`, `third_party/`; `mit/bevfusion` vẫn `da93b27`; không đổi `PlumeConfig` ngoài `lifetime_*`
- [x] commit: `fix(plume): remove double lifetime penalty (steady-state cluster count); correct occlusion/attenuation docs`
      → `75d210c`, tree sạch

**PM nghiệm thu 2026-11-07 15:20.** Đo lại sau ticket: 60→3, 80→**8**, 100→13, 130→20 cụm/frame; còn thiếu
**2,1×** so với 17,06 đo thật (phần còn lại do `wfh` chưa biết — agent **không** tự nâng tham số, đúng yêu cầu).

<!-- END -->