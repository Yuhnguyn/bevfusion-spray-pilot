#!/usr/bin/env python3
"""Bảng ``cụm/frame`` SSPP tính theo fold — không leak, có CI95 ở mức scene.

Vì sao có script này (ADR-0006 D1/D2, chẩn đoán **V2**): bảng
``_CLUSTER_VISIBLE_BY_SPEED`` trong ``spray/plume.py`` đo trên SSPP ``cal``, mà
``cal`` chứa **6/12 scene test** của split cũ ⇒ tham số generator được chọn trên
chính scene sẽ chấm. Script này tính lại bảng đó, nhưng:

* **theo fold của protocol 3-fold leave-speed-out** (ADR-0006 D1) trên 36 scene
  có human box: rule tất định ``fold = rank(speed)+1`` với ``rank`` đếm từ 0 trên
  9 tốc độ 50…130 km/h (0-based: ``rank(speed) mod 3 + 1``). Mỗi fold test 12
  scene (4 scene/tốc độ × 3 tốc độ), 24 scene train;
* **bảng của fold k không chứa bất kỳ scene test nào của fold k**: ở tốc độ
  held-out của fold k, 4 scene có box đều là scene test nên bị loại; ô còn lại
  10 scene (đều không box, ``itr_after_water`` 2–6);
* **recipe đo giữ y nguyên** như bảng cũ ``docs/measurements/
  semantic-spray-clusters-by-speed.md``: chỉ điểm ``label == 2``; DBSCAN trên
  mặt phẳng ``(azimuth, elevation)`` với ``eps = 0,7°``, ``minPts = 3``,
  elevation snap ``0,333°``, azimuth wrap — gọi thẳng
  :func:`spray.semantic_stats.cluster_angular`; 15 frame cách đều mỗi scene;
* **CI95 = percentile bootstrap ở mức scene** (resample scene, không resample
  frame), B = 2000, seed cố định: frame trong cùng scene không độc lập
  (ICC 0,14 — ``.scratch/roadspray-cal/power-design.md`` §1).

Phạm vi: **toàn bộ 207 scene** của ``data/SemanticSprayDataset`` (17 419 frame).
Chỉ 36 scene có human box; 171 scene còn lại là dữ liệu train (pseudo-box,
``itr_after_water`` 2–6). Dùng chúng để mỗi ô đạt 10–12 scene / 150–180 frame;
nếu chỉ dùng 24 scene train có box thì mỗi ô chỉ có 2 scene / 30 frame.

Các chế độ::

    # Kiểm tra cấu trúc fold + no-leak (nhanh, không đọc point cloud)
    CONDA_NO_PLUGINS=true env -u PYTHONPATH PYTHONPATH=. /opt/anaconda3/bin/python \
        scripts/sspp_cluster_table_folds.py --check

    # Chạy đủ: đo 207 scene × 15 frame, in bảng markdown + JSON
    ... scripts/sspp_cluster_table_folds.py --json-out /tmp/folds.json \
        --md-out /tmp/folds.md --cache /tmp/folds-cache.json

    # Kiểm chéo file đã đo: mọi ô của fold k không chứa scene test của fold k
    ... scripts/sspp_cluster_table_folds.py --check --measured /tmp/folds.json

    # Dựng lại bảng 45-frame cũ (cal 15 frame/scene) để so sánh
    ... scripts/sspp_cluster_table_folds.py --compare-old --cache /tmp/folds-cache.json

Marker: ``FOLDS_CHECK_OK`` / ``FOLDS_CHECK_FAIL`` / ``FOLDS_MEASURE_OK``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:  # cho phép chạy trực tiếp từ mọi cwd
    sys.path.insert(0, str(REPO))

from spray.semantic_stats import cluster_angular  # noqa: E402
from spray.semantic_split import (  # noqa: E402
    ROLE_CAL,
    assign_roles,
    read_dataset,
)
from spray.sspp_adapter import (  # noqa: E402
    object_speed_kmh,
    read_frame_boxes,
    read_metadata,
)

GROUPS = ("Crafter_dynamic", "Golf_dynamic")
CLASS_BY_GROUP = {"Crafter_dynamic": "crafter", "Golf_dynamic": "golf"}
GROUP_BY_CLASS = {value: key for key, value in CLASS_BY_GROUP.items()}
SPEEDS_KMH = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)
FOLDS = (1, 2, 3)

FOLD_RULE = "fold = rank(speed) mod 3 + 1 (rank 0-based trên 9 tốc độ 50..130)"
NOISE_LABEL = 2
ANGULAR_EPS_DEG = 0.7
MIN_PTS = 3
DEFAULT_FRAMES_PER_SCENE = 15
DEFAULT_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20261118
CACHE_VERSION = 1

# 36 scene human box / 2587 frame chia theo fold, [ĐO] khớp plan.md §E1.
EXPECTED_TEST_FRAMES = {1: 886, 2: 893, 3: 808}

# Bảng cũ đã commit — docs/measurements/semantic-spray-clusters-by-speed.md Bảng 1
# (SSPP `cal`, 15 frame/scene × 3 scene/ô, DBSCAN 0,7°/minPts 3). 45 frame/ô.
OLD_TABLE_45 = {
    "crafter": {
        50.0: 4.18,
        60.0: 11.31,
        70.0: 17.42,
        80.0: 22.02,
        90.0: 20.69,
        100.0: 29.24,
        110.0: 28.49,
        120.0: 17.58,
        130.0: 17.69,
    },
    "golf": {
        50.0: 3.62,
        60.0: 8.84,
        70.0: 11.36,
        80.0: 12.87,
        90.0: 10.51,
        100.0: 18.07,
        110.0: 16.69,
        120.0: 15.27,
        130.0: 16.64,
    },
}

# Bảng RoadSpray `*_static` (calibration độc lập, ADR-0006 D2) —
# docs/measurements/roadspray-static-clusters-by-speed.md §4, chỉ Crafter,
# itr_after_water = 1, 18 bag / 295 frame.
STATIC_TABLE_CRAFTER = {
    70.0: 19.8,
    80.0: 29.3,
    90.0: 31.4,
    100.0: 28.1,
    110.0: 30.2,
    120.0: 15.0,
    130.0: 24.2,
}


# ---------------------------------------------------------------------------
# Fold rule (ADR-0006 D1) + sampling
# ---------------------------------------------------------------------------


def speed_rank(speed_kmh: float) -> int:
    """Rank 0-based của ``speed_kmh`` trong 9 mốc 50…130."""

    try:
        return SPEEDS_KMH.index(float(speed_kmh))
    except ValueError as exc:
        raise ValueError(
            f"tốc độ {speed_kmh!r} không nằm trong 9 mốc 50..130 km/h"
        ) from exc


def fold_for_speed(speed_kmh: float) -> int:
    """``fold = rank(speed) mod 3 + 1`` — rule tất định của ADR-0006 D1.

    ``rank`` đếm từ 0 trên 9 tốc độ 50…130 km/h (tăng dần). Cho ra fold 1
    ``{50, 80, 110}``, fold 2 ``{60, 90, 120}``, fold 3 ``{70, 100, 130}`` —
    đúng bảng E1 của ``.scratch/roadspray-cal/plan.md``.
    """

    return speed_rank(speed_kmh) % 3 + 1


def speeds_for_fold(fold: int) -> tuple[float, ...]:
    if fold not in FOLDS:
        raise ValueError(f"fold không hợp lệ: {fold!r}")
    return tuple(speed for speed in SPEEDS_KMH if fold_for_speed(speed) == fold)


def sample_frame_indices(n_frames: int, count: int) -> list[int]:
    """``count`` chỉ số frame cách đều trong ``[0, n_frames)``, giống bảng cũ.

    Dùng ``np.linspace(0, n-1, count)`` rồi làm tròn (frame đầu và cuối luôn có
    mặt); nếu scene ngắn hơn ``count`` thì lấy hết, không lặp.
    """

    if n_frames <= 0:
        raise ValueError(f"scene không có frame: n_frames={n_frames}")
    if count <= 0:
        raise ValueError(f"count phải > 0, nhận {count!r}")
    if count >= n_frames:
        return list(range(n_frames))
    picks = np.linspace(0.0, float(n_frames - 1), int(count)).round().astype(int)
    return sorted({int(index) for index in picks.tolist()})


# ---------------------------------------------------------------------------
# Inventory: 207 scene, speed, itr, frame, scene nào có human box
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SceneInfo:
    rel_path: str
    group: str
    class_name: str
    speed_kmh: float
    itr_after_water: int
    distance_to_object_m: float
    n_frames: int
    boxed_frames: tuple[str, ...]

    @property
    def has_box(self) -> bool:
        return bool(self.boxed_frames)


def _boxed_frame_ids(scene_dir: Path) -> tuple[str, ...]:
    """Frame có ít nhất một box Car/Van — cùng luật ``build_sspp_split``."""

    labels_dir = scene_dir / "object_labels" / "lidar"
    if not labels_dir.is_dir():
        return ()
    return tuple(
        path.stem
        for path in sorted(labels_dir.glob("*.json"), key=lambda item: item.name)
        if read_frame_boxes(path)
    )


def read_scene_inventory(root: str | Path) -> list[SceneInfo]:
    """Đọc metadata + đếm frame + box cho mọi scene của 2 group."""

    root = Path(root)
    scenes: list[SceneInfo] = []
    for group in GROUPS:
        group_dir = root / group
        if not group_dir.is_dir():
            raise FileNotFoundError(f"missing dataset group: {group_dir}")
        for scene_dir in sorted(
            (path for path in group_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        ):
            metadata = read_metadata(scene_dir / "metadata.txt")
            speed = float(round(object_speed_kmh(metadata)))
            if speed not in SPEEDS_KMH:
                raise ValueError(
                    f"{group}/{scene_dir.name}: tốc độ {speed} không thuộc "
                    f"9 mốc 50..130"
                )
            scan_ids = sorted(
                path.stem for path in (scene_dir / "velodyne").glob("*.bin")
            )
            if not scan_ids:
                raise FileNotFoundError(f"scene không có frame: {scene_dir}")
            scenes.append(
                SceneInfo(
                    rel_path=f"{group}/{scene_dir.name}",
                    group=group,
                    class_name=CLASS_BY_GROUP[group],
                    speed_kmh=speed,
                    itr_after_water=int(metadata["itr_after_water"]),
                    distance_to_object_m=float(
                        metadata["distance_to_object"]
                    ),
                    n_frames=len(scan_ids),
                    boxed_frames=_boxed_frame_ids(scene_dir),
                )
            )
    scenes.sort(key=lambda scene: scene.rel_path)
    return scenes


def inventory_by_path(scenes: list[SceneInfo]) -> dict[str, SceneInfo]:
    return {scene.rel_path: scene for scene in scenes}


def fold_test_scenes(scenes: list[SceneInfo], fold: int) -> list[SceneInfo]:
    """12 scene test của fold ``k``: scene có box ở 3 tốc độ held-out."""

    held = set(speeds_for_fold(fold))
    return [scene for scene in scenes if scene.has_box and scene.speed_kmh in held]


def fold_train_scenes(scenes: list[SceneInfo], fold: int) -> list[SceneInfo]:
    """24 scene train có box của fold ``k`` (cùng 36 scene eval)."""

    held = set(speeds_for_fold(fold))
    return [
        scene
        for scene in scenes
        if scene.has_box and scene.speed_kmh not in held
    ]


# ---------------------------------------------------------------------------
# Kế hoạch đo: mỗi fold, mỗi (class, speed) dùng scene nào
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellPlan:
    group: str
    class_name: str
    speed_kmh: float
    fold_holdout: int
    scenes: tuple[str, ...]  # scene được phép dùng cho ô này trong fold này

    @property
    def n_scene(self) -> int:
        return len(self.scenes)


def build_fold_plan(
    scenes: list[SceneInfo],
) -> dict[int, dict[tuple[str, float], CellPlan]]:
    """Với mỗi fold, lập danh sách scene được phép dùng cho từng ô.

    Bảng của fold ``k`` chỉ được dùng scene **không thuộc test set của fold k**.
    Test set của fold k = 12 scene có box ở 3 tốc độ held-out (theo ADR-0006
    D1). Vì vậy:

    * ô ở tốc độ held-out: 2 scene có box đã bị loại ⇒ còn 10 scene không box;
    * ô ở tốc độ khác: dùng cả 12 scene (scene có box ở tốc độ đó thuộc các
      fold khác, không thuộc test set của fold k).
    """

    plan: dict[int, dict[tuple[str, float], CellPlan]] = {}
    for fold in FOLDS:
        test_paths = {scene.rel_path for scene in fold_test_scenes(scenes, fold)}
        cells: dict[tuple[str, float], CellPlan] = {}
        for group in GROUPS:
            class_name = CLASS_BY_GROUP[group]
            for speed in SPEEDS_KMH:
                allowed = tuple(
                    scene.rel_path
                    for scene in scenes
                    if scene.group == group
                    and scene.speed_kmh == speed
                    and scene.rel_path not in test_paths
                )
                cells[(group, speed)] = CellPlan(
                    group=group,
                    class_name=class_name,
                    speed_kmh=speed,
                    fold_holdout=fold_for_speed(speed),
                    scenes=allowed,
                )
        plan[fold] = cells
    return plan


def plan_cell_frames(
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    info: dict[str, SceneInfo],
    frames_per_scene: int,
) -> dict[int, dict[tuple[str, float], int]]:
    """Số frame mỗi ô sẽ đo (không đọc point cloud)."""

    counts: dict[int, dict[tuple[str, float], int]] = {}
    for fold, cells in plan.items():
        counts[fold] = {
            key: sum(
                len(
                    sample_frame_indices(
                        info[rel_path].n_frames, frames_per_scene
                    )
                )
                for rel_path in cell.scenes
            )
            for key, cell in cells.items()
        }
    return counts


def verify_plan(
    scenes: list[SceneInfo],
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    frames_per_scene: int,
) -> list[str]:
    """Kiểm tra cấu trúc fold + no-leak. Trả ``[]`` nếu mọi thứ đúng.

    Bất biến được kiểm:
    1. rule fold khớp ADR-0006: fold k có đúng 3 tốc độ, và hợp 3 fold = 9 tốc
       độ, rời nhau;
    2. 36 scene có box, mỗi fold test 12 scene, 24 scene train; 12 scene test
       rời nhau và hợp lại đủ 36 (mỗi scene test đúng một lần);
    3. với **mọi** fold k và **mọi** ô, tập scene được dùng không giao với 12
       scene test của fold k (đây là điều kiện không leak);
    4. ô ở tốc độ held-out có 10 scene (trừ Golf 80/90 của dataset chỉ có 8/7
       scene), ô khác 12 scene; số frame = n_scene × ``frames_per_scene``
       (scene ngắn hơn thì lấy hết).
    """

    problems: list[str] = []
    boxed = [scene for scene in scenes if scene.has_box]
    if len(boxed) != 36:
        problems.append(f"số scene có box = {len(boxed)}, kỳ vọng 36")

    test_sets = {fold: fold_test_scenes(scenes, fold) for fold in FOLDS}
    seen: dict[str, int] = {}
    for fold in FOLDS:
        held = set(speeds_for_fold(fold))
        if len(held) != 3:
            problems.append(f"fold {fold}: {len(held)} tốc độ held-out, kỳ vọng 3")
        for scene in test_sets[fold]:
            if scene.speed_kmh not in held:
                problems.append(
                    f"fold {fold}: scene test {scene.rel_path} có tốc độ "
                    f"{scene.speed_kmh} không held-out"
                )
            seen[scene.rel_path] = seen.get(scene.rel_path, 0) + 1
        if len(test_sets[fold]) != 12:
            problems.append(
                f"fold {fold}: {len(test_sets[fold])} scene test, kỳ vọng 12"
            )
        train = fold_train_scenes(scenes, fold)
        if len(train) != 24:
            problems.append(
                f"fold {fold}: {len(train)} scene train có box, kỳ vọng 24"
            )
    duplicated = sorted(path for path, count in seen.items() if count > 1)
    if duplicated:
        problems.append(f"scene bị test nhiều lần: {duplicated[:5]}")
    if set(seen) != {scene.rel_path for scene in boxed}:
        problems.append("tập scene test 3 fold không phủ đủ 36 scene có box")

    info = inventory_by_path(scenes)
    expected_n_scene = {
        (group, speed): sum(
            1 for scene in scenes if scene.group == group and scene.speed_kmh == speed
        )
        for group in GROUPS
        for speed in SPEEDS_KMH
    }
    for fold in FOLDS:
        test_paths = {scene.rel_path for scene in test_sets[fold]}
        for (group, speed), cell in plan[fold].items():
            total = expected_n_scene[(group, speed)]
            # 2 scene có box mỗi (group, tốc độ); bị loại khi tốc độ held-out.
            expect = total - 2 if fold_for_speed(speed) == fold else total
            if cell.n_scene != expect:
                problems.append(
                    f"fold {fold} {CLASS_BY_GROUP[group]} {speed:.0f}: "
                    f"{cell.n_scene} scene, kỳ vọng {expect}"
                )
            leaked = sorted(test_paths.intersection(cell.scenes))
            if leaked:
                problems.append(
                    f"LEAK fold {fold} {CLASS_BY_GROUP[group]} {speed:.0f}: "
                    f"{len(leaked)} scene test lọt vào bảng ({leaked[:3]})"
                )
            if cell.n_scene == 0:
                problems.append(
                    f"fold {fold} {CLASS_BY_GROUP[group]} {speed:.0f}: ô rỗng"
                )
            if fold_for_speed(speed) == fold:
                boxed_used = [
                    rel_path for rel_path in cell.scenes if info[rel_path].has_box
                ]
                if boxed_used:
                    problems.append(
                        f"fold {fold} {CLASS_BY_GROUP[group]} {speed:.0f}: "
                        f"tốc độ held-out nhưng vẫn dùng scene có box "
                        f"({boxed_used[:3]})"
                    )
    return problems


# ---------------------------------------------------------------------------
# Đo: 207 scene × frames_per_scene, cache JSON
# ---------------------------------------------------------------------------


def _recipe_signature(frames_per_scene: int) -> dict:
    return {
        "noise_label": NOISE_LABEL,
        "eps_deg": ANGULAR_EPS_DEG,
        "min_pts": MIN_PTS,
        "frames_per_scene": int(frames_per_scene),
    }


def measure_scene(
    scene: SceneInfo,
    root: Path,
    frames_per_scene: int,
) -> dict:
    """Đo một scene: cụm/frame + noise/frame cho các frame được sample."""

    scene_dir = root / scene.rel_path
    scan_ids = sorted(
        path.stem for path in (scene_dir / "velodyne").glob("*.bin")
    )
    indices = sample_frame_indices(len(scan_ids), frames_per_scene)
    frames = []
    dropped = 0
    for index in indices:
        scan_id = scan_ids[index]
        points = np.fromfile(
            scene_dir / "velodyne" / f"{scan_id}.bin", dtype=np.float32
        ).reshape(-1, 5)
        labels = np.fromfile(
            scene_dir / "labels" / f"{scan_id}.label", dtype=np.uint32
        )
        if labels.size != points.shape[0]:
            dropped += 1
            continue
        noise = points[labels == NOISE_LABEL][:, :3].astype(np.float64)
        if noise.shape[0] < MIN_PTS:
            n_clusters = 0
        else:
            cluster_ids = cluster_angular(
                noise, eps_deg=ANGULAR_EPS_DEG, min_pts=MIN_PTS
            )
            n_clusters = int(
                len(np.unique(cluster_ids[cluster_ids >= 0]))
            )
        frames.append(
            {
                "scan_id": scan_id,
                "n_noise": int(noise.shape[0]),
                "n_clusters": n_clusters,
            }
        )
    return {"frames": frames, "n_frame_dropped": dropped}


def load_cache(path: Path, recipe: dict) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if document.get("version") != CACHE_VERSION:
        return {}
    if document.get("recipe") != recipe:
        return {}
    scenes = document.get("scenes")
    return scenes if isinstance(scenes, dict) else {}


def save_cache(path: Path, recipe: dict, scenes: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"version": CACHE_VERSION, "recipe": recipe, "scenes": scenes}
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def measure_all(
    scenes: list[SceneInfo],
    root: Path,
    frames_per_scene: int,
    cache_path: Path | None,
    quiet: bool = False,
) -> dict[str, dict]:
    """Đo mọi scene, dùng cache nếu có (cache hit bỏ qua đọc point cloud)."""

    recipe = _recipe_signature(frames_per_scene)
    measured: dict[str, dict] = (
        load_cache(cache_path, recipe) if cache_path is not None else {}
    )
    todo = [scene for scene in scenes if scene.rel_path not in measured]
    if not quiet:
        print(
            f"MEASURE_START scenes={len(scenes)} cached={len(scenes) - len(todo)} "
            f"frames_per_scene={frames_per_scene} "
            f"recipe=label{NOISE_LABEL}/eps{ANGULAR_EPS_DEG}/minPts{MIN_PTS}",
            flush=True,
        )
    started = time.time()
    for position, scene in enumerate(todo, start=1):
        measured[scene.rel_path] = measure_scene(
            scene, root, frames_per_scene
        )
        if not quiet and (position % 20 == 0 or position == len(todo)):
            elapsed = time.time() - started
            rate = position / elapsed if elapsed > 0 else 0.0
            print(
                f"MEASURE scene {position}/{len(todo)} "
                f"({scene.rel_path}) elapsed={elapsed:.1f}s "
                f"rate={rate:.1f} scene/s",
                flush=True,
            )
        if cache_path is not None and position % 20 == 0:
            save_cache(cache_path, recipe, measured)
    if cache_path is not None:
        save_cache(cache_path, recipe, measured)
    n_frames = sum(len(item["frames"]) for item in measured.values())
    n_dropped = sum(item["n_frame_dropped"] for item in measured.values())
    if not quiet:
        print(
            f"MEASURE_OK scenes={len(measured)} frames={n_frames} "
            f"dropped={n_dropped} seconds={time.time() - started:.1f}",
            flush=True,
        )
    return measured


# ---------------------------------------------------------------------------
# Thống kê ô: frame-pooled mean + bootstrap mức scene
# ---------------------------------------------------------------------------


def scene_pairs(
    rel_paths: list[str] | tuple[str, ...],
    measured: dict[str, dict],
) -> tuple[np.ndarray, np.ndarray]:
    """``(n_frame_i, tổng cụm_i)`` cho từng scene."""

    n_frames = []
    sums = []
    for rel_path in rel_paths:
        frames = measured[rel_path]["frames"]
        n_frames.append(len(frames))
        sums.append(sum(frame["n_clusters"] for frame in frames))
    return (
        np.asarray(n_frames, dtype=np.float64),
        np.asarray(sums, dtype=np.float64),
    )


def pooled_mean(n_frames: np.ndarray, sums: np.ndarray) -> float:
    total = float(n_frames.sum())
    if total <= 0.0:
        raise ValueError("ô không có frame nào")
    return float(sums.sum() / total)


def bootstrap_pooled_ci(
    n_frames: np.ndarray,
    sums: np.ndarray,
    bootstrap: int,
    seed: int,
) -> tuple[float, float]:
    """Percentile bootstrap 95 % resample **scene** (frame-pooled mean).

    Mỗi replicate bốc ``n`` scene có hoàn lại (multinomial), tính lại mean gộp
    theo frame trên các scene được bốc. Không resample frame.
    """

    n_scene = int(n_frames.size)
    if n_scene == 0:
        raise ValueError("ô không có scene nào")
    if n_scene == 1:
        value = pooled_mean(n_frames, sums)
        return value, value
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(
        n_scene, np.full(n_scene, 1.0 / n_scene), size=int(bootstrap)
    ).astype(np.float64)
    totals = counts @ n_frames
    sums_boot = counts @ sums
    values = sums_boot / totals
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


@dataclass
class SubCell:
    """Một ô (class × tốc độ) trên một tập scene xác định."""

    scenes: tuple[str, ...]
    n_scene: int
    n_frame: int
    mean: float
    ci_low: float
    ci_high: float
    mean_noise: float
    cv_scene: float
    scene_means: dict[str, float]
    n_frame_dropped: int

    @property
    def ci_half_width_pct(self) -> float:
        if self.mean == 0.0:
            return 0.0
        return 100.0 * 0.5 * (self.ci_high - self.ci_low) / self.mean

    def to_json(self) -> dict:
        return {
            "scenes": list(self.scenes),
            "n_scene": self.n_scene,
            "n_frame": self.n_frame,
            "mean_clusters_per_frame": self.mean,
            "ci95": [self.ci_low, self.ci_high],
            "ci95_half_width_pct": self.ci_half_width_pct,
            "mean_noise_per_frame": self.mean_noise,
            "cv_scene": self.cv_scene,
            "scene_means": dict(sorted(self.scene_means.items())),
            "n_frame_dropped": self.n_frame_dropped,
        }


def compute_subcell(
    rel_paths: tuple[str, ...] | list[str],
    measured: dict[str, dict],
    bootstrap: int,
    seed: int,
) -> SubCell:
    paths = tuple(rel_paths)
    if not paths:
        raise ValueError("ô không có scene nào")
    n_frames, sums = scene_pairs(paths, measured)
    means = np.divide(
        sums,
        n_frames,
        out=np.full_like(sums, np.nan),
        where=n_frames > 0,
    )
    scene_means = {
        rel_path: float(value)
        for rel_path, value in zip(paths, means)
        if math.isfinite(value)
    }
    mean_noise = float(
        np.mean(
            [
                np.mean([frame["n_noise"] for frame in measured[path]["frames"]])
                for path in paths
                if measured[path]["frames"]
            ]
        )
    )
    cv_scene = (
        float(np.std(means) / np.mean(means))
        if means.size > 1 and np.mean(means) > 0.0
        else 0.0
    )
    ci_low, ci_high = bootstrap_pooled_ci(n_frames, sums, bootstrap, seed)
    return SubCell(
        scenes=paths,
        n_scene=len(paths),
        n_frame=int(n_frames.sum()),
        mean=pooled_mean(n_frames, sums),
        ci_low=ci_low,
        ci_high=ci_high,
        mean_noise=mean_noise,
        cv_scene=cv_scene,
        scene_means=scene_means,
        n_frame_dropped=sum(
            measured[path]["n_frame_dropped"] for path in paths
        ),
    )


def _cell_seed(fold: int | str, class_name: str, speed_kmh: float) -> int:
    """Seed ổn định cho từng ô (để chạy lại ra đúng số)."""

    key = f"{fold}|{class_name}|{speed_kmh:.0f}"
    checksum = 0
    for char in key.encode("utf-8"):
        checksum = (checksum * 131 + char) % 2_000_000_011
    return (BOOTSTRAP_SEED + checksum) % 2**32


def combined_fold_bootstrap_ci(
    all_sub: SubCell,
    non_box_sub: SubCell,
    measured: dict[str, dict],
    holdout_fold: int,
    bootstrap: int,
    seed: int,
) -> tuple[float, float]:
    """CI95 cho "gộp 3 fold" = trung bình 3 giá trị bảng fold.

    Với một ô (class, tốc độ ``v``), giá trị trong bảng của fold ``k`` là:
    * fold ``fold(v)`` (fold test đúng tốc độ này): 10 scene không box;
    * 2 fold còn lại: cả 12 scene.
    Trung bình 3 fold = (2·all + non_box)/3. Bootstrap dùng **cùng một lần
    resample scene** cho cả 3 fold (để giữ tương quan giữa các fold), rồi lấy
    phân vị 2,5 / 97,5 của trung bình.
    """

    scene_paths = tuple(sorted(all_sub.scenes))
    index = {path: position for position, path in enumerate(scene_paths)}
    n_scene = len(scene_paths)
    n_frames = np.zeros(n_scene, dtype=np.float64)
    sums = np.zeros(n_scene, dtype=np.float64)
    for position, path in enumerate(scene_paths):
        frames = measured[path]["frames"]
        n_frames[position] = float(len(frames))
        sums[position] = float(
            sum(frame["n_clusters"] for frame in frames)
        )
    mask_non_box = np.zeros(n_scene, dtype=np.float64)
    for path in non_box_sub.scenes:
        mask_non_box[index[path]] = 1.0
    mask_all = np.ones(n_scene, dtype=np.float64)
    masks = []
    for fold in FOLDS:
        masks.append(mask_non_box if fold == holdout_fold else mask_all)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(
        n_scene, np.full(n_scene, 1.0 / n_scene), size=int(bootstrap)
    ).astype(np.float64)
    fold_values = []
    fold_totals = []
    for mask in masks:
        weighted = counts * mask
        totals = weighted @ n_frames
        with np.errstate(divide="ignore", invalid="ignore"):
            values = (weighted @ sums) / totals
        fold_values.append(values)
        fold_totals.append(totals)
    combined = np.mean(np.vstack(fold_values), axis=0)
    valid = np.all(np.vstack(fold_totals) > 0.0, axis=0)
    if not valid.any():
        raise ValueError("mọi replicate bootstrap đều rỗng")
    low, high = np.percentile(combined[valid], [2.5, 97.5])
    return float(low), float(high)


@dataclass
class EvalCell:
    """Chỉ scene có human box (``itr_after_water = 1``) — điều kiện eval.

    36 scene eval đều ``itr = 1``; 10–12 scene còn lại của ô là ``itr 2–6``
    (bể nước vơi dần) nên **khô hơn**. Ô này tách riêng 2 scene/ô itr = 1 để
    so đúng điều kiện eval với bảng cũ và bảng RoadSpray static. Mẫu chỉ 2
    scene (30 frame) nên chỉ báo point estimate + dải 2 scene, không báo CI95.
    """

    scenes: tuple[str, ...]
    n_scene: int
    n_frame: int
    mean: float
    scene_means: dict[str, float]

    @property
    def value_min(self) -> float:
        return min(self.scene_means.values()) if self.scene_means else float("nan")

    @property
    def value_max(self) -> float:
        return max(self.scene_means.values()) if self.scene_means else float("nan")

    def to_json(self) -> dict:
        return {
            "scenes": list(self.scenes),
            "n_scene": self.n_scene,
            "n_frame": self.n_frame,
            "mean_clusters_per_frame": self.mean,
            "scene_means": dict(sorted(self.scene_means.items())),
            "scene_mean_min": self.value_min,
            "scene_mean_max": self.value_max,
            "itr_after_water": 1,
        }


@dataclass
class CellResult:
    group: str
    class_name: str
    speed_kmh: float
    fold_holdout: int
    all_scenes: SubCell
    non_box_scenes: SubCell
    eval_condition: EvalCell
    fold_subcells: dict[int, SubCell]
    gop_mean: float
    gop_ci_low: float
    gop_ci_high: float

    @property
    def gop(self) -> dict:
        return {
            "n_scene_by_fold": {
                str(fold): self.fold_subcells[fold].n_scene for fold in FOLDS
            },
            "mean": self.gop_mean,
            "ci95": [self.gop_ci_low, self.gop_ci_high],
            "ci95_half_width_pct": (
                100.0
                * 0.5
                * (self.gop_ci_high - self.gop_ci_low)
                / self.gop_mean
                if self.gop_mean != 0.0
                else 0.0
            ),
        }


def build_tables(
    scenes: list[SceneInfo],
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    measured: dict[str, dict],
    bootstrap: int,
) -> dict[int, dict[tuple[str, float], CellResult]]:
    """Tính mọi ô của 3 fold + bảng gộp (mean 3 fold) + CI95."""

    tables: dict[int, dict[tuple[str, float], CellResult]] = {}
    for fold in FOLDS:
        cells: dict[tuple[str, float], CellResult] = {}
        for key, cell_plan in plan[fold].items():
            group, speed = key
            all_paths = tuple(
                scene.rel_path
                for scene in scenes
                if scene.group == group and scene.speed_kmh == speed
            )
            non_box_paths = tuple(
                scene.rel_path
                for scene in scenes
                if scene.group == group
                and scene.speed_kmh == speed
                and not scene.has_box
            )
            all_sub = compute_subcell(
                all_paths,
                measured,
                bootstrap,
                _cell_seed("all", cell_plan.class_name, speed),
            )
            non_box_sub = compute_subcell(
                non_box_paths,
                measured,
                bootstrap,
                _cell_seed("nonbox", cell_plan.class_name, speed),
            )
            boxed_paths = tuple(
                scene.rel_path
                for scene in scenes
                if scene.group == group
                and scene.speed_kmh == speed
                and scene.has_box
            )
            boxed_n_frames, boxed_sums = scene_pairs(boxed_paths, measured)
            eval_condition = EvalCell(
                scenes=boxed_paths,
                n_scene=len(boxed_paths),
                n_frame=int(boxed_n_frames.sum()),
                mean=pooled_mean(boxed_n_frames, boxed_sums),
                scene_means={
                    rel_path: float(
                        sum(
                            frame["n_clusters"]
                            for frame in measured[rel_path]["frames"]
                        )
                        / len(measured[rel_path]["frames"])
                    )
                    for rel_path in boxed_paths
                },
            )
            fold_subcells = {
                fold_index: (
                    non_box_sub
                    if fold_index == fold_for_speed(speed)
                    else all_sub
                )
                for fold_index in FOLDS
            }
            gop_mean = float(
                np.mean([fold_subcells[index].mean for index in FOLDS])
            )
            gop_low, gop_high = combined_fold_bootstrap_ci(
                all_sub,
                non_box_sub,
                measured,
                fold_for_speed(speed),
                bootstrap,
                _cell_seed("gop", cell_plan.class_name, speed),
            )
            cells[key] = CellResult(
                group=group,
                class_name=cell_plan.class_name,
                speed_kmh=speed,
                fold_holdout=fold_for_speed(speed),
                all_scenes=all_sub,
                non_box_scenes=non_box_sub,
                eval_condition=eval_condition,
                fold_subcells=fold_subcells,
                gop_mean=gop_mean,
                gop_ci_low=gop_low,
                gop_ci_high=gop_high,
            )
        tables[fold] = cells
    return tables


# ---------------------------------------------------------------------------
# Dựng lại bảng 45-frame cũ (cal, 15 frame/scene) từ cache đo
# ---------------------------------------------------------------------------


def reproduce_old_table(
    scenes: list[SceneInfo],
    measured: dict[str, dict],
    root: Path,
) -> dict:
    """Dựng lại bảng cũ từ split ``cal`` (luật 29d) + 15 frame/scene.

    Bảng cũ commit không kèm script đo, nên đây là phép dựng lại trung thực
    nhất theo phần "Phương pháp" của doc: chỉ scene ``cal``, 15 frame/scene
    cách đều. Doc cũ ghi mỗi ô 45 frame = 15 × 3 scene, nên thử 3 cách đọc:
    cell 20 m, cell 30 m, và cả hai cell (6 scene).
    """

    metas = read_dataset(root)
    roles = assign_roles(metas)
    role_by_path = {meta.rel_path: roles[meta.rel_path] for meta in metas}
    cal = [
        scene
        for scene in scenes
        if role_by_path.get(scene.rel_path) == ROLE_CAL
    ]
    result: dict[str, dict] = {}
    for class_name in ("crafter", "golf"):
        result[class_name] = {}
        for speed in SPEEDS_KMH:
            entry: dict[str, float] = {}
            for distances in ((20.0,), (30.0,), (20.0, 30.0)):
                paths = tuple(
                    scene.rel_path
                    for scene in cal
                    if scene.class_name == class_name
                    and scene.speed_kmh == speed
                    and round(scene.distance_to_object_m) in distances
                )
                if not paths:
                    entry["_".join(str(int(d)) for d in distances)] = float("nan")
                    continue
                n_frames, sums = scene_pairs(paths, measured)
                entry["_".join(str(int(d)) for d in distances)] = pooled_mean(
                    n_frames, sums
                )
            result[class_name][speed] = entry
    return result


# ---------------------------------------------------------------------------
# So sánh: bảng cũ 45-frame + bảng RoadSpray static
# ---------------------------------------------------------------------------


def mean_abs_pct_delta(
    values: dict[float, float], reference: dict[float, float]
) -> tuple[float, float]:
    """(mean |Δ%|, max |Δ%|) giữa 2 bảng cùng tốc độ."""

    common = sorted(set(values) & set(reference))
    if not common:
        return float("nan"), float("nan")
    deltas = [
        abs(values[speed] - reference[speed]) / reference[speed] * 100.0
        for speed in common
        if reference[speed]
    ]
    return float(np.mean(deltas)), float(np.max(deltas))


def pearson(left: dict[float, float], right: dict[float, float]) -> float:
    common = sorted(set(left) & set(right))
    if len(common) < 3:
        return float("nan")
    x = np.array([left[speed] for speed in common], dtype=np.float64)
    y = np.array([right[speed] for speed in common], dtype=np.float64)
    if x.std() == 0.0 or y.std() == 0.0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def spearman(left: dict[float, float], right: dict[float, float]) -> float:
    common = sorted(set(left) & set(right))
    if len(common) < 3:
        return float("nan")
    x = np.array([left[speed] for speed in common], dtype=np.float64)
    y = np.array([right[speed] for speed in common], dtype=np.float64)
    rank = lambda values: np.argsort(np.argsort(values))  # noqa: E731
    return pearson(
        {speed: float(rank(x)[index]) for index, speed in enumerate(common)},
        {speed: float(rank(y)[index]) for index, speed in enumerate(common)},
    )


# ---------------------------------------------------------------------------
# Định dạng số kiểu Việt Nam (dấu phẩy thập phân, dấu chấm nghìn)
# ---------------------------------------------------------------------------


def vn(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def vn_pct(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    sign = "+" if value >= 0 else "−"
    return f"{sign}{vn(abs(value), digits)} %"


def vn_ratio(value: float | None) -> str:
    return vn(value, 2)


def ci_text(sub: SubCell) -> str:
    return f"{vn(sub.mean)} [{vn(sub.ci_low)}; {vn(sub.ci_high)}]"


# ---------------------------------------------------------------------------
# In kế hoạch / --check
# ---------------------------------------------------------------------------


def print_plan_report(
    scenes: list[SceneInfo],
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    frames_per_scene: int,
) -> None:
    boxed = [scene for scene in scenes if scene.has_box]
    print(
        f"INVENTORY scenes={len(scenes)} boxed={len(boxed)} "
        f"frames={sum(scene.n_frames for scene in scenes)} "
        f"frames_per_scene={frames_per_scene}",
        flush=True,
    )
    for fold in FOLDS:
        test = fold_test_scenes(scenes, fold)
        train = fold_train_scenes(scenes, fold)
        held = ",".join(f"{speed:.0f}" for speed in speeds_for_fold(fold))
        print(
            f"FOLD fold={fold} held_out_kmh={held} "
            f"test_scenes={len(test)} test_frames={sum(scene.n_frames for scene in test)} "
            f"train_scenes={len(train)} train_frames={sum(scene.n_frames for scene in train)} "
            f"used_scenes={len(scenes) - len(test)}",
            flush=True,
        )
        for scene in test:
            print(f"FOLD_TEST fold={fold} scene={scene.rel_path}", flush=True)
        for group in GROUPS:
            for speed in SPEEDS_KMH:
                cell = plan[fold][(group, speed)]
                frames = sum(
                    len(
                        sample_frame_indices(
                            inventory_by_path(scenes)[rel_path].n_frames,
                            frames_per_scene,
                        )
                    )
                    for rel_path in cell.scenes
                )
                if fold_for_speed(speed) == fold:
                    # Ô ở tốc độ held-out: chỉ còn scene không box (cùng tốc độ
                    # với test) ⇒ không leak scene test, nhưng không phải
                    # "speed-level holdout" — xem doc, mục "đọc chặt hơn".
                    all_non_box = all(
                        not inventory_by_path(scenes)[rel_path].has_box
                        for rel_path in cell.scenes
                    )
                    print(
                        f"FOLD_HELDOUT_CELL fold={fold} class={cell.class_name} "
                        f"kmh={speed:.0f} n_scene={cell.n_scene} "
                        f"n_frame={frames} all_non_box={int(all_non_box)} "
                        f"note=scene-level-only",
                        flush=True,
                    )
                else:
                    print(
                        f"FOLD_CELL fold={fold} class={cell.class_name} "
                        f"kmh={speed:.0f} n_scene={cell.n_scene} "
                        f"n_frame={frames}",
                        flush=True,
                    )


def check_measured_document(
    document: dict,
    scenes: list[SceneInfo],
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    frames_per_scene: int,
) -> list[str]:
    """So file JSON đã đo với kế hoạch: scene nào thực sự vào bảng mỗi ô."""

    problems: list[str] = []
    info = inventory_by_path(scenes)
    tables = document.get("tables")
    if not isinstance(tables, dict):
        return ["file measured không có khoá 'tables'"]
    for fold in FOLDS:
        key = f"fold{fold}"
        cells = tables.get(key)
        if not isinstance(cells, dict):
            problems.append(f"measured thiếu {key}")
            continue
        test_paths = {scene.rel_path for scene in fold_test_scenes(scenes, fold)}
        for class_name in ("crafter", "golf"):
            class_cells = cells.get(class_name) or {}
            for speed in SPEEDS_KMH:
                cell = class_cells.get(f"{speed:.0f}")
                if not isinstance(cell, dict):
                    problems.append(f"{key}/{class_name}/{speed:.0f}: thiếu")
                    continue
                used = list(cell.get("scenes") or [])
                if not used:
                    problems.append(f"{key}/{class_name}/{speed:.0f}: rỗng")
                    continue
                leaked = sorted(test_paths.intersection(used))
                if leaked:
                    problems.append(
                        f"LEAK {key}/{class_name}/{speed:.0f}: {len(leaked)} "
                        f"scene test lọt vào bảng ({leaked[:3]})"
                    )
                expected = plan[fold][(GROUP_BY_CLASS[class_name], speed)]
                if set(used) != set(expected.scenes):
                    problems.append(
                        f"{key}/{class_name}/{speed:.0f}: scene dùng không "
                        f"khớp kế hoạch"
                    )
                expected_frames = sum(
                    len(
                        sample_frame_indices(
                            info[rel_path].n_frames, frames_per_scene
                        )
                    )
                    for rel_path in expected.scenes
                )
                if int(cell.get("n_frame", -1)) != expected_frames:
                    problems.append(
                        f"{key}/{class_name}/{speed:.0f}: n_frame="
                        f"{cell.get('n_frame')}, kỳ vọng {expected_frames}"
                    )
                if int(cell.get("n_scene", -1)) != len(expected.scenes):
                    problems.append(
                        f"{key}/{class_name}/{speed:.0f}: n_scene không khớp"
                    )
    return problems


def run_check(args) -> int:
    root = Path(args.root)
    scenes = read_scene_inventory(root)
    plan = build_fold_plan(scenes)
    print_plan_report(scenes, plan, args.frames_per_scene)
    problems = verify_plan(scenes, plan, args.frames_per_scene)
    for fold in FOLDS:
        test = fold_test_scenes(scenes, fold)
        expected = EXPECTED_TEST_FRAMES.get(fold)
        measured = sum(scene.n_frames for scene in test)
        mark = "OK" if expected is None or expected == measured else "MISMATCH"
        print(
            f"FOLD_FRAMES fold={fold} measured={measured} "
            f"expected={expected} {mark}",
            flush=True,
        )
        if expected is not None and expected != measured:
            problems.append(
                f"fold {fold}: {measured} frame test, kỳ vọng {expected}"
            )
    if args.measured:
        document = json.loads(Path(args.measured).read_text(encoding="utf-8"))
        problems.extend(
            check_measured_document(
                document, scenes, plan, args.frames_per_scene
            )
        )
    if problems:
        print(f"FOLDS_CHECK_FAIL problems={len(problems)}", flush=True)
        for problem in problems:
            print(f"  - {problem}", flush=True)
        return 1
    print(
        f"FOLDS_CHECK_OK folds=3 scenes={len(scenes)} "
        f"boxed={sum(1 for scene in scenes if scene.has_box)} "
        f"cells={sum(len(plan[fold]) for fold in FOLDS)}",
        flush=True,
    )
    return 0


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(
    scenes: list[SceneInfo],
    tables: dict[int, dict[tuple[str, float], CellResult]],
    measured: dict[str, dict],
    args,
    old_repro: dict | None = None,
) -> str:
    lines: list[str] = []
    add = lines.append
    add("### Cấu trúc fold và mẫu [ĐO]")
    add("")
    add(
        "| fold | tốc độ held-out | scene test | frame test | scene train có box "
        "| frame train có box | scene dùng được |"
    )
    add("|---:|---|---:|---:|---:|---:|---:|")
    for fold in FOLDS:
        test = fold_test_scenes(scenes, fold)
        train = fold_train_scenes(scenes, fold)
        held = ", ".join(f"{speed:.0f}" for speed in speeds_for_fold(fold))
        add(
            f"| {fold} | {held} | {len(test)} | "
            f"{sum(scene.n_frames for scene in test)} | {len(train)} | "
            f"{sum(scene.n_frames for scene in train)} | "
            f"{len(scenes) - len(test)} |"
        )
    add("")
    add(
        f"Recipe: `label == {NOISE_LABEL}`; DBSCAN `(azimuth, elevation)` "
        f"eps = {vn(ANGULAR_EPS_DEG, 1)}°, minPts = {MIN_PTS}, elevation snap "
        f"0,333°, azimuth wrap; {args.frames_per_scene} frame cách đều/scene; "
        f"bootstrap mức scene B = {args.bootstrap}, seed = {BOOTSTRAP_SEED}."
    )
    add("")

    for fold in FOLDS:
        held = ", ".join(f"{speed:.0f}" for speed in speeds_for_fold(fold))
        add(f"### Bảng fold {fold} — test {held} km/h [ĐO]")
        add("")
        add(
            "| km/h | Crafter scene/frame | Crafter cụm/frame [CI95] "
            "| Golf scene/frame | Golf cụm/frame [CI95] |"
        )
        add("|---:|---:|---:|---:|---:|")
        for speed in SPEEDS_KMH:
            row = [f"{speed:.0f}"]
            if fold_for_speed(speed) == fold:
                row[0] += " †"
            for class_name in ("crafter", "golf"):
                cell = tables[fold][(GROUP_BY_CLASS[class_name], speed)]
                sub = cell.fold_subcells[fold]
                row.append(f"{sub.n_scene}/{sub.n_frame}")
                row.append(ci_text(sub))
            add("| " + " | ".join(row) + " |")
        add("")
        add(
            "† = tốc độ held-out của fold này: 4 scene test (2 scene/group) bị "
            "loại, ô chỉ còn 10 scene không box (`itr_after_water` 2–6) — trừ "
            "Golf 80/90 của dataset chỉ có 8/7 scene nên ô còn 6/5 scene."
        )
        add("")

    add("### Bảng gộp 3 fold [ĐO]")
    add("")
    add(
        'Giá trị "gộp 3 fold" = trung bình 3 giá trị bảng fold của ô '
        "(2 fold dùng cả 12 scene, fold test đúng tốc độ đó dùng 10 scene "
        "không box); CI95 = bootstrap scene giữ tương quan giữa 3 fold."
    )
    add("")
    half_widths: list[float] = []
    for class_name in ("crafter", "golf"):
        add(f"#### {class_name.capitalize()}")
        add("")
        add(
            "| km/h | n scene | n frame | gộp 3 fold [CI95] "
            "| tất cả scene [CI95] | bỏ scene boxed [CI95] |"
        )
        add("|---:|---:|---:|---:|---:|---:|")
        for speed in SPEEDS_KMH:
            cell = tables[1][(GROUP_BY_CLASS[class_name], speed)]
            half_widths.append(cell.gop["ci95_half_width_pct"])
            add(
                f"| {speed:.0f} | {cell.all_scenes.n_scene} | "
                f"{cell.all_scenes.n_frame} | "
                f"{vn(cell.gop_mean)} "
                f"[{vn(cell.gop_ci_low)}; {vn(cell.gop_ci_high)}] | "
                f"{ci_text(cell.all_scenes)} | {ci_text(cell.non_box_scenes)} |"
            )
        add("")
    add(
        f"CI95 half-width của 18 ô gộp: median **{vn(float(np.median(half_widths)), 1)} %**, "
        f"max **{vn(float(np.max(half_widths)), 1)} %** (ô hẹp nhất "
        f"{vn(float(np.min(half_widths)), 1)} %)."
    )
    add("")

    add("### Điều kiện eval — chỉ scene có box (`itr_after_water = 1`) [ĐO]")
    add("")
    add(
        "36 scene eval đều `itr = 1`. Bảng dưới là ô 2 scene/ô (30 frame) — "
        "đúng điều kiện eval nhất, dùng được ở fold **không** test tốc độ đó "
        "(2 scene có box đều là scene train của fold). Ở fold test đúng tốc độ "
        "đó, không còn scene `itr = 1` nào ngoài test set ⇒ dấu **—** (đây là "
        "lỗ hổng D2 mà bảng RoadSpray static lấp). Cột \"dải\" là 2 giá trị "
        "per-scene, không phải CI."
    )
    add("")
    for class_name in ("crafter", "golf"):
        add(f"#### {class_name.capitalize()}")
        add("")
        header = (
            "| km/h | bảng cũ 45-frame | fold 1 | fold 2 | fold 3 "
            "| cả 12 scene | dải 2 scene |"
        )
        if class_name == "crafter":
            header += " static (D2) |"
            add(header)
            add("|---:|---:|---:|---:|---:|---:|---:|---:|")
        else:
            add(header)
            add("|---:|---:|---:|---:|---:|---:|---:|")
        for speed in SPEEDS_KMH:
            cell = tables[1][(GROUP_BY_CLASS[class_name], speed)]
            fold_values = []
            for fold in FOLDS:
                if fold_for_speed(speed) == fold:
                    fold_values.append("—")
                else:
                    fold_values.append(vn(cell.eval_condition.mean))
            row = [
                f"{speed:.0f}",
                vn(OLD_TABLE_45[class_name][speed]),
                *fold_values,
                vn(cell.eval_condition.mean),
                f"{vn(cell.eval_condition.value_min)}–"
                f"{vn(cell.eval_condition.value_max)}",
            ]
            if class_name == "crafter":
                static = STATIC_TABLE_CRAFTER.get(speed)
                row.append(vn(static) if static is not None else "—")
            add("| " + " | ".join(row) + " |")
        add("")

    add("### Bảng 45-frame cũ lệch bao nhiêu [ĐO]")
    add("")
    add(
        "Bảng cũ = số commit trong `docs/measurements/"
        "semantic-spray-clusters-by-speed.md` Bảng 1 (đo trên `cal`, 45 frame/ô). "
        "Script đo bảng cũ không có trong repo; cột \"dựng lại cal 20 m\" là "
        "phép dựng lại trung thực nhất theo phần Phương pháp của doc cũ — "
        "15 frame/scene, 3 scene `cal` của **ô 20 m** (đúng 45 frame/ô), "
        "cùng recipe đo."
    )
    add("")
    for class_name in ("crafter", "golf"):
        add(f"#### {class_name.capitalize()}")
        add("")
        add(
            "| km/h | bảng cũ (commit) | dựng lại cal 20 m | Δ dựng lại/cũ "
            "| gộp 3 fold (10–12 scene) | Δ gộp/cũ | eval itr = 1 (2 scene) "
            "| Δ itr/cũ |"
        )
        add("|---:|---:|---:|---:|---:|---:|---:|---:|")
        repro_values: dict[float, float] = {}
        pooled_values: dict[float, float] = {}
        eval_values: dict[float, float] = {}
        for speed in SPEEDS_KMH:
            cell = tables[1][(GROUP_BY_CLASS[class_name], speed)]
            old = OLD_TABLE_45[class_name][speed]
            pooled_values[speed] = cell.gop_mean
            eval_values[speed] = cell.eval_condition.mean
            if old_repro is not None:
                repro = old_repro[class_name][speed]["20"]
                repro_values[speed] = repro
                repro_text = vn(repro)
                repro_delta = vn_pct((repro - old) / old * 100.0)
            else:
                repro_text, repro_delta = "—", "—"
            add(
                f"| {speed:.0f} | {vn(old)} | {repro_text} | {repro_delta} | "
                f"{vn(cell.gop_mean)} | "
                f"{vn_pct((cell.gop_mean - old) / old * 100.0)} | "
                f"{vn(cell.eval_condition.mean)} | "
                f"{vn_pct((cell.eval_condition.mean - old) / old * 100.0)} |"
            )
        add("")
        stats: list[str] = []
        for label, values in (
            ("gộp 3 fold", pooled_values),
            ("eval itr = 1", eval_values),
        ):
            mean_delta, max_delta = mean_abs_pct_delta(
                values, OLD_TABLE_45[class_name]
            )
            stats.append(
                f"{label}: |Δ%| mean **{vn(mean_delta, 1)} %**, "
                f"max {vn(max_delta, 1)} %, r = {vn(pearson(values, OLD_TABLE_45[class_name]), 2)}, "
                f"ρ = {vn(spearman(values, OLD_TABLE_45[class_name]), 2)}"
            )
        if repro_values:
            mean_delta, max_delta = mean_abs_pct_delta(
                repro_values, OLD_TABLE_45[class_name]
            )
            stats.insert(
                0,
                f"dựng lại cal 20 m: |Δ%| mean **{vn(mean_delta, 1)} %**, "
                f"max {vn(max_delta, 1)} %",
            )
        for line in stats:
            add(f"- {line}")
        add("")

    add("### So với bảng RoadSpray `*_static` [ĐO]")
    add("")
    add(
        "`static` = calibration độc lập, ego đỗ, `itr_after_water = 1` "
        "(ADR-0006 D2). Chỉ Crafter có số."
    )
    add("")
    add(
        "| km/h | static (D2) | eval itr = 1 (2 scene) | tỉ lệ itr/static "
        "| gộp 3 fold (10–12 scene) | tỉ lệ gộp/static |"
    )
    add("|---:|---:|---:|---:|---:|---:|")
    eval_values = {}
    pooled_values = {}
    for speed in sorted(STATIC_TABLE_CRAFTER):
        cell = tables[1][(GROUP_BY_CLASS["crafter"], speed)]
        static = STATIC_TABLE_CRAFTER[speed]
        eval_values[speed] = cell.eval_condition.mean
        pooled_values[speed] = cell.gop_mean
        add(
            f"| {speed:.0f} | {vn(static)} | {vn(cell.eval_condition.mean)} | "
            f"{vn_ratio(cell.eval_condition.mean / static)} | "
            f"{vn(cell.gop_mean)} | {vn_ratio(cell.gop_mean / static)} |"
        )
    add("")
    for label, values in (
        ("eval itr = 1", eval_values),
        ("gộp 3 fold", pooled_values),
    ):
        mean_delta, max_delta = mean_abs_pct_delta(
            values, STATIC_TABLE_CRAFTER
        )
        add(
            f"- {label} vs static: |Δ%| mean **{vn(mean_delta, 1)} %**, "
            f"max {vn(max_delta, 1)} %, r = "
            f"{vn(pearson(values, STATIC_TABLE_CRAFTER), 2)}, ρ = "
            f"{vn(spearman(values, STATIC_TABLE_CRAFTER), 2)}"
        )
    mean_delta, max_delta = mean_abs_pct_delta(
        OLD_TABLE_45["crafter"], STATIC_TABLE_CRAFTER
    )
    add(
        f"- bảng cũ 45-frame vs static: |Δ%| mean "
        f"**{vn(mean_delta, 1)} %**, max {vn(max_delta, 1)} %, r = "
        f"{vn(pearson(OLD_TABLE_45['crafter'], STATIC_TABLE_CRAFTER), 2)}, "
        f"ρ = {vn(spearman(OLD_TABLE_45['crafter'], STATIC_TABLE_CRAFTER), 2)}"
    )
    add("")

    add("### Độ ổn định giữa 3 fold [ĐO]")
    add("")
    add(
        "| class | km/h | fold test đúng tốc độ này (10 scene không box) "
        "| 2 fold còn lại (12 scene) | spread % |"
    )
    add("|---|---:|---:|---:|---:|")
    for class_name in ("crafter", "golf"):
        for speed in SPEEDS_KMH:
            cell = tables[1][(GROUP_BY_CLASS[class_name], speed)]
            strict = cell.non_box_scenes.mean
            full = cell.all_scenes.mean
            spread = (
                abs(strict - full) / full * 100.0 if full else float("nan")
            )
            add(
                f"| {class_name} | {speed:.0f} | {vn(strict)} | {vn(full)} | "
                f"{vn(spread, 1)} |"
            )
    add("")
    all_spreads = [
        abs(
            tables[1][(GROUP_BY_CLASS[class_name], speed)].non_box_scenes.mean
            - tables[1][(GROUP_BY_CLASS[class_name], speed)].all_scenes.mean
        )
        / tables[1][(GROUP_BY_CLASS[class_name], speed)].all_scenes.mean
        * 100.0
        for class_name in ("crafter", "golf")
        for speed in SPEEDS_KMH
    ]
    add(
        f"Spread trung bình = **{vn(float(np.mean(all_spreads)), 1)} %**, "
        f"median = {vn(float(np.median(all_spreads)), 1)} %, "
        f"max = {vn(float(np.max(all_spreads)), 1)} %."
    )
    add("")

    add("### Nếu đọc chặt hơn: bỏ hẳn mọi scene cùng tốc độ held-out [TÍNH]")
    add("")
    add(
        "Cách đọc chặt của ADR-0006 D2: ngoài 12 scene test, mọi scene **cùng "
        "tốc độ** cũng thuộc chiến dịch/điều kiện của test nên không được dùng "
        "để calibration. Khi đó bảng của fold k chỉ có 6 mốc tốc độ; 3 tốc độ "
        "held-out phải nội suy tuyến tính từ 6 mốc đó. Bảng dưới so giá trị "
        "nội suy với số đo trực tiếp (cả 12 scene) để thấy sai số của cách làm "
        "SSPP-only — chính là lỗ hổng D2."
    )
    add("")
    add("| fold | class | km/h held-out | nội suy từ 6 mốc | đo trực tiếp | Δ % |")
    add("|---:|---|---:|---:|---:|---:|")
    strict_deltas: list[float] = []
    for fold in FOLDS:
        held = set(speeds_for_fold(fold))
        for class_name in ("crafter", "golf"):
            group = GROUP_BY_CLASS[class_name]
            knots = [
                (speed, tables[fold][(group, speed)].all_scenes.mean)
                for speed in SPEEDS_KMH
                if speed not in held
            ]
            knot_speeds = np.asarray([row[0] for row in knots])
            knot_values = np.asarray([row[1] for row in knots])
            for speed in SPEEDS_KMH:
                if speed not in held:
                    continue
                interpolated = float(np.interp(speed, knot_speeds, knot_values))
                direct = tables[fold][(group, speed)].all_scenes.mean
                delta = (interpolated - direct) / direct * 100.0
                strict_deltas.append(abs(delta))
                note = " †" if speed < knot_speeds[0] else ""
                add(
                    f"| {fold} | {class_name} | {speed:.0f}{note} | "
                    f"{vn(interpolated)} | {vn(direct)} | {vn_pct(delta)} |"
                )
    add("")
    add(
        f"|Δ%| trung bình = **{vn(float(np.mean(strict_deltas)), 1)} %**, "
        f"median = {vn(float(np.median(strict_deltas)), 1)} %, "
        f"max = {vn(float(np.max(strict_deltas)), 1)} %."
    )
    add("")
    add(
        "† 50 km/h của fold 1 nằm dưới mốc thấp nhất của bảng (60): "
        "`np.interp` kẹp về giá trị 60, còn `cluster_visible_target_for_speed` "
        "trong `spray/plume.py` trả **0,0** khi tốc độ dưới mốc đầu — tức "
        "plume biến mất ở 50 km/h nếu chỉ dùng bảng SSPP của fold 1."
    )
    add("")

    add("### Nước (`itr_after_water`) — vì sao ô 10–12 scene khô hơn eval [ĐO]")
    add("")
    add(
        "36 scene eval đều `itr_after_water = 1`; 10 scene còn lại trong ô "
        "là `itr 2–6` (bể nước vơi dần). Bảng dưới tách 2 nhóm để thấy đại "
        "lượng lệch là do **nước**, không phải do tốc độ."
    )
    add("")
    add(
        "| class | km/h | cụm/frame (2 scene itr = 1) | cụm/frame (10 scene "
        "itr 2–6) | tỉ lệ |"
    )
    add("|---|---:|---:|---:|---:|")
    itr_ratios: list[float] = []
    for class_name in ("crafter", "golf"):
        group = GROUP_BY_CLASS[class_name]
        for speed in SPEEDS_KMH:
            cells = [
                scene
                for scene in scenes
                if scene.group == group and scene.speed_kmh == speed
            ]
            boxed_paths = tuple(
                scene.rel_path for scene in cells if scene.has_box
            )
            non_box_paths = tuple(
                scene.rel_path for scene in cells if not scene.has_box
            )
            if not boxed_paths or not non_box_paths:
                continue
            boxed_sub = compute_subcell(
                boxed_paths,
                measured,
                args.bootstrap,
                _cell_seed("it1", class_name, speed),
            )
            non_box_sub = compute_subcell(
                non_box_paths,
                measured,
                args.bootstrap,
                _cell_seed("it2", class_name, speed),
            )
            ratio = boxed_sub.mean / non_box_sub.mean
            itr_ratios.append(ratio)
            add(
                f"| {class_name} | {speed:.0f} | {vn(boxed_sub.mean)} | "
                f"{vn(non_box_sub.mean)} | {vn_ratio(ratio)} |"
            )
    add("")
    add(
        f"Tỉ lệ itr = 1 / itr 2–6: trung bình "
        f"**{vn_ratio(float(np.mean(itr_ratios)))}×**, "
        f"min {vn_ratio(float(np.min(itr_ratios)))}×, "
        f"max {vn_ratio(float(np.max(itr_ratios)))}× — đúng chiều ADR-0006 "
        f"(pseudo scene khô hơn, 1,2–5,4× theo tốc độ)."
    )
    add("")
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def build_json_document(
    scenes: list[SceneInfo],
    plan: dict[int, dict[tuple[str, float], CellPlan]],
    tables: dict[int, dict[tuple[str, float], CellResult]],
    args,
    old_repro: dict | None,
) -> dict:
    boxed = [scene for scene in scenes if scene.has_box]
    document: dict = {
        "generated_by": "scripts/sspp_cluster_table_folds.py",
        "fold_rule": FOLD_RULE,
        "fold_speeds": {
            str(fold): [speed for speed in speeds_for_fold(fold)]
            for fold in FOLDS
        },
        "recipe": _recipe_signature(args.frames_per_scene),
        "bootstrap": {"B": args.bootstrap, "seed": BOOTSTRAP_SEED},
        "inventory": {
            "n_scene": len(scenes),
            "n_scene_boxed": len(boxed),
            "n_frame_total": sum(scene.n_frames for scene in scenes),
            "n_frame_boxed": sum(scene.n_frames for scene in boxed),
        },
        "folds": {
            str(fold): {
                "held_out_speeds": list(speeds_for_fold(fold)),
                "test_scenes": [
                    scene.rel_path for scene in fold_test_scenes(scenes, fold)
                ],
                "n_test_scenes": len(fold_test_scenes(scenes, fold)),
                "n_test_frames": sum(
                    scene.n_frames for scene in fold_test_scenes(scenes, fold)
                ),
                "train_scenes": [
                    scene.rel_path for scene in fold_train_scenes(scenes, fold)
                ],
                "n_train_scenes": len(fold_train_scenes(scenes, fold)),
                "n_used_scenes": len(scenes)
                - len(fold_test_scenes(scenes, fold)),
            }
            for fold in FOLDS
        },
        "old_table_45": {
            class_name: {f"{speed:.0f}": value for speed, value in rows.items()}
            for class_name, rows in OLD_TABLE_45.items()
        },
        "static_table_crafter": {
            f"{speed:.0f}": value
            for speed, value in STATIC_TABLE_CRAFTER.items()
        },
        "tables": {},
    }
    for fold in FOLDS:
        per_class: dict[str, dict] = {}
        for class_name in ("crafter", "golf"):
            group = GROUP_BY_CLASS[class_name]
            per_class[class_name] = {}
            for speed in SPEEDS_KMH:
                cell = tables[fold][(group, speed)]
                per_class[class_name][f"{speed:.0f}"] = {
                    **cell.fold_subcells[fold].to_json(),
                    "fold_holding_speed_out": cell.fold_holdout,
                    "is_speed_held_out": cell.fold_holdout == fold,
                }
        document["tables"][f"fold{fold}"] = per_class
    document["pooled"] = {}
    for class_name in ("crafter", "golf"):
        group = GROUP_BY_CLASS[class_name]
        document["pooled"][class_name] = {}
        for speed in SPEEDS_KMH:
            cell = tables[1][(group, speed)]
            document["pooled"][class_name][f"{speed:.0f}"] = {
                "gop_3fold": cell.gop,
                "all_scenes": cell.all_scenes.to_json(),
                "non_box_scenes": cell.non_box_scenes.to_json(),
                "eval_condition_itr1": cell.eval_condition.to_json(),
                "fold_means": {
                    str(fold): cell.fold_subcells[fold].mean
                    for fold in FOLDS
                },
            }
    if old_repro is not None:
        document["old_table_reproduction"] = {
            class_name: {
                f"{speed:.0f}": entry
                for speed, entry in rows.items()
            }
            for class_name, rows in old_repro.items()
        }
    return document


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Tính bảng cụm/frame SSPP theo fold leave-speed-out (không leak) "
            "với CI95 bootstrap ở mức scene."
        )
    )
    parser.add_argument(
        "--root",
        default=str(REPO / "data" / "SemanticSprayDataset"),
        help="thư mục SemanticSprayDataset",
    )
    parser.add_argument(
        "--frames-per-scene",
        type=int,
        default=DEFAULT_FRAMES_PER_SCENE,
        help=f"số frame cách đều mỗi scene (mặc định {DEFAULT_FRAMES_PER_SCENE})",
    )
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=DEFAULT_BOOTSTRAP,
        help=f"số replicate bootstrap (mặc định {DEFAULT_BOOTSTRAP})",
    )
    parser.add_argument("--json-out", default=None, help="ghi JSON kết quả")
    parser.add_argument("--md-out", default=None, help="ghi bảng markdown")
    parser.add_argument(
        "--cache",
        default=None,
        help="file cache frame-level (JSON) để chạy lại nhanh",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="chỉ kiểm tra cấu trúc fold + no-leak (không đo)",
    )
    parser.add_argument(
        "--measured",
        default=None,
        help="với --check: file JSON đã đo để kiểm chéo scene từng ô",
    )
    parser.add_argument(
        "--compare-old",
        action="store_true",
        help="dựng lại bảng 45-frame cũ (cal) và in so sánh",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.bootstrap < 10:
        raise SystemExit("--bootstrap phải >= 10")
    if args.frames_per_scene < 1:
        raise SystemExit("--frames-per-scene phải >= 1")
    root = Path(args.root)
    if not root.is_dir():
        raise SystemExit(f"missing dataset: {root}")

    if args.check:
        return run_check(args)

    scenes = read_scene_inventory(root)
    plan = build_fold_plan(scenes)
    problems = verify_plan(scenes, plan, args.frames_per_scene)
    if problems:
        print(f"FOLDS_CHECK_FAIL problems={len(problems)}", flush=True)
        for problem in problems:
            print(f"  - {problem}", flush=True)
        return 1
    measured = measure_all(
        scenes,
        root,
        args.frames_per_scene,
        Path(args.cache) if args.cache else None,
        quiet=args.quiet,
    )
    tables = build_tables(scenes, plan, measured, args.bootstrap)
    old_repro = (
        reproduce_old_table(scenes, measured, root)
        if args.compare_old
        else None
    )
    document = build_json_document(scenes, plan, tables, args, old_repro)

    measured_problems = check_measured_document(
        document, scenes, plan, args.frames_per_scene
    )
    if measured_problems:
        print(f"FOLDS_CHECK_FAIL problems={len(measured_problems)}", flush=True)
        for problem in measured_problems:
            print(f"  - {problem}", flush=True)
        return 1
    print(
        f"FOLDS_CHECK_OK measured=1 folds=3 cells={sum(len(plan[fold]) for fold in FOLDS)}",
        flush=True,
    )

    markdown = render_markdown(scenes, tables, measured, args, old_repro)
    print(markdown, flush=True)
    if args.md_out:
        Path(args.md_out).write_text(markdown, encoding="utf-8")
        print(f"WRITE md={args.md_out}", flush=True)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"WRITE json={args.json_out}", flush=True)

    if old_repro is not None:
        for class_name in ("crafter", "golf"):
            for distances in ("20", "30", "20_30"):
                values = {
                    speed: old_repro[class_name][speed][distances]
                    for speed in SPEEDS_KMH
                    if math.isfinite(
                        old_repro[class_name][speed][distances]
                    )
                }
                mean_delta, max_delta = mean_abs_pct_delta(
                    values, OLD_TABLE_45[class_name]
                )
                print(
                    f"OLD_REPRO class={class_name} cell=cal_{distances} "
                    f"n={len(values)} mean_abs_pct={mean_delta:.2f} "
                    f"max_abs_pct={max_delta:.2f}",
                    flush=True,
                )
    print("FOLDS_MEASURE_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
