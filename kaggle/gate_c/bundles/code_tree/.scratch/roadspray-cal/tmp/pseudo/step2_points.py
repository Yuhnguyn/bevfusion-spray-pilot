"""Pass 1: per-frame characterisation of label==1 points vs the human box (36 boxed scenes)."""
import sys, os, glob, csv, numpy as np
sys.path.insert(0,'.scratch/roadspray-cal/tmp')
import lib

def robust_ext(x, lo=1.0, hi=99.0):
    return np.percentile(x,lo), np.percentile(x,hi)

def main():
    scenes=lib.discover()
    boxed=[s for s in scenes if s['n_box_json']>0]
    out=[]
    for s in boxed:
        js=sorted(glob.glob(f"{s['dir']}/object_labels/lidar/*.json"))
        for jp in js:
            sid=os.path.basename(jp)[:-5]
            boxes=lib.read_frame_boxes(jp)
            if not boxes: continue
            b=boxes[0]
            pts=lib.load_points(s['dir'],sid); lbl=lib.load_labels(s['dir'],sid)
            m=lbl==1; n1=int(m.sum())
            p=pts[m,:3]
            rec=dict(scene=s['rel'],group=s['group'],frame=int(sid),name=b['name'],n1=n1,
                     n2=int((lbl==2).sum()),n_tot=int(len(lbl)),
                     x=b['x'],y=b['y'],zb=b['z_bottom'],sx=b['size_x'],sy=b['size_y'],sz=b['size_z'],yaw=b['yaw'],
                     dist=float(s['meta']['distance_to_object']),vel=float(s['meta']['object_velocity']),
                     itr=s['meta'].get('itr_after_water'))
            if n1==0:
                out.append(rec); continue
            # --- yaw estimated from the points alone: PCA on BEV, major axis = box lateral axis
            xy=p[:,:2]; c=xy.mean(0); cov=np.cov((xy-c).T); w,V=np.linalg.eigh(cov)
            major=V[:,np.argmax(w)]                     # direction of largest spread
            yaw_pca=np.arctan2(major[1],major[0]) - np.pi/2
            # wrap to (-pi/2, pi/2]
            yaw_pca=(yaw_pca+np.pi/2)%np.pi-np.pi/2
            for tag,yaw in (('pca',yaw_pca),('zero',0.0)):
                u,v=lib.to_box_frame(p,b) if tag=='zero' else _box_frame_yaw(p,b['x'],b['y'],yaw)
                rec[f'umin_{tag}']=float(u.min()); rec[f'umax_{tag}']=float(u.max())
                rec[f'u1_{tag}'],rec[f'u99_{tag}']=robust_ext(u)
                rec[f'v1_{tag}'],rec[f'v99_{tag}']=robust_ext(v)
                rec[f'vmed_{tag}']=float(np.median(v))
                rec[f'u50_{tag}']=float(np.median(u))
            # offsets vs human box in HUMAN box frame
            u,v=lib.to_box_frame(p,b)
            rec['u_min']=float(u.min()); rec['u_p1']=float(np.percentile(u,1)); rec['u_p2']=float(np.percentile(u,2))
            rec['u_max']=float(u.max()); rec['u_p99']=float(np.percentile(u,99)); rec['u_p98']=float(np.percentile(u,98))
            rec['v_min']=float(v.min()); rec['v_max']=float(v.max())
            rec['v_p1']=float(np.percentile(v,1)); rec['v_p99']=float(np.percentile(v,99))
            rec['v_med']=float(np.median(v)); rec['v_std']=float(v.std())
            rec['z_min']=float(p[:,2].min()); rec['z_p1']=float(np.percentile(p[:,2],1))
            rec['z_med']=float(np.median(p[:,2])); rec['z_max']=float(p[:,2].max())
            rec['inside_bev']=float(np.mean((np.abs(u)<=b['size_x']/2)&(np.abs(v)<=b['size_y']/2)))
            rec['inside3d']=float(np.mean((np.abs(u)<=b['size_x']/2)&(np.abs(v)<=b['size_y']/2)
                                          &(p[:,2]>=b['z_bottom'])&(p[:,2]<=b['z_bottom']+b['size_z'])))
            rec['rear_face_frac']=float(np.mean(np.abs(u+b['size_x']/2)<0.10))
            rec['side_frac']=float(np.mean(np.abs(np.abs(v)-b['size_y']/2)<0.10))
            rec['rng_med']=float(np.median(np.linalg.norm(p[:,:2],axis=1)))
            rec['yaw_pca']=float(yaw_pca)
            out.append(rec)
    keys=sorted({k for r in out for k in r})
    with open('.scratch/roadspray-cal/tmp/frames_boxes.csv','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
        for r in out: w.writerow({k:r.get(k,'') for k in keys})
    print('frames written',len(out))

def _box_frame_yaw(p,cx,cy,yaw):
    c,s=np.cos(yaw),np.sin(yaw); dx=p[:,0]-cx; dy=p[:,1]-cy
    return c*dx+s*dy, -s*dx+c*dy

main()
