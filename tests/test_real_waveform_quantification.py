from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest

from goa_eval.metrics import RealEvalConfig, evaluate_waveform_metrics
from goa_eval.real_waveform_eval import run_real_waveform_evaluation
from goa_eval.scorer import score_real_evaluation


def _frame_with_repeated_pulses() -> pd.DataFrame:
    time = np.arange(0.0, 40e-6, 0.5e-6)
    frame = pd.DataFrame({"time": time})
    for index in range(1, 4):
        signal = np.zeros_like(time)
        for base in [2e-6, 22e-6]:
            start = base + (index - 1) * 2e-6
            signal[(time >= start) & (time <= start + 4e-6)] = 6.0
        frame[f"o{index}"] = signal
    return frame


def test_repeated_legal_windows_are_counted_without_false_trigger():
    result = evaluate_waveform_metrics(
        _frame_with_repeated_pulses(),
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6),
        output_nodes=["o1", "o2", "o3"],
    )

    first = result.stage_rows[0]
    assert first["LegalPulseCount"] == 2
    assert len(first["legal_windows"]) == 2
    assert first["FalseTrigger"] is False
    assert first["FalseTriggerCount"] == 0
    assert result.summary["FalseTriggerCount"] == 0
    assert result.summary["All_pulses_exist"] is True


def test_short_high_outside_legal_windows_is_false_trigger_not_normal_cycle():
    frame = _frame_with_repeated_pulses()
    time = frame["time"].to_numpy()
    frame.loc[(time >= 14e-6) & (time <= 15e-6), "o1"] = 6.0

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6, false_trigger_min_duration=0.5e-6),
        output_nodes=["o1", "o2", "o3"],
    )

    first = result.stage_rows[0]
    assert first["LegalPulseCount"] == 2
    assert first["FalseTrigger"] is True
    assert first["FalseTriggerCount"] == 1
    assert result.summary["FalseTriggerCount"] == 1


def test_overlap_ratio_uses_min_adjacent_primary_width():
    time = np.arange(0.0, 20.5e-6, 0.5e-6)
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.where((time >= 2e-6) & (time < 8e-6), 6.0, 0.0),
            "o2": np.where((time >= 6e-6) & (time < 10e-6), 6.0, 0.0),
        }
    )

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6),
        output_nodes=["o1", "o2"],
    )

    assert result.stage_rows[0]["Overlap"] == pytest.approx(2e-6)
    expected_ratio = result.stage_rows[0]["Overlap"] / min(result.stage_rows[0]["PulseWidth"], result.stage_rows[1]["PulseWidth"])
    assert result.stage_rows[0]["OverlapRatio"] == pytest.approx(expected_ratio)
    assert result.summary["Max_overlap_ratio"] == pytest.approx(expected_ratio)


def test_overlap_ratio_for_repeated_windows_is_normalized_by_total_active_width():
    index = np.arange(0, 41)
    time = index * 0.5e-6
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.where(((index >= 4) & (index < 16)) | ((index >= 24) & (index < 36)), 6.0, 0.0),
            "o2": np.where(((index >= 12) & (index < 20)) | ((index >= 32) & (index < 40)), 6.0, 0.0),
        }
    )

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6),
        output_nodes=["o1", "o2"],
    )

    assert result.stage_rows[0]["Overlap"] == pytest.approx(4e-6)
    assert result.stage_rows[0]["OverlapRatio"] == pytest.approx(4e-6 / 8e-6)
    assert result.summary["Max_overlap_ratio"] == pytest.approx(0.5)


def test_overlap_ignores_common_startup_window_at_left_boundary():
    index = np.arange(0, 41)
    time = index * 0.5e-6
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.where(((index >= 0) & (index < 4)) | ((index >= 20) & (index < 24)), 6.0, 0.0),
            "o2": np.where(((index >= 0) & (index < 4)) | ((index >= 26) & (index < 30)), 6.0, 0.0),
        }
    )

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=1e-6),
        output_nodes=["o1", "o2"],
    )

    assert result.stage_rows[0]["Overlap"] == pytest.approx(0.0)
    assert result.stage_rows[0]["OverlapRatio"] == pytest.approx(0.0)


def test_voltage_loss_is_reported_per_stage_and_summary():
    time = np.arange(0.0, 12e-6, 1.0e-6)
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.array([0.0, 0.0, 6.0, 7.0, 6.4, 6.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
        }
    )

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6),
        output_nodes=["o1"],
    )

    row = result.stage_rows[0]
    assert row["VHoldEnd"] == pytest.approx(6.2)
    assert row["VoltageLoss"] == pytest.approx(0.8)
    assert row["VoltageLossRatio"] == pytest.approx(0.8 / 7.0)
    assert result.summary["Max_voltage_loss"] == pytest.approx(0.8)
    assert result.summary["Max_voltage_loss_ratio"] == pytest.approx(0.8 / 7.0)


