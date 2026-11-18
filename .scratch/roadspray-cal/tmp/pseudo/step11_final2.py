"""FINAL: 3D-DBSCAN primary cluster -> p2-anchored pseudo box. 3-fold scene CV + breakdowns,
then applied to a sample of the 171 unboxed scenes for gate rates / payoff."""
import sys, os, glob, csv, collections, json
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
from sklearn.cluster import DBSCAN
CLS={"Golf":"Car","Crafter":"Van"}
DEFAULT_Z={'Car':-0.3964,'Van':-0.34}
SPLITS=json.load(open('data/sspp_split.json'))['split']
SPLIT_OF={rel:sp for sp,l in SPLITS.items() for rel in l}

def primary3d(p,eps=0.7,ms=8):
    lab=DBSCAN(eps=eps,min_samples=ms).fit(p).labels_
    best=-1;bn=0
    for c in sorted(set(lab)):
        if c<0: continue
        n=int((lab==c).sum())
        if n>bn: best,bn=c,n
    if best<0: return p,1.0
    return p[lab==best],bn/len(p)

def ground_z(pts,lbl,cx,cy):
    bg=pts[lbl==0,:3].astype(float)
    road=bg[(np.abs(bg[:,1])<2.0)&(bg[:,0]>4.0)&(bg[:,0]<cx+8.0)&(bg[:,2]>-2.5)&(bg[:,2]<0.6)]
    if len(road)<30: return np.nan
    X=np.c_[np.ones(len(road)),road[:,0],road[:,1]]
    sol,_,_,_=np.linalg.lstsq(X,road[:,2],rcond=None)
    res=road[:,2]-X@sol; k=np.abs(res-np.median(res))<0.35
    if k.sum()>=20: sol,_,_,_=np.linalg.lstsq(X[k],road[k,2],rcond=None)
    return float(sol[0]+sol[1]*cx+sol[2]*cy)

def anchors(pts,lbl):
    m=lbl==1; p=pts[m,:3].astype(float)
    if len(p)<10: return None
    q,pur=primary3d(p)
    sx=float(np.percentile(q[:,0],2)); sy=float(np.median(q[:,1]))
    return dict(q=q,pur=pur,n1=int(m.sum()),anchor=sx,cy0=sy)

def fit_constants(recs):
    C={}
    for cls in ('Car','Van'):
        sub=[r for r in recs if r['cls']==cls]
        C[cls]=dict(
            dims=[float(np.median([r['hsx'] for r in sub])),float(np.median([r['hsy'] for r in sub])),float(np.median([r['hsz'] for r in sub]))],
            dx=float(np.median([r['anchor']-r['hrear'] for r in sub])),
            dy=float(np.median([r['hy']-r['cy0'] for r in sub])),
            zb=float(np.median([r['hzb'] - r['gz'] for r in sub if r['gz']==r['gz']])) if any(r['gz']==r['gz'] for r in sub) else DEFAULT_Z[cls])
    # zb is a ground-plane offset: human_zb - estimated_ground
    return C

def evaluate(recs,C):
    out=[]
    for r in recs:
        cls=r['cls']; sx,sy,sz=C[cls]['dims']
        cx=r['anchor']-C[cls]['dx']+sx/2.0
        cy=r['cy0']+C[cls]['dy']
        if r['gz']==r['gz']: zb=r['gz']+C[cls]['zb']
        else: zb=DEFAULT_Z[cls]
        pb=dict(x=cx,y=cy,z_bottom=zb,size_x=sx,size_y=sy,size_z=sz,yaw=0.0)
        hb=dict(x=r['hx'],y=r['hy'],z_bottom=r['hzb'],size_x=r['hsx'],size_y=r['hsy'],size_z=r['hsz'],yaw=r['hyaw'])
        d=dict(r); d.update(bev=lib.bev_iou(pb,hb),iou3d=lib.iou_3d(pb,hb),pb=pb,
                            dcx=cx-r['hx'],dcy=cy-r['hy'],dzb=zb-r['hzb'],
                            dsx=sx-r['hsx'],dsy=sy-r['hsy'],dsz=sz-r['hsz'])
        out.append(d)
    return out

def collect_boxed():
    scenes=lib.discover(); boxed=[s for s in scenes if s['n_box_json']>0]
    recs=[]
    for s in boxed:
        for jp in sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json")):
            sid=os.path.basename(jp)[:-5]
            bx=lib.read_frame_boxes(jp)
            if not bx: continue
            b=bx[0]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            a=anchors(pts,lbl)
            if a is None: continue
            gz=ground_z(pts,lbl,a['anchor'],a['cy0'])
            recs.append(dict(scene=s['rel'],group=s['group'],frame=int(sid),
                cls=CLS[s['meta']['object_name']],vel=float(s['meta']['object_velocity']),
                dist=float(s['meta']['distance_to_object']),split=SPLIT_OF.get(s['rel'],'?'),
                n1=a['n1'],n_primary=len(a['q']),purity=a['pur'],anchor=a['anchor'],cy0=a['cy0'],gz=gz,
                hx=b['x'],hy=b['y'],hzb=b['z_bottom'],hsx=b['size_x'],hsy=b['size_y'],hsz=b['size_z'],
                hyaw=b['yaw'],hrear=b['x']-b['size_x']/2))
    return recs

