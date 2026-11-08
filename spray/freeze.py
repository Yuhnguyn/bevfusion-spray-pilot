"""Freeze the camera branch by parameter *name*.

Names are used instead of module attributes on purpose: the vendored MIT model
is a pinned third-party tree, and attribute paths are exactly what changes when
it is re-vendored.  A parameter name that matches neither list is reported in
``unmatched`` rather than raising, so the kernel log shows the rename instead of
silently training (or freezing) the wrong thing.

Verification::

    report = apply_freeze(model)
    print(report["n_trainable_params"], report["unmatched"])
"""

from __future__ import annotations

__all__ = [
    "FROZEN_PREFIXES",
    "FROZEN_SUBSTRINGS",
    "TRAINABLE_PREFIXES",
    "apply_freeze",
    "is_frozen",
]

# [CHỌN] Camera branch stays at the pretrained checkpoint.
FROZEN_PREFIXES = ("img_backbone.", "img_neck.", "encoders.camera.")
# Backstop for a differently-rooted view transform.
FROZEN_SUBSTRINGS = ("vtransform.",)

# Everything else that is expected to learn: LiDAR encoder, fusion, BEV
# backbone/neck, detection heads.
TRAINABLE_PREFIXES = (
    "pts_voxel_encoder.",
    "pts_middle_encoder.",
    "pts_backbone.",
    "pts_neck.",
    "encoders.lidar.",
    "fuser.",
    "decoder.",
    "heads.",
)


def is_frozen(
    name: str,
    frozen_prefixes: tuple[str, ...] = FROZEN_PREFIXES,
    frozen_substrings: tuple[str, ...] = FROZEN_SUBSTRINGS,
) -> bool:
    """True when ``name`` belongs to the frozen camera branch."""
    if any(name.startswith(prefix) for prefix in frozen_prefixes):
        return True
    return any(sub in name for sub in frozen_substrings)


def apply_freeze(
    module,
    frozen_prefixes: tuple[str, ...] = FROZEN_PREFIXES,
    frozen_substrings: tuple[str, ...] = FROZEN_SUBSTRINGS,
    trainable_prefixes: tuple[str, ...] = TRAINABLE_PREFIXES,
) -> dict:
    """Set ``requires_grad=False`` on frozen names and return a report."""
    frozen_names: list[str] = []
    trainable_names: list[str] = []
    unmatched: list[str] = []

    for name, param in module.named_parameters():
        frozen = is_frozen(name, frozen_prefixes, frozen_substrings)
        if frozen:
            param.requires_grad_(False)
            frozen_names.append(name)
        elif not any(name.startswith(prefix) for prefix in trainable_prefixes):
            unmatched.append(name)
        if param.requires_grad:
            trainable_names.append(name)

    params = list(module.parameters())
    return {
        "n_total_params": sum(param.numel() for param in params),
        "n_trainable_params": sum(
            param.numel() for param in params if param.requires_grad
        ),
        "trainable_names": trainable_names,
        "frozen_names": frozen_names,
        "unmatched": unmatched,
    }
