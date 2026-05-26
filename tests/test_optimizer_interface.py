import subprocess
import sys
import pandas as pd

from goa_eval.optimizer import (
    OptimizationRequest,
    OptimizationResult,
    CircuitPilotOptimizer,
    generate_next_round_candidates,
    load_param_space,
    propose_candidates,
    rank_candidates,
)


def test_optimizer_interface_selects_best_history_row():
    request = OptimizationRequest(
        parameter_space={"vdd": [10.0, 15.0]},
        objective="overall_score",
        history=[
            {"run_id": "run_001", "overall_score": 48.0, "hard_constraint_passed": False, "vdd": 10.0},
            {"run_id": "run_002", "overall_score": 72.0, "hard_constraint_passed": True, "vdd": 15.0},
        ],
    )
    optimizer = CircuitPilotOptimizer()

    result = optimizer.optimize(request)

    assert result.status == "ok"
    assert result.best_parameters == {"vdd": 15.0}
    assert result.best_run_id == "run_002"
    assert result.next_candidates


def test_optimizer_rule_helpers_propose_and_rank_candidates(tmp_path):
    param_space = tmp_path / "param_space.yaml"
    param_space.write_text(
        """
parameters:
  C_store: [1pF, 2pF]
  R_driver: [10k, 8k]
  W_nmos: [1u, 1.5u]
""".strip(),
        encoding="utf-8",
    )
    loaded = load_param_space(param_space)
    recommendations = [
        {
            "recommendation_id": "ripple_hold_window_review",
            "trigger_metric": "Max_ripple",
            "next_tuning_actions": "增大保持电容或检查泄漏路径。",
        },
        {
            "recommendation_id": "delay_drive_load_review",
            "trigger_metric": "Delay_mean",
            "next_tuning_actions": "调整驱动能力。",
        },
    ]

    candidates = propose_candidates(loaded, recommendations)
    ranked = rank_candidates(candidates)

    assert any(candidate["parameter"] == "C_store" for candidate in candidates)
    assert any(candidate["parameter"] == "R_driver" for candidate in candidates)
    assert ranked[0]["priority"] >= ranked[-1]["priority"]


def test_closed_loop_optimizer_builds_next_round_candidates_from_leaderboard(tmp_path):
    param_space = tmp_path / "param_space.yaml"
    param_space.write_text(
        """
parameters:
  C_store:
    values: [1pF, 2pF, 3pF]
  R_driver:
    values: [8k, 10k, 12k]
  W_nmos:
    values: [1u, 1.5u]
""".strip(),
        encoding="utf-8",
    )
    leaderboard = pd.DataFrame(
        [
            {"run_id": "run_001", "overall_score": 42.0, "hard_constraint_passed": False, "C_store": "1pF", "R_driver": "10k", "W_nmos": "1u"},
            {"run_id": "run_002", "overall_score": 64.0, "hard_constraint_passed": False, "C_store": "2pF", "R_driver": "10k", "W_nmos": "1u"},
        ]
    )

    candidates = generate_next_round_candidates(
        param_space=load_param_space(param_space),
        leaderboard=leaderboard,
        max_candidates=4,
    )

    assert len(candidates) == 4
    assert candidates[0]["source_run_id"] == "run_002"
    assert candidates[0]["engineering_validity"] == "simulation_only"
    assert "parameters_json" in candidates[0]
    assert any(candidate["candidate_kind"] == "two_parameter_combo" for candidate in candidates)


def test_optimize_loop_cli_writes_leaderboard_and_candidates(tmp_path):
    param_space = tmp_path / "param_space.yaml"
    param_space.write_text(
        """
parameters:
  C_store:
    values: [1pF, 2pF, 3pF]
  R_driver:
    values: [8k, 10k, 12k]
""".strip(),
        encoding="utf-8",
    )
    leaderboard = tmp_path / "leaderboard.csv"
    pd.DataFrame(
        [
            {"run_id": "run_001", "overall_score": 55.0, "hard_constraint_passed": False, "C_store": "1pF", "R_driver": "10k"},
            {"run_id": "run_002", "overall_score": 75.0, "hard_constraint_passed": True, "C_store": "2pF", "R_driver": "10k"},
        ]
    ).to_csv(leaderboard, index=False)
    out = tmp_path / "closed_loop"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "goa_eval.cli",
            "optimize-loop",
            "--leaderboard",
            str(leaderboard),
            "--param-space",
            str(param_space),
            "--output-dir",
            str(out),
            "--max-candidates",
            "3",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out / "optimization_leaderboard.csv").exists()
    assert (out / "next_candidates.csv").exists()
    assert (out / "next_candidates.md").exists()
    candidates = pd.read_csv(out / "next_candidates.csv")
    assert len(candidates) == 3
    assert {"candidate_id", "source_run_id", "parameters_json", "changed_parameters", "engineering_validity"} <= set(candidates.columns)
