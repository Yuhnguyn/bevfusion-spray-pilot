# Velocity contract (BEVFusion MIT, `da93b27`)

## Answer

Box velocity is stored in the **LiDAR frame**.

- The data converter reads `nusc.box_velocity(token)` (global) and rotates it into LiDAR:
  `velo @ inv(e2g_r_mat).T @ inv(l2e_r_mat).T`.
- The loader appends `gt_velocity` to the box tensor as dimensions 7:9.
- `GlobalRotScaleTrans` rotates dimensions 7:9 together with the box.
- `RandomFlip3D` flips velocity through the strided slices `[0::7]` and `[1::7]`, so flips stay consistent.

## ObjectPaste

The ground-truth database stores the full 9-dimension `box3d_lidar`, and `DataBaseSampler` concatenates those boxes into the current frame. Pasted boxes therefore carry the **source object's velocity**, translated to the new centre but not recomputed for the target scene.

Consequence: pasted-box velocity is usable as a direction hint, but it is not a measured target-scene velocity. Log it and do not treat it as ground truth.

## Fallback

If velocity is missing, non-finite, or the speed is below the threshold, skip the box and increment the skip counter. Do not place a plume from heading alone.

## Open check

Counts of eligible boxes with valid velocity on a real frame require the dataset gate (ticket 04).
