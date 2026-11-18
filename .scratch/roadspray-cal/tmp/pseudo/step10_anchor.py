"""Compare cluster/anchor variants for robustness: 2D-BEV vs 3D DBSCAN, min vs percentiles."""
import sys, os, glob, csv, collections, json
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
from sklearn.cluster import DBSCAN
C=json.load(open('.scratch/roadspray-cal/tmp/pseudo/constants.json'))
CLS={"Golf":"Car","Crafter":"Van"}

def primary(p, use3d, eps, ms):
    X=p if use3d else p[:,:2]
    lab=DBSCAN(eps=eps,min_samples=ms).fit(X).labels_
    best=-1;bn=0
    for c in sorted(set(lab)):
        if c<0: continue
        n=int((lab==c).sum())
        if n>bn: best,bn=c,n
    if best<0: return p,1.0
    return p[lab==best],bn/len(p)

def main():
    scenes=lib.discover(); boxed=[s for s in scenes if s['n_box_json']>0]
    rows=[]
    for s in boxed:
        for jp in sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json")):
            sid=os.path.basename(jp)[:-5]
            bx=lib.read_frame_boxes(jp)
            if not bx: continue
            b=bx[0]; hrear=b['x']-b['size_x']/2
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            p=pts[lbl==1,:3].astype(float)
            if len(p)<10: continue
            cls=CLS[s['meta']['object_name']]
            r=dict(scene=s['rel'],frame=int(sid),name=cls,n1=len(p),vel=float(s['meta']['object_velocity']),
                   dist=float(s['meta']['distance_to_object']),hx=b['x'],hrear=hrear,hy=b['y'],
                   hsx=b['size_x'],hsy=b['size_y'],hsz=b['size_z'],hzb=b['z_bottom'],hyaw=b['yaw'])
            for tag,u3,eps,ms in (('d2',False,1.0,8),('d3',True,0.7,8),('d3b',True,0.9,6)):
                q,pur=primary(p,u3,eps,ms)
                r[f'pur_{tag}']=pur; r[f'n_{tag}']=len(q)
                for pc in (0,1,2,5,10):
                    r[f'anchor_{tag}_{pc}']=float(np.percentile(q[:,0],pc))
                r[f'y50_{tag}']=float(np.median(q[:,1])); r[f'x50_{tag}']=float(np.median(q[:,0]))
                r[f'contam_{tag}']=float(np.mean(q[:,0]<hrear-0.30))
                r[f'z50_{tag}']=float(np.median(q[:,2]))
            rows.append(r)
    keys=sorted({k for r in rows for k in r})
    with open('.scratch/roadspray-cal/tmp/pseudo/anchor_eval.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); w.writerows(rows)
    print('frames',len(rows))
    # fit dx per class for each (tag,pc) and evaluate
    print('\n(tag,pct)  dxCar  dxVan    p5     p50    ge0.7   <0.3   note')
    for tag in ('d2','d3','d3b'):
        for pc in (0,1,2,5,10):
            ious=[]
            for cls in ('Car','Van'):
                sub=[r for r in rows if r['name']==cls]
                dx=float(np.median([r[f'anchor_{tag}_{pc}']-r['hrear'] for r in sub]))
                sx,sy,sz=C[cls]['dims']; dy=C[cls]['dy']
                for r in sub:
                    cx=r[f'anchor_{tag}_{pc}']-dx+sx/2.0
                    cy=r[f'y50_{tag}']+dy
                    pb=dict(x=cx,y=cy,z_bottom=r['hzb'],size_x=sx,size_y=sy,size_z=sz,yaw=0.0)
                    hb=dict(x=r['hx'],y=r['hy'],z_bottom=r['hzb'],size_x=r['hsx'],size_y=r['hsy'],size_z=r['hsz'],yaw=r['hyaw'])
                    ious.append(lib.bev_iou(pb,hb))
            a=np.array(ious)
            dxs={cls:float(np.median([r[f'anchor_{tag}_{pc}']-r['hrear'] for r in rows if r['name']==cls])) for cls in ('Car','Van')}
            print(f'{tag:4s} p{pc:<2d} {dxs["Car"]:+.3f} {dxs["Van"]:+.3f}  {np.percentile(a,5):.3f}  {np.percentile(a,50):.3f}  {100*np.mean(a>=0.7):5.1f}% {100*np.mean(a<0.3):4.1f}%')
    # contamination stats
    print('\ncontamination (frac of primary-cluster pts behind human rear-0.3m):')
    for tag in ('d2','d3','d3b'):
        c=np.array([r[f'contam_{tag}'] for r in rows]); print(f'  {tag}: p50={np.median(c):.3f} p95={np.percentile(c,95):.3f} frac>0 2%: {100*np.mean(c>0.02):.1f}%')
    print('\n3D cluster size vs 2D: n_d3/n_d2 p5/p50/p95', np.round(np.percentile([r['n_d3']/r['n_d2'] for r in rows],[5,50,95]),3))
    print('purity d2/d3 p5:', np.round(np.percentile([r['pur_d2'] for r in rows],5),3), np.round(np.percentile([r['pur_d3'] for r in rows],5),3))

main()
