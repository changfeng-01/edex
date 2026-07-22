from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goa_eval.metrics import RealEvalConfig, detect_main_pulse_window, evaluate_waveform_metrics
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.waveform_io import normalize_column_name


def _config() -> RealEvalConfig:
    return RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2.0e-6)


def test_column_normalization():
    assert normalize_column_name(" v(o1) ") == "o1"
    assert normalize_column_name("V(XS4.PU)") == "xs4.pu"
    assert normalize_column_name("XVAL") == "time"


def test_detect_main_pulse():
    time = np.array([0, 1, 2, 3, 4, 5], dtype=float) * 1e-6
    signal = np.array([0, 0, 6, 7, 6, 0], dtype=float)

    window = detect_main_pulse_window(time, signal, _config())

    assert window == pytest.approx((2e-6, 5e-6))


def test_compute_pulse_width():
    time = np.array([0, 1, 2, 3, 4, 5], dtype=float) * 1e-6
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": [0, 0, 6, 7, 6, 0],
            "o2": [0, 0, 0, 6, 7, 0],
            "o3": [0, 0, 0, 0, 6, 7],
        }
    )

    result = evaluate_waveform_metrics(frame, _config(), output_nodes=["o1", "o2", "o3"])

    assert result.stage_rows[0]["pulse_width"] == pytest.approx(3e-6)


def test_real_evaluation_marks_partial_output_coverage(tmp_path: Path) -> None:
    waveform = tmp_path / "waveform.csv"
    waveform.write_text("XVAL,v(o1),v(o2)\n0,0,0\n0.000001,6,0\n0.000002,0,6\n", encoding="utf-8")

    summary = run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "out",
        stage_count=3,
        spec_path=None,
    )

    assert summary["expected_stage_count"] == 3
    assert summary["observed_stage_count"] == 2
    assert summary["output_coverage_ratio"] == pytest.approx(2 / 3)
    assert summary["coverage_status"] == "partial"
    assert summary["missing_output_nodes"] == ["o3"]
    assert summary["full_cascade_claim_allowed"] is False


def test_real_evaluation_strict_output_coverage_fails_closed(tmp_path: Path) -> None:
    waveform = tmp_path / "waveform.csv"
    waveform.write_text("XVAL,v(o1),v(o2)\n0,0,0\n0.000001,6,0\n0.000002,0,6\n", encoding="utf-8")

    with pytest.raises(ValueError, match="output coverage"):
        run_real_waveform_evaluation(
            waveform_path=waveform,
            internal_waveform_path=None,
            output_dir=tmp_path / "out",
            stage_count=3,
            strict_output_coverage=True,
            spec_path=None,
        )


def test_sequence_pass():
    time = np.arange(0, 10, dtype=float) * 1e-6
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.where((time >= 1e-6) & (time < 4e-6), 6.0, 0.0),
            "o2": np.where((time >= 2e-6) & (time < 5e-6), 6.0, 0.0),
            "o3": np.where((time >= 3e-6) & (time < 6e-6), 6.0, 0.0),
        }
    )

    result = evaluate_waveform_metrics(frame, _config(), output_nodes=["o1", "o2", "o3"])

    assert result.summary["Seq_pass"] is True


def test_short_window_starting_high_is_detected_as_single_pulse():
    time = np.arange(0.0, 4.1e-9, 0.1e-9)
    signal = np.where(time < 0.8e-9, 1.8, 0.0)
    frame = pd.DataFrame({"time": time, "o1": signal})
    config = RealEvalConfig(
        high_threshold=0.9,
        low_threshold=0.3,
        target_pulse_width=0.8e-9,
        pulse_width_tolerance=0.4e-9,
        min_pulse_width=0.05e-9,
        false_trigger_min_duration=0.05e-9,
    )

    result = evaluate_waveform_metrics(frame, config, output_nodes=["o1"])

    assert result.stage_rows[0]["PulseExist"] is True
    assert result.stage_rows[0]["rise_edge_time"] == pytest.approx(0.0)
    assert result.summary["All_pulses_exist"] is True
    assert result.summary["Seq_pass"] is True
    assert result.summary["Width_mean"] == pytest.approx(0.8e-9)


def test_false_trigger_detection():
    time = np.arange(0, 20, dtype=float) * 1e-6
    o1 = np.where((time >= 2e-6) & (time < 6e-6), 6.0, 0.0)
    o1[(time >= 12e-6) & (time < 13e-6)] = 6.0
    frame = pd.DataFrame({"time": time, "o1": o1})

    result = evaluate_waveform_metrics(frame, _config(), output_nodes=["o1"])

    assert result.stage_rows[0]["false_trigger"] is True


def test_summary_contains_validity_labels(tmp_path: Path):
    waveform = tmp_path / "yuanshi_csv"
    time = np.arange(0, 10, dtype=float) * 1e-6
    rows = pd.DataFrame(
        {
            "XVAL": time,
            "v(o1)": np.where((time >= 1e-6) & (time < 4e-6), 6.0, 0.0),
            "v(o2)": np.where((time >= 2e-6) & (time < 5e-6), 6.0, 0.0),
            "v(o3)": np.where((time >= 3e-6) & (time < 6e-6), 6.0, 0.0),
        }
    )
    rows.to_csv(waveform, index=False)

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "outputs",
        high_threshold=5.0,
        low_threshold=1.0,
        output_nodes=["o1", "o2", "o3"],
    )

    summary = pd.read_json(tmp_path / "outputs" / "real_summary.json", typ="series")
    assert summary["data_source"] == "real_simulation_csv"
    assert summary["engineering_validity"] == "simulation_only"


def test_single_output_real_waveform_evaluation_writes_stacked_plot(tmp_path: Path):
    waveform = tmp_path / "single_output.csv"
    time = np.arange(0, 10, dtype=float) * 1e-6
    rows = pd.DataFrame(
        {
            "XVAL": time,
            "v(o1)": np.where((time >= 1e-6) & (time < 4e-6), 6.0, 0.0),
        }
    )
    rows.to_csv(waveform, index=False)

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "outputs",
        high_threshold=5.0,
        low_threshold=1.0,
        output_nodes=["o1"],
    )

    assert (tmp_path / "outputs" / "figures" / "o1_o8_stacked.png").exists()


def test_real_report_lists_optimized_figures_and_validity_labels(tmp_path: Path):
    waveform = tmp_path / "yuanshi_csv"
    time = np.arange(0, 20, dtype=float) * 1e-6
    rows = pd.DataFrame({"XVAL": time})
    for index in range(1, 9):
        start = index * 1e-6
        rows[f"v(o{index})"] = np.where((time >= start) & (time < start + 4e-6), 6.0 + index * 0.1, 0.0)
    rows.to_csv(waveform, index=False)

    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=tmp_path / "outputs",
        high_threshold=5.0,
        low_threshold=1.0,
    )

    report = (tmp_path / "outputs" / "real_waveform_report.md").read_text(encoding="utf-8")
    assert "data_source = real_simulation_csv" in report
    assert "engineering_validity = simulation_only" in report
    assert "Delay_i 柱状图" in report
    assert "VOL_max / Ripple 柱状图" in report
    assert "??" not in report
    for name in [
        "o1_o8_overview.png",
        "o1_o8_stacked.png",
        "voh_width_bar.png",
        "delay_bar.png",
        "vol_ripple_bar.png",
    ]:
        assert (tmp_path / "outputs" / "figures" / name).exists()
