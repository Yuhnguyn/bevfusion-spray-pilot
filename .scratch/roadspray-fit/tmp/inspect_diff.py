import shutil, sys, zipfile
from pathlib import Path
import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore
TMP=Path(".scratch/roadspray-fit/tmp"); dest=TMP/"x.bag"
with zipfile.ZipFile("data/roadspray/Crafter_dynamic.zip") as zf:
    m="Crafter_dynamic/2021-09-08-16-06-27_0.bag"
    with zf.open(zf.getinfo(m)) as s, open(dest,"wb") as d: shutil.copyfileobj(s,d,1<<22)
ts=get_typestore(Stores.ROS1_NOETIC)
root=Path("data/SemanticSprayDataset/Crafter_dynamic/0053_2021-09-08-16-06-27_0/velodyne")
with Reader(dest) as rd:
    vel=[c for c in rd.connections if c.topic=="/velodyne_points"]
    for i,(conn,stamp,raw) in enumerate(rd.messages(vel)):
        m2=ts.deserialize_ros1(raw,conn.msgtype)
        a=np.frombuffer(bytes(m2.data),dtype=np.uint8).reshape(-1,int(m2.point_step))
        bag=np.empty((a.shape[0],5),dtype=np.float32)
        bag[:,0:3]=np.ascontiguousarray(a[:,0:12]).view(np.float32).reshape(-1,3)
        bag[:,3]=np.ascontiguousarray(a[:,16:20]).view(np.float32).ravel()
        bag[:,4]=np.ascontiguousarray(a[:,20:22]).view(np.uint16).ravel()
        if i>0: continue
        ref=np.fromfile(root/"000000.bin",dtype=np.float32).reshape(-1,5)
        print("bag rows",bag.shape,"ssp rows",ref.shape,"point_step",int(m2.point_step))
        for c,name in enumerate(["x","y","z","intensity","ring"]):
            print(" %-9s bag[min,max,mean]=%9.3f %9.3f %9.3f | ssp=%9.3f %9.3f %9.3f | maxabsdiff=%9.4f"%(
                name,bag[:,c].min(),bag[:,c].max(),bag[:,c].mean(),ref[:,c].min(),ref[:,c].max(),ref[:,c].mean(),np.abs(bag[:,c]-ref[:,c]).max()))
        print(" first rows bag:", bag[:3])
        print(" first rows ssp:", ref[:3])
        print(" sums: bag xyz=%s ssp xyz=%s" % (bag[:,:3].sum(0).round(2), ref[:,:3].sum(0).round(2)))
        # is ssp a normalized/centered version? check row-wise equality of sorted by intensity
        o1=np.lexsort((bag[:,3],)); o2=np.lexsort((ref[:,3],))
        print(" sorted-by-intensity maxdiff xyz:", np.abs(bag[o1,:3]-ref[o2,:3]).max())
        print(" z diff unique:", np.unique(np.round(bag[:,2]-ref[:,2],3))[:8])
        print(" x diff unique:", np.unique(np.round(bag[:,0]-ref[:,0],3))[:8])
        break
dest.unlink(missing_ok=True)
