Repo: /Users/huynguyen/projects/bevfusion-spray-pilot  (chỉ ĐỌC — không commit, không sửa file repo)

## Nhiệm vụ

Cập nhật **live artifact** của dự án ở địa chỉ:

  https://artifacts.commandcode.ai/hk7d56v2pqp5q76x

Đây là trang artifact bạn đã publish trước đó cho dự án này ("Spray plume cho BEVFusion"). Nội dung hiện
tại đã **cũ** — nó được tạo trước khi ticket 16/17/18 xong. Dùng cơ chế artifact của bạn để cập nhật
**đúng artifact đó** (cùng id/URL), không tạo artifact mới nếu không cần.

## Nguồn sự thật để đọc (theo thứ tự)

1. `.scratch/spray-augmentation/STATUS.md`
2. `docs/PROJECT.md`
3. `docs/plume-geometry-vs-real.md` (số đo ticket 16)
4. `docs/nuscenes-eligibility.md` (số ticket 18)
5. `docs/plume-model-provenance.md`
6. `git log --oneline -8` (5 commit mới: `08f6715`, `55c3cb2`, `5d7c478`, `af0ec1e`, `722dcf6`, `8b03d6a`)

## Nội dung phải phản ánh (đây là thay đổi so với bản cũ)

**Trạng thái:** 15, 16, 17, 18 **xong**. Test **35 passed**. Tiếp theo: **08 → 09 → 10 → 11 → 13**, `14`
chạy song song.

**Generator đã đổi (ticket 17, commit `5d7c478`)** — bản artifact cũ đang mô tả generator trước khi sửa:

| cũ (SAI) | mới (ĐÚNG) |
|---|---|
| số điểm/cụm cố định median **17** ở mọi cự ly | median **theo cự ly**: 30 / 20 / 14 / 10 / 10 cho `0–5 / 5–10 / 10–20 / 20–30 / >30 m` |
| điểm rải đều trong khối cầu | khối cầu rồi **bẹp theo phương tia ×0,885** → `r_range/r_extent` = **1,28** |
| "cảm biến chỉ thấy bề mặt cụm" là **điều biết là sai, chưa sửa** | đã **đo và bác bỏ**: cụm có bề dày theo tia (ratio 1,28 > 1); paper lấy range quanh **tâm** cụm |
| — | bán kính giữ **0,30 m** theo paper Fig. 5; đo được 0,755 m nhưng là **cận trên** do single-linkage chaining |

**Eval set đã chốt (ticket 18):** val split, box vehicle ≥50 km/h **phía trước** (`x>0`), `d ≤ 50 m`,
không lọc ego → **196 frame / 16 cảnh**.

**Giới hạn phải giữ nguyên trên artifact** (đừng làm mất, đây là phần trung thực):

- Chỉ chèn plume vào **nhánh LiDAR**, ảnh camera giữ sạch ⇒ cặp "ảnh sạch + point cloud bẩn" là **lý tưởng
  hoá**; kết quả dương là **cận trên** của lợi ích kỳ vọng trên xe thật, nơi cả hai modality cùng bẩn.
- Plume trong eval set A rơi vào **31–60 m**, ngoài vùng đo được của SemanticSpray (cụm dày >50 m: **0**)
  ⇒ là **ngoại xuy**, phải ghi rõ.
- Thiếu attenuation/occlusion (`ADR-0002`), thiếu `P_det` per-tia, thiếu cụm tan dần theo thời gian.
- Số nào không có file nguồn trong repo (thông số datasheet cảm biến, hồ sơ nuScenes, cách chấm NDS) thì
  **giữ callout `[?]` như bản sổ tay**, không bịa trích dẫn.

## Ràng buộc

- **Không sửa file nào trong repo.** Không commit, không `git add`. Đây là việc publish artifact.
- Nhãn nguồn cho số: `[ĐO]`, `[PAPER]`, `[CHỌN]` như các doc trong repo.
- Nếu gặp 404 / cần đăng nhập / không có quyền với artifact id này: **DỪNG** và báo nguyên văn lỗi + cần gì.
  Không được tạo artifact mới rồi báo "đã cập nhật" — phải đúng id `hk7d56v2pqp5q76x`.

## Báo lại (ngắn)

1. URL artifact sau khi cập nhật + thời điểm
2. Danh sách mục đã đổi (mục nào, đổi gì)
3. Sau khi publish, **fetch lại URL** và xác nhận trong nội dung có 2 chuỗi: `0,885` và `196 frame`
   (hoặc `196`). Nếu fetch không xem được vì cần đăng nhập, nói rõ là bạn xác nhận bằng cách nào.
4. Có mục nào bạn không dám khẳng định vì thiếu nguồn trong repo