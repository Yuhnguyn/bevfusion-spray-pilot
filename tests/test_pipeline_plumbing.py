"""Tests for ``spray.pipeline`` collect/format plumbing (no mmcv required)."""

import sys

import numpy as np
import pytest

from spray import pipeline as spray_pipeline


class _DataContainer:
    def __init__(self, data, **kwargs):
        self.data = data
        self.kwargs = kwargs


class _BasePoints:
    def __init__(self, tensor):
        self.tensor = tensor


class _Registry:
    def __init__(self):
        self.modules = {}

    def get(self, name):
        return self.modules.get(name)

    def register_module(self, name=None, force=False):
        def decorator(cls):
            self.modules[name or cls.__name__] = cls
            return cls

        return decorator


def _to_tensor(value):
    return value


class _FakeCollect3D:
    """Mirrors the vendor's indexing behaviour: missing keys raise KeyError."""

    def __init__(self, keys, meta_keys=("camera_intrinsics",), meta_lis_keys=("token",)):
        self.keys = keys
        self.meta_keys = meta_keys
        self.meta_lis_keys = meta_lis_keys

    def __call__(self, results):
        data = {}
        for key in self.keys:
            if key not in self.meta_keys:
                data[key] = results[key]
        for key in self.meta_keys:
            if key in results:
                data[key] = results[key]
        data["metas"] = {key: results[key] for key in self.meta_lis_keys if key in results}
        return data


class _FakeFormatBundle3D:
    def __init__(self, classes, with_gt=True, with_label=True):
        self.class_names = classes
        self.with_gt = with_gt
        self.with_label = with_label

    def __call__(self, results):
        if "points" in results:
            results["points"] = _DataContainer(results["points"].tensor)
        return results


_REGISTRY = _Registry()


def _fake_modules():
    mmcv = type(sys)("mmcv")
    mmcv_parallel = type(sys)("mmcv.parallel")
    mmcv_parallel.DataContainer = _DataContainer
    mmcv.parallel = mmcv_parallel

    mmdet = type(sys)("mmdet")
    mmdet_datasets = type(sys)("mmdet.datasets")
    mmdet_builder = type(sys)("mmdet.datasets.builder")
    mmdet_builder.PIPELINES = _REGISTRY
    mmdet_pipelines = type(sys)("mmdet.datasets.pipelines")
    mmdet_pipelines.to_tensor = _to_tensor
    mmdet_datasets.builder = mmdet_builder
    mmdet_datasets.pipelines = mmdet_pipelines
    mmdet.datasets = mmdet_datasets

    mmdet3d = type(sys)("mmdet3d")
    mmdet3d_core = type(sys)("mmdet3d.core")
    mmdet3d_points = type(sys)("mmdet3d.core.points")
    mmdet3d_points.BasePoints = _BasePoints
    mmdet3d_core.points = mmdet3d_points
    mmdet3d_datasets = type(sys)("mmdet3d.datasets")
    mmdet3d_pipelines = type(sys)("mmdet3d.datasets.pipelines")
    mmdet3d_formating = type(sys)("mmdet3d.datasets.pipelines.formating")
    mmdet3d_formating.Collect3D = _FakeCollect3D
    mmdet3d_formating.DefaultFormatBundle3D = _FakeFormatBundle3D
    mmdet3d_pipelines.formating = mmdet3d_formating
    mmdet3d_datasets.pipelines = mmdet3d_pipelines
    mmdet3d.datasets = mmdet3d_datasets
    mmdet3d.core = mmdet3d_core
    mmdet3d.models = type(sys)("mmdet3d.models")

    return {
        "mmcv": mmcv,
        "mmcv.parallel": mmcv_parallel,
        "mmdet": mmdet,
        "mmdet.datasets": mmdet_datasets,
        "mmdet.datasets.builder": mmdet_builder,
        "mmdet.datasets.pipelines": mmdet_pipelines,
        "mmdet3d": mmdet3d,
        "mmdet3d.core": mmdet3d_core,
        "mmdet3d.core.points": mmdet3d_points,
        "mmdet3d.datasets": mmdet3d_datasets,
        "mmdet3d.datasets.pipelines": mmdet3d_pipelines,
        "mmdet3d.datasets.pipelines.formating": mmdet3d_formating,
        "mmdet3d.models": mmdet3d.models,
    }


