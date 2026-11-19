from collections import Counter

import yaml
import pytest

from spray.semantic_split import (
    GROUPS,
    ROLE_CAL,
    ROLE_HELD_OUT,
    RULE_VERSION,
    SPLIT_VERSION,
    SceneMeta,
    assign_roles,
    build_split,
    dump_split,
    evaluate_criteria,
    halves,
    itr_balance,
    load_split,
    verify_split,
)

VELOCITIES = (50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0)
DISTANCES = (20.0, 30.0)


def _meta(group, scene, velocity=50.0, distance=20.0, itr=1, amb=20.0):
    return SceneMeta(
        group=group,
        scene=scene,
        object_velocity_kmh=velocity,
        distance_to_object_m=distance,
        itr_after_water=itr,
        amb_tmp_c=amb,
    )


def _grid_metas(per_cell=6):
    metas = []
    for group in GROUPS:
        for velocity in VELOCITIES:
            for distance in DISTANCES:
                for index in range(per_cell):
                    scene = f"{int(velocity):03d}_{int(distance):02d}_{index:02d}"
                    metas.append(_meta(group, scene, velocity, distance))
    return metas


def _itr_grid_metas(velocities=(50.0, 60.0), distances=(20.0, 30.0)):
    metas = []
    for group in GROUPS:
        for velocity in velocities:
            for distance in distances:
                for index in range(6):
                    scene = f"{int(velocity):03d}_{int(distance):02d}_{index:02d}"
                    metas.append(
                        _meta(
                            group,
                            scene,
                            velocity,
                            distance,
                            itr=index + 1,
                        )
                    )
    return metas


def _three_per_cell_metas(velocities=(50.0, 60.0), distances=(20.0, 30.0)):
    metas = []
    for group in GROUPS:
        for velocity in velocities:
            for distance in distances:
                for index in range(3):
                    scene = f"{int(velocity):03d}_{int(distance):02d}_{index:02d}"
                    metas.append(
                        _meta(
                            group,
                            scene,
                            velocity,
                            distance,
                            itr=index + 1,
                        )
                    )
    return metas


def _cal_metas(metas, split):
    cal_rel_paths = {
        rel_path
        for cell in split["cells"]
        for rel_path in cell["scenes"][ROLE_CAL]
    }
    return [meta for meta in metas if meta.rel_path in cal_rel_paths]


def _metrics(**overrides):
    values = {
        "G1": 100.0,
        "G2": 20.0,
        "G3": 10.0,
        "G4": 1.0,
        "G5": 2.0,
        "G6_p5": 0.5,
        "G6_med": 1.0,
        "G6_p95": 1.5,
        "G7": 10.0,
        "frames": 1000,
        "n_clusters": 500,
    }
    values.update(overrides)
    return values


def test_full_cells_split_three_cal_three_held_out():
    split = build_split(_grid_metas(6))

    assert len(split["cells"]) == 36
    for cell in split["cells"]:
        assert len(cell["scenes"][ROLE_CAL]) == 3
        assert len(cell["scenes"][ROLE_HELD_OUT]) == 3
        assert cell["unpaired"] is False


def test_assign_roles_does_not_depend_on_input_order():
    metas = _grid_metas(6)

    expected = assign_roles(metas)

    assert assign_roles(list(reversed(metas))) == expected
    rotated = metas[7:] + metas[:7]
    assert assign_roles(rotated) == expected

    shuffled = list(metas)
    for left, right in ((0, 100), (5, 200), (11, 150)):
        shuffled[left], shuffled[right] = shuffled[right], shuffled[left]
    assert assign_roles(shuffled) == expected


