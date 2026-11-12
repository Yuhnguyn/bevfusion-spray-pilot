"""Ticket 29e-d-ii: the pure helpers of the two measurement scripts.

``scripts/measure_29ed.py`` (bugs 1 and 2) and ``scripts/measure_29ed2.py``
(cluster overlap) are measurement-only code, so the tests pin the definitions
the ticket names, not the file IO.
"""

import numpy as np
import pytest

from scripts import measure_29ed, measure_29ed2


def test_stats_fills_p10_even_though_it_is_not_a_caller_quantile():
    # Bug 1: ``p10`` was initialised to nan and only filled for the quantiles
    # the caller passed, so the column was always nan.
    values = np.arange(1.0, 101.0)
    stats = measure_29ed._stats(values)
    assert stats["p10"] == pytest.approx(float(np.percentile(values, 10)))


def test_stats_keeps_p10_nan_when_there_are_no_values():
    stats = measure_29ed._stats(np.array([], dtype=np.float64))
    assert np.isnan(stats["p10"])


def test_unmerged_mask_is_elong_le_1_2_and_p_det_le_1():
    data = {
        "elong": np.array([1.0, 1.2, 1.21, 1.5]),
        "p_det": np.array([0.5, 0.9, 0.5, 3.0]),
    }
    assert measure_29ed._unmerged_mask(data).tolist() == [True, True, False, False]


def test_nearest_neighbour_normalises_by_the_two_radii():
    centres = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    radii = np.array([0.5, 0.4, 3.0])

    distance, normalised = measure_29ed2.nearest_neighbours(centres, radii)

    assert distance == pytest.approx([1.0, 1.0, 4.0])
    assert normalised == pytest.approx([1.0 / 0.9, 1.0 / 0.9, 4.0 / 3.4])


def test_nearest_neighbour_is_nan_for_a_lone_cluster():
    distance, normalised = measure_29ed2.nearest_neighbours(
        np.array([[0.0, 0.0, 0.0]]), np.array([0.5])
    )
    assert np.isnan(distance[0]) and np.isnan(normalised[0])


def test_overlap_frac_counts_only_clusters_that_have_a_neighbour():
    normalised = np.array([0.4, 1.5, np.nan, 0.9])
    # Three clusters have a neighbour and two of them overlap; the lone one is
    # not in the denominator.
    assert measure_29ed2.overlap_frac(normalised) == pytest.approx(2.0 / 3.0)


def test_pts_in_overlap_is_the_point_share_of_overlapping_clusters():
    normalised = np.array([0.5, 1.5, 2.0])
    sizes = np.array([10, 30, 60])
    assert measure_29ed2.pts_in_overlap(normalised, sizes) == pytest.approx(0.10)


def test_n_merged_counts_clusters_above_the_elongation_threshold():
    assert measure_29ed2.n_merged(np.array([1.4, 1.5, 1.51, 4.0])) == 2


def test_nn_merged_is_the_median_of_the_merged_clusters_only():
    elong = np.array([1.0, 2.0, 2.0])
    normalised = np.array([0.2, 0.6, 1.0])
    assert measure_29ed2.nn_merged(elong, normalised) == pytest.approx(0.8)


def test_frozen_results_document_names_match_the_constants():
    assert measure_29ed2.OVERLAP_THRESHOLD == pytest.approx(0.05)
    assert measure_29ed2.MERGED_ELONG == pytest.approx(1.5)
