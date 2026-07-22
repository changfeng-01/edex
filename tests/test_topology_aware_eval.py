from pathlib import Path

import pandas as pd
import pytest

from goa_eval.analysis_metrics import extract_analysis_metrics
from goa_eval.scorer import score_real_evaluation
from goa_eval.topology_profiles import load_eval_profiles, resolve_topology_profile


def test_profile_loader_maps_known_topologies_and_defaults():
    profiles = load_eval_profiles(Path("config/eval_profiles.yaml"))

    ota = resolve_topology_profile("two_stage_opamp", profiles)
    comparator = resolve_topology_profile("comparator", profiles)
    unknown = resolve_topology_profile("unknown_filter", profiles)

    assert ota["name"] == "ota"
    assert comparator["name"] == "comparator"
    assert unknown["name"] == "default"


def test_extract_analysis_metrics_from_mock_op_ac_dc_tran_files(tmp_path):
    (tmp_path / "op_metrics.csv").write_text(
        "metric,value\nsupply_voltage_v,1.8\nsupply_current_a,0.001\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "frequency_hz": [1.0, 10.0, 100.0, 1000.0],
            "gain_db": [40.0, 39.0, 35.0, -1.0],
        }
    ).to_csv(tmp_path / "ac_metrics.csv", index=False)
    pd.DataFrame(
        {
            "input_v": [0.0, 0.9, 1.8],
            "output_v": [1.8, 0.95, 0.0],
        }
    ).to_csv(tmp_path / "dc_metrics.csv", index=False)
    time = [0, 1e-9, 2e-9, 3e-9, 4e-9, 5e-9]
    pd.DataFrame({"TIME": time, "v(out)": [0.0, 0.1, 1.8, 1.7, 0.2, 0.0]}).to_csv(tmp_path / "tran_metrics.csv", index=False)

    metrics = extract_analysis_metrics(tmp_path, topology_profile="ota")

    assert metrics["op_metrics"]["static_power_w"] == pytest.approx(1.8e-3)
    assert metrics["ac_metrics"]["dc_gain_db"] == pytest.approx(40.0)
    assert metrics["ac_metrics"]["bandwidth_3db_hz"] == pytest.approx(100.0)
    assert metrics["ac_metrics"]["unity_gain_hz"] == pytest.approx(1000.0)
    assert metrics["dc_metrics"]["switching_threshold_v"] == pytest.approx(0.9)
    assert metrics["tran_metrics"]["output_swing_v"] == pytest.approx(1.8)


def test_missing_analysis_files_are_not_evaluable(tmp_path):
    metrics = extract_analysis_metrics(tmp_path, topology_profile="ota")

    assert {"op_metrics", "ac_metrics", "dc_metrics", "tran_metrics"} <= set(metrics["not_evaluable"])


def test_extract_analysis_metrics_uses_waveform_as_tran_fallback(tmp_path):
    pd.DataFrame({"TIME": [0.0, 1e-9, 2e-9], "v(o1)": [0.0, 1.8, 0.0]}).to_csv(
        tmp_path / "waveform.csv",
        index=False,
    )

    metrics = extract_analysis_metrics(tmp_path, topology_profile="oscillator")

    assert "tran_metrics" not in metrics["not_evaluable"]
    assert metrics["tran_metrics"]["output_swing_v"] == pytest.approx(1.8)


def test_score_real_evaluation_adds_topology_profile_scores():
    profiles = load_eval_profiles(Path("config/eval_profiles.yaml"))
    summary = {
        "All_pulses_exist": True,
        "Seq_pass": True,
        "FalseTriggerCount": 0,
        "Max_overlap_ratio": 0.0,
        "Max_ripple": 0.02,
        "Max_voltage_loss": 0.01,
        "Delay_std": 1e-9,
        "Width_std": 1e-9,
        "Width_mean": 20e-9,
        "VOH_min": 1.7,
        "high_threshold": 0.9,
    }
    spec = {
        "max_overlap_ratio": 0.10,
        "max_ripple_v": 0.10,
        "max_voltage_loss_v": 0.20,
        "max_delay_std": 20e-9,
        "pulse_width_tolerance": 20e-9,
        "target_pulse_width": 20e-9,
        "min_voh_margin_v": 0.2,
        "weights": {
            "function_score": 0.35,
            "quality_score": 0.25,
            "stability_score": 0.15,
            "consistency_score": 0.15,
            "cost_score": 0.10,
        },
    }
    analysis = {
        "op_metrics": {"static_power_w": 1e-3},
        "ac_metrics": {"dc_gain_db": 45.0, "bandwidth_3db_hz": 2e6, "unity_gain_hz": 20e6},
        "dc_metrics": {"output_swing_v": 1.7},
        "tran_metrics": {"slew_rate_v_per_s": 1e8},
        "not_evaluable": {},
    }

    score = score_real_evaluation(
        summary,
        [],
        spec,
        topology="two_stage_opamp",
        analysis_metrics=analysis,
        profiles=profiles,
    )

    assert score["topology_profile"] == "ota"
    assert "dc_gain_db" in score["profile_metric_scores"]
    assert score["circuit_profile"] == "ota"
    assert score["objective_score"] == score["profile_score"]
    assert "profile_metric_score" in score["objective_breakdown"]
    assert "not_evaluable_required_metrics" in score
    assert "dc_gain_db" in score["analysis_metric_penalties"]
    assert score["not_evaluable_metrics"] == {}
    assert score["overall_score"] > 0