@pytest.fixture
def fake_vendor():
    modules = _fake_modules()
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    _REGISTRY.modules.clear()
    try:
        yield modules
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_collect_forwards_points_clean(fake_vendor):
    collect = spray_pipeline.build_collect3d()(keys=["points"])

    out = collect({"points": "P", "points_clean": "C"})

    assert out["points"] == "P"
    assert out["points_clean"] == "C"


def test_collect_without_points_clean_matches_vendor(fake_vendor):
    Collect3D, _ = spray_pipeline._formatting_base()
    original = Collect3D(keys=["points"])({"points": np.zeros((2, 5))})
    collect = spray_pipeline.build_collect3d()(keys=["points"])

    out = collect({"points": np.zeros((2, 5))})

    assert out.keys() == original.keys()
    assert out["points"].shape == original["points"].shape


def test_collect_clean_key_none_restores_vendor_behaviour(fake_vendor):
    collect = spray_pipeline.build_collect3d()(keys=["points"], clean_key=None)

    out = collect({"points": "P", "points_clean": "C"})

    assert "points_clean" not in out


def test_format_wraps_points_clean_as_datacontainer(fake_vendor):
    format_bundle = spray_pipeline.build_format_bundle()(classes=["car"])
    points = _BasePoints(np.zeros((2, 5), dtype=np.float32))
    clean = _BasePoints(np.ones((2, 5), dtype=np.float32))

    out = format_bundle({"points": points, "points_clean": clean})

    assert set(out) == {"points", "points_clean"}
    assert isinstance(out["points"], _DataContainer)
    assert isinstance(out["points_clean"], _DataContainer)
    assert np.array_equal(out["points_clean"].data, clean.tensor)


def test_format_without_points_clean_matches_vendor(fake_vendor):
    _, DefaultFormatBundle3D = spray_pipeline._formatting_base()
    format_bundle = spray_pipeline.build_format_bundle()(classes=["car"])
    points = _BasePoints(np.zeros((2, 5), dtype=np.float32))

    original = DefaultFormatBundle3D(classes=["car"])({"points": points})
    out = format_bundle({"points": points})

    assert set(out) == set(original) == {"points"}
    assert np.array_equal(out["points"].data, original["points"].data)


def test_points_clean_survives_format_then_collect(fake_vendor):
    format_bundle = spray_pipeline.build_format_bundle()(classes=["car"])
    collect = spray_pipeline.build_collect3d()(keys=["points"])
    results = {
        "points": _BasePoints(np.zeros((2, 5), dtype=np.float32)),
        "points_clean": _BasePoints(np.ones((2, 5), dtype=np.float32)),
    }

    batch = collect(format_bundle(results))

    assert set(batch) >= {"points", "points_clean"}
    assert isinstance(batch["points_clean"], _DataContainer)
    assert isinstance(batch["points"], _DataContainer)


def test_missing_points_clean_survives_format_then_collect(fake_vendor):
    format_bundle = spray_pipeline.build_format_bundle()(classes=["car"])
    collect = spray_pipeline.build_collect3d()(keys=["points"])
    results = {"points": _BasePoints(np.zeros((2, 5), dtype=np.float32))}

    batch = collect(format_bundle(results))

    assert set(batch) == {"points", "metas"}


def test_install_registers_pipeline_classes(fake_vendor):
    installed = spray_pipeline.install()

    assert installed["CleanPointsCollect3D"] is _REGISTRY.get("CleanPointsCollect3D")
    assert installed["CleanPointsFormatBundle3D"] is _REGISTRY.get(
        "CleanPointsFormatBundle3D"
    )
