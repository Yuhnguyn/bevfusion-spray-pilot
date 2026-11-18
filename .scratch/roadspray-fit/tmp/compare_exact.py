"""Exact per-point comparison: bag PointCloud2 -> 5x f32 vs SSPP .bin, all frames."""
import shutil, sys, zipfile
from pathlib import Path
import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore
TMP=Path(".scratch/roadspray-fit/tmp")
zip_path, member, scene = sys.argv[1], sys.argv[2], sys.argv[3]
dest=TMP/Path(member).name
with zipfile.ZipFile(zip_path) as zf:
    with zf.open(zf.getinfo(member)) as s, open(dest,"wb") as d: shutil.copyfileobj(s,d,1<<22)
ts=get_typestore(Stores.ROS1_NOETIC); root=Path("data/SemanticSprayDataset")/scene
files=sorted((root/"velodyne").glob("*.bin"))
n=0; ok_frame=0; ok_int=0; ok_ring=0; maxd=0.0
with Reader(dest) as rd:
    vel=[c for c in rd.connections if c.topic=="/velodyne_points"]
    for conn, stamp, raw in rd.messages(vel):
        if n>=len(files): break
        m=ts.deserialize_ros1(raw, conn.msgtype)
        a=np.frombuffer(bytes(m.data),dtype=np.uint8).reshape(-1,int(m.point_step))
        pts=np.empty((a.shape[0],5),dtype=np.float32)
        pts[:,0:3]=np.ascontiguousarray(a[:,0:12]).view(np.float32).reshape(-1,3)
        pts[:,3]=np.ascontiguousarray(a[:,16:20]).view(np.float32).ravel()
        pts[:,4]=np.ascontiguousarray(a[:,20:22]).view(np.uint16).ravel()
        ref=np.fromfile(files[n],dtype=np.float32).reshape(-1,5)
        if pts.shape==ref.shape:
            ok_frame+=1
            d=np.abs(pts[:,:4]-ref[:,:4]).max(); maxd=max(maxd,float(d))
            if np.array_equal(pts[:,3],ref[:,3]): ok_int+=1
            if np.array_equal(pts[:,4],ref[:,4]): ok_ring+=1
        n+=1
dest.unlink(missing_ok=True)
print(f"frames compared={n}/{len(files)} same_shape={ok_frame} identical_intensity_col={ok_int} identical_ring_col={ok_ring} max_abs_diff_xyzi={maxd:.6g}")
print(f"-> point values (x,y,z,intensity) {'EXACT' if maxd==0 else 'DIFFER'}; intensity stored raw ({'no' if maxd else 'no'} scaling applied)")
