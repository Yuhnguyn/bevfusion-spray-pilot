"""Pure-Python checks for the ticket 11-c1 A/B training entrypoint.

``kaggle/train/main.py`` resolves ``/kaggle/input`` at import time, so it is
loaded the same way ``test_task_args.py`` does.  ``ab_run.py`` must import
without torch: every torch import lives inside a function.
"""

import ast
import builtins
import importlib.util
import pathlib
import statistics
import sys
import types

import pytest

TRAIN_DIR = pathlib.Path(__file__).resolve().parents[1] / "kaggle" / "train"
MAIN = TRAIN_DIR / "main.py"
AB_RUN = TRAIN_DIR / "ab_run.py"


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


def _load_ab_run():
    spec = importlib.util.spec_from_file_location("ab_run", AB_RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------- main.py: task
def test_parse_task_at_start():
    task, rest = _load_main().parse_task(["--task", "ab-run", "--steps", "10"])

    assert task == "ab-run"
    assert rest == ["--steps", "10"]


def test_parse_task_in_middle():
    task, rest = _load_main().parse_task(["--steps", "10", "--task", "ab-run", "--lr", "1e-4"])

    assert task == "ab-run"
    assert rest == ["--steps", "10", "--lr", "1e-4"]


def test_parse_task_at_end():
    task, rest = _load_main().parse_task(["--steps", "10", "--task", "ab-run"])

    assert task == "ab-run"
    assert rest == ["--steps", "10"]


def test_parse_task_defaults_to_smoke_and_keeps_args():
    args = ["--sweeps-probe", "--nusc-version", "v1.0-mini"]
    task, rest = _load_main().parse_task(args)

    assert task == "smoke"
    assert rest == args


def test_parse_task_never_forwards_task_token():
    task, rest = _load_main().parse_task(["--task", "ab-run", "--task", "smoke"])

    assert task == "smoke"
    assert "--task" not in rest
    assert rest == []


def test_task_script_maps_dash_to_underscore():
    main = _load_main()

    assert main.task_script("ab-run") == "kaggle/train/ab_run.py"
    assert main.task_script("smoke") == "kaggle/train/smoke.py"


# -------------------------------------------------------------- ab_run helpers
def test_arm_specs_are_symmetric():
    specs = _load_ab_run().arm_specs(["A", "B"])

    assert [spec["arm"] for spec in specs] == ["A", "B"]
    assert len({(spec["steps"], spec["lr"], spec["seed"]) for spec in specs}) == 1
    assert specs[0]["steps"] == 2000
    assert specs[0]["lr"] == 1e-4
    assert specs[0]["seed"] == 0


def test_summarize_records_matches_statistics():
    losses = [float(index) for index in range(150)]
    times = [0.5 + 0.01 * index for index in range(150)]
    records = [{"loss": loss, "s": elapsed} for loss, elapsed in zip(losses, times)]

    summary = _load_ab_run().summarize_records(records)

    assert summary["s_per_step"] == pytest.approx(statistics.mean(times))
    assert summary["loss_first"] == losses[0]
    assert summary["loss_last"] == losses[-1]
    assert summary["loss_mean_last100"] == pytest.approx(
        statistics.mean(losses[-100:])
    )


def test_checkpoint_payload_has_required_keys():
    payload = _load_ab_run().checkpoint_payload(
        {}, arm="A", steps=2000, lr=1e-4, sweeps_num=0
    )

    assert set(payload) >= {"state_dict", "arm", "steps", "lr", "sweeps_num"}
    assert payload["state_dict"] == {}
    assert payload["arm"] == "A"
    assert payload["steps"] == 2000
    assert payload["lr"] == 1e-4
    assert payload["sweeps_num"] == 0


def test_loss_keys_prefers_total_loss_over_components():
    losses = {"loss": 1.0, "loss_cls": 0.6, "loss_bbox": 0.4}

    assert _load_ab_run().loss_keys(losses) == ["loss"]


def test_loss_keys_sums_components_when_no_total():
    losses = {"loss_cls": 0.6, "loss_bbox": 0.4}

    assert _load_ab_run().loss_keys(losses) == ["loss_bbox", "loss_cls"]


def test_loss_keys_empty_when_no_loss_keys():
    assert _load_ab_run().loss_keys({"acc": 1.0}) == []


def test_time_budget_exceeded_at_boundary():
    module = _load_ab_run()

    assert module.time_budget_exceeded(100.0, 10, now=109.999) is False
    assert module.time_budget_exceeded(100.0, 10, now=110.0) is True
    assert module.time_budget_exceeded(100.0, 10, now=110.5) is True


def test_ab_run_imports_without_torch(monkeypatch):
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("torch imported at module scope")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    monkeypatch.delitem(sys.modules, "ab_run", raising=False)

    module = _load_ab_run()

    assert hasattr(module, "main")
