"""Static guards for the train kernel script.

Kaggle uploads only ``main.py`` as ``/kaggle/src/script.py``; sibling modules are
not present until the dataset is extracted, so ``main.py`` must import stdlib
only. ``main.py`` is not imported here because it resolves ``/kaggle/input`` at
import time; the source is read as text and parsed with ``ast`` instead.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN = ROOT / "kaggle" / "train" / "main.py"
DEVKIT_DEPS = ROOT / "kaggle" / "train" / "devkit_deps.py"


def test_uv_is_primary_path_and_devkit_packages_pinned():
    src = MAIN.read_text()
    assert "pip_into_env(" in src
    assert "ensurepip" in src
    assert src.index("pip_into_env(") < src.index("ensurepip")


def test_main_imports_stdlib_only():
    tree = ast.parse(MAIN.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    assert roots <= {"importlib", "pathlib", "sys"}, roots


def test_devkit_packages_pins():
    src = MAIN.read_text()
    assert "def devkit_packages(" in src
    assert '"nuscenes-devkit==%s"' in src
    assert '"numpy==1.22.4"' in src
    assert '"opencv-python==4.8.1.78"' in src


def test_no_sibling_module():
    assert not DEVKIT_DEPS.exists()


def _function_source(name):
    src = MAIN.read_text()
    node = next(
        item
        for item in ast.parse(src).body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(src, node) or ""


def test_numba_errors_shim_writes_alias_into_site_packages():
    body = _function_source("install_numba_errors_shim")
    assert '"numba" / "errors.py"' in body
    assert "numba.core.errors" in body
    assert "mmdet3d.datasets.pipelines" in body
    assert "SMOKE_NUMBA_SHIM_OK" in body


def test_numba_shim_runs_before_devkit_install():
    body = _function_source("main")
    assert "install_numba_errors_shim(e2e)" in body
    assert "install_devkit(e2e)" in body
    assert body.index("install_numba_errors_shim(e2e)") < body.index("install_devkit(e2e)")
