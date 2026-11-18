"""Pass 4: robust selection of the labelled-vehicle cluster when spray is mislabeled as class 1."""
import sys, os, glob, csv, collections
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
from sklearn.cluster import DBSCAN

def clusters(p):
    lab=DBSCAN(eps=1.0,min_samples=8).fit(p[:,:2]).labels_
    out=[]
    for c in sorted(set(lab)):
        if c<0: continue
        sub=p[lab==c]
        out.append(dict(n=len(sub),x50=float(np.median(sub[:,0])),y50=float(np.median(sub[:,1])),
                        x1=float(np.percentile(sub[:,0],1)),x0=float(sub[:,0].min()),
                        sub=sub))
    return out

def iou_for(p_anchor, p_all, b, dims, dx, dy):
    """anchor on a chosen subset; dims class prior; yaw=0"""
    sx,sy,sz=dims
    rear=p_anchor[:,0].min() if len(p_anchor) else np.nan
    # p0.5-ish via two smallest values
    rear=float(np.mean(np.sort(p_anchor[:,0])[:2])) if len(p_anchor)>=2 else rear
    cx=rear-dx+sx/2
    cy=float(np.median(p_anchor[:,1]))+dy
    pb=dict(x=cx,y=cy,z_bottom=b['z_bottom'],size_x=sx,size_y=sy,size_z=sz,yaw=0.0)
    return lib.bev_iou(pb,b),cx,cy

def main():
    scenes=lib.discover(); boxed=[s for s in scenes if s['n_box_json']>0]
    # campaign constants from previous fit
    DIMS={'Car':(4.2503,2.0215,1.5006),'Van':(6.8288,2.4186,2.6206)}
    DX={'Car':0.1268,'Van':0.1864}; DY={'Car':0.0194,'Van':0.0762}
    rows=[]; rules=collections.Counter()
    for s in boxed:
        for jp in sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json")):
            sid=os.path.basename(jp)[:-5]
            bx=lib.read_frame_boxes(jp)
            if not bx: continue
            b=bx[0]; bits=s['rel']
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            p=pts[lbl==1,:3].astype(float)
            if len(p)<8: continue
            med=np.median(p[:,:2],axis=0)
            p8=p[np.linalg.norm(p[:,:2]-med,axis=1)<8.0]
            cls=b['name']; dims=DIMS[cls]; dx=DX[cls]; dy=DY[cls]
            hx=b['x']; hrear=hx-b['size_x']/2
            res={}
            # A: median-radius8 then x_p1
            iouA,_,_=iou_for(p8[np.argsort(p8[:,0])],p8,b,dims,dx,dy)
            res['A_med8']=iouA
            # C: x mode filter
            def mode_filter(p):
                if len(p)<10: return p
                hist,edges=np.histogram(p[:,0],bins=np.arange(p[:,0].min()-0.2,p[:,0].max()+0.6,0.4))
                # smooth
                k=np.array([1,2,3,2,1]); hs=np.convolve(hist,k,'same')
                peak=edges[np.argmax(hs)]+0.2
                keep=np.abs(p[:,0]-peak)<3.0
                q=p[keep]
                if len(q)>5:
                    yo=np.median(q[:,1]); keep2=np.abs(q[:,1]-yo)<1.6
                    if keep2.sum()>5: q=q[keep2]
                return q
            qC=mode_filter(p)
            iouC,_,_=iou_for(qC,p,b,dims,dx,dy)
            res['C_xmode']=iouC
            # D/E: DBSCAN dominant
            cs=clusters(p)
            if cs:
                big=max(cs,key=lambda c:c['n'])
                qD=big['sub']
                iouD,_,_=iou_for(qD,p,b,dims,dx,dy)
                res['D_dbscan_big']=iouD
                # E: merge clusters with |x50-big.x50|<=3.2 and same y side
                qE=np.vstack([c['sub'] for c in cs if abs(c['x50']-big['x50'])<=3.2])
                iouE,_,_=iou_for(qE,p,b,dims,dx,dy)
                res['E_dbscan_merge']=iouE
                # did dominant cluster lie on the human box? rear within 1 m of human rear
                rules['big_ok' if abs(big['x1']-hrear)<1.0 else 'big_bad']+=1
                # another rule: largest x among clusters n>=20
                cand=[c for c in cs if c['n']>=20] or cs
                far=max(cand,key=lambda c:c['x50'])
                rules['farx_ok' if abs(far['x1']-hrear)<1.0 else 'farx_bad']+=1
            rows.append(dict(scene=bits,frame=int(sid),name=cls,n1=len(p),**res,
                             hyaw=b['yaw'],hrear=hrear,vel=float(s['meta']['object_velocity']),
                             dist=float(s['meta']['distance_to_object'])))
    keys=sorted({k for r in rows for k in r})
    with open('.scratch/roadspray-cal/tmp/pseudo/filter_eval.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader()
        for r in rows: w.writerow({k:r.get(k,'') for k in keys})
    print('frames',len(rows)); print('cluster selection:',dict(rules))
    for k in [k for k in keys if k in ('A_med8','C_xmode','D_dbscan_big','E_dbscan_merge')]:
        a=np.array([r[k] for r in rows if k in r and r[k]==r[k]],float)
        print(f'{k:16s} n={len(a)} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} p95={np.percentile(a,95):.3f} ge0.7={100*(a>=0.7).mean():.1f}% ge0.5={100*(a>=0.5).mean():.1f}% <0.3={100*(a<0.3).mean():.1f}%')

main()
