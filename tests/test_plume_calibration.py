"""Ticket 29c: calibrate the plume output against measurements on ``cal``.

Only ``cal`` numbers are used (ticket 29d froze the split); ``held-out`` must
never select a parameter.
"""

import inspect

import numpy as np
import pytest

from spray import plume
from spray.plume import (
    PlumeConfig,
    _injected_budget,
    _lateral_offset,
    cluster_count_for_speed,
    cluster_rate_for_speed,
    visible_cluster_count_for_speed,
)

# docs/measurements/semantic-spray-clusters-by-speed.md, Table 1 (cal only).
CAL_CLUSTERS_PER_FRAME = {
    "crafter": {
        50: 4.18,
        60: 11.31,
        70: 17.42,
        80: 22.02,
        90: 20.69,
        100: 29.24,
        110: 28.49,
        120: 17.58,
        130: 17.69,
    },
    "golf": {
        50: 3.62,
        60: 8.84,
        70: 11.36,
        80: 12.87,
        90: 10.51,
        100: 18.07,
        110: 16.69,
        120: 15.27,
        130: 16.64,
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
    assert cluster_count_for_speed(100.0, vehicle_class="golf") == 18
    assert cluster_count_for_speed(100.0, vehicle_class="crafter") == 29


def test_unknown_vehicle_class_is_rejected():
    with pytest.raises(ValueError):
        visible_cluster_count_for_speed(100.0, vehicle_class="sedan")


def test_rate_does_not_contain_water_film_height():
    dry = cluster_rate_for_speed(100.0, PlumeConfig(water_film_height_m=0.001))
    wetter = cluster_rate_for_speed(100.0, PlumeConfig(water_film_height_m=0.0012))

    assert dry == pytest.approx(wetter)


def test_rate_is_closed_at_the_one_millimetre_reference():
    # Ticket 29e-c: WFH_REF_MM = 1.0. `rate` is the reference visible count
    # divided by K at 1 mm, so at wfh = 1 mm it reproduces the table exactly.
    assert plume.WFH_REF_MM == 1.0
    for speed_kmh, expected in CAL_CLUSTERS_PER_FRAME["crafter"].items():
        rate = cluster_rate_for_speed(float(speed_kmh))
        config = PlumeConfig(water_film_height_m=1.0 / 1000.0)
        visible = rate * plume.steady_state_cluster_factor(float(speed_kmh), config)
        assert visible == pytest.approx(expected, rel=0.05)


def test_no_clusters_below_the_first_cal_row():
    assert cluster_count_for_speed(49.9) == 0
    assert cluster_count_for_speed(50.0) == 4


@pytest.mark.parametrize(
    ("real_points", "expected"),
    [(1000, 500), (10000, 500), (40000, 2000)],
)
def test_injected_budget_is_five_percent_with_a_floor_of_500(
    real_points, expected
):
    assert _injected_budget(real_points) == expected


def test_lateral_offset_is_uniform_on_plus_minus_half_width():
    half_width = PlumeConfig().lateral_half_width_m
    rng = np.random.default_rng(0)
    samples = np.array(
        [_lateral_offset(rng, half_width) for _ in range(20_000)]
    )

    assert samples.min() >= -half_width
    assert samples.max() <= half_width

    counts, _ = np.histogram(samples, bins=10, range=(-half_width, half_width))
    expected = np.full(10, samples.size / 10.0)
    chi_square = float(((counts - expected) ** 2 / expected).sum())
    # 9 degrees of freedom, p = 0.01 -> 21.666.
    assert chi_square < 21.666


def test_inject_plume_no_longer_draws_gaussian_lateral():
    source = inspect.getsource(plume.inject_plume)

    assert "rng.normal(0.0, cfg.lateral" not in source
    assert "_lateral_offset" in source


def test_lateral_half_width_comes_from_the_cal_measurement():
    # p95(|y - y_box|) on 1,022 cal frames = 2.22 m; uniform ±a has p95 = 0.95a.
    assert PlumeConfig().lateral_half_width_m == pytest.approx(2.34, abs=0.01)
