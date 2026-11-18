"""Final rule: DBSCAN primary cluster -> pseudo box; validate on all 36 boxed scenes.
Usage: python step8_final.py  (writes final_eval.csv + prints report)"""
import sys, os, glob, csv, collections, json
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
from sklearn.cluster import DBSCAN

# campaign constants fitted on the 36 boxed scenes (per class); see step4
C=json.load(open('.scratch/roadspray-cal/tmp/pseudo/constants.json'))
SPLITS=json.load(open('data/sspp_split.json'))

def primary_cluster(p, eps=1.0, min_samples=8):
    lab=DBSCAN(eps=eps,min_samples=min_samples).fit(p[:,:2]).labels_
    best=-1; bestn=0
    for c in sorted(set(lab)):
        if c<0: continue
        n=int((lab==c).sum())
        if n>bestn: best,bestn=c,n
    if best<0: return p, 1.0
    return p[lab==best], bestn/len(p)

def ground_z(pts,lbl,cx,cy):
    bg=pts[lbl==0,:3].astype(float)
    road=bg[(np.abs(bg[:,1])<2.0)&(bg[:,0]>4.0)&(bg[:,0]<cx+8.0)&(bg[:,2]>-2.5)&(bg[:,2]<0.6)]
    if len(road)<30: return np.nan
    X=np.c_[np.ones(len(road)),road[:,0],road[:,1]]
    sol,_,_,_=np.linalg.lstsq(X,road[:,2],rcond=None)
    res=road[:,2]-X@sol; keep=np.abs(res-np.median(res))<0.35
    if keep.sum()>=20:
        sol,_,_,_=np.linalg.lstsq(X[keep],road[keep,2],rcond=None)
    return float(sol[0]+sol[1]*cx+sol[2]*cy)

def build(pts,lbl,cls,zmode='ground'):
    """Pseudo box from points+labels only. cls = Car/Van from metadata object_name."""
    m=lbl==1
    p=pts[m,:3].astype(float)
    if len(p)<10: return None, dict(n1=int(m.sum()),purity=0.0)
    q,purity=primary_cluster(p)
    sx,sy,sz=C[cls]['dims']
    cx=float(np.mean(np.sort(q[:,0])[:2])) - C[cls]['dx'] + sx/2.0
    cy=float(np.median(q[:,1])) + C[cls]['dy']
    zg=ground_z(pts,lbl,cx,cy)
    if zmode=='ground' and np.isfinite(zg): zb=zg+C[cls]['zg']; zsrc='ground'
    else: zb=C[cls]['zb']; zsrc='const'
    pb=dict(x=cx,y=cy,z_bottom=zb,size_x=sx,size_y=sy,size_z=sz,yaw=0.0)
    diag=dict(n1=int(m.sum()),n_primary=int(len(q)),purity=purity,src=zsrc,
              rng=float(np.median(np.linalg.norm(q[:,:2],axis=1))))
    return pb,diag

