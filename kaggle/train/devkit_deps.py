"""Dependency pins for installing ``nuscenes-devkit`` in the train kernel.

Kept separate from ``main.py`` so it can be imported without touching Kaggle
paths. numpy and opencv-python stay pinned: the devkit's ``numpy`` requirement
is loose and letting the resolver upgrade it breaks the pinned torch 1.10 /
numba stack.
"""


def devkit_packages(version):
    """Return the packages that install ``nuscenes-devkit==<version>`` safely."""
    return [
        "nuscenes-devkit==%s" % version,
        "numpy==1.22.4",
        "opencv-python==4.8.1.78",
    ]
