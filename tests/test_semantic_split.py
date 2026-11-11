import yaml
import pytest

from spray.semantic_split import (
    GROUPS,
    ROLE_CAL,
    ROLE_HELD_OUT,
    SPLIT_VERSION,
    SceneMeta,
    assign_roles,
    build_split,
    dump_split,
    evaluate_criteria,
    halves,
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


def test_halves_are_alternating_disjoint_and_stable():
    paths = [f"scene_{index}" for index in range(5)]

    first, second = halves(paths)

    assert first == paths[::2]
    assert second == paths[1::2]
    assert not set(first) & set(second)
    assert set(first) | set(second) == set(paths)
    assert halves(paths) == (first, second)


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