def collect_unboxed(n_per=12):
    scenes=lib.discover(); unb=[s for s in scenes if s['n_box_json']==0]
    recs=[]
    for s in unb:
        labs=sorted(glob.glob(f"{s['dir']}/labels/*.label"))
        for i in sorted(set(int(x) for x in np.linspace(0,len(labs)-1,n_per).round())):
            sid=os.path.basename(labs[i])[:-6]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            a=anchors(pts,lbl)
            r=dict(scene=s['rel'],group=s['group'],frame=int(sid),
                   cls=CLS[s['meta']['object_name']],vel=float(s['meta']['object_velocity']),
                   dist=float(s['meta']['distance_to_object']),n_frame=s['n_frame'],
                   itr=int(s['meta']['itr_after_water']),n2=int((lbl==2).sum()))
            if a is None:
                r.update(ok=0,n1=0,n_primary=0,purity=0.0)
            else:
                r.update(ok=1,n1=a['n1'],n_primary=len(a['q']),purity=a['pur'],anchor=a['anchor'],cy0=a['cy0'],
                         gz=ground_z(pts,lbl,a['anchor'],a['cy0']))
            recs.append(r)
    return recs

def pr(a,ps=(5,50,95),fmt='{:.3f}'):
    a=np.asarray([x for x in a if x==x],float)
    return ' '.join(f'p{p}={fmt.format(np.percentile(a,p))}' for p in ps)

def report(R,C):
    print('frames',len(R))
    print('constants:',json.dumps(C,indent=None))
    bev=np.array([r['bev'] for r in R]); d3=np.array([r['iou3d'] for r in R])
    print(f'\nBEV  p5={np.percentile(bev,5):.3f} p50={np.percentile(bev,50):.3f} p95={np.percentile(bev,95):.3f} mean={bev.mean():.3f} ge0.7={100*np.mean(bev>=0.7):.1f}% ge0.5={100*np.mean(bev>=0.5):.1f}% <0.3={100*np.mean(bev<0.3):.1f}%')
    print(f'3D   p5={np.percentile(d3,5):.3f} p50={np.percentile(d3,50):.3f} p95={np.percentile(d3,95):.3f} mean={d3.mean():.3f} ge0.7={100*np.mean(d3>=0.7):.1f}% ge0.5={100*np.mean(d3>=0.5):.1f}%')
    print('\nbias pseudo-human:')
    for k,lbl in (('dcx','centre_x'),('dcy','centre_y'),('dzb','z_bottom'),('dsx','size_x'),('dsy','size_y'),('dsz','size_z')):
        a=np.array([r[k] for r in R]); print(f'  {lbl:10s} p5={np.percentile(a,5):+.3f} p50={np.percentile(a,50):+.3f} p95={np.percentile(a,95):+.3f} mean={a.mean():+.3f} sd={a.std():.3f}')
    print('\nby class:')
    for cls in ('Car','Van'):
        a=np.array([r['bev'] for r in R if r['cls']==cls]); b=np.array([r['iou3d'] for r in R if r['cls']==cls])
        print(f'  {cls} n={len(a)} bev p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}% | 3d p50={np.percentile(b,50):.3f} ge0.7={100*np.mean(b>=0.7):.1f}%')
    print('by distance:')
    for d in (20.0,30.0):
        a=np.array([r['bev'] for r in R if r['dist']==d]); b=np.array([r['iou3d'] for r in R if r['dist']==d])
        print(f'  {d:.0f}m n={len(a)} bev p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}% | 3d p50={np.percentile(b,50):.3f} ge0.7={100*np.mean(b>=0.7):.1f}%')
    print('by speed:')
    for v in sorted(set(r['vel'] for r in R)):
        a=np.array([r['bev'] for r in R if r['vel']==v]); b=np.array([r['iou3d'] for r in R if r['vel']==v])
        print(f'  {v:3.0f} n={len(a):4d} bev p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):5.1f}% | 3d p50={np.percentile(b,50):.3f} ge0.7={100*np.mean(b>=0.7):.1f}%')
    print('by existing split:')
    for sp in ('train','val','test'):
        a=np.array([r['bev'] for r in R if r['split']==sp]); b=np.array([r['iou3d'] for r in R if r['split']==sp])
        print(f'  {sp:5s} n={len(a)} bev p50={np.percentile(a,50):.3f} ge0.7={100*np.mean(a>=0.7):.1f}% | 3d p50={np.percentile(b,50):.3f} ge0.7={100*np.mean(b>=0.7):.1f}%')
    print('\nworst 10 by BEV:')
    for r in sorted(R,key=lambda x:x['bev'])[:10]:
        print(f"  {r['scene'][:24]:24s} f{r['frame']:>3d} {r['cls']:3s} v={r['vel']:.0f} d={r['dist']:.0f} n1={r['n1']:3d} nP={r['n_primary']:3d} pur={r['purity']:.2f} hyaw={r['hyaw']:+.2f} bev={r['bev']:.2f} 3d={r['iou3d']:.2f} dcx={r['dcx']:+.2f} dzb={r['dzb']:+.2f}")
    print('\ngates (from point-only quantities):')
    for g,fn in (('purity>=0.7',lambda r:r['purity']>=0.7),('n_primary>=50',lambda r:r['n_primary']>=50),
                 ('pur>=0.7 & n>=50',lambda r:r['purity']>=0.7 and r['n_primary']>=50),
                 ('pur>=0.9 & n>=50',lambda r:r['purity']>=0.9 and r['n_primary']>=50)):
        keep=[r for r in R if fn(r)]; a=np.array([r['bev'] for r in keep])
        print(f'  {g:20s} keeps {100*len(keep)/len(R):5.1f}% -> ge0.7={100*np.mean(a>=0.7):.2f}% <0.3={100*np.mean(a<0.3):.2f}%')
    print('\npurity p5/p50/p95:',pr([r['purity'] for r in R]))
    print('n_primary p5/p50/p95:',pr([r['n_primary'] for r in R],fmt='{:.0f}'))
    print('z source ground: ',f"{100*np.mean([r['gz']==r['gz'] for r in R]):.1f}%")

