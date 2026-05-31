import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.strategy_benchmark import _relative_gain, _strategy_leaderboard


def test_strategy_benchmark_cli_compares_all_supported_strategies(tmp_path: Path):
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps([_row()]), encoding="utf-8")
    sweep_path = tmp_path / "sweep.yaml"
    sweep_path.write_text(
        """
parameters:
  m1_width:
    target: M1.W
    values: ["1u", "2u"]
  load_cap:
    target: CLOAD.C
    values: ["1pF", "2pF"]
""",
        encoding="utf-8",
    )
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(
        """
target:
  metric: Max_overlap_ratio
  threshold: 999
validation_matrix:
  - name: nominal_rerun
    max_runs: 1
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "benchmark"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "strategy-benchmark",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--validation-config",
            str(validation_path),
            "--seeds",
            "1,2",
            "--rounds",
            "1",
            "--max-runs-per-round",
            "1",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = pd.read_csv(output_root / "strategy_benchmark.csv")
    summary = json.loads((output_root / "strategy_benchmark_summary.json").read_text(encoding="utf-8"))
    report = (output_root / "strategy_benchmark_report.md").read_text(encoding="utf-8")

    assert set(rows["strategy"]) == {"random", "adaptive", "genetic", "bayesian", "surrogate", "hybrid"}
    assert set(rows["seed"]) == {1, 2}
    for column in [
        "rank_status",
        "target_status",
        "hard_constraint_passed",
        "not_evaluable_metric_count",
        "validation_not_evaluable_count",
        "worst_case_name",
        "worst_case_value",
        "first_pass_sim_count",
        "candidate_source",
        "source_candidate_trigger_metric",
        "source_candidate_rationale",
        "model_status",
        "changed_parameters",
    ]:
        assert column in rows.columns
    for metric in [
        "best_score_mean",
        "best_score_std",
        "target_pass_rate",
        "hard_constraint_pass_rate",
        "hard_fail_rate",
        "validation_pass_rate",
        "not_evaluable_rate",
        "avg_sim_count",
        "first_pass_sim_count_mean",
        "improvement_per_simulation",
        "mock_used_rate",
        "score_improvement_vs_random",
        "target_pass_rate_gain_vs_random",
        "simulation_efficiency_gain_vs_random",
    ]:
        assert metric in summary["strategies"]["random"]
    assert summary["data_source"] == "real_simulation_csv"
    assert summary["engineering_validity"] == "simulation_only"
    assert summary["fairness"]["same_seed_set"] is True
    assert summary["fairness"]["random_baseline_no_replay"] is True
    assert "scenario" in summary
    assert "strategy_groups" in summary
    assert summary["strategies"]["random"]["mock_used_rate"] == 1.0
    strategy_leaderboard = pd.read_csv(output_root / "strategy_leaderboard.csv")
    assert {"strategy", "hard_constraint_pass_rate", "score_improvement_vs_random"} <= set(strategy_leaderboard.columns)
    assert "random" in report
    assert "adaptive" in report
    assert "Strategy Leaderboard" in report


def test_strategy_benchmark_relative_gain_handles_missing_or_zero_baseline():
    assert _relative_gain(10.0, 0.0) is None
    assert _relative_gain(None, 10.0) is None
    assert _relative_gain(12.0, 10.0) == 0.2


def test_strategy_leaderboard_sorts_hard_pass_before_soft_score():
    summary = {
        "strategies": {
            "soft_high": {
                "hard_constraint_pass_rate": 0.0,
                "target_pass_rate": 1.0,
                "validation_pass_rate": 1.0,
                "best_score_mean": 100.0,
                "avg_sim_count": 1.0,
            },
            "hard_pass": {
                "hard_constraint_pass_rate": 1.0,
                "target_pass_rate": 0.0,
                "validation_pass_rate": 0.0,
                "best_score_mean": 10.0,
                "avg_sim_count": 10.0,
            },
        }
    }

    leaderboard = _strategy_leaderboard(summary)

    assert leaderboard.iloc[0]["strategy"] == "hard_pass"


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title strategy benchmark fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            "CLOAD vout 0 1pF",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "strategy_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {
            "ports": [
                {"name": "vout", "role": "output_v"},
                {"name": "vaux", "role": "output_v"},
            ]
        },
    }
