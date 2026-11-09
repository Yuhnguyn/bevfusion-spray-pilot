"""Reporting artifact (PM-authored, NOT part of the spray/ module).

Renders docs/figs/plume/v1-audit/compare.mp4: the repo's own
``spray.plume.inject_plume`` (left) next to an illustrative re-implementation
of the published reference mechanism (right). Panel (2) is a mock-up used for
comparison only; it is not repo code and must not be cited as such.

Run from anywhere:  python docs/figs/plume/v1-audit/render_compare.py
Needs matplotlib + ffmpeg on PATH.
"""
import pathlib, subprocess, sys, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.gridspec import GridSpec

HERE = pathlib.Path(__file__).resolve()
REPO = str(HERE.parents[4])  # docs/figs/plume/v1-audit/render_compare.py -> repo root
sys.path.insert(0, REPO)
from spray.plume import (  # noqa: E402
    PlumeConfig, inject_plume, _lognormal_clipped, _ball,
    _count_for_distance, cluster_count_for_speed,
)

OUT = str(HERE.parent / "compare.mp4")
W, H, FPS = 1280, 720, 30
N_SIM, N_HOLD = 240, 60
GROUND_Z = -1.84
DT = 1.0 / FPS
V = 80 / 3.6
L, WID, HT = 4.6, 1.9, 1.7
BOX_X = 25.0                      # fixed world pose handed to inject_plume

cfg = PlumeConfig()
T_CONST = cfg.water_film_height_m * 0.02 * (80 - 50) + 0.2
MEAN_CLUSTERS = (0.2 * cfg.water_film_height_m + 0.1) * (80 - 50)   # 3.0 per 0.1 s

rng = np.random.default_rng(7)

# road strip in world coords (long enough for the whole clip, no wrap)
gx, gy = np.meshgrid(np.arange(-260, 45, 0.5), np.arange(-7.6, 7.6, 0.32))
road = np.column_stack([
    gx.ravel() + rng.normal(0, 0.05, gx.size),
    gy.ravel() + rng.normal(0, 0.05, gy.size),
    GROUND_Z + rng.normal(0, 0.03, gx.size),
    np.zeros(gx.size), np.zeros(gx.size),
]).astype(np.float32)
road = road[rng.random(len(road)) < 0.5]

fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
gs = GridSpec(2, 2, figure=fig, height_ratios=[1.58, 1.0], left=0.045, right=0.985,
              top=0.895, bottom=0.085, wspace=0.13, hspace=0.34)
ax1, ax2, ax3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])

BG, GREY, RED, TEAL, BLUE = "#fbfbfc", "#939ca7", "#c9394b", "#00808f", "#2f6fdb"
for ax in (ax1, ax2):
    ax.set_facecolor(BG); ax.set_aspect("equal")
    ax.set_ylim(-7.5, 7.5); ax.set_xlim(-30, 8)
    ax.grid(True, color="#e8eaee", lw=0.6); ax.tick_params(labelsize=8)
    ax.set_xlabel("x tương đối so với tâm xe [m]", fontsize=8)
    ax.set_ylabel("y [m]", fontsize=8)
ax3.set_facecolor(BG); ax3.grid(True, color="#e8eaee", lw=0.6)
ax3.tick_params(labelsize=8)
ax3.set_xlabel("x tương đối so với tâm xe [m]", fontsize=8)
ax3.set_ylabel("z [m]  (0 = cảm biến)", fontsize=8)
ax3.set_xlim(-30, 8); ax3.set_ylim(-2.25, 2.45)

fig.text(0.045, 0.947, "Mỗi frame sinh plume một lần — generator hiện tại của repo  vs  cơ chế trong code tham chiếu",
         fontsize=14.5, weight="bold", color="#1d2530")
fig.text(0.045, 0.908, "xe dẫn đường 80 km/h · 8 cụm/frame · ~10 điểm/cụm · bán kính 0,30 m · wfh 1 mm · T = 0,20 s · khung nhìn = khung xe",
         fontsize=9.0, color="#5b6572")
fig.text(0.045, 0.882, "(2) dồn sát đuôi xe, sống tới 4T, mờ dần theo tuổi — mô phỏng minh hoạ cơ chế trong code tham chiếu, để so sánh hình dạng",
         fontsize=8.6, color=TEAL)
ax1.set_title("(1)  inject_plume — code thật của repo, mỗi frame độc lập",
              fontsize=9.5, color=RED, loc="left", pad=6)
ax2.set_title("(2)  cơ chế tham chiếu — chỉ minh hoạ, không phải code repo",
              fontsize=9.5, color=TEAL, loc="left", pad=6)