def test_single_and_pair_cells_are_flagged_unpaired():
    metas = [
        _meta("Golf_dynamic", "only_scene", 90.0, 20.0),
        _meta("Golf_dynamic", "pair_a", 80.0, 30.0),
        _meta("Golf_dynamic", "pair_b", 80.0, 30.0),
    ]

    split = build_split(metas)
    cells = {
        (
            cell["key"]["group"],
            cell["key"]["velocity_kmh"],
            cell["key"]["distance_m"],
        ): cell
        for cell in split["cells"]
    }

    single = cells[("Golf_dynamic", 90.0, 20.0)]
    assert single["scenes"][ROLE_CAL] == ["Golf_dynamic/only_scene"]
    assert single["scenes"][ROLE_HELD_OUT] == []
    assert single["unpaired"] is True

    pair = cells[("Golf_dynamic", 80.0, 30.0)]
    assert pair["scenes"][ROLE_CAL] == ["Golf_dynamic/pair_a"]
    assert pair["scenes"][ROLE_HELD_OUT] == ["Golf_dynamic/pair_b"]
    assert pair["unpaired"] is False


def test_roles_partition_every_scene_and_counts_match():
    metas = _grid_metas(6)
    split = build_split(metas)

    cal = set()
    held_out = set()
    for cell in split["cells"]:
        cal.update(cell["scenes"][ROLE_CAL])
        held_out.update(cell["scenes"][ROLE_HELD_OUT])

    assert not cal & held_out
    assert cal | held_out == {meta.rel_path for meta in metas}
    assert split["counts"] == {
        ROLE_CAL: len(cal),
        ROLE_HELD_OUT: len(held_out),
    }


def test_dump_is_byte_identical_and_verify_detects_one_role_change(tmp_path):
    split = build_split(_grid_metas(6))

    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    dump_split(split, first)
    dump_split(split, second)

    assert first.read_bytes() == second.read_bytes()
    assert load_split(first)["version"] == SPLIT_VERSION
    assert verify_split(split, first) == []

    tampered_doc = load_split(first)
    cell = next(
        cell
        for cell in tampered_doc["cells"]
        if cell["scenes"][ROLE_CAL] and cell["scenes"][ROLE_HELD_OUT]
    )
    moved = cell["scenes"][ROLE_CAL].pop()
    cell["scenes"][ROLE_HELD_OUT].append(moved)
    tampered = tmp_path / "tampered.yaml"
    with tampered.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(tampered_doc, handle, sort_keys=False, allow_unicode=True)

    problems = verify_split(split, tampered)
    assert len(problems) == 1
    assert moved in problems[0]


def test_halves_partitions_cal_disjointly_and_is_stable():
    metas = [
        _meta(
            "Crafter_dynamic",
            f"scene_{index:02d}",
            50.0,
            20.0,
            itr=index % 3 + 1,
        )
        for index in range(6)
    ]

    first, second = halves(metas)

    assert not set(first) & set(second)
    assert set(first) | set(second) == {meta.rel_path for meta in metas}
    assert halves(metas) == (first, second)


def test_halves_balance_itr_after_water_within_each_group():
    metas = _three_per_cell_metas()
    split = build_split(metas)
    cal_metas = _cal_metas(metas, split)
    by_rel_path = {meta.rel_path: meta for meta in cal_metas}

    first, second = halves(cal_metas)

    assert not set(first) & set(second)
    assert set(first) | set(second) == set(by_rel_path)

    for group in GROUPS:
        counts_first = Counter(
            by_rel_path[rel_path].itr_after_water
            for rel_path in first
            if by_rel_path[rel_path].group == group
        )
        counts_second = Counter(
            by_rel_path[rel_path].itr_after_water
            for rel_path in second
            if by_rel_path[rel_path].group == group
        )
        assert counts_first == counts_second
        assert sum(counts_first.values()) + sum(counts_second.values()) == sum(
            1 for meta in cal_metas if meta.group == group
        )

    assert abs(len(first) - len(second)) <= 1


