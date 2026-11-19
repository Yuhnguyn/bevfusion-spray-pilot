"""Apply the final pseudo-box rule to a 12-frame/scene sample of all 171 unboxed scenes:
gate pass rates, spray level by itr_after_water, consistency with metadata."""
import sys, os, glob, csv, collections, json
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
from sklearn.cluster import DBSCAN
C=json.load(open('.scratch/roadspray-cal/tmp/pseudo/constants.json'))
CLS={"Golf":"Car","Crafter":"Van"}

def primary(p,eps=1.0,ms=8):
    lab=DBSCAN(eps=eps,min_samples=ms).fit(p[:,:2]).labels_
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

def build(pts,lbl,cls):
    m=lbl==1; p=pts[m,:3].astype(float)
    d=dict(n1=int(m.sum()),n_primary=0,purity=0.0,ok=0)
    if len(p)<10: return None,d
    q,pur=primary(p); sx,sy,sz=C[cls]['dims']
    cx=float(np.mean(np.sort(q[:,0])[:2]))-C[cls]['dx']+sx/2.0
    cy=float(np.median(q[:,1]))+C[cls]['dy']
    zg=ground_z(pts,lbl,cx,cy)
    zsrc='ground'
    if np.isfinite(zg): zb=zg+C[cls]['zg']
    else: zb=C[cls]['zb']; zsrc='const'
    pb=dict(x=cx,y=cy,z_bottom=zb,size_x=sx,size_y=sy,size_z=sz,yaw=0.0)
    d.update(n_primary=int(len(q)),purity=pur,zsrc=zsrc,ok=1)
    return pb,d

def main():
    scenes=lib.discover(); unb=[s for s in scenes if s['n_box_json']==0]
    rows=[]
    for s in unb:
        labs=sorted(glob.glob(f"{s['dir']}/labels/*.label"))
        for i in sorted(set(int(x) for x in np.linspace(0,len(labs)-1,12).round())):
            sid=os.path.basename(labs[i])[:-6]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            cls=CLS[s['meta']['object_name']]
            pb,d=build(pts,lbl,cls)
            r=dict(scene=s['rel'],group=s['group'],frame=int(sid),cls=cls,
                   vel=float(s['meta']['object_velocity']),dist=float(s['meta']['distance_to_object']),
                   itr=int(s['meta']['itr_after_water']),n2=int((lbl==2).sum()),n0=int((lbl==0).sum()),
                   n_frame=s['n_frame'],**d)
            if pb is not None:
                r['cx']=pb['x']; r['cy']=pb['y']; r['zb']=pb['z_bottom']
                r['cx_minus_dist']=pb['x']-r['dist']
                rel=lib.ROOT/s['rel']
                r['rng']=float(np.hypot(pb['x'],pb['y']))
            rows.append(r)
    keys=sorted({k for r in rows for k in r})
    with open('.scratch/roadspray-cal/tmp/pseudo/unboxed_final.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); w.writerows(rows)
    R=[r for r in rows if r.get('ok')]
    print(f'sampled frames {len(rows)} usable {len(R)} ({100*len(R)/len(rows):.1f}%)')
    def pr(a,ps=(5,50,95)):
        a=np.asarray(a,float); return ' '.join(f'p{p}={np.percentile(a,p):.1f}' for p in ps)
    print('n1      :',pr([r['n1'] for r in rows]))
    print('n_prim  :',pr([r['n_primary'] for r in R]))
    print('purity  :',pr([r['purity'] for r in R]))
    print('cx-dist :',pr([r['cx_minus_dist'] for r in R]))
    print('range   :',pr([r['rng'] for r in R]))
    for g,fn in (('n_primary>=30',lambda r:r['n_primary']>=30),
                 ('n_primary>=50',lambda r:r['n_primary']>=50),
                 ('purity>=0.7',lambda r:r['purity']>=0.7),
                 ('|cx-dist|<=10',lambda r:abs(r['cx_minus_dist'])<=10),
                 ('all gates',lambda r:r['n_primary']>=30 and r['purity']>=0.7 and abs(r['cx_minus_dist'])<=10),
                 ('z=ground',lambda r:r['zsrc']=='ground')):
        print(f' pass {g:16s}: {100*np.mean([fn(r) for r in R]):.1f}%')
    print('\nspray points/frame (n2) by itr_after_water (unboxed) + boxed itr=1 for reference:')
    by=collections.defaultdict(list)
    for r in rows: by[r['itr']].append(r['n2'])
    for k in sorted(by): print(f'  itr{k}: n={len(by[k]):4d} n2 p50={np.median(by[k]):7.1f} p95={np.percentile(by[k],95):7.1f}')
    boxed=list(csv.DictReader(open('.scratch/roadspray-cal/tmp/pseudo/features.csv')))
    n2b=np.array([float(r['n2']) for r in boxed]); print(f'  boxed itr1: n={len(n2b)} n2 p50={np.median(n2b):7.1f} p95={np.percentile(n2b,95):7.1f}')
    print('\nn2 by speed for unboxed sample:')
    for v in sorted(set(r['vel'] for r in rows)):
        a=[r['n2'] for r in rows if r['vel']==v]; print(f'  {v:3.0f}: n={len(a):4d} p50={np.median(a):7.1f}')
    print('\nscenes with >=70% frames passing all gates:')
    sc=collections.defaultdict(list)
    for r in R: sc[r['scene']].append(r['n_primary']>=30 and r['purity']>=0.7 and abs(r['cx_minus_dist'])<=10)
    good=[k for k,v in sc.items() if np.mean(v)>=0.7]
    print(f'  {len(good)}/{len(sc)} scenes; frames in those scenes (actual n_frame) = {sum(s["n_frame"] for s in unb if s["rel"] in good)}')
    # per split-speed payoff
    vel_of={s['rel']:s['meta']['object_velocity'] for s in unb}
    nfr={s['rel']:s['n_frame'] for s in unb}
    goodset=set(good)
    for nm,vs in (('train60/80/100/120',{'60','80','100','120'}),('val70/110',{'70','110'}),('test50/90/130',{'50','90','130'})):
        ss=[s for s in unb if s['meta']['object_velocity'] in vs]
        print(f'  unboxed {nm}: scenes={len(ss)} frames={sum(s["n_frame"] for s in ss)} usable-scenes={len([s for s in ss if s["rel"] in goodset])} usable-frames~{sum(s["n_frame"] for s in ss if s["rel"] in goodset)}')

main()
