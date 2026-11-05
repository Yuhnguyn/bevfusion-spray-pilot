# ADR-0001: Pin MIT BEVFusion at commit `da93b27`

Status: Accepted (2026-01)

## Context

`third_party/bevfusion` là clone reference; working copy ở `mit/bevfusion`. Repo MIT ở HEAD có
hai flag mới trong `BaseDepthTransform`: `add_depth_features=True` và `height_expand=True`. Với hai
flag này, tensor depth vào camera branch có 6 channel, trong khi `dtransform` mở đầu bằng
`Conv2d(1, 8, 1)` — sai shape so với checkpoint fused chính thức.

## Decision

Dùng commit release `da93b27` ("[Major] Code release.", 2022-06-03) cho mọi thí nghiệm.
Không dùng HEAD `326653d`. Kiểm tra bằng `git -C mit/bevfusion rev-parse --short HEAD`.

## Consequences

- Checkpoint fused load được mà không phải sửa code hay shape.
- Không có các tính năng depth mới của HEAD; chấp nhận được vì chúng không thuộc câu hỏi nghiên cứu.
- Mọi config snapshot và report phải ghi commit này; nếu ai đó build từ HEAD thì kết quả không so sánh được.
- Nếu buộc phải lên HEAD: set `add_depth_features: false` và `height_expand: false`, rồi chạy lại smoke test trước khi dùng.