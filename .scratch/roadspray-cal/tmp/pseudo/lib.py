"""Shared helpers for the pseudo-box study (read-only on data/)."""
import sys, json, csv, glob, os
from pathlib import Path
import numpy as np
REPO=Path('/Users/huynguyen/projects/bevfusion-spray-pilot')
sys.path.insert(0,str(REPO))
from spray.sspp_adapter import read_frame_boxes, read_metadata
from proxy_eval.matcher import bev_corners

ROOT=REPO/'data'/'SemanticSprayDataset'
GROUPS=('Crafter_dynamic','Golf_dynamic')

def load_points(scene_dir, scan_id):
    p=np.fromfile(Path(scene_dir)/'velodyne'/f'{scan_id}.bin',dtype=np.float32).reshape(-1,5)
    return p

def load_labels(scene_dir, scan_id):
    return np.fromfile(Path(scene_dir)/'labels'/f'{scan_id}.label',dtype=np.uint32).reshape(-1)

def to_box_frame(pts, box):
    """pts (N,>=2) -> local (u along heading, v lateral) using yaw of box; centre at (x,y)."""
    c,s=np.cos(box['yaw']),np.sin(box['yaw'])
    dx=pts[:,0]-box['x']; dy=pts[:,1]-box['y']
    u= c*dx + s*dy
    v=-s*dx + c*dy
    return u,v

def bev_iou(a,b):
    """a,b = dict(x,y,yaw,size_x,size_y). Reuses repo polygon clipping (layout x-extent first)."""
    ba=np.array([a['x'],a['y'],0.0,a['size_x'],a['size_y'],1.0,a['yaw']])
    bb=np.array([b['x'],b['y'],0.0,b['size_x'],b['size_y'],1.0,b['yaw']])
    from proxy_eval.matcher import _clip_polygon, _polygon_area
    pa,pb=bev_corners(ba),bev_corners(bb)
    inter=_clip_polygon(pa,pb)
    ia=_polygon_area(inter)
    if ia<=0: return 0.0
    ua=_polygon_area(pa)+_polygon_area(pb)-ia
    return float(ia/ua)

def iou_3d(a,b):
    """Exact for two extruded boxes: BEV inter area * z overlap / (Va+Vb-Vinter)."""
    from proxy_eval.matcher import _clip_polygon, _polygon_area
    ba=np.array([a['x'],a['y'],0.0,a['size_x'],a['size_y'],1.0,a['yaw']])
    bb=np.array([b['x'],b['y'],0.0,b['size_x'],b['size_y'],1.0,b['yaw']])
    ia=_polygon_area(_clip_polygon(bev_corners(ba),bev_corners(bb)))
    za=min(a['z_bottom']+a['size_z'], b['z_bottom']+b['size_z'])-max(a['z_bottom'],b['z_bottom'])
    if ia<=0 or za<=0: return 0.0
    ib=ia*za
    va=a['size_x']*a['size_y']*a['size_z']; vb=b['size_x']*b['size_y']*b['size_z']
    return float(ib/(va+vb-ib))

def discover():
    out=[]
    for g in GROUPS:
        for s in sorted(os.listdir(ROOT/g)):
            d=ROOT/g/s
            if not d.is_dir(): continue
            nb=len(glob.glob(f'{d}/object_labels/lidar/*.json'))
            nl=len(glob.glob(f'{d}/labels/*.label'))
            out.append(dict(group=g,scene=s,rel=f'{g}/{s}',dir=d,n_box_json=nb,n_frame=nl,
                            meta=read_metadata(d/'metadata.txt')))
    return out

def pct(a,ps=(5,50,95)):
    a=np.asarray(a,float)
    return {f'p{p}':float(np.percentile(a,p)) for p in ps}