def test_halves_balances_odd_strata_at_every_itr_level():
    metas = []
    for group in GROUPS:
        odd_levels = (1, 2, 3, 4, 5, 6) if group == GROUPS[0] else (1, 6)
        for itr in range(1, 7):
            count = 3 if itr in odd_levels else 2
            for index in range(count):
                metas.append(
                    _meta(
                        group,
                        f"scene_{itr:02d}_{index:02d}",
                        50.0,
                        20.0,
                        itr=itr,
                    )
                )

    first, second = halves(metas)
    by_rel_path = {meta.rel_path: meta for meta in metas}

    for level in range(1, 7):
        first_level = sum(
            1
            for rel_path in first
            if by_rel_path[rel_path].itr_after_water == level
        )
        second_level = sum(
            1
            for rel_path in second
            if by_rel_path[rel_path].itr_after_water == level
        )
        assert abs(first_level - second_level) <= 1

    for group in GROUPS:
        for level in range(1, 7):
            first_level = sum(
                1
                for rel_path in first
                if by_rel_path[rel_path].group == group
                and by_rel_path[rel_path].itr_after_water == level
            )
            second_level = sum(
                1
                for rel_path in second
                if by_rel_path[rel_path].group == group
                and by_rel_path[rel_path].itr_after_water == level
            )
            assert abs(first_level - second_level) <= 1

    assert abs(len(first) - len(second)) <= 1


def test_halves_is_deterministic_under_input_permutation():
    metas = _itr_grid_metas()
    split = build_split(metas)
    cal_metas = _cal_metas(metas, split)

    expected = halves(cal_metas)

    assert halves(list(reversed(cal_metas))) == expected
    rotated = cal_metas[7:] + cal_metas[:7]
    assert halves(rotated) == expected

    shuffled = list(cal_metas)
    for left, right in ((0, 12), (7, 19), (5, 11)):
        shuffled[left], shuffled[right] = shuffled[right], shuffled[left]
    assert halves(shuffled) == expected


def test_threshold_stays_at_floor_when_half_split_is_huge():
    metrics_by_role = {
        ROLE_CAL: _metrics(),
        ROLE_HELD_OUT: _metrics(G1=101.0),
        "cal_a": _metrics(),
        "cal_b": _metrics(G1=150.0),
    }

    results = evaluate_criteria(metrics_by_role)
    g1 = next(result for result in results if result.id == "G1")

    assert g1.half_split_delta == pytest.approx(0.5)
    assert g1.threshold == pytest.approx(0.15)
    assert g1.passed is True


def test_regression_beyond_floor_fails_despite_huge_half_split():
    metrics_by_role = {
        ROLE_CAL: _metrics(),
        ROLE_HELD_OUT: _metrics(G1=145.0),
        "cal_a": _metrics(),
        "cal_b": _metrics(G1=300.0),
    }

    results = evaluate_criteria(metrics_by_role)
    g1 = next(result for result in results if result.id == "G1")

    assert g1.delta == pytest.approx(45.0)
    assert g1.threshold == pytest.approx(0.15)
    assert g1.passed is False


def test_observed_beyond_twice_half_split_only_adds_a_note():
    metrics_by_role = {
        ROLE_CAL: _metrics(),
        ROLE_HELD_OUT: _metrics(G1=110.0),
        "cal_a": _metrics(),
        "cal_b": _metrics(G1=102.0),
    }

    results = evaluate_criteria(metrics_by_role)
    g1 = next(result for result in results if result.id == "G1")

    assert g1.half_split_delta == pytest.approx(0.02)
    assert g1.passed is True
    assert "vượt sàn nhiễu nội tại" in g1.note


def test_evaluate_criteria_flags_shift_and_missing_data():
    identical = {
        ROLE_CAL: _metrics(),
        ROLE_HELD_OUT: _metrics(),
        "cal_a": _metrics(),
        "cal_b": _metrics(),
    }
    results = evaluate_criteria(identical)
    assert [result.id for result in results] == [
        "G1", "G2", "G3", "G4", "G5", "G6", "G7"
    ]
    assert all(result.passed for result in results)

    shifted = {
        ROLE_CAL: _metrics(),
        ROLE_HELD_OUT: _metrics(G4=1.11),
        "cal_a": _metrics(),
        "cal_b": _metrics(),
    }
    shifted_results = evaluate_criteria(shifted)
    assert [result.id for result in shifted_results if not result.passed] == ["G4"]
    g4 = next(result for result in shifted_results if result.id == "G4")
    assert g4.delta == pytest.approx(0.11)

    starved = {
        ROLE_CAL: _metrics(frames=100),
        ROLE_HELD_OUT: _metrics(frames=100),
        "cal_a": _metrics(frames=100),
        "cal_b": _metrics(frames=100),
    }
    starved_results = evaluate_criteria(starved)
    assert not any(result.passed for result in starved_results)
    assert all(
        "quá ít dữ liệu" in result.note for result in starved_results
    )


