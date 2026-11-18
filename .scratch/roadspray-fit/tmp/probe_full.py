"""Full probe of one bag: velodyne per-frame stats + ego velocity from /adma/twist.

usage: probe_full.py <zip> <member> <out.json>
"""
import json
import shutil
import statistics
import sys
import time
import zipfile
from pathlib import Path

TMP = Path(".scratch/roadspray-fit/tmp")
zip_path, member, outpath = sys.argv[1], sys.argv[2], sys.argv[3]
out = {"zip": zip_path, "member": member}

t0 = time.time()
dest = TMP / Path(member).name
with zipfile.ZipFile(zip_path) as zf:
    info = zf.getinfo(member)
    with zf.open(info) as src, open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 22)
out["extract_s"] = round(time.time() - t0, 2)
out["bag_mb"] = round(info.file_size / 1e6, 1)

import numpy as np  # noqa: E402
from rosbags.rosbag1 import Reader  # noqa: E402
from rosbags.typesys import Stores, get_typestore  # noqa: E402

ts = get_typestore(Stores.ROS1_NOETIC)
t1 = time.time()
frames = []
twist = []
decoded_bytes = 0
with Reader(dest) as rd:
    out["duration_s"] = round((rd.end_time - rd.start_time) / 1e9, 2)
    out["n_connections"] = len(rd.connections)
    out["topics"] = sorted(c.topic for c in rd.connections)
    out["counts"] = {c.topic: c.msgcount for c in rd.connections}
    vel = [c for c in rd.connections if c.topic == "/velodyne_points"]
    tw = [c for c in rd.connections if c.topic == "/adma/twist"]
    t_v = time.time()
    for conn, tstamp, raw in rd.messages(vel):
        msg = ts.deserialize_ros1(raw, conn.msgtype)
        data = bytes(msg.data)
        decoded_bytes += len(data)
        step = int(msg.point_step)
        arr = np.frombuffer(data, dtype=np.uint8).reshape(-1, step)
        f32 = np.ascontiguousarray(arr[:, 0:12]).view(np.float32).reshape(-1, 3)
        inten = np.ascontiguousarray(arr[:, 16:20]).view(np.float32).ravel()
        ring = np.ascontiguousarray(arr[:, 20:22]).view(np.uint16).ravel()
        frames.append({
            "t": round((tstamp - rd.start_time) / 1e9, 3),
            "n": len(inten),
            "i_mean": round(float(inten.mean()), 2),
            "i_max": int(inten.max()),
            "x_absmax": round(float(np.abs(f32[:, 0]).max()), 2),
            "ring_max": int(ring.max()),
            "n_ring": int(len(np.unique(ring))),
        })
    out["velodyne_read_s"] = round(time.time() - t_v, 2)
    out["decoded_MB"] = round(decoded_bytes / 1e6, 1)
    if tw:
        t_a = time.time()
        for conn, tstamp, raw in rd.messages(tw):
            msg = ts.deserialize_ros1(raw, conn.msgtype)
            twist.append({
                "t": round((tstamp - rd.start_time) / 1e9, 3),
                "vx": round(float(msg.twist.linear.x), 3),
                "vy": round(float(msg.twist.linear.y), 3),
                "wz": round(float(msg.twist.angular.z), 4),
            })
        out["twist_read_s"] = round(time.time() - t_a, 2)
out["open_total_s"] = round(time.time() - t1, 2)
out["velodyne_frames"] = frames
out["velodyne_n_frames"] = len(frames)
if frames:
    span = frames[-1]["t"] - frames[0]["t"]
    out["velodyne_span_s"] = round(span, 3)
    out["velodyne_hz"] = round((len(frames) - 1) / span, 2) if span > 0 else None
out["twist"] = twist
if twist:
    speeds = [abs(x["vx"]) for x in twist]
    out["speed_mps"] = {"median": round(statistics.median(speeds), 3),
                        "mean": round(statistics.mean(speeds), 3),
                        "p10": round(float(np.percentile(speeds, 10)), 3),
                        "p90": round(float(np.percentile(speeds, 90)), 3),
                        "min": round(min(speeds), 3), "max": round(max(speeds), 3),
                        "kmh_median": round(statistics.median(speeds) * 3.6, 1)}

dest.unlink(missing_ok=True)
out["total_s"] = round(time.time() - t0, 2)
Path(outpath).write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k not in ("velodyne_frames", "twist")}, indent=1))
print("frames:", len(frames), "twist:", len(twist), "-> wrote", outpath)
