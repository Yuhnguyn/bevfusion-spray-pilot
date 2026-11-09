"""Static guard: the train kernel installs nuscenes-devkit through uv first.

``main.py`` is not imported here because it resolves ``/kaggle/input`` at import
time; the source is read as text instead, and ``devkit_deps`` is loaded by path.
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN = ROOT / "kaggle" / "train" / "main.py"
DEVKIT_DEPS = ROOT / "kaggle" / "train" / "devkit_deps.py"


def _load_devkit_deps():
    spec = importlib.util.spec_from_file_location(
        "devkit_deps_under_test", DEVKIT_DEPS
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_uv_is_primary_path_and_devkit_packages_pinned():
    src = MAIN.read_text()
    assert "pip_into_env(" in src
    assert "ensurepip" in src
    assert src.index("pip_into_env(") < src.index("ensurepip")

    packages = _load_devkit_deps().devkit_packages("1.1.11")
    assert len(packages) == 3
    assert "nuscenes-devkit==1.1.11" in packages
    assert "numpy==1.22.4" in packages
    assert "opencv-python==4.8.1.78" in packages
