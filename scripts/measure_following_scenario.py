#!/usr/bin/env python3
"""T5 — Đo mật độ spray ở kịch bản **following** (kiểm chứng, không tune).

A3 nghiệm thu ở kịch bản **static** (ego đứng yên, xe chạy ra xa). Production
(`spray/plume_transform.py`) lại chạy **following**: ego chạy theo xe SSPP thật.
Cùng plume nhưng góc khối khác hẳn (cụm trôi tới gần cảm biến) ⇒ số A3 không suy
ra được số train. Script này đo tỉ lệ **sinh/thật** đúng kịch bản production.

Với mỗi frame của scene SSPP:
1. **Thật**: số điểm ``label == 2`` trong frame.
2. **Sinh**: `PlumeContext` dựng từ chính frame đó (ego speed thật, object speed
   thật từ `metadata.txt`, vị trí xe thật: human box với 36 scene có box, pseudo
   box từ điểm ``label == 1`` với 171 scene không box), `PlumeState` warm-start
   theo scene (giống production), `inject_plume_stateful` →
   `raycast_frame(load_beam_table())` → đếm `RaycastResult.detections`.
   **Cùng một seed cho mọi frame** (paired).
3. Tỉ lệ sinh/thật từng frame; **bootstrap CI95 ở mức scene** (B = 2000).

Hai tập scene báo **riêng**:
- **A**: 36 scene có human box = tập eval (D1) — dùng làm covariate cho cổng C.
- **B**: 2 scene/(group, tốc độ) trong 171 scene **không box** (36 scene) =
  kiểm chứng sạch, không bao giờ nằm trong eval.

Chạy:
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/measure_following_scenario.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from spray.beam_model import load_beam_table  # noqa: E402
from spray.plume import PlumeConfig, inject_plume_stateful  # noqa: E402
from spray.plume_context import PlumeContext  # noqa: E402
from spray.plume_state import PlumeState, PlumeStateConfig  # noqa: E402
from spray.raycast import raycast_frame  # noqa: E402
from spray.sspp_adapter import (  # noqa: E402
    _boxes_to_arrays,
    read_frame_boxes,
    read_metadata,
)

SPRAY_LABEL = 2
VEHICLE_LABEL = 1
FIXED_SEED = 20261119
BOOTSTRAP = 2000
CI_SEED = 20261119

# Dims per class từ `spray/sspp_adapter.py` + pseudo-box doc (campaign chỉ có
# một xe/lớp; sd 0,003 m). Dùng cho pseudo box của scene không có human box.
CLASS_DIMS_M = {
    "crafter": (6.829, 2.419, 2.621),  # Van
    "golf": (4.250, 2.020, 1.501),  # Car
}

# A3-V (ADR-0006): vùng đo 0–60 m sau box xe dẫn, mask |y| ≤ 5 m,
# 0 ≤ z − road_z ≤ 3 m. KHÔNG đếm cả frame. Chốt trước khi xem số.
REGION_DEPTH_M = 60.0
REGION_HALF_WIDTH_M = 5.0
REGION_HEIGHT_MIN_M = 0.0
REGION_HEIGHT_MAX_M = 3.0
DEPTH_BIN_M = 2.0
DEPTH_BIN_EDGES_M = tuple(
    float(i) * DEPTH_BIN_M for i in range(int(REGION_DEPTH_M / DEPTH_BIN_M) + 1)
)

SPEED_BANDS = (
    ("50–70", (50, 60, 70)),
    ("80–110", (80, 90, 100, 110)),
    ("120–130", (120, 130)),
)


def _scene_meta(root: Path) -> list[dict]:
    """Đọc metadata mọi scene + đánh dấu scene có human box."""

    scenes: list[dict] = []
    for group in ("Crafter_dynamic", "Golf_dynamic"):
        group_dir = root / group
        for scene_dir in sorted(group_dir.iterdir(), key=lambda p: p.name):
            if not scene_dir.is_dir():
                continue
            row = read_metadata(scene_dir / "metadata.txt")
            speed = float(round(float(row["object_velocity"])))
            has_box = (scene_dir / "object_labels" / "lidar").is_dir()
            scenes.append(
                {
                    "rel_path": f"{group}/{scene_dir.name}",
                    "group": group,
                    "vehicle_class": (
                        "crafter" if group.startswith("Crafter") else "golf"
                    ),
                    "speed_kmh": speed,
                    "ego_kmh": float(row.get("ego_velocity") or speed),
                    "itr_after_water": int(row["itr_after_water"]),
                    "has_box": has_box,
                    "n_frames": len(
                        list((scene_dir / "velodyne").glob("*.bin"))
                    ),
                }
            )
    return scenes


def build_sample_b(scenes: list[dict]) -> list[dict]:
    """Tập B: 4 scene/(group, tốc độ) trong 171 scene KHÔNG box — tất định."""

    unboxed = [scene for scene in scenes if not scene["has_box"]]
    sample_b: list[dict] = []
    for group in ("Crafter_dynamic", "Golf_dynamic"):
        for speed in sorted({scene["speed_kmh"] for scene in unboxed}):
            members = sorted(
                (
                    scene
                    for scene in unboxed
                    if scene["group"] == group and scene["speed_kmh"] == speed
                ),
                key=lambda scene: scene["rel_path"],
            )
            sample_b.extend(members[:4])
    return sample_b


def split_fit_verify(scenes: list[dict]) -> dict[str, list[dict]]:
    """Chia 2/3 fit – 1/3 verify, phân tầng theo (lớp, nhóm tốc độ).

    Tất định: trong mỗi tầng, sort theo ``rel_path`` rồi index % 3 == 0 → verify
    (1/3), còn lại → fit (2/3). Không RNG.
    """

    band_of: dict[int, str] = {}
    for label, speeds in SPEED_BANDS:
        for speed in speeds:
            band_of[int(speed)] = label
    strata: dict[tuple[str, str], list[dict]] = {}
    for scene in scenes:
        key = (scene["vehicle_class"], band_of[int(scene["speed_kmh"])])
        strata.setdefault(key, []).append(scene)
    split: dict[str, list[dict]] = {"fit": [], "verify": []}
    for key in sorted(strata):
        members = sorted(strata[key], key=lambda scene: scene["rel_path"])
        for index, scene in enumerate(members):
            split["verify" if index % 3 == 0 else "fit"].append(scene)
    return split


def _sample_scene_indices(n_frames: int, count: int) -> list[int]:
    if count <= 0 or count >= n_frames:
        return list(range(n_frames))
    picks = np.linspace(0, n_frames - 1, count).round().astype(int)
    return sorted({int(index) for index in picks.tolist()})


def _pseudo_box_from_vehicle_points(
    points: np.ndarray, labels: np.ndarray, vehicle_class: str
) -> np.ndarray | None:
    """Human-box thay thế cho scene không có box, từ điểm ``label == 1``.

    Campaign chỉ có một xe mỗi lớp và xe gần như thẳng trục (|yaw| < 0,1 rad ở
    531/534 box), nên ước lượng đủ để đặt vùng sinh: mặt sau = percentile 2 của
    x (điểm gần ego nhất trên thân xe), tâm = mặt sau + size_x/2, y = median,
    đáy = percentile 2 của z. Vận tốc box để 0 (stateful path lấy vận tốc từ
    `PlumeContext`, không lấy từ box).
    """

    xyz = points[labels == VEHICLE_LABEL][:, :3].astype(np.float64)
    if xyz.shape[0] < 10:
        return None
    length, width, height = CLASS_DIMS_M[vehicle_class]
    rear_x = float(np.percentile(xyz[:, 0], 2.0))
    center_x = rear_x + length / 2.0
    center_y = float(np.median(xyz[:, 1]))
    bottom_z = float(np.percentile(xyz[:, 2], 2.0))
    return np.array(
        [[center_x, center_y, bottom_z, length, width, height, 0.0, 0.0, 0.0]],
        dtype=np.float32,
    )


def _human_boxes(scene_dir: Path, scan_id: str, speed_mps: float) -> np.ndarray:
    path = scene_dir / "object_labels" / "lidar" / f"{scan_id}.json"
    if not path.is_file():
        return np.zeros((0, 9), dtype=np.float32)
    boxes, _, _ = _boxes_to_arrays(read_frame_boxes(path), speed_mps)
    return boxes


def _region_mask(
    xyz: np.ndarray, box: np.ndarray, road_z: float
) -> np.ndarray:
    """Mask A3-V: 0–60 m sau box, |y| ≤ 5 m, 0 ≤ z − road_z ≤ 3 m."""

    if xyz.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    center_x = float(box[0])
    length = float(box[3])
    rear_x = center_x - length / 2.0
    depth = rear_x - xyz[:, 0]
    height = xyz[:, 2] - road_z
    return (
        (depth >= 0.0)
        & (depth < REGION_DEPTH_M)
        & (np.abs(xyz[:, 1]) <= REGION_HALF_WIDTH_M)
        & (height >= REGION_HEIGHT_MIN_M)
        & (height <= REGION_HEIGHT_MAX_M)
    )


def measure_scene(
    scene: dict,
    root: Path,
    frames_per_scene: int,
    spawn_scale: float = 1.0,
) -> dict:
    """Đo một scene theo metric A3-V (paired real/generated, vùng 0–60 m).

    ``spawn_scale`` chỉ nhân tốc độ phát cụm (núm production sẵn có, default
    1,0) — dùng cho fit D2-v2; không đổi mặc định.
    """

    scene_dir = root / scene["rel_path"]
    scan_ids = sorted(path.stem for path in (scene_dir / "velodyne").glob("*.bin"))
    indices = _sample_scene_indices(len(scan_ids), frames_per_scene)
    object_speed_mps = scene["speed_kmh"] / 3.6
    ego_speed_mps = scene["ego_kmh"] / 3.6
    state = PlumeState(PlumeStateConfig(spawn_scale=float(spawn_scale)))
    config = PlumeConfig()
    table = load_beam_table()

    n_bins = len(DEPTH_BIN_EDGES_M) - 1
    real_profile = np.zeros(n_bins, dtype=np.float64)
    gen_profile = np.zeros(n_bins, dtype=np.float64)
    frame_rows: list[dict] = []
    for position, index in enumerate(indices):
        scan_id = scan_ids[index]
        points = np.fromfile(
            scene_dir / "velodyne" / f"{scan_id}.bin", dtype=np.float32
        ).reshape(-1, 5)
        labels = np.fromfile(
            scene_dir / "labels" / f"{scan_id}.label", dtype=np.uint32
        )
        if labels.size != points.shape[0]:
            continue

        if scene["has_box"]:
            boxes = _human_boxes(scene_dir, scan_id, object_speed_mps)
            road_z = (
                float(np.median(boxes[:, 2]))
                if len(boxes)
                else float(np.percentile(points[:, 2], 5.0))
            )
        else:
            boxes = _pseudo_box_from_vehicle_points(
                points, labels, scene["vehicle_class"]
            )
            road_z = float(np.percentile(points[:, 2], 5.0))
        if boxes is None or len(boxes) == 0:
            continue
        box = np.asarray(boxes[0], dtype=np.float64)

        clean = points[labels != SPRAY_LABEL].astype(np.float32)
        context = PlumeContext(
            scene_token=scene["rel_path"],
            frame_index=position,
            epoch=0,
            sensor_origin=np.zeros(3, dtype=np.float64),
            ego_speed_mps=ego_speed_mps,
            object_speed_mps=object_speed_mps,
            wfh_mm=1.0,
            road_z_m=road_z,
        )
        result = inject_plume_stateful(
            clean,
            boxes,
            context,
            state,
            seed=FIXED_SEED,
            token=f"follow/{scene['rel_path']}/{position}",
            config=config,
            vehicle_class=scene["vehicle_class"],
        )
        ray = raycast_frame(
            result.points_clean,
            state.all_alive(),
            table=table,
            road_z_m=road_z,
            rng=np.random.default_rng(FIXED_SEED),
        )
        synthetic = ray.detections
        gen_xyz = synthetic[:, :3].astype(np.float64)
        point_xyz = points[:, :3].astype(np.float64)
        rear_x = float(box[0]) - float(box[3]) / 2.0

        # --- metric A3-V: cùng vùng đo cho hai vế ---
        real_region_mask = _region_mask(point_xyz, box, road_z)
        real_region_mask &= labels == SPRAY_LABEL
        gen_region_mask = _region_mask(gen_xyz, box, road_z)
        real_region = int(real_region_mask.sum())
        gen_region = int(gen_region_mask.sum())
        depth_real = rear_x - point_xyz[real_region_mask, 0]
        depth_gen = rear_x - gen_xyz[gen_region_mask, 0]
        bins_real = np.floor(depth_real / DEPTH_BIN_M).astype(np.int64)
        bins_gen = np.floor(depth_gen / DEPTH_BIN_M).astype(np.int64)
        if bins_real.size:
            real_profile += np.bincount(bins_real, minlength=n_bins)
        if bins_gen.size:
            gen_profile += np.bincount(bins_gen, minlength=n_bins)

        # --- phụ: near-field trên toàn bộ detection sinh ---
        ranges = (
            np.linalg.norm(gen_xyz, axis=1) if gen_xyz.shape[0] else np.zeros(0)
        )
        frame_rows.append(
            {
                "scan_id": scan_id,
                "real_region": real_region,
                "generated_region": gen_region,
                "ratio": (gen_region / real_region) if real_region > 0 else None,
                "near10": int((ranges < 10.0).sum()),
                "near4": int((ranges < 4.0).sum()),
                "generated_total": int(gen_xyz.shape[0]),
                "vehicle_range_m": float(np.linalg.norm(box[:3])),
            }
        )
    n_frames = max(len(frame_rows), 1)
    return {
        "scene": scene,
        "frames": frame_rows,
        "real_profile_per_frame": (real_profile / n_frames).tolist(),
        "gen_profile_per_frame": (gen_profile / n_frames).tolist(),
        "depth_bin_edges_m": list(DEPTH_BIN_EDGES_M),
    }


def _bootstrap_scene_median(
    scene_frame_ratios: list[list[float]],
) -> tuple[float, float, float]:
    """Median của toàn bộ tỉ lệ frame + CI95 bootstrap **theo scene**.

    Metric chính A3-V = median_frame(tỉ lệ). CI: resample scene (B=2000), gộp
    frame của các scene được bốc, lấy median; phân vị 2,5/97,5.
    """

    pooled = [value for ratios in scene_frame_ratios for value in ratios]
    if not pooled:
        return float("nan"), float("nan"), float("nan")
    median = float(np.median(pooled))
    if len(scene_frame_ratios) == 1:
        return median, median, median
    rng = np.random.default_rng(CI_SEED)
    boots = np.empty(BOOTSTRAP, dtype=np.float64)
    count = len(scene_frame_ratios)
    for index in range(BOOTSTRAP):
        picks = rng.integers(0, count, size=count)
        sample = [
            value
            for pick in picks
            for value in scene_frame_ratios[int(pick)]
        ]
        boots[index] = np.median(sample) if sample else np.nan
    low, high = np.nanpercentile(boots, [2.5, 97.5])
    return median, float(low), float(high)


def _summarise(results: list[dict], set_name: str) -> list[dict]:
    rows: list[dict] = []
    for band_label, band_speeds in SPEED_BANDS:
        for vehicle_class in ("crafter", "golf"):
            selected = [
                result
                for result in results
                if result["scene"]["has_box"] == (set_name == "A")
                and result["scene"]["vehicle_class"] == vehicle_class
                and result["scene"]["speed_kmh"] in band_speeds
                and result["frames"]
            ]
            if not selected:
                continue
            scene_ratios = [
                [
                    float(row["ratio"])
                    for row in result["frames"]
                    if row["ratio"] is not None
                ]
                for result in selected
            ]
            scene_ratios = [ratios for ratios in scene_ratios if ratios]
            median, low, high = _bootstrap_scene_median(scene_ratios)
            all_frames = [row for result in selected for row in result["frames"]]
            real = np.asarray(
                [row["real_region"] for row in all_frames], dtype=float
            )
            generated = np.asarray(
                [row["generated_region"] for row in all_frames], dtype=float
            )
            generated_total = sum(row["generated_total"] for row in all_frames)
            near10 = sum(row["near10"] for row in all_frames)
            near4 = sum(row["near4"] for row in all_frames)
            vehicle_ranges = np.asarray(
                [row["vehicle_range_m"] for row in all_frames], dtype=float
            )
            rows.append(
                {
                    "set": set_name,
                    "vehicle_class": vehicle_class,
                    "band": band_label,
                    "speeds_kmh": list(band_speeds),
                    "n_scene": len(selected),
                    "n_frame": len(all_frames),
                    "n_frame_ratio": sum(len(r) for r in scene_ratios),
                    "n_frame_real_zero": int((real == 0).sum()),
                    "real_region_per_frame": float(real.mean()),
                    "generated_region_per_frame": float(generated.mean()),
                    "median_frame_ratio": median,
                    "ratio_ci95": [low, high],
                    "scene_medians": [
                        float(np.median(r)) for r in scene_ratios
                    ],
                    "near10_pct": (
                        100.0 * near10 / generated_total
                        if generated_total else 0.0
                    ),
                    "near4_pct": (
                        100.0 * near4 / generated_total
                        if generated_total else 0.0
                    ),
                    "vehicle_range_p5_m": float(
                        np.percentile(vehicle_ranges, 5)
                    ),
                    "vehicle_range_p50_m": float(
                        np.percentile(vehicle_ranges, 50)
                    ),
                    "vehicle_range_p95_m": float(
                        np.percentile(vehicle_ranges, 95)
                    ),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", default=str(REPO / "data" / "SemanticSprayDataset")
    )
    parser.add_argument(
        "--frames-per-scene",
        type=int,
        default=30,
        help="số frame cách đều mỗi scene (0 = tất cả)",
    )
    parser.add_argument(
        "--limit-scenes",
        type=int,
        default=0,
        help="chỉ chạy N scene mỗi tập (smoke)",
    )
    parser.add_argument(
        "--sets", default="AB", help="tập cần đo: A (36 boxed), B (unboxed), AB"
    )
    parser.add_argument(
        "--spawn-scale",
        type=float,
        default=1.0,
        help="D2-v2: nhân tốc độ phát cụm (núm production sẵn có; default 1,0)",
    )
    parser.add_argument(
        "--split",
        choices=("all", "fit", "verify"),
        default="all",
        help="fit 2/3 – verify 1/3, phân tầng (lớp × nhóm tốc độ), tất định",
    )
    parser.add_argument(
        "--out",
        default=str(REPO / ".scratch/tmp/following_scenario.json"),
    )
    args = parser.parse_args()
    root = Path(args.root)
    scenes = _scene_meta(root)
    boxed = [scene for scene in scenes if scene["has_box"]]
    # Tập B: 4 scene/(group, tốc độ) ⇒ ≥20 scene/nhóm, cả 2 lớp. Không RNG.
    sample_b = build_sample_b(scenes)
    split = split_fit_verify(sample_b)
    if args.split != "all":
        sample_b = split[args.split]
        print(
            f"SPLIT {args.split}: {len(sample_b)} scene "
            f"(fit={len(split['fit'])}, verify={len(split['verify'])})",
            flush=True,
        )

    sets: dict[str, list[dict]] = {}
    if "A" in args.sets:
        sets["A"] = boxed
    if "B" in args.sets:
        sets["B"] = sample_b
    if args.limit_scenes > 0:
        sets = {
            name: members[: args.limit_scenes] for name, members in sets.items()
        }

    all_results: list[dict] = []
    for set_name, members in sets.items():
        print(
            f"TẬP {set_name}: {len(members)} scene, "
            f"{args.frames_per_scene or 'tất cả'} frame/scene",
            flush=True,
        )
        for position, scene in enumerate(members, start=1):
            result = measure_scene(
                scene,
                root,
                args.frames_per_scene,
                spawn_scale=args.spawn_scale,
            )
            all_results.append(result)
            ratios = [
                row["ratio"] for row in result["frames"]
                if row["ratio"] is not None
            ]
            print(
                f"  [{position}/{len(members)}] {scene['rel_path']} "
                f"{scene['speed_kmh']:.0f} km/h "
                f"frames={len(result['frames'])} "
                f"ratio_mean={np.mean(ratios) if ratios else float('nan'):.2f}",
                flush=True,
            )

    summary: list[dict] = []
    for set_name in sets:
        summary.extend(_summarise(all_results, set_name))

    print()
    header = (
        f"{'set':>3} {'class':>7} {'band':>8} {'scene':>5} {'frame':>6} "
        f"{'real/f':>8} {'gen/f':>8} {'median':>7} {'CI95':>16} "
        f"{'<10m':>6} {'<4m':>6} {'zero-real':>9} {'veh range p5/p50/p95':>22}"
    )
    print(header)
    for row in summary:
        print(
            f"{row['set']:>3} {row['vehicle_class']:>7} {row['band']:>8} "
            f"{row['n_scene']:>5} {row['n_frame']:>6} "
            f"{row['real_region_per_frame']:>8.1f} "
            f"{row['generated_region_per_frame']:>8.1f} "
            f"{row['median_frame_ratio']:>7.2f} "
            f"[{row['ratio_ci95'][0]:>6.2f}; {row['ratio_ci95'][1]:>6.2f}] "
            f"{row['near10_pct']:>5.1f}% {row['near4_pct']:>5.1f}% "
            f"{row['n_frame_real_zero']:>9} "
            f"{row['vehicle_range_p5_m']:>6.1f}/"
            f"{row['vehicle_range_p50_m']:.1f}/"
            f"{row['vehicle_range_p95_m']:.1f}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "generated_by": "scripts/measure_following_scenario.py",
                "scenario": "following (context per real SSPP frame)",
                "note": (
                    "T5 kiểm chứng, không tune. A=36 scene có human box (eval); "
                    "B=2 scene/(group,tốc độ) trong 171 scene không box."
                ),
                "fixed_seed": FIXED_SEED,
                "spawn_scale": args.spawn_scale,
                "split": args.split,
                "bootstrap": BOOTSTRAP,
                "frames_per_scene": args.frames_per_scene,
                "summary": summary,
                "scenes": [
                    {
                        "rel_path": result["scene"]["rel_path"],
                        "speed_kmh": result["scene"]["speed_kmh"],
                        "vehicle_class": result["scene"]["vehicle_class"],
                        "has_box": result["scene"]["has_box"],
                        "frames": result["frames"],
                        "real_profile_per_frame": result[
                            "real_profile_per_frame"
                        ],
                        "gen_profile_per_frame": result[
                            "gen_profile_per_frame"
                        ],
                        "depth_bin_edges_m": result["depth_bin_edges_m"],
                    }
                    for result in all_results
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nFOLLOWING_WRITTEN path={out}")


if __name__ == "__main__":
    main()
