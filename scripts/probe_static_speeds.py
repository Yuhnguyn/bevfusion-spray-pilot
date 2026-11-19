"""Đo vận tốc xe đối tượng trong các bag `Crafter_static`.

Mục đích: `static` là calibration set của Paper A. Paper A hiệu chuẩn theo tốc độ
50-130 km/h. Không có metadata.txt trong RoadSpray, nên phải suy tốc độ bằng cách
track object từ `/front_ibeo_lux/as_tx/objects` (MarkerArray, có id ổn định).

Cách đo: với mỗi id xuất hiện >= 20 lần, tính tốc độ từ delta vị trí / delta thời gian,
lấy median. Báo cáo phân bố tốc độ trên các bag mẫu.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore

ZIP = Path.home() / ".hermes/cache/scratch/roadspray/Crafter_static.zip"
TOPIC = "/front_ibeo_lux/as_tx/objects"


def bag_names() -> list[str]:
    out = subprocess.run(
        ["unzip", "-l", str(ZIP)], capture_output=True, text=True, check=True
    ).stdout
    names = []
    for line in out.splitlines():
        if line.strip().endswith(".bag"):
            names.append(line.split()[-1])
    return sorted(names)


def object_speeds(bag: Path) -> tuple[np.ndarray, float]:
    ts = get_typestore(Stores.ROS1_NOETIC)
    tracks: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    with Reader(bag) as reader:
        conns = [c for c in reader.connections if c.topic == TOPIC]
        if not conns:
            return np.array([]), 0.0
        for conn, stamp, raw in reader.messages(connections=conns):
            msg = ts.deserialize_ros1(raw, conn.msgtype)
            t = stamp / 1e9
            for mk in msg.markers:
                p = mk.pose.position
                tracks[mk.id].append((t, p.x, p.y))
    speeds = []
    for _oid, pts in tracks.items():
        if len(pts) < 20:
            continue
        arr = np.asarray(pts, dtype=float)
        dt = np.diff(arr[:, 0])
        ok = dt > 1e-3
        if ok.sum() < 10:
            continue
        d = np.hypot(np.diff(arr[:, 1]), np.diff(arr[:, 2]))[ok]
        v = d / dt[ok] * 3.6
        v = v[(v > 1.0) & (v < 200.0)]
        if len(v) >= 10:
            speeds.append(float(np.median(v)))
    return np.asarray(speeds), float(len(tracks))


def main() -> None:
    names = bag_names()
    print(f"STATIC_BAGS total={len(names)}")
    if not names:
        return

    # lấy mẫu trải đều
    idx = np.linspace(0, len(names) - 1, min(10, len(names))).astype(int)
    sample = [names[i] for i in sorted(set(idx))]

    all_speeds: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for name in sample:
            subprocess.run(
                ["unzip", "-o", "-j", str(ZIP), name, "-d", str(tmpdir)],
                capture_output=True, check=True,
            )
            bag = tmpdir / Path(name).name
            speeds, n_tracks = object_speeds(bag)
            bag.unlink(missing_ok=True)
            short = Path(name).stem.replace("_0", "")
            if len(speeds) == 0:
                print(f"  {short}: 0 object đủ dài ({n_tracks:.0f} track)")
                continue
            all_speeds.extend(speeds.tolist())
            print(f"  {short}: {len(speeds):2d} object, "
                  f"v median={np.median(speeds):5.1f} "
                  f"range={speeds.min():5.1f}..{speeds.max():5.1f} km/h")

    if all_speeds:
        a = np.asarray(all_speeds)
        print()
        print(f"STATIC_SPEED_SAMPLE n={len(a)}")
        print(f"  p5={np.percentile(a,5):.1f} p25={np.percentile(a,25):.1f} "
              f"p50={np.median(a):.1f} p75={np.percentile(a,75):.1f} "
              f"p95={np.percentile(a,95):.1f} max={a.max():.1f} km/h")
        bins = [(40, 60), (60, 80), (80, 100), (100, 120), (120, 140)]
        print("  phân bố theo dải:")
        for lo, hi in bins:
            n = int(((a >= lo) & (a < hi)).sum())
            print(f"    {lo:3d}-{hi:3d} km/h: {n:3d} object "
                  f"({100.0 * n / len(a):4.1f}%)")
    print("\nSTATIC_SPEED_OK")


if __name__ == "__main__":
    sys.exit(main())
