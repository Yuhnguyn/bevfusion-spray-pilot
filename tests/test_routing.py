"""Tests for ``spray.model_routing`` (stub base, no mmcv/mmdet3d required)."""

import pathlib
import subprocess
import sys
import textwrap

import pytest
import torch

from spray import model_routing


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


def _identity_auto_fp16(apply_to=None, out_fp32=False):
    def decorate(func):
        return func

    return decorate


class _StubBEVFusion(torch.nn.Module):
    """Minimal stand-in that mirrors the vendor dispatch points."""

    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(3, 4)
        self.camera_points = None
        self.lidar_points = None

    def extract_camera_features(self, img, points):
        self.camera_points = points
        return points

    def extract_lidar_features(self, points):
        self.lidar_points = points
        return points

    def forward(self, img, points, **kwargs):
        return [
            self.extract_camera_features(img, points),
            self.extract_lidar_features(points),
        ]


_REGISTRY = _Registry()


def _fake_modules():
    mmcv = type(sys)("mmcv")
    mmcv_runner = type(sys)("mmcv.runner")
    mmcv_runner.auto_fp16 = _identity_auto_fp16
    mmcv.runner = mmcv_runner

    mmdet3d = type(sys)("mmdet3d")
    models = type(sys)("mmdet3d.models")
    models.FUSIONMODELS = _REGISTRY
    fusion_models = type(sys)("mmdet3d.models.fusion_models")
    bevfusion = type(sys)("mmdet3d.models.fusion_models.bevfusion")
    bevfusion.BEVFusion = _StubBEVFusion
    fusion_models.bevfusion = bevfusion
    models.fusion_models = fusion_models
    mmdet3d.models = models

    return {
        "mmcv": mmcv,
        "mmcv.runner": mmcv_runner,
        "mmdet3d": mmdet3d,
        "mmdet3d.models": models,
        "mmdet3d.models.fusion_models": fusion_models,
        "mmdet3d.models.fusion_models.bevfusion": bevfusion,
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


def _model_and_markers():
    model = model_routing.build_clean_points_bevfusion()()
    points = torch.tensor([[1.0, 2.0, 3.0]])
    clean = torch.tensor([[9.0, 8.0, 7.0]])
    return model, points, clean


def test_camera_branch_receives_clean_points(fake_vendor):
    model, points, clean = _model_and_markers()

    model(img=torch.zeros(1), points=points, points_clean=clean)

    assert torch.equal(model.camera_points, clean)


def test_lidar_branch_receives_augmented_points(fake_vendor):
    model, points, clean = _model_and_markers()

    model(img=torch.zeros(1), points=points, points_clean=clean)

    assert torch.equal(model.lidar_points, points)


def test_without_clean_points_camera_receives_points(fake_vendor):
    model, points, _ = _model_and_markers()

    model(img=torch.zeros(1), points=points, points_clean=None)
    assert torch.equal(model.camera_points, points)
    assert torch.equal(model.lidar_points, points)

    model(img=torch.zeros(1), points=points)
    assert model.camera_points is points
    assert model._points_clean is None


def test_parameter_count_unchanged(fake_vendor):
    model = model_routing.build_clean_points_bevfusion()()
    base = _StubBEVFusion()

    assert sum(p.numel() for p in base.parameters()) == 16
    assert sum(p.numel() for p in model.parameters()) == 16
    assert [name for name, _ in model.named_parameters()] == [
        name for name, _ in base.named_parameters()
    ]


def test_install_registers_fusion_model(fake_vendor):
    installed = model_routing.install()

    registered = _REGISTRY.get(model_routing.DEFAULT_MODEL_NAME)
    assert installed[model_routing.DEFAULT_MODEL_NAME] is registered
    assert issubclass(registered, _StubBEVFusion)


def test_spray_modules_import_without_mmcv_or_mmdet3d():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class Blocker(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in {"mmcv", "mmdet", "mmdet3d"}:
                    raise ImportError("blocked: " + name)
                return None

        sys.meta_path.insert(0, Blocker())
        import spray.pipeline
        import spray.model_routing

        loaded = [
            name
            for name in sys.modules
            if name.split(".")[0] in {"mmcv", "mmdet", "mmdet3d"}
        ]
        assert loaded == [], loaded
        print("ok")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
