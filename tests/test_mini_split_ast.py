"""Parse ``splits.py`` via AST, including devkit 1.1.11's backslash layout."""

import importlib.util
from pathlib import Path

import pytest

from spray.mini_split import _read_list, load_camera_types, load_val_scenes

MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts/make_mini_split.py"


def _load_make_mini_split():
    spec = importlib.util.spec_from_file_location("make_mini_split", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path, text, name="splits.py"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_val_list_continued_after_a_backslash(tmp_path):
    """nuscenes-devkit 1.1.11 writes ``val = \\`` then the list."""
    path = _write(tmp_path, "val = \\\n    ['scene-0796', 'scene-0815']\n")

    assert load_val_scenes(path) == frozenset({"scene-0796", "scene-0815"})


def test_val_list_across_multiple_bracket_lines(tmp_path):
    path = _write(
        tmp_path,
        "train = ['scene-0009']\n"
        "val = [\n"
        "    'scene-0796',\n"
        "    'scene-0815',\n"
        "]\n"
        "test = []\n"
        "mini_val = ['scene-0003']\n",
    )

    assert load_val_scenes(path) == frozenset({"scene-0796", "scene-0815"})


def test_val_list_with_annotation(tmp_path):
    path = _write(
        tmp_path,
        "from typing import List\n"
        "val: List[str] = ['scene-0796']\n",
    )

    assert load_val_scenes(path) == frozenset({"scene-0796"})


def test_val_list_on_a_single_line(tmp_path):
    path = _write(tmp_path, "val = ['scene-0796', 'scene-0815']\n")

    assert load_val_scenes(path) == frozenset({"scene-0796", "scene-0815"})


def test_missing_val_names_the_file_and_the_seen_variables(tmp_path):
    path = _write(tmp_path, "train = ['scene-0009']\nalt = ['scene-0003']\n")

    with pytest.raises(ValueError) as excinfo:
        load_val_scenes(path)

    message = str(excinfo.value)
    assert str(path) in message
    assert "train" in message
    assert "alt" in message


def test_val_that_is_not_a_list_raises(tmp_path):
    path = _write(tmp_path, "val = 3\n")

    with pytest.raises(ValueError):
        load_val_scenes(path)


def test_val_list_with_non_string_entry_raises(tmp_path):
    path = _write(tmp_path, "val = ['scene-0796', 3]\n")

    with pytest.raises(ValueError):
        load_val_scenes(path)


def test_syntax_error_reports_the_file_and_line(tmp_path):
    path = _write(tmp_path, "val = [\n")

    with pytest.raises(ValueError) as excinfo:
        load_val_scenes(path)

    message = str(excinfo.value)
    assert str(path) in message
    assert "line " in message


def test_read_list_missing_file_still_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        _read_list(tmp_path / "does-not-exist.py", "val")


def test_load_camera_types_reads_the_vendor_converter_fixture(tmp_path):
    path = _write(
        tmp_path,
        "def _fill_trainval_infos():\n"
        "    camera_types = ['CAM_WRONG']\n"
        "\n"
        "camera_types = [\n"
        "    'CAM_FRONT',\n"
        "    'CAM_FRONT_RIGHT',\n"
        "    'CAM_BACK_RIGHT',\n"
        "    'CAM_BACK',\n"
        "    'CAM_BACK_LEFT',\n"
        "    'CAM_FRONT_LEFT',\n"
        "]\n",
        name="nuscenes_converter.py",
    )

    assert load_camera_types(path) == (
        "CAM_FRONT",
        "CAM_FRONT_RIGHT",
        "CAM_BACK_RIGHT",
        "CAM_BACK",
        "CAM_BACK_LEFT",
        "CAM_FRONT_LEFT",
    )


def test_tokens_json_does_not_need_the_val_split():
    make_mini_split = _load_make_mini_split()

    random_selection = make_mini_split.parse_args(
        ["--dataroot", "d", "--out", "o"]
    )
    token_selection = make_mini_split.parse_args(
        ["--dataroot", "d", "--out", "o", "--tokens-json", "eval_set.json"]
    )

    assert make_mini_split.needs_val_scenes(random_selection) is True
    assert make_mini_split.needs_val_scenes(token_selection) is False
