# ADR-0004: v2 mở lại wet-ground, attenuation và trạng thái theo thời gian

Status: Accepted (2026-11-10) · **thay thế ADR-0002**

## Context

ADR-0002 (2026-11-04) chốt: v1 chỉ có plume, không wet-ground, không attenuation, vì lúc đó
cả hai có tác động **đo được** nhỏ hơn ngưỡng nhiễu của phép đo, và vì A/B cần đúng một biến
thay đổi.

Sau khi audit generator v1 (`docs/history/plume-v1-defects.md`) và đo lại, ba lý do đó đổi:

| Cơ chế | Lúc ADR-0002 | Bây giờ |
|---|---|---|
| Wet-ground | "chỉ `set_intensity`, không xoá điểm ⇒ không đáng" | Nhưng nó quyết định **độ tương phản** giữa mặt đường và plume. Port được từ `dee.cpp:305–380` (MPL-2.0), không phải vendor CC BY-NC |
| Attenuation | "tia chỉ xuyên 0,5–0,8 m ⇒ còn 96,9–98 % độ sáng" | Đo trên frame thật: **631 điểm thật bị giảm intensity** mỗi frame. Đây chính là cơ chế "plume che xe", thứ cần cho câu hỏi nghiên cứu |
| Trạng thái / trôi / tan | "cần state qua frame; `4T ≈ 0,8 s` mà keyframe cách 0,5 s" | Đã có `PlumeState`; vệt đo được **73,4 m @130 km/h**. Không có state thì plume là một đám đứng yên — sai bản chất |

Lý do "một biến duy nhất" vẫn đúng, nhưng cách giữ nó khác: **wet-ground mặc định tắt**, bật
bằng config, nên arm A và arm B chỉ khác nhau ở plume.

## Decision

1. Port `simulate_wet_pavement` (Snell eq. 12–19, `×0,3`) vào `spray/wet_ground.py`; **chỉ**
   `set_intensity`, không xoá điểm; **mặc định tắt**.
2. Attenuation `e^(−2·0,02·L)` vào `spray/raycast.py`, áp lên cả điểm thật nằm sau plume.
3. Trạng thái cụm (`spawn` / `advance` / `prune`) vào `spray/plume_state.py`, advection hệ ground,
   `C = −0,15 m⁻¹`, xoá `age > 4T`.
4. `points_clean` **bất khả xâm phạm**: wet-ground và attenuation không được sửa nó.

## Consequences

- Repo tái lập được 4/5 cơ chế của paper; còn thiếu **occlusion** (`add_max_detection`) và
  self-spray của ego — ghi trong `docs/PROJECT.md` §5.2.
- A/B vẫn hợp lệ với điều kiện wet-ground tắt trong cả hai arm; bật nó là một thí nghiệm khác.
- Chi phí: mỗi frame thêm 2 marker (`PLUME_STATE`, `WET_GROUND_STATS`), và latency ray casting
  hiện **266–476 ms/frame** — phải hạ dưới 100 ms ở ticket 29c.
- ADR-0002 chuyển sang `Superseded`; không xoá, để giữ dấu vết lý do ban đầu.