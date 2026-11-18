"""Probe one .bag from a RoadSpray zip without extracting the whole zip.

usage: probe.py <zip> <member> [--decode]
Streams exactly one member to .scratch/roadspray-fit/tmp/, reads it with
rosbags.rosbag1.Reader, prints JSON facts, then deletes the temp bag.
"""
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

TMP = Path(".scratch/roadspray-fit/tmp")
sys.path.insert(0, "/opt/anaconda3/lib/python3.12/site-packages")

zip_path, member = sys.argv[1], sys.argv[2]
do_decode = "--decode" in sys.argv
out = {"zip": zip_path, "member": member}

t0 = time.time()
dest = TMP / Path(member).name
with zipfile.ZipFile(zip_path) as zf:
    info = zf.getinfo(member)
    with zf.open(info) as src, open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 22)
out["extract_s"] = round(time.time() - t0, 2)
out["bag_mb"] = round(info.file_size / 1e6, 1)
out["zip_mb"] = round(info.compress_size / 1e6, 1)

from rosbags.rosbag1 import Reader  # noqa: E402

t1 = time.time()
with Reader(dest) as rd:
    out["open_s"] = None
    out["duration_s"] = round((rd.end_time - rd.start_time) / 1e9, 2)
    out["start"] = float(rd.start_time) / 1e9
    out["end"] = float(rd.end_time) / 1e9
    conns = list(rd.connections)
    out["topics"] = {
        c.topic: {"type": c.msgtype, "count": c.msgcount, "msgdef_name": c.msgdef.format.value if hasattr(c.msgdef.format, "value") else str(c.msgdef.format),
                  "msgdef_len": len(c.msgdef.data or "")}
        for c in sorted(conns, key=lambda c: c.topic)
    }
    out["open_s"] = round(time.time() - t1, 2)

    vel = [c for c in conns if c.topic == "/velodyne_points"]
    out["velodyne_count"] = vel[0].msgcount if vel else 0
    if do_decode and conns:
        from rosbags.typesys import Stores, get_types_from_msg, get_typestore

        ts = get_typestore(Stores.ROS1_NOETIC)
        # register custom types straight from the bag's own msgdefs
        for c in conns:
            if c.msgtype not in ts.types:
                try:
                    for name, cls in get_types_from_msg(c.msgdef.data, c.msgtype).items():
                        ts.register(cls)
                except Exception as exc:  # pragma: no cover
                    out.setdefault("register_fail", {})[c.msgtype] = str(exc)[:120]
        dec = {}
        want = ("/velodyne_points", "/adma")
        t2 = time.time()
        seen = set()
        n_deser = 0
        for conn, tstamp, raw in rd.messages():
            if conn.topic not in want:
                continue
            try:
                msg = ts.deserialize_ros1(raw, conn.msgtype)
                n_deser += 1
            except Exception as exc:
                dec.setdefault("deser_fail", {})[conn.topic] = str(exc)[:200]
                continue
            if conn.topic == "/velodyne_points" and "pc" not in dec:
                dec["pc"] = {
                    "fields": [(f.name, f.offset, f.datatype, f.count) for f in msg.fields],
                    "height": int(msg.height), "width": int(msg.width),
                    "point_step": int(msg.point_step), "row_step": int(msg.row_step),
                    "n_data_bytes": len(msg.data), "is_bigendian": bool(msg.is_bigendian),
                    "is_dense": bool(msg.is_dense),
                }
                import numpy as np

                arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
                rec = np.lib.stride_tricks.as_strided(
                    arr, shape=(int(msg.width), int(msg.point_step)),
                    strides=(int(msg.point_step), 1))
                for f in msg.fields:
                    col = rec[:, f.offset:f.offset + 32 * f.count if f.count > 1 else f.offset + 32]
                    vals = col[:, :4].copy().view(np.float32).ravel() if f.datatype == 7 else None
                    dec.setdefault("field_stats", {})[f.name] = {
                        "dtype": int(f.datatype),
                        "min": float(np.nanmin(vals)) if vals is not None else None,
                        "max": float(np.nanmax(vals)) if vals is not None else None,
                        "mean": float(np.nanmean(vals)) if vals is not None else None,
                    }
            if conn.topic == "/adma":
                dec.setdefault("adma_examples", []).append(
                    {k: (list(v) if hasattr(v, "__len__") and not isinstance(v, (str, bytes)) else float(v))
                     for k, v in vars(msg).items() if isinstance(v, (int, float, list, tuple))})
                if len(dec["adma_examples"]) >= 2:
                    dec["adma_examples"] = dec["adma_examples"][:2]
            seen.add(conn.topic)
            if "pc" in dec and ("/adma" not in want or "adma_examples" in dec):
                break
            if time.time() - t2 > 120:
                break
        dec["deser_count"] = n_deser
        dec["decode_s"] = round(time.time() - t2, 2)
        out["decode"] = dec

dest.unlink(missing_ok=True)
out["total_s"] = round(time.time() - t0, 2)
out["tmp_cleaned"] = not dest.exists()
print(json.dumps(out, indent=1))
