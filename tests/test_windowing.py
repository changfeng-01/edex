import numpy as np
import pytest

from goa_eval.evaluation.feature_extractor import extract_waveform_features
from goa_eval.models.waveform import WaveformBundle


def test_truth_window_plateau_false_trigger_and_edge_guard():
    time = np.arange(0.0, 40e-6, 20e-9)
    signal = np.full_like(time, -5.0)
    signal[(time >= 10e-6) & (time <= 20e-6)] = 15.0
    signal[(time >= 9.9e-6) & (time < 10e-6)] = 15.0
    signal[(time >= 30e-6) & (time < 30.4e-6)] = 15.0

    waveform = WaveformBundle(
        version_name="v8",
        time=time,
        signals={"o1": signal},
        data_source="mock",
        engineering_validity="workflow_test_only",
        truth_windows={"o1": (10e-6, 20e-6)},
    )

    features = extract_waveform_features(
        waveform,
        {
            "voltage": {"VGH": 15.0, "VGL": -5.0, "VH_ratio": 0.70, "VL_ratio": 0.20, "edge_low_ratio": 0.10, "edge_high_ratio": 0.90},
            "time": {"expected_line_period": 20e-6, "edge_guard_ratio_of_line": 0.05, "min_false_trigger_duration": 0.2e-6, "min_valid_pulse_width": 2e-6},
            "windows": {"plateau_center_ratio": 0.60},
        },
    )

    assert features["nodes"]["o1"]["target_window"] == (10e-6, 20e-6)
    assert features["nodes"]["o1"]["VOH"] == 15.0
    assert features["nodes"]["o1"]["FalseTrigger"] is True
    assert features["nodes"]["o1"]["Twidth"] > 9e-6


def test_repeated_real_waveform_pulses_are_legitimate_windows_not_false_triggers():
    time = np.arange(0.0, 240e-6, 20e-9)
    signal = np.full_like(time, -5.0)
    for start in [10e-6, 110e-6, 210e-6]:
        signal[(time >= start) & (time <= start + 10e-6)] = 15.0

    waveform = WaveformBundle(
        version_name="v8",
        time=time,
        signals={"o1": signal},
        data_source="simulation",
        engineering_validity="simulation_result",
    )

    features = extract_waveform_features(
        waveform,
        {
            "voltage": {"VGH": 15.0, "VGL": -5.0, "VH_ratio": 0.70, "VL_ratio": 0.20, "edge_low_ratio": 0.10, "edge_high_ratio": 0.90},
            "time": {"expected_line_period": 20e-6, "edge_guard_ratio_of_line": 0.05, "min_false_trigger_duration": 0.2e-6, "min_valid_pulse_width": 2e-6},
            "windows": {"plateau_center_ratio": 0.60},
        },
    )

    node = features["nodes"]["o1"]
    assert node["FalseTrigger"] is False
    assert node["legitimate_pulse_count"] == 3
    assert node["first_scan_window"] == node["target_window"]
    assert len(node["repeated_scan_windows"]) == 2
    assert node["true_false_trigger_count"] == 0


def test_overlap_duration_uses_interval_endpoints_for_nonuniform_sampling():
    time = np.array([0.0, 1e-6, 2e-6, 3e-6, 10e-6, 10.2e-6, 10.4e-6, 12e-6])
    o1 = np.full_like(time, -5.0)
    o2 = np.full_like(time, -5.0)
    high = (time >= 1e-6) & (time < 3e-6) | ((time >= 10e-6) & (time < 12e-6))
    o1[high] = 15.0
    o2[high] = 15.0

    waveform = WaveformBundle(
        version_name="v8",
        time=time,
        signals={"o1": o1, "o2": o2},
        data_source="simulation",
        engineering_validity="simulation_result",
    )

    features = extract_waveform_features(
        waveform,
        {
            "voltage": {"VGH": 15.0, "VGL": -5.0, "VH_ratio": 0.70, "VL_ratio": 0.20, "edge_low_ratio": 0.10, "edge_high_ratio": 0.90},
            "time": {"expected_line_period": 20e-6, "edge_guard_ratio_of_line": 0.0, "min_false_trigger_duration": 0.2e-6, "min_valid_pulse_width": 0.5e-6},
            "windows": {"plateau_center_ratio": 0.60},
        },
    )

    assert features["overlaps"]["o1_o2"] == pytest.approx(4e-6)
