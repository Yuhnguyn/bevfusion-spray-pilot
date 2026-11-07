"""Pipeline replacements that carry ``points_clean`` down to the model.

The pinned vendor pipeline has two gaps:

- ``DefaultFormatBundle3D`` only wraps ``points``/``radar`` into a
  ``DataContainer``;
- ``Collect3D`` only forwards keys listed in ``keys`` and raises ``KeyError``
  when one is missing.

:class:`spray.plume_transform.PlumeTransform` writes ``points_clean`` into the
result dict, so without these replacements the clean stream never reaches
``BEVFusion.forward``.

Both classes live here instead of the pinned, gitignored ``mit/bevfusion`` tree.
They are built lazily (inside :func:`build_collect3d` /
:func:`build_format_bundle`) so importing this module does not require
mmcv/mmdet3d; :func:`install` registers them into ``PIPELINES`` when those
packages are importable.

Config usage (ticket 10)::

    dict(type="CleanPointsFormatBundle3D", classes=..., clean_key="points_clean")
    dict(type="CleanPointsCollect3D", keys=[...], clean_key="points_clean")

``clean_key=None`` restores the original (vendor) behaviour.
"""

from __future__ import annotations

DEFAULT_CLEAN_KEY = "points_clean"

__all__ = [
    "DEFAULT_CLEAN_KEY",
    "build_collect3d",
    "build_format_bundle",
    "install",
]


def _formatting_base():
    from mmdet3d.datasets.pipelines.formating import (
        Collect3D,
        DefaultFormatBundle3D,
    )

    return Collect3D, DefaultFormatBundle3D


def _pipelines_registry():
    from mmdet.datasets.builder import PIPELINES

    return PIPELINES


def _register(registry, name, cls):
    existing = registry.get(name)
    if existing is not None:
        return existing
    return registry.register_module(name=name)(cls)


def build_collect3d():
    """Return a ``Collect3D`` subclass that also forwards ``points_clean``.

    When ``points_clean`` is absent from ``results`` the base implementation is
    called with the key removed, which keeps both the original output and the
    original ``KeyError`` for any other missing key.
    """

    from types import SimpleNamespace

    Collect3D, _ = _formatting_base()

    class CleanPointsCollect3D(Collect3D):
        def __init__(self, keys, clean_key=DEFAULT_CLEAN_KEY, **kwargs):
            self.clean_key = clean_key
            keys = list(keys)
            if clean_key is not None and clean_key not in keys:
                keys.append(clean_key)
            super().__init__(keys=keys, **kwargs)

        def __call__(self, results):
            if self.clean_key is None or self.clean_key in results:
                return super().__call__(results)
            proxy = SimpleNamespace(
                keys=[key for key in self.keys if key != self.clean_key],
                meta_keys=self.meta_keys,
                meta_lis_keys=self.meta_lis_keys,
            )
            return Collect3D.__call__(proxy, results)

    return CleanPointsCollect3D


def build_format_bundle():
    """Return a ``DefaultFormatBundle3D`` subclass that wraps ``points_clean``."""

    from mmcv.parallel import DataContainer as DC
    from mmdet.datasets.pipelines import to_tensor
    from mmdet3d.core.points import BasePoints

    _, DefaultFormatBundle3D = _formatting_base()

    class CleanPointsFormatBundle3D(DefaultFormatBundle3D):
        def __init__(self, *args, clean_key=DEFAULT_CLEAN_KEY, **kwargs):
            self.clean_key = clean_key
            super().__init__(*args, **kwargs)

        def __call__(self, results):
            results = super().__call__(results)
            key = self.clean_key
            if key is None or key not in results:
                return results
            value = results[key]
            tensor = value.tensor if isinstance(value, BasePoints) else to_tensor(value)
            results[key] = DC(tensor)
            return results

    return CleanPointsFormatBundle3D


def install():
    """Build and register both replacements; return them keyed by name.

    Returns an empty dict when mmcv/mmdet3d are unavailable, which is the
    normal case on a laptop.
    """

    classes = {}
    try:
        registry = _pipelines_registry()
        collect_cls = build_collect3d()
        format_cls = build_format_bundle()
    except Exception:  # noqa: BLE001 - laptop has no mmcv/mmdet3d
        return classes
    classes["CleanPointsCollect3D"] = _register(
        registry, "CleanPointsCollect3D", collect_cls
    )
    classes["CleanPointsFormatBundle3D"] = _register(
        registry, "CleanPointsFormatBundle3D", format_cls
    )
    return classes


_INSTALLED = install()