def main():
    recs=collect_boxed()
    print('=== 3-FOLD SCENE CV (constants fitted on 24 scenes, evaluated on 12) ===')
    scenes=sorted(set(r['scene'] for r in recs)); rng=np.random.default_rng(7)
    order=[scenes[i] for i in rng.permutation(len(scenes))]
    folds=[set(order[0::3]),set(order[1::3]),set(order[2::3])]
    held=[]
    for k in range(3):
        tr=[r for r in recs if r['scene'] not in folds[k]]; va=[r for r in recs if r['scene'] in folds[k]]
        C=fit_constants(tr); E=evaluate(va,C)
        bev=np.array([r['bev'] for r in E]); d3=np.array([r['iou3d'] for r in E])
        print(f' fold{k}: val frames={len(va)} dx Car={C["Car"]["dx"]:.3f} Van={C["Van"]["dx"]:.3f} zb Car={C["Car"]["zb"]:+.3f} Van={C["Van"]["zb"]:+.3f} | bev p5={np.percentile(bev,5):.3f} p50={np.percentile(bev,50):.3f} ge0.7={100*np.mean(bev>=0.7):.1f}% 3d p50={np.percentile(d3,50):.3f} ge0.7={100*np.mean(d3>=0.7):.1f}%')
        held+=E
    print('\nHELD-OUT POOLED:')
    report(held,fit_constants(recs))
    C=fit_constants(recs)
    print('\n=== ALL-36 (constants fitted on all 36) ===')
    report(evaluate(recs,C),C)
    # unboxed
    print('\n=== UNBOXED SAMPLE (171 scenes, 12 frames each) ===')
    U=collect_unboxed()
    good=[r for r in U if r['ok']]
    print(f'sampled {len(U)} frames, primary cluster found {len(good)} ({100*len(good)/len(U):.1f}%)')
    print('gate pass rates on unboxed sample (applying the SAME gates):')
    def gate(r): return r['ok'] and r['purity']>=0.7 and r['n_primary']>=50
    print(f"  purity>=0.7 & n_primary>=50: {100*np.mean([gate(r) for r in U]):.1f}%")
    E=[]
    for r in good:
        pass
    # payoff: scene-level pass rate, frames estimated
    sc=collections.defaultdict(list); nfr={}
    for r in U:
        sc[r['scene']].append(1 if gate(r) else 0); nfr[r['scene']]=r['n_frame']
    goodset={k for k,v in sc.items() if np.mean(v)>=0.8}
    vel={r['scene']:r['vel'] for r in U}
    allsc=lib.discover(); unb=[s for s in allsc if s['n_box_json']==0]
    for nm,vs in (('train 60/80/100/120',{'60','80','100','120'}),('val 70/110',{'70','110'}),('test 50/90/130',{'50','90','130'}),('ALL unboxed',None)):
        ss=[s for s in unb if vs is None or s['meta']['object_velocity'] in vs]
        sgood=[s for s in ss if s['rel'] in goodset]
        print(f'  {nm:22s}: scenes {len(ss):3d} -> usable {len(sgood):3d} | frames {sum(s["n_frame"] for s in ss):5d} -> usable-scene frames {sum(s["n_frame"] for s in sgood):5d}')
    print('\nspray level label2 pts/frame by itr (unboxed sample):')
    by=collections.defaultdict(list)
    for r in U: by[r['itr']].append(r['n2'])
    for k in sorted(by): print(f'  itr{k}: n={len(by[k]):4d} p50={np.median(by[k]):7.0f} p95={np.percentile(by[k],95):7.0f}')

main()