def test_diagnostic_only_ripple_is_not_a_summary_hard_metric():
    time = np.arange(0.0, 12e-6, 1.0e-6)
    frame = pd.DataFrame(
        {
            "time": time,
            "o1": np.array([0.0, 0.0, 6.0, 14.0, 13.0, 6.0, 0.0, 0.1, 0.6, 0.2, 0.0, 0.0]),
        }
    )

    result = evaluate_waveform_metrics(
        frame,
        RealEvalConfig(
            high_threshold=5.0,
            low_threshold=1.0,
            min_pulse_width=2e-6,
            ripple_mode="diagnostic_only",
        ),
        output_nodes=["o1"],
    )

    assert result.stage_rows[0]["Ripple"] is None
    assert result.stage_rows[0]["RippleRaw"] == pytest.approx(0.6)
    assert result.summary["Max_ripple"] is None
    assert result.summary["Max_ripple_raw"] == pytest.approx(0.6)
    assert result.summary["ripple_mode"] == "diagnostic_only"


def test_low_frequency_stability_is_not_evaluable_when_waveform_is_shorter_than_frame_hold_time():
    result = evaluate_waveform_metrics(
        _frame_with_repeated_pulses(),
        RealEvalConfig(high_threshold=5.0, low_threshold=1.0, min_pulse_width=2e-6, target_refresh_hz=10.0),
        output_nodes=["o1", "o2", "o3"],
    )

    assert result.summary["target_refresh_hz"] == 10.0
    assert result.summary["frame_hold_time"] == pytest.approx(0.1)
    assert result.summary["LowFreqStable"] == "not_evaluable_with_current_waveform"
    assert "短于目标刷新周期" in result.summary["low_frequency_evaluation_note"]


def test_scorer_outputs_scores_in_0_to_100_and_failure_reasons():
    summary = {
        "Seq_pass": True,
        "All_pulses_exist": True,
        "FalseTriggerCount": 0,
        "Max_overlap_ratio": 0.2,
        "Max_ripple": 0.1,
        "Delay_std": 0.1e-6,
        "VOH_min": 6.0,
        "high_threshold": 5.0,
        "Width_mean": 10e-6,
        "Width_std": 0.1e-6,
        "VOL_max_all": 0.5,
    }
    spec = {
        "max_overlap_ratio": 0.1,
        "max_ripple_v": 0.5,
        "max_delay_std": 0.5e-6,
        "min_voh_margin_v": 1.0,
        "target_pulse_width": 10e-6,
        "pulse_width_tolerance": 1e-6,
        "weights": {
            "function_score": 0.35,
            "quality_score": 0.25,
            "stability_score": 0.15,
            "consistency_score": 0.15,
            "cost_score": 0.10,
        },
    }

    scores = score_real_evaluation(summary, [], spec)

    for key in ["function_score", "quality_score", "stability_score", "consistency_score", "cost_score", "overall_score"]:
        assert 0.0 <= scores[key] <= 100.0
    assert scores["hard_constraint_passed"] is False
    assert "Max_overlap_ratio" in " ".join(scores["hard_constraint_failures"])


def test_real_evaluation_writes_score_diagnosis_dataset_and_report(tmp_path: Path):
    waveform = tmp_path / "waveform.csv"
    time = np.arange(0.0, 40e-6, 0.5e-6)
    rows = pd.DataFrame({"XVAL": time})
    for index in range(1, 9):
        start = 2e-6 + (index - 1) * 1.5e-6
        rows[f"v(o{index})"] = np.where((time >= start) & (time <= start + 4e-6), 6.0 + index * 0.1, 0.0)
    rows.to_csv(waveform, index=False)

    out = tmp_path / "outputs"
    run_real_waveform_evaluation(
        waveform_path=waveform,
        internal_waveform_path=None,
        output_dir=out,
        high_threshold=5.0,
        low_threshold=1.0,
    )

    for name in [
        "real_metrics.csv",
        "real_summary.json",
        "score_summary.json",
        "optimization_dataset.csv",
        "diagnosis_report.md",
        "real_waveform_report.md",
    ]:
        assert (out / name).exists()

    dataset = pd.read_csv(out / "optimization_dataset.csv")
    required = {
        "run_id",
        "run_timestamp",
        "design_name",
        "parameter_set_id",
        "W_PU",
        "W_PD",
        "C_boot",
        "C_load",
        "V_CLKH",
        "Max_voltage_loss",
        "Max_voltage_loss_ratio",
        "LowFreqStable",
        "overall_score",
        "data_source",
        "engineering_validity",
    }
    assert required.issubset(set(dataset.columns))
    assert dataset.loc[0, "data_source"] == "real_simulation_csv"
    assert dataset.loc[0, "engineering_validity"] == "simulation_only"

    metrics = pd.read_csv(out / "real_metrics.csv")
    assert {"VHoldEnd", "VoltageLoss", "VoltageLossRatio"}.issubset(set(metrics.columns))

    summary = json.loads((out / "real_summary.json").read_text(encoding="utf-8"))
    assert "Max_voltage_loss" in summary
    assert "Max_voltage_loss_ratio" in summary
    assert summary["LowFreqStable"] == "not_evaluable_with_current_waveform"

    manifest = json.loads((out / "run_manifest_real.json").read_text(encoding="utf-8"))
    assert manifest["thresholds"]["max_voltage_loss_v"] == 0.5
    assert manifest["thresholds"]["target_refresh_hz"] == 60.0

    report = (out / "real_waveform_report.md").read_text(encoding="utf-8")
    assert "real_simulation_csv" in report
    assert "simulation_only" in report
    assert "不是实物测试结果" in report
    assert "Max_voltage_loss" in report
    assert "LowFreqStable" in report
