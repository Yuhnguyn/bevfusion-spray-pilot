"""Pure-Python YAML helpers: placeholder resolution, deep merge, config diff.

The pinned MIT configs use mmcv's ``${dotted.path}`` interpolation.  mmcv is
only available inside the kernel image, so the A/B config builder on a laptop
needs its own resolver.  Nothing here imports mmcv/mmdet3d.

Placeholders are whole-string only (``"${a.b}"``), matching mmcv: a string such
as ``"${dataset_root}x"`` is left alone.  A placeholder that cannot be resolved
raises :class:`KeyError` instead of silently staying as a literal ``"${...}"``
string, because the kernel would later choke on it in a confusing place.
"""

from __future__ import annotations

import copy
import pathlib
import re
from typing import Any

import yaml

__all__ = [
    "PLACEHOLDER",
    "diff_paths",
    "load_yaml",
    "lookup",
    "merge",
    "resolve",
]

PLACEHOLDER = re.compile(r"^\$\{([^}]+)\}$")

_PART = re.compile(r"^([^\[\]]+)((?:\[\d+\])*)$")


def load_yaml(path: str | pathlib.Path) -> dict:
    """Load a YAML file into plain Python objects."""
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def lookup(roots: Any, path: str) -> Any:
    """Walk ``roots`` along a path such as ``augment3d.rotate`` or ``a.resize[0]``.

    Any missing key, out-of-range index or type mismatch becomes ``KeyError``
    so callers only have to catch one exception type.
    """
    node = roots
    for part in path.split("."):
        part = part.strip()
        match = _PART.match(part)
        if match is None:
            raise KeyError(path)
        key, indexes = match.group(1), match.group(2)
        try:
            node = node[key]
            for index in re.findall(r"\[(\d+)\]", indexes):
                node = node[int(index)]
        except (KeyError, IndexError, TypeError) as exc:
            raise KeyError(path) from exc
    return node


def resolve(node: Any, roots: Any) -> Any:
    """Recursively replace ``${...}`` strings in ``node`` using values in ``roots``.

    Resolved values are themselves resolved, so a placeholder may point at a
    value that is another placeholder.  Missing placeholders raise ``KeyError``.
    """
    if isinstance(node, dict):
        return {key: resolve(value, roots) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve(value, roots) for value in node]
    if isinstance(node, str):
        match = PLACEHOLDER.match(node.strip())
        if match is not None:
            try:
                value = lookup(roots, match.group(1))
            except KeyError as exc:
                raise KeyError(f"unresolved placeholder: {node!r}") from exc
            return resolve(value, roots)
    return node


def merge(base: dict, override: dict) -> dict:
    """Deep-merge ``override`` on top of ``base``; neither input is mutated."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def diff_paths(a: Any, b: Any, prefix: str = "") -> list[str]:
    """Return dotted paths where ``a`` and ``b`` differ.

    Dicts are compared key by key; everything else (including lists) is compared
    as a whole value, so a list difference is reported at the list's own path.
    Paths are sorted because dict keys are visited in sorted order.
    """
    paths: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in a or key not in b:
                paths.append(path)
            else:
                paths.extend(diff_paths(a[key], b[key], path))
        return paths
    if a != b:
        paths.append(prefix or "<root>")
    return paths