ax3.set_title("Nhìn ngang: cloud nằm ở độ cao nào so với mặt đường và thân xe",
              fontsize=10, color="#1d2530", loc="left", pad=5)
fig.text(0.045, 0.018,
         "panel (1) gọi đúng hàm của repo.  panel (2) chỉ minh hoạ cơ chế tham chiếu.  "
         "mặt đường nuScenes ≈ −1,84 m trong frame LiDAR (cần xác nhận bằng 1 frame thật).",
         fontsize=7.8, color="#7a828c")

g1 = ax1.scatter(road[:, 0], road[:, 1], s=2, c=GREY, lw=0, alpha=0.5, zorder=1)
g2 = ax2.scatter(road[:, 0], road[:, 1], s=2, c=GREY, lw=0, alpha=0.5, zorder=1)
p1 = ax1.scatter([], [], s=12, c=RED, lw=0, alpha=0.95, zorder=4)
p2 = ax2.scatter([], [], s=12, c=TEAL, lw=0, alpha=0.95, zorder=4)
for ax in (ax1, ax2):
    ax.add_patch(Rectangle((-L / 2, -WID / 2), L, WID, fc=BLUE, ec="#1b4fa6", lw=1.4, alpha=0.28, zorder=5))
    ax.arrow(3.5, 0, 3.2, 0, width=0.06, head_width=0.5, head_length=0.7,
             color="#2f6fdb", alpha=0.55, zorder=6, length_includes_head=True)
    ax.text(3.6, -0.95, "chiều chạy", fontsize=7.5, color="#2f6fdb")

ax3.axhspan(-2.25, GROUND_Z, color="#eceff2", zorder=0)
ax3.axhline(GROUND_Z, color="#8a929c", lw=2.0, zorder=1)
ax3.axhline(0.0, color="#c0392b", lw=0.9, ls="--", alpha=0.65, zorder=1)
ax3.text(7.6, 0.08, "z = 0 (cảm biến)", fontsize=7.5, color="#c0392b", ha="right")
ax3.text(-29.6, GROUND_Z + 0.1, "mặt đường ≈ −1,84 m", fontsize=7.5, color="#6b7480")
s1 = ax3.scatter([], [], s=8, c=RED, lw=0, alpha=0.9, zorder=4)
s2 = ax3.scatter([], [], s=8, c=TEAL, lw=0, alpha=0.9, zorder=4)
ax3.add_patch(Rectangle((-L / 2, GROUND_Z), L, HT, fc=BLUE, ec="#1b4fa6", lw=1.3, alpha=0.25, zorder=5))

box_style = dict(fc="white", ec="#dfe3e8", alpha=0.92, pad=5)
t1 = ax1.text(0.985, 0.028, "", transform=ax1.transAxes, va="bottom", ha="right", fontsize=8.4,
              family="monospace", color="#39414d", bbox=box_style)
t2 = ax2.text(0.985, 0.028, "", transform=ax2.transAxes, va="bottom", ha="right", fontsize=8.4,
              family="monospace", color="#39414d", bbox=box_style)
t3 = ax3.text(0.014, 0.95, "", transform=ax3.transAxes, va="top", fontsize=8.4,
              family="monospace", color="#39414d", bbox=box_style)

# ---------------- reference-style stateful plume, simulated in the car frame
clusters = []
def spawn(t):
    for _ in range(int(round(MEAN_CLUSTERS))):
        cy = rng.uniform(-1.7, 1.7)
        cz = GROUND_Z + rng.uniform(0.0, 1.45)
        radius = float(min(1.0, _lognormal_clipped(
            rng, cfg.cluster_radius_median_m, cfg.cluster_radius_sigma, cfg.cluster_radius_bounds_m)))
        count = int(_count_for_distance(rng, BOX_X, cfg))
        clusters.append(dict(s=0.0, u=V, cy=cy, cz=cz, radius=radius,
                             off=_ball(rng, count, radius), age=0.0,
                             T=float(max(0.10, T_CONST + rng.normal(0, 0.045)))))
def step(dt):
    alive = []
    for c in clusters:
        c["age"] += dt
        if c["age"] > 4 * c["T"]:
            continue
        c["u"] = max(0.0, c["u"] - 0.12 * c["u"] ** 2 * dt)   # drag_factor ≈ −0,12 [CODE]
        c["s"] += (V - c["u"]) * dt                            # distance fallen behind
        alive.append(c)
    clusters[:] = alive

