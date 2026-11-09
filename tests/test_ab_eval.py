"""Pure-Python checks for the ticket 11-c3b A/B evaluation entrypoint.

``kaggle/train/main.py`` resolves ``/kaggle/input`` at import time, so it is
loaded the same way ``test_ab_run.py`` does.  ``ab_eval.py`` must import
without torch: every torch/mmcv import lives inside a function.
"""

import ast
import json
import pathlib
import types

import pytest

from proxy_eval.mit_adapter import MIT_CLASSES

TRAIN_DIR = pathlib.Path(__file__).resolve().parents[1] / "kaggle" / "train"
MAIN = TRAIN_DIR / "main.py"
AB_EVAL = TRAIN_DIR / "ab_eval.py"

BOX = [10.0, 0.0, 0.0, 2.0, 4.0, 1.5, 0.0]


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


def _load_ab_eval():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ab_eval", AB_EVAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_cell(tmp_path, frames):
    """Write ``(token, pred, gt)`` frames into one pred/gt directory pair."""
    pred_dir = tmp_path / "pred"
    gt_dir = tmp_path / "gt"
    pred_dir.mkdir()
    gt_dir.mkdir()
    for token, pred, gt in frames:
        (pred_dir / ("%s.pred.json" % token)).write_text(json.dumps(pred))
        (gt_dir / ("%s.gt.json" % token)).write_text(json.dumps(gt))
    return pred_dir, gt_dir


def _perfect_pred():
    return {
        "class_names": list(MIT_CLASSES),
        "boxes_3d": [BOX],
        "scores_3d": [0.9],
        "labels_3d": [0],
    }


def _car_gt():
    return {"gt_boxes": [BOX], "gt_names": ["car"]}


# ---------------------------------------------------------------- score_cell
def test_score_cell_counts_frames_and_averages_map(tmp_path):
    empty_pred = {
        "class_names": list(MIT_CLASSES),
        "boxes_3d": [],
        "scores_3d": [],
        "labels_3d": [],
    }
    pred_dir, gt_dir = _write_cell(
        tmp_path,
        [
            ("tok-hit", _perfect_pred(), _car_gt()),
            ("tok-miss", empty_pred, _car_gt()),
        ],
    )

    score = _load_ab_eval().score_cell(pred_dir, gt_dir)

    assert score["n_frames"] == 2
    assert score["map"] == pytest.approx(0.5)
    assert score["recall"] == pytest.approx(0.5)
    assert score["precision"] == pytest.approx(0.5)
    assert set(score["per_frame"]) == {"tok-hit", "tok-miss"}


def test_score_cell_raises_when_prediction_is_missing(tmp_path):
    pred_dir, gt_dir = _write_cell(
        tmp_path, [("tok-hit", _perfect_pred(), _car_gt())]
    )
    (gt_dir / "tok-gone.gt.json").write_text(json.dumps(_car_gt()))

    with pytest.raises(FileNotFoundError) as excinfo:
        _load_ab_eval().score_cell(pred_dir, gt_dir)

    assert "tok-gone" in str(excinfo.value)


# ------------------------------------------------------------ summarize_cells
def test_summarize_cells_key_order_and_interaction():
    cells = {
        "A": {"clean": {"map": 0.30}, "spray": {"map": 0.20}},
        "B": {"clean": {"map": 0.30}, "spray": {"map": 0.25}},
    }

    summary = _load_ab_eval().summarize_cells(cells)

    assert list(summary) == ["delta_A", "delta_B", "interaction"]
    assert summary["delta_A"] == pytest.approx(-0.10)
    assert summary["delta_B"] == pytest.approx(-0.05)
    assert summary["interaction"] == pytest.approx(0.05)


def test_summarize_cells_appends_ci95_when_given():
    cells = {
        "A": {"clean": {"map": 0.30}, "spray": {"map": 0.20}},
        "B": {"clean": {"map": 0.30}, "spray": {"map": 0.25}},
    }

    summary = _load_ab_eval().summarize_cells(
        cells, ci={"lo": -0.01, "hi": 0.11, "mean": 0.05}
    )

    assert list(summary) == ["delta_A", "delta_B", "interaction", "ci95"]
    assert summary["ci95"] == [-0.01, 0.11]


# ----------------------------------------------------------------- parse_args
def test_parse_args_reads_paths_and_limit():
    module = _load_ab_eval()

    args = module.parse_args(
        ["--ckpt-dir", "/ckpt", "--out-dir", "/out", "--limit", "5"]
    )
    defaults = module.parse_args([])

    assert args.ckpt_dir == "/ckpt"
    assert args.out_dir == "/out"
    assert args.limit == 5
    assert defaults.limit == 0


# ------------------------------------------------------------- main.py routing
def test_main_routes_ab_eval_task_to_script():
    main = _load_main()

    assert main.task_script("ab-eval") == "kaggle/train/ab_eval.py"
    task, rest = main.parse_task(["--task", "ab-eval", "--limit", "5"])
    assert task == "ab-eval"
    assert rest == ["--limit", "5"]


def test_verdict_accepts_eval_ok():
    assert _load_main().verdict(0, "EVAL_OK delta_A=0.1") == (True, "EVAL_OK")
