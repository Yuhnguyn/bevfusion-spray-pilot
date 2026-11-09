"""Token-list driven mini split (--tokens-json), no devkit needed."""

import importlib.util
import json
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parent.parent / "scripts/make_mini_split.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("make_mini_split", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_mini_split = _load_module()


def _write_frames(tmp_path, frames):
    path = tmp_path / "eval_set.json"
    path.write_text(json.dumps({"frames": frames}))
    return path


def test_load_tokens_keeps_json_order_and_count(tmp_path):
    path = _write_frames(
        tmp_path,
        [
            {"sample_token": "tok-c", "scene": "scene-0002"},
            {"sample_token": "tok-a", "scene": "scene-0001"},
            {"sample_token": "tok-b", "scene": "scene-0002"},
        ],
    )

    tokens = make_mini_split.load_tokens_from_json(path)

    assert tokens == ["tok-c", "tok-a", "tok-b"]
    assert len(tokens) == 3


def test_build_infos_reports_tokens_whose_build_raises():
    def build_info(token):
        if token == "tok-missing-file":
            raise FileNotFoundError(token)
        if token == "tok-absent":
            raise KeyError(token)
        return {"token": token}

    infos, missing = make_mini_split.build_infos_for_tokens(
        ["tok-ok-a", "tok-missing-file", "tok-ok-b", "tok-absent"], build_info
    )

    assert [info["token"] for info in infos] == ["tok-ok-a", "tok-ok-b"]
    assert missing == ["tok-missing-file", "tok-absent"]


def test_build_infos_calls_builder_once_per_token_in_order():
    calls = []

    def build_info(token):
        calls.append(token)
        return {"token": token}

    infos, missing = make_mini_split.build_infos_for_tokens(
        ["tok-1", "tok-2", "tok-3"], build_info
    )

    assert calls == ["tok-1", "tok-2", "tok-3"]
    assert [info["token"] for info in infos] == ["tok-1", "tok-2", "tok-3"]
    assert missing == []


def test_parse_args_accepts_tokens_json():
    with_flag = make_mini_split.parse_args(
        ["--dataroot", "d", "--out", "o", "--tokens-json", "eval_set.json"]
    )
    without_flag = make_mini_split.parse_args(["--dataroot", "d", "--out", "o"])

    assert with_flag.tokens_json == "eval_set.json"
    assert without_flag.tokens_json is None
