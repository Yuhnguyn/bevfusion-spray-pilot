"""Count-only probe: topics + velodyne msgcount + duration, no point decoding."""
import json, shutil, sys, time, zipfile
from pathlib import Path
TMP = Path(".scratch/roadspray-fit/tmp")
zip_path, member = sys.argv[1], sys.argv[2]
row = {"member": Path(member).name}
t0 = time.time()
dest = TMP / row["member"]
with zipfile.ZipFile(zip_path) as zf:
    info = zf.getinfo(member)
    with zf.open(info) as src, open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 22)
t1 = time.time()
from rosbags.rosbag1 import Reader
with Reader(dest) as rd:
    t2 = time.time()
    row.update({"mb": round(info.file_size/1e6, 1),
                "duration_s": round((rd.end_time-rd.start_time)/1e9, 2),
                "velodyne": next((c.msgcount for c in rd.connections if c.topic == "/velodyne_points"), 0),
                "topics": len(rd.connections),
                "img": next((c.msgcount for c in rd.connections if c.topic == "/front_mono/image/compressed"), 0),
                "extract_s": round(t1-t0, 2), "open_s": round(time.time()-t2, 2)})
dest.unlink(missing_ok=True)
print(json.dumps(row))
