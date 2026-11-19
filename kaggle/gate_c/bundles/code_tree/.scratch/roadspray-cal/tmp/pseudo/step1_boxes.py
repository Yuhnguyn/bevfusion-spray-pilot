import os, glob, json, csv, collections
import numpy as np
root='data/SemanticSprayDataset'
rows=[]; meta={}
for cls in ['Crafter_dynamic','Golf_dynamic']:
    for s in sorted(os.listdir(f'{root}/{cls}')):
        d=f'{root}/{cls}/{s}'
        if not os.path.isdir(d): continue
        m=open(f'{d}/metadata.txt').read().splitlines()
        hdr=m[0].split(','); vals=m[1].split(',')
        meta[(cls,s)]=dict(zip(hdr,vals))
        if not os.path.isdir(f'{d}/object_labels/lidar'): continue
        for p in glob.glob(f'{d}/object_labels/lidar/*.json'):
            frame=int(os.path.basename(p)[:-5])
            d0=json.load(open(p))
            for obj in d0:
                for inst in obj.get('instances',[]):
                    c=inst['contour']
                    rows.append(dict(cls=cls,scene=s,frame=frame,clsname=inst.get('className'),
                        cx=c['center3D']['x'],cy=c['center3D']['y'],cz=c['center3D']['z'],
                        yaw=c['rotation3D']['z'],sx=c['size3D']['x'],sy=c['size3D']['y'],sz=c['size3D']['z'],
                        pointN=c.get('pointN'),
                        objname=meta[(cls,s)]['object_name'],vel=float(meta[(cls,s)]['object_velocity']),
                        ego=float(meta[(cls,s)]['ego_velocity']),dist=float(meta[(cls,s)]['distance_to_object'])))
print('total boxes', len(rows), 'from scenes', len(set(r['scene'] for r in rows)))
def pct(a):
    a=np.asarray(a,float); return f"n={len(a)} p5={np.percentile(a,5):.3f} p50={np.percentile(a,50):.3f} p95={np.percentile(a,95):.3f} mean={a.mean():.3f} sd={a.std():.3f}"
print('\n=== className vs object_name ===')
print(collections.Counter((r['clsname'],r['objname']) for r in rows))
print('\n=== dims per class ===')
for cn in sorted(set(r['clsname'] for r in rows)):
    sub=[r for r in rows if r['clsname']==cn]
    print(cn, 'n=',len(sub))
    for k in ['sx','sy','sz']:
        print('  ',k,pct([r[k] for r in sub]))
print('\n=== yaw / zbottom / cy ===')
print('yaw', pct([r['yaw'] for r in rows]))
print('|yaw|>0.1:', sum(1 for r in rows if abs(r['yaw'])>0.1))
print('zbottom', pct([r['cz']-r['sz']/2 for r in rows]))
print('cy', pct([r['cy'] for r in rows]))
print('\n=== distance_to_object <> centre relationship, per class ===')
for cn in sorted(set(r['clsname'] for r in rows)):
    sub=[r for r in rows if r['clsname']==cn]
    cx=np.array([r['cx'] for r in sub]); dist=np.array([r['dist'] for r in sub])
    sx=np.array([r['sx'] for r in sub])
    print(cn, 'n=',len(sub))
    print('  dist-centre_x     ', pct(dist-cx))
    print('  dist-front_face_x ', pct(dist-(cx-sx/2)))
    print('  dist-rear_face_x  ', pct(dist-(cx+sx/2)))
print('\n=== within-scene centre-x variation (is distance constant?) ===')
by=collections.defaultdict(list)
for r in rows: by[(r['cls'],r['scene'])].append(r['cx'])
sd=[np.std(v) for v in by.values()]
rng=[max(v)-min(v) for v in by.values()]
print('scenes',len(by),'within-scene std cx:',pct(sd))
print('within-scene range cx:',pct(rng), 'max range', max(rng))
print('\n=== dist / vel combos ===')
print(collections.Counter((r['clsname'],r['dist'],r['vel']) for r in rows))
# save csv for reuse
with open('.scratch/roadspray-cal/tmp/boxes.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
