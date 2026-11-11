"""Ticket 29e: the sidecar speed index and ``SprayContextTransform``."""

import json
import pickle

import numpy as np
import pytest

from scripts.build_plume_speed_index import build_index, load_infos, main
from spray.plume_context import PlumeContext, PlumeContextError
from spray.spray_context_transform import SprayContextTransform


def _info(lidar_path, token, scene_token, timestamp, translation):
    return {
        "lidar_path": lidar_path,
        "token": token,
        "scene_token": scene_token,
        "timestamp": timestamp,
        "ego2global_translation": list(translation),
    }


def _infos():
    return [
        _info("a/0.bin", "t0", "scene-a", 0, (0.0, 0.0, 0.0)),
        _info("a/1.bin", "t1", "scene-a", 500_000, (5.0, 0.0, 0.0)),
        _info("a/2.bin", "t2", "scene-a", 1_000_000, (10.0, 0.0, 0.0)),
        _info("b/0.bin", "t3", "scene-b", 0, (0.0, 0.0, 0.0)),
        _info("b/1.bin", "t4", "scene-b", 500_000, (0.0, 3.0, 0.0)),
    ]


def test_build_index_derives_speed_and_repeats_the_last_value():
    index = build_index(_infos())

    assert index["a/0.bin"]["ego_speed_mps"] == pytest.approx(10.0)
    assert index["a/1.bin"]["ego_speed_mps"] == pytest.approx(10.0)
    # Last frame has no successor: it reuses the previous frame's speed.
    assert index["a/2.bin"]["ego_speed_mps"] == pytest.approx(10.0)
    assert index["b/1.bin"]["ego_speed_mps"] == pytest.approx(6.0)
    assert index["b/1.bin"]["object_speed_mps"] == pytest.approx(6.0)
    assert index["a/1.bin"]["frame_index"] == 1
    assert index["a/1.bin"]["scene_token"] == "scene-a"


def test_build_index_rejects_infos_without_scene_token():
    infos = _infos()
    del infos[0]["scene_token"]

    with pytest.raises(KeyError, match="scene_token"):
        build_index(infos)


def test_main_writes_a_json_sidecar(tmp_path):
    infos_path = tmp_path / "infos.pkl"
    out = tmp_path / "index.json"
    with infos_path.open("wb") as handle:
        pickle.dump({"infos": _infos(), "metadata": {}}, handle)

    assert main([str(infos_path), "--out", str(out)]) == 0

    index = json.loads(out.read_text())
    assert set(index) == {"a/0.bin", "a/1.bin", "a/2.bin", "b/0.bin", "b/1.bin"}
    assert index["a/0.bin"]["ego_speed_mps"] == pytest.approx(10.0)
    assert len(load_infos(infos_path)) == 5


def _sample(lidar_path="a/0.bin", **overrides):
    sample = {
        "lidar_path": lidar_path,
        "scene_token": "scene-a",
        "sample_idx": 3,
        "timestamp": 1_000_000,
        "ego2global": np.eye(4, dtype=np.float64),
        "lidar2ego": np.eye(4, dtype=np.float64),
        "gt_bboxes_3d": np.zeros((1, 9), dtype=np.float64),
    }
    sample.update(overrides)
    return sample


@pytest.fixture
def sidecar(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(json.dumps(build_index(_infos())))
    return path


def test_transform_attaches_a_plume_context(sidecar):
    transform = SprayContextTransform(sidecar, road_z_m=-0.35)
    results = _sample()

    out = transform(results)

    context = out["plume_context"]
    assert isinstance(context, PlumeContext)
    assert context.scene_token == "scene-a"
    assert context.frame_index == 3
    assert context.ego_speed_mps == pytest.approx(10.0)
    assert context.object_speed_mps == pytest.approx(10.0)
    assert context.wfh_mm == pytest.approx(1.0)
    assert context.road_z_m == pytest.approx(-0.35)


def test_transform_uses_the_sidecar_frame_when_sample_idx_is_missing(sidecar):
    results = _sample()
    del results["sample_idx"]

    context = SprayContextTransform(sidecar)(results)["plume_context"]

    assert context.frame_index == 0


def test_transform_raises_on_a_missing_lidar_path(sidecar):
    results = _sample()
    del results["lidar_path"]

    with pytest.raises(PlumeContextError, match="lidar_path"):
        SprayContextTransform(sidecar)(results)


def test_transform_raises_when_the_sidecar_has_no_entry(sidecar):
    with pytest.raises(PlumeContextError, match="no sidecar entry"):
        SprayContextTransform(sidecar)(_sample(lidar_path="missing.bin"))


def test_transform_raises_when_scene_token_is_absent_everywhere(sidecar):
    results = _sample()
    del results["scene_token"]
    sidecar_data = json.loads(sidecar.read_text())
    for entry in sidecar_data.values():
        entry.pop("scene_token")
    sidecar.write_text(json.dumps(sidecar_data))

    with pytest.raises(PlumeContextError, match="scene_token"):
        SprayContextTransform(sidecar)(results)


def test_transform_disabled_leaves_results_untouched(sidecar):
    results = _sample()

    out = SprayContextTransform(sidecar, enabled=False)(results)

    assert "plume_context" not in out
