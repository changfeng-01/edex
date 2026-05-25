import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from goa_eval.analysis_metrics import extract_analysis_metrics
from goa_eval.circuit_profiles import load_circuit_profiles
from goa_eval.scorer import score_real_evaluation


def _write_csv_import_input(path: Path, *, gain: float = 45.0) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "waveform.csv").write_text(Path("examples/sample_waveform.csv").read_text(encoding="utf-8"), encoding="utf-8")
    (path / "op_metrics.csv").write_text("metric,value\nsupply_voltage_v,1.8\nsupply_current_a,0.001\n", encoding="utf-8")
    pd.DataFrame({"frequency_hz": [1.0, 10.0, 100.0], "gain_db": [gain, gain - 1.0, gain - 5.0]}).to_csv(
        path / "ac_metrics.csv",
        index=False,
    )
    pd.DataFrame({"TIME": [0.0, 1e-9, 2e-9], "v(out)": [0.0, 1.8, 0.0]}).to_csv(
        path / "tran_metrics.csv",
        index=False,
    )
    pd.DataFrame({"input_v": [0.0, 0.9, 1.8], "output_v": [1.8, 0.9, 0.0]}).to_csv(
        path / "dc_metrics.csv",
        index=False,
    )
    (path / "simulation_metadata.json").write_text(
        json.dumps({"simulator": "external_csv", "corner": "tt", "temperature_c": 25}),
        encoding="utf-8",
    )


def test_analysis_metrics_include_provenance_and_units(tmp_path):
    _write_csv_import_input(tmp_path)

    metrics = extract_analysis_metrics(tmp_path, topology_profile="ota_general")

    provenance = metrics["metric_provenance"]
    assert provenance["ac_metrics.dc_gain_db"]["unit"] == "dB"
    assert provenance["ac_metrics.dc_gain_db"]["source_file"] == "ac_metrics.csv"
    assert provenance["ac_metrics.dc_gain_db"]["source_analysis"] == "ac"
    assert provenance["op_metrics.static_power_w"]["unit"] == "W"
    assert provenance["tran_metrics.output_swing_v"]["source_column"] == "v(out)"
    assert metrics["not_evaluable"] == {}


def test_profile_objective_uses_weighted_scores_and_hard_gate():
    profiles = load_circuit_profiles(Path("config/circuit_profiles.yaml"))
    spec = {
        "max_overlap_ratio": 0.10,
        "max_ripple_v": 0.10,
        "max_voltage_loss_v": 0.20,
        "max_delay_std": 20e-9,
        "pulse_width_tolerance": 20e-9,
        "target_pulse_width": 20e-9,
        "min_voh_margin_v": 0.2,
        "weights": {"function_score": 1.0},
    }
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
    analysis = {
        "op_metrics": {"static_power_w": 0.010},
        "ac_metrics": {"dc_gain_db": 30.0, "unity_gain_hz": 20e6, "phase_margin_deg": 60.0},
        "tran_metrics": {"slew_rate_v_per_s": 1e8},
        "not_evaluable": {},
    }

    score = score_real_evaluation(summary, [], spec, topology="ota_general", analysis_metrics=analysis, profiles=profiles)

    assert score["objective_breakdown"]["objective_method"] == "weighted_sum"
    assert score["objective_breakdown"]["hard_constraint_gate"] == "passed"
    assert "metric_objective_scores" in score["objective_breakdown"]
    assert score["objective_score"] != pytest.approx(score["profile_score"])
    assert "metric_provenance" in score

    failed = score_real_evaluation(
        {**summary, "Seq_pass": False},
        [],
        spec,
        topology="ota_general",
        analysis_metrics=analysis,
        profiles=profiles,
    )
    assert failed["hard_constraint_passed"] is False
    assert failed["objective_score"] == 0.0
    assert failed["objective_breakdown"]["hard_constraint_gate"] == "failed"


def test_csv_import_cli_writes_unified_artifacts(tmp_path):
    source = tmp_path / "csv_source"
    output = tmp_path / "run"
    _write_csv_import_input(source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "csv-import",
            "--input-dir",
            str(source),
            "--output-dir",
            str(output),
            "--circuit-profile",
            "ota_general",
            "--profile-file",
            "config/circuit_profiles.yaml",
            "--params",
            "config/parameter_semantics.yaml",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    status = json.loads((output / "adapter_status.json").read_text(encoding="utf-8"))
    metadata = json.loads((output / "simulation_metadata.json").read_text(encoding="utf-8"))
    analysis = json.loads((output / "analysis_metrics.json").read_text(encoding="utf-8"))
    score = json.loads((output / "score_summary.json").read_text(encoding="utf-8"))
    dataset = pd.read_csv(output / "optimization_dataset.csv")

    assert status["adapter"] == "csv-import"
    assert status["status"] == "imported"
    assert metadata["engineering_validity"] == "simulation_only"
    assert "metric_provenance" in analysis
    assert "metric_provenance" in score
    assert "metric_provenance" in dataset.columns
    assert (output / "next_candidates.csv").exists()


def test_csv_import_reports_missing_waveform(tmp_path):
    from goa_eval.csv_import_adapter import run_csv_import

    source = tmp_path / "missing"
    source.mkdir()
    with pytest.raises(FileNotFoundError, match="waveform.csv"):
        run_csv_import(input_dir=source, output_dir=tmp_path / "out")


def test_simulate_run_csv_import_cli(tmp_path):
    source = tmp_path / "csv_source"
    output = tmp_path / "sim_run"
    _write_csv_import_input(source)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "simulate-run",
            "--adapter",
            "csv-import",
            "--input-dir",
            str(source),
            "--output-dir",
            str(output),
            "--circuit-profile",
            "ota_general",
            "--profile-file",
            "config/circuit_profiles.yaml",
            "--params",
            "config/parameter_semantics.yaml",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "adapter_status.json").exists()
    assert (output / "score_summary.json").exists()
    assert (output / "recommendations.md").exists()
    assert (output / "next_candidates.csv").exists()


def test_simulate_sweep_csv_import_cli(tmp_path):
    input_root = tmp_path / "inputs"
    _write_csv_import_input(input_root / "run_a", gain=35.0)
    _write_csv_import_input(input_root / "run_b", gain=65.0)
    output_root = tmp_path / "sweep"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "simulate-sweep",
            "--adapter",
            "csv-import",
            "--input-root",
            str(input_root),
            "--output-root",
            str(output_root),
            "--circuit-profile",
            "ota_general",
            "--profile-file",
            "config/circuit_profiles.yaml",
            "--params",
            "config/parameter_semantics.yaml",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    runs = pd.read_csv(output_root / "simulate_sweep_runs.csv")
    leaderboard = pd.read_csv(output_root / "simulate_sweep_leaderboard.csv")
    assert len(runs) == 2
    assert {"status", "overall_score", "objective_score", "run_dir", "adapter"} <= set(runs.columns)
    assert list(leaderboard["status"]) == ["evaluated", "evaluated"]
