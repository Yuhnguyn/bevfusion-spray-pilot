# ADR-0007: Những gì trong tài liệu là LỖI THỜI — bảng tra một chỗ

Status: Accepted (2026-11-20). Bổ sung, **không** thay ADR-0006.

## Context

Qua 4 phiên làm việc, nhiều quyết định đã bị đảo nhưng tài liệu cũ vẫn còn trên đĩa và vẫn
được đọc như hiện hành. Đo được ngày 2026-11-20:

- **10/36 file doc** còn ghi ít nhất một quyết định đã bị đảo, **không** có dòng đánh dấu.
- Bốn cơ chế đã bị đảo hoàn toàn: `prune` cắt cứng `4T` → tan xác suất; khối đuôi
  `0,05–0,92 × cao box` → slab `|v|·Δt`; `clamp ngang 2,43 m` → bỏ; `streak` → tắt.
- Một nguồn calibration đã bị thay hoàn toàn: bảng SSPP `cal` → RoadSpray `*_static` (D2).
- Một tài liệu chẩn đoán xếp `wet_ground` là "biến gây nhiễu lớn nhất chưa tách", trong khi
  đo lại cho thấy nó là **no-op** trên đường ống production.

Hệ quả thực tế: câu trả lời cho "cơ chế hoạt động thế nào" phụ thuộc phiên đọc file nào trước.

## Decision

**1. Nguồn sự thật duy nhất về hành vi hiện tại là CODE.** Tài liệu chỉ giải thích *vì sao*.
Khi tài liệu và code lệch nhau, code đúng, và tài liệu phải được sửa.

**2. Mỗi tài liệu còn quyết định đã đảo phải mang khối cảnh báo ở dòng đầu tiên**, đúng định dạng:

```
> ⚠️ **LỖI THỜI một phần** — xem `docs/adr/0007-superseded-claims.md` mục <số>.
> Phần còn đúng: <mô tả ngắn>.
```

Không được xoá tài liệu, vì mỗi file là bản ghi số đo tại thời điểm đo — xoá là mất dấu vết
của một kết luận đã từng được dùng để ra quyết định.

**3. Bảng tra chốt (dưới đây) là nơi duy nhất được liệt kê các cặp "đã đảo".** Không thêm
cặp mới ở nơi khác; sửa bảng này.

## Bảng tra — 6 cơ chế đã bị đảo

### (S1) `prune` — cắt cứng `4T` → tan theo xác suất

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/generator-reading-map.md` §6, `docs/measurements/plume-root-cause.md`, `docs/measurements/plume-a3-diagnosis.md`, `docs/reference/openmsl-sl-1-2-deep-dive.md`, `docs/reference/paper-qa-notebooklm.md` |
| Code hiện tại | `spray/plume_state.py:645-685` — `P_sống = exp(−dt/T)` mỗi chu kỳ, trần số học `12·T` |
| Quyết định | QĐ12 (2026-11-19), `[PAPER]` Eq. 1 |
| Vì sao đảo | Cắt cứng `4T` làm hệ số tích luỹ sai **4 lần** so với paper |

### (S2) Khối sinh — `0,05–0,92 × cao box` → slab `|v|·Δt × 3,4 × 1,5 m`

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/generator-reading-map.md` §4, `docs/measurements/a3-parameter-provenance.md`, `docs/measurements/plume-a3-diagnosis.md`, `docs/measurements/semantic-spray-cal-vs-heldout.md` |
| Code hiện tại | `spray/plume.py:592-655` — dài `|v|·dt`, rộng 3,4 m, cao 1,5 m tính từ `road_z` |
| Quyết định | QĐ11 (2026-11-19), `[CODE]` `define_spray_volumes()` |
| Vì sao đảo | QĐ7 gộp nhầm **vùng sinh** với **vùng đo 20 m** của calibration |

