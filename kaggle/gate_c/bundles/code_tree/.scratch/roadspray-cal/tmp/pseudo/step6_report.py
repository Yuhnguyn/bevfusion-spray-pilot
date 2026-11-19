"""Final report numbers: rule choice, breakdowns, bias, worst frames, spray shift, payoff."""
import csv, sys, collections
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib
NAN=float('nan')
def fn(v):
    try: return float(v)
    except: return NAN

def load(path, arrs=()):
    rs=list(csv.DictReader(open(path)))
    out=[]
    for r in rs:
        d={k:fn(v) for k,v in r.items() if k not in ('scene','group','name','itr')}
        d['scene']=r['scene']; d['group']=r['group']; d['name']=r['name']; d['itr']=r.get('itr')
        for a,n in arrs:
            d[a]=[fn(r[f'{a}{i}']) for i in range(n)]
        d['hbox']=dict(x=d['hx'],y=d['hy'],z_bottom=d['hzb'],size_x=d['hsx'],size_y=d['hsy'],size_z=d['hsz'],yaw=d['hyaw'])
        out.append(d)
    return out

def fit(rows):
    c={}
    for name in ('Car','Van'):
        sub=[r for r in rows if r['name']==name]
        c[name]=dict(
            dims=(float(np.median([r['hsx'] for r in sub])),float(np.median([r['hsy'] for r in sub])),float(np.median([r['hsz'] for r in sub]))),
            dx=float(np.median([r['x_p'][1]-(r['hx']-r['hsx']/2) for r in sub])),
            zb=float(np.median([r['hzb'] for r in sub])),
            zg=float(np.median([r['hzb']-r['g_z0'] for r in sub if np.isfinite(r['g_z0'])])),
            dy=float(np.median([r['hy']-r['y_p'][4] for r in sub])))
    return c

def pseudo(r,c,yaw_mode='zero',z_mode='ground',xpct=1):
    cls=r['name']; sx,sy,sz=c[cls]['dims']
    cx=r['x_p'][xpct]-c[cls]['dx']+sx/2.0
    cy=r['y_p'][4]+c[cls]['dy']
    yaw=0.0 if yaw_mode=='zero' else (r['yaw_rearfit'] if np.isfinite(r['yaw_rearfit']) else 0.0)
    zb=(c[cls]['zb'] if z_mode=='const' else r['g_z0']+c[cls]['zg'])
    return dict(x=cx,y=cy,z_bottom=zb,size_x=sx,size_y=sy,size_z=sz,yaw=yaw)

def pr(a,ps=(5,50,95)):
    a=np.asarray(a,float); return ' '.join(f'p{p}={np.percentile(a,p):.3f}' for p in ps)

