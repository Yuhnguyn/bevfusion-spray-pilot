"""Pass 2: per-frame features usable WITHOUT the human box (points+labels only)
plus the human box for validation. Survives in features.csv for offline rule search."""
import sys, os, glob, csv, numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib

def pcts(a, ps):
    if len(a)==0: return [np.nan]*len(ps)
    return [float(np.percentile(a,p)) for p in ps]

def frame_features(pts, lbl, meta):
    m=lbl==1
    p=pts[m,:3].astype(np.float64)
    f=dict(n1=int(m.sum()), n2=int((lbl==2).sum()), nbg=int((lbl==0).sum()))
    if len(p)<10:
        return f
    med=np.median(p[:,:2],axis=0)
    d=np.linalg.norm(p[:,:2]-med,axis=1)
    keep=d<8.0
    q=p[keep]
    f['n1_kept']=int(keep.sum()); f['n1_out']=int((~keep).sum())
    f['x_p']=pcts(q[:,0],(0,1,2,5,50,95,98,99,100))
    f['y_p']=pcts(q[:,1],(0,1,2,5,50,95,98,99,100))
    f['z_p']=pcts(q[:,2],(0,1,5,25,50,75,95,99,100))
    # ---- yaw from rear-face line fit: rear slab x <= x_p2 + 0.40 ; x = b + a*y ; yaw = -atan(a)
    x2=f['x_p'][2]
    slab=q[q[:,0]<=x2+0.40]
    f['slab_n']=int(len(slab)); f['yaw_rearfit']=np.nan; f['rearfit_r2']=np.nan
    if len(slab)>=8 and np.ptp(slab[:,1])>0.3:
        A=np.c_[slab[:,1],np.ones(len(slab))]
        sol,res,_,_=np.linalg.lstsq(A,slab[:,0],rcond=None)
        pred=A@sol
        ss=float(np.sum((slab[:,0]-pred)**2)); tot=float(np.sum((slab[:,0]-slab[:,0].mean())**2))
        f['yaw_rearfit']=float(-np.arctan(sol[0])); f['rearfit_r2']=1.0-ss/tot if tot>0 else np.nan
        f['yaw_rearfit']=float((f['yaw_rearfit']+np.pi/2)%np.pi-np.pi/2)
    # ---- PCA yaw
    xy=q[:,:2]; c=xy.mean(0)
    w,V=np.linalg.eigh(np.cov((xy-c).T))
    major=V[:,np.argmax(w)]
    yaw_pca=np.arctan2(major[1],major[0])-np.pi/2
    f['yaw_pca']=float((yaw_pca+np.pi/2)%np.pi-np.pi/2)
    # ---- local ground plane from background points (label==0): z = a + b x + c y
    bgm=(lbl==0)
    b=p[0] if False else None
    bp=pts[bgm,:3].astype(np.float64)
    cx=float(np.median(q[:,0])); cy=float(np.median(q[:,1]))
    f['cx_est']=cx; f['cy_est']=cy
    sel=(np.abs(bp[:,1])<1.0)&(bp[:,0]>0) if False else None
    road=bp[(np.abs(bp[:,1])<2.0)&(bp[:,0]>4.0)&(bp[:,0]<cx+8.0)&(bp[:,2]>-2.5)&(bp[:,2]<0.6)]
    f['road_n']=int(len(road))
    for k in ('g_z0','g_zb','g_zc'):
        f[k]=np.nan
    if len(road)>=30:
        X=np.c_[np.ones(len(road)),road[:,0],road[:,1]]
        sol,_,_,_=np.linalg.lstsq(X,road[:,2],rcond=None)
        r=road[:,2]-X@sol
        keep2=np.abs(r-np.median(r))<0.35
        if keep2.sum()>=20:
            X2=X[keep2]; sol,_,_,_=np.linalg.lstsq(X2,road[keep2,2],rcond=None)
        f['g_z0']=float(sol[0]+sol[1]*cx+sol[2]*cy)   # ground height at object centre
        f['g_zb']=float(sol[0]+sol[1]*(cx-2.0)+sol[2]*cy)
        f['g_zc']=float(sol[0]+sol[1]*(cx+2.0)+sol[2]*cy)
        f['g_n']=int(keep2.sum()) if len(road)>=30 else 0
    # visible-face characterisation vs human box done separately
    return f

def main():
    scenes=lib.discover(); boxed=[s for s in scenes if s['n_box_json']>0]
    out=[]
    for s in boxed:
        for jp in sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json")):
            sid=os.path.basename(jp)[:-5]
            boxes=lib.read_frame_boxes(jp)
            if not boxes: continue
            b=boxes[0]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            f=frame_features(pts,lbl,s['meta'])
            f.update(scene=s['rel'],group=s['group'],frame=int(sid),name=b['name'],
                     hx=b['x'],hy=b['y'],hzb=b['z_bottom'],hsx=b['size_x'],hsy=b['size_y'],
                     hsz=b['size_z'],hyaw=b['yaw'],
                     dist=float(s['meta']['distance_to_object']),vel=float(s['meta']['object_velocity']),
                     itr=s['meta'].get('itr_after_water'))
            out.append(f)
    # flatten
    keys=set()
    for r in out:
        for k,v in r.items():
            if isinstance(v,list):
                for i in range(len(v)): keys.add(f'{k}{i}')
            else: keys.add(k)
    keys=sorted(keys)
    with open('.scratch/roadspray-cal/tmp/pseudo/features.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader()
        for r in out:
            row={}
            for k,v in r.items():
                if isinstance(v,list):
                    for i,x in enumerate(v): row[f'{k}{i}']=x
                else: row[k]=v
            w.writerow({k:row.get(k,'') for k in keys})
    print('frames',len(out))

main()
