Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự:
1. .scratch/spray-augmentation/STATUS.md
2. .scratch/spray-augmentation/issues/18-nuscenes-eligibility.md  ← đã viết lại, đọc kỹ mục
   "Bài học từ v1" và "Bỏ phụ thuộc cứng vào devkit"

## Nhiệm vụ lượt này

Sửa `kaggle/eligibility/main.py` theo đúng ticket 18 (bản mới), sửa `kaggle/eligibility/kernel-metadata.json`
(`id` → `nguynhuy9669/nuscenes-eligibility-scan`), rồi push MỘT lần và thoát.

Nội dung chính, tóm tắt (chi tiết trong ticket, ticket là nguồn đúng):
- Bỏ phụ thuộc cứng vào nuscenes-devkit. Hai đường: devkit (`pip install --no-deps`, KHÔNG để pip đổi
  numpy) hoặc fallback thuần Python (tự tính velocity theo công thức devkit, tải `splits.py` từ GitHub
  raw để lấy val scene names). Ghi `velocity_source` + `val_split_available` vào JSON và log.
- Script PHẢI chạy hết kể cả khi devkit không import được. Không được chết ở bước cài đặt.
- Tách split: báo riêng **toàn bộ keyframe / val / train**, kèm `n_scenes_total`, `n_samples_total`.
- Định nghĩa `d` phải có điều kiện **`x > 0`** (box phía trước), và in thêm hàng đối chứng `d_legacy`
  (khoảng cách tâm + `x>0`, toàn bộ keyframe) để so với 952 box / 697 frame của bảng cũ.
- 5 bảng theo đúng thứ tự trong ticket.

## Ràng buộc cứng

- KHÔNG sửa `spray/`, không đổi `PlumeConfig`, không đổi ngưỡng.
- KHÔNG sửa `kaggle/smoke_test/`.
- KHÔNG để `pip install` đổi numpy. Mọi lệnh pip phải có `--no-deps` hoặc gói thuần Python.
- KHÔNG chờ kernel, KHÔNG poller, KHÔNG process nền. Push xong là dừng.
- Nếu bạn thấy định nghĩa trong ticket mâu thuẫn: DỪNG, báo PM.
- Không gõ số nào chưa chạy. Không viết `docs/nuscenes-eligibility.md` ở lượt này.

## Test + commit

- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → phải vẫn **33 passed**.
- Commit: `fix(kaggle): devkit-free eligibility scan with split breakdown (ticket 18 v2)`

## Báo lại (5 dòng)

1. version kernel mới
2. `velocity_source` bạn kỳ vọng sẽ chạy (devkit hay fallback) và vì sao
3. danh sách bảng sẽ in
4. chỗ nào trong ticket bạn thấy còn mơ hồ
5. đã kiểm gì để tin script không chết ở bước cài đặt