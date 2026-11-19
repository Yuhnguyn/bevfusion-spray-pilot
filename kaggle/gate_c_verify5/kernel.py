#!/usr/bin/env python3
"""Kaggle script kernel: verify the channel-4 fix of ``scripts/sspp_infer.py``.

Câu hỏi: Model 0 (BEVFusion LiDAR-only zero-shot) có hết mù trên SSPP sau khi
zero-hoá cột 4 (ring -> time-lag) hay không? Đo **cùng 5 frame, cùng seed** ở
ba chế độ, trong **một** kernel:

* ``legacy_channel4`` — ``--legacy-channel4``: tái hiện lỗi cũ (nạp ring vào
  chỗ time-lag);
* ``fixed`` — mặc định: cột 4 = 0 như pipeline chuẩn của nuScenes;
* ``fixed_z_m1p45`` — mặc định + ``--z-shift-m -1.45``: biến thể covariate độ
  cao, chỉ chạy để trả lời trước câu "nếu vẫn mù thì có phải do z?" (một biến
  thể duy nhất, chốt trước khi xem số).

Kernel này KHÔNG chạy lại cổng C đầy đủ (954 frame): nó chỉ đo 5 frame của
``Crafter_dynamic`` ở 90/130 km/h. Bootstrap (venv py3.8 + torch 1.10.1+cu113 +
mmcv-full 1.4.0 + 12 CUDA op) dùng lại nguyên vẹn recipe đã chứng minh của
``kaggle/e2e/main.py`` (branch ``main``, ship trong dataset ``sspp-gate-c-code``),
y như ``kaggle/gate_c/kernel.py``.

Inputs (Kaggle datasets, read-only):
  * ``sspp-gate-c-code`` — repo tree + ``scripts/sspp_infer.py`` +
    ``kaggle/e2e/main.py`` + ``checkpoints/lidar-only-det.pth``
  * ``sspp-gate-c-data`` — 954 frame test (``Crafter_dynamic``/``Golf_dynamic``)
    + ``sspp_infos_test.pkl`` + ``sspp_split.json``

Outputs (``/kaggle/working/verify5_out``, giữ làm kernel output):
  * ``<mode>.jsonl`` + ``<mode>_summary.json`` — mỗi chế độ một file
  * ``verify5_table.json`` + ``verify5_table.md`` — bảng trước/sau + verdict
"""

import json
import os
import pickle
import subprocess
import sys
import tarfile
import time
import traceback
from pathlib import Path

WORK = Path("/kaggle/working")
REPO = WORK / "repo"
OUT = WORK / "verify5_out"
PIN_SHORT = "da93b27"
PIN_FULL = "da93b27d0fe4563eecd46604e6cc5ddf1c5bd1ea"

# Chốt trước khi xem số: 3 frame ở 90 km/h + 2 frame ở 130 km/h, chọn theo vị
# trí đều trong scene (không chọn theo điểm/nội dung để tránh cherry-pick).
SCENE_FRAMES = {
    "Crafter_dynamic/0048_2021-09-08-16-02-18_0": [6, 32, 58],   # 90 km/h, 65 frame
    "Crafter_dynamic/0096_2021-09-08-17-49-24_0": [12, 59],      # 130 km/h, 79 frame
}

MODES = (
    ("legacy_channel4", ["--legacy-channel4"]),
    ("fixed", []),
    ("fixed_z_m1p45", ["--z-shift-m", "-1.45"]),
)

SCORE_GATE = 0.20   # τ của cổng C (pre-registered)
IOU_GATE = 0.50
IN3M_M = 3.0
IN5M_M = 5.0
SCORE_FLOOR = 0.05  # ngưỡng ghi của cổng C, để "n_det" so được với runbook

_LINES = []


def log(*parts):
    print(*parts, flush=True)


def stream(cmd, cwd=None, env=None, timeout=None):
    log("$ " + " ".join(str(part) for part in cmd))
    proc = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=None if cwd is None else str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            _LINES.append(line)
            if len(_LINES) > 4000:
                del _LINES[:2000]
            print(line, flush=True)
    finally:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            log("[timeout after %ss]" % timeout)
    log("[exit=%s]" % proc.returncode)
    return proc.returncode, "\n".join(lines)


def fail(step, detail):
    log("")
    log("VERIFY_KERNEL_FAILED step=%s" % step)
    log(detail)
    sys.exit(1)


# --------------------------------------------------------------------------
# Mount lookups (copy của kaggle/gate_c/kernel.py, giữ nguyên hành vi)
# --------------------------------------------------------------------------
def find_input(predicate, label):
    for root in [Path("/kaggle/input")]:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            try:
                if predicate(path):
                    return path
            except OSError:
                continue
    fail("mount", "could not find %s under /kaggle/input" % label)


def find_code_mount():
    candidates = [
        Path("/kaggle/input/sspp-gate-c-code"),
        Path("/kaggle/input/datasets/nguynhuy9669/sspp-gate-c-code"),
    ]
    for path in candidates:
        if (path / "kaggle" / "e2e" / "main.py").is_file():
            return path
    try:
        marker = find_input(
            lambda p: p.name == "main.py"
            and p.parent.name == "e2e"
            and p.parent.parent.name == "kaggle",
            "kaggle/e2e/main.py (code dataset)",
        )
        return marker.parents[2]
    except SystemExit:
        archive = find_input(lambda p: p.name == "code.tar", "code.tar (code dataset)")
        log("code dataset is a code.tar payload:", archive)
        REPO.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:*") as handle:
            handle.extractall(REPO)
        return REPO


def find_data_mount():
    candidates = [
        Path("/kaggle/input/sspp-gate-c-data"),
        Path("/kaggle/input/datasets/nguynhuy9669/sspp-gate-c-data"),
    ]
    for path in candidates:
        if (path / "sspp_infos_test.pkl").is_file() and (path / "Crafter_dynamic").is_dir():
            return path
    marker = find_input(
        lambda p: p.name == "sspp_infos_test.pkl", "sspp_infos_test.pkl (data dataset)"
    )
    return marker.parent


def load_bootstrap(code_mount):
    import importlib.util

    path = code_mount / "kaggle" / "e2e" / "main.py"
    spec = importlib.util.spec_from_file_location("gate_c_e2e_bootstrap", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        fail("bootstrap", "cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patch_bootstrap(bootstrap, code_mount):
    bootstrap.DATASET_MOUNT = code_mount
    bootstrap.REPO = REPO
    bootstrap.WORK = WORK
    bootstrap.MIT = REPO / "mit" / "bevfusion"
    bootstrap.SCRATCH = Path("/root/gate_c_e2e")
    bootstrap.VENV = bootstrap.SCRATCH / "env"
    bootstrap.PY = bootstrap.VENV / "bin" / "python"
    bootstrap.LOGS = bootstrap.SCRATCH / "logs"
    bootstrap.GPU_PYTHON = sys.executable
    bootstrap.PIN_SHORT = PIN_SHORT
    bootstrap.PIN_FULL = PIN_FULL
    bootstrap.find_mount = lambda: code_mount
    log("bootstrap patched: REPO=%s SCRATCH=%s" % (bootstrap.REPO, bootstrap.SCRATCH))
    return bootstrap


def check_data_mount(data_mount):
    log("")
    log("[data] dataset mount:", data_mount)
    infos = data_mount / "sspp_infos_test.pkl"
    split = data_mount / "sspp_split.json"
    if not infos.is_file() or not split.is_file():
        fail("data", "data mount is missing sspp_infos_test.pkl / sspp_split.json")
    n_bin = len(list(data_mount.rglob("*.bin")))
    n_label = len(list(data_mount.rglob("*.label")))
    if n_bin != 954 or n_label != 954:
        fail("data", "expected 954 .bin + 954 .label under the mount, got %d / %d"
             % (n_bin, n_label))
    log("VERIFY_DATA_OK frames_bin=%d labels=%d" % (n_bin, n_label))
    return data_mount


# --------------------------------------------------------------------------
# Chọn frame + chạy 3 chế độ
# --------------------------------------------------------------------------
def select_tokens(infos_path):
    with infos_path.open("rb") as handle:
        infos = pickle.load(handle)
    by_scene = {}
    for info in infos:
        scene = str(info["token"]).rsplit("/", 1)[0]
        by_scene.setdefault(scene, []).append(info)
    tokens = []
    for scene, positions in SCENE_FRAMES.items():
        frames = sorted(by_scene.get(scene, []), key=lambda item: item["timestamp"])
        if not frames:
            fail("frames", "scene %s has no frame in %s" % (scene, infos_path))
        for position in positions:
            if position >= len(frames):
                fail("frames", "scene %s has only %d frames, want #%d"
                     % (scene, len(frames), position))
            tokens.append(str(frames[position]["token"]))
    if len(set(tokens)) != len(tokens) or len(tokens) != 5:
        fail("frames", "expected 5 distinct tokens, got %r" % (tokens,))
    for token in tokens:
        log("VERIFY_FRAME %s" % token)
    return tokens


def run_mode(bootstrap, dataset, checkpoint, name, extra, tokens):
    out_path = OUT / ("%s.jsonl" % name)
    command = [
        str(bootstrap.PY),
        "scripts/sspp_infer.py",
        "--config", "model0",
        "--checkpoint", str(checkpoint),
        "--dataset-root", str(dataset),
        "--infos", str(dataset / "sspp_infos_test.pkl"),
        "--split-json", str(dataset / "sspp_split.json"),
        "--split", "test",
        "--arms", "clean",
        "--tokens", *tokens,
        "--seed", "0",
        "--score-thresh", str(SCORE_GATE),
        "--min-score", "0.001",
        "--log-every", "1",
        "--out", str(out_path),
    ] + list(extra)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    rc, text = stream(command, cwd=REPO, env=env, timeout=3600)
    for line in text.splitlines():
        if line.startswith(("GATE_C_INPUT_MODE", "GATE_C_ARM ", "GATE_C_OUTPUT ")):
            log("RESULT " + line)
    if rc != 0 or "GATE_C_OK" not in text:
        fail("inference:" + name, "sspp_infer.py rc=%d for mode %s; see log above"
             % (rc, name))
    return out_path


# --------------------------------------------------------------------------
# Phân tích: mỗi frame x mỗi chế độ
# --------------------------------------------------------------------------
def short_token(token):
    parts = str(token).rsplit("/", 2)
    if len(parts) < 3:
        return str(token)
    return "%s/%s" % (parts[1].split("_")[0], parts[2])


def analyse(mode_files, dataset, tokens):
    import numpy as np

    sys.path.insert(0, str(REPO))
    from proxy_eval.matcher import bev_iou

    with (dataset / "sspp_infos_test.pkl").open("rb") as handle:
        infos = {str(info["token"]): info for info in pickle.load(handle)}

    rows = []
    summary = {}
    for mode, path in mode_files.items():
        frames = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                frames[record["token"]] = record
        if len(frames) != len(tokens):
            fail("analyse", "%s has %d frames, want %d" % (path, len(frames), len(tokens)))
        mode_rows = []
        for token in tokens:
            record = frames[token]
            info = infos[token]
            gt = np.asarray(info["gt_boxes"], dtype=np.float64).reshape(-1, 9)
            gt_box = gt[0][:7]
            boxes = record["boxes"]
            scores = np.asarray([box["score"] for box in boxes], dtype=np.float64)
            centres = np.asarray(
                [[box["x"], box["y"]] for box in boxes], dtype=np.float64
            ).reshape(-1, 2)
            det = np.asarray(
                [[box["x"], box["y"], box["z"], box["dx"], box["dy"], box["dz"], box["yaw"]]
                 for box in boxes],
                dtype=np.float64,
            ).reshape(-1, 7)
            ious = (
                np.asarray([bev_iou(row, gt_box) for row in det], dtype=np.float64)
                if len(boxes) else np.zeros(0)
            )
            dists = (
                np.hypot(centres[:, 0] - gt_box[0], centres[:, 1] - gt_box[1])
                if len(boxes) else np.zeros(0)
            )
            ego_dists = np.hypot(centres[:, 0], centres[:, 1]) if len(boxes) else np.zeros(0)
            keep = scores >= SCORE_FLOOR
            high = scores >= SCORE_GATE
            row = {
                "mode": mode,
                "token": token,
                "speed_kmh": float(info["ego_speed_kmh"]),
                "n_det_all": int(len(boxes)),
                "n_det": int(keep.sum()),
                "max_score": float(scores.max()) if len(scores) else 0.0,
                "best_bev_iou": float(ious.max()) if len(ious) else 0.0,
                "nearest_center_dist_m": float(dists.min()) if len(dists) else float("inf"),
                "n_det_in_3m": int(((dists <= IN3M_M) & high).sum()),
                "n_det_in_3m_any_score": int((dists <= IN3M_M).sum()),
                "n_det_in_5m_ego": int(((ego_dists <= IN5M_M) & keep).sum()),
                "tp_at_gate": int(bool(((ious >= IOU_GATE) & high).sum())),
                "n_gt": int(len(gt)),
            }
            rows.append(row)
            mode_rows.append(row)
            log(
                "VERIFY_ROW mode=%s token=%s speed=%.0f n_det=%d n_det_all=%d "
                "max_score=%.4f best_bev_iou=%.4f nearest_m=%.2f n_in3m=%d "
                "n_in3m_any=%d n_in5m_ego=%d tp=%d"
                % (row["mode"], token, row["speed_kmh"], row["n_det"],
                   row["n_det_all"], row["max_score"], row["best_bev_iou"],
                   row["nearest_center_dist_m"], row["n_det_in_3m"],
                   row["n_det_in_3m_any_score"], row["n_det_in_5m_ego"],
                   row["tp_at_gate"])
            )
        n_det = sum(row["n_det"] for row in mode_rows)
        n_in5 = sum(row["n_det_in_5m_ego"] for row in mode_rows)
        frames_in3 = sum(1 for row in mode_rows if row["n_det_in_3m"] >= 1)
        summary[mode] = {
            "frames": len(mode_rows),
            "n_det": n_det,
            "n_det_in_5m_ego": n_in5,
            "pct_det_in_5m_ego": (100.0 * n_in5 / n_det) if n_det else 0.0,
            "frames_with_det_in_3m": frames_in3,
            "max_score": max(row["max_score"] for row in mode_rows),
            "frames_with_tp": sum(row["tp_at_gate"] for row in mode_rows),
            "n_det_all": sum(row["n_det_all"] for row in mode_rows),
        }
        log(
            "VERIFY_MODE mode=%s frames=%d n_det=%d n_det_all=%d in5m=%d pct_in5m=%.1f "
            "frames_with_in3m=%d max_score=%.4f frames_with_tp=%d"
            % (mode, len(mode_rows), n_det, summary[mode]["n_det_all"], n_in5,
               summary[mode]["pct_det_in_5m_ego"], frames_in3,
               summary[mode]["max_score"], summary[mode]["frames_with_tp"])
        )

    fixed = summary["fixed"]
    zfix = summary["fixed_z_m1p45"]
    pass_fixed = fixed["max_score"] > SCORE_GATE and fixed["frames_with_det_in_3m"] >= 3
    pass_z = zfix["max_score"] > SCORE_GATE and zfix["frames_with_det_in_3m"] >= 3
    log(
        "VERIFY_VERDICT fixed_pass=%d z_pass=%d legacy_frames_in3m=%d "
        "legacy_max_score=%.4f"
        % (int(pass_fixed), int(pass_z), summary["legacy_channel4"]["frames_with_det_in_3m"],
           summary["legacy_channel4"]["max_score"])
    )
    payload = {
        "criteria": {
            "pass_max_score_gt": SCORE_GATE,
            "pass_frames_with_det_in_3m_min": 3,
            "n_frames": len(tokens),
            "det_in_3m_counts_only_with_score_ge": SCORE_GATE,
            "iou_gate": IOU_GATE,
            "score_floor_for_n_det": SCORE_FLOOR,
        },
        "tokens": tokens,
        "rows": rows,
        "summary": summary,
        "verdict": {
            "fixed_pass": bool(pass_fixed),
            "fixed_z_m1p45_pass": bool(pass_z),
        },
    }
    (OUT / "verify5_table.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Verify kênh 4 — 5 frame Crafter_dynamic (90/130 km/h)",
        "",
        "| chế độ | n_det | n_det_all | max_score | in3m (score>=0,2) | "
        "frames_in3m | in5m_ego | % in5m_ego | frames TP |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in ("legacy_channel4", "fixed", "fixed_z_m1p45"):
        item = summary[mode]
        lines.append(
            "| %s | %d | %d | %.4f | %d | %d/%d | %d | %.1f%% | %d |"
            % (mode, item["n_det"], item["n_det_all"], item["max_score"],
               sum(row["n_det_in_3m"] for row in rows if row["mode"] == mode),
               item["frames_with_det_in_3m"], len(tokens), item["n_det_in_5m_ego"],
               item["pct_det_in_5m_ego"], item["frames_with_tp"])
        )
    lines.append("")
    lines.append(
        "PASS (max_score > %.2f và >=1 det trong %.1f m tâm GT ở >=3/5 frame): "
        "fixed=%s · fixed_z_m1p45=%s"
        % (SCORE_GATE, IN3M_M, pass_fixed, pass_z)
    )
    lines.append("")
    lines.append("| mode | token | speed | n_det | max_score | best_bev_iou | "
                 "nearest_m | n_in3m | n_in3m_any | n_in5m_ego |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            "| %s | %s | %.0f | %d | %.4f | %.4f | %.2f | %d | %d | %d |"
            % (row["mode"], short_token(row["token"]),
               row["speed_kmh"], row["n_det"], row["max_score"], row["best_bev_iou"],
               row["nearest_center_dist_m"], row["n_det_in_3m"],
               row["n_det_in_3m_any_score"], row["n_det_in_5m_ego"])
        )
    (OUT / "verify5_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


# --------------------------------------------------------------------------
def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    code_mount = find_code_mount()
    data_mount = find_data_mount()
    dataset = check_data_mount(data_mount)
    log("VERIFY_CODE_MOUNT", code_mount)
    log("gpu:", subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True,
    ).stdout.strip())

    tokens = select_tokens(dataset / "sspp_infos_test.pkl")

    tar_form = code_mount == REPO
    bootstrap = patch_bootstrap(load_bootstrap(code_mount), code_mount)

    log("")
    log("[1/6] extract tracked repo tree")
    if tar_form:
        log("code dataset was a code.tar payload; already extracted into", REPO)
    else:
        bootstrap.extract_code()
    log("")
    log("[2/6] clone mit/bevfusion @", PIN_SHORT)
    bootstrap.clone_pin()
    checkpoint = REPO / "checkpoints" / "lidar-only-det.pth"
    if not checkpoint.is_file():
        fail("checkpoint", "missing %s (code dataset must ship it)" % checkpoint)
    log("")
    log("[3/6] pinned Python 3.8 venv")
    bootstrap.install_env()
    log("")
    log("[4/6] CUDA toolchain")
    toolchain = bootstrap.choose_toolchain()
    log("")
    log("[5/6] compile mmdet3d CUDA ops")
    ops_ok, ops_report = bootstrap.build_ops(toolchain)
    log("build report:", json.dumps(ops_report))
    if not ops_ok:
        fail("ops", "CUDA extension build failed")
    stack_ok, probe = bootstrap.verify_stack()
    if not stack_ok:
        fail("stack", "pinned stack import failed:\n%s" % probe[-4000:])

    log("")
    log("[6/6] ba chế độ x 5 frame")
    mode_files = {}
    for name, extra in MODES:
        log("")
        log("=== mode %s %s" % (name, " ".join(extra) or "(default)"))
        mode_files[name] = run_mode(bootstrap, dataset, checkpoint, name, extra, tokens)

    log("")
    log("[analyse] bảng trước/sau")
    payload = analyse(mode_files, dataset, tokens)
    log("")
    log("VERIFY_TABLE %s" % (OUT / "verify5_table.md"))
    log("elapsed_s=%.0f" % (time.time() - started))
    log("VERIFY_KERNEL_OK frames=%d modes=%d fixed_pass=%d"
        % (len(tokens), len(MODES), int(payload["verdict"]["fixed_pass"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        log("VERIFY_KERNEL_FAILED step=unhandled")
        sys.exit(1)
