"""Tests cho ``scripts/sspp_cluster_table_folds.py``.

Trọng tâm: rule fold của ADR-0006 D1, phép lấy mẫu frame giữ đúng recipe cũ,
và **điều kiện không leak** — bảng của fold k không được chứa scene test của
fold k. Các test dùng inventory tổng hợp (không cần ``data/``), riêng 1 test
tích hợp chạy trên dataset thật và tự skip nếu thiếu ``data/``.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from scripts.sspp_cluster_table_folds import (
    BOOTSTRAP_SEED,
    CLASS_BY_GROUP,
    FOLDS,
    GROUPS,
    OLD_TABLE_45,
    SPEEDS_KMH,
    SceneInfo,
    SubCell,
    bootstrap_pooled_ci,
    build_fold_plan,
    check_measured_document,
    combined_fold_bootstrap_ci,
    fold_for_speed,
    fold_test_scenes,
    mean_abs_pct_delta,
    pearson,
    plan_cell_frames,
    pooled_mean,
    sample_frame_indices,
    spearman,
    speeds_for_fold,
    verify_plan,
    vn,
    vn_pct,
)

REPO = Path(__file__).resolve().parents[1]
DATASET = REPO / "data" / "SemanticSprayDataset"


# ---------------------------------------------------------------------------
# Inventory + measured data tổng hợp
# ---------------------------------------------------------------------------


def _scene(
    group: str,
    index: int,
    speed: float,
    *,
    itr: int = 1,
    n_frames: int = 20,
    boxed: bool = True,
) -> SceneInfo:
    name = f"{'C' if group.startswith('Crafter') else 'G'}{index:03d}"
    return SceneInfo(
        rel_path=f"{group}/scene_{name}",
        group=group,
        class_name=CLASS_BY_GROUP[group],
        speed_kmh=speed,
        itr_after_water=itr,
        distance_to_object_m=20.0 if index % 2 else 30.0,
        n_frames=n_frames,
        boxed_frames=("000000",) if boxed else (),
    )


def _synthetic_scenes() -> list[SceneInfo]:
    """2 group × 9 tốc độ × (2 scene box itr=1 + 2 scene không box itr 2–3)."""

    scenes: list[SceneInfo] = []
    for group in GROUPS:
        index = 0
        for speed in SPEEDS_KMH:
            for _ in range(2):
                scenes.append(_scene(group, index, speed, itr=1, boxed=True))
                index += 1
            for _ in range(2):
                scenes.append(
                    _scene(group, index, speed, itr=2, boxed=False)
                )
                index += 1
    return scenes


def _measured_from_scenes(
    scenes: list[SceneInfo], *, frames: int = 15
) -> dict[str, dict]:
    """``measured`` giả: mỗi scene có ``frames`` frame với số cụm tăng dần."""

    measured: dict[str, dict] = {}
    for scene in scenes:
        records = [
            {
                "scan_id": f"{index:06d}",
                "n_noise": 100 * (index + 1),
                "n_clusters": index + 1,
            }
            for index in range(min(frames, scene.n_frames))
        ]
        measured[scene.rel_path] = {
            "frames": records,
            "n_frame_dropped": 0,
        }
    return measured


def _fake_measured_document(
    scenes: list[SceneInfo],
    plan: dict,
    frames_per_scene: int = 15,
) -> dict:
    """Document JSON giả đủ mọi ô, đúng định dạng ``build_json_document``."""

    info = {scene.rel_path: scene for scene in scenes}
    document: dict = {"tables": {}}
    for fold in FOLDS:
        per_class: dict = {"crafter": {}, "golf": {}}
        for (group, speed), cell in plan[fold].items():
            n_frame = sum(
                len(
                    sample_frame_indices(
                        info[rel_path].n_frames, frames_per_scene
                    )
                )
                for rel_path in cell.scenes
            )
            per_class[CLASS_BY_GROUP[group]][f"{speed:.0f}"] = {
                "scenes": list(cell.scenes),
                "n_scene": cell.n_scene,
                "n_frame": n_frame,
            }
        document["tables"][f"fold{fold}"] = per_class
    return document


# ---------------------------------------------------------------------------
# Fold rule (ADR-0006 D1)
# ---------------------------------------------------------------------------


def test_fold_rule_matches_adr_0006():
    expected = {
        50.0: 1,
        60.0: 2,
        70.0: 3,
        80.0: 1,
        90.0: 2,
        100.0: 3,
        110.0: 1,
        120.0: 2,
        130.0: 3,
    }
    assert {speed: fold_for_speed(speed) for speed in SPEEDS_KMH} == expected
    assert speeds_for_fold(1) == (50.0, 80.0, 110.0)
    assert speeds_for_fold(2) == (60.0, 90.0, 120.0)
    assert speeds_for_fold(3) == (70.0, 100.0, 130.0)
    with pytest.raises(ValueError):
        fold_for_speed(55.0)
    with pytest.raises(ValueError):
        speeds_for_fold(4)


def test_fold_rule_is_a_partition_of_nine_speeds():
    union = [speed for fold in FOLDS for speed in speeds_for_fold(fold)]
    assert sorted(union) == sorted(SPEEDS_KMH)
    assert len(union) == len(set(union)) == 9


# ---------------------------------------------------------------------------
# Lấy mẫu frame (giữ recipe bảng cũ: 15 frame cách đều/scene)
# ---------------------------------------------------------------------------


def test_sample_frame_indices_matches_old_recipe():
    # np.linspace(0, 75, 15).round() — đúng phép lấy mẫu của bảng 45-frame cũ.
    assert sample_frame_indices(76, 15) == [
        0,
        5,
        11,
        16,
        21,
        27,
        32,
        38,
        43,
        48,
        54,
        59,
        64,
        70,
        75,
    ]


def test_sample_frame_indices_short_scene_returns_every_frame():
    assert sample_frame_indices(10, 15) == list(range(10))
    assert sample_frame_indices(15, 15) == list(range(15))
    assert len(sample_frame_indices(39, 15)) == 15


def test_sample_frame_indices_rejects_bad_arguments():
    with pytest.raises(ValueError):
        sample_frame_indices(0, 15)
    with pytest.raises(ValueError):
        sample_frame_indices(20, 0)


# ---------------------------------------------------------------------------
# Thống kê ô: mean gộp theo frame + bootstrap mức scene
# ---------------------------------------------------------------------------


def test_pooled_mean_is_frame_weighted():
    n_frames = np.array([10.0, 30.0])
    sums = np.array([10.0, 30.0])
    # scene 1: 1 cụm/frame; scene 2: 0,1 cụm/frame; gộp frame = 40/40 = 1,0
    assert pooled_mean(n_frames, sums) == pytest.approx(1.0)
    # scene dài hơn nặng hơn scene ngắn
    assert pooled_mean(np.array([10.0, 30.0]), np.array([10.0, 0.0])) == (
        pytest.approx(0.25)
    )


def test_bootstrap_pooled_ci_brackets_mean_and_is_deterministic():
    rng = np.random.default_rng(7)
    n_frames = np.full(12, 15.0)
    sums = n_frames * rng.uniform(5.0, 25.0, size=12)
    mean = pooled_mean(n_frames, sums)
    low, high = bootstrap_pooled_ci(n_frames, sums, 500, BOOTSTRAP_SEED)
    assert low <= mean <= high
    low_again, high_again = bootstrap_pooled_ci(
        n_frames, sums, 500, BOOTSTRAP_SEED
    )
    assert (low, high) == (low_again, high_again)


def test_bootstrap_single_scene_returns_point_estimate():
    n_frames = np.array([15.0])
    sums = np.array([45.0])
    assert bootstrap_pooled_ci(n_frames, sums, 200, 1) == (3.0, 3.0)


def _subcell(scenes: tuple[str, ...], mean: float) -> SubCell:
    return SubCell(
        scenes=scenes,
        n_scene=len(scenes),
        n_frame=15 * len(scenes),
        mean=mean,
        ci_low=mean,
        ci_high=mean,
        mean_noise=0.0,
        cv_scene=0.0,
        scene_means={rel_path: mean for rel_path in scenes},
        n_frame_dropped=0,
    )


def test_combined_fold_bootstrap_ci_is_two_thirds_full_plus_one_strict():
    scenes = ("a", "b", "c")
    measured = {
        "a": {"frames": [{"n_clusters": 3}] * 15, "n_frame_dropped": 0},
        "b": {"frames": [{"n_clusters": 6}] * 15, "n_frame_dropped": 0},
        "c": {"frames": [{"n_clusters": 9}] * 15, "n_frame_dropped": 0},
    }
    all_sub = _subcell(scenes, mean=6.0)
    strict_sub = _subcell(("b", "c"), mean=7.5)
    low, high = combined_fold_bootstrap_ci(
        all_sub,
        strict_sub,
        measured,
        holdout_fold=1,
        bootstrap=500,
        seed=3,
    )
    expected = (2.0 * 6.0 + 7.5) / 3.0
    assert low <= expected <= high


# ---------------------------------------------------------------------------
# Kế hoạch fold + no-leak
# ---------------------------------------------------------------------------


def test_build_fold_plan_keeps_test_scenes_out():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    for fold in FOLDS:
        test_paths = {
            scene.rel_path for scene in fold_test_scenes(scenes, fold)
        }
        assert len(test_paths) == 12
        for (group, speed), cell in plan[fold].items():
            if fold_for_speed(speed) == fold:
                # Tốc độ held-out: 2 scene có box đều là test ⇒ chỉ còn 2
                # scene không box trong inventory tổng hợp.
                assert cell.n_scene == 2
                assert test_paths.isdisjoint(cell.scenes)
                assert all(
                    not scene.boxed_frames
                    for scene in scenes
                    if scene.rel_path in cell.scenes
                )
            else:
                assert cell.n_scene == 4
        assert len(plan[fold]) == 18


def test_verify_plan_accepts_clean_plan():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    assert verify_plan(scenes, plan, 15) == []


def test_verify_plan_detects_a_leaked_test_scene():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    test_scene = fold_test_scenes(scenes, 1)[0]
    key = (test_scene.group, test_scene.speed_kmh)
    leaked_cell = replace(
        plan[1][key], scenes=plan[1][key].scenes + (test_scene.rel_path,)
    )
    plan[1][key] = leaked_cell
    problems = verify_plan(scenes, plan, 15)
    assert any("LEAK fold 1" in problem for problem in problems)


def test_plan_cell_frames_matches_sampled_frames():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    info = {scene.rel_path: scene for scene in scenes}
    counts = plan_cell_frames(plan, info, 15)
    for fold in FOLDS:
        for key, cell in plan[fold].items():
            # inventory tổng hợp: mọi scene 20 frame ⇒ mỗi scene 15 frame mẫu
            assert counts[fold][key] == 15 * cell.n_scene


def test_check_measured_document_proves_no_leak_on_clean_document():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    document = _fake_measured_document(scenes, plan, 15)
    assert check_measured_document(document, scenes, plan, 15) == []


def test_check_measured_document_detects_leaked_scene():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    document = _fake_measured_document(scenes, plan, 15)
    test_scene = fold_test_scenes(scenes, 1)[0]
    cell = document["tables"]["fold1"][test_scene.class_name][
        f"{test_scene.speed_kmh:.0f}"
    ]
    cell["scenes"] = list(cell["scenes"]) + [test_scene.rel_path]
    cell["n_scene"] = len(cell["scenes"])
    problems = check_measured_document(document, scenes, plan, 15)
    assert any("LEAK fold1" in problem for problem in problems)


def test_check_measured_document_detects_wrong_frame_count():
    scenes = _synthetic_scenes()
    plan = build_fold_plan(scenes)
    document = _fake_measured_document(scenes, plan, 15)
    document["tables"]["fold2"]["crafter"]["50"]["n_frame"] = 1
    problems = check_measured_document(document, scenes, plan, 15)
    assert any("n_frame" in problem for problem in problems)


# ---------------------------------------------------------------------------
# So sánh bảng + định dạng số
# ---------------------------------------------------------------------------


def test_mean_abs_pct_delta_and_correlations():
    left = {50.0: 1.0, 60.0: 2.0, 70.0: 3.0}
    right = {50.0: 2.0, 60.0: 2.0, 70.0: 3.0}
    mean_delta, max_delta = mean_abs_pct_delta(left, right)
    assert mean_delta == pytest.approx((50.0 + 0.0 + 0.0) / 3.0)
    assert max_delta == pytest.approx(50.0)
    assert pearson(left, right) == pytest.approx(0.866, abs=1e-3)
    assert spearman(left, right) == pytest.approx(1.0)
    assert math.isnan(pearson({50.0: 1.0}, {50.0: 2.0}))


def test_vietnamese_number_formatting():
    assert vn(1382.0, 1) == "1.382,0"
    assert vn(4.846, 2) == "4,85"
    assert vn(float("nan")) == "—"
    assert vn_pct(-6.84) == "−6,8 %"
    assert vn_pct(0.0) == "+0,0 %"
    # bảng cũ được hardcode đúng như commit
    assert OLD_TABLE_45["crafter"][100.0] == 29.24
    assert OLD_TABLE_45["golf"][50.0] == 3.62


# ---------------------------------------------------------------------------
# Tích hợp trên dataset thật (skip nếu máy không có data/)
# ---------------------------------------------------------------------------

pytestmark_dataset = pytest.mark.skipif(
    not DATASET.is_dir(), reason="data/SemanticSprayDataset không có trên máy"
)


@pytest.fixture(scope="module")
def real_scenes():
    from scripts.sspp_cluster_table_folds import read_scene_inventory

    return read_scene_inventory(DATASET)


@pytestmark_dataset
def test_real_dataset_matches_adr_fold_composition(real_scenes):
    boxed = [scene for scene in real_scenes if scene.has_box]
    assert len(real_scenes) == 207
    assert len(boxed) == 36
    expected_frames = {1: 886, 2: 893, 3: 808}
    for fold in FOLDS:
        test = fold_test_scenes(real_scenes, fold)
        assert len(test) == 12
        assert sum(scene.n_frames for scene in test) == expected_frames[fold]
    # mỗi scene có box được test đúng một lần
    tested = [
        scene.rel_path
        for fold in FOLDS
        for scene in fold_test_scenes(real_scenes, fold)
    ]
    assert len(tested) == len(set(tested)) == 36
    plan = build_fold_plan(real_scenes)
    assert verify_plan(real_scenes, plan, 15) == []


@pytestmark_dataset
def test_check_cli_reports_no_leak(capsys):
    from scripts.sspp_cluster_table_folds import main

    exit_code = main(["--check"])
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "FOLDS_CHECK_OK" in captured
    assert "INVENTORY scenes=207 boxed=36" in captured
    assert "FOLD_FRAMES fold=1 measured=886 expected=886 OK" in captured
    assert "FOLD_FRAMES fold=2 measured=893 expected=893 OK" in captured
    assert "FOLD_FRAMES fold=3 measured=808 expected=808 OK" in captured
