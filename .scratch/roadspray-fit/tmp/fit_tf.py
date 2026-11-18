import shutil, zipfile
from pathlib import Path
import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore
TMP=Path(".scratch/roadspray-fit/tmp"); dest=TMP/"y.bag"
with zipfile.ZipFile("data/roadspray/Crafter_dynamic.zip") as zf:
    m="Crafter_dynamic/2021-09-08-16-06-27_0.bag"
    with zf.open(zf.getinfo(m)) as s, open(dest,"wb") as d: shutil.copyfileobj(s,d,1<<22)
ts=get_typestore(Stores.ROS1_NOETIC)
ref=np.fromfile("data/SemanticSprayDataset/Crafter_dynamic/0053_2021-09-08-16-06-27_0/velodyne/000000.bin",dtype=np.float32).reshape(-1,5)
with Reader(dest) as rd:
    vel=[c for c in rd.connections if c.topic=="/velodyne_points"]
    for conn,stamp,raw in rd.messages(vel):
        m2=ts.deserialize_ros1(raw,conn.msgtype)
        a=np.frombuffer(bytes(m2.data),dtype=np.uint8).reshape(-1,int(m2.point_step))
        bag=np.empty((a.shape[0],3),dtype=np.float64)
        bag[:,:]=np.ascontiguousarray(a[:,0:12]).view(np.float32).reshape(-1,3)
        break
dest.unlink(missing_ok=True)
A=np.c_[bag, np.ones(len(bag))]
sol,*_=np.linalg.lstsq(A, ref[:,:3].astype(np.float64), rcond=None)
pred=A@sol
res=np.abs(pred-ref[:,:3]).max()
print("fitted 3x4 affine (columns x,y,z,bias):")
np.set_printoptions(precision=5, suppress=True)
print(sol)
print("max residual over %d pts: %.6g m" % (len(bag), res))
# compare with meta_data_dataset.json extrinsics
R=sol[:3,:].T; t=sol[3]
print("\nfitted R:\n", R, "\nfitted t:", t)
import math
yaw=math.atan2(R[1,0],R[0,0]); pitch=math.asin(-R[2,0]); roll=math.atan2(R[2,1],R[2,2])
print("decomposed roll=%.4f pitch=%.4f yaw=%.4f (rad)" % (roll,pitch,yaw))
print("meta says roll=-0.017 pitch=-0.010 yaw=-1.587, t=(1.333,0.009,1.686)")
