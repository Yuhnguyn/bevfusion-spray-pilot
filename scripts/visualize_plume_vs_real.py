"""Clip so sánh **spray thật vs plume do generator sinh** trên cùng một scene SSPP.

Mục đích: cho phép kiểm tra bằng mắt — mỗi frame render 2 panel cạnh nhau từ
**cùng một point cloud**:

* **trái — REAL**: giữ nguyên điểm spray thật (``label == 2``), tô đỏ;
* **phải — GENERATOR**: bỏ điểm spray thật, chèn plume tổng hợp bằng
  ``inject_plume_stateful`` (state giữ qua các frame nên plume trôi/tan như thật),
  tô đỏ.

Khác biệt giữa hai panel đúng bằng phần spray, nên mắt thường so được: mật độ,
kích thước đám, vị trí sau đuôi xe, độ cao, và độ "vón cục" (chuỗi) — chính là
những thứ A3 đang hiệu chỉnh.

Xuất PNG từng frame rồi ghép bằng ``ffmpeg`` thành mp4 (máy này có ffmpeg).

Ví dụ::

    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \\
        scripts/visualize_plume_vs_real.py \\
        --scene Crafter_dynamic/0100_2021-09-08-17-53-31_0 \\
        --frames 50 --out .scratch/plume_vs_real_100kmh.mp4
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from spray.beam_model import BeamTable, ELEVATION_MAX_DEG, ELEVATION_MIN_DEG
from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.sspp_adapter import _boxes_to_arrays, read_frame_boxes

BACKGROUND = 0
VEHICLE = 1
SPRAY = 2


def vlp32c_table() -> BeamTable:
    """Bộ tia VLP-32C (32 ring, bước az 0,2°) — như scripts/visualize_sspp_plume.py."""
    elevation = np.linspace(ELEVATION_MIN_DEG, ELEVATION_MAX_DEG, 32,
                            dtype=np.float64)
    return BeamTable(elevation_deg=tuple(float(v) for v in elevation),
                     azimuth_step_deg=0.2)


def read_metadata_row(scene_dir: Path) -> dict[str, str]:
    with (scene_dir / "metadata.txt").open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))


def load_frame(scene_dir: Path, scan_id: str) -> tuple[np.ndarray, np.ndarray]:
    points = np.fromfile(scene_dir / "velodyne" / f"{scan_id}.bin",
                         dtype=np.float32).reshape(-1, 5)
    labels = np.fromfile(scene_dir / "labels" / f"{scan_id}.label",
                         dtype=np.uint32)
    if labels.size != points.shape[0]:
        labels = np.full(points.shape[0], BACKGROUND, dtype=np.uint32)
    return points, labels


def boxes_for_frame(scene_dir: Path, scan_id: str,
                    speed_mps: float) -> np.ndarray:
    path = scene_dir / "object_labels" / "lidar" / f"{scan_id}.json"
    if not path.is_file():
        return np.zeros((0, 9), dtype=np.float32)
    boxes = read_frame_boxes(path)
    array, _, _ = _boxes_to_arrays(boxes, speed_mps)
    return array


def draw_panel(ax, points: np.ndarray, labels: np.ndarray, spray_mask: np.ndarray,
               boxes: np.ndarray, title: str, subsample: int) -> None:
    """BEV: x dọc (trước), y ngang. Nền xám, xe xanh, spray đỏ."""
    keep = (labels != SPRAY)
    if subsample > 1:
        idx = np.arange(points.shape[0])
        keep &= ((idx % subsample) == 0) | spray_mask
    background = keep & (labels != VEHICLE) & (~spray_mask)
    vehicle = keep & (labels == VEHICLE) & (~spray_mask)
    ax.scatter(points[background, 0], points[background, 1], s=0.35,
               c="#9aa0a6", alpha=0.35, linewidths=0)
    ax.scatter(points[vehicle, 0], points[vehicle, 1], s=1.2,
               c="#1a73e8", alpha=0.9, linewidths=0)
    ax.scatter(points[spray_mask, 0], points[spray_mask, 1], s=2.2,
               c="#d93025", alpha=0.95, linewidths=0)
    for box in boxes[:2]:
        x, y, _, length, width, _, yaw = (float(v) for v in box[:7])
        corners = []
        for dx, dy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
            px = x + dx * length / 2 * np.cos(yaw) - dy * width / 2 * np.sin(yaw)
            py = y + dx * length / 2 * np.sin(yaw) + dy * width / 2 * np.cos(yaw)
            corners.append((px, py))
        corners.append(corners[0])
        ax.plot([c[0] for c in corners], [c[1] for c in corners],
                color="#f9ab00", linewidth=1.2)
    ax.set_xlim(-8, 60)
    ax.set_ylim(-22, 22)
    ax.set_aspect("equal")
    ax.set_facecolor("#111315")
    ax.tick_params(colors="#cccccc", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#444")
    ax.set_title(title, color="#eeeeee", fontsize=9)
    ax.set_xlabel("x dọc (m)", color="#cccccc", fontsize=7)
    ax.set_ylabel("y ngang (m)", color="#cccccc", fontsize=7)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/SemanticSprayDataset")
    parser.add_argument("--scene", required=True)
    parser.add_argument("--frames", type=int, default=50)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--subsample", type=int, default=3)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--out", default=".scratch/plume_vs_real.mp4")
    args = parser.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root = Path(args.root)
    scene_dir = root / args.scene
    if not scene_dir.is_dir():
        raise SystemExit(f"không thấy scene: {scene_dir}")
    metadata = read_metadata_row(scene_dir)
    object_kmh = float(metadata["object_velocity"])
    ego_kmh = float(metadata.get("ego_velocity") or object_kmh)
    speed_mps = object_kmh / 3.6

    scans = sorted(path.stem for path in (scene_dir / "velodyne").glob("*.bin"))
    selected = scans[args.start:args.start + args.frames]
    print(f"scene {args.scene}: {len(scans)} frame, dùng {len(selected)}; "
          f"object {object_kmh:.0f} km/h, ego {ego_kmh:.0f} km/h, "
          f"itr_after_water={metadata.get('itr_after_water')}", flush=True)

    state = PlumeState()
    # wfh cố định 1 mm (itr = 1, mực nước cao nhất của SSPP) để so sánh chéo
    # tốc độ công bằng — không lấy mẫu theo scene (water_film_mm khác None ⇒
    # inject_plume_stateful dùng số đó, log "PLUME_WFH fixed=1").
    config = PlumeConfig(water_film_mm=1.0)
    frames: list[Path] = []
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="plumeviz-"))

    for position, scan_id in enumerate(selected):
        points, labels = load_frame(scene_dir, scan_id)
        boxes = boxes_for_frame(scene_dir, scan_id, speed_mps)
        road_z = (float(np.median(boxes[:, 2])) if len(boxes)
                  else float(np.percentile(points[:, 2], 5)))
        clean = points[labels != SPRAY]
        context = PlumeContext(
            scene_token=args.scene,
            frame_index=position,
            epoch=0,
            sensor_origin=np.zeros(3, dtype=np.float64),
            ego_speed_mps=ego_kmh / 3.6,
            object_speed_mps=speed_mps,
            wfh_mm=1.0,
            road_z_m=road_z,
        )
        result = inject_plume_stateful(
            clean.astype(np.float32), boxes, context, state,
            seed=1000 + position, token=f"viz/{position}", config=config,
        )
        # TẦNG DETECTOR: panel phải vẽ raycast.detections — những gì cảm biến
        # nhìn thấy (tia×mặt cầu + P_det + strongest-per-beam), KHÔNG phải các
        # điểm vật chất hoá ring=-1 vốn vô hiệu với detector
        # (spray/raycast.py:117). Bản cũ vẽ injected => trông "tròn vo" như cụm
        # cứng — đúng cái user bắt được trong clip.
        # Dùng select_alive() như production (spray/plume_transform.py:132), KHÔNG dùng
        # all_alive(): all_alive gồm cả cụm nằm ngoài miền mô hình (min_range 2,5 m /
        # max_range 50 m), nên clip tô hồng phần detections mà training không bao giờ thấy.
        # Đo được: 130 km/h 550 det (all_alive) vs 239 det (select_alive) — lệch 2,3×.
        ray = raycast_frame(
            result.points_clean,
            state.select_alive(),
            table=vlp32c_table(),
            road_z_m=road_z,
            rng=np.random.default_rng(555 + position),
        )
        synthetic = ray.detections

        figure, (left, right) = plt.subplots(
            1, 2, figsize=(13.5, 5.4), facecolor="#ffffff")
        real_spray = labels == SPRAY
        draw_panel(left, points, labels, real_spray, boxes,
                   f"REAL — spray thật ({int(real_spray.sum())} điểm)", args.subsample)
        augmented = np.vstack([clean[:, :3], synthetic[:, :3]])
        augmented_labels = np.concatenate([
            labels[labels != SPRAY],
            np.full(synthetic.shape[0], SPRAY, dtype=labels.dtype),
        ]) if labels.size else np.full(synthetic.shape[0], SPRAY, dtype=np.uint32)
        synthetic_mask = augmented_labels == SPRAY
        draw_panel(right, augmented, augmented_labels, synthetic_mask, boxes,
                   f"GENERATOR — det sau raycast ({int(synthetic.shape[0])} điểm)",
                   args.subsample)
        figure.text(0.5, 0.02,
                    f"{args.scene}  ·  frame {position + 1}/{len(selected)}  ·  "
                    f"{object_kmh:.0f} km/h  ·  đỏ = spray, xanh = xe, xám = nền",
                    ha="center", fontsize=8, color="#333")
        png = tmp_dir / f"frame_{position:04d}.png"
        figure.savefig(png, dpi=110, facecolor=figure.get_facecolor())
        plt.close(figure)
        frames.append(png)
        if position % 10 == 0 or position == len(selected) - 1:
            print(f"  [{position + 1}/{len(selected)}] real spray "
                  f"{int(real_spray.sum()):5d} · sinh {synthetic.shape[0]:5d} điểm "
                  f"· cụm {len(state.all_alive())} (giữ {len(state.select_alive())})",
                  flush=True)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print(f"không có ffmpeg — ảnh PNG nằm ở {tmp_dir}")
        return
    # image2 demuxer (pattern) thay cho concat: concat cần directive `duration`.
    # `scale=trunc(iw/2)*2:...` vì libx264 + yuv420p đòi kích thước CHẴN.
    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-framerate", str(args.fps),
        "-i", str(tmp_dir / "frame_%04d.png"),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
    ]
    subprocess.run(command, check=True)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"xong: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
