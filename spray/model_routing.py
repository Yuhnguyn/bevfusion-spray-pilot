"""BEVFusion subclass that routes ``points_clean`` to the camera branch.

``BEVFusion.forward`` in the pinned MIT tree calls
``extract_camera_features(img, points, ...)`` for the camera encoder and
``extract_lidar_features(points)`` for the LiDAR encoder with the same
augmented ``points``. To keep the camera branch clean, this subclass overrides
only ``extract_camera_features``: ``forward`` stores ``points_clean`` for the
duration of the call and delegates everything else to the base model. No module
is added or replaced, so the parameter count is unchanged.

The class is built inside :func:`build_clean_points_bevfusion` and comes from
the pinned, gitignored vendor runtime package, so importing this module never
requires mmcv/mmdet3d. :func:`install` registers it into ``FUSIONMODELS`` when
available; ticket 10 points ``model.type`` at ``CleanPointsBEVFusion``.
"""

from __future__ import annotations

DEFAULT_MODEL_NAME = "CleanPointsBEVFusion"

__all__ = ["DEFAULT_MODEL_NAME", "build_clean_points_bevfusion", "install"]


def _base_model():
    from mmdet3d.models.fusion_models.bevfusion import BEVFusion

    return BEVFusion


def _fusion_registry():
    from mmdet3d.models import FUSIONMODELS

    return FUSIONMODELS


def build_clean_points_bevfusion():
    """Return the ``BEVFusion`` subclass routing clean points to the camera."""

    from mmcv.runner import auto_fp16

    BEVFusion = _base_model()

    class CleanPointsBEVFusion(BEVFusion):
        _points_clean = None

        @auto_fp16(apply_to=("img", "points", "points_clean"))
        def forward(self, img, points, *args, points_clean=None, **kwargs):
            self._points_clean = points_clean
            try:
                return super().forward(img, points, *args, **kwargs)
            finally:
                self._points_clean = None

        def extract_camera_features(self, img, points, *args, **kwargs):
            clean = self._points_clean
            source = points if clean is None else clean
            return super().extract_camera_features(img, source, *args, **kwargs)

    return CleanPointsBEVFusion


def install():
    """Build and register the subclass; return ``{name: class}``.

    Returns an empty dict when mmcv/mmdet3d are unavailable (laptop case).
    """

    try:
        registry = _fusion_registry()
        cls = build_clean_points_bevfusion()
    except Exception:  # noqa: BLE001 - laptop has no mmcv/mmdet3d
        return {}
    existing = registry.get(DEFAULT_MODEL_NAME)
    if existing is None:
        existing = registry.register_module(name=DEFAULT_MODEL_NAME)(cls)
    return {DEFAULT_MODEL_NAME: existing}


_INSTALLED = install()
