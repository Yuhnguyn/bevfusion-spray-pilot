import numpy as np
import pytest

from spray.plume import (
    PlumeConfig,
    cluster_count_for_speed,
    steady_state_cluster_factor,
)


def test_cluster_count_follows_the_cal_table():
    # [ĐO] Δ=1,0 (a3_targets_static.json) — bảng cũ Δ=2,5 đã bị bỏ.
    # Bảng RoadSpray static D2: 9,04 @50 · 14,40 @60 · 25,13 @80 · 35,86 @100 · 33,08 @130.
    assert cluster_count_for_speed(39.0) == 0
    assert cluster_count_for_speed(40.0) == 0
    assert cluster_count_for_speed(45.0) == 0
    assert cluster_count_for_speed(50.0) == 9
    assert cluster_count_for_speed(60.0) == 14
    assert cluster_count_for_speed(80.0) == 25
    assert cluster_count_for_speed(100.0) == 36
    assert cluster_count_for_speed(130.0) == 33


def test_no_clusters_at_45_kmh():
    assert cluster_count_for_speed(45.0) == 0


def test_cluster_count_at_130_kmh_with_one_mm_water_film():
    # [ĐO] Δ=1,0: 33,08 cụm/frame @130 -> 33.
    assert cluster_count_for_speed(130.0, PlumeConfig(water_film_height_m=0.001)) == 33
    assert cluster_count_for_speed(130.0, PlumeConfig(water_film_height_m=0.0)) == 0


def test_cluster_count_at_80_kmh_matches_the_table():
    # [ĐO] Δ=1,0 (a3_targets_static.json) — bảng cũ Δ=2,5 đã bị bỏ: 25,13 cụm/frame @80.
    assert cluster_count_for_speed(80.0) == 25


def test_steady_state_cluster_factor_is_the_paper_geometric_sum():
    """K = Σ_{k≥0} exp(-k·Δt/T) = 1/(1−exp(−Δt/T)) — paper Eq. 1 (QĐ12).

    Trước QĐ12 code cắt cứng ở 4T nên tổng chỉ tới k = 8 và K = 2,5133. Nay cụm
    tan xác suất nên cấp số nhân **vô hạn**: T = 0,2 s, Δt = 0,1 s → 2,5415.
    """
    config = PlumeConfig()
    at_fifty = steady_state_cluster_factor(50.0, config)
    expected = 1.0 / (1.0 - np.exp(-0.1 / 0.2))

    assert at_fifty == pytest.approx(expected)
    assert at_fifty == pytest.approx(2.5415, abs=1e-4)
    # T tăng nhẹ theo tốc độ (dee.cpp:530) nên K ở 130 km/h lớn hơn.
    assert steady_state_cluster_factor(130.0, config) > at_fifty


def test_radius_distribution_matches_paper():
    """[PAPER] Fig. 5: r_cl = exp(-1.2 + 0.8 Z), KHÔNG có trần."""
    from spray.plume_state import PlumeState, PlumeStateConfig, RADIUS_MAX_M
    import numpy as np

    assert RADIUS_MAX_M == float("inf"), "paper không đặt trần cho r_cl"
    cfg = PlumeStateConfig(radius_sigma=0.8)
    rng = np.random.default_rng(0)
    draws = np.exp(rng.normal(np.log(0.3012), cfg.radius_sigma, size=200_000))
    assert abs(np.median(draws) - 0.3012) < 0.01
    # p90 lý thuyết = exp(-1.2 + 1.2816*0.8) = 0.84 m
    assert abs(np.percentile(draws, 90) - 0.84) < 0.05
