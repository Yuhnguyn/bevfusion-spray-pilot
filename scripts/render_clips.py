#!/usr/bin/env python3
"""Render the real-spray clip, the clean/plume flicker clip, and index.html.

Outputs (``docs/figs/plume``):

* ``clip-a-real-spray.mp4``  76 real SemanticSpray frames, spray red, fixed axes;
* ``clip-c-flicker.mp4``     clean <-> with plume, 2 Hz, 12 frames;
* ``index.html``             self-contained page embedding stills and clips.

Run with the isolated viz env::

    ~/.venvs/viz/bin/python scripts/render_clips.py

The generator is frame-independent, so clip C is expected to flicker; the
script never interpolates between frames.
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from scripts.visualize_plume import (  # noqa: E402
    BOX_COLOR,
    CLEAN_COLOR,
    CLEAN_SIZE,
    EGO_COLOR,
    FIG_DIR,
    PLUME_COLOR,
    PLUME_SIZE,
    _style_axes,
    draw_box,
    draw_ego,
    make_box,
    spawn_counts,
    synthetic_clean,
)
from spray.spray_stats import NOISE_LABEL, load_scan  # noqa: E402
from scripts.semantic_spray_stats import scene_dirs  # noqa: E402

CLIP_A_FPS = 10
CLIP_C_FPS = 2
CLIP_C_CYCLES = 6
CLIP_C_EXTRA_PNGS = ("clip-c-clean.png", "clip-c-with-plume.png")
CLIP_A_KEEP_FRAMES = (0, 19, 38, 57, 75)


def scan_ids(scene: str) -> list[str]:
    return sorted(
        name[: -len(".bin")]
        for name in os.listdir(os.path.join(scene, "velodyne"))
        if name.endswith(".bin")
    )


def select_sequence(root: str) -> str:
    """First Crafter_dynamic sequence with at least 60 labelled frames."""
    for scene in scene_dirs(root, ["Crafter_dynamic"]):
        if len(scan_ids(scene)) >= 60:
            return scene
    raise SystemExit("no Crafter_dynamic sequence with >= 60 frames found")


def read_object_velocity(scene: str) -> float:
    lines = (
        open(os.path.join(scene, "metadata.txt"), encoding="utf-8")
        .read()
        .strip()
        .splitlines()
    )
    return float(dict(zip(lines[0].split(","), lines[1].split(",")))["object_velocity"])


def fixed_spray_extent(scene: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """One fixed window for the whole clip, from every spray point of every frame."""
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for scan_id in scan_ids(scene):
        points, labels = load_scan(scene, scan_id)
        spray = points[labels == NOISE_LABEL]
        xs.append(spray[:, 0])
        ys.append(spray[:, 1])
    ax = np.concatenate(xs)
    ay = np.concatenate(ys)
    pad = 3.0
    return (
        (float(np.percentile(ax, 0.5)) - pad, float(np.percentile(ax, 99.5)) + pad),
        (float(np.percentile(ay, 0.5)) - pad, float(np.percentile(ay, 99.5)) + pad),
    )


def render_clip_a(scene: str, out: str, work_dir: str) -> dict:
    xlim, ylim = fixed_spray_extent(scene)
    ids = scan_ids(scene)
    frame_dir = os.path.join(work_dir, "clip_a")
    os.makedirs(frame_dir, exist_ok=True)
    spray_counts: list[int] = []
    width = 11.0
    height = width * (ylim[1] - ylim[0]) / (xlim[1] - xlim[0]) + 0.9

    for index, scan_id in enumerate(ids):
        points, labels = load_scan(scene, scan_id)
        spray = labels == NOISE_LABEL
        spray_counts.append(int(spray.sum()))

        fig, ax = plt.subplots(figsize=(width, height))
        _style_axes(ax)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.scatter(
            points[~spray, 0],
            points[~spray, 1],
            s=CLEAN_SIZE,
            c=CLEAN_COLOR,
            linewidths=0,
            rasterized=True,
        )
        ax.scatter(
            points[spray, 0],
            points[spray, 1],
            s=7.0,
            c=PLUME_COLOR,
            linewidths=0,
        )
        draw_ego(ax)
        ax.set_title(
            f"real SemanticSpray (VLP-32C) — frame {index:03d}/{len(ids) - 1}  "
            f"spray points: {spray_counts[-1]}  |  fixed axes",
            fontsize=11,
        )
        fig.tight_layout()
        fig.savefig(
            os.path.join(frame_dir, f"frame_{index:03d}.png"),
            dpi=110,
            facecolor="white",
        )
        plt.close(fig)

    target = os.path.join(out, "clip-a-real-spray.mp4")
    encode(frame_dir, target, CLIP_A_FPS)
    for index in CLIP_A_KEEP_FRAMES:
        source = os.path.join(frame_dir, f"frame_{index:03d}.png")
        shutil.copyfile(
            source, os.path.join(out, f"clip-a-frame-{index:03d}.png")
        )
    return {
        "sequence": os.path.relpath(scene, REPO),
        "group": os.path.basename(os.path.dirname(scene)),
        "frames": len(ids),
        "duration_s": len(ids) / CLIP_A_FPS,
        "xlim": xlim,
        "ylim": ylim,
        "spray_min": int(min(spray_counts)),
        "spray_median": float(np.median(spray_counts)),
        "spray_max": int(max(spray_counts)),
        "velocity_kmh": read_object_velocity(scene),
    }


def render_clip_c(out: str, work_dir: str) -> dict:
    clean = synthetic_clean()
    box = make_box(22.0, 0.0, 72.0)
    result, _ = spawn_counts(clean, box, seed=0)

    frame_dir = os.path.join(work_dir, "clip_c")
    os.makedirs(frame_dir, exist_ok=True)
    xlim = (-10.0, 45.0)
    ylim = (-15.0, 15.0)
    frame_index = 0

    for cycle in range(CLIP_C_CYCLES):
        for with_plume in (False, True):
            fig, ax = plt.subplots(figsize=(11, 6.2))
            _style_axes(ax)
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            ax.scatter(
                result.points_clean[:, 0],
                result.points_clean[:, 1],
                s=CLEAN_SIZE,
                c=CLEAN_COLOR,
                linewidths=0,
                zorder=1,
            )
            if with_plume:
                ax.scatter(
                    result.injected[:, 0],
                    result.injected[:, 1],
                    s=PLUME_SIZE,
                    c=PLUME_COLOR,
                    linewidths=0,
                    zorder=4,
                )
            draw_box(ax, box)
            draw_ego(ax)
            label = "with plume (seed 0)" if with_plume else "clean"
            ax.text(
                0.02,
                0.97,
                label,
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=15,
                fontweight="bold",
                color=PLUME_COLOR if with_plume else EGO_COLOR,
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.9, edgecolor="#d0d4d9"),
            )
            ax.text(
                0.98,
                0.03,
                "generator is frame-independent: no temporal state",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=9,
                color="#555a60",
            )
            ax.set_title(
                f"flicker A/B — cycle {cycle + 1}/{CLIP_C_CYCLES} at {CLIP_C_FPS} Hz",
                fontsize=11,
            )
            fig.tight_layout()
            fig.savefig(
                os.path.join(frame_dir, f"frame_{frame_index:03d}.png"),
                dpi=110,
                facecolor="white",
            )
            plt.close(fig)
            if frame_index < 2:
                name = "clip-c-with-plume.png" if with_plume else "clip-c-clean.png"
                shutil.copyfile(
                    os.path.join(frame_dir, f"frame_{frame_index:03d}.png"),
                    os.path.join(out, name),
                )
            frame_index += 1

    target = os.path.join(out, "clip-c-flicker.mp4")
    encode(frame_dir, target, CLIP_C_FPS)
    return {
        "frames": frame_index,
        "duration_s": frame_index / CLIP_C_FPS,
        "fps": CLIP_C_FPS,
        "plume_points": int(result.stats.injected),
        "clusters": int(result.stats.clusters),
    }


def encode(frame_dir: str, target: str, fps: int) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(frame_dir, "frame_%03d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "20",
        target,
    ]
    subprocess.run(command, check=True)
    print(f"encoded {target}")


def probe(path: str) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames,r_frame_rate,duration",
            "-of",
            "default=noprint_wrappers=1",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def data_uri(path: str, mime: str) -> str:
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_index(out: str, clip_a: dict, clip_c: dict) -> str:
    images = {}
    for name in (
        "bev-plume.png",
        "real-vs-synth.png",
        "grid-12-22-38.png",
        "clip-a-frame-019.png",
        "clip-c-clean.png",
        "clip-c-with-plume.png",
    ):
        path = os.path.join(out, name)
        if os.path.exists(path):
            images[name] = data_uri(path, "image/png")

    video_a = data_uri(os.path.join(out, "clip-a-real-spray.mp4"), "video/mp4")
    video_c = data_uri(os.path.join(out, "clip-c-flicker.mp4"), "video/mp4")

    def figure(name: str, alt: str) -> str:
        return f'<img src="{images[name]}" alt="{alt}">'

    sections = [
        (
            "1. BEV một frame tổng hợp",
            figure("bev-plume.png", "synthetic BEV plume"),
            "Chứng minh: plume nằm sau đuôi box theo hướng −v/|v|, đúng dải 1–10 m và "
            "cao 0,2–2 m; 66 điểm / 6 cụm, median r_range/r_extent = 1,130.",
            "Không chứng minh: độ thực tế của cảnh nền (điểm xám là mặt đường tổng hợp "
            "tất định để định hướng, không phải dữ liệu đo), và không chứng minh "
            "diễn biến thời gian.",
        ),
        (
            "2. Thật vs tổng hợp",
            figure("real-vs-synth.png", "real vs synthetic"),
            "Chứng minh: frame SemanticSpray thật chọn tự động "
            f"({clip_a['group']}/0012_2021-09-08-14-50-58_0, frame 000000, "
            "object_velocity = 60 km/h, 51 điểm spray, ngưỡng ≥ 50) có spray ở cùng "
            "thang đo với frame tổng hợp.",
            "Không chứng minh: khớp thống kê (chỉ 1 frame), cùng cảm biến, hay hình học "
            "cụm giống nhau — single-linkage trên frame thật cho 5 cụm, 2 cụm dày ≥ 5 điểm.",
        ),
        (
            "3. Lưới mật độ theo cự ly",
            figure("grid-12-22-38.png", "density grid"),
            "Chứng minh: cùng một box, cùng tốc độ 130 km/h (20 cụm/panel để median ổn "
            "định), mật độ giảm theo cự ly: median điểm/cụm 22,5 và 21,0 ở x=12 m "
            "(plume cách sensor ~1–11 m), 10,5 và 15,0 ở x=22 m (~11–21 m), 10,0 và "
            "9,5 ở x=38 m (~27–37 m) — đúng xu hướng 30/20 → 14 → 10 của ticket 16.",
            "Không chứng minh: đúng từng con số của một bucket đơn lẻ. Vì plume nằm sau "
            "đuôi box (−v), mỗi panel trộn 2 bucket (x=12 m trộn 0–5 và 5–10 m), và "
            "chỉ có 20 cụm/panel nên median còn dao động; không chứng minh hình học "
            "cụm thật.",
        ),
        (
            "Clip A. Spray thật",
            f'<video controls loop muted playsinline src="{video_a}"></video>',
            "Chứng minh: spray thật (label 2) tồn tại qua toàn bộ "
            f"{clip_a['frames']} frame của {clip_a['sequence']} và di chuyển khi trục "
            "cố định một lần cho cả clip; số điểm spray/frame biến thiên "
            f"{clip_a['spray_min']}–{clip_a['spray_max']} (median {clip_a['spray_median']:.1f}).",
            "Không chứng minh: độ chính xác của generator. Lưu ý: ibeo_front không có "
            "label (README dataset chỉ cung cấp label cho VLP-32C), nên clip dùng "
            "velodyne (VLP-32C) — cảm biến duy nhất có nhãn spray — thay vì ibeo_front.",
        ),
        (
            "Clip C. Flicker A/B",
            f'<video controls loop muted playsinline src="{video_c}"></video>',
            "Chứng minh: generator độc lập từng frame — cùng một frame sạch lặp lại 6 vòng "
            f"với frame có plume (seed 0) ở 2 Hz ({clip_c['frames']} frame, "
            f"{clip_c['duration_s']:.0f} s).",
            "Không chứng minh: động học plume, lifetime hay fade. Generator không có "
            "trạng thái thời gian; nhấp nháy là sự thật của code, không nội suy/làm mượt.",
        ),
    ]

    cards = "\n".join(
        f"""
    <section>
      <h2>{title}</h2>
      <div class="media">{media}</div>
      <p><strong>Chứng minh:</strong> {proves}</p>
      <p><strong>Không chứng minh:</strong> {disproves}</p>
    </section>"""
        for title, media, proves, disproves in sections
    )

    html = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plume visualization — ticket 20</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #f5f6f8; color: #1b1d21;
         font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 26px; margin: 0 0 6px; }}
  .lede {{ color: #555a60; margin: 0 0 22px; }}
  section {{ background: #fff; border: 1px solid #e2e5e9; border-radius: 12px;
             padding: 18px 20px; margin: 0 0 20px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
  h2 {{ font-size: 17px; margin: 0 0 12px; }}
  .media {{ margin: 0 0 12px; }}
  img, video {{ display: block; width: 100%; height: auto; border-radius: 8px;
                border: 1px solid #e2e5e9; background: #fff; }}
  p {{ margin: 6px 0; }}
  code {{ background: #f0f2f4; padding: 1px 5px; border-radius: 4px; font-size: 13px; }}
  .note {{ border-left: 4px solid #b3001b; padding: 10px 14px; background: #fff5f6;
           border-radius: 6px; margin: 0 0 22px; }}
  footer {{ color: #6b7076; font-size: 13px; }}
</style>
</head>
<body>
<main>
  <h1>Plume visualization — ticket 20</h1>
  <p class="lede">Ảnh tĩnh và clip cho <code>spray/plume.py</code>. Tham số plume giữ nguyên;
     mọi frame sinh từ seed cố định trong script.</p>
  <div class="note"><strong>Generator frame-independent.</strong> Mỗi frame rút mới, không có
     hạt/lifetime/fade như paper (<code>Δt=100 ms</code>, <code>P_t(t)=e^(−t/T)</code>).
     Clip C vì vậy nhấp nháy có chủ đích; không nội suy, không làm mượt.</div>
{cards}
  <footer>
    Clip A: {clip_a['group']}/{os.path.basename(clip_a['sequence'])},
    {clip_a['frames']} frame @ {CLIP_A_FPS} fps. Clip C: {clip_c['frames']} frame @
    {clip_c['fps']} Hz. Sinh bằng <code>scripts/visualize_plume.py</code> và
    <code>scripts/render_clips.py</code>.
  </footer>
</main>
</body>
</html>
"""
    path = os.path.join(out, "index.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=FIG_DIR)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    root = os.path.join(REPO, "data", "SemanticSprayDataset")

    work_dir = tempfile.mkdtemp(
        prefix="plume-clips-",
        dir=os.environ.get("COMMANDCODE_SCRATCHPAD") or None,
    )
    try:
        scene = select_sequence(root)
        clip_a = render_clip_a(scene, args.out, work_dir)
        clip_c = render_clip_c(args.out, work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    for name in ("clip-a-real-spray.mp4", "clip-c-flicker.mp4"):
        path = os.path.join(args.out, name)
        print(f"{name}: {probe(path)}")

    index = build_index(args.out, clip_a, clip_c)
    print(f"index: {index}")
    print(f"clip A: {clip_a}")
    print(f"clip C: {clip_c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