def test_itr_after_water_counts_match_between_roles_per_group_and_globally():
    metas = _itr_grid_metas()
    split = build_split(metas)
    balance = itr_balance(metas, split)

    assert split["version"] == SPLIT_VERSION
    assert split["rule_version"] == RULE_VERSION

    for group in GROUPS:
        cal = Counter(balance[group][ROLE_CAL])
        held = Counter(balance[group][ROLE_HELD_OUT])
        assert cal == held
        assert set(cal) == {1, 2, 3, 4, 5, 6}
        assert set(cal.values()) == {2}

    global_cal = Counter()
    global_held = Counter()
    for group in GROUPS:
        global_cal.update(balance[group][ROLE_CAL])
        global_held.update(balance[group][ROLE_HELD_OUT])
    assert global_cal == global_held
    assert set(global_cal.values()) == {4}


def test_assign_roles_orders_by_itr_after_water_not_by_name():
    metas = [
        _meta(
            "Crafter_dynamic",
            f"scene_{5 - index:02d}",
            50.0,
            20.0,
            itr=index + 1,
        )
        for index in range(6)
    ]

    roles = assign_roles(metas)

    assert roles["Crafter_dynamic/scene_05"] == ROLE_CAL
    assert roles["Crafter_dynamic/scene_03"] == ROLE_CAL
    assert roles["Crafter_dynamic/scene_01"] == ROLE_CAL
    assert roles["Crafter_dynamic/scene_04"] == ROLE_HELD_OUT
    assert roles["Crafter_dynamic/scene_02"] == ROLE_HELD_OUT
    assert roles["Crafter_dynamic/scene_00"] == ROLE_HELD_OUT


def test_odd_cells_keep_extra_scene_in_cal():
    metas = [
        _meta(
            "Crafter_dynamic",
            f"five_{index}",
            50.0,
            20.0,
            itr=index + 1,
        )
        for index in range(5)
    ]
    metas.append(_meta("Golf_dynamic", "single", 60.0, 20.0, itr=3))

    split = build_split(metas)
    cells = {
        (
            cell["key"]["group"],
            cell["key"]["velocity_kmh"],
            cell["key"]["distance_m"],
        ): cell
        for cell in split["cells"]
    }

    five = cells[("Crafter_dynamic", 50.0, 20.0)]
    assert len(five["scenes"][ROLE_CAL]) == 3
    assert len(five["scenes"][ROLE_HELD_OUT]) == 2
    assert five["unpaired"] is True

    single = cells[("Golf_dynamic", 60.0, 20.0)]
    assert single["scenes"][ROLE_CAL] == ["Golf_dynamic/single"]
    assert single["scenes"][ROLE_HELD_OUT] == []
    assert single["unpaired"] is True


def test_itr_balance_helper_counts_and_rejects_unknown_scene():
    metas = _itr_grid_metas()
    split = build_split(metas)

    balance = itr_balance(metas, split)

    assert set(balance) == set(GROUPS)
    for group in GROUPS:
        assert sum(balance[group][ROLE_CAL].values()) == 12
        assert sum(balance[group][ROLE_HELD_OUT].values()) == 12

    with pytest.raises(ValueError):
        itr_balance(
            metas + [_meta("Crafter_dynamic", "ghost", 70.0, 20.0, itr=1)],
            split,
        )


def test_assign_roles_is_deterministic_with_itr_ordering():
    metas = _itr_grid_metas()

    expected = assign_roles(metas)

    assert assign_roles(list(reversed(metas))) == expected
    rotated = metas[5:] + metas[:5]
    assert assign_roles(rotated) == expected

    shuffled = list(metas)
    for left, right in ((0, 40), (7, 31), (13, 23)):
        shuffled[left], shuffled[right] = shuffled[right], shuffled[left]
    assert assign_roles(shuffled) == expected
