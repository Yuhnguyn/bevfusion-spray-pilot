"""Ticket 29g: ``render()`` of ``scripts/measure_29f.py`` must count the cells
*below* the stop gate, not the ones above it.

The worker of 29f printed ``high`` (``alive_ratio > STOP_GATE``) under the
label "≤ STOP_GATE", so the conclusion of section 3 said 16/18 cells were
under the gate while only 2/18 actually were.
"""

from __future__ import annotations

import re

import pytest

from scripts.measure_29f import STOP_GATE, render


def _cell(group: str, speed: float, alive_ratio: float) -> dict:
    """Minimal cell dict: ``render`` only reads the keys it formats."""
    return {
        "group": group,
        "speed": speed,
        "frames": 90,
        "alive": alive_ratio * 10.0,
        "alive_vs_target": 1.0,
        "visible": 5.0,
        "dbscan": 5.0,
        "covered": 5.0,
        "largest_cover": 1.0,
        "alive_not_dbscan": 5.0,
        "det_per_alive": 4.0,
        "real_per_frame": 10.0,
        "delta": -5.0,
        "alive_ratio": alive_ratio,
        "dbscan_ratio": 0.5,
        "alive_target": 10,
        "spawn_rate": 1.0,
        "lifetime_s": 1.0,
        "capped": 0,
    }


def _cells(ratios: list[float]) -> list[dict]:
    return [
        _cell("Crafter_dynamic", 50.0 + 10.0 * index, ratio)
        for index, ratio in enumerate(ratios)
    ]


@pytest.mark.parametrize(
    ("ratios", "below"),
    [
        # Exactly on the gate counts as below (``<=``).
        ([0.5, 0.7, 1.0], 2),
        # Nothing under the gate: branch 3a, 0 cells reported.
        ([0.8, 1.2, 1.5], 0),
        # All under the gate: branch 3b, all cells reported.
        ([0.1, 0.2, 0.3], 3),
    ],
)
def test_section_3_counts_cells_below_the_stop_gate(ratios, below):
    body = render(_cells(ratios), 1.5)
    section = body.split("## 3. Kết luận cửa chặn")[1]

    assert f"{below}/{len(ratios)} ô có `alive` ≤ {STOP_GATE:g}×" in section
    assert f"{below}/{len(ratios)} ô có `alive` > {STOP_GATE:g}×" not in section


def test_section_3_never_reports_more_below_than_cells():
    """The 29f bug: 16/18 reported below while 16 cells were *above*."""
    ratios = [0.5, 0.6] + [1.1] * 16
    body = render(_cells(ratios), 1.5)
    section = body.split("## 3. Kết luận cửa chặn")[1]

    assert re.search(r"2/18 ô có `alive` ≤", section)
    assert not re.search(r"16/18 ô có `alive` ≤", section)
