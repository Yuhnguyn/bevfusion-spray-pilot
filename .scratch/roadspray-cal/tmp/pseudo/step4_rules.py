"""Offline rule search + validation on the 36 boxed scenes (features.csv)."""
import csv, sys, collections
import numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp/pseudo')
import lib

FEATS='.scratch/roadspray-cal/tmp/pseudo/features.csv'
NAN=float('nan')
def fnum(v):
    try: return float(v)
    except: return NAN

def load():
    rs=list(csv.DictReader(open(FEATS)))
    out=[]
    for r in rs:
        d={k:fnum(v) for k,v in r.items() if k not in ('scene','group','name','itr')}
        d['scene']=r['scene']; d['group']=r['group']; d['name']=r['name']
        d['x_p']=[fnum(r[f'x_p{i}']) for i in range(9)]
        d['y_p']=[fnum(r[f'y_p{i}']) for i in range(9)]
        d['z_p']=[fnum(r[f'z_p{i}']) for i in range(9)]
        d['hbox']=dict(x=d['hx'],y=d['hy'],z_bottom=d['hzb'],size_x=d['hsx'],size_y=d['hsy'],size_z=d['hsz'],yaw=d['hyaw'])
        out.append(d)
    return out

def fit(rows):
    """Campaign constants from boxed frames: class dims, rear-face fiducial delta, z bottom, ground offset."""
    c={}
    for name in ('Car','Van'):
        sub=[r for r in rows if r['name']==name]
        dims=(float(np.median([r['hsx'] for r in sub])),float(np.median([r['hsy'] for r in sub])),float(np.median([r['hsz'] for r in sub])))
        # fiducial: how far inside the human rear face the robust point boundary (x_p1) sits
        dx=float(np.median([r['x_p'][1]-(r['hx']-r['hsx']/2) for r in sub]))
        zb=float(np.median([r['hzb'] for r in sub]))
        zg=float(np.median([r['hzb']-r['g_z0'] for r in sub if np.isfinite(r['g_z0'])]))
        dy=float(np.median([r['hy']-r['y_p'][4] for r in sub]))
        c[name]=dict(dims=dims,dx=dx,zb=zb,zg=zg,dy=dy)
    return c

def pseudo(r,c,yaw_mode='zero',xpct=1,cy_mode='median',z_mode='const',x_mode='points'):
    cls=r['name']; sx,sy,sz=c[cls]['dims']
    if x_mode=='points':
        rear=r['x_p'][xpct]-c[cls]['dx']
    elif x_mode=='points_p0':
        rear=r['x_p'][0]-c[cls]['dx']
    elif x_mode=='meta':
        rear=r['dist']-0.20
    cx=rear+sx/2.0
    cy=(r['y_p'][4]+c[cls]['dy']) if cy_mode=='median' else r['hy']+c[cls]['dy']
    if yaw_mode=='zero': yaw=0.0
    elif yaw_mode=='pca': yaw=r['yaw_pca'] if np.isfinite(r['yaw_pca']) else 0.0
    elif yaw_mode=='rearfit': yaw=r['yaw_rearfit'] if np.isfinite(r['yaw_rearfit']) else 0.0
    elif yaw_mode=='human': yaw=r['hyaw']
    if z_mode=='const': zb=c[cls]['zb']
    elif z_mode=='ground': zb=r['g_z0']+c[cls]['zg']
    elif z_mode=='human': zb=r['hzb']
    return dict(x=cx,y=cy,z_bottom=zb,size_x=sx,size_y=sy,size_z=sz,yaw=yaw)

def evaluate(rows,cfg,label):
    ious=[]
    for r in rows:
        pb=pseudo(r,cfg[0],**cfg[1])
        ious.append((r,lib.bev_iou(pb,r['hbox']),lib.iou_3d(pb,r['hbox']),pb))
    return ious

def rep(name,ious,key=1):
    a=np.array([x[key] for x in ious])
    print(f"{name:44s} n={len(a):4d} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} p95={np.percentile(a,95):.3f} mean={a.mean():.3f} "
          f"ge0.7={100*(a>=0.7).mean():5.1f}% ge0.5={100*(a>=0.5).mean():5.1f}% lt0.3={100*(a<0.3).mean():4.1f}%")

def main():
    rows=load()
    print('frames',len(rows))
    cfg=fit(rows); 
    print('\n=== fitted campaign constants (all 36 scenes) ===')
    for k,v in cfg.items(): print(k,v)
    print('\n=== BEV IoU by rule ===')
    for ious,yaw,xpct,zm in [
        (None,'zero',1,'const'),(None,'pca',1,'const'),(None,'rearfit',1,'const'),
        (None,'zero',0,'const'),(None,'zero',2,'const'),
        (None,'zero',1,'ground'),(None,'zero',1,'human'),(None,'human',1,'const'),
        (None,'human',1,'human'),
    ]:
        ious=evaluate(rows,(cfg,dict(yaw_mode=yaw,xpct=xpct,z_mode=zm)),f'{yaw}/{xpct}/{zm}')
        rep(f'yaw={yaw} x_p{xpct} z={zm}',ious)
    print('\n=== 3D IoU by z rule (yaw=zero, x_p1) ===')
    for zm in ('const','ground','human'):
        ious=evaluate(rows,(cfg,dict(yaw_mode='zero',xpct=1,z_mode=zm)),zm)
        rep(f'3D IoU z={zm}',ious,key=2)
    print('\n=== metadata-only baseline (place box at distance_to_object) ===')
    ious=evaluate(rows,(cfg,dict(yaw_mode='zero',xpct=1,z_mode='const',x_mode='meta')),'meta')
    rep('meta-only x',ious)
    print('\n=== diagnostic: tight-fit from points (no class prior) ===')
    tight=[]
    for r in rows:
        sx=r['x_p'][7]-r['x_p'][1]; sy=r['y_p'][7]-r['y_p'][1]
        pb=dict(x=(r['x_p'][7]+r['x_p'][1])/2,y=(r['y_p'][7]+r['y_p'][1])/2,z_bottom=r['hzb'],
                size_x=sx,size_y=sy,size_z=r['hsz'],yaw=0.0)
        tight.append((r,lib.bev_iou(pb,r['hbox']),lib.iou_3d(pb,r['hbox']),pb))
    rep('tight-fit points',tight)
    print('tight dims: sx p5/50/95',np.round(np.percentile([np.float64(p[3]["size_x"]) for p in tight],[5,50,95]),2),
          'sy',np.round(np.percentile([np.float64(p[3]["size_y"]) for p in tight],[5,50,95]),2))

main()
