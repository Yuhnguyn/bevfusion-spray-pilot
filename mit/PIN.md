# MIT BEVFusion pin

- Source: `third_party/bevfusion` (read-only reference clone).
- Working copy: `mit/bevfusion`.
- Commit: `da93b27` ("[Major] Code release.", 2022-06-03).
- Not using HEAD `326653d`: at HEAD, `BaseDepthTransform` defaults `add_depth_features=True` and `height_expand=True`, which feed a 6-channel depth tensor into a transform whose `dtransform` starts with `Conv2d(1, 8, 1)`.
- The release commit has neither flag and uses a 1-channel depth input.
- Version check: `git -C mit/bevfusion rev-parse --short HEAD` must print `da93b27`.
