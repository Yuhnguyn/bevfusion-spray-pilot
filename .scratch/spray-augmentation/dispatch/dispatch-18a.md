Repo: /Users/huynguyen/projects/bevfusion-spray-pilot

Đọc theo thứ tự, chưa cần đọc gì khác:
1. .scratch/spray-augmentation/STATUS.md — mục "Thứ tự hiện tại"
2. .scratch/spray-augmentation/issues/18-nuscenes-eligibility.md
3. kaggle/smoke_test/kernel-metadata.json — để copy đúng format metadata + dataset ref

## Nhiệm vụ LƯỢT NÀY — chỉ phase 1

Dựng kernel mới `kaggle/eligibility/` gồm hai file:

- `kernel-metadata.json`: id `nguynhuy9669/bevfusion-eligibility`, title "nuScenes eligibility scan",
  `code_file: main.py`, `kernel_type: script`, `language: python`, `is_private: true`,
  `enable_gpu: false`, `enable_internet: true`, `dataset_sources` giữ đúng dataset nuScenes
  như kernel cũ.
- `main.py`: `pip install nuscenes-devkit`, load devkit, tính đúng 4 bảng trong ticket 18, in từng
  bảng ra stdout NGAY khi tính xong (mỗi bảng bọc try/except riêng), ghi `/kaggle/working/eligibility.json`,
  và in `TICKET18_OK` ở dòng cuối.

Rồi push đúng MỘT lần: `kaggle kernels push -p kaggle/eligibility`. In ra version mới + ref. Thoát.

### Ba chi tiết dễ sai, phải xử lý trước khi push

1. **Đường dẫn dataset**: ở đầu script in `os.listdir('/kaggle/input')` và tự dò root bằng cách tìm
   thư mục cha của `*/sample_annotation.json` (hoặc `*/*/sample_annotation.json`) thay vì hardcode
   một đường dẫn đoán mò. Nếu không tìm thấy, in rõ đã tìm ở đâu rồi raise.
2. **Chỉ val split**, và chỉ keyframe: dùng `nusc.sample` (không phải `sample_data`) để lấy 1 mẫu/frame.
3. **`v_ego`**: lấy `ego_pose` của keyframe hiện tại và keyframe trước **trong cùng scene**, dt = 0.5 s.
   Keyframe đầu của scene → NaN, và các hàng có lọc ego phải loại nó ra.

Định nghĩa `d`, `v_box`, tập class, chia split: theo đúng mục "Định nghĩa phải dùng đúng" của ticket 18.
Không tự đặt biến thể khác.

## Không làm ở lượt này

- KHÔNG viết `docs/nuscenes-eligibility.md`. Bảng phải lấy từ output thật của kernel.
  Không được gõ một con số nào chưa chạy.
- KHÔNG chờ kernel. KHÔNG `kaggle kernels status` trong vòng lặp. KHÔNG process nền. KHÔNG poller.
  Push xong là dừng, báo lại, thoát. PM tự poll.
- Không sửa `kaggle/smoke_test/` — kernel đó đang là bằng chứng cho ticket 04/06/07.
- Không sửa `spray/`, không đổi `PlumeConfig`, không đổi ngưỡng nào trong code.
- Không cài gì local, không tải nuScenes về máy.

## Ràng buộc cứng

- Nếu bạn cho rằng định nghĩa trong ticket sai, hoặc phải đổi tham số: **DỪNG**, báo PM kèm lý do.
  Đó là quyết định của PM, không phải của bạn.
- Chỉ push MỘT lần (quota). Trước khi push, đọc lại `main.py` một lượt để bắt lỗi cú pháp và lỗi
  đường dẫn. Ở máy local KHÔNG chạy được script (không có nuScenes) — nên chỉ commit code, không
  tự "chạy thử rồi báo pass".

## Test + commit

- `CONDA_NO_PLUGINS=true /opt/anaconda3/bin/python -m pytest -q tests/` → phải vẫn **33 passed**.
- Commit: `feat(kaggle): add CPU eligibility kernel for nuScenes scan (ticket 18 phase 1)`

## Báo lại (ngắn, 4 dòng)

1. version kernel mới + ref
2. `main.py` in ra những bảng nào, theo thứ tự
3. đường dẫn dataset bạn giả định, và bạn đã làm gì để kiểm nó
4. chỗ nào trong ticket 18 bạn thấy mơ hồ