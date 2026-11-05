# MIT BEVFusion pin

- Source: `third_party/bevfusion` (read-only reference clone).
- Working copy: `mit/bevfusion`.
- Commit: `da93b27` ("[Major] Code release.", 2022-06-03).
- Not using HEAD `326653d`: at HEAD, `BaseDepthTransform` defaults `add_depth_features=True` and `height_expand=True`, which feed a 6-channel depth tensor into a transform whose `dtransform` starts with `Conv2d(1, 8, 1)`.
- The release commit has neither flag and uses a 1-channel depth input.
- Version check: `git -C mit/bevfusion rev-parse --short HEAD` must print `da93b27`.

## Official fused detection checkpoint

- Primary URL (named in ticket 02): `https://bevfusion.mit.edu/files/pretrained/bevfusion-det.pth`
  returns **HTTP 404**; it redirects to
  `https://hanlab.mit.edu/projects/bevfusion/files/pretrained/bevfusion-det.pth`, which is also 404.
- Working mirror (the link the upstream BEVFusion README lists today, Dropbox):
  `https://www.dropbox.com/scl/fi/ulaz9z4wdwtypjhx7xdi3/bevfusion-det.pth?rlkey=ovusfi2rchjub5oafogou255v&dl=1`
- Size: `163715701` bytes.
- `sha256`: `ee0a389213922343508db40dff0ec04767b36d8f512da34b093939c37aaf2122`.
- Format: torch archive (magic `504b0304`).
- Source of these values: the Kaggle smoke-test run on 2026-11-05 (ticket 02). Final run:
  checkpoint loaded into the model with **582/582 keys matched, 0 missing, 0 unexpected,
  0 shape mismatches**; forward succeeded and all outputs were finite.
