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


def _load_main(path=MAIN):
    tree = ast.parse(path.read_text())
    body = [
        node
        for node in tree.body
        if not (
            isinstance(node, ast.Assign)
            and any(getattr(target, "id", None) == "BOOT" for target in node.targets)
        )
    ]
    module = types.ModuleType("train_main")
    module.__file__ = str(path)
    exec(
        compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"),
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


def test_checked_in_args_file_holds_only_cli_tokens():
    assert ARGS_FILE.is_file()
    assert all(token.startswith("-") for token in _load_main().task_args())


def test_resolve_args_file_prefers_repo_over_cwd(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_flag = repo / "kaggle" / "train" / "task_args.txt"
    repo_flag.parent.mkdir(parents=True)
    repo_flag.write_text("--sweeps-probe\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    resolved = _load_main().resolve_args_file(
        [repo_flag, cwd / "kaggle" / "train" / "task_args.txt"]
    )

    assert resolved == repo_flag


def test_resolve_args_file_returns_none_when_absent(tmp_path):
    main = _load_main()

    assert main.resolve_args_file([tmp_path / "absent.txt"]) is None
    assert main.resolve_args_file([]) is None


def test_resolve_args_file_returns_first_existing(tmp_path):
    first = tmp_path / "first.txt"
    first.write_text("--one\n")
    second = tmp_path / "second.txt"
    second.write_text("--two\n")
    main = _load_main()

    assert main.resolve_args_file([first, second]) == first
    assert main.resolve_args_file([tmp_path / "missing.txt", second]) == second


def test_flag_found_when_main_py_lives_outside_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    flag = repo / "kaggle" / "train" / "task_args.txt"
    flag.parent.mkdir(parents=True)
    flag.write_text("--sweeps-probe\n")

    script = tmp_path / "kernel" / "main.py"
    script.parent.mkdir()
    script.write_text(MAIN.read_text())

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    main = _load_main(script)
    candidates = [
        pathlib.Path(repo) / "kaggle/train/task_args.txt",
        pathlib.Path.cwd() / "kaggle/train/task_args.txt",
        pathlib.Path(main.__file__).resolve().parent / "task_args.txt",
    ]

    resolved = main.resolve_args_file(candidates)

    assert pathlib.Path(main.__file__).resolve().parent == script.parent
    assert resolved == flag
    assert main.task_args(resolved) == ["--sweeps-probe"]


def test_verdict_accepts_sweeps_ok():
    assert _load_main().verdict(0, "x\nSWEEPS_OK n_single=1\n") == (True, "SWEEPS_OK")


def test_verdict_accepts_smoke_ok():
    assert _load_main().verdict(0, "SMOKE_OK s_per_step=1") == (True, "SMOKE_OK")


def test_verdict_rejects_nonzero_rc():
    assert _load_main().verdict(1, "SWEEPS_OK") == (False, "")


def test_verdict_rejects_zero_rc_without_marker():
    assert _load_main().verdict(0, "SMOKE_FAILED split") == (False, "")
