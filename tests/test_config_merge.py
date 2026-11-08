"""Tests for the pure-Python YAML helpers used by the A/B config builder."""

import copy

import pytest

from spray.config_merge import (
    PLACEHOLDER,
    diff_paths,
    load_yaml,
    lookup,
    merge,
    resolve,
)


def test_placeholder_is_whole_string_only():
    assert PLACEHOLDER.match("${a.b}") is not None
    assert PLACEHOLDER.match("${a.b} suffix") is None
    assert PLACEHOLDER.match("plain") is None


def test_lookup_dotted_indexed_and_nested():
    roots = {
        "a": [1.0, 2.0],
        "b": {"c": 3, "d": [{"e": 4}]},
        "augment3d": {"rotate": [-0.1, 0.1]},
    }
    assert lookup(roots, "b.c") == 3
    assert lookup(roots, "a[1]") == 2.0
    assert lookup(roots, "augment3d.rotate") == [-0.1, 0.1]
    assert lookup(roots, "b.d[0].e") == 4


def test_lookup_missing_raises_key_error():
    roots = {"a": [1.0], "b": {"c": 3}}
    with pytest.raises(KeyError):
        lookup(roots, "missing")
    with pytest.raises(KeyError):
        lookup(roots, "a[5]")
    with pytest.raises(KeyError):
        lookup(roots, "a.b")


def test_resolve_placeholders():
    roots = {
        "a": [1.0, 2.0],
        "b": {"c": 3},
        "chain": "${b.c}",
        "steps": [
            {"v": "${a}"},
            {"w": "${b.c}"},
            {"u": "${a[1]}"},
            {"x": "${chain}"},
            {"y": {"z": ["${b.c}"]}},
        ],
    }
    assert resolve(roots["steps"], roots) == [
        {"v": [1.0, 2.0]},
        {"w": 3},
        {"u": 2.0},
        {"x": 3},
        {"y": {"z": [3]}},
    ]


def test_resolve_leaves_numbers_and_partial_strings_alone():
    roots = {"a": 1}
    assert resolve(3.5, roots) == 3.5
    assert resolve("no placeholder ${a} here", roots) == "no placeholder ${a} here"
    assert resolve({"k": 1}, roots) == {"k": 1}


def test_resolve_raises_on_missing_placeholder():
    with pytest.raises(KeyError):
        resolve("${missing}", {})
    with pytest.raises(KeyError):
        resolve({"k": "${a.b.c}"}, {"a": {"b": {}}})
    with pytest.raises(KeyError):
        resolve(["${a}"], {"a": "${missing}"})


def test_merge_deep_override_and_no_mutation():
    base = {"a": {"b": 1, "c": 2}, "d": [1, 2], "e": 5}
    override = {"a": {"c": 3, "f": 4}, "g": 6}
    snapshot = copy.deepcopy(base)

    merged = merge(base, override)

    assert merged == {
        "a": {"b": 1, "c": 3, "f": 4},
        "d": [1, 2],
        "e": 5,
        "g": 6,
    }
    assert base == snapshot
    assert merged["d"] is not base["d"]
    assert merged["a"] is not base["a"]


def test_merge_override_replaces_non_dict_with_dict_and_vice_versa():
    assert merge({"a": {"b": 1}}, {"a": 2}) == {"a": 2}
    assert merge({"a": 2}, {"a": {"b": 1}}) == {"a": {"b": 1}}


def test_diff_paths_nested_and_sorted():
    a = {"a": {"b": 1, "c": 2}, "d": [1, 2], "e": 5}
    b = {"a": {"b": 1, "c": 9}, "d": [1, 3], "e": 5}
    assert diff_paths(a, b) == ["a.c", "d"]


def test_diff_paths_added_and_removed_keys():
    assert diff_paths({"x": 1}, {"y": 1}) == ["x", "y"]
    assert diff_paths({}, {"a": {"b": 1}}) == ["a"]
    assert diff_paths({"a": {"b": 1}}, {}) == ["a"]


def test_diff_paths_prefix_and_equal_values():
    assert diff_paths({"a": 1}, {"a": 1}) == []
    assert diff_paths([1], [1]) == []
    assert diff_paths({"a": {"b": 1}}, {"a": {}}, prefix="root") == ["root.a.b"]
    assert diff_paths({"a": {"b": 1}}, {"a": {"b": 2}}, prefix="root") == [
        "root.a.b"
    ]


def test_load_yaml_reads_dataset_config():
    raw = load_yaml("mit/bevfusion/configs/nuscenes/default.yaml")
    assert isinstance(raw, dict)
    assert "train_pipeline" in raw
    assert raw["reduce_beams"] == 32
