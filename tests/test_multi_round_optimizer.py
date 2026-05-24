import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from goa_eval.multi_round_optimizer import build_adaptive_sweep_config, should_stop_optimization


def _base_config() -> dict:
    return {
        "parameters": {
            "m1_width": {"target": "M1.W", "values": ["1u", "2u", "3u"]},
            "load_cap": {"target": "CLOAD.C", "values": ["0.5pF", "1pF", "2pF"]},
        }
    }


def test_build_adaptive_sweep_config_prefers_high_scores_candidates_and_skips_seen(tmp_path: Path):
    history = pd.DataFrame(
        [
            {"status": "evaluated", "overall_score": 60.0, "m1_width": "1u", "load_cap": "0.5pF", "run_dir": "run_a"},
            {"status": "evaluated", "overall_score": 80.0, "m1_width": "2u", "load_cap": "1pF", "run_dir": "run_b"},
            {"status": "failed", "overall_score": None, "m1_width": "3u", "load_cap": "2pF", "run_dir": "run_c"},
        ]
    )
    best_run = tmp_path / "run_b"
    best_run.mkdir()
    pd.DataFrame(
        [
            {
                "parameter": "m1_width",
                "candidate_value": "3u",
                "search_score": 95,
                "trigger_metric": "dc_gain_db",
            }
        ]
    ).to_csv(best_run / "next_candidates.csv", index=False)

    result = build_adaptive_sweep_config(
        base_config=_base_config(),
        history=history,
        best_run_dir=best_run,
        max_runs=4,
        seed=11,
        exploration_ratio=0.25,
    )

    points = result["points"]
    assert {"m1_width": "3u", "load_cap": "1pF"} in points
    assert {"m1_width": "2u", "load_cap": "1pF"} not in points
    assert len(points) <= 4
    assert result["stop_reason"] == ""
    assert result["config"]["parameters"]["m1_width"]["target"] == "M1.W"


def test_should_stop_optimization_uses_patience_and_min_improvement():
    rounds = [
        {"round_index": 1, "best_score": 80.0},
        {"round_index": 2, "best_score": 80.1},
    ]

    assert should_stop_optimization(rounds, patience=1, min_improvement=0.5) == "no improvement for 1 round(s)"
    assert should_stop_optimization(rounds, patience=1, min_improvement=0.05) == ""


def test_optimize_rounds_cli_mock_writes_multi_round_outputs(tmp_path: Path):
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
    output_root = tmp_path / "multi_round"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "optimize-rounds",
            "--mock-dataset-json",
            str(rows_path),
            "--mock-ngspice",
            "--sweep",
            str(sweep_path),
            "--rounds",
            "2",
            "--max-runs-per-round",
            "2",
            "--output-root",
            str(output_root),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_root / "round_001" / "sky130_sweep_runs.csv").exists()
    assert (output_root / "round_002" / "sky130_sweep_runs.csv").exists()
    assert (output_root / "optimization_history.json").exists()
    assert (output_root / "optimization_leaderboard.csv").exists()
    assert (output_root / "round_summary.csv").exists()
    assert (output_root / "final_param_space.yaml").exists()
    assert (output_root / "best_next_candidates.csv").exists()

    summary = pd.read_csv(output_root / "round_summary.csv")
    leaderboard = pd.read_csv(output_root / "optimization_leaderboard.csv")
    final_space = yaml.safe_load((output_root / "final_param_space.yaml").read_text(encoding="utf-8"))
    assert len(summary) == 2
    assert {"round_index", "best_score", "stop_reason"} <= set(summary.columns)
    assert {"round_index", "overall_score", "run_dir"} <= set(leaderboard.columns)
    assert "parameters" in final_space


def _row() -> dict:
    testbench = "\n".join(
        [
            ".title multi-round fixture",
            "VDD vdd 0 DC 1.8",
            "M1 vout vin vdd vdd PMOS W=1u L=0.15u",
            "CLOAD vout 0 1pF",
            "V1 vin 0 pulse(0 1.8 1n 1n 1n 5n 20n)",
            ".tran 1n 40n",
            ".end",
        ]
    )
    return {
        "circuit_id": "multi_round_amp",
        "topology": "two_stage_opamp",
        "source_dataset": "unit_fixture",
        "pdk": "sky130",
        "spice_netlist": testbench,
        "testbench_spice": testbench,
        "netlist_json": {"ports": [{"name": "vout", "role": "output_v"}]},
    }
