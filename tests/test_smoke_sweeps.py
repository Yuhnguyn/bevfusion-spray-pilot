"""Pure-Python checks for the ticket-20-b sweeps probe helpers in smoke.py."""

import importlib.util
from pathlib import Path

import numpy as np

from spray.mini_split import load_val_scenes

SMOKE_PATH = Path(__file__).resolve().parent.parent / "kaggle" / "train" / "smoke.py"


def _load_smoke():
    spec = importlib.util.spec_from_file_location("smoke", SMOKE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_dataroot_mini_version(tmp_path, monkeypatch):
    module = _load_smoke()
    root = tmp_path / "nuscenes-mini"
    (root / "v1.0-mini").mkdir(parents=True)
    (root / "v1.0-mini" / "sample.json").write_text("{}")

    monkeypatch.setattr(module, "DEFAULT_DATAROOT", str(tmp_path / "missing-a"))
    monkeypatch.setattr(module, "ALT_DATAROOT", str(tmp_path / "missing-b"))
    monkeypatch.setattr(module, "MINI_DATAROOT", str(root))

    assert module.find_dataroot(version="v1.0-mini") == root


def test_ensure_splits_file_mini_writes_parsable_val(tmp_path):
    module = _load_smoke()
    out = tmp_path / "mini_splits.py"

    result = module.ensure_splits_file(
        version="v1.0-mini",
        scene_names=["scene-0003", "scene-0001", "scene-0002"],
        path=out,
    )

    assert result == out
    assert load_val_scenes(out) == frozenset({"scene-0002", "scene-0003"})


def test_sweeps_summary_duplicated_keyframe_ratio_is_low():
    module = _load_smoke()
    keyframe = np.array(
        [[0.0, 0.0, 0.0, 1.0], [1.0, 0.0, 0.0, 1.0], [2.0, 0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    multi = np.concatenate([keyframe] * 10)

    summary = module.sweeps_summary(keyframe, multi)

    assert summary["n_single"] == 3
    assert summary["n_multi"] == 30
    assert summary["ratio"] == 0.1


def test_sweeps_summary_distinct_sweeps_ratio_is_high():
    module = _load_smoke()
    single = np.arange(12, dtype=np.float32).reshape(3, 4)
    multi = np.arange(120, dtype=np.float32).reshape(30, 4)

    summary = module.sweeps_summary(single, multi)

    assert summary["n_single"] == 3
    assert summary["n_multi"] == 30
    assert summary["ratio"] == 1.0
    assert summary["n_multi"] > summary["n_single"] * 2
