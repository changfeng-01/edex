import pytest

from goa_eval.windowing import interval_overlap_duration, total_pairwise_overlap


def test_interval_overlap_duration_uses_endpoints_not_sample_step():
    left = [(1.0e-6, 3.0e-6), (10.0e-6, 12.0e-6)]
    right = [(2.0e-6, 4.0e-6), (10.5e-6, 11.0e-6)]

    assert total_pairwise_overlap(left, right) == pytest.approx(1.5e-6)
    assert interval_overlap_duration((1.0e-6, 3.0e-6), (2.0e-6, 4.0e-6)) == pytest.approx(1.0e-6)


def test_total_pairwise_overlap_returns_zero_for_disjoint_windows():
    assert total_pairwise_overlap([(1.0, 2.0)], [(2.5, 3.0)]) == 0.0
