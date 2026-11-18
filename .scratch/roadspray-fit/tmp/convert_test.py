"""Measure real conversion cost: bag -> SSPP-style 5x float32 .bin per frame."""
import shutil, sys, time, zipfile
from pathlib import Path
import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore
TMP = Path(".scratch/roadspray-fit/tmp"); OUT = TMP / "conv_out"; OUT.mkdir(exist_ok=True)
zip_path, member = sys.argv[1], sys.argv[2]
t0=time.time()
dest = TMP / Path(member).name
with zipfile.ZipFile(zip_path) as zf:
    info = zf.getinfo(member)
    with zf.open(info) as s, open(dest,"wb") as d: shutil.copyfileobj(s,d,1<<22)
t_ext=time.time()-t0
ts=get_typestore(Stores.ROS1_NOETIC)
t1=time.time(); n=0; npts=0; nbytes=0
with Reader(dest) as rd:
    vel=[c for c in rd.connections if c.topic=="/velodyne_points"]
    for conn, stamp, raw in rd.messages(vel):
        m=ts.deserialize_ros1(raw, conn.msgtype)
        a=np.frombuffer(bytes(m.data), dtype=np.uint8).reshape(-1, int(m.point_step))
        pts=np.empty((a.shape[0],5), dtype=np.float32)
        pts[:,0:3]=np.ascontiguousarray(a[:,0:12]).view(np.float32).reshape(-1,3)
        pts[:,3]=np.ascontiguousarray(a[:,16:20]).view(np.float32).ravel()
        pts[:,4]=np.ascontiguousarray(a[:,20:22]).view(np.uint16).ravel()
        pts.astype(np.float32).tofile(OUT/f"{n:06d}.bin")
        n+=1; npts+=pts.shape[0]; nbytes+=pts.nbytes
t_conv=time.time()-t1
dest.unlink(missing_ok=True)
shutil.rmtree(OUT)
print(f"extract={t_ext:.2f}s convert={t_conv:.2f}s frames={n} pts={npts} out={nbytes/1e6:.1f}MB")
print(f"per_frame={t_conv/n*1000:.1f} ms  throughput={n/t_conv:.2f} frames/s  {npts/1e6/t_conv:.2f} Mpts/s")
print(f"bytes_per_frame(raw32B)={npts/n*32:.0f}  converted20B={npts/n*20:.0f}  avg_pts={npts/n:.0f}")
