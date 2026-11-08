"""Pure-Python config placeholder resolver (runs on a laptop, no mmcv).

The e2e test loads ``mit/bevfusion/configs/nuscenes/default.yaml`` with
``yaml.safe_load`` instead of ``mmcv.Config.fromfile``, so the mmcv ``${...}``
interpolation has to be applied here.  Keeping it in its own module means the
resolver can be tested without the pinned kernel stack.
"""

import re

_PLACEHOLDER = re.compile(r"^\$\{([^}]+)\}$")


def _lookup(roots, path):
    """Walk a path such as ``augment3d.rotate`` or ``augment2d.resize[0]``."""
    cur = roots
    for part in path.split("."):
        match = re.match(r"^(\w+)((?:\[\d+\])*)$", part)
        key, index = match.group(1), match.group(2)
        cur = cur[key]
        for i in re.findall(r"\[(\d+)\]", index):
            cur = cur[int(i)]
    return cur


def _resolve(node, roots):
    """Replace every ``${dotted.path}`` string with the real value in ``roots``."""
    if isinstance(node, dict):
        return {k: _resolve(v, roots) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, roots) for v in node]
    if isinstance(node, str):
        match = _PLACEHOLDER.match(node.strip())
        if match:
            return _resolve(_lookup(roots, match.group(1)), roots)
    return node


def test_resolve_placeholders():
    roots = {
        "a": [1.0, 2.0],
        "b": {"c": 3},
        "steps": [{"v": "${a}"}, {"w": "${b.c}"}, {"u": "${a[1]}"}],
    }
    assert _resolve(roots["steps"], roots) == [
        {"v": [1.0, 2.0]},
        {"w": 3},
        {"u": 2.0},
    ]