def main():
    rows=load('.scratch/roadspray-cal/tmp/pseudo/features.csv',arrs=(('x_p',9),('y_p',9),('z_p',9)))
    unb=list(csv.DictReader(open('.scratch/roadspray-cal/tmp/pseudo/unboxed_sample.csv')))
    print(f'boxed frames {len(rows)}; unboxed sampled frames {len(unb)}')
    # ---------- 1. distance <-> centre relationship ----------
    print('\n=== [1] distance_to_object vs human box x ===')
    scenes=collections.defaultdict(list)
    for r in rows: scenes[r['scene']].append(r)
    for name in ('Car','Van'):
        sub=[r for r in rows if r['name']==name]
        cx=np.array([r['hx'] for r in sub]); d=np.array([r['dist'] for r in sub]); sx=np.array([r['hsx'] for r in sub])
        print(f'{name}: centre_x - dist     {pr(cx-d)}   sd={np.std(cx-d):.2f}')
        print(f'{name}: rear_face - dist    {pr(cx-sx/2-d)}   sd={np.std(cx-sx/2-d):.2f}')
    first=[np.median([(r['hx']-r['hsx']/2)-r['dist'] for r in v if r['frame']==min(x['frame'] for x in v)]) for v in scenes.values()]
    print('per-scene FIRST frame (rear_face - dist):',pr(first),'sd=',round(float(np.std(first)),2))
    scene_med=[np.median([(r['hx']-r['hsx']/2)-r['dist'] for r in v]) for v in scenes.values()]
    scene_rng=[max((r['hx']-r['hsx']/2)-r['dist'] for r in v)-min((r['hx']-r['hsx']/2)-r['dist'] for r in v) for v in scenes.values()]
    print('per-scene MEDIAN (rear_face - dist):',pr(scene_med),'sd=',round(float(np.std(scene_med)),2))
    print('per-scene drift range of (rear_face - dist):',pr(scene_rng))
    # metadata-only IoU
    ious_meta=[]; 
    for r in rows:
        cls=r['name']; sx=r['hsx']
        pb=dict(x=r['dist']-0.20+sx/2,y=r['y_p'][4],z_bottom=r['hzb'],size_x=sx,size_y=r['hsy'],size_z=r['hsz'],yaw=0.0)
        ious_meta.append(lib.bev_iou(pb,r['hbox']))
    print('metadata-only placement BEV IoU:',pr(ious_meta),'ge0.7=',f'{100*np.mean(np.array(ious_meta)>=0.7):.1f}%')
    # ---------- 2. rule choice / k-fold ----------
    print('\n=== [2] 3-fold scene CV (fit constants on 24 scenes, validate on 12) ===')
    keys=sorted(scenes); rng=np.random.default_rng(0)
    order=[keys[i] for i in rng.permutation(len(keys))]
    folds=[order[0::3],order[1::3],order[2::3]]
    allp=[]
    for k in range(3):
        va=set(folds[k]); fitrows=[r for r in rows if r['scene'] not in va]; valrows=[r for r in rows if r['scene'] in va]
        c=fit(fitrows)
        for r in valrows:
            pb=pseudo(r,c); r['pb']=pb
            allp.append((r,lib.bev_iou(pb,r['hbox']),lib.iou_3d(pb,r['hbox'])))
        print(f' fold{k}: fit scenes {len(set(r["scene"] for r in fitrows))} val {len(va)} | dx Car={c["Car"]["dx"]:.3f} Van={c["Van"]["dx"]:.3f} zg Car={c["Car"]["zg"]:.3f} Van={c["Van"]["zg"]:.3f}')
    bev=np.array([x[1] for x in allp]); d3=np.array([x[2] for x in allp])
    print('held-out BEV IoU:',pr(bev),'ge0.7=',f'{100*np.mean(bev>=0.7):.1f}%','ge0.5=',f'{100*np.mean(bev>=0.5):.1f}%','<0.3=',f'{100*np.mean(bev<0.3):.1f}%')
    print('held-out 3D  IoU:',pr(d3),'ge0.7=',f'{100*np.mean(d3>=0.7):.1f}%','ge0.5=',f'{100*np.mean(d3>=0.5):.1f}%')
    # use full-fit constants for breakdowns
    c=fit(rows); recs=[]
    for r in rows:
        pb=pseudo(r,c); r['pb']=pb
        recs.append((r,lib.bev_iou(pb,r['hbox']),lib.iou_3d(pb,r['hbox'])))
    bev=np.array([x[1] for x in recs]); d3=np.array([x[2] for x in recs])
    print('\nall-36 BEV IoU:',pr(bev),'ge0.7=',f'{100*np.mean(bev>=0.7):.1f}%','ge0.5=',f'{100*np.mean(bev>=0.5):.1f}%')
    print('all-36 3D  IoU:',pr(d3),'ge0.7=',f'{100*np.mean(d3>=0.7):.1f}%','ge0.5=',f'{100*np.mean(d3>=0.5):.1f}%')
    # ---------- 3. bias ----------
    print('\n=== [3] systematic bias pseudo - human ===')
    dz=np.array([x[0]['pb']['z_bottom']-x[0]['hzb'] for x in recs])
    dxc=np.array([x[0]['pb']['x']-x[0]['hx'] for x in recs])
    dyc=np.array([x[0]['pb']['y']-x[0]['hy'] for x in recs])
    # 'length' error proxied by front-face error: pseudo front vs human front
    dfront=np.array([(x[0]['pb']['x']+x[0]['pb']['size_x']/2)-(x[0]['hx']+x[0]['hsx']/2) for x in recs])
    drear=np.array([(x[0]['pb']['x']-x[0]['pb']['size_x']/2)-(x[0]['hx']-x[0]['hsx']/2) for x in recs])
    print('d_centre_x:',pr(dxc,ps=(5,50,95)),'mean',round(dxc.mean(),3))
    print('d_centre_y:',pr(dyc,ps=(5,50,95)),'mean',round(dyc.mean(),3))
    print('d_rear_face_x:',pr(drear,ps=(5,50,95)),'mean',round(drear.mean(),3))
    print('d_front_face_x:',pr(dfront,ps=(5,50,95)),'mean',round(dfront.mean(),3))
    print('d_z_bottom:',pr(dz,ps=(5,50,95)),'mean',round(dz.mean(),3))
    print('d_yaw (pseudo-human): bias 0 by rule; human yaw p5/50/95:',pr([r['hyaw'] for r in rows]))
    # ---------- 4. breakdowns ----------
    print('\n=== [4] BEV IoU breakdown (rule: yaw=0, rear=p1-dx, class dims, z=ground) ===')
    def grp(key):
        g=collections.defaultdict(list)
        for r,b,_ in recs: g[key(r)].append(b)
        return g
    for nm,key in (('by class',lambda r:r['name']),
                   ('by distance',lambda r:int(r['dist'])),
                   ('by speed',lambda r:int(r['vel'])),
                   ('by group',lambda r:r['group']),
                   ('by |human yaw|>0.1',lambda r:'|yaw|>0.1' if abs(r['hyaw'])>0.1 else '|yaw|<=0.1')):
        print(' ',nm)
        for k,v in sorted(grp(key).items()):
            v=np.array(v); print(f'   {str(k):14s} n={len(v):4d} p5={np.percentile(v,5):.3f} p50={np.percentile(v,50):.3f} ge0.7={100*np.mean(v>=0.7):5.1f}% ge0.5={100*np.mean(v>=0.5):5.1f}%')
    # ---------- 5. worst 10 ----------
    print('\n=== [5] worst 10 frames by BEV IoU ===')
    srt=sorted(recs,key=lambda x:x[1])[:10]
    for r,b,d in srt:
        print(f"  {r['scene'][:26]:26s} f{r['frame']:>3.0f} {r['name']:3s} vel={r['vel']:.0f} d={r['dist']:.0f} n1={r['n1']:.0f} n1_kept={r['n1_kept']:.0f} rng={np.linalg.norm([r['hx'],r['hy']]):.1f} yaw={r['hyaw']:+.2f} IoU={b:.2f} 3D={d:.2f} d_centre_x={r['pb']['x']-r['hx']:+.2f}")
    return rows,recs,unb

rows,recs,unb=main()