### (S3) `clamp ngang 2,43 m` — bỏ hẳn

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/measurements/a3-parameter-provenance.md`, `docs/measurements/sspp-cluster-table-folds.md`, `docs/measurements/sspp-point-range-distribution.md` |
| Code hiện tại | `spray/plume_state.py:618-620` — comment ghi rõ "BỎ clamp ngang", không còn code |
| Quyết định | QĐ7 (2026-11-19), audit R2 đánh **PHẢI BỎ** |
| Vì sao đảo | Nguồn số là SSPP `cal` (bị leak); vùng sinh đã bị giới hạn bởi slab nên không cần clamp riêng |

### (S4) `streak` — tắt (`streak_scale = 0.0`)

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/measurements/plume-a3-diagnosis.md` (10 chỗ), `docs/measurements/a3-parameter-provenance.md`, `HANDOFF.md`, `docs/measurements/following-scenario-density.md` |
| Code hiện tại | `spray/plume_state.py:210-217` — `streak_scale: float = 0.0`, kèm comment QĐ |
| Quyết định | Audit R2 (2026-11-19) — `streak` **không có** trong paper |
| Vì sao đảo | Ở 130 km/h nó làm `max` điểm/cụm ~3.500 trong khi static chỉ p95 36–181 |

### (S5) Nguồn calibration — bảng SSPP `cal` → RoadSpray `*_static`

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/generator-reading-map.md`, `docs/measurements/semantic-spray-cal-vs-heldout.md`, `docs/measurements/sspp-cluster-table-folds.md`, `docs/measurements/a3-parameter-provenance.md`, `docs/measurements/pdet-vs-range.md`, `docs/reference/roadspray-fit-for-repo.md`, `docs/reference/paper-qa-notebooklm.md`, `docs/measurements/semantic-spray-stats.md`, `docs/measurements/rootcause-recall-mechanism.md` |
| Code hiện tại | `spray/plume.py:23-60` — `_CLUSTER_VISIBLE_BY_SPEED` dựng từ `a3_targets_static.json`, Δ=1,0 m |
| Quyết định | ADR-0006 **D2** (2026-11-18) |
| Vì sao đảo | `cal` chứa 6/12 scene test ⇒ tham số fit một phần trên chính dữ liệu báo kết quả |

### (S6) Trần bán kính cụm `RADIUS_MAX_M = 2,0 m` — bỏ hẳn (`inf`)

| | |
|---|---|
| Tài liệu còn nói cũ | `docs/measurements/a3-parameter-provenance.md` §1 (dòng `RADIUS_MAX_M`), `docs/measurements/plume-a3-diagnosis.md` §“clip 2,0 m giữ nguyên” |
| Code hiện tại | `spray/plume_state.py:84` — `RADIUS_MAX_M = float("inf")`, kèm comment `[PAPER]` |
| Quyết định | Ticket 02b (2026-11-27), `[PAPER]` §III-B: không đặt trần cho `r_cl` |
| Vì sao đảo | Paper không có trần; comment biện minh cũ ghi "cắt ~0,1 % đuôi" trong khi thực tế với σ=0,72 là `P(r>2,0) = 0,43 %` |

**Lưu ý về (S5):** bảng SSPP `cal` vẫn còn **một** vai trò hợp lệ — kiểm chứng chéo
(`docs/measurements/sspp-cluster-table-folds.md`, r = 0,77 với bảng static). Nó không còn là
nguồn *chọn* tham số.

## Sửa một kết luận sai cụ thể

`docs/measurements/rootcause-recall-mechanism.md` §5 xếp `wet_ground` là "biến gây nhiễu **lớn
nhất**, chưa tách được". **Sai.** Đo lại ngày 2026-11-20:

- `inject_plume_stateful` trả `points_clean` = input **y nguyên** (`spray/plume.py:730`);
- `raycast_frame` chạy trên `result.points_clean` (`spray/plume_transform.py:130`), không trên
  `base` — mà `base` mới là biến đã bị wet-ground sửa;
- Hệ quả đo được: bật/tắt `wet_ground`, output transform **giống từng byte**, `det` 221 = 221;
- Kernel A7-b (`--no-wet-ground`) ra file jsonl có **md5 trùng khít** bản v5
  (`18d02243961f1e2c2915692e5520c1f0`, 2.862/2.862 dòng), chỉ nhanh hơn 273 s.

Kết luận đúng: `wet_ground` là **dead branch**, không phải "biến chưa tách". Đừng đổ lỗi cho nó
và đừng "sửa" tham số của nó để cải thiện eval.

Điều này **không** đổi kết quả cổng C: Δrecall = −0,2188 vẫn đứng, vì biến đó chưa từng tác động.

## Cấm

1. Đọc một file trong danh sách trên rồi phát biểu về hành vi generator mà **không** đối chiếu code.
2. Sửa bảng tra này bằng cách thêm mục ở nơi khác — mọi cặp "đã đảo" chỉ sống ở đây.
3. Xoá một file doc vì nó "lỗi thời". Nó là bản ghi số đo, không phải bản mô tả code.
