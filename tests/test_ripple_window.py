import numpy as np
import pytest

from goa_eval.metrics import RealEvalConfig, compute_stage_metrics


def test_ripple_excludes_pulse_edges_and_counts_hold_disturbance():
    time = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float) * 1e-6
    signal = np.array([0.0, 0.0, 6.0, 14.0, 13.0, 6.0, 0.0, 0.1, 0.6, 0.2, 0.0])

    row = compute_stage_metrics(
        time,
        signal,
        RealEvalConfig(
            high_threshold=5.0,
            low_threshold=1.0,
            min_pulse_width=2.0e-6,
            edge_buffer_ratio=0.2,
        ),
    )

    assert row["PulseExist"] is True
    assert row["Ripple"] == pytest.approx(0.6)
    assert row["VOL_max"] == pytest.approx(0.6)
    assert row["Ripple"] < 14.0


def test_diagnostic_only_ripple_keeps_raw_value_without_hard_metric():
    time = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float) * 1e-6
    signal = np.array([0.0, 0.0, 6.0, 14.0, 13.0, 6.0, 0.0, 0.1, 0.6, 0.2, 0.0])

    row = compute_stage_metrics(
        time,
        signal,
        RealEvalConfig(
            high_threshold=5.0,
            low_threshold=1.0,
            min_pulse_width=2.0e-6,
            edge_buffer_ratio=0.2,
            ripple_mode="diagnostic_only",
        ),
    )

    assert row["Ripple"] is None
    assert row["RippleRaw"] == pytest.approx(0.6)
    assert row["ripple_mode"] == "diagnostic_only"
