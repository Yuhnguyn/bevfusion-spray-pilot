"""Freeze report on a fake module that mirrors the vendor parameter names."""

import torch
from torch import nn

from spray.freeze import apply_freeze, is_frozen

CAMERA_PREFIXES = ("img_backbone.", "img_neck.", "encoders.camera.")


def _leaf(rows, cols):
    module = nn.Module()
    module.weight = nn.Parameter(torch.zeros(rows, cols))
    module.bias = nn.Parameter(torch.zeros(rows))
    return module


def _module():
    root = nn.Module()
    root.img_backbone = _leaf(4, 2)
    root.img_neck = _leaf(3, 2)
    encoders = nn.Module()
    encoders.camera = _leaf(5, 2)
    encoders.lidar = _leaf(6, 2)
    root.encoders = encoders
    root.fuser = _leaf(7, 2)
    root.decoder = _leaf(8, 2)
    root.heads = _leaf(9, 2)
    root.pts_voxel_encoder = _leaf(1, 1)
    root.pts_middle_encoder = _leaf(2, 1)
    root.pts_backbone = _leaf(3, 1)
    root.pts_neck = _leaf(4, 1)
    return root


def _camera(name):
    return any(name.startswith(prefix) for prefix in CAMERA_PREFIXES)


def _expected_counts(module):
    params = dict(module.named_parameters())
    total = sum(param.numel() for param in params.values())
    trainable = sum(
        param.numel() for name, param in params.items() if not _camera(name)
    )
    return total, trainable


def test_only_camera_branch_is_frozen():
    module = _module()
    total, trainable = _expected_counts(module)

    report = apply_freeze(module)

    assert report["n_total_params"] == total
    assert report["n_trainable_params"] == trainable
    assert set(report["frozen_names"]) == {
        name for name, _ in module.named_parameters() if _camera(name)
    }
    assert not set(report["trainable_names"]) & set(report["frozen_names"])
    for name, param in module.named_parameters():
        assert param.requires_grad == (not _camera(name)), name


def test_unmatched_empty_then_reports_unknown_names():
    module = _module()
    assert apply_freeze(module)["unmatched"] == []

    module.classifier = _leaf(2, 3)
    report = apply_freeze(module)

    assert report["unmatched"] == ["classifier.weight", "classifier.bias"]
    assert "classifier.weight" in report["trainable_names"]


def test_apply_freeze_is_idempotent():
    module = _module()

    first = apply_freeze(module)
    second = apply_freeze(module)

    assert first == second


def test_is_frozen_matches_prefixes_and_vtransform_substring():
    assert is_frozen("img_backbone.conv1.weight")
    assert is_frozen("img_neck.lateral.weight")
    assert is_frozen("encoders.camera.backbone.weight")
    assert is_frozen("lidar.vtransform.reduce.weight")
    assert not is_frozen("fuser.weight")
    assert not is_frozen("heads.object.weight")
