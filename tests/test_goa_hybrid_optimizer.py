import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from goa_eval.goa_hybrid_optimizer import generate_repair_candidates, run_hybrid_goa_optimizer
from goa_eval.pareto import pareto_rank


def test_pareto_rank_gates_hard_constraints_before_soft_score():
    frame = pd.DataFrame(
        [
            {"candidate_id": "soft_high", "hard_constraint_passed": False, "overall_score": 99.0, "Max_ripple": 0.1},
            {"candidate_id": "hard_pass", "hard_constraint_passed": True, "overall_score": 50.0, "Max_ripple": 0.2},
            {"candidate_id": "front_peer", "hard_constraint_passed": True, "overall_score": 45.0, "Max_ripple": 0.05},
        ]
    )

    ranked = pareto_rank(
        frame,
        [
            {"name": "hard_constraint_passed", "direction": "max"},
            {"name": "overall_score", "direction": "max"},
            {"name": "Max_ripple", "direction": "min"},
        ],
    )

    row_by_id = ranked.set_index("candidate_id")
    assert row_by_id.loc["hard_pass", "pareto_rank"] < row_by_id.loc["soft_high", "pareto_rank"]
    assert row_by_id.loc["front_peer", "pareto_is_front"] is True


def test_repair_candidates_follow_goa_failure_modes():
    history = pd.DataFrame(
        [
            {
                "candidate_id": "bad_overlap",
                "Max_overlap_ratio": 0.7,
                "Max_ripple": 0.04,
                "Max_voltage_loss": 0.1,
                "Delay_std": 0.01,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"clk_delay": 1.0, "load_cap": 1.0, "drive_width": 1.0}),
            },
            {
                "candidate_id": "bad_ripple",
                "Max_overlap_ratio": 0.1,
                "Max_ripple": 0.8,
                "Max_voltage_loss": 0.1,
                "Delay_std": 0.01,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"clk_delay": 1.0, "load_cap": 1.0, "drive_width": 1.0}),
            },
            {
                "candidate_id": "not_eval",
                "Max_overlap_ratio": 0.1,
                "Max_ripple": 0.1,
                "Max_voltage_loss": 0.1,
                "Delay_std": 0.01,
                "rank_status": "not_evaluable",
                "not_evaluable_metric_count": 4,
                "parameters_json": json.dumps({"clk_delay": 1.0, "load_cap": 1.0, "drive_width": 1.0}),
            },
        ]
    )
    param_space = {
        "clk_delay": {"values": [0.8, 1.0, 1.2]},
        "load_cap": {"values": [0.8, 1.0, 1.2]},
        "drive_width": {"values": [0.8, 1.0, 1.2]},
    }

    candidates = generate_repair_candidates(history, param_space, max_candidates=6, seed=3)
    operators = {candidate["repair_operator"] for candidate in candidates}

    assert "overlap_timing_repair" in operators
    assert "ripple_stability_repair" in operators
    assert "recover_evaluability_conservative_repair" in operators
    assert all(candidate["candidate_source"] == "repair" for candidate in candidates)
    assert all(candidate["repair_rationale"] for candidate in candidates)


def test_hybrid_optimizer_falls_back_and_writes_required_outputs(tmp_path: Path):
    leaderboard = tmp_path / "optimization_leaderboard.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "seed_1",
                "overall_score": 61.0,
                "Max_overlap_ratio": 0.5,
                "Max_ripple": 0.2,
                "Max_voltage_loss": 0.1,
                "Delay_std": 0.04,
                "hard_constraint_passed": False,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"clk_delay": 1.0, "load_cap": 1.0, "drive_width": 1.0}),
            }
        ]
    ).to_csv(leaderboard, index=False, encoding="utf-8-sig")
    param_space = tmp_path / "params.yaml"
    param_space.write_text(
        """
parameters:
  clk_delay:
    values: [0.8, 1.0, 1.2]
  load_cap:
    values: [0.8, 1.0, 1.2]
  drive_width:
    values: [0.8, 1.0, 1.2]
""",
        encoding="utf-8",
    )

    summary = run_hybrid_goa_optimizer(
        history_path=None,
        leaderboard_path=leaderboard,
        param_space_path=param_space,
        output_root=tmp_path / "hybrid",
        max_candidates=9,
        seed=11,
    )

    output_root = tmp_path / "hybrid"
    candidates = pd.read_csv(output_root / "hybrid_candidates.csv")
    report = (output_root / "hybrid_optimizer_report.md").read_text(encoding="utf-8")

    assert summary["candidate_count"] == len(candidates)
    assert {"surrogate", "repair", "exploration"} <= set(candidates["candidate_source"])
    assert "fallback_insufficient_data" in set(candidates["model_status"])
    for column in [
        "candidate_id",
        "candidate_source",
        "parameters_json",
        "changed_parameters",
        "predicted_overall_score",
        "predicted_Max_overlap_ratio",
        "predicted_Max_ripple",
        "predicted_Max_voltage_loss",
        "predicted_Delay_std",
        "predicted_hard_constraint_passed",
        "pareto_rank",
        "pareto_is_front",
        "candidate_style",
        "repair_operator",
        "trigger_metric",
        "repair_rationale",
        "recommendation_rationale",
        "data_source",
        "engineering_validity",
        "evidence_level",
        "simulation_backend",
        "mock_used",
    ]:
        assert column in candidates.columns
    assert all(candidates["parameters_json"].astype(str).str.len() > 2)
    assert all(candidates["recommendation_rationale"].astype(str).str.len() > 0)
    assert (output_root / "pareto_front.csv").exists()
    assert (output_root / "pareto_summary.json").exists()
    assert "GOA simulation-only optimizer" in report
    assert "no real ngspice required" in report


def test_hybrid_goa_cli_smoke_generates_report(tmp_path: Path):
    leaderboard = tmp_path / "optimization_leaderboard.csv"
    pd.DataFrame(
        [
            {
                "candidate_id": "seed_1",
                "overall_score": 70.0,
                "Max_overlap_ratio": 0.2,
                "Max_ripple": 0.3,
                "Max_voltage_loss": 0.2,
                "Delay_std": 0.1,
                "hard_constraint_passed": True,
                "target_passed": True,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"clk_delay": 1.0, "load_cap": 1.0, "drive_width": 1.0}),
            },
            {
                "candidate_id": "seed_2",
                "overall_score": 55.0,
                "Max_overlap_ratio": 0.7,
                "Max_ripple": 0.6,
                "Max_voltage_loss": 0.4,
                "Delay_std": 0.3,
                "hard_constraint_passed": False,
                "target_passed": False,
                "rank_status": "evaluated",
                "parameters_json": json.dumps({"clk_delay": 1.2, "load_cap": 1.2, "drive_width": 0.8}),
            },
        ]
    ).to_csv(leaderboard, index=False, encoding="utf-8-sig")
    param_space = tmp_path / "params.yaml"
    param_space.write_text(
        """
parameters:
  clk_delay:
    values: [0.8, 1.0, 1.2]
  load_cap:
    values: [0.8, 1.0, 1.2]
  drive_width:
    values: [0.8, 1.0, 1.2]
""",
        encoding="utf-8",
    )
    output_root = tmp_path / "cli_hybrid"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "hybrid-goa-optimize",
            "--leaderboard",
            str(leaderboard),
            "--param-space",
            str(param_space),
            "--output-root",
            str(output_root),
            "--max-candidates",
            "6",
            "--seed",
            "5",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output_root / "hybrid_candidates.csv").exists()
    assert (output_root / "pareto_front.csv").exists()
    assert (output_root / "hybrid_optimizer_report.md").exists()
