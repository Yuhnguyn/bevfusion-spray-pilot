"""Calibrate the plume output against RoadSpray ``*_static`` (ADR-0006 D2).

Bảng SSPP ``cal`` cũ đã bị thay: ``cal`` chứa 6/12 scene test (V2). Nguồn mới
không leak vì RoadSpray static không nằm trong tập đánh giá; dải bất định
±30-40 % ghi trong docs/measurements/roadspray-static-clusters-by-speed.md.
"""

import numpy as np
import pytest

from spray import plume
from spray.plume import (
    PlumeConfig,
    _injected_budget,
    cluster_count_for_speed,
    cluster_rate_for_speed,
    visible_cluster_count_for_speed,
)

# [ĐO] Δ=1,0 (a3_targets_static.json, a3_targets_static.json key "{v}_1.0") —
# bảng cũ Δ=2,5 đã bị bỏ. Nguồn: RoadSpray static D2.
CAL_CLUSTERS_PER_FRAME = {
    "crafter": {
        50: 9.04,
        60: 14.40,
        70: 19.77,
        80: 25.13,
        90: 30.50,
        100: 35.86,
        110: 34.93,
        120: 34.01,
        130: 33.08,
    },
    "golf": {
        50: 4.73,
        60: 8.79,
        70: 13.19,
        80: 17.80,
        90: 20.88,
        100: 22.56,
        110: 21.95,
        120: 25.75,
        130: 25.18,
    },
}


def test_visible_cluster_count_matches_the_cal_table_for_both_classes():
    for vehicle_class, rows in CAL_CLUSTERS_PER_FRAME.items():
        for speed_kmh, expected in rows.items():
            got = visible_cluster_count_for_speed(
                float(speed_kmh), vehicle_class=vehicle_class
            )
            assert abs(got - expected) <= 0.20 * expected, (
                vehicle_class,
                speed_kmh,
                got,
                expected,
            )


def test_default_class_is_crafter_and_golf_is_not_derived_from_it():
    for speed_kmh, expected in CAL_CLUSTERS_PER_FRAME["crafter"].items():
        assert (
            cluster_count_for_speed(float(speed_kmh))
            == visible_cluster_count_for_speed(
                float(speed_kmh), vehicle_class="crafter"
            )
        )
    assert cluster_count_for_speed(100.0, vehicle_class="golf") == 23
    assert cluster_count_for_speed(100.0, vehicle_class="crafter") == 36  # Δ=1,0


def test_unknown_vehicle_class_is_rejected():
    with pytest.raises(ValueError):
        visible_cluster_count_for_speed(100.0, vehicle_class="sedan")


def test_rate_does_not_contain_water_film_height():
    dry = cluster_rate_for_speed(100.0, PlumeConfig(water_film_height_m=0.001))
    wetter = cluster_rate_for_speed(100.0, PlumeConfig(water_film_height_m=0.0012))

    assert dry == pytest.approx(wetter)


def test_rate_is_closed_at_the_one_millimetre_reference():
    # Ticket 29e-c: WFH_REF_MM = 1.0. `rate` is the reference visible count
    # divided by the steady-state alive factor at 1 mm, so at wfh = 1 mm it
    # reproduces the table exactly. Ticket 29f: the factor is 4T/dt (hard
    # prune), not the geometric K.
    assert plume.WFH_REF_MM == 1.0
    for speed_kmh, expected in CAL_CLUSTERS_PER_FRAME["crafter"].items():
        rate = cluster_rate_for_speed(float(speed_kmh))
        config = PlumeConfig(water_film_height_m=1.0 / 1000.0)
        visible = rate * plume.steady_state_alive_factor(float(speed_kmh), config)
        assert visible == pytest.approx(expected, rel=0.05)


def test_no_clusters_below_the_first_cal_row():
    assert cluster_count_for_speed(49.9) == 0
    assert cluster_count_for_speed(50.0) == 9  # [ĐO] Δ=1,0: 9,04 -> 9


@pytest.mark.parametrize(
    ("real_points", "expected"),
    [(1000, 500), (10000, 500), (40000, 2000)],
)
def test_injected_budget_is_five_percent_with_a_floor_of_500(
    real_points, expected
):
    assert _injected_budget(real_points) == expected