def ref_points():
    if not clusters:
        return np.empty((0, 3)), np.empty(0)
    pts, al = [], []
    for c in clusters:
        base = np.array([-L / 2 - 0.2 - c["s"], c["cy"], c["cz"]])
        pts.append(c["off"] + base)
        al.append(np.full(len(c["off"]), math.exp(-c["age"] / c["T"])))
    return np.concatenate(pts), np.concatenate(al)

proc = subprocess.Popen(
    ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
     "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
     "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", OUT],
    stdin=subprocess.PIPE)

last_cycle, tot_rej, tot_gen = -1, 0, 0
N_CLU = cluster_count_for_speed(80.0, cfg)
med1_hist = []
for frame in range(N_SIM + N_HOLD):
    t = min(frame, N_SIM - 1) * DT
    scroll = -V * t

    res = inject_plume(road, np.array([[BOX_X, 0.0, 1.0, L, WID, HT, 0.0, V, 0.0]]),
                       seed=frame % 89, token=f"viz{frame}", config=cfg)
    tot_rej += res.stats.rejected_box
    tot_gen += res.stats.rejected_box + res.stats.rejected_range + res.stats.capped + res.stats.injected
    inj = res.injected

    cyc = int(t / 0.1)
    if frame < N_SIM:
        if cyc != last_cycle:
            spawn(t); last_cycle = cyc
        step(DT)
    rp, ra = ref_points()

    gx_disp = road[:, 0] + scroll + BOX_X          # world -> car frame offset
    g1.set_offsets(np.column_stack([gx_disp, road[:, 1]]))
    g2.set_offsets(np.column_stack([gx_disp, road[:, 1]]))

    d1 = np.column_stack([inj[:, 0] - BOX_X, inj[:, 1]]) if len(inj) else np.empty((0, 2))
    p1.set_offsets(d1)
    p2.set_offsets(np.column_stack([rp[:, 0], rp[:, 1]]) if len(rp) else np.empty((0, 2)))
    if len(rp):
        al = np.clip(ra, 0.06, 1.0)
        p2.set_facecolors(np.column_stack([np.tile([0.0, 0.502, 0.561], (len(al), 1)), al]))

    s1.set_offsets(np.column_stack([d1[:, 0], inj[:, 2]]) if len(inj) else np.empty((0, 2)))
    s2.set_offsets(np.column_stack([rp[:, 0], rp[:, 2]]) if len(rp) else np.empty((0, 2)))
    if len(rp):
        s2.set_facecolors(np.column_stack([np.tile([0.0, 0.502, 0.561], (len(al), 1)), al]))

    med1 = float(np.median(-(d1[:, 0]) - L / 2)) if len(d1) else 0.0
    med2 = float(np.median(-(rp[:, 0]) - L / 2)) if len(rp) else 0.0
    eff = float(sum(math.exp(-c["age"] / c["T"]) for c in clusters))
    med1_hist.append(med1)
    t1.set_text(f"điểm/frame    : {len(inj):4d}\ncụm/frame     : {N_CLU:4d}\n"
                f"cách đuôi xe  : {np.mean(med1_hist[-30:]):4.2f} m (TB 1 s)\n"
                f"bị xoá trong box: {100*tot_rej/max(tot_gen,1):4.1f}%")
    t2.set_text(f"cụm đang sống: {len(clusters):4d}\ncụm hiệu dụng: {eff:4.1f}  (trọng số exp(−age/T))\n"
                f"cách đuôi xe : {med2:4.2f} m (trung vị)\nmodel này tạo ra VỆT, không phải đám bụi rời")
    t3.set_text(f"(1) z = {inj[:,2].min() if len(inj) else 0:+.2f} … {inj[:,2].max() if len(inj) else 0:+.2f} m"
                f"  →  trung bình {inj[:,2].mean()-GROUND_Z if len(inj) else 0:.1f} m trên mặt đường\n"
                f"(2) z = {rp[:,2].min() if len(rp) else 0:+.2f} … {rp[:,2].max() if len(rp) else 0:+.2f} m"
                f"  →  trung bình {rp[:,2].mean()-GROUND_Z if len(rp) else 0:.1f} m trên mặt đường")

    fig.canvas.draw()
    proc.stdin.write(np.asarray(fig.canvas.buffer_rgba()).tobytes())
    if frame % 40 == 0:
        print(f"frame {frame:3d} v1pts={len(inj):4d} v2alive={len(clusters):3d} med1={med1:.2f} med2={med2:.2f}", flush=True)

proc.stdin.close(); proc.wait()
print("wrote", OUT)