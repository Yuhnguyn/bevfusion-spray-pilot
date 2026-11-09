"""Pure-Python checks for the ticket-20-c task flags and verdict helpers.

``kaggle/train/main.py`` resolves ``/kaggle/input`` at import time, so importing
it on a normal machine raises ``StopIteration``.  The module source is parsed
with ``ast`` and executed without that one assignment; the helpers under test
are stdlib-only.
"""

import ast
import pathlib
import types

MAIN = pathlib.Path(__file__).resolve().parents[1] / "kaggle" / "train" / "main.py"
ARGS_FILE = MAIN.parent / "task_args.txt"


def _load_main():
    tree = ast.parse(MAIN.read_text())
    body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.Assign)
            and any(getattr(target, "id", None) == "BOOT" for target in node.targets)
        )
    ]
    module = types.ModuleType("train_main")
    module.__file__ = str(MAIN)
    exec(
        compile(ast.Module(body=body, type_ignores=[]), str(MAIN), "exec"),
        module.__dict__,
    )
    return module


def test_missing_args_file_returns_empty(tmp_path):
    assert _load_main().task_args(path=tmp_path / "absent.txt") == []


def test_comment_only_file_returns_empty(tmp_path):
    path = tmp_path / "task_args.txt"
    path.write_text("# only a comment\n# and another\n")

    assert _load_main().task_args(path=path) == []


def test_comment_then_flag_keeps_the_flag(tmp_path):
    path = tmp_path / "task_args.txt"
    path.write_text("# ...\n--sweeps-probe\n")

    assert _load_main().task_args(path=path) == ["--sweeps-probe"]


def test_whitespace_and_newlines_split_into_tokens(tmp_path):
    path = tmp_path / "task_args.txt"
    path.write_text("  --sweeps-probe   --nusc-version v1.0-mini \n\t--extra\n")

    assert _load_main().task_args(path=path) == [
        "--sweeps-probe",
        "--nusc-version",
        "v1.0-mini",
        "--extra",
    ]


def test_checked_in_args_file_is_comment_only():
    assert ARGS_FILE.is_file()
    assert _load_main().task_args() == []


def test_verdict_accepts_sweeps_ok():
    assert _load_main().verdict(0, "x\nSWEEPS_OK n_single=1\n") == (True, "SWEEPS_OK")


def test_verdict_accepts_smoke_ok():
    assert _load_main().verdict(0, "SMOKE_OK s_per_step=1") == (True, "SMOKE_OK")


def test_verdict_rejects_nonzero_rc():
    assert _load_main().verdict(1, "SWEEPS_OK") == (False, "")


def test_verdict_rejects_zero_rc_without_marker():
    assert _load_main().verdict(0, "SMOKE_FAILED split") == (False, "")