def main():
    scenes=lib.discover(); boxed=[s for s in scenes if s['n_box_json']>0]
    split_of={}
    for sp,lst in SPLITS['split'].items():
        for rel in lst: split_of[rel]=sp
    rows=[]
    for s in boxed:
        for jp in sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json")):
            sid=os.path.basename(jp)[:-5]
            bx=lib.read_frame_boxes(jp)
            if not bx: continue
            b=bx[0]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            cls={"Golf":"Car","Crafter":"Van"}[s["meta"]["object_name"]]
            pb,diag=build(pts,lbl,cls)
            if pb is None: continue
            hb=dict(x=b['x'],y=b['y'],z_bottom=b['z_bottom'],size_x=b['size_x'],size_y=b['size_y'],size_z=b['size_z'],yaw=b['yaw'])
            # also yaw fitted on primary cluster rear slab
            m=lbl==1; p=pts[m,:3].astype(float); q,_=primary_cluster(p)
            slab=q[q[:,0]<=np.percentile(q[:,0],2)+0.4]
            yawfit=np.nan
            if len(slab)>=8 and np.ptp(slab[:,1])>0.3:
                A=np.c_[slab[:,1],np.ones(len(slab))]; sol,_,_,_=np.linalg.lstsq(A,slab[:,0],rcond=None)
                yawfit=float((-np.arctan(sol[0])+np.pi/2)%np.pi-np.pi/2)
            pb2=dict(pb); 
            if np.isfinite(yawfit): pb2['yaw']=yawfit
            # visible-face characterisation in human-box frame
            u,v=lib.to_box_frame(p,b)
            rows.append(dict(scene=s['rel'],group=s['group'],frame=int(sid),name=cls,
                vel=float(s['meta']['object_velocity']),dist=float(s['meta']['distance_to_object']),
                split=split_of.get(s['rel'],'?'),itr=s['meta'].get('itr_after_water'),
                bev=lib.bev_iou(pb,hb),iou3d=lib.iou_3d(pb,hb),bev_yawfit=lib.bev_iou(pb2,hb),iou3d_yawfit=lib.iou_3d(pb2,hb),
                yawfit=yawfit,hyaw=b['yaw'],
                dcx=pb['x']-b['x'],dcy=pb['y']-b['y'],dzb=pb['z_bottom']-b['z_bottom'],
                n1=diag['n1'],n_primary=diag['n_primary'],purity=diag['purity'],zsrc=diag['src'],
                # visible geometry, in human box frame
                u_p2=float(np.percentile(u,2)),u_max=float(u.max()),
                vis_depth=float(np.percentile(u,98)-np.percentile(u,2)),
                v_span=float(np.percentile(v,98)-np.percentile(v,2)),
                z_p2=float(np.percentile(p[:,2],2)),z_p98=float(np.percentile(p[:,2],98)),
                rear_off=float(np.percentile(u,2)+b['size_x']/2),
                hsx=b['size_x'],hsy=b['size_y'],hsz=b['size_z'],hx=b['x'],hzb=b['z_bottom']))
    keys=sorted({k for r in rows for k in r})
    with open('.scratch/roadspray-cal/tmp/pseudo/final_eval.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); w.writerows(rows)
    R=rows
    def pr(a,ps=(5,50,95)):
        a=np.asarray([x for x in a if x==x],float); return ' '.join(f'p{p}={np.percentile(a,p):.3f}' for p in ps)
    print(f'frames {len(R)}')
    for col in ('bev','iou3d','bev_yawfit','iou3d_yawfit'):
        a=np.array([r[col] for r in R],float)
        print(f'{col:14s} n={len(a)} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} p95={np.percentile(a,95):.3f} mean={a.mean():.3f} '
              f'ge0.7={100*np.mean(a>=0.7):5.1f}% ge0.5={100*np.mean(a>=0.5):5.1f}% <0.3={100*np.mean(a<0.3):4.1f}%')
    print('\nbias pseudo-human:', 'dcx',pr([r['dcx'] for r in R],(5,50,95)),'mean',round(float(np.mean([r['dcx'] for r in R])),3))
    print('                     dcy',pr([r['dcy'] for r in R],(5,50,95)),'mean',round(float(np.mean([r['dcy'] for r in R])),3))
    print('                     dzb',pr([r['dzb'] for r in R],(5,50,95)),'mean',round(float(np.mean([r['dzb'] for r in R])),3))
    print('\nby class:'); 
    for cls in ('Car','Van'):
        a=np.array([r['bev'] for r in R if r['name']==cls]); print(f'  {cls} n={len(a)} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}%')
    print('by distance:')
    for d in (20.0,30.0):
        a=np.array([r['bev'] for r in R if r['dist']==d]); print(f'  {d:.0f} m n={len(a)} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}%')
    print('by speed (BEV p5/p50/ge0.7 | 3D p50/ge0.7):')
    for v in sorted(set(r['vel'] for r in R)):
        a=np.array([r['bev'] for r in R if r['vel']==v]); b=np.array([r['iou3d'] for r in R if r['vel']==v])
        print(f'  {v:3.0f} n={len(a):4d} bev p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.0f}% | 3d p50={np.percentile(b,50):.3f} ge0.7={100*np.mean(b>=0.7):.0f}%')
    print('by split (for reference):')
    for sp in ('train','val','test'):
        a=np.array([r['bev'] for r in R if r['split']==sp]); print(f'  {sp} n={len(a)} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}%')
    print('\npurity: p5/p50/p95',pr([r['purity'] for r in R]))
    print('z source:',collections.Counter(r['zsrc'] for r in R))
    print('gates: n_primary>=30', f"{100*np.mean([r['n_primary']>=30 for r in R]):.1f}%", '>=50',f"{100*np.mean([r['n_primary']>=50 for r in R]):.1f}%")
    print('\nworst 10:')
    for r in sorted(R,key=lambda x:x['bev'])[:10]:
        print(f"  {r['scene'][:24]:24s} f{r['frame']:>3d} {r['name']:3s} v={r['vel']:.0f} d={r['dist']:.0f} n1={r['n1']:3d} nP={r['n_primary']:3d} pur={r['purity']:.2f} rng={np.hypot(r['hx'],0):.0f} hyaw={r['hyaw']:+.2f} bev={r['bev']:.2f} 3d={r['iou3d']:.2f} dcx={r['dcx']:+.2f}")
    # visible faces
    print('\n=== visible-face characterisation (human box frame) ===')
    print('u_p2 offset vs human rear face (m):',pr([r['rear_off'] for r in R]))
    for cls in ('Car','Van'):
        vis=np.array([r['vis_depth'] for r in R if r['name']==cls]); mx=np.array([r['u_max'] for r in R if r['name']==cls])
        hsx=np.array([r['hsx'] for r in R if r['name']==cls]); vs=np.array([r['v_span'] for r in R if r['name']==cls]); hsy=np.array([r['hsy'] for r in R if r['name']==cls])
        print(f'  {cls}: visible depth p50={np.median(vis):.2f} m = {100*np.median(vis/hsx):.0f}% of length; u_max - front face p50={np.median(mx-hsx/2):+.2f} m; v_span={np.median(vs):.2f} = {100*np.median(vs/hsy):.0f}% of width')
    print('z point bottom - human zb:',pr([r['z_p2']-r['hzb'] for r in R]),' z point top - human ztop:',pr([r['z_p98']-(r['hzb']+r['hsz']) for r in R]))

main()
