"""Pass 3: sample unboxed scenes -> pseudo-box producibility + spray level by itr_after_water."""
import sys, os, glob, csv, numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
sys.path.insert(0,'.')
import lib
from spray.sspp_adapter import read_metadata

def snapshot(lbl):
    return dict(n2=int((lbl==2).sum()), n0=int((lbl==0).sum()))

def main():
    scenes=lib.discover()
    unb=[s for s in scenes if s['n_box_json']==0]
    boxed=[s for s in scenes if s['n_box_json']>0]
    out=[]
    for s in unb:
        labs=sorted(glob.glob(f"{s['dir']}/labels/*.label"))
        idx=sorted(set(int(x) for x in np.linspace(0,len(labs)-1,10).round()))
        for i in idx:
            sid=os.path.basename(labs[i])[:-6]
            lbl=lib.load_labels(s['dir'],sid); pts=lib.load_points(s['dir'],sid)
            m=lbl==1; p=pts[m,:3].astype(np.float64)
            r=dict(scene=s['rel'],group=s['group'],frame=int(sid),name=s['meta']['object_name'],
                   vel=float(s['meta']['object_velocity']),dist=float(s['meta']['distance_to_object']),
                   itr=int(s['meta']['itr_after_water']),n1=int(m.sum()),**snapshot(lbl))
            if len(p)>=10:
                med=np.median(p[:,:2],axis=0); d=np.linalg.norm(p[:,:2]-med,axis=1); kept=p[d<8.0]
                r['n1_kept']=int(len(kept)); r['x_p1']=float(np.percentile(kept[:,0],1))
                r['y_p50']=float(np.median(kept[:,1]))
                r['x_p50']=float(np.median(kept[:,0]))
                r['rng']=float(np.median(np.linalg.norm(kept[:,:2],axis=1)))
                r['x_span']=float(np.percentile(kept[:,0],99)-np.percentile(kept[:,0],1))
                r['y_span']=float(np.percentile(kept[:,1],99)-np.percentile(kept[:,1],1))
                # ground plane
                bg=pts[lbl==0,:3].astype(np.float64)
                road=bg[(np.abs(bg[:,1])<2.0)&(bg[:,0]>4.0)&(bg[:,0]<r['x_p50']+8.0)&(bg[:,2]>-2.5)&(bg[:,2]<0.6)]
                r['g_z0']=np.nan
                if len(road)>=30:
                    X=np.c_[np.ones(len(road)),road[:,0],road[:,1]]
                    sol,_,_,_=np.linalg.lstsq(X,road[:,2],rcond=None)
                    res=road[:,2]-X@sol; keep2=np.abs(res-np.median(res))<0.35
                    if keep2.sum()>=20:
                        sol,_,_,_=np.linalg.lstsq(X[keep2],road[keep2,2],rcond=None)
                    r['g_z0']=float(sol[0]+sol[1]*np.median(kept[:,0])+sol[2]*np.median(kept[:,1]))
            out.append(r)
    keys=sorted({k for r in out for k in r})
    with open('.scratch/roadspray-cal/tmp/pseudo/unboxed_sample.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=keys); w.writeheader()
        for r in out: w.writerow({k:r.get(k,'') for k in keys})
    print('sampled frames',len(out),'scenes',len(unb))
    # spray level by itr
    import collections
    by=collections.defaultdict(list)
    for r in unb:
        by[r['meta']['itr_after_water']].append(r)
    print('\nunboxed scenes per itr:',{k:len(v) for k,v in sorted(by.items())})

main()
