Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. docs/knowledge-base.html  ← file bạn cần sửa ("Sổ tay dự án — Spray plume cho BEVFusion")
2. docs/PROJECT.md           ← trạng thái mới nhất của dự án
3. docs/measurements/plume-geometry-vs-real.md  ← số đo hình học plume thật (ticket 16)
4. docs/reference/nuscenes-eligibility.md    ← số frame/scene dùng được để eval (ticket 18)
5. spray/plume.py            ← generator SAU khi ticket 17 sửa xong (đọc code, không đoán)
6. .scratch/spray-augmentation/STATUS.md

## Nhiệm vụ

Cập nhật `docs/knowledge-base.html` cho khớp thực tế hôm nay. Giữ nguyên: tên file, văn phong tiếng Việt
giản dị cho người không chuyên, cấu trúc 10 mục hiện có, và tính chất **một file HTML tự chứa**
(không phụ thuộc file ngoài, không CDN nếu đang không có).

## Hai chỗ đang SAI, bắt buộc phải sửa

1. Mục "Những chỗ ta biết là chưa đúng", ý 1, đang viết:
   *"Cảm biến thật chỉ thấy bề mặt hướng về nó — không nhìn xuyên qua đám nước. Hiện tại điểm được rải
   khắp thể tích."*
   → **Sai, đã đo**: `r_range/r_extent = 1,28` (median, n=11.607) nghĩa là cụm **có bề dày theo phương
   bán kính**, không phải vỏ mỏng. Paper cũng lấy range của mỗi detection theo phân bố chuẩn quanh **tâm**
   cụm, không phải trên bề mặt. Generator nay **bẹp 0,64** theo phương bán kính để ra tỉ lệ đó.

2. Mục đó, ý 2, đang viết: *"...Cần đo trước khi sửa."*
   → **Đã đo xong và đã sửa**: median điểm/cụm giảm **3,0×** từ 0–5 m xuống 20–30 m (30 → 10), và
   generator nay lấy số điểm theo cự ly.

## Việc phải làm

- Đọc lại **toàn bộ** sổ tay, đối chiếu từng con số với các file ở trên. Con số nào lệch → sửa theo file
  nguồn. Con số nào **không tìm được nguồn trong repo** → ghi `[?]` và liệt kê trong báo cáo, **không bịa**.
- Cập nhật mục "Đang ở đâu" theo `STATUS.md` (16, 18, 15 đã xong; 17 vừa xong; tiếp theo 08 → 09 → 10 → 11).
- Thêm vào mục "Con số nào đáng tin" (hoặc mục phù hợp) 3 số mới, kèm nhãn nguồn:
  - trần của val để eval: **196 frame / 16 scene** (val, box ≥50 km/h phía trước, d ≤ 50 m, không lọc ego)
    `[ĐO: docs/reference/nuscenes-eligibility.md]`
  - hình học cụm thật: `r_range/r_extent` = **1,28**, median điểm/cụm = **17,0**, giảm **3,0×** theo cự ly
    `[ĐO: docs/measurements/plume-geometry-vs-real.md]`
  - 850 scene / 34.149 keyframe (trainval), val = 150 / 6.019 `[ĐO: docs/reference/nuscenes-eligibility.md]`
- Nếu văn phong chỗ nào còn nói "sẽ sửa"/"chưa đo" mà thực tế đã xong: chuyển sang thì quá khứ + số.

## Ràng buộc

- Chỉ sửa `docs/knowledge-base.html`. Không sửa file nào khác.
- Không bịa số. Không thêm số liệu không có trong repo.
- Không đổi cấu trúc 10 mục, không đổi tên file.
- Nếu phát hiện mâu thuẫn giữa các file nguồn: **DỪNG**, báo PM, đừng tự chọn.

## Test + commit

- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → phải đúng **35 passed**.
- Commit: `docs(kb): refresh handbook with measured plume geometry and eval-set numbers`

## Lưu ý về tiến độ

`docs/PROJECT.md` **đã được PM cập nhật** sau ticket 17 (bảng §4 dòng e/g + đoạn "Đã sửa ở ticket 16–17").
Đọc lại file đó, đừng dựa vào ký ức. Generator hiện tại: count theo cự ly 30/20/14/10/10, bẹp theo tia
×0,885, bán kính vẫn 0,30.

## Báo lại (ngắn)

1. những chỗ đã sửa (mục nào, đổi gì)
2. danh sách `[?]` — số nào không tìm được nguồn
3. câu nào bạn thấy mâu thuẫn giữa các file nguồn